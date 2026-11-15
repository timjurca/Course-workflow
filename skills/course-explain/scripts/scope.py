#!/usr/bin/env python3
"""Load one concept's material, and nothing else.

E is a tutoring loop, not a batch job: a session is many questions, and a skill
that loads a whole lesson per question spends the student's context on material
it will not use. Everything here is therefore scoped to one concept - the
matching H2 sections, the extraction items for the IDs those sections cite, and
the narrow slices of two files E is allowed to open only where they still add
something.

**The narrow reads are the point of this module, not a detail.** A correction
whose `status` is `applied` at the notes' current `run` is already in the text E
is reading; opening the log to find it adds nothing and widens E's reach into a
file it does not own. An `active` erratum is already applied in the extraction E
is reading, for the same reason. So the log is opened for `pending`, `orphaned`
and needs-replay entries only, and an erratum surfaces only when it is newer
than the extraction that would have carried it. That is the difference between
E reading what it needs and E reading D's files.

**The student's own writing is loaded and marked, never asserted.** Protection
is against writes, not reads: `## My additions`, the overview's `## My notes`
and C's `## My questions` are where a misunderstanding is actually visible, and
they come back here tagged `[your note]` so that nothing quoted from them can be
laundered into an explanation as if it were course material.

**The depth switch resets the scope.** `explain_depth` is overridable per
request, so a session can legally reach "task index loaded, now working a
problem". Context does not unload by itself, so the rule is structural: a switch
to `analogous` discards everything loaded and re-resolves. A switch back needs
no reset, because the task index is a negative filter and acquiring it late is
harmless.

CLI:
    scope.py section --course <c> --concept <id> [--lesson L03]
    scope.py items   --course <c> --lesson L03 --ids S14 S16
    scope.py student --course <c> --lesson L03
    scope.py tasks   --course <c>
    scope.py reset   --course <c> --to analogous [--apply]
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
import coverage as cov                                               # noqa: E402
import ladder                                                        # noqa: E402
import sections as _sections                                         # noqa: E402
from vault import read_frontmatter                                   # noqa: E402
from runstamp import norm_run                                        # noqa: E402

H2_RE = re.compile(r'^##\s+(?P<title>.+?)\s*$', re.MULTILINE)
CONCEPT_COMMENT_RE = re.compile(r'<!--\s*concept:\s*(?P<id>[a-z0-9-]+)\s*-->')
ITEM_RE = re.compile(r'^###\s+(?P<id>\S+)\s*$', re.MULTILINE)
LOG_HEAD_RE = re.compile(r'^##\s+(?P<id>c-\d+)\s*·\s*(?P<date>\S+)\s*·\s*(?P<action>\w+)',
                         re.MULTILINE)
RUN_RE = re.compile(r'run\s+(?P<run>\S+)')

STUDENT_BLOCKS = ('My additions', 'My notes', 'My questions')


def split_h2(text: str) -> list:
    """Every concept's own section, plus the H2 containers that carry none.

    The name is historical. It used to split on H2 only and take the first
    `<!-- concept: -->` inside each one, which meant `## Concepts` came back as
    a single 70,788-character block labelled with its first concept and every
    other concept in the lesson resolved to nothing. Concepts live on H3 (360 of
    364 across 13 lessons), so the concept blocks come from
    `shared/sections.concept_blocks` now. H2 containers with no concept of their
    own -- Definitions, Recap, My additions -- are kept, because callers still
    look those up by heading.
    """
    out = [{'heading': b['heading'], 'concept': b['concept'],
            'body': text[b['body_start']:b['end']].strip(), 'start': b['start']}
           for b in _sections.concept_blocks(text)]
    claimed = {b['start'] for b in _sections.concept_blocks(text)}
    marks = list(H2_RE.finditer(text))
    for i, m in enumerate(marks):
        if m.start() in claimed:
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append({'heading': m.group('title'), 'concept': None,
                    'body': text[m.end():end].strip(), 'start': m.start()})
    return sorted(out, key=lambda r: r['start'])


def cited_ids(text: str) -> list:
    """Source-marker IDs inside a section, in order, deduplicated.

    Only B's family: an uppercase letter from SBTAHNCVKG followed immediately by
    a digit (note-invariants section 5). E's own tier markers and D's correction
    markers have deliberately different shapes and are not collected here.
    """
    ids = []
    for bracket in re.findall(r'\[([^\]]+)\]', text):
        for part in bracket.split(','):
            part = part.strip()
            token = part.split()[0] if part else ''
            if re.fullmatch(r'[SBTAHNCVKG]\d[\w.!]*', token) and token not in ids:
                ids.append(token)
    return ids


def section(course: Path | str, concept: str, lesson: str | None = None) -> dict:
    """The H2 sections carrying this concept ID, across its lessons."""
    course = Path(course)
    concepts = cov.load_concepts(course)
    entry = concepts.get(concept) or {}
    lessons = [lesson] if lesson else [s.get('lesson') for s in entry.get('sections') or []]
    out = {'concept': concept, 'title': entry.get('title'),
           'retired': bool(entry.get('retired')), 'sections': [],
           'source_ids': [], 'lessons': lessons, 'missing_in': []}
    for key in [k for k in lessons if k]:
        folder = ladder.lesson_folder(course, key)
        notes = ladder.notes_file(folder, key) if folder else None
        if notes is None:
            out['missing_in'].append(key)
            continue
        fm, body = read_frontmatter(notes)
        for sec in split_h2(body):
            if sec['concept'] != concept:
                continue
            ids = cited_ids(sec['body'])
            out['sections'].append({
                'lesson': key, 'file': str(notes.relative_to(course)),
                'heading': sec['heading'], 'text': sec['body'],
                'source_ids': ids, 'notes_run': norm_run(fm.get('run')) or None})
            for i in ids:
                if i not in out['source_ids']:
                    out['source_ids'].append(i)
    if not out['sections']:
        out['note'] = ('no section carries this concept ID in the notes; fall back '
                       'to heading text and say resolution is degraded')
    return out


def items(course: Path | str, lesson: str, ids: list) -> dict:
    """Extraction items for named IDs only. Never a whole extraction file."""
    course = Path(course)
    folder = ladder.lesson_folder(course, lesson)
    out = {'lesson': lesson, 'requested': ids, 'items': [], 'not_found': [],
           'runs': [], 'files': []}
    if folder is None:
        out['error'] = 'no lesson folder'
        out['not_found'] = list(ids)
        return out
    wanted = set(ids)
    for path in ladder.extractions(folder):
        text = path.read_text(encoding='utf-8', errors='replace')
        head = text.split('###', 1)[0]
        run = re.search(r'^run:\s*(\S+)', head, re.MULTILINE)
        shash = re.search(r'^sources_hash:\s*(\S+)', head, re.MULTILINE)
        run = (norm_run(run.group(1)) or None) if run else None
        if run and run not in out['runs']:
            out['runs'].append(run)
        out['files'].append({'file': str(path.relative_to(course)), 'run': run,
                             'sources_hash': shash.group(1) if shash else None})
        marks = list(ITEM_RE.finditer(text))
        for i, m in enumerate(marks):
            if m.group('id') not in wanted:
                continue
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            block = text[m.end():end].strip()
            tags = re.search(r'^tags:\s*\[(.*?)\]', block, re.MULTILINE)
            body = re.sub(r'^tags:.*$', '', block, count=1, flags=re.MULTILINE).strip()
            out['items'].append({
                'id': m.group('id'), 'run': run,
                'tags': [t.strip() for t in tags.group(1).split(',')] if tags else [],
                'text': body, 'file': str(path.relative_to(course))})
    found = {i['id'] for i in out['items']}
    out['not_found'] = [i for i in ids if i not in found]
    if len(out['runs']) > 1:
        out['warning'] = ('these items come from more than one B run; say which '
                          'run each came from')
    return out


# ------------------------------------------------------- the two narrow reads

def corrections(course: Path | str, lesson: str) -> dict:
    """Status lines always; before/after only where the fix is not in the text.

    An entry that is `applied` at the notes' current run is already in the notes
    E has loaded, so its before/after text is withheld: reading it would add
    nothing and would widen E's reach into D's file for no gain.
    """
    course = Path(course)
    folder = ladder.lesson_folder(course, lesson)
    out = {'lesson': lesson, 'entries': [], 'file': None, 'notes_run': None}
    if folder is None:
        return out
    notes = ladder.notes_file(folder, lesson)
    if notes is not None:
        try:
            fm, _ = read_frontmatter(notes)
            out['notes_run'] = norm_run(fm.get('run')) or None
        except Exception:
            pass
    log = folder / 'notes_corrections.md'
    if not log.is_file():
        out['note'] = 'no correction log for this lesson'
        return out
    out['file'] = str(log.relative_to(course))
    text = log.read_text(encoding='utf-8', errors='replace')
    heads = list(LOG_HEAD_RE.finditer(text))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        block = text[m.end():end]
        fields = dict(re.findall(r'^(\w+):\s*(.*)$', block, re.MULTILINE))
        status = (fields.get('status') or '').strip()
        replayed = fields.get('last_replayed') or ''
        run_m = RUN_RE.search(replayed)
        replayed_run = norm_run(run_m.group('run')) if run_m else None
        needs_replay = (status == 'applied' and out['notes_run']
                        and replayed_run != out['notes_run'])
        in_the_text = status == 'applied' and not needs_replay
        row = {'id': m.group('id'), 'date': m.group('date'),
               'action': m.group('action'), 'status': status,
               'concept': (fields.get('concept') or '').strip(),
               'last_replayed': replayed.strip() or None,
               'needs_replay': bool(needs_replay),
               'already_in_the_notes': bool(in_the_text)}
        if not in_the_text:
            row['before'] = (fields.get('before') or '').strip().strip('"')
            row['after'] = (fields.get('after') or '').strip().strip('"')
            row['why_readable'] = 'not applied at the notes\' current run'
        out['entries'].append(row)
    out['open'] = [r['id'] for r in out['entries']
                   if r['status'] in ('pending', 'orphaned') or r['needs_replay']]
    return out


def errata(course: Path | str, lesson: str, extraction_runs: list | None = None) -> dict:
    """Errata newer than the extraction that would already carry them."""
    course = Path(course)
    path = course / '.data' / 'source_errata.json'
    out = {'lesson': lesson, 'relevant': [], 'suppressed': [], 'file_exists': path.is_file()}
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding='utf-8')) or {}
    except Exception as exc:
        out['error'] = str(exc)
        return out
    runs = extraction_runs
    if runs is None:
        folder = ladder.lesson_folder(course, lesson)
        runs = []
        for p in (ladder.extractions(folder) if folder else []):
            m = re.search(r'^run:\s*(\S+)', p.read_text(encoding='utf-8',
                                                        errors='replace'), re.MULTILINE)
            if m and m.group(1) not in runs:
                runs.append(m.group(1))
    newest = max(runs) if runs else None
    out['extraction_run'] = newest
    for e in data.get('errata') or []:
        if e.get('lesson') not in (None, lesson) and e.get('lesson') != lesson:
            continue
        # The extraction predates the erratum only when the erratum is newer.
        # Otherwise the correction is already inside the text E is reading.
        if newest and (e.get('date') or '') <= newest[:10]:
            out['suppressed'].append({'id': e.get('id'), 'item': e.get('item'),
                                      'why': 'already applied in the extraction'})
            continue
        out['relevant'].append(e)
    return out


def student(course: Path | str, lesson: str) -> dict:
    """The three protected blocks. Read, marked `[your note]`, never written."""
    course = Path(course)
    folder = ladder.lesson_folder(course, lesson)
    out = {'lesson': lesson, 'blocks': [], 'marker': '[your note]',
           'rules': ['never tier 1', 'never asserted', 'never evidence',
                     'never written to', 'named when used']}
    candidates = []
    if folder is not None:
        notes = ladder.notes_file(folder, lesson)
        if notes:
            candidates.append((notes, 'My additions'))
        for p in sorted(folder.glob('*_Overview.md')):
            candidates.append((p, 'My notes'))
    rev = course / 'Exams' / 'Revision_questions'
    if rev.is_dir():
        for p in sorted(rev.glob(f'*_{lesson.upper()}_Revision.md')):
            candidates.append((p, 'My questions'))
    for path, block in candidates:
        try:
            _, body = read_frontmatter(path)
        except Exception:
            continue
        for sec in split_h2(body):
            if sec['heading'].strip() != block or not sec['body'].strip():
                continue
            out['blocks'].append({'file': str(path.relative_to(course)),
                                  'block': block, 'text': sec['body']})
    return out


def tasks(course: Path | str) -> dict:
    """C's task index: a negative filter, and readable in `concept` mode only."""
    course = Path(course)
    depth = cov.depth(course)['explain_depth']
    path = course / 'Exams' / '.work' / 'assignment_tasks.json'
    out = {'explain_depth': depth, 'readable': depth == 'concept',
           'file': str(path.relative_to(course)), 'exists': path.is_file()}
    if depth != 'concept':
        out['tasks'] = None
        out['why'] = ('in analogous mode the student has already consented to a '
                      'structurally identical problem, so the index protects '
                      'nothing section 8.1 does not forbid absolutely, and reading '
                      'it would mean holding the task text while working a problem')
        return out
    if not path.is_file():
        out['tasks'] = []
        out['why'] = 'the task index is missing; say the filter is unavailable'
        return out
    try:
        out['tasks'] = (json.loads(path.read_text(encoding='utf-8')) or {}).get('tasks', [])
    except Exception as exc:
        out['tasks'] = []
        out['error'] = str(exc)
    out['use'] = ('a negative filter only: if the explanation as asked would *be* '
                  'the answer to a listed task, stop short and say so')
    return out


