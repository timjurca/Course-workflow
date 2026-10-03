#!/usr/bin/env python3
"""Gather what B, C and E each found wrong, and turn one problem into one proposal.

Three skills report into D and they report differently. B's `D_verification.md`
is a run report: uncovered items, OCR and `verify` flags, contradictions it
noticed, broken links. C's `revision_findings.json` says *the notes disagree
with slide 22*. E's `explain_findings.json` says *the notes disagree with the
field*. Those are three descriptions of, often, one sentence.

So the collapse is the point of this module (G17): findings pointing at the same
(`concept`, `source`, anchor) become **one proposal carrying every origin and
every piece of evidence**, and closing it writes the status back to each source
file. The anchor half of that key is resolved in `anchor.py`, by located span,
because two findings on one passage must merge and two on adjacent passages must
not.

What does **not** change when E joins (G19): D's evidence ladder. An E finding
is a report, not evidence. A fix resting only on E's claim is `basis: user` and
carries `[student, sources differ: <ID>]`. A `basis: external` finding hands
over a snapshot that can corroborate the extraction — never replace it.

Three asymmetric write grants, and they are narrow on purpose:

    D_verification.md          never written. It is B's report, and D knows an
                               item is handled from its own log (`origin:
                               uncovered S24`), so `review` does not re-propose it.
    revision_findings.json     `status`, `closed_by`, `reason`. Nothing else.
    explain_findings.json      `status`, `closed_by`, `reason`. Nothing else.

A missing input degrades and says so: `review` on B's report alone, or on C's
findings alone, is a smaller run, not a failed one.

CLI:
    findings.py collect --course <path> --lesson L03
    findings.py close   --course <path> --id f-0007 --status resolved
                        --closed-by c-0003 [--reason <text>] [--apply]
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
import anchor                                                     # noqa: E402
import sections as _sections                                     # noqa: E402
import gate as dgate                                              # noqa: E402
import log as dlog                                                # noqa: E402

CLOSE_STATUSES = ('resolved', 'rejected', 'absorbed')
WRITABLE_FIELDS = ('status', 'closed_by', 'reason')

H2_RE = re.compile(r'^##\s+(?P<title>.+?)\s*$', re.MULTILINE)
BULLET_RE = re.compile(r'^\s*[-*]\s+(?P<text>.+?)\s*$', re.MULTILINE)

# B's report headings, as B §14 writes them. An unrecognised heading is carried
# through as `unparsed` rather than dropped: a silently skipped section of the
# verification report is a silently unreviewed problem.
VERIFICATION_SECTIONS = {
    'uncovered material': 'uncovered',
    'flags': 'flag',
    'verify flags': 'flag',
    'ocr flags': 'flag',
    'contradictions': 'contradiction',
    'down-weighted highlights': 'note',
    'transcript corrections': 'note',
    'discarded segments': 'note',
    'broken links': 'broken_link',
}


def _concept_of(notes: str, source_id: str) -> dict:
    """Which concept cites this ID. B's report names the item, not the concept.

    Returns `{'concept': id|None, 'candidates': [...]}`. It used to walk H2
    sections, so every ID in `## Concepts` came back labelled with whichever
    concept appeared first in that 700-line block. Now it asks the concept
    blocks, and when an ID is cited by several concepts -- 106 IDs across the
    corpus, one of them in 11 blocks -- it returns no concept and hands over the
    candidates for the plan to show, rather than guessing silently.
    """
    return _sections.concept_of(notes, source_id)


def read_verification(path: Path, notes: str) -> dict:
    """B's run report. Read tolerantly, never written."""
    out = {'file': str(path), 'exists': path.is_file(), 'items': [],
           'unparsed': []}
    if not out['exists']:
        out['note'] = ('no D_verification.md: review runs on the findings files '
                       'alone, and says so')
        return out
    text = path.read_text(encoding='utf-8')
    heads = list(H2_RE.finditer(text))
    for n, m in enumerate(heads):
        end = heads[n + 1].start() if n + 1 < len(heads) else len(text)
        title = m.group('title').strip().lower()
        kind = VERIFICATION_SECTIONS.get(title)
        block = text[m.end():end]
        if kind is None:
            if block.strip():
                out['unparsed'].append({'heading': m.group('title').strip(),
                                        'lines': block.strip().splitlines()})
            continue
        if kind == 'note':
            continue
        for b in BULLET_RE.finditer(block):
            line = b.group('text')
            ids = anchor.SOURCE_ID_RE.findall(line)
            who = _concept_of(notes, ids[0]) if ids else {'concept': None,
                                                          'candidates': []}
            out['items'].append({
                'origin': f'{kind} {ids[0]}' if ids else kind,
                'from': 'course-notes', 'type': kind,
                'source': ids[0] if ids else None,
                'concept': who['concept'],
                'concept_candidates': who['candidates'],
                'quote': line, 'writable': False})
    return out


