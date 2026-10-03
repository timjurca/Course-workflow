#!/usr/bin/env python3
"""Apply skill A's renumber blocks to C's records, all moves at once, exactly once.

A renumbers a lesson by renaming folders and files and writing a `## renumber`
block to its filing log. It never edits another skill's data file, so C's ledger
still says `L03` for a lesson that is now `L04`. Left alone, the next run creates
a second concept history under the new key and the old one silently stops
growing: the student's whole record of what they get wrong splits in two.

Two properties are the reason this is not a loop over a mapping:

  * **Simultaneous.** `L03 -> L04` and `L04 -> L05` in the same block are one
    substitution. Applied in sequence, L03 would be moved twice and land on L05.
  * **Once.** The block id goes into `applied_renumbers`, so a second run is a
    no-op even though the values now match the destination of the mapping.

Both live in `shared/scripts/renumber.py`; this module supplies only C's field
mapper, which is the part no shared module can know: which of C's fields hold a
lesson token, and which merely mention one in prose.

`revision_status.json` and `revision_findings.json` are migrated. C's other two
data files carry no lesson reference at all, by design (`exam_profile.json` keys
past exams by filename, `exam_glossary.json` by term), which is what makes a
course-code rename cost C nothing.

CLI:
    migrate.py plan  --course <path>
    migrate.py apply --course <path>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import renumber                                                    # noqa: E402

# C's field mapper. A lesson token anywhere else in these files is prose.
#   ledger:   concept `lessons`, question `file`, signal `lesson`
#   findings: finding `lesson`
LEDGER_FIELDS = ['lessons', 'file', 'lesson']
FINDINGS_FIELDS = ['lesson']

TARGETS = [('.data/revision_status.json', LEDGER_FIELDS),
           ('.data/revision_findings.json', FINDINGS_FIELDS)]


def pending(course: Path | str) -> list[dict]:
    """Every renumber block, with the ids each target has already applied."""
    course = Path(course)
    out = []
    for rel, _fields in TARGETS:
        path = course / rel
        applied = []
        if path.is_file():
            try:
                applied = json.loads(path.read_text(encoding='utf-8')).get(
                    'applied_renumbers') or []
            except Exception:
                applied = []
        blocks = renumber.pending_blocks(course, applied)
        out.append({'file': rel, 'exists': path.is_file(),
                    'pending': [{'id': b['id'], 'timestamp': b['timestamp'],
                                 'moves': b.get('moves')} for b in blocks]})
    return out


def run(course: Path | str, apply: bool = False, since: str | None = None) -> dict:
    course = Path(course)
    results = []
    for rel, fields in TARGETS:
        path = course / rel
        if not path.is_file():
            results.append({'file': rel, 'exists': False, 'applied': []})
            continue
        results.append(renumber.migrate_file(course, path, fields,
                                             apply=apply, since=since))
    total = sorted({i for r in results for i in (r.get('applied') or [])})
    return {'course': str(course), 'applied': apply, 'blocks': total,
            'files': results,
            'note': 'no renumber block is pending' if not total else
                    'lesson references migrated; A renamed the files themselves'}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('plan', 'apply'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True)
        p.add_argument('--since', help="C's latest output timestamp, for a rebuild")
    args = ap.parse_args(argv)
    if args.cmd == 'plan':
        out = {'course': args.course, 'targets': pending(args.course)}
    else:
        out = run(args.course, apply=True, since=args.since)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
