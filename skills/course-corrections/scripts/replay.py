#!/usr/bin/env python3
"""Put the logged corrections back after B has rewritten the notes — or admit it cannot.

B regenerates a lesson from its sources and knows nothing about the correction
log. Every fix D ever applied is gone from the file the moment that happens.
Replay is the mechanism that makes a correction survive, and it has exactly one
hard rule (D-19):

    **Nothing is re-applied silently into a rewritten passage.**

An automatic move to the most similar sentence is the silent change this plugin
exists to avoid. So the classification below has only two automatic outcomes —
the fix is already there, or its anchor is still there verbatim — and every
other case becomes a question with candidates attached.

    after present in the concept's section     absorbed, nothing written
    before present                             re-applied, status applied
    neither, concept still exists              ask; candidates ranked, never chosen
    concept id gone (retired or merged)        ask, with the successor by B's own
                                               overlap rule; otherwise orphaned

`orphaned` is not a failure state to be avoided. It is the honest record that a
fix no longer has a home, and `review` brings it back so the student can
re-place or withdraw it.

Two more rules that fall out of the spec: entries in one group are applied
together within the lesson, and every re-applied fix is re-verified before it is
written, because the surrounding text is new even when the anchor is not.

CLI:
    replay.py plan --course <path> --lesson L03 [--decisions <file>]
    replay.py run  --course <path> --lesson L03 [--decisions <file>] [--apply]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import anchor                                                     # noqa: E402
import apply as dapply                                            # noqa: E402
import fingerprint                                                # noqa: E402
import gate as dgate                                              # noqa: E402
import log as dlog                                                # noqa: E402

CASES = ('absorbed', 'reapply', 'rewritten', 'concept_gone', 'not_this_file')


def _log_path(course: Path, lesson: str) -> Path:
    folder = dgate.lesson_dir(course, lesson)
    return folder / 'notes_corrections.md'


def classify(notes: str, entry: dict, registry: dict, lesson: str) -> dict:
    v = entry['values']
    concept = v.get('concept')
    after, before = v.get('after') or '', v.get('before') or ''

    row = {'id': entry['id'], 'operation': entry['operation'], 'concept': concept,
           'group': v.get('group'), 'file': v.get('file'), 'before': before,
           'after': after, 'verified': v.get('verified'), 'basis': v.get('basis')}

    section = anchor.section_for(notes, concept) if concept else None
    if concept and section is None:
        entry_in_registry = (registry.get('concepts') or {}).get(concept)
        succ = anchor.successor(registry, concept, lesson)
        # "Already there" beats "cannot be placed". A concept that was renamed or
        # merged takes its text with it, so a fix B now writes by itself would
        # otherwise be reported as orphaned and asked about for nothing.
        if after:
            for where in ([c['concept'] for c in succ['candidates']] or [None]):
                if anchor.find(notes, after, where)['found']:
                    return {**row, 'case': 'absorbed', 'moved_to': where,
                            'note': 'the corrected text is already in the notes, under '
                                    + (f'concept {where}' if where else 'another section')}
        return {**row, 'case': 'concept_gone',
                'retired': bool(entry_in_registry and entry_in_registry.get('retired')),
                'successor': succ,
                'question': 'the concept this correction was anchored to is no longer '
                            'in these notes. Re-place it on the successor below, or '
                            'leave it orphaned.'}

    if after and anchor.find(notes, after, concept)['found']:
        return {**row, 'case': 'absorbed',
                'note': 'course-notes now writes the corrected text by itself'}

    hit = anchor.find(notes, before, concept)
    if hit['found']:
        return {**row, 'case': 'reapply', 'occurrences': hit['count'],
                'unique': hit['unique'],
                'question': None if hit['unique'] else
                            'the anchor appears more than once; say which'}

    return {**row, 'case': 'rewritten',
            'candidates': anchor.candidates(notes, before, concept)['candidates'],
            'question': 'the passage was rewritten. Pick the passage that makes the '
                        'same claim, or leave it orphaned. Nothing is moved for you.'}


def plan(course: Path | str, lesson: str) -> dict:
    course = Path(course)
    folder = dgate.lesson_dir(course, lesson)
    if folder is None:
        return {'ok': False, 'reason': f'no folder for {lesson}'}
    notes_path = dgate.notes_path(course, lesson)
    if notes_path is None:
        return {'ok': False, 'reason': f'no notes for {lesson}'}
    notes = notes_path.read_text(encoding='utf-8')
    run_id = fingerprint.notes_run(notes)

    log_path = _log_path(course, lesson)
    data = dlog.parse_log(log_path)
    dlog.require_parsable(data)
    registry = anchor.load_concepts(course / '.data' / 'concepts.json')

    # scan runs first, so a hand edit is never overwritten unnoticed
    scan = fingerprint.check(course, lesson, notes_path)

    rows, open_ids = [], {e['id'] for e in dlog.open_entries(data, run_id)}
    for entry in data['entries']:
        if entry['id'] not in open_ids:
            continue
        if entry['values'].get('status') == 'withdrawn':
            continue
        rows.append(classify(notes, entry, registry, lesson))

    groups: dict[str, list[str]] = {}
    for row in rows:
        if row.get('group'):
            groups.setdefault(row['group'], []).append(row['id'])

    return {'ok': True, 'lesson': lesson, 'run': run_id,
            'notes': str(notes_path.relative_to(course)),
            'log': str(log_path.relative_to(course)),
            'scan': scan,
            'entries': rows,
            'automatic': [r['id'] for r in rows if r['case'] in ('absorbed', 'reapply')
                          and r.get('unique', True)],
            'ask': [r['id'] for r in rows if r['case'] in ('rewritten', 'concept_gone')
                    or not r.get('unique', True)],
            'groups': groups,
            'note': 'entries in one group are applied together within this lesson; '
                    'the report names the group so the other lessons can be replayed '
                    'too'}


def run(course: Path | str, lesson: str, decisions: dict | None = None,
        apply: bool = False) -> dict:
    course = Path(course)
    made = plan(course, lesson)
    if not made.get('ok'):
        return made
    decisions = {d['id']: d for d in (decisions or {}).get('decisions', [])}

    notes_rel = made['notes']
    log_path = course / made['log']
    stamp = datetime.now().strftime('%Y-%m-%dT%H:%M')

    edits, statuses, left = [], {}, []
    for row in made['entries']:
        decision = decisions.get(row['id'], {})
        action = decision.get('action')

        if row['case'] == 'absorbed':
            statuses[row['id']] = {'status': 'absorbed',
                                   'last_replayed': f'{stamp} · run {made["run"]}'}
            continue

        if action == 'withdraw':
            statuses[row['id']] = {'status': 'withdrawn',
                                   'reason': decision.get('reason') or 'withdrawn at replay'}
            continue
        if action == 'orphan':
            statuses[row['id']] = {'status': 'orphaned',
                                   'reason': decision.get('reason') or
                                             'not re-placed at replay'}
            continue

        if row['case'] == 'reapply' and (row.get('unique') or 'occurrence' in decision):
            edits.append({'id': row['id'], 'file': notes_rel,
                          'operation': row['operation'], 'concept': row['concept'],
                          'before': row['before'], 'after': row['after'],
                          'occurrence': decision.get('occurrence'),
                          'verify': decision.get('verify') or 'text',
                          'evidence_text': decision.get('evidence_text')})
            continue

        if action == 'apply_at' and decision.get('before'):
            moved_to = decision.get('concept') or row['concept']
            edits.append({'id': row['id'], 'file': notes_rel,
                          'operation': row['operation'], 'concept': moved_to,
                          'before': decision['before'], 'after': row['after'],
                          'occurrence': decision.get('occurrence'),
                          'verify': decision.get('verify') or 'text',
                          'evidence_text': decision.get('evidence_text')})
            # A re-placed entry records its new home and its new anchor, so the
            # next replay starts from where the fix actually is.
            if moved_to != row['concept'] or decision['before'] != row['before']:
                statuses[row['id']] = {'concept': moved_to,
                                       'before': decision['before']}
            continue

        # Unanswered. Nothing is guessed: the entry stays open and comes back.
        left.append({'id': row['id'], 'case': row['case'],
                     'question': row.get('question')})

    result = {'lesson': lesson, 'run': made['run'], 'scan': made['scan'],
              'unanswered': left}

    verdicts = {}
    if edits:
        import verify_fix
        checks = verify_fix.for_plan(course, {'edits': edits})
        verdicts = {c['id']: c for c in checks['checks']}
        # a fix that fails its check is dropped, never repaired
        edits = [e for e in edits if verdicts[e['id']]['ok']]
        for cid in checks['dropped']:
            statuses.setdefault(cid, {'status': 'orphaned',
                                      'reason': 'dropped at replay: '
                                                + (verdicts[cid].get('reason') or
                                                   'the check failed')})

    if edits:
        written = dapply.run(course, {'run_id': sorted(e['id'] for e in edits)[0],
                                      'edits': edits}, apply)
        result['write'] = written
        if written.get('aborted'):
            # A refusal is about the whole run, so no status moves: the entries
            # stay exactly as they were and the problems go into the report.
            result['aborted'] = True
            result['problems'] = written['problems']
            result['summary'] = {'reapplied': [], 'absorbed': [], 'orphaned': [],
                                 'withdrawn': [],
                                 'unanswered': [r['id'] for r in left],
                                 'refused': [q.get('id') for q in written['problems']]}
            return result
        ok_ids = {i for w in written['written'] for i in w['ids']}
        dropped_ids = {i for w in written['dropped'] for i in w['ids']}
        for e in edits:
            if e['id'] in ok_ids:
                statuses.setdefault(e['id'], {}).update({
                    'status': 'applied',
                    'verified': verdicts.get(e['id'], {}).get('verified',
                                                              'not machine-verified'),
                    'last_replayed': f'{stamp} · run {made["run"]}'})
            elif e['id'] in dropped_ids:
                statuses.setdefault(e['id'], {}).update(
                    {'status': 'orphaned',
                     'reason': 'the write did not verify and was rolled back'})
    else:
        result['write'] = {'applied': False, 'written': [], 'dropped': []}

    for cid, changes in statuses.items():
        dlog.set_fields(log_path, cid, changes, apply)
    result['statuses'] = statuses

    if apply:
        fingerprint.record(course, lesson, course / notes_rel, apply=True)

    result['summary'] = {
        'reapplied': [k for k, v in statuses.items() if v.get('status') == 'applied'],
        'absorbed': [k for k, v in statuses.items() if v.get('status') == 'absorbed'],
        'orphaned': [k for k, v in statuses.items() if v.get('status') == 'orphaned'],
        'withdrawn': [k for k, v in statuses.items() if v.get('status') == 'withdrawn'],
        'unanswered': [r['id'] for r in left]}
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('plan', 'run'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True); p.add_argument('--lesson', required=True)
        p.add_argument('--decisions')
        if name == 'run':
            p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    decisions = json.loads(Path(args.decisions).read_text(encoding='utf-8')) \
        if getattr(args, 'decisions', None) else None
    try:
        out = plan(args.course, args.lesson) if args.cmd == 'plan' \
            else run(args.course, args.lesson, decisions, args.apply)
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
