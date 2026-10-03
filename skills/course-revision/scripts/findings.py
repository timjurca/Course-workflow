#!/usr/bin/env python3
"""Report a note problem to skill D once, and never a second time.

C sees things D wants to know: a detail cited in a section but absent from the
notes text, an extraction that contradicts the notes, a formula that fails the
calculation check. It reports them and stops -- C never edits a note.

The whole value of this module is the filter in front of the append. A findings
file that re-reports the same problem every week is worse than no findings file:
D's review turns into forty duplicates, the student stops reading it, and the
one new finding in the list is missed. Four exclusions, and each closes a
different path back in:

  1  the notes' own `## Uncovered material`   B already said it did not fit
  2  B's `.work/D_verification.md`            B already flagged it for D
  3  a correction marker in the section       D already ruled on that passage
  4  C's own findings, **of any status**      including ones D rejected

Exclusion 3 covers all three of D's markers (`source error`, `student, sources
differ`, `unverified`). A passage carrying any of them has been looked at by a
human with the sources open; C re-reporting it would be C arguing with that
decision on every run.

Exclusion 4 has one deliberate hole. A finding D closed as `resolved` whose
problem has come back is not a duplicate: it is the alarm that a fix was lost,
almost always a correction replay that did not land. That case appends a new
finding carrying `reopens:`, and the report says so out loud.

CLI:
    findings.py add   --course <path> --lesson L03 --candidates <json> [--apply]
    findings.py list  --course <path> [--status open]
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
import gate                                                        # noqa: E402
import markers as _markers                                         # noqa: E402
import renumber                                                    # noqa: E402
from vault import read_frontmatter                                 # noqa: E402

FINDINGS_REL = Path('.data') / 'revision_findings.json'
TYPES = ('gap', 'contradiction', 'suspect')
# The canonical parser. The local copy this replaced truncated `B4.2.11` to a
# phantom `B4.2` and never captured the `!`; see shared/scripts/markers.py.
SOURCE_ID_RE = _markers.SOURCE_ID_RE
# The three markers of note-invariants section 3, matched by their closed
# leading words so an unknown shape is never mistaken for one of them.
CORRECTION_MARKER_RE = re.compile(
    r'\[(?:source error|student, sources differ|unverified):\s*([^\]]+)\]')
VERIFY_RE = re.compile(r'\[([^\]]*?),\s*(?:OCR,\s*)?verify\]')


def path_of(course: Path | str) -> Path:
    return Path(course) / FINDINGS_REL


def empty(course: Path | str) -> dict:
    return {'applied_renumbers': [b['id'] for b in renumber.renumber_blocks(course)],
            'findings': []}


def load(course: Path | str) -> dict:
    p = path_of(course)
    if not p.is_file():
        return empty(course)
    data = json.loads(p.read_text(encoding='utf-8'))
    if isinstance(data, list):           # tolerate the bare-array shape
        data = {'applied_renumbers': [], 'findings': data}
    data.setdefault('applied_renumbers', [])
    data.setdefault('findings', [])
    return data


def save(course: Path | str, data: dict) -> Path:
    p = path_of(course)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    os.replace(tmp, p)
    return p


def next_id(data: dict) -> str:
    used = [int(m.group(1)) for f in data['findings']
            if (m := re.match(r'^f-(\d+)$', str(f.get('id') or '')))]
    return 'f-%04d' % ((max(used) + 1) if used else 1)


# ---------------------------------------------------------------- note reading

def sections_by_concept(body: str) -> dict:
    """H2 -> its text, keyed by the concept comment under the heading."""
    out, cid, buf = {}, None, []
    for line in body.splitlines():
        if line.startswith('## '):
            if cid:
                out[cid] = '\n'.join(buf)
            cid, buf = None, []
            continue
        m = gate.CONCEPT_RE.search(line)
        if m and cid is None and not buf:
            cid = m.group(1)
            continue
        buf.append(line)
    if cid:
        out[cid] = '\n'.join(buf)
    return out


def uncovered_ids(body: str) -> set:
    """Source IDs the notes already list under `## Uncovered material`."""
    grab, ids = False, set()
    for line in body.splitlines():
        if line.startswith('## '):
            grab = line[3:].strip() == 'Uncovered material'
            continue
        if grab:
            ids.update(SOURCE_ID_RE.findall(line))
    return ids


def verification_ids(work: Path) -> set:
    p = work / 'D_verification.md'
    if not p.is_file():
        return set()
    return set(SOURCE_ID_RE.findall(p.read_text(encoding='utf-8')))


def marked_ids(section_text: str) -> set:
    """IDs the section already marks: D's three markers, or a verify flag."""
    ids = set()
    for inner in CORRECTION_MARKER_RE.findall(section_text):
        ids.update(SOURCE_ID_RE.findall(inner))
    for inner in VERIFY_RE.findall(section_text):
        ids.update(SOURCE_ID_RE.findall(inner))
    return ids


