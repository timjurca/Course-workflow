#!/usr/bin/env python3
"""The ledger: what each concept is worth, and what the student actually knows.

`revision_status.json` is the only place in this plugin that holds evidence
about the student rather than about the course. Two design choices in it are
what keep the skill honest, and both are easy to erode by accident:

  **Only graded answers enter it.** Revision files have no checkboxes and no
  self-assessment, because a student marking their own recall is generous at
  exactly the moment accuracy matters. `by` is always `graded`.

  **No weight ever reaches zero.** `error` has a floor of 0.3 and a mastered
  concept keeps a weight, so nothing drops out of the pool. A concept answered
  correctly once and then never seen again is the classic way a revision system
  produces a confident student who fails on lesson 3 material.

Every number here is derived from stored evidence, never accumulated in place:
`importance` is the sum of its own `signals`, and `error` and `state` are
replayed from `history` on every read. That is what makes the file rebuildable
from the feedback files after a loss, and what makes a wrong weight traceable to
the signal that caused it rather than to an arithmetic drift six weeks ago.

Keys carry no course code and no lesson number, so a code rename needs no
rewrite here at all; the lesson tokens that do appear are migrated by
`migrate.py` from A's renumber log.

Constants are speculative (spec 6.2, 13.2) and meant to be calibrated against a
real course; they are named here so a calibration is one edit.

CLI:
    ledger.py init    --course <path> [--apply]
    ledger.py show    --course <path> [--concept <id>]
    ledger.py sync    --course <path> [--apply]        concepts.json -> ledger
    ledger.py score   --course <path> --signals <json> [--apply]
    ledger.py record  --course <path> --results <json> [--apply]
    ledger.py weights --course <path> [--scope L01,L02] [--asof YYYY-MM-DD]
    ledger.py skip    --course <path> --concept <id> --reason "..." [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import renumber                                                    # noqa: E402

LEDGER_REL = Path('.data') / 'revision_status.json'
CONCEPTS_REL = Path('.data') / 'concepts.json'

# --- speculative constants, spec 6.2 and 13.2 -----------------------------
BASE_IMPORTANCE = 1
POINTS = {'exam_signal': 3, 'past_exam': 3, 'lectured': 2, 'assignment': 2,
          'objective': 2, 'emphasis': 2, 'highlight': 1}
# Signals that count once per concept however many times they are observed.
ONCE_ONLY = {'emphasis', 'highlight', 'lectured'}
ERROR_UP = 0.5          # a graded wrong answer
ERROR_DOWN = 0.5        # a graded correct answer
ERROR_FLOOR = 0.3       # never zero: a mastered concept still gets asked
ERROR_CEILING = 3.0     # never lets one concept swallow a whole mock
RECENCY_DIVISOR = 7.0   # days
RECENCY_CEILING = 3.0
MASTERY_RUN = 2         # graded correct answers in a row


def path_of(course: Path | str) -> Path:
    return Path(course) / LEDGER_REL


def empty(course: Path | str) -> dict:
    """A fresh ledger, with every renumber block in A's log pre-applied.

    Pre-filling `applied_renumbers` is what stops a first run on an established
    course from re-applying a renumber that happened before C existed, which
    would rewrite lesson keys that were already correct.
    """
    ids = [b['id'] for b in renumber.renumber_blocks(course)]
    return {'applied_renumbers': ids, 'concepts': {}}


def load(course: Path | str, create: bool = False) -> dict:
    p = path_of(course)
    if not p.is_file():
        if create:
            return empty(course)
        raise FileNotFoundError(str(p))
    data = json.loads(p.read_text(encoding='utf-8'))
    data.setdefault('applied_renumbers', [])
    data.setdefault('concepts', {})
    return data


def save(course: Path | str, data: dict) -> Path:
    """Atomic: a half-written ledger is a lost semester of graded history."""
    p = path_of(course)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    os.replace(tmp, p)
    return p


# ---------------------------------------------------------------- derivations

def importance_of(entry: dict) -> int:
    """The sum of the concept's own signals. Never stored independently.

    Deduplicated the way the signal table defines: emphasis, highlighting and
    being lectured count once per concept however many items carry them, while
    past exams and assignments count per exam and per assignment.
    """
    seen, total = set(), BASE_IMPORTANCE
    for s in entry.get('signals') or []:
        kind = s.get('type')
        if kind in ONCE_ONLY:
            if kind in seen:
                continue
            seen.add(kind)
        else:
            fingerprint = (kind, s.get('source'), s.get('lesson'))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
        total += int(s.get('points', POINTS.get(kind, 0)))
    return total


def _graded(entry: dict) -> list[dict]:
    return [h for h in (entry.get('history') or []) if h.get('by') == 'graded']


def error_of(entry: dict) -> float:
    """Replayed from history, never accumulated in place."""
    err = 1.0
    for h in _graded(entry):
        result = h.get('result')
        if result == 'wrong':
            err += ERROR_UP
        elif result == 'partial':
            err += ERROR_UP / 2
        elif result == 'correct':
            err -= ERROR_DOWN
    return round(min(max(err, ERROR_FLOOR), ERROR_CEILING), 3)


def state_of(entry: dict) -> str:
    if entry.get('retired'):
        return 'retired'
    graded = _graded(entry)
    if not graded:
        return 'untested'
    last = [h.get('result') for h in graded[-MASTERY_RUN:]]
    if len(last) == MASTERY_RUN and all(r == 'correct' for r in last):
        return 'mastered'
    return 'learning'


def recency_of(entry: dict, asof: date) -> float:
    """Untested concepts sit at the ceiling, so they are pulled in first."""
    last = entry.get('last_tested')
    if not last:
        return RECENCY_CEILING
    try:
        then = datetime.strptime(str(last)[:10], '%Y-%m-%d').date()
    except ValueError:
        return RECENCY_CEILING
    days = max((asof - then).days, 0)
    return round(min(1 + days / RECENCY_DIVISOR, RECENCY_CEILING), 3)


def refresh(entry: dict, asof: date | None = None) -> dict:
    entry['importance'] = importance_of(entry)
    entry['state'] = state_of(entry)
    graded = _graded(entry)
    entry['last_tested'] = graded[-1]['date'] if graded else None
    return entry


def refresh_all(data: dict) -> dict:
    for entry in data['concepts'].values():
        refresh(entry)
    return data


# ---------------------------------------------------------------- operations

def _entry(data: dict, cid: str) -> dict:
    return data['concepts'].setdefault(cid, {
        'title': cid, 'lessons': [], 'importance': BASE_IMPORTANCE, 'signals': [],
        'questions': [], 'history': [], 'last_tested': None,
        'state': 'untested', 'skipped': [], 'retired': False})


def sync(course: Path | str, apply: bool = False) -> dict:
    """Bring the ledger's concept set in line with B's registry.

    New concepts arrive at importance 1 rather than being left out, because a
    concept absent from the ledger is invisible to mock selection and would be
    skipped silently -- the one outcome the weighting rules forbid.
    """
    data = load(course, create=True)
    reg = json.loads((Path(course) / CONCEPTS_REL).read_text(encoding='utf-8'))
    added, retired, relessoned = [], [], []
    for cid, c in (reg.get('concepts') or {}).items():
        entry = data['concepts'].get(cid)
        if entry is None:
            entry = _entry(data, cid)
            added.append(cid)
        entry['title'] = c.get('title') or entry.get('title') or cid
        lessons = sorted({s.get('lesson') for s in (c.get('sections') or [])
                          if s.get('lesson')})
        if lessons and lessons != entry.get('lessons'):
            entry['lessons'] = lessons
            relessoned.append(cid)
        if c.get('retired') and not entry.get('retired'):
            entry['retired'] = True
            retired.append(cid)
        elif not c.get('retired'):
            entry['retired'] = False
    refresh_all(data)
    if apply:
        save(course, data)
    return {'added': added, 'retired': retired, 'lessons_updated': relessoned,
            'concepts': len(data['concepts']), 'written': apply}


def score(course: Path | str, signals: dict, apply: bool = False) -> dict:
    """Merge importance signals. Each signal keeps its own evidence.

    `{"<concept-id>": {"title": ..., "lessons": [...],
                       "signals": [{"type","points","lesson","source","note"}]}}`

    A signal is replaced, never doubled, when the same (type, source, lesson)
    arrives again: re-running `revise` on a lesson must not inflate its own
    concepts by re-observing the same slide.
    """
    data = load(course, create=True)
    changed = {}
    for cid, payload in signals.items():
        entry = _entry(data, cid)
        if payload.get('title'):
            entry['title'] = payload['title']
        for key in ('lessons',):
            if payload.get(key):
                entry[key] = sorted(set(entry.get(key) or []) | set(payload[key]))
        before = entry['importance']
        index = {(s.get('type'), s.get('source'), s.get('lesson')): i
                 for i, s in enumerate(entry['signals'])}
        for s in payload.get('signals') or []:
            s = dict(s)
            s.setdefault('points', POINTS.get(s.get('type'), 0))
            k = (s.get('type'), s.get('source'), s.get('lesson'))
            if k in index:
                entry['signals'][index[k]] = s
            else:
                index[k] = len(entry['signals'])
                entry['signals'].append(s)
        refresh(entry)
        if entry['importance'] != before:
            changed[cid] = {'was': before, 'now': entry['importance']}
    if apply:
        save(course, data)
    return {'scored': list(signals), 'importance_changed': changed,
            'written': apply}


def record(course: Path | str, results: list[dict], apply: bool = False) -> dict:
    """Write graded results into the history. The only input the ledger accepts.

    `[{"concept","result","score","question","date"}]`, result in
    wrong | partial | correct. A result already present for the same
    (question, date) is not added twice, so re-grading one attempt after a
    correction to the marking does not double-count it.
    """
    data = load(course, create=True)
    added, skipped, moved = [], [], {}
    for r in results:
        cid = r['concept']
        entry = _entry(data, cid)
        row = {'date': r.get('date') or date.today().isoformat(),
               'result': r['result'], 'by': 'graded',
               'score': r.get('score'), 'question': r.get('question')}
        if row['result'] not in ('wrong', 'partial', 'correct'):
            raise ValueError(f'unknown graded result {row["result"]!r} for {cid}')
        key = (row['question'], row['date'])
        if any((h.get('question'), h.get('date')) == key for h in entry['history']):
            skipped.append({'concept': cid, 'question': row['question'],
                            'why': 'already recorded for that attempt'})
            continue
        was = state_of(entry)
        entry['history'].append(row)
        entry['history'].sort(key=lambda h: (str(h.get('date')), str(h.get('question'))))
        refresh(entry)
        added.append({'concept': cid, 'result': row['result']})
        if state_of(entry) != was:
            moved[cid] = {'was': was, 'now': state_of(entry)}
    if apply:
        save(course, data)
    return {'recorded': added, 'skipped': skipped, 'state_changes': moved,
            'written': apply}


def weights(course: Path | str, scope: list[str] | None = None,
            asof: str | None = None) -> dict:
    """weight = importance x recency x error, for every non-retired concept.

    Retired concepts are the only exclusion, and even they keep their history.
    """
    data = load(course, create=True)
    day = datetime.strptime(asof, '%Y-%m-%d').date() if asof else date.today()
    rows = []
    for cid, entry in data['concepts'].items():
        refresh(entry)
        if entry.get('retired') or entry.get('state') == 'retired':
            continue
        if scope and not (set(entry.get('lessons') or []) & set(scope)):
            continue
        imp, rec, err = importance_of(entry), recency_of(entry, day), error_of(entry)
        rows.append({'concept': cid, 'title': entry.get('title'),
                     'lessons': entry.get('lessons'), 'importance': imp,
                     'recency': rec, 'error': err,
                     'weight': round(imp * rec * err, 3),
                     'state': entry['state'], 'last_tested': entry.get('last_tested'),
                     'skipped': bool(entry.get('skipped'))})
    rows.sort(key=lambda r: -r['weight'])
    excluded = [cid for cid, e in data['concepts'].items() if e.get('retired')]
    return {'asof': day.isoformat(), 'scope': scope, 'concepts': rows,
            'retired_excluded': excluded}


def skip(course: Path | str, concept: str, reason: str, cost: str = '',
         apply: bool = False) -> dict:
    """Record a requested skip. It is shown in every later verdict, permanently.

    C states the cost before this is called; recording it is what stops the cost
    from being stated once and then forgotten by the readiness verdict.
    """
    data = load(course, create=True)
    entry = _entry(data, concept)
    row = {'date': date.today().isoformat(), 'reason': reason, 'cost': cost}
    entry.setdefault('skipped', []).append(row)
    if apply:
        save(course, data)
    return {'concept': concept, 'skipped': row, 'written': apply,
            'note': 'this appears in every later readiness verdict'}


def show(course: Path | str, concept: str | None = None) -> dict:
    data = refresh_all(load(course, create=True))
    if concept:
        return {'concept': concept, 'entry': data['concepts'].get(concept)}
    by_state: dict = {}
    for cid, e in data['concepts'].items():
        by_state.setdefault(e['state'], []).append(cid)
    return {'applied_renumbers': data['applied_renumbers'],
            'concepts': len(data['concepts']),
            'by_state': {k: sorted(v) for k, v in sorted(by_state.items())},
            'skipped': {cid: e['skipped'] for cid, e in data['concepts'].items()
                        if e.get('skipped')}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('init', 'show', 'sync', 'score', 'record', 'weights', 'skip'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True)
        p.add_argument('--apply', action='store_true')
        if name == 'show':
            p.add_argument('--concept')
        if name == 'score':
            p.add_argument('--signals', required=True, help='JSON file or literal')
        if name == 'record':
            p.add_argument('--results', required=True, help='JSON file or literal')
        if name == 'weights':
            p.add_argument('--scope', help='comma separated L03,T02')
            p.add_argument('--asof')
        if name == 'skip':
            p.add_argument('--concept', required=True)
            p.add_argument('--reason', required=True)
            p.add_argument('--cost', default='')
    args = ap.parse_args(argv)

    def _json(raw):
        # A literal long enough to be a whole signal set is not a path, and
        # Path.is_file() raises on one rather than answering False.
        try:
            p = Path(raw)
            if p.is_file():
                return json.loads(p.read_text(encoding='utf-8'))
        except OSError:
            pass
        return json.loads(raw)

    if args.cmd == 'init':
        data = load(args.course, create=True) if path_of(args.course).is_file() \
            else empty(args.course)
        if args.apply:
            save(args.course, data)
        out = {'ledger': str(path_of(args.course)), 'concepts': len(data['concepts']),
               'applied_renumbers': data['applied_renumbers'], 'written': args.apply}
    elif args.cmd == 'show':
        out = show(args.course, args.concept)
    elif args.cmd == 'sync':
        out = sync(args.course, args.apply)
    elif args.cmd == 'score':
        out = score(args.course, _json(args.signals), args.apply)
    elif args.cmd == 'record':
        out = record(args.course, _json(args.results), args.apply)
    elif args.cmd == 'weights':
        out = weights(args.course, args.scope.split(',') if args.scope else None,
                      args.asof)
    else:
        out = skip(args.course, args.concept, args.reason, args.cost, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
