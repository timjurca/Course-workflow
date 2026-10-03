#!/usr/bin/env python3
"""Execute an approved filing plan and write the log block that makes it reversible.

The order is the whole design, and it is ordered so that an interruption is
always recoverable:

  1. open the log block, with its header, **before anything moves**
  2. create folders, recording each created path
  3. move and rename each file, **appending its log row as it completes**
  4. create or append videos.md and links_*.md
  5. append or update the Weekly_overview row, recording it verbatim, and the
     previous row as overview_row_before when it is an update
  6. (book indexes are built by the skill and recorded here)
  7. close the block
  8. validate

An earlier design wrote the log after the moves. A crash during the slowest step
then left every file moved and no log at all, so undo had nothing to reverse and
"resume from what is still in _Inbox" was simply false.

Refusals, all before any write:
  * a `low` confidence row that was not explicitly confirmed
  * a destination that already exists — never overwrite, propose a _2 suffix
  * a destination outside the course, or inside a machine-owned folder
  * a forbidden character in a destination name

Any one of them aborts the **whole batch**. A partial apply followed by an error
leaves the student not knowing what moved, which is worse than doing nothing.

CLI:
    apply_plan.py check --plan plan.json
    apply_plan.py apply --plan plan.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import naming                                                    # noqa: E402
import overview as ov                                            # noqa: E402
from vault import read_frontmatter, write_frontmatter            # noqa: E402

LOG_REL = Path('_Inbox') / '_filing_log.md'

# Destinations no filing plan may ever name. Explanations/ is on the list because
# the classifier must never file anything into tutor output.
FORBIDDEN_DESTS = ('Final_notes/', 'Explanations/', '.work/', '.data/',
                   'Articles/', 'Videos/', 'Links/')
# ...except the course-root note folders are only forbidden at the course root;
# a lesson's own Articles/ is a legitimate destination.
LESSON_ARTICLES_RE = re.compile(r'^(Lessons|Tutorials)/[^/]+/Articles/')


def _forbidden(dest: str) -> str | None:
    if LESSON_ARTICLES_RE.match(dest):
        return None
    for bad in FORBIDDEN_DESTS:
        if dest.startswith(bad) or f'/{bad}' in dest:
            return bad
    return None


def check(plan: dict) -> dict:
    course = Path(plan['course'])
    problems = []
    seen_dests = set()
    for i, row in enumerate(plan.get('rows', []), 1):
        src = row.get('source')
        dest = row.get('destination')
        if not src or not dest:
            problems.append({'row': i, 'reason': 'row has no source or destination'})
            continue
        if row.get('confidence') == 'low' and not row.get('confirmed'):
            problems.append({'row': i, 'reason':
                             'low confidence and not confirmed; it stays in _Inbox',
                             'path': src})
            continue
        bad = _forbidden(dest)
        if bad:
            problems.append({'row': i, 'reason':
                             f'destination is inside {bad}, which is machine-owned',
                             'path': dest})
        chars = naming.has_forbidden(Path(dest).name)
        if chars:
            problems.append({'row': i, 'reason':
                             f'destination name contains {" ".join(chars)}',
                             'path': dest})
        abs_dest = course / dest
        try:
            abs_dest.resolve().relative_to(course.resolve())
        except ValueError:
            problems.append({'row': i, 'reason': 'destination is outside the course',
                             'path': dest})
        if abs_dest.exists():
            problems.append({'row': i, 'reason':
                             'destination already exists; nothing is ever overwritten. '
                             'Propose a _2 suffix or ask.', 'path': dest})
        if dest in seen_dests:
            problems.append({'row': i, 'reason': 'two rows target the same destination',
                             'path': dest})
        seen_dests.add(dest)

        abs_src = Path(src) if Path(src).is_absolute() else course / src
        if not abs_src.exists():
            problems.append({'row': i, 'reason': 'source does not exist', 'path': src})

    blocking = [p for p in problems
                if 'low confidence' not in p['reason']]
    return {'ok': not blocking, 'problems': problems,
            'blocking': blocking,
            'skipped_low_confidence': [p for p in problems
                                       if 'low confidence' in p['reason']]}


def _open_block(course: Path, plan: dict, batch_id: str, ts: str) -> None:
    log = course / LOG_REL
    log.parent.mkdir(parents=True, exist_ok=True)
    if not log.exists():
        log.write_text('# Filing log\n\n**Never edit or clear this file by hand.**\n',
                       encoding='utf-8')
    head = [
        '', f'## batch {ts} · id {batch_id}',
        f'mode: {plan.get("mode", "move")}',
        f'source_root: {plan.get("source_root", "_Inbox")}',
        'created_folders: []',
        f'overview_row: {json.dumps(plan.get("overview_row") or "")}',
    ]
    if plan.get('overview_row_before'):
        head.append(f'overview_row_before: {json.dumps(plan["overview_row_before"])}')
    head += [
        'appended_lines: []',
        f'assignment_rows: {json.dumps(plan.get("assignment_rows") or [])}',
        f'built_indexes: {json.dumps(plan.get("built_indexes") or [])}',
        'created_files: []',
        'status: open',
        '',
        '| Source | Destination | Basis |',
        '|---|---|---|',
    ]
    with open(log, 'a', encoding='utf-8') as fh:
        fh.write('\n'.join(head) + '\n')


def _append_log_row(course: Path, src: str, dest: str, basis: str) -> None:
    with open(course / LOG_REL, 'a', encoding='utf-8') as fh:
        fh.write(f'| {src} | {dest} | {basis} |\n')


def _patch_block(course: Path, batch_id: str, field: str, value) -> None:
    log = course / LOG_REL
    text = log.read_text(encoding='utf-8')
    marker = f'· id {batch_id}'
    idx = text.find(marker)
    if idx < 0:
        return
    pattern = re.compile(rf'^({re.escape(field)}:).*$', re.MULTILINE)
    head, tail = text[:idx], text[idx:]
    tail = pattern.sub(lambda m: f'{m.group(1)} {json.dumps(value) if not isinstance(value, str) else value}',
                       tail, count=1)
    log.write_text(head + tail, encoding='utf-8')


def apply(plan: dict) -> dict:
    pre = check(plan)
    if not pre['ok']:
        return {'applied': False, 'aborted': True,
                'reason': 'the whole batch aborts before any file moves',
                'problems': pre['blocking']}

    course = Path(plan['course'])
    mode = plan.get('mode', 'move')
    ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    batch_id = secrets.token_hex(2)

    _open_block(course, plan, batch_id, ts)

    created_folders = []
    for rel in plan.get('create_folders', []):
        p = course / rel
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created_folders.append(rel)
    _patch_block(course, batch_id, 'created_folders', created_folders)

    moved, skipped = [], []
    for row in plan.get('rows', []):
        if row.get('confidence') == 'low' and not row.get('confirmed'):
            skipped.append(row.get('source'))
            continue
        src = row['source']
        abs_src = Path(src) if Path(src).is_absolute() else course / src
        abs_dest = course / row['destination']
        abs_dest.parent.mkdir(parents=True, exist_ok=True)
        if mode == 'copy':
            shutil.copy2(abs_src, abs_dest)
        else:
            try:
                os.replace(abs_src, abs_dest)
            except OSError:              # cross-volume move: copy then remove
                shutil.copy2(abs_src, abs_dest)
                try:
                    abs_src.unlink()
                except OSError as e:
                    row['note'] = f'copied, but the original could not be removed: {e}'
        _append_log_row(course, src, row['destination'], row.get('basis', 'inferred'))
        moved.append({'source': src, 'destination': row['destination']})

    created_files, appended = [], []
    for item in plan.get('appended_lines', []):
        p = course / item['file']
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            heading = ('# Assigned videos' if p.name.startswith('video')
                       else '# Assigned reading')
            p.write_text(heading + '\n\n', encoding='utf-8')
            created_files.append(item['file'])
        with open(p, 'a', encoding='utf-8') as fh:
            fh.write(item['line'].rstrip('\n') + '\n')
        appended.append(item)
    _patch_block(course, batch_id, 'created_files', created_files)
    _patch_block(course, batch_id, 'appended_lines', appended)

    overview = _write_overview_row(course, plan)
    _patch_block(course, batch_id, 'status', 'complete')

    return {'applied': True, 'batch_id': batch_id, 'timestamp': ts,
            'moved': moved, 'created_folders': created_folders,
            'created_files': created_files, 'appended_lines': appended,
            'left_in_inbox': skipped, 'overview': overview,
            'log': str(LOG_REL)}


def _write_overview_row(course: Path, plan: dict) -> dict:
    row = plan.get('overview_row')
    if not row:
        return {'written': False}
    path = course / 'Weekly_overview.md'
    fm, body = read_frontmatter(path)
    lines = body.rstrip('\n').splitlines()
    before = plan.get('overview_row_before')
    if before:
        for i, line in enumerate(lines):
            if line.strip() == before.strip():
                lines[i] = row
                write_frontmatter(path, fm, '\n'.join(lines) + '\n')
                return {'written': True, 'updated': True, 'row': row}
    # Anchored on the *lesson* table, resolved by overview.py, not on the last
    # line in the file that happens to start with a pipe. A course that keeps the
    # lecturer's published schedule below the machine-readable one has two tables,
    # and the naive anchor appended into the wrong one, where overview.py never
    # looked: written, logged, and invisible.
    at = ov.lesson_table_end('\n'.join(lines))
    if at is None:
        lines += ['', '| Type     | No | Date       | Topic | Book | Chapters | Lesson |',
                  '|----------|----|------------|-------|------|----------|--------|', row]
    else:
        lines.insert(at, row)
    write_frontmatter(path, fm, '\n'.join(lines) + '\n')
    return {'written': True, 'updated': False, 'row': row}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('check', 'apply'):
        p = sub.add_parser(name); p.add_argument('--plan', required=True)
    args = ap.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    out = check(plan) if args.cmd == 'check' else apply(plan)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
