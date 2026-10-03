#!/usr/bin/env python3
"""Hand D a tier-3 conflict, once, on confirmation, and never anything else.

E is the only skill that generates content the sources do not contain, so it is
the only skill that can *disagree* with the notes on grounds the notes cannot
check. That disagreement is worth recording - D exists to act on it - and it is
also the easiest way to fill D's review queue with model opinion, which is
exactly the basis D refuses to act on alone.

Three rules keep that from happening, and all three are enforced here:

**Only a tier-3 claim becomes a finding.** A gap E filled from its own knowledge
is tier 2 and is not a finding. A `[your note]` is never a finding: the
student's own writing is not evidence, and logging it would turn a confusion
into a proposal to change the notes. A rejected framing is never a finding
either - it is a fact about E's output, not about the notes.

**Nothing is written without a yes.** The conflict is stated, then asked about.
This module's `add` refuses to write without `--apply`, and the caller is
expected to have asked first.

**Duplicates are skipped by (type, concept, source), whatever their status.**
Not "open findings" - any status. A closed finding whose problem is still
visible means D looked at it and decided; re-raising it is how a review queue
becomes noise. E also skips anything already carrying one of D's correction
markers, and anything B already flagged in `D_verification.md`, because both
mean the passage is already known.

An E finding is a **report, not evidence**. D's evidence ladder is unchanged by
one: a fix resting only on E's claim is `basis: user` and carries D's
`[student, sources differ: <ID>]` marker. A `basis: external` finding hands D a
snapshot, usable as corroboration, never as the primary source.

CLI:
    findings.py list  --course <c>
    findings.py check --course <c> --type differs --concept <id> --source S16
                      [--lesson L03]
    findings.py add   --course <c> --type differs --concept <id> --source S16
                      --lesson L03 --notes-text <t> --claim <t> --basis external
                      [--evidence <t>] [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import coverage as cov                                               # noqa: E402
import fields                                                        # noqa: E402
import ladder                                                        # noqa: E402
import scope                                                         # noqa: E402
from vault import parse_frontmatter                                  # noqa: E402

FINDINGS_REL = Path('.data') / 'explain_findings.json'
TYPES = ('differs', 'differs_source')
BASES = ('model', 'external')

# D's three correction markers. A passage already carrying one is settled: D
# looked at it, recorded what it decided, and E does not re-open it.
D_MARKER_RE = re.compile(r'\[(?:source error|student, sources differ|unverified):\s*'
                         r'(?P<id>[SBTAHNCVKG]\d[\w.!]*)\]')


def load(course: Path | str) -> dict:
    path = Path(course) / FINDINGS_REL
    if not path.is_file():
        return {'applied_renumbers': [], 'findings': [], '_status': 'missing'}
    try:
        data = json.loads(path.read_text(encoding='utf-8')) or {}
        data.setdefault('applied_renumbers', [])
        data.setdefault('findings', [])
        data['_status'] = 'ok'
        return data
    except Exception as exc:
        return {'applied_renumbers': [], 'findings': [], '_status': 'unparseable',
                '_error': str(exc)}


def _write(course: Path | str, data: dict) -> Path:
    path = Path(course) / FINDINGS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in data.items() if not k.startswith('_')}
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    os.replace(tmp, path)
    return path


def check(course: Path | str, ftype: str, concept: str, source: str,
          lesson: str | None = None) -> dict:
    """Would this be a duplicate? Three places to look, not one."""
    course = Path(course)
    data = load(course)
    out = {'type': ftype, 'concept': concept, 'source': source, 'lesson': lesson,
           'duplicate': False, 'reasons': [], 'findings_status': data['_status']}

    for f in data['findings']:
        if (f.get('type'), f.get('concept'), f.get('source')) == (ftype, concept, source):
            out['duplicate'] = True
            out['reasons'].append({
                'code': 'own_finding', 'id': f.get('id'), 'status': f.get('status'),
                'message': ('E already raised this (type, concept, source); a '
                            'closed one means D decided, and it is not re-opened')})

    keys = [lesson] if lesson else []
    if not keys:
        entry = cov.load_concepts(course).get(concept) or {}
        keys = [s.get('lesson') for s in entry.get('sections') or [] if s.get('lesson')]
    for key in keys:
        folder = ladder.lesson_folder(course, key)
        if folder is None:
            continue
        notes = ladder.notes_file(folder, key)
        if notes is not None:
            _, body = parse_frontmatter(notes.read_text(encoding='utf-8',
                                                        errors='replace'))
            for sec in scope.split_h2(body):
                if sec['concept'] != concept:
                    continue
                for m in D_MARKER_RE.finditer(sec['body']):
                    if m.group('id') == source:
                        out['duplicate'] = True
                        out['reasons'].append({
                            'code': 'correction_marker', 'lesson': key,
                            'marker': m.group(0),
                            'message': ('the passage already carries one of D\'s '
                                        'correction markers: settled, not re-raised')})
        dv = folder / '.work' / 'D_verification.md'
        if dv.is_file() and source in dv.read_text(encoding='utf-8', errors='replace'):
            out['duplicate'] = True
            out['reasons'].append({
                'code': 'd_verification', 'lesson': key,
                'message': f'{source} is already listed in D_verification.md'})
    return out


def add(course: Path | str, ftype: str, concept: str, source: str, lesson: str,
        notes_text: str, claim: str, basis: str, evidence: str | None = None,
        apply: bool = False) -> dict:
    course = Path(course)
    if ftype not in TYPES:
        return {'written': False, 'error': f'type must be one of {TYPES}'}
    if basis not in BASES:
        return {'written': False, 'error': f'basis must be one of {BASES}'}
    dup = check(course, ftype, concept, source, lesson)
    if dup['duplicate']:
        return {'written': False, 'duplicate': True, 'reasons': dup['reasons'],
                'say': 'say it is already known and by whom; write nothing'}
    data = load(course)
    if data['_status'] == 'unparseable':
        return {'written': False, 'error': data.get('_error'),
                'say': ('explain_findings.json does not parse: report it, write no '
                        'findings, and keep explaining')}

    # A confirmed finding is one of the two writes that migrate first: a finding
    # carrying the old lesson number would point D at the wrong lesson.
    migration = fields.migrate(course, apply=apply) if apply else \
        {'pending': fields.pending(course)['pending']}

    state = cov.load_state(course)
    nid = int(state.get('next_finding_id') or 1)
    used = {f.get('id') for f in data['findings']}
    while f'x-{nid:04d}' in used:
        nid += 1
    row = {'id': f'x-{nid:04d}', 'date': date.today().isoformat(), 'lesson': lesson,
           'type': ftype, 'concept': concept, 'source': source,
           'notes_text': notes_text, 'explain_claim': claim, 'basis': basis,
           'evidence': evidence or '', 'status': 'open'}
    data['findings'].append(row)
    out = {'finding': row, 'written': False, 'renumbers': migration.get('pending'),
           'opt_in': 'nothing is written without the student saying yes',
           'd_reads_it_as': ('a report, not evidence: a fix resting only on this is '
                             'basis user and carries [student, sources differ: '
                             f'{source}]')}
    if apply:
        _write(course, data)
        state['next_finding_id'] = nid + 1
        cov.write_state(course, state)
        out['written'] = True
        out['next'] = f'run course-corrections review for {lesson}'
    return out


def listing(course: Path | str) -> dict:
    data = load(course)
    rows = data['findings']
    return {'status': data['_status'], 'count': len(rows),
            'open': [f for f in rows if f.get('status') == 'open'],
            'closed': [f for f in rows if f.get('status') not in (None, 'open')],
            'applied_renumbers': data.get('applied_renumbers'),
            'd_may_set': ['status', 'closed_by', 'reason']}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list'); p.add_argument('--course', required=True)
    p = sub.add_parser('check')
    p.add_argument('--course', required=True); p.add_argument('--type', required=True)
    p.add_argument('--concept', required=True); p.add_argument('--source', required=True)
    p.add_argument('--lesson')
    p = sub.add_parser('add')
    p.add_argument('--course', required=True); p.add_argument('--type', required=True)
    p.add_argument('--concept', required=True); p.add_argument('--source', required=True)
    p.add_argument('--lesson', required=True)
    p.add_argument('--notes-text', dest='notes_text', required=True)
    p.add_argument('--claim', required=True)
    p.add_argument('--basis', required=True, choices=BASES)
    p.add_argument('--evidence'); p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'list':
        out = listing(args.course)
    elif args.cmd == 'check':
        out = check(args.course, args.type, args.concept, args.source, args.lesson)
    else:
        out = add(args.course, args.type, args.concept, args.source, args.lesson,
                  args.notes_text, args.claim, args.basis, args.evidence, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
