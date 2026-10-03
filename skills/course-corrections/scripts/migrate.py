#!/usr/bin/env python3
"""Apply A's renumber blocks to D's own records, once, before any write.

A renumbers a lesson, renames the folders and the generated files, and writes a
`## renumber` block to its filing log. It never edits another skill's data file
(note-invariants section 17), so every skill migrates its own records. The rule
itself lives in `shared/scripts/renumber.py` and is not re-implemented here:
this module supplies only D's **field mapper** and D's idempotency bookkeeping.

What D holds that carries a lesson number:

    source_errata.json     `lesson`
    corrections.json       `lesson`, `lessons`, and the recorded archive and
                           file names of the last run, which carry an `L<NN>`
                           token that A renamed at the same time
    the correction logs     the `file:` and `lesson:` values, and `Used in L<NN>`

Two idempotency lists, not one, and that is deliberate. A chained renumber
(`L03 -> L04`, `L04 -> L05`) is **not** idempotent, so a run interrupted between
two files must not leave one of them able to be remapped a second time. Each
JSON file therefore carries its own `applied_renumbers`, and each Markdown log
carries an `<!-- applied_renumbers: ... -->` marker in its own header. A file is
migrated and stamped in the same write.

Source paths inside an erratum are lesson-relative (`Content/slides_lecture3.pptx`)
and contain no lesson number, so they are never migrated — which is also why a
course-code rename costs D nothing at all.

CLI:
    migrate.py pending --course <path>
    migrate.py apply   --course <path> [--apply]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import log as dlog                                                # noqa: E402
from renumber import (migrate_file, moves_to_mapping,             # noqa: E402
                      pending_blocks, remap_key)

# D's field mapper. A lesson token in any other field is prose and stays prose.
ERRATA_FIELDS = ['lesson']
STATE_FIELDS = ['lesson', 'lessons', 'file_rel', 'archive_name']

# In a Markdown log, the fields whose values hold a lesson token.
LOG_FIELDS = ('lesson', 'file')
USED_IN_RE = re.compile(r'(Used in\s+)([LT]\d{2})')


def pending(course: Path | str) -> dict:
    """Every block each of D's records still has to apply."""
    course = Path(course)
    out = {'errata': [], 'state': [], 'logs': []}
    errata = course / '.data' / 'source_errata.json'
    if errata.is_file():
        try:
            data = json.loads(errata.read_text(encoding='utf-8'))
        except ValueError:
            data = {}
        out['errata'] = [b['id'] for b in
                         pending_blocks(course, data.get('applied_renumbers') or [])]
    state = dlog.read_state(course)
    out['state'] = [b['id'] for b in
                    pending_blocks(course, state.get('applied_renumbers') or [])]
    for path in dlog.all_logs(course):
        parsed = dlog.parse_log(path)
        ids = [b['id'] for b in
               pending_blocks(course, parsed.get('applied_renumbers') or [])]
        if ids:
            out['logs'].append({'file': str(path.relative_to(course)), 'pending': ids})
    out['any'] = bool(out['errata'] or out['state'] or out['logs'])
    return out


def _migrate_markdown_log(course: Path, path: Path, apply: bool) -> dict:
    parsed = dlog.parse_log(path)
    dlog.require_parsable(parsed)
    already = parsed.get('applied_renumbers') or []
    blocks = pending_blocks(course, already)
    if not blocks:
        return {'file': str(path.relative_to(course)), 'applied': [], 'changed': False}

    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    changes = 0
    for block in blocks:
        mapping = moves_to_mapping(block.get('moves') or [])
        if not mapping:
            continue
        for i, line in enumerate(lines):
            m = dlog.FIELD_RE.match(line)
            if m and m.group('key') in LOG_FIELDS:
                new = m.group('key') + ': ' + remap_key(m.group('value'), mapping)
                if new != line:
                    lines[i] = new
                    changes += 1
                continue
            new = USED_IN_RE.sub(
                lambda mm: mm.group(1) + remap_key(mm.group(2), mapping), line)
            if new != line:
                lines[i] = new
                changes += 1
        already.append(block['id'])

    if apply:
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        tmp.replace(path)
        # The stamp goes on in the same write sequence as the remap. A log that
        # was remapped but not stamped would be remapped again on the next run.
        dlog.set_applied_renumbers(path, already, apply=True)
    return {'file': str(path.relative_to(course)),
            'applied': [b['id'] for b in blocks], 'lines_changed': changes,
            'changed': True, 'written': apply}


def apply_all(course: Path | str, apply: bool = False) -> dict:
    course = Path(course)
    out = {'errata': None, 'logs': [], 'state': None, 'written': apply}

    out['errata'] = migrate_file(course, course / '.data' / 'source_errata.json',
                                 ERRATA_FIELDS, apply)

    for path in dlog.all_logs(course):
        out['logs'].append(_migrate_markdown_log(course, path, apply))

    # corrections.json last: it is the only record that can be rebuilt from the
    # others, so it is the cheapest one to lose to an interruption.
    state_path = dlog.state_path(course)
    if state_path.is_file():
        out['state'] = migrate_file(course, state_path, STATE_FIELDS, apply)
    else:
        out['state'] = {'file': str(state_path), 'exists': False}

    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('pending'); p.add_argument('--course', required=True)
    p = sub.add_parser('apply')
    p.add_argument('--course', required=True); p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    try:
        out = pending(args.course) if args.cmd == 'pending' \
            else apply_all(args.course, args.apply)
    except ValueError as exc:
        json.dump({'ok': False, 'stop': str(exc)}, sys.stdout, ensure_ascii=False,
                  indent=2)
        sys.stdout.write('\n')
        return 2
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