def reset(course: Path | str, to: str, apply: bool = False) -> dict:
    res = cov.depth(course, to, apply)
    if res.get('reset_required'):
        res['discard'] = ('discard every loaded section, item, ledger entry and '
                          'task-index row, say so in one line, and re-resolve from '
                          'scratch under the analogous read set')
    else:
        res['discard'] = None
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('section', 'items', 'student', 'tasks', 'reset', 'corrections',
                 'errata'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True)
        if name == 'section':
            p.add_argument('--concept', required=True); p.add_argument('--lesson')
        if name in ('items', 'student', 'corrections', 'errata'):
            p.add_argument('--lesson', required=True)
        if name == 'items':
            p.add_argument('--ids', nargs='+', required=True)
        if name == 'reset':
            p.add_argument('--to', required=True, choices=cov.DEPTHS)
            p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'section':
        out = section(args.course, args.concept, args.lesson)
    elif args.cmd == 'items':
        out = items(args.course, args.lesson, args.ids)
    elif args.cmd == 'student':
        out = student(args.course, args.lesson)
    elif args.cmd == 'tasks':
        out = tasks(args.course)
    elif args.cmd == 'corrections':
        out = corrections(args.course, args.lesson)
    elif args.cmd == 'errata':
        out = errata(args.course, args.lesson)
    else:
        out = reset(args.course, args.to, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
