#!/usr/bin/env python3
"""The readiness gate: refuse to build revision material on notes that have moved.

Questions are the one artefact in this plugin a student *memorises*. A stale
question is worse than no question: it is rehearsed, it feels learned, and it is
wrong in the exam. So every check here is a hard fail rather than a warning,
except the three that genuinely cannot be resolved by the student right now.

Nine ordered checks, fail fast. The order is not cosmetic:

  1  identity     the code in the overview maps to this course in A's registry
  2  iCloud       stat only, over every file this run will read, BEFORE reading
  3  notes        exist and carry concept comments
  4  freshness    sources_stat, the Content/Articles listing, and `inputs`
  5  extractions  one per source, header run + sources_hash equal to the notes
  6  concepts     the registry exists
  7  folders      Exams/Revision_questions/ exists
  8  corrections  no open entry in the lesson's correction log
  9  flags        uncovered material or OCR flags -> warn and carry through

Check 2 runs second for a reason that has bitten every other skill: an iCloud
placeholder reads as an empty file, so a gate that hashes before it stats passes
vacuously on a lesson whose slides are not on this machine.

Check 8 is the seam to skill D. C may read the H2 headers and the `status:` and
`last_replayed:` lines of a correction log and nothing else, ever. A correction
that is pending or awaiting replay means the notes are known to be wrong in a
place someone already identified; building questions from that passage teaches
the error. `orphaned` alone is only a warning: nothing can be replayed until the
student re-places the passage, so blocking would leave them with no way forward.

`notes_hash` lives here too, because it is the same question in a different
tense: not "were the notes right when I read them" but "are they still the notes
I built this file from". It normalises the course-code and lesson tokens inside
wikilink targets, so A's mechanical rewrites during a code rename or a renumber
do not make every revision file look stale.

CLI:
    gate.py check      --course <path> --lesson L03 [--vault <path>] [--for revise|mock]
    gate.py notes-hash --notes <path>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import icloud                                                      # noqa: E402
import naming                                                      # noqa: E402
import overview as ov                                              # noqa: E402
from source_hash import (compare_stat, split_entry,                # noqa: E402
                         absolve_annotation_changes)
from vault import read_config, read_frontmatter                    # noqa: E402

CONCEPT_RE = re.compile(r'<!--\s*concept:\s*([a-z0-9][a-z0-9-]*)\s*-->')
WIKILINK_RE = re.compile(r'\[\[([^\]\|#]*)')
LESSON_TOKEN_RE = re.compile(r'\b[LT]\d{2}\b')
CORRECTION_HEAD_RE = re.compile(r'^##\s+(c-\d+)\s*·')
STATUS_RE = re.compile(r'^status:\s*(\S+)')
REPLAYED_RUN_RE = re.compile(r'^last_replayed:.*?\brun\s+(\S+)')
OPEN_BLOCKING = ('pending',)

# Read as a source only when it sits in one of these; everything else in a
# lesson folder is another skill's output and never enters the comparison.
SOURCE_DIRS = ('Content', 'Articles')


def _rel(base: Path, p: Path) -> str:
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(p)


def lesson_folder(course: Path, key: str) -> Path | None:
    """Find Lessons/NN_date or Tutorials/NN_date for L03 / T02."""
    kind = 'Lessons' if key.upper().startswith('L') else 'Tutorials'
    num = key[1:]
    root = course / kind
    if not root.is_dir():
        return None
    for p in sorted(root.iterdir()):
        info = naming.parse_lesson_folder(p.name) if p.is_dir() else None
        if info and info['num'] == num:
            return p
    return None


def notes_path(course: Path, key: str) -> Path | None:
    folder = lesson_folder(course, key)
    if folder is None:
        return None
    fn = folder / 'Final_notes'
    if not fn.is_dir():
        return None
    want = f'{key.upper()}_Final_notes.md'
    for p in sorted(fn.glob('*_Final_notes.md')):
        if naming.strip_code_token(p.name) == want:
            return p
    return None


def strip_protected(body: str, heading: str = 'My additions') -> str:
    """Drop one H2 section, its heading included, up to the next H2 or EOF."""
    out, skipping = [], False
    for line in body.splitlines():
        if line.startswith('## '):
            skipping = line[3:].strip() == heading
            if skipping:
                continue
        if not skipping:
            out.append(line)
    return '\n'.join(out)


def normalise_links(text: str) -> str:
    """Replace the course code and the lesson token inside wikilink targets.

    A code rename and a renumber are both mechanical rewrites A performs on the
    link *targets* of every file it owns. Without this, every revision file in
    the course would report itself stale the morning after a rename, and the
    student would regenerate thirty files for nothing.
    """
    def repl(m):
        target = m.group(1)
        target = naming.CODE_TOKEN_RE.sub('<CODE>_', target)
        target = LESSON_TOKEN_RE.sub('<LN>', target)
        return '[[' + target
    return WIKILINK_RE.sub(repl, text)


def notes_hash(path: Path | str) -> str:
    _, body = read_frontmatter(Path(path))
    text = normalise_links(strip_protected(body))
    # Trailing whitespace churns when Obsidian saves; it is not a change.
    text = '\n'.join(line.rstrip() for line in text.splitlines()).strip()
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]


# ---------------------------------------------------------------- correction log

def read_correction_status(path: Path | str) -> dict:
    """H2 headers and the status / last_replayed lines. Nothing else, ever.

    An unparseable log is deliberately read as "open": a log C cannot understand
    may hold a pending correction, and guessing "probably fine" is the one
    outcome that teaches the student a known error.
    """
    path = Path(path)
    if not path.is_file():
        return {'exists': False, 'entries': [], 'parse_error': None}
    entries, current, err = [], None, None
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError as e:
        return {'exists': True, 'entries': [], 'parse_error': str(e)}
    for line in lines:
        m = CORRECTION_HEAD_RE.match(line)
        if m:
            current = {'id': m.group(1), 'status': None, 'replayed_run': None}
            entries.append(current)
            continue
        if line.startswith('## '):
            # An H2 that is not a correction header means the file is not the
            # format this reader knows. It may hold a pending correction whose
            # status line is somewhere C cannot see.
            err = err or f'unrecognised block header: {line.strip()!r}'
            current = None
            continue
        if current is None:
            continue
        s = STATUS_RE.match(line)
        if s:
            current['status'] = s.group(1)
            continue
        r = REPLAYED_RUN_RE.match(line)
        if r:
            current['replayed_run'] = r.group(1)
    if not entries and any(l.strip().startswith('## ') for l in lines):
        err = 'the file has H2 blocks but none of them parse as a correction id'
    for e in entries:
        if e['status'] is None:
            err = err or f'{e["id"]} has no status line'
    return {'exists': True, 'entries': entries, 'parse_error': err}


def open_corrections(path: Path | str, notes_run: str | None) -> dict:
    """Split the log's entries into blocking, warning and settled.

    "Needs replay" is derived, never stored: applied, but the run recorded in
    `last_replayed` is not the run the notes currently carry. B never touches
    this file, so the mismatch appears by itself the moment B re-runs.
    """
    log = read_correction_status(path)
    if not log['exists']:
        return {'exists': False, 'blocking': [], 'warning': [], 'parse_error': None}
    if log['parse_error']:
        return {'exists': True, 'blocking': [{'id': '?', 'why': 'log unparseable'}],
                'warning': [], 'parse_error': log['parse_error']}
    blocking, warning = [], []
    for e in log['entries']:
        st = e['status']
        if st in OPEN_BLOCKING:
            blocking.append({'id': e['id'], 'why': f'status {st}'})
        elif st == 'orphaned':
            warning.append({'id': e['id'], 'why': 'orphaned: nothing to replay '
                                                  'until the passage is re-placed'})
        elif st == 'applied' and notes_run and e['replayed_run'] != notes_run:
            blocking.append({'id': e['id'],
                             'why': f'needs replay: last replayed against run '
                                    f'{e["replayed_run"] or "(none recorded)"}, '
                                    f'the notes are at run {notes_run}'})
    return {'exists': True, 'blocking': blocking, 'warning': warning,
            'parse_error': None}


# ---------------------------------------------------------------- the gate

def _f(num, name, ok, message, **extra):
    row = {'check': num, 'name': name, 'ok': ok, 'message': message}
    row.update(extra)
    return row


def extraction_name(entry: str) -> str:
    """A_<slugify(entry without the #range)>.md, uncapped (folder-structure 3)."""
    rel, _ = split_entry(entry)
    return 'A_' + naming.slugify(rel, cap=False) + '.md'


def check(course: Path | str, key: str, vault: Path | str | None = None,
          action: str = 'revise') -> dict:
    course = Path(course)
    key = key.upper()
    checks: list[dict] = []
    reads: list[Path] = []

    # 1 identity ------------------------------------------------------------
    ovp = course / 'Weekly_overview.md'
    code = None
    if not ovp.is_file():
        checks.append(_f(1, 'identity', False, 'Weekly_overview.md is missing: this '
                                               'is not a conforming course. Ask '
                                               'course-setup to validate it.'))
        return _finish(course, key, action, checks, [])
    fm, _ = read_frontmatter(ovp)
    code = (fm.get('code') or '').strip()
    if not code:
        checks.append(_f(1, 'identity', False, 'Weekly_overview.md has no code:. '
                                               'Ask course-setup to repair it.'))
        return _finish(course, key, action, checks, [])
    registry_ok, registry_note = True, f'code {code}'
    if vault:
        try:
            cfg = read_config(vault)
        except Exception as e:
            registry_ok, registry_note = False, f'_config.md unreadable: {e}'
        else:
            reg = cfg.get('course_codes') or {}
            try:
                rel = str(course.resolve().relative_to(Path(vault).resolve()))
            except ValueError:
                rel = None
            if code not in reg:
                registry_ok = False
                registry_note = (f'code {code} is not in course_codes in _config.md. '
                                 'Ask course-setup to register it.')
            elif rel is not None and reg[code] != rel:
                registry_ok = False
                registry_note = (f'course_codes maps {code} to {reg[code]}, not to '
                                 'this course. Two courses with one code collide on '
                                 'every generated filename.')
    else:
        registry_note += ' (registry not checked: no --vault given)'
    checks.append(_f(1, 'identity', registry_ok, registry_note, code=code))
    if not registry_ok:
        return _finish(course, key, action, checks, [])

    # 3-prep: locate the notes before check 2, so check 2 knows what to stat.
    npath = notes_path(course, key)
    folder = lesson_folder(course, key)
    nfm, nbody = ({}, '')
    sources: list[str] = []
    if npath is not None:
        try:
            nfm, nbody = read_frontmatter(npath)
        except Exception:
            nfm, nbody = {}, ''
        sources = list(nfm.get('sources') or [])

    # 2 iCloud --------------------------------------------------------------
    for p in [ovp, course / '.data' / 'concepts.json', course / '.data' / 'terms.json',
              course / 'Learning_objectives.md', course / 'Course_description.md',
              course / '_Inbox' / '_filing_log.md',
              course / '.data' / 'revision_status.json',
              course / '.data' / 'revision_findings.json',
              course / '.data' / 'exam_profile.json',
              course / '.data' / 'exam_glossary.json']:
        if p.exists():
            reads.append(p)
    if folder is not None:
        if npath is not None:
            reads.append(npath)
        for p in sorted(folder.glob('*_Overview.md')):
            reads.append(p)
        work = folder / '.work'
        if work.is_dir():
            reads.extend(sorted(work.glob('A_*.md')))
            if (work / 'D_verification.md').is_file():
                reads.append(work / 'D_verification.md')
        if (folder / 'notes_corrections.md').is_file():
            reads.append(folder / 'notes_corrections.md')
    ic = icloud.check([str(p) for p in reads])
    bad = ic['placeholders'] + ic['conflicts']
    checks.append(_f(2, 'icloud', not bad,
                     'every file this run reads is downloaded and unconflicted'
                     if not bad else
                     'these files are iCloud placeholders or conflicted copies. '
                     'Reading a placeholder returns empty content, so the run would '
                     'silently build questions from half a lesson. Download them in '
                     'Finder and re-run.',
                     placeholders=[_rel(course, Path(x['path'])) for x in ic['placeholders']],
                     conflicts=[_rel(course, Path(x['path'])) for x in ic['conflicts']]))
    if bad:
        return _finish(course, key, action, checks, [])

    # 3 notes ---------------------------------------------------------------
    if npath is None:
        checks.append(_f(3, 'notes', False,
                         f'no Final_notes file for {key}. Run course-notes for {key}.'))
        return _finish(course, key, action, checks, [])
    concepts_in_notes = CONCEPT_RE.findall(nbody)
    if not concepts_in_notes:
        checks.append(_f(3, 'notes', False,
                         f'{_rel(course, npath)} carries no <!-- concept: --> comments. '
                         f'Re-run course-notes for {key}: without them every question '
                         'would be keyed on a heading, and a reworded heading would '
                         'lose its history.'))
        return _finish(course, key, action, checks, [])
    checks.append(_f(3, 'notes', True,
                     f'{_rel(course, npath)}, {len(set(concepts_in_notes))} concepts',
                     notes=_rel(course, npath), concepts=sorted(set(concepts_in_notes))))

    # 4 freshness -----------------------------------------------------------
    unknown: list[str] = []
    recorded = list(nfm.get('sources_stat') or [])
    stat = compare_stat(course, recorded, folder)
    stat = absolve_annotation_changes(stat, sources, course, folder,
                                      nfm.get('highlights'))
    unknown += stat['freshness_unknown']
    listing_extra, listing_missing = listing_drift(folder, sources)
    drift = inputs_drift(course, key, nfm.get('inputs') or {})
    fresh_ok = (not stat['changed'] and not stat['gone']
                and not listing_extra and not listing_missing and not drift)
    checks.append(_f(4, 'freshness', fresh_ok,
                     'sources, folder listing and recorded inputs all match the notes'
                     if fresh_ok else
                     f'the lesson moved under the notes. Re-run course-notes for {key}.',
                     changed=stat['changed'], gone=stat['gone'],
                     newly_filed=listing_extra, no_longer_present=listing_missing,
                     inputs_drift=drift, freshness_unknown=unknown))
    if not fresh_ok:
        return _finish(course, key, action, checks, [])

    # 5 extractions ---------------------------------------------------------
    want_run = str(nfm.get('run') or '')
    want_hash = str(nfm.get('sources_hash') or '')
    missing, mismatched = [], []
    work = folder / '.work'
    for entry in sources:
        p = work / extraction_name(entry)
        if not p.is_file():
            missing.append(entry)
            continue
        head = _extraction_header(p)
        if head.get('run') != want_run or head.get('sources_hash') != want_hash:
            mismatched.append({'entry': entry, 'file': p.name,
                               'run': head.get('run'), 'sources_hash': head.get('sources_hash')})
    ext_ok = not missing and not mismatched
    checks.append(_f(5, 'extractions', ext_ok,
                     f'{len(sources)} extractions match run {want_run}' if ext_ok else
                     'the extractions are missing or come from a different course-notes '
                     f'run. Re-run course-notes for {key}: C never opens a raw source, '
                     'so a mismatched extraction set is not something it can work around.',
                     missing=missing, mismatched=mismatched))
    if not ext_ok:
        return _finish(course, key, action, checks, [])

    # 6 concepts registry ---------------------------------------------------
    cj = course / '.data' / 'concepts.json'
    ok6 = cj.is_file()
    checks.append(_f(6, 'concepts', ok6,
                     '.data/concepts.json present' if ok6 else
                     '.data/concepts.json is missing. Run course-notes to rebuild the '
                     'concept registry: concept IDs are what every question, every '
                     'history entry and every correction is keyed on.'))
    if not ok6:
        return _finish(course, key, action, checks, [])

    # 7 folders -------------------------------------------------------------
    rq = course / 'Exams' / 'Revision_questions'
    ok7 = rq.is_dir()
    checks.append(_f(7, 'folders', ok7,
                     'Exams/Revision_questions/ present' if ok7 else
                     'Exams/Revision_questions/ is missing. Ask course-setup to '
                     'prepare revision folders: C creates no visible folder.'))
    if not ok7:
        return _finish(course, key, action, checks, [])

    # 8 corrections ---------------------------------------------------------
    corr = open_corrections(folder / 'notes_corrections.md', want_run)
    ok8 = not corr['blocking']
    checks.append(_f(8, 'corrections', ok8,
                     ('no correction log' if not corr['exists'] else
                      'every correction is applied and current') if ok8 else
                     f'run course-corrections replay for {key} first. Questions built '
                     'on notes whose known corrections are missing teach the error.',
                     blocking=corr['blocking'], warning=corr['warning'],
                     parse_error=corr['parse_error']))

    # 9 flags ---------------------------------------------------------------
    uncovered = '## Uncovered material' in nbody
    flags = list(nfm.get('flags') or [])
    checks.append(_f(9, 'flags', True,
                     'no uncovered material and no source flags' if not (uncovered or flags)
                     else 'carry these into the answers they touch',
                     uncovered_section=uncovered, flags=flags))

    warnings = []
    if unknown:
        warnings.append({'code': 'freshness_unknown', 'paths': unknown,
                         'message': 'these sources are offloaded, so their date could '
                                    'not be confirmed. Never downloaded by C.'})
    if corr['warning']:
        warnings.append({'code': 'orphaned_corrections', 'entries': corr['warning'],
                         'message': 'orphaned corrections exist for this lesson. '
                                    'course-corrections must re-place them.'})
    if uncovered or flags:
        warnings.append({'code': 'notes_flags', 'flags': flags,
                         'uncovered_section': uncovered,
                         'message': 'carry these flags into every answer that uses the '
                                    'flagged material.'})
    return _finish(course, key, action, checks, warnings, npath)


def _finish(course, key, action, checks, warnings, npath=None):
    hard = [c for c in checks if not c['ok']]
    # `mock` never blocks on one lesson: it warns and builds over what is current.
    if action == 'mock':
        soft = [c for c in hard if c['check'] == 8]
        hard = [c for c in hard if c['check'] != 8]
        for c in soft:
            warnings = list(warnings) + [{'code': 'open_corrections', 'lesson': key,
                                          'message': c['message'],
                                          'entries': c.get('blocking', [])}]
    return {'course': str(course), 'lesson': key, 'for': action,
            'ok': not hard, 'failed': [c['name'] for c in hard],
            'checks': checks, 'warnings': warnings,
            'notes': str(npath) if npath else None,
            'notes_hash': notes_hash(npath) if npath else None}


def _extraction_header(path: Path) -> dict:
    """The first lines only: run and sources_hash. Never the items."""
    head = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            if not line.strip():
                if head:
                    break
                continue
            m = re.match(r'^(run|sources_hash):\s*(\S+)', line)
            if m:
                head[m.group(1)] = m.group(2)
            elif line.startswith('###'):
                break
    return head


def listing_drift(folder: Path, sources: list[str]) -> tuple[list, list]:
    """What is on disk in Content/ and Articles/ against what the notes hashed.

    A directory listing catches the case `sources_stat` cannot: a file filed
    today that kept an old modification time. Names are compared with the
    course-code token stripped, so a rename by A is not a new file.
    """
    def untokened(rel: str) -> str:
        parent, _, base = rel.rpartition('/')
        return f'{parent}/{naming.strip_code_token(base)}' if parent else \
            naming.strip_code_token(base)

    listed = set()
    for entry in sources:
        rel, _ = split_entry(entry)
        if rel.split('/')[0] in SOURCE_DIRS:
            listed.add(untokened(rel))
    on_disk = set()
    for sub in SOURCE_DIRS:
        d = folder / sub
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and not p.name.startswith('.'):
                on_disk.add(untokened(f'{sub}/{p.name}'))
    return sorted(on_disk - listed), sorted(listed - on_disk)


def inputs_drift(course: Path, key: str, recorded: dict) -> list:
    """Compare by parsed, trimmed cells; a re-padded table is not a change."""
    drift = []
    current = ov.inputs_for(course, key)
    was = (recorded.get('overview_row_normalised') or '').strip()
    now = (current.get('overview_row_normalised') or '').strip()
    if was != now:
        drift.append({'field': 'overview_row', 'was': was, 'now': now})
    for field in ('resolved_book', 'resolved_chapters'):
        a = (recorded.get(field) or '')
        b = (current.get(field) or '')
        if str(a).strip() != str(b).strip():
            drift.append({'field': field, 'was': a, 'now': b})
    was_rows = sorted(_assignment_key(r, key) for r in (recorded.get('assignment_rows') or []))
    now_rows = sorted(_assignment_key(a['_raw'], key)
                      for a in ov.assignments_for(ov.load(course), key))
    if was_rows != now_rows:
        drift.append({'field': 'assignment_rows', 'was': was_rows, 'now': now_rows})
    return drift


def _assignment_key(raw: str, key: str) -> str:
    """No, File and this lesson's own tasks. Nothing else is comparable.

    Renumbering another lesson rewrites that lesson's tasks in the same row.
    Comparing the whole row would then make this lesson stale for a change that
    does not touch it, and the student would re-run notes for a course's worth
    of lessons after one renumber.
    """
    cells = [c.strip() for c in str(raw).strip().strip('|').split('|')]
    row = dict(zip(ov.ASSIGNMENT_COLUMNS, cells))
    token = re.compile(rf'\b{re.escape(key)}\b')
    mine = [t.strip() for t in (row.get('Tasks') or '').split('\u00b7')
            if t.strip() and token.search(t)]
    return '|'.join([row.get('No', ''), row.get('File', '')] + sorted(mine))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('check')
    p.add_argument('--course', required=True)
    p.add_argument('--lesson', required=True)
    p.add_argument('--vault')
    p.add_argument('--for', dest='action', default='revise',
                   choices=['revise', 'mock'])
    h = sub.add_parser('notes-hash')
    h.add_argument('--notes', required=True)
    args = ap.parse_args(argv)
    if args.cmd == 'check':
        out = check(args.course, args.lesson, args.vault, args.action)
    else:
        out = {'notes': args.notes, 'notes_hash': notes_hash(args.notes)}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0 if out.get('ok', True) else 1


if __name__ == '__main__':
    raise SystemExit(main())
