#!/usr/bin/env python3
"""Reverse the most recent filing batch, and refuse when reversing would lie.

Scope is deliberately narrow: **the most recent `## batch` block, and only that
one.** Chained or selective undo is excluded because undoing a batch from three
weeks ago, when two later batches touched the same lesson, has no sensible
outcome.

Renumber and code-rename blocks are never undone. A wrong renumber is fixed by
another renumber.

Undo **never deletes.** Files move back to where they came from; copies and
files this plugin created move to `_Inbox/_undone/`, which intake never picks up
again. The vault is iCloud-synced: a deletion reaches every device in seconds
and gets there before the student notices the mistake.

The refusals all have the same shape: something downstream now depends on the
filed material, so putting it back would leave a note, a question bank or an
index referring to a file that is no longer there.

CLI:
    undo.py inspect --course <path>
    undo.py apply   --course <path>
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import naming                                                   # noqa: E402
from renumber import parse_filing_log                           # noqa: E402
from vault import read_frontmatter, write_frontmatter           # noqa: E402
from runstamp import norm_run                                      # noqa: E402

UNDONE = Path('_Inbox') / '_undone'
MTIME_GRACE = timedelta(seconds=120)


def _parse_list(raw: str):
    raw = (raw or '').strip()
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        pass
    if raw.startswith('[') and raw.endswith(']'):
        inner = raw[1:-1].strip()
        return [x.strip().strip('"') for x in inner.split(',') if x.strip()]
    return [raw]


def _ts(value: str):
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(value[:len(fmt) + 2], fmt)
        except Exception:
            continue
    return None


def find_batch(course: Path) -> dict:
    blocks = parse_filing_log(course)
    # A batch already reversed is not a candidate: undoing it twice would move
    # the restored files somewhere they never were.
    batches = [b for b in blocks if b['kind'] == 'batch'
               and b['fields'].get('status') != 'undone']
    if not batches:
        return {'found': False,
                'reason': 'no filing batch left to undo (the most recent one was '
                          'already reversed, or there has never been one)'}
    last = batches[-1]
    after = blocks[blocks.index(last) + 1:]
    return {'found': True, 'block': last,
            'blocks_after': [{'kind': b['kind'], 'id': b['id'],
                              'timestamp': b['timestamp']} for b in after]}


def inspect(course: Path | str) -> dict:
    course = Path(course)
    found = find_batch(course)
    if not found['found']:
        return {'can_undo': False, 'reason': found['reason']}
    block = found['block']
    refusals = []

    if block['fields'].get('status') == 'open':
        return {'can_undo': False, 'batch': block['id'],
                'reason': 'this batch is still open, which means an interrupted run. '
                          'It is reported, never silently undone: complete it or roll '
                          'it back explicitly.'}

    for b in found['blocks_after']:
        if b['kind'] in ('renumber', 'code-rename'):
            refusals.append(
                f'a {b["kind"]} block ({b["id"]}) follows this batch in the log, so '
                'the paths and the overview row it recorded no longer match the disk')

    ts = _ts(block['timestamp'])
    moves = [(r[0], r[1]) for r in block['table'] if len(r) >= 2
             and r[0] not in ('Source',)]

    lessons = set()
    for _, dest in moves:
        parts = Path(dest).parts
        if len(parts) >= 2 and parts[0] in ('Lessons', 'Tutorials'):
            parsed = naming.parse_lesson_folder(parts[1])
            if parsed:
                lessons.add(('L' if parts[0] == 'Lessons' else 'T') + parsed['num'])

    # a filed file that has been edited since it moved
    for _, dest in moves:
        p = course / dest
        if not p.exists():
            refusals.append(f'{dest} is no longer where the batch put it')
            continue
        # A move preserves mtime, so an untouched filed file is normally *older*
        # than the batch. The grace window absorbs the sub-second difference
        # between a file written moments before the batch opened and the batch's
        # second-resolution timestamp; a real edit is minutes or hours later.
        if ts and datetime.fromtimestamp(p.stat().st_mtime) > ts + MTIME_GRACE:
            refusals.append(f'{dest} has been modified since it was filed')

    # the notes skill has run on an affected lesson
    for key in sorted(lessons):
        for notes in course.rglob(f'*_{key}_Final_notes.md'):
            try:
                fm, _ = read_frontmatter(notes)
            except Exception:
                continue
            run = _ts(norm_run(fm.get('run') or fm.get('generated')))
            if run and ts and run > ts:
                refusals.append(
                    f'the notes for {key} were written after this batch and depend on '
                    'the filed material')

    # a lesson listed in an appended assignment row, or citing a newly built index
    for raw in _parse_list(block['fields'].get('assignment_rows', '')):
        for key in sorted({k for k in _lesson_tokens(str(raw))}):
            for notes in course.rglob(f'*_{key}_Final_notes.md'):
                refusals.append(
                    f'{key} has notes and was listed in an assignment row this batch '
                    'appended; its assessed-in callouts depend on that row')
    for index in _parse_list(block['fields'].get('built_indexes', '')):
        book = Path(str(index)).name.replace('.index.md', '')
        for notes in course.rglob('*_Final_notes.md'):
            try:
                fm, _ = read_frontmatter(notes)
            except Exception:
                continue
            if any(book.lower() in str(s).lower() for s in (fm.get('sources') or [])):
                refusals.append(
                    f'{notes.name} cites {book}, whose index this batch built')

    # the revision skill has used a filed exam or graded an attempt
    profile = course / '.data' / 'exam_profile.json'
    filed_names = {Path(d).name for _, d in moves}
    if profile.is_file():
        try:
            blob = profile.read_text(encoding='utf-8')
        except OSError:
            blob = ''
        for name in filed_names:
            if naming.strip_code_token(name) in blob or name in blob:
                refusals.append(f'{name} is recorded in the revision skill\'s exam '
                                'profile')
    for _, dest in moves:
        name = Path(dest).name
        if '_Attempt_' in name:
            stem = Path(dest).with_suffix('').name.replace('_Attempt_', '_Feedback_')
            if any((course / 'Exams' / 'Mock_exams').glob(stem + '*')):
                refusals.append(f'{name} has been graded; its feedback file exists')

    return {'can_undo': not refusals, 'batch': block['id'],
            'timestamp': block['timestamp'],
            'mode': block['fields'].get('mode', 'move'),
            'moves': moves, 'lessons': sorted(lessons),
            'refusals': sorted(set(refusals))}


def _lesson_tokens(text: str):
    import re
    return re.findall(r'\b([LT]\d{2})\b', text)


def apply(course: Path | str) -> dict:
    course = Path(course)
    pre = inspect(course)
    if not pre.get('can_undo'):
        return {'undone': False, **pre}

    block = find_batch(course)['block']
    fields = block['fields']
    mode = fields.get('mode', 'move')
    source_root = fields.get('source_root', '_Inbox')
    undone_dir = course / UNDONE
    undone_dir.mkdir(parents=True, exist_ok=True)

    restored, set_aside, notes = [], [], []

    for src, dest in pre['moves']:
        p = course / dest
        if not p.exists():
            continue
        if mode == 'copy':
            target = undone_dir / p.name
            # the originals still exist outside the vault, so the vault copy is
            # set aside rather than moved back on top of them
            target = _free_name(target)
            shutil.move(str(p), str(target))
            set_aside.append(str(target.relative_to(course)))
        else:
            back = Path(src) if Path(src).is_absolute() else course / src
            back.parent.mkdir(parents=True, exist_ok=True)
            if back.exists():
                back = _free_name(back)
                notes.append(f'{src} already existed; restored as {back.name}')
            os.replace(p, back)
            restored.append(str(back))

    for item in _parse_list(fields.get('appended_lines', '')):
        if isinstance(item, dict):
            f, line = item.get('file'), item.get('line')
        else:
            continue
        p = course / f
        if not p.is_file():
            continue
        lines = p.read_text(encoding='utf-8').splitlines()
        kept = [l for l in lines if l.strip() != str(line).strip()]
        p.write_text('\n'.join(kept) + '\n', encoding='utf-8')

    overview = course / 'Weekly_overview.md'
    row = fields.get('overview_row', '').strip().strip('"')
    before = fields.get('overview_row_before', '').strip().strip('"')
    if row and overview.is_file():
        fm, body = read_frontmatter(overview)
        lines = body.rstrip('\n').splitlines()
        out = []
        for line in lines:
            if line.strip() == row:
                if before:
                    out.append(before)
                continue
            out.append(line)
        write_frontmatter(overview, fm, '\n'.join(out) + '\n')

    for rel in _parse_list(fields.get('assignment_rows', '')):
        if overview.is_file():
            fm, body = read_frontmatter(overview)
            lines = [l for l in body.rstrip('\n').splitlines()
                     if l.strip() != str(rel).strip()]
            write_frontmatter(overview, fm, '\n'.join(lines) + '\n')

    for rel in (_parse_list(fields.get('built_indexes', ''))
                + _parse_list(fields.get('created_files', ''))):
        p = course / str(rel)
        if p.is_file():
            target = _free_name(undone_dir / p.name)
            shutil.move(str(p), str(target))
            set_aside.append(str(target.relative_to(course)))

    removed_folders = []
    for rel in sorted(_parse_list(fields.get('created_folders', '')), reverse=True):
        p = course / str(rel)
        if p.is_dir() and not any(p.iterdir()):
            try:
                p.rmdir()
                removed_folders.append(str(rel))
            except OSError as e:
                notes.append(f'{rel} could not be removed: {e}')

    _mark_undone(course, block['id'])

    return {'undone': True, 'batch': block['id'], 'restored': restored,
            'set_aside_in_undone': set_aside, 'removed_empty_folders': removed_folders,
            'notes': notes,
            'reminder': 'files in _Inbox/_undone/ are never picked up by intake again; '
                        'refile them explicitly when you want them back'}


def _free_name(path: Path) -> Path:
    if not path.exists():
        return path
    for n in range(2, 100):
        cand = path.with_name(f'{path.stem}_{n}{path.suffix}')
        if not cand.exists():
            return cand
    return path.with_name(path.stem + '_x' + path.suffix)


def _mark_undone(course: Path, batch_id: str):
    log = course / '_Inbox' / '_filing_log.md'
    text = log.read_text(encoding='utf-8')
    marker = f'· id {batch_id}'
    idx = text.find(marker)
    if idx < 0:
        return
    head, tail = text[:idx], text[idx:]
    tail = tail.replace('status: complete', 'status: undone', 1)
    log.write_text(head + tail, encoding='utf-8')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('inspect', 'apply'):
        p = sub.add_parser(name); p.add_argument('--course', required=True)
    args = ap.parse_args(argv)
    out = inspect(args.course) if args.cmd == 'inspect' else apply(args.course)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
