#!/usr/bin/env python3
"""The six checks, in order, before anything is read for meaning or written.

Every one of them exists because passing it wrongly produces a **confident wrong
note** rather than an error message:

  1. the course resolves and its code is the one A registered — otherwise the
     corrections land in a different course's files
  2. nothing in this run's file set is an iCloud placeholder or a conflicted
     copy — a placeholder reads as empty, so the evidence would be "the source
     does not say that" for every source
  3. the notes exist and carry concept comments — without them nothing can be
     anchored and replay has no identity to match on
  4. every extraction belongs to **this** run — evidence from another run is
     evidence about a different version of the material
  5. the notes are current — correcting notes B is about to rewrite wastes the
     correction and hides the fact that the new material may already fix it
  6. `concepts.json` exists — the concept registry is how a correction survives
     a rewrite

Check 5 is a hard fail on purpose (spec section 5). After the re-run, replay
applies everything together and the fixed items come back as `absorbed`. A
`replay` is **not** blocked by the notes `run` differing from the one recorded
in the correction log — that difference is precisely what replay is for — and an
offloaded source yields "freshness unknown" and continues, never "unchanged".

CLI:
    gate.py run --course <path> --lesson L03 [--vault <path>] [--action correct]
                [--also <path> ...]
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
import icloud                                                     # noqa: E402
import naming                                                     # noqa: E402
import overview as ov                                             # noqa: E402
from source_hash import (compare_stat, split_entry,               # noqa: E402
                         absolve_annotation_changes)
from vault import read_config, read_frontmatter, find_vault       # noqa: E402
from anchor import CONCEPT_RE                                     # noqa: E402

LESSON_RE = re.compile(r'^(?P<kind>[LT])(?P<num>\d{2})$')
HEADER_RE = re.compile(r'^(?P<key>run|sources_hash):\s*(?P<value>.+?)\s*$', re.MULTILINE)

# Files every D run reads, whatever the action. Listed rather than globbed so a
# missing one is a named absence and not a silently shorter list.
DATA_FILES = ('concepts.json', 'terms.json', 'corrections.json',
              'source_errata.json', 'revision_findings.json',
              'explain_findings.json', 'shared_corrections.md')


def lesson_dir(course: Path, lesson: str) -> Path | None:
    m = LESSON_RE.match(lesson or '')
    if not m:
        return None
    parent = course / ('Lessons' if m.group('kind') == 'L' else 'Tutorials')
    if not parent.is_dir():
        return None
    for child in sorted(parent.iterdir()):
        parsed = naming.parse_lesson_folder(child.name)
        if parsed and parsed['num'] == m.group('num'):
            return child
    return None


def notes_path(course: Path, lesson: str) -> Path | None:
    folder = lesson_dir(course, lesson)
    if folder is None:
        return None
    final = folder / 'Final_notes'
    if not final.is_dir():
        return None
    hits = [p for p in sorted(final.glob('*.md'))
            if naming.strip_code_token(p.name) == f'{lesson}_Final_notes.md']
    return hits[0] if hits else None


def _extraction_name(entry: str) -> str:
    """B's Pass A naming: A_<slugify(entry without the #range)>.md, uncapped."""
    from source_hash import split_entry
    path, _ = split_entry(entry)
    return 'A_' + naming.slugify(path, cap=False) + '.md'


