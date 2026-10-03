#!/usr/bin/env python3
"""Fix a misreading at the root, and never assert what a source does not say.

An erratum repairs the **extraction**, not the notes: B applies it at the end of
Pass A, so every later reader of `.work/A_*.md` — C, E and D itself — sees the
corrected text instead of the OCR slip. That is why it is worth the cost, and
the cost is real: an erratum enters the `inputs` of every lesson citing the
source, so those lessons go stale and need re-running.

The one rule that keeps this honest: **an erratum exists only for a misreading**
(spec section 6.2, D-21). A source that is genuinely wrong is corrected in the
notes with `[source error: <ID>]` and a footnote, and the extraction stays a
faithful record of what the source says. `[unverified: <ID>]` never produces one
either, because an erratum asserts what the source says and an unverified
correction is precisely the case where nobody looked.

**Reach follows the source, not the lesson** (D-29). A lesson-local source is
read by that lesson only; a course-level one — a book, or anything outside the
lesson folder — is repaired wherever it is cited, and the `lesson` field becomes
provenance. The cost is stated before the student confirms, because "L03, L05
and L09 now need re-running" is not a detail to discover afterwards.

Statuses are derived from the extractions, never stored by hand and never
written by B:

    active     the erratum still applies (the item carries `wrong`, or carries
               `right` with the `errata` tag)
    obsolete   the item carries `right` without the tag: the source was fixed
    stale      neither text is in the item: the source changed under it
    withdrawn  withdrawn by the student, or reversed by `undo`

CLI:
    errata.py list     --course <path>
    errata.py reach    --course <path> --source <rel path> [--lesson L03]
    errata.py statuses --course <path> [--apply]
    errata.py add      --course <path> --entry <entry.json> [--apply]
    errata.py withdraw --course <path> --id e-0002 [--apply]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import log as dlog                                                # noqa: E402
import naming                                                     # noqa: E402
from vault import read_frontmatter                                # noqa: E402

ITEM_RE = re.compile(r'^###\s+(?P<id>\S+)\s*$', re.MULTILINE)
TAGS_RE = re.compile(r'^tags:\s*\[(?P<tags>.*?)\]\s*$', re.MULTILINE)

ERRATA_NAME = 'source_errata.json'
STATUSES = ('active', 'obsolete', 'stale', 'withdrawn')


def errata_path(course: Path | str) -> Path:
    return Path(course) / '.data' / ERRATA_NAME


def load(course: Path | str) -> dict:
    path = errata_path(course)
    if not path.is_file():
        return {'applied_renumbers': [], 'errata': []}
    data = json.loads(path.read_text(encoding='utf-8'))
    data.setdefault('applied_renumbers', [])
    data.setdefault('errata', [])
    return data


def save(course: Path | str, data: dict, apply: bool = False) -> dict:
    path = errata_path(course)
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                       encoding='utf-8')
        tmp.replace(path)
    return {'file': str(path), 'written': apply}


# --------------------------------------------------------------------------
# reach


def _lesson_folders(course: Path):
    for parent in ('Lessons', 'Tutorials'):
        root = course / parent
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            parsed = naming.parse_lesson_folder(child.name)
            if parsed:
                yield ('L' if parent == 'Lessons' else 'T') + parsed['num'], child


def _notes_of(folder: Path) -> Path | None:
    final = folder / 'Final_notes'
    if not final.is_dir():
        return None
    hits = sorted(final.glob('*_Final_notes.md'))
    return hits[0] if hits else None


def reach(course: Path | str, source: str, lesson: str | None = None) -> dict:
    """Which lessons an erratum for this source touches, and what it costs them."""
    course = Path(course)
    rel = Path(source)
    local = rel.parts and rel.parts[0] in ('Content', 'Articles')
    wanted = naming.strip_code_token(rel.name)

    citing = []
    for key, folder in _lesson_folders(course):
        notes = _notes_of(folder)
        if notes is None:
            continue
        try:
            fm, _ = read_frontmatter(notes)
        except Exception:
            continue
        for entry in (fm.get('sources') or []):
            name = naming.strip_code_token(Path(str(entry).split('#')[0]).name)
            if name == wanted:
                citing.append({'lesson': key,
                               'notes': str(notes.relative_to(course)),
                               'run': fm.get('run')})
                break

    if local:
        citing = [c for c in citing if not lesson or c['lesson'] == lesson]

    return {'source': source, 'scope': 'lesson-local' if local else 'course-level',
            'lesson': lesson, 'applies_in': [c['lesson'] for c in citing],
            'citing': citing,
            'cost': ('no other lesson reads this file, so nothing else goes stale'
                     if local else
                     'every lesson above cites this source: the erratum enters their '
                     'inputs, so their notes become stale and need re-running')}


# --------------------------------------------------------------------------
# statuses from the extractions


def _extraction_items(course: Path, folder: Path, source: str) -> dict:
    from source_hash import split_entry
    path, _ = split_entry(source)
    ex = folder / '.work' / ('A_' + naming.slugify(path, cap=False) + '.md')
    if not ex.is_file():
        return {}
    text = ex.read_text(encoding='utf-8')
    out = {}
    marks = list(ITEM_RE.finditer(text))
    for n, m in enumerate(marks):
        end = marks[n + 1].start() if n + 1 < len(marks) else len(text)
        block = text[m.end():end]
        tm = TAGS_RE.search(block)
        tags = [t.strip().strip('"\'') for t in tm.group('tags').split(',')] if tm else []
        body = TAGS_RE.sub('', block).strip()
        out[m.group('id')] = {'tags': [t for t in tags if t], 'text': body,
                              'file': str(ex.relative_to(course))}
    return out


def derive_status(item: dict | None, entry: dict) -> tuple[str, str]:
    if entry.get('status') == 'withdrawn':
        return 'withdrawn', 'withdrawn by you or reversed by undo'
    if item is None:
        return entry.get('status', 'active'), \
            'the extraction for this source is not present in this run'
    text = item['text']
    has_right = entry.get('right', '') and entry['right'] in text
    has_wrong = entry.get('wrong', '') and entry['wrong'] in text
    if has_right and 'errata' in item['tags']:
        return 'active', 'applied in the latest run'
    if has_right:
        return 'obsolete', 'the source itself now carries the corrected text'
    if has_wrong:
        return 'active', 'not applied yet: re-run course-notes for this lesson'
    return 'stale', ('neither text is in the item any more: the source changed, so '
                     'nothing was repaired. Move the erratum to a new id or '
                     'withdraw it.')


def statuses(course: Path | str, apply: bool = False) -> dict:
    course = Path(course)
    data = load(course)
    folders = dict(_lesson_folders(course))
    rows, changed = [], []
    for entry in data['errata']:
        lessons = reach(course, entry.get('source', ''),
                        entry.get('lesson'))['applies_in'] or [entry.get('lesson')]
        item, seen_in = None, None
        for key in lessons:
            folder = folders.get(key)
            if folder is None:
                continue
            items = _extraction_items(course, folder, entry.get('source', ''))
            if entry.get('item') in items:
                item, seen_in = items[entry['item']], key
                break
        status, why = derive_status(item, entry)
        rows.append({'id': entry.get('id'), 'item': entry.get('item'),
                     'source': entry.get('source'), 'was': entry.get('status'),
                     'now': status, 'why': why, 'seen_in': seen_in,
                     'applies_in': lessons})
        if status != entry.get('status'):
            changed.append(entry.get('id'))
            entry['status'] = status
    if changed:
        save(course, data, apply)
    return {'errata': rows, 'changed': changed, 'written': apply and bool(changed)}


# --------------------------------------------------------------------------
# writing


def add(course: Path | str, entry: dict, apply: bool = False) -> dict:
    """Allocate an id and record the erratum. Refuses anything but a misreading."""
    course = Path(course)
    if entry.get('kind') == 'source_error' or entry.get('source_is_wrong'):
        return {'ok': False,
                'reason': 'a source that is genuinely wrong is corrected in the notes '
                          'with [source error: <ID>] and a footnote; the extraction '
                          'stays a faithful record of what the source says'}
    if entry.get('basis') == 'user' and not entry.get('checked'):
        return {'ok': False,
                'reason': 'an unverified correction never produces an erratum: an '
                          'erratum asserts what the source says, and nobody looked'}
    for field in ('source', 'item', 'wrong', 'right', 'evidence'):
        if not entry.get(field):
            return {'ok': False, 'reason': f'an erratum needs {field}'}

    data = load(course)
    state = dlog.read_state(course)
    eid = entry.get('id') or dlog.allocate(state, 'e')[0]
    row = {'id': eid, 'date': entry.get('date') or date.today().isoformat(),
           'lesson': entry.get('lesson'), 'source': entry['source'],
           'item': entry['item'], 'wrong': entry['wrong'], 'right': entry['right'],
           'evidence': entry['evidence'],
           'correction': entry.get('correction'), 'status': 'active'}
    data['errata'].append(row)
    save(course, data, apply)
    if not entry.get('id'):
        dlog.write_state(course, state, apply)
    return {'ok': True, 'erratum': row,
            'reach': reach(course, row['source'], row['lesson']), 'written': apply}


def withdraw(course: Path | str, eid: str, apply: bool = False) -> dict:
    data = load(course)
    hit = next((e for e in data['errata'] if e.get('id') == eid), None)
    if hit is None:
        return {'ok': False, 'reason': f'{eid} is not in {ERRATA_NAME}'}
    hit['status'] = 'withdrawn'
    save(course, data, apply)
    return {'ok': True, 'id': eid, 'written': apply,
            'note': 'the extraction returns to its previous state only when '
                    'course-notes runs again'}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list'); p.add_argument('--course', required=True)
    p = sub.add_parser('reach')
    p.add_argument('--course', required=True); p.add_argument('--source', required=True)
    p.add_argument('--lesson')
    p = sub.add_parser('statuses')
    p.add_argument('--course', required=True); p.add_argument('--apply', action='store_true')
    p = sub.add_parser('add')
    p.add_argument('--course', required=True); p.add_argument('--entry', required=True)
    p.add_argument('--apply', action='store_true')
    p = sub.add_parser('withdraw')
    p.add_argument('--course', required=True); p.add_argument('--id', required=True)
    p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)

    if args.cmd == 'list':
        out = load(args.course)
    elif args.cmd == 'reach':
        out = reach(args.course, args.source, args.lesson)
    elif args.cmd == 'statuses':
        out = statuses(args.course, args.apply)
    elif args.cmd == 'add':
        out = add(args.course, json.loads(Path(args.entry).read_text(encoding='utf-8')),
                  args.apply)
    else:
        out = withdraw(args.course, args.id, args.apply)

    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