def _load_json(path: Path) -> tuple[list, dict]:
    """Both shapes: a bare list (C writes one) and {applied_renumbers, findings}."""
    if not path.is_file():
        return [], {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(data, list):
        return data, {'_shape': 'list'}
    return data.get('findings') or [], data


def read_findings(path: Path, lesson: str, who: str, prefix: str) -> dict:
    rows, _ = _load_json(path)
    out = {'file': str(path), 'exists': path.is_file(), 'items': []}
    if not out['exists']:
        out['note'] = f'no {path.name}: review runs without {who} findings, and says so'
        return out
    for row in rows:
        if row.get('lesson') and row.get('lesson') != lesson:
            continue
        if row.get('status') not in (None, 'open'):
            continue
        fid = row.get('id') or ''
        out['items'].append({
            'id': fid, 'origin': f'{prefix} {fid}'.strip(), 'from': who,
            'type': row.get('type'), 'source': row.get('source'),
            'concept': row.get('concept'),
            'quote': row.get('quote') or row.get('notes_text') or '',
            'claim': row.get('explain_claim'),
            'basis': row.get('basis'),
            'evidence': row.get('evidence'),
            'writable': True, 'file': str(path)})
    return out


def collect(course: Path | str, lesson: str) -> dict:
    course = Path(course)
    folder = dgate.lesson_dir(course, lesson)
    notes_path = dgate.notes_path(course, lesson)
    if folder is None or notes_path is None:
        return {'ok': False, 'reason': f'no notes for {lesson}'}
    notes = notes_path.read_text(encoding='utf-8')

    b = read_verification(folder / '.work' / 'D_verification.md', notes)
    c = read_findings(course / '.data' / 'revision_findings.json', lesson,
                      'course-revision', 'finding')
    e = read_findings(course / '.data' / 'explain_findings.json', lesson,
                      'course-explain', 'explain')

    # already handled: D skips anything in its log with the same origin
    log_path = folder / 'notes_corrections.md'
    parsed = dlog.parse_log(log_path)
    dlog.require_parsable(parsed)
    known = {str(x['values'].get('origin') or '') for x in parsed['entries']}

    items, skipped = [], []
    for source in (b, c, e):
        for item in source['items']:
            if item['origin'] in known:
                skipped.append(item['origin'])
            else:
                items.append(item)

    merged = anchor.collapse(notes, items)
    proposals = []
    for g in merged['groups']:
        rows = g['items']
        proposals.append({
            'concept': g['concept'], 'source': g['source'], 'span': g['span'],
            'located': g['located'], 'ambiguous': g['ambiguous'],
            'origins': g['origins'],
            'from': sorted({r['from'] for r in rows}),
            'types': sorted({r['type'] for r in rows if r.get('type')}),
            'quotes': [r['quote'] for r in rows if r.get('quote')],
            'evidence': [r['evidence'] for r in rows if r.get('evidence')],
            'claims': [r['claim'] for r in rows if r.get('claim')],
            'closes': [{'id': r['id'], 'file': r['file']} for r in rows
                       if r.get('writable') and r.get('id')],
            'ladder_note': _ladder(rows)})

    return {'ok': True, 'lesson': lesson,
            'inputs': {'verification': {'present': b['exists'],
                                        'items': len(b['items']),
                                        'unparsed': b['unparsed'],
                                        'note': b.get('note')},
                       'revision': {'present': c['exists'], 'items': len(c['items']),
                                    'note': c.get('note')},
                       'explain': {'present': e['exists'], 'items': len(e['items']),
                                   'note': e.get('note')}},
            'skipped_already_in_log': sorted(set(skipped)),
            'collapsed': merged['collapsed'],
            'proposals': proposals}


def _ladder(rows: list[dict]) -> str:
    """State, per proposal, what the evidence ladder allows this to rest on."""
    from_e = [r for r in rows if r['from'] == 'course-explain']
    others = [r for r in rows if r['from'] != 'course-explain']
    if not from_e:
        return 'the extractions decide; open the cited location only if they cannot'
    external = any(r.get('basis') == 'external' for r in from_e)
    if others:
        return ('course-explain reports a conflict here too; it is corroboration, '
                'never the primary source. The extraction still decides.')
    if external:
        return ('course-explain has an external snapshot. It may corroborate the '
                'extraction; it can never replace it. A fix resting on it alone is '
                'basis: user with [student, sources differ: <ID>].')
    return ('this rests only on course-explain\'s own claim, which is a report and '
            'not evidence: basis: user with [student, sources differ: <ID>]')


def close(course: Path | str, fid: str, status: str, closed_by: str | None = None,
          reason: str | None = None, apply: bool = False) -> dict:
    """Set the three fields D is allowed to set, in whichever file holds the id."""
    course = Path(course)
    if status not in CLOSE_STATUSES:
        return {'ok': False,
                'reason': f'status must be one of {", ".join(CLOSE_STATUSES)}'}
    for name in ('revision_findings.json', 'explain_findings.json'):
        path = course / '.data' / name
        rows, blob = _load_json(path)
        hit = next((r for r in rows if r.get('id') == fid), None)
        if hit is None:
            continue
        before = dict(hit)
        hit['status'] = status
        if closed_by:
            hit['closed_by'] = closed_by
        if reason:
            hit['reason'] = reason
        touched = [k for k in hit if before.get(k) != hit.get(k)]
        outside = [k for k in touched if k not in WRITABLE_FIELDS]
        if outside:
            return {'ok': False, 'file': name,
                    'reason': f'refusing to write {", ".join(outside)}: D may set only '
                              + ', '.join(WRITABLE_FIELDS)}
        if apply:
            payload = rows if blob.get('_shape') == 'list' else {**blob, 'findings': rows}
            if isinstance(payload, dict):
                payload.pop('_shape', None)
            tmp = path.with_name(path.name + '.tmp')
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8')
            tmp.replace(path)
        return {'ok': True, 'file': name, 'id': fid, 'status': status,
                'changed': touched, 'written': apply}
    return {'ok': False, 'reason': f'{fid} is not in revision_findings.json or '
                                   'explain_findings.json'}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('collect')
    p.add_argument('--course', required=True); p.add_argument('--lesson', required=True)
    p = sub.add_parser('close')
    p.add_argument('--course', required=True); p.add_argument('--id', required=True)
    p.add_argument('--status', required=True); p.add_argument('--closed-by')
    p.add_argument('--reason'); p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    try:
        out = collect(args.course, args.lesson) if args.cmd == 'collect' \
            else close(args.course, args.id, args.status, args.closed_by,
                       args.reason, args.apply)
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
