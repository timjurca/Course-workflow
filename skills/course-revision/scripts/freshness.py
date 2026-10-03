#!/usr/bin/env python3
"""Course-wide freshness, without downloading a single byte.

A mock can be asked for at any time, over a whole semester, so this check runs
over every lesson in the overview. That makes it the one place where a careless
implementation would be expensive rather than merely wrong: opening each
lesson's sources to see whether they changed would pull a semester of slide
decks and textbooks out of iCloud, on a laptop, before the student has agreed to
anything.

So it reads only what B already recorded -- `sources_stat`, `sources:`,
`inputs`, the revision file's `notes_hash` -- plus `stat` and a directory
listing. Never a source. A file whose bytes are not on this machine is reported
as **"freshness unknown"**, which is the honest answer, and the run continues;
building the mock afterwards may download what it actually needs, and says so.

Nothing here blocks. `revise` is per lesson and hard-fails; a mock over twelve
lessons cannot be held hostage by one stale lesson, so gaps are listed first and
the student decides the scope. Open corrections are named here as warnings for
the same reason.

`Explanations/` is invisible to this check, as it is to all of C: it holds
tutor prose, not course material, and a saved explanation changing is not a
reason to call a lesson stale.

CLI:
    freshness.py scan --course <path> [--scope L01,L02]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import gate                                                        # noqa: E402
import icloud                                                      # noqa: E402
import naming                                                      # noqa: E402
import overview as ov                                              # noqa: E402
from source_hash import (compare_stat,                             # noqa: E402
                         absolve_annotation_changes)
from vault import read_frontmatter                                 # noqa: E402


def revision_path(course: Path, key: str) -> Path | None:
    d = course / 'Exams' / 'Revision_questions'
    if not d.is_dir():
        return None
    want = f'{key}_Revision.md'
    for p in sorted(d.glob('*_Revision.md')):
        if naming.strip_code_token(p.name) == want:
            return p
    return None


def one(course: Path, key: str) -> dict:
    row = {'lesson': key, 'state': 'current', 'reasons': [], 'warnings': []}
    npath = gate.notes_path(course, key)
    if npath is None:
        row['state'] = 'no_notes'
        row['reasons'].append('no notes file; run course-notes for this lesson')
        return row
    if icloud.is_placeholder(npath)['placeholder']:
        row['state'] = 'unknown'
        row['reasons'].append('the notes file is not downloaded on this machine')
        return row

    fm, body = read_frontmatter(npath)
    folder = gate.lesson_folder(course, key)

    rpath = revision_path(course, key)
    row['revision_file'] = rpath.name if rpath else None
    if rpath is None:
        row['state'] = 'no_revision'
        row['reasons'].append('no revision file yet')
    else:
        rfm, _ = read_frontmatter(rpath)
        recorded = str(rfm.get('notes_hash') or '')
        current = gate.notes_hash(npath)
        row['notes_hash'] = {'recorded': recorded, 'current': current}
        if recorded and recorded != current:
            row['state'] = 'stale'
            row['reasons'].append('the notes changed since this revision file was '
                                  'written (a course-notes re-run, a correction, or '
                                  'a hand edit)')

    stat = compare_stat(course, list(fm.get('sources_stat') or []), folder)
    stat = absolve_annotation_changes(stat, list(fm.get('sources') or []),
                                      course, folder, fm.get('highlights'))
    if stat['changed']:
        row['state'] = 'stale'
        row['reasons'].append('sources changed: '
                              + ', '.join(c['path'] for c in stat['changed']))
    if stat['gone']:
        row['state'] = 'stale'
        row['reasons'].append('sources missing: ' + ', '.join(stat['gone']))
    if stat['freshness_unknown']:
        if row['state'] == 'current':
            row['state'] = 'unknown'
        row['warnings'].append({'code': 'freshness_unknown',
                                'paths': stat['freshness_unknown'],
                                'message': 'offloaded, so the date could not be '
                                           'confirmed. Never downloaded here.'})

    extra, missing = gate.listing_drift(folder, list(fm.get('sources') or []))
    if extra or missing:
        row['state'] = 'stale'
        row['reasons'].append(
            'the folder listing no longer matches the notes'
            + (f'; newly filed: {", ".join(extra)}' if extra else '')
            + (f'; no longer present: {", ".join(missing)}' if missing else ''))

    drift = gate.inputs_drift(course, key, fm.get('inputs') or {})
    if drift:
        row['state'] = 'stale'
        row['reasons'].append('the overview or assignment rows changed: '
                              + ', '.join(d['field'] for d in drift))

    corr = gate.open_corrections(folder / 'notes_corrections.md', str(fm.get('run') or ''))
    if corr['blocking'] or corr['warning']:
        row['warnings'].append({'code': 'open_corrections',
                                'blocking': corr['blocking'],
                                'orphaned': corr['warning'],
                                'message': 'corrections are open for this lesson. '
                                           'A mock is still built, and says so; '
                                           'revise would stop here.'})
    return row


def scan(course: Path | str, scope: list[str] | None = None) -> dict:
    course = Path(course)
    data = ov.load(course)
    keys = [r['key'] for r in data['rows'] if r.get('key')]
    if scope:
        keys = [k for k in keys if k in set(scope)]
    rows = [one(course, k) for k in keys]
    buckets: dict = {}
    for r in rows:
        buckets.setdefault(r['state'], []).append(r['lesson'])
    usable = [r['lesson'] for r in rows if r['state'] == 'current']
    unknown = [r['lesson'] for r in rows if r['state'] == 'unknown']
    return {
        'course': str(course), 'lessons': rows,
        'by_state': {k: sorted(v) for k, v in sorted(buckets.items())},
        'suggested_scope': sorted(usable + unknown),
        'corrections_open': sorted(r['lesson'] for r in rows
                                   for w in r['warnings']
                                   if w['code'] == 'open_corrections' and w['blocking']),
        'prompt': _prompt(buckets, usable + unknown),
        'note': 'nothing was downloaded; Explanations/ is not read by this check'}


def _prompt(buckets: dict, usable: list) -> str:
    gaps = []
    for state, label in (('no_notes', 'have no current notes'),
                         ('no_revision', 'have no revision file'),
                         ('stale', 'are stale'),
                         ('unknown', 'freshness unknown (files offloaded)')):
        if buckets.get(state):
            gaps.append(f'{", ".join(sorted(buckets[state]))} {label}')
    head = '. '.join(gaps)
    if not usable:
        return (head + '. No lesson is current, so there is nothing to build a '
                       'mock over yet.') if head else 'every lesson is current'
    span = f'{min(usable)} to {max(usable)}' if len(usable) > 1 else usable[0]
    return (f'{head}. Build the mock over {span}?' if head
            else f'every lesson is current. Build the mock over {span}?')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('scan')
    p.add_argument('--course', required=True)
    p.add_argument('--scope')
    args = ap.parse_args(argv)
    out = scan(args.course, args.scope.split(',') if args.scope else None)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
