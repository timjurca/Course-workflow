#!/usr/bin/env python3
"""Choose what a mock asks about, and be able to explain the choice afterwards.

Three properties, each preventing a different way a practice exam lies to the
student about what they know.

  **Nothing ever reaches weight zero.** `error` has a floor and a mastered
  concept keeps its importance, so every non-retired concept stays in the pool.
  A concept that drops out after one correct answer is how a student arrives at
  the exam confident about lesson 3 and empty about lesson 5.

  **A coverage floor across the series, not within one mock.** Every in-scope
  concept appears in at least one mock before any concept appears a third time.
  Pure weighted sampling would ask about the three heaviest concepts in every
  mock and never touch the long tail, which is precisely where the untested
  material is.

  **The seed is recorded.** A mock is reproducible, so "why did it ask that?"
  has an answer. Without it the selection is unexplainable even to the person
  who wrote it, and an unexplainable weighting is one nobody can calibrate.

Appearances across the series are counted from the mock files' own
`concepts_used` frontmatter, not from the ledger: the ledger records what was
*graded*, and a mock the student never sat still used up its concepts.

The weight formula and its constants live in `ledger.py` and are speculative
(spec 13.2).

CLI:
    select_mock.py select --course <path> --scope L01,L02 --count 8
                          [--seed N] [--asof YYYY-MM-DD]
    select_mock.py series --course <path>
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import ledger as led                                               # noqa: E402
import naming                                                      # noqa: E402
from vault import read_frontmatter                                 # noqa: E402

MOCK_RE = re.compile(r'^Mock_(\d{2})\.md$')
ATTEMPT_RE = re.compile(r'^Mock_(\d{2})_Attempt_')
THIRD_APPEARANCE = 3          # the coverage floor's ceiling


def mock_dir(course: Path | str) -> Path:
    return Path(course) / 'Exams' / 'Mock_exams'


def series(course: Path | str) -> dict:
    """Every mock written so far, with the concepts it used and whether it is frozen.

    A mock with a filed attempt is frozen for good: the feedback refers to it
    question by question, so regenerating it would leave the grading pointing at
    text that no longer exists.
    """
    d = mock_dir(course)
    mocks, attempts = {}, set()
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            stem = naming.strip_code_token(p.name)
            m = ATTEMPT_RE.match(stem)
            if m:
                attempts.add(m.group(1))
                continue
            m = MOCK_RE.match(stem)
            if not m:
                continue
            try:
                fm, _ = read_frontmatter(p)
            except Exception:
                fm = {}
            mocks[m.group(1)] = {
                'file': p.name, 'number': m.group(1),
                'concepts_used': list(fm.get('concepts_used') or []),
                'scope': list(fm.get('scope') or []),
                'seed': fm.get('seed')}
    for num in attempts:
        if num in mocks:
            mocks[num]['frozen'] = True
    for num, row in mocks.items():
        row.setdefault('frozen', False)
    used = [n for n in mocks]
    nxt = 1
    while '%02d' % nxt in mocks:
        nxt += 1
    counts: dict = {}
    for row in mocks.values():
        for cid in row['concepts_used']:
            counts[cid] = counts.get(cid, 0) + 1
    return {'mocks': [mocks[k] for k in sorted(mocks)], 'next_number': '%02d' % nxt,
            'frozen': sorted(n for n, r in mocks.items() if r['frozen']),
            'appearances': counts,
            'note': None if used else 'no mock has been written for this course yet'}


def select(course: Path | str, scope: list[str], count: int,
           seed: int | None = None, asof: str | None = None) -> dict:
    rows = led.weights(course, scope, asof)['concepts']
    hist = series(course)
    appearances = hist['appearances']
    for r in rows:
        r['appearances'] = appearances.get(r['concept'], 0)

    if not rows:
        return {'scope': scope, 'chosen': [], 'seed': seed,
                'why': 'no non-retired concept is in scope. Either the lessons have '
                       'no notes yet, or every concept in them is retired.'}

    # The coverage floor. While some in-scope concept has never been asked,
    # a concept that already has two appearances is held back rather than
    # allowed to reach a third.
    never_asked = [r for r in rows if r['appearances'] == 0]
    pool = rows
    floor_applied = False
    if never_asked:
        held = [r for r in rows if r['appearances'] >= THIRD_APPEARANCE - 1]
        if held and len(rows) - len(held) >= count:
            pool = [r for r in rows if r['appearances'] < THIRD_APPEARANCE - 1]
            floor_applied = True

    seed = seed if seed is not None else random.randrange(1, 1_000_000)
    rng = random.Random(seed)

    chosen, remaining = [], list(pool)
    # Untested concepts are taken first while the floor is in force, so a mock
    # that cannot hold everything still measures what has never been measured.
    forced = [r for r in remaining if r['appearances'] == 0
              and r['state'] == 'untested']
    rng.shuffle(forced)
    forced.sort(key=lambda r: -r['weight'])
    for r in forced[:count]:
        chosen.append({**r, 'reason': 'never asked and never graded'})
        remaining.remove(r)

    while len(chosen) < count and remaining:
        total = sum(r['weight'] for r in remaining)
        if total <= 0:
            pick = remaining[0]
        else:
            t = rng.random() * total
            acc = 0.0
            pick = remaining[-1]
            for r in remaining:
                acc += r['weight']
                if acc >= t:
                    pick = r
                    break
        chosen.append({**pick, 'reason': _reason(pick)})
        remaining.remove(pick)

    short = max(0, count - len(chosen))
    return {'scope': scope, 'count': count, 'seed': seed,
            'coverage_floor_applied': floor_applied,
            'held_back_to_protect_the_floor':
                sorted(r['concept'] for r in rows if r not in pool),
            'chosen': chosen,
            'concepts_used': [r['concept'] for r in chosen],
            'short_by': short,
            'note': None if not short else
                    f'only {len(chosen)} concepts are in scope; the mock is '
                    f'{short} question-slot(s) short of the requested {count}',
            'never_asked_remaining':
                sorted(r['concept'] for r in rows
                       if r['appearances'] == 0
                       and r['concept'] not in {c['concept'] for c in chosen})}


def _reason(row: dict) -> str:
    bits = [f"importance {row['importance']}"]
    if row['error'] > 1:
        bits.append('graded misses outstanding')
    if row['state'] == 'mastered':
        bits.append('mastered, still in the pool')
    if row['recency'] >= 3:
        bits.append('not tested recently')
    if row.get('skipped'):
        bits.append('skipped by request earlier')
    return ', '.join(bits)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('select')
    s.add_argument('--course', required=True)
    s.add_argument('--scope', required=True)
    s.add_argument('--count', type=int, required=True)
    s.add_argument('--seed', type=int)
    s.add_argument('--asof')
    h = sub.add_parser('series')
    h.add_argument('--course', required=True)
    args = ap.parse_args(argv)
    if args.cmd == 'select':
        out = select(args.course, [x.strip() for x in args.scope.split(',') if x.strip()],
                     args.count, args.seed, args.asof)
    else:
        out = series(args.course)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
