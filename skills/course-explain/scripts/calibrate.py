#!/usr/bin/env python3
"""Read C's ledger for one concept, so an explanation starts where the student is.

A tutor who opens with the definition for someone who has already been graded
twice on the same confusion is wasting the one thing the student came for. C's
`revision_status.json` records what has actually been graded, so E reads that
one entry and adapts the shape of the explanation to it.

Three properties, and each one is a boundary rather than a nicety:

**Read-only, one entry, never recorded.** E reads the ledger and writes nothing
back, not even an "explained" flag. C's ledger is filled only by graded answers
and there is no self-assessment input at all; a flag from E would be exactly
that, arriving through a side door.

**The exam profile is prose, not a marker.** `exam_profile.json` says what this
course rewards, and that belongs in a sentence at the end of an explanation, not
in a tier marker.

**A missing ledger is said once.** Uncalibrated explaining is a perfectly good
outcome; saying so on every answer is noise, and saying nothing is a quiet
change in behaviour the student cannot see.

CLI:
    calibrate.py concept --course <c> --concept <id>
    calibrate.py profile --course <c>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
from coverage import load_concepts, successor_of                     # noqa: E402

# The shape of the explanation each ledger state calls for. These are defaults
# the model may override on the student's word, not rules.
DEFAULTS = {
    'untested': 'full build-up from prerequisites',
    'learning': ('lead with the specific error pattern in history, then rebuild '
                 'from there'),
    'mastered': 'short refresher, no build-up, unless more is asked for',
    'retired': 'explain it, and say it is retired',
}


def concept(course: Path | str, cid: str) -> dict:
    course = Path(course)
    path = course / '.data' / 'revision_status.json'
    concepts = load_concepts(course)
    entry = concepts.get(cid) or {}
    out = {'concept': cid, 'ledger': str(path.relative_to(course)),
           'ledger_present': path.is_file(), 'retired': bool(entry.get('retired')),
           'write_back': 'never: E records nothing about the student, anywhere'}
    if out['retired']:
        out['successor'] = successor_of(concepts, cid)['successor']
    if not path.is_file():
        out['state'] = None
        out['default'] = 'uncalibrated explaining'
        out['say_once'] = ('there is no revision ledger yet, so this is '
                           'uncalibrated - say it once in the session, not once '
                           'per answer')
        return out
    try:
        data = json.loads(path.read_text(encoding='utf-8')) or {}
    except Exception as exc:
        out['error'] = str(exc)
        out['default'] = 'uncalibrated explaining'
        return out
    row = (data.get('concepts') or {}).get(cid)
    if row is None:
        out['state'] = 'untested'
        out['in_ledger'] = False
        out['default'] = DEFAULTS['untested']
        return out
    out['in_ledger'] = True
    out['state'] = row.get('state')
    out['importance'] = row.get('importance')
    out['history'] = row.get('history') or []
    out['signals'] = row.get('signals') or []
    out['default'] = DEFAULTS.get(
        'retired' if out['retired'] else (row.get('state') or 'untested'),
        DEFAULTS['untested'])
    graded_errors = [h for h in out['history']
                     if isinstance(h, dict) and (h.get('score') or 1) < 1]
    out['graded_errors'] = graded_errors
    if out['state'] == 'learning' and graded_errors:
        out['lead_with'] = graded_errors[-1]
    if str(row.get('importance', '')).lower() in ('high', 'critical'):
        out['length'] = ('longer, exam-shaped, with the signals named: '
                         + '; '.join(map(str, out['signals'])) if out['signals']
                         else 'longer, exam-shaped')
    return out


def profile(course: Path | str) -> dict:
    """What the exam rewards. Said in prose at the end, never as a marker."""
    course = Path(course)
    path = course / '.data' / 'exam_profile.json'
    out = {'file': str(path.relative_to(course)), 'present': path.is_file(),
           'use': ('when E disagrees with the course, say which version the exam '
                   'rewards - in separate sentences, never blended with the '
                   'disagreement')}
    if not path.is_file():
        out['note'] = 'no exam profile; say nothing about what the exam rewards'
        return out
    try:
        out['profile'] = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        out['error'] = str(exc)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('concept'); p.add_argument('--course', required=True)
    p.add_argument('--concept', required=True)
    p = sub.add_parser('profile'); p.add_argument('--course', required=True)
    args = ap.parse_args(argv)
    out = concept(args.course, args.concept) if args.cmd == 'concept' \
        else profile(args.course)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