# ---------------------------------------------------------------- the filter

def add(course: Path | str, lesson: str, candidates: list[dict],
        apply: bool = False) -> dict:
    course = Path(course)
    lesson = lesson.upper()
    npath = gate.notes_path(course, lesson)
    if npath is None:
        raise FileNotFoundError(f'no notes for {lesson}; the gate should have '
                                'stopped this run before a finding was considered')
    _fm, body = read_frontmatter(npath)
    folder = gate.lesson_folder(course, lesson)
    sections = sections_by_concept(body)
    already_uncovered = uncovered_ids(body)
    already_verified = verification_ids(folder / '.work')

    data = load(course)
    index: dict = {}
    for f in data['findings']:
        index.setdefault((f.get('type'), f.get('concept'), f.get('source')), []).append(f)

    added, skipped, reopened = [], [], []
    for cand in candidates:
        kind = cand.get('type')
        if kind not in TYPES:
            raise ValueError(f'unknown finding type {kind!r}; the closed set is '
                             f'{", ".join(TYPES)}')
        cid, src = cand.get('concept'), cand.get('source')
        key = (kind, cid, src)

        if src and src in already_uncovered:
            skipped.append({**cand, 'why': 'the notes already list it under '
                                           '## Uncovered material'})
            continue
        if src and src in already_verified:
            skipped.append({**cand, 'why': 'course-notes already flagged it in '
                                           'D_verification.md'})
            continue
        if src and src in marked_ids(sections.get(cid, '')):
            skipped.append({**cand, 'why': 'the passage already carries a correction '
                                           'marker or a verify flag'})
            continue

        prior = index.get(key) or []
        if prior:
            resolved = [f for f in prior if f.get('status') == 'resolved']
            live = [f for f in prior if f.get('status') != 'resolved']
            if live:
                skipped.append({**cand, 'why': f'already logged as '
                                               f'{live[-1]["id"]} '
                                               f'(status {live[-1].get("status")})'})
                continue
            cand = {**cand, 'reopens': resolved[-1]['id']}
            reopened.append({'reopens': resolved[-1]['id'], 'concept': cid,
                             'source': src})

        row = {'id': next_id(data), 'date': date.today().isoformat(),
               'lesson': lesson, 'type': kind, 'concept': cid, 'source': src,
               'quote': cand.get('quote'), 'status': 'open'}
        if cand.get('reopens'):
            row['reopens'] = cand['reopens']
        if cand.get('notes_text'):
            row['notes_text'] = cand['notes_text']
        data['findings'].append(row)
        index.setdefault(key, []).append(row)
        added.append(row)

    if apply and added:
        save(course, data)
    return {'lesson': lesson, 'added': added, 'skipped': skipped,
            'reopened': reopened, 'total': len(data['findings']),
            'written': bool(apply and added),
            'note': 'a reopened finding means a fix was lost, almost always a '
                    'correction replay that did not land'
                    if reopened else None}


def listing(course: Path | str, status: str | None = None) -> dict:
    data = load(course)
    rows = [f for f in data['findings']
            if status is None or f.get('status') == status]
    counts: dict = {}
    for f in data['findings']:
        counts[f.get('status') or 'open'] = counts.get(f.get('status') or 'open', 0) + 1
    return {'findings': rows, 'counts': counts,
            'applied_renumbers': data['applied_renumbers']}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('add')
    a.add_argument('--course', required=True)
    a.add_argument('--lesson', required=True)
    a.add_argument('--candidates', required=True, help='JSON file or literal')
    a.add_argument('--apply', action='store_true')
    l = sub.add_parser('list')
    l.add_argument('--course', required=True)
    l.add_argument('--status')
    args = ap.parse_args(argv)
    if args.cmd == 'add':
        try:
            p = Path(args.candidates)
            raw = p.read_text(encoding='utf-8') if p.is_file() else args.candidates
        except OSError:
            raw = args.candidates
        out = add(args.course, args.lesson, json.loads(raw), args.apply)
    else:
        out = listing(args.course, args.status)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