def run(course: Path | str, lesson: str, vault: Path | str | None = None,
        action: str = 'correct', also: list[str] | None = None) -> dict:
    course = Path(course).resolve()
    checks: list[dict] = []

    def add(n, name, ok, detail=None, remedy=None, warn=False):
        checks.append({'n': n, 'check': name,
                       'status': 'pass' if ok else ('warn' if warn else 'fail'),
                       'detail': detail, 'remedy': remedy})
        return ok

    # 1 --------------------------------------------------------------------
    overview_path = course / 'Weekly_overview.md'
    code = None
    if not overview_path.is_file():
        add(1, 'course resolves and its code is registered', False,
            'no Weekly_overview.md at the course root',
            'ask course-setup to set this course up or adopt the folder')
        return {'ok': False, 'stopped_at': 1, 'checks': checks}
    fm, _ = read_frontmatter(overview_path)
    code = fm.get('code')
    vault_root = Path(vault) if vault else find_vault(course)
    registered = None
    if vault_root:
        registered = (read_config(vault_root).get('course_codes') or {}).get(code)
    if not code:
        add(1, 'course resolves and its code is registered', False,
            'Weekly_overview.md carries no code:', 'ask course-setup to repair it')
        return {'ok': False, 'stopped_at': 1, 'checks': checks}
    if registered is not None and vault_root is not None:
        same = (vault_root / registered).resolve() == course
        if not same:
            add(1, 'course resolves and its code is registered', False,
                f'code {code} is registered to {registered}',
                'ask course-setup: one of the two values was hand-edited')
            return {'ok': False, 'stopped_at': 1, 'checks': checks}
    add(1, 'course resolves and its code is registered', True,
        f'{code} -> {course.name}'
        + ('' if registered else ' (no _config.md registry found; not verified)'))

    folder = lesson_dir(course, lesson)
    notes = notes_path(course, lesson) if folder else None

    # 2 --------------------------------------------------------------------
    watched = [str(overview_path)]
    if notes:
        watched.append(str(notes))
    if folder:
        watched.append(str(folder / 'notes_corrections.md'))
        work = folder / '.work'
        if work.is_dir():
            watched += [str(p) for p in sorted(work.glob('A_*.md'))]
            if (work / 'D_verification.md').is_file():
                watched.append(str(work / 'D_verification.md'))
    watched += [str(course / '.data' / n) for n in DATA_FILES]
    watched += [str(p) for p in (also or [])]
    present = [p for p in watched if Path(p).exists()]
    ic = icloud.check(present)
    # A conflicted copy is a *sibling* of the file we are about to read, never
    # the file itself, so checking only the watched paths would always come back
    # clean while the student's real edits sat in the branch next door.
    siblings = _conflicted_siblings(present)
    conflicts = ic['conflicts'] + siblings
    if not add(2, 'no iCloud placeholder or conflicted copy in this run',
               not ic['placeholders'] and not conflicts,
               {'placeholders': ic['placeholders'], 'conflicts': conflicts},
               'download the files, or move the conflicted copies aside with '
               'course-setup; nothing here is ever merged'):
        return {'ok': False, 'stopped_at': 2, 'checks': checks}

    # 3 --------------------------------------------------------------------
    if notes is None:
        add(3, 'notes exist and carry concept comments', False,
            f'no Final_notes file for {lesson}', f'run course-notes for {lesson}')
        return {'ok': False, 'stopped_at': 3, 'checks': checks}
    text = notes.read_text(encoding='utf-8')
    concepts_in_notes = CONCEPT_RE.findall(text)
    if not add(3, 'notes exist and carry concept comments', bool(concepts_in_notes),
               f'{len(concepts_in_notes)} concept comments',
               f'run course-notes for {lesson}: the notes predate concept ids'):
        return {'ok': False, 'stopped_at': 3, 'checks': checks}
    nfm, _ = read_frontmatter(notes)
    sources = nfm.get('sources') or []
    run_id = str(nfm.get('run') or '')
    shash = str(nfm.get('sources_hash') or '')

    # 4 --------------------------------------------------------------------
    work = folder / '.work'
    missing, mismatched = [], []
    for entry in sources:
        ex = work / _extraction_name(str(entry))
        if not ex.is_file():
            missing.append(str(ex.relative_to(course)))
            continue
        head = dict(HEADER_RE.findall(ex.read_text(encoding='utf-8')[:2000]))
        if head.get('run') != run_id or head.get('sources_hash') != shash:
            mismatched.append({'file': str(ex.relative_to(course)),
                               'extraction': head,
                               'notes': {'run': run_id, 'sources_hash': shash}})
    if not add(4, 'every extraction belongs to this run', not (missing or mismatched),
               {'missing': missing, 'from_another_run': mismatched},
               f're-run course-notes for {lesson}: the evidence would otherwise '
               'belong to a different version of the material'):
        return {'ok': False, 'stopped_at': 4, 'checks': checks}

    # 5 --------------------------------------------------------------------
    stat = compare_stat(course, nfm.get('sources_stat') or [], folder)
    stat = absolve_annotation_changes(stat, sources, course, folder,
                                      nfm.get('highlights'))
    # `on_disk` only ever lists the lesson's own folders, so `listed` has to be
    # narrowed to the same population. A book lives at the course root and the
    # video/links stubs are muted below, so comparing them against a lesson
    # listing reports them absent on every single run.
    def _muted(name: str) -> bool:
        # Dotfiles are not course material. macOS writes `.DS_Store` into every
        # folder the student opens in Finder, and counting it as an unfiled
        # source failed check 5 for all six EBT lessons, which blocks
        # corrections, revision and explain on a lesson nobody has changed.
        return (name.startswith('.') or name in ('videos.md', 'video.md')
                or name.startswith('links_'))

    listed = set()
    for s in sources:
        rel = Path(split_entry(str(s))[0])
        if len(rel.parts) > 1 and rel.parts[0] in ('Content', 'Articles') \
                and not _muted(rel.name):
            listed.add(naming.strip_code_token(rel.name))
    on_disk = set()
    for sub in ('Content', 'Articles'):
        d = folder / sub
        if d.is_dir():
            on_disk |= {naming.strip_code_token(p.name) for p in d.iterdir()
                        if p.is_file() and not _muted(p.name)}
    new_files = sorted(on_disk - listed)
    gone_files = sorted(listed - on_disk)

    inputs = nfm.get('inputs') or {}
    now = ov.inputs_for(course, lesson)
    row_changed = None
    recorded_row = (inputs.get('overview_row') or '').strip()
    if recorded_row and now.get('overview_row'):
        a = ov.normalised_row(ov.find_row(ov.load(course), lesson) or {})
        b = ov.normalised_row(_row_from_raw(recorded_row))
        if a != b:
            row_changed = {'was': b, 'now': a}

    fresh = not stat['changed'] and not stat['gone'] and not new_files \
        and not gone_files and not row_changed
    detail = {'sources_changed': stat['changed'], 'sources_gone': stat['gone'],
              'annotations_elsewhere': stat.get('annotations_elsewhere') or [],
              'freshness_unknown': stat['freshness_unknown'],
              'new_files_in_lesson': new_files, 'listed_but_absent': gone_files,
              'overview_row_changed': row_changed}
    if not add(5, 'the notes are current', fresh, detail,
               f'run course-notes for {lesson} first, then corrections: correcting '
               'notes that are about to be rewritten wastes the correction'):
        return {'ok': False, 'stopped_at': 5, 'checks': checks}
    if stat['freshness_unknown']:
        add(5.1, 'freshness unknown for offloaded sources', True,
            stat['freshness_unknown'],
            'the dates of these sources could not be read; continuing', warn=True)

    # 6 --------------------------------------------------------------------
    concepts = course / '.data' / 'concepts.json'
    if not add(6, 'the concept registry exists', concepts.is_file(),
               str(concepts.relative_to(course)),
               'run course-notes to rebuild the concept registry'):
        return {'ok': False, 'stopped_at': 6, 'checks': checks}

    return {'ok': True, 'stopped_at': None, 'checks': checks,
            'course': str(course), 'code': code, 'lesson': lesson,
            'action': action,
            'lesson_dir': str(folder.relative_to(course)),
            'notes': str(notes.relative_to(course)),
            'run': run_id, 'sources': [str(s) for s in sources],
            'concepts_in_notes': concepts_in_notes}


