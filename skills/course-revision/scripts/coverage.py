#!/usr/bin/env python3
"""Set arithmetic over a planned question set: nothing in the lesson is skipped.

The failure this prevents is quiet. A model writing fourteen questions from a
six-concept lesson will naturally write nine about the two concepts it found
interesting and none about the section it found dull, and the file will look
complete. The student then revises a lesson with a hole in it and has no way to
see the hole: a revision file gives no signal about what it left out.

So coverage is decided by set difference against B's concept registry and the
notes' own `exam_signals`, not by inspection. One repair pass, then a loud flag
in the file and in the report -- it never loops, the same rule as B's Pass C'.

The difficulty floor is here for the same reason and is deliberately not a
setting. Recall questions are the ones a model writes fastest and a student
answers most comfortably, and a file that is mostly recall feels like revision
while measuring almost nothing. Asking for easier questions adds easy ones; it
never removes the hard ones.

CLI:
    coverage.py check --course <path> --lesson L03 --questions <json>
                      [--ledger-weights <json>]
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
import ledger as led                                               # noqa: E402
from vault import read_frontmatter                                 # noqa: E402

# Types that count toward the floor: everything that asks the student to do
# something with the material rather than retrieve it.
HARD_TYPES = {'explain', 'application', 'calculation'}
DIFFICULTY_FLOOR = 0.5          # speculative, spec 9.2
HIGH_IMPORTANCE = 5             # at or above this, two questions of two types


def check(course: Path | str, lesson: str, questions: list[dict]) -> dict:
    course = Path(course)
    lesson = lesson.upper()
    npath = gate.notes_path(course, lesson)
    if npath is None:
        raise FileNotFoundError(f'no notes for {lesson}')
    fm, body = read_frontmatter(npath)

    in_notes = []
    for cid in gate.CONCEPT_RE.findall(body):
        if cid not in in_notes:
            in_notes.append(cid)
    signals = list(fm.get('exam_signals') or [])

    covered: dict = {}
    for q in questions:
        covered.setdefault(q.get('concept'), []).append(q)
    cited = {c for q in questions for c in (q.get('cites') or [])}

    missing = [c for c in in_notes if c not in covered]
    stray = sorted(c for c in covered if c and c not in in_notes)

    signal_gaps = []
    for s in signals:
        cid, src = s.get('concept'), s.get('source')
        if cid not in covered:
            signal_gaps.append({'signal': s, 'why': 'its concept has no question'})
        elif src and src not in cited:
            signal_gaps.append({'signal': s,
                                'why': f'no question cites {src}'})

    # Per-concept floors. Importance and past-exam counts come from the ledger,
    # which is the only place that knows what the exams asked.
    try:
        weights = {r['concept']: r for r in led.weights(course)['concepts']}
        entries = led.load(course, create=True)['concepts']
    except Exception:
        weights, entries = {}, {}
    floor_gaps = []
    for cid in in_notes:
        qs = covered.get(cid) or []
        entry = entries.get(cid) or {}
        past = sum(1 for s in (entry.get('signals') or [])
                   if s.get('type') == 'past_exam')
        imp = (weights.get(cid) or {}).get('importance', 1)
        want = max(1, 1 + past)
        if imp >= HIGH_IMPORTANCE:
            want = max(want, 2)
        if len(qs) < want:
            floor_gaps.append({'concept': cid, 'have': len(qs), 'want': want,
                               'why': f'importance {imp}, {past} past-exam '
                                      'appearances'})
        if imp >= HIGH_IMPORTANCE and len({q.get('type') for q in qs}) < 2:
            floor_gaps.append({'concept': cid, 'have_types':
                               sorted({q.get('type') for q in qs}),
                               'want': 'two different types',
                               'why': f'importance {imp} is at or above '
                                      f'{HIGH_IMPORTANCE}'})

    hard = [q for q in questions if q.get('type') in HARD_TYPES]
    share = round(len(hard) / len(questions), 3) if questions else 0.0
    difficulty_ok = share >= DIFFICULTY_FLOOR

    ok = not missing and not signal_gaps and not floor_gaps and difficulty_ok
    return {
        'lesson': lesson, 'ok': ok,
        'questions': len(questions), 'concepts_in_notes': in_notes,
        'concepts_covered': sorted(c for c in covered if c),
        'uncovered_concepts': missing,
        'questions_on_unknown_concepts': stray,
        'exam_signal_gaps': signal_gaps,
        'floor_gaps': floor_gaps,
        'difficulty': {'hard': len(hard), 'share': share,
                       'floor': DIFFICULTY_FLOOR, 'ok': difficulty_ok},
        'mix': _mix(questions),
        'action': 'commit' if ok else
                  'one repair pass, then flag what is still missing in the file '
                  'and in the report. Never loop.'}


def _mix(questions: list[dict]) -> dict:
    out: dict = {}
    for q in questions:
        out[q.get('type') or 'unknown'] = out.get(q.get('type') or 'unknown', 0) + 1
    return dict(sorted(out.items()))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('check')
    p.add_argument('--course', required=True)
    p.add_argument('--lesson', required=True)
    p.add_argument('--questions', required=True, help='JSON file or literal')
    args = ap.parse_args(argv)
    try:
        q = Path(args.questions)
        raw = q.read_text(encoding='utf-8') if q.is_file() else args.questions
    except OSError:
        raw = args.questions
    out = check(args.course, args.lesson, json.loads(raw))
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0 if out['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
