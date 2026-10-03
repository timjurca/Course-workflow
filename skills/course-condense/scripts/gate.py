#!/usr/bin/env python3
"""Four checks before a condensed set of notes is written.

F is a **projection** of the final notes and of nothing else, so its gate is much
smaller than B's or D's: there are no sources to re-stat and no extractions to
match. What it must establish is only that the thing being projected exists, is
readable, is anchored, and that the student knows how fresh it is.

  1  the notes exist and are readable
  2  no iCloud placeholder or conflicted copy
  3  the notes carry concept comments
  4  freshness, reported and never blocking

Check 4 is deliberately a **warning**. A condensed version of stale notes is
exactly as stale as the notes, which is honest and still useful; refusing would
strand the student with nothing on the eve of an exam. B's own gate is where
staleness gets blocked.
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

import icloud                                                      # noqa: E402
import sections as S                                               # noqa: E402
from source_hash import compare_stat, absolve_annotation_changes   # noqa: E402
from vault import read_frontmatter                                 # noqa: E402

LESSON_RE = re.compile(r'^(?P<kind>[LT])(?P<num>\d{1,3})$', re.IGNORECASE)


def lesson_dir(course: Path, key: str) -> Path | None:
    m = LESSON_RE.match((key or '').strip())
    if not m:
        return None
    parent = course / ('Tutorials' if m.group('kind').upper() == 'T' else 'Lessons')
    num = f"{int(m.group('num')):02d}"
    if not parent.is_dir():
        return None
    return next((p for p in sorted(parent.iterdir())
                 if p.is_dir() and p.name.split('_')[0] == num), None)


def notes_path(folder: Path) -> Path | None:
    fn = folder / 'Final_notes'
    if not fn.is_dir():
        return None
    return next((p for p in sorted(fn.glob('*_Final_notes.md'))), None)


def condensed_path(folder: Path, notes: Path) -> Path:
    return notes.parent / notes.name.replace('_Final_notes.md', '_Revision_notes.md')


def notes_hash(path: Path) -> str:
    """Over the body only, so a frontmatter-only touch is not a content change."""
    import hashlib
    text = path.read_text(encoding='utf-8')
    body = text.split('---', 2)[2] if text.startswith('---') else text
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def run(course: Path | str, key: str, vault: Path | str | None = None) -> dict:
    course = Path(course)
    checks: list[dict] = []

    def add(n, name, ok, detail, remedy):
        checks.append({'n': n, 'check': name,
                       'status': 'pass' if ok else 'fail',
                       'detail': detail, 'remedy': remedy})
        return ok

    folder = lesson_dir(course, key)
    if folder is None:
        return {'ok': False, 'stopped_at': 1,
                'checks': [{'n': 1, 'check': 'the lesson exists', 'status': 'fail',
                            'detail': f'no lesson folder for {key}',
                            'remedy': 'check the lesson number, or file its material '
                                      'with course-setup'}]}
    notes = notes_path(folder)
    rel = lambda p: str(p.relative_to(course))                     # noqa: E731

    # 1 ---------------------------------------------------------------------
    if not add(1, 'the final notes exist', notes is not None,
               {'folder': rel(folder)},
               f'run course-notes for {key} first: there is nothing to condense'):
        return {'ok': False, 'stopped_at': 1, 'checks': checks}

    # 2 ---------------------------------------------------------------------
    ic = icloud.is_placeholder(notes)
    conflicted = icloud.looks_conflicted(notes.name, notes.parent)
    if not add(2, 'no placeholder or conflicted copy',
               not ic.get('placeholder') and not conflicted,
               {'placeholder': bool(ic.get('placeholder')), 'conflicted': conflicted,
                'file': rel(notes)},
               'download the file, or move the conflicted copy aside with '
               'course-setup; nothing here is ever merged'):
        return {'ok': False, 'stopped_at': 2, 'checks': checks}

    text = notes.read_text(encoding='utf-8')
    fm, _ = read_frontmatter(notes)
    blocks = S.concept_blocks(text)

    # 3 ---------------------------------------------------------------------
    if not add(3, 'the notes carry concept comments', bool(blocks),
               {'concepts': len(blocks)},
               f'run course-notes for {key}: without concept ids nothing can be '
               'keyed, and a reworded heading would silently lose its block'):
        return {'ok': False, 'stopped_at': 3, 'checks': checks}

    # 4 freshness, warn only ------------------------------------------------
    stat = compare_stat(course, fm.get('sources_stat') or [], folder)
    stat = absolve_annotation_changes(stat, fm.get('sources') or [], course, folder,
                                      fm.get('highlights'))
    fresh = not stat['changed'] and not stat['gone']
    add(4, 'the notes are current (warning only)', fresh,
        {'sources_changed': stat['changed'], 'sources_gone': stat['gone'],
         'annotations_elsewhere': stat.get('annotations_elsewhere') or []},
        f'the condensed notes will be exactly as stale as the notes. Run '
        f'course-notes for {key} first if that matters')

    out_path = condensed_path(folder, notes)
    existing = None
    if out_path.is_file():
        efm, _ = read_frontmatter(out_path)
        recorded = str(efm.get('notes_hash') or '')
        current = notes_hash(notes)
        existing = {'file': rel(out_path),
                    'state': 'current' if recorded == current else 'stale',
                    'recorded_notes_hash': recorded[:16],
                    'current_notes_hash': current[:16],
                    'generated': efm.get('generated')}

    return {'ok': True, 'stopped_at': None, 'checks': checks,
            'lesson': key, 'folder': rel(folder), 'notes': rel(notes),
            'out': rel(out_path), 'existing': existing,
            'notes_hash': notes_hash(notes),
            'concepts': len(blocks),
            'notes_words': len(text.split()),
            'stale_sources': not fresh}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('run')
    p.add_argument('--course', required=True)
    p.add_argument('--lesson', required=True)
    p.add_argument('--vault')
    args = ap.parse_args(argv)
    json.dump(run(args.course, args.lesson, args.vault), sys.stdout,
              ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