def _conflicted_siblings(paths: list[str]) -> list[dict]:
    wanted: dict[Path, set[str]] = {}
    for raw in paths:
        p = Path(raw)
        wanted.setdefault(p.parent, set()).add(p.name)
    out = []
    for directory, names in wanted.items():
        if not directory.is_dir():
            continue
        for child in directory.iterdir():
            if not child.is_file() or child.name in names:
                continue
            if not icloud.looks_conflicted(child.name, directory):
                continue
            origin = icloud.original_of(child.name, directory)
            if origin in names:
                out.append({'path': str(child), 'original': origin,
                            'note': 'a conflicted copy of a file this run reads'})
    return out


def _row_from_raw(raw: str) -> dict:
    cells = [c.strip() for c in raw.strip().strip('|').split('|')]
    cols = ov.LESSON_COLUMNS if hasattr(ov, 'LESSON_COLUMNS') else []
    return {c: (cells[i] if i < len(cells) else '') for i, c in enumerate(cols)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('run')
    p.add_argument('--course', required=True); p.add_argument('--lesson', required=True)
    p.add_argument('--vault'); p.add_argument('--action', default='correct')
    p.add_argument('--also', nargs='*', default=[])
    args = ap.parse_args(argv)
    out = run(args.course, args.lesson, args.vault, args.action, args.also)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0 if out['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
