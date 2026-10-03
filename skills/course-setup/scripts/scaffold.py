#!/usr/bin/env python3
"""Create a course's folders and scaffolding files. Idempotent by construction.

Called at init, at adoption, and by validate's safe auto-fixes. Running it twice
is a no-op: it creates what is missing and never overwrites what exists, because
validate runs on every invocation and a scaffolder that overwrote would quietly
undo the student's edits to _Structure.md once a week.

Folders are created **on demand**, so this does not create Lessons/ or
Tutorials/; the first filing does. Exams/ is created whole or not at all.

CLI:
    scaffold.py plan   --course <path> [--exams] [--with-prose ...]
    scaffold.py apply  --course <path> --course-name "..." --code ECON
                       [--notes-language auto] [--exams] [--templates <dir>]
    scaffold.py exams  --course <path> --apply
    scaffold.py lesson --course <path> --key L03 --date 2026-03-12 --apply
    scaffold.py register --vault <path> --course <path> --code ECON --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
from vault import read_config, write_config, read_frontmatter, write_frontmatter  # noqa: E402

TEMPLATES = HERE.parent / 'templates'

ALWAYS_FOLDERS = ['_Inbox', '_Inbox/_conflicts', '_Inbox/_undone',
                  'Articles', 'Videos', 'Links', '.data']
EXAMS_FOLDERS = ['Exams', 'Exams/Past_exams', 'Exams/Mock_exams',
                 'Exams/Revision_questions']
PROSE_FILES = {'description': 'Course_description.md',
               'objectives': 'Learning_objectives.md',
               'literature': 'Literature.md'}

FILING_LOG_HEADER = """# Filing log

Written by the course-setup skill. **Never edit or clear this file by hand.**
Undo reads the most recent batch from it, and the notes, revision, corrections
and explain skills migrate their own records from its renumber blocks.
"""


def _template(name: str, templates: Path | None = None) -> str:
    base = Path(templates) if templates else TEMPLATES
    return (base / name).read_text(encoding='utf-8')


def _fill(text: str, **kw) -> str:
    for k, v in kw.items():
        text = text.replace('{{' + k + '}}', str(v))
    return text


def plan(course: Path | str, exams: bool = False, prose: dict | None = None) -> dict:
    course = Path(course)
    folders = [f for f in ALWAYS_FOLDERS if not (course / f).is_dir()]
    if exams:
        folders += [f for f in EXAMS_FOLDERS if not (course / f).is_dir()]
    files = []
    for rel in ['_Structure.md', 'Weekly_overview.md', 'Table_of_contents.md',
                '.data/terms.json', '_Inbox/_filing_log.md']:
        if not (course / rel).is_file():
            files.append(rel)
    for key, name in PROSE_FILES.items():
        if (prose or {}).get(key) and not (course / name).is_file():
            files.append(name)
    return {'course': str(course), 'exists': course.exists(),
            'create_folders': folders, 'create_files': files,
            'nothing_to_do': not folders and not files}


def apply(course: Path | str, course_name: str, code: str,
          notes_language: str = 'auto', exams: bool = False,
          prose: dict | None = None, templates: Path | None = None) -> dict:
    course = Path(course)
    created_folders, created_files, skipped = [], [], []

    wanted = list(ALWAYS_FOLDERS) + (EXAMS_FOLDERS if exams else [])
    course.mkdir(parents=True, exist_ok=True)
    for rel in wanted:
        p = course / rel
        if p.is_dir():
            skipped.append(rel)
            continue
        p.mkdir(parents=True, exist_ok=True)
        created_folders.append(rel)

    def _write(rel: str, text: str):
        p = course / rel
        if p.exists():
            skipped.append(rel)
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        created_files.append(rel)

    _write('Weekly_overview.md',
           _fill(_template('weekly_overview.md', templates), course=course_name,
                 code=code, notes_language=notes_language))
    _write('Table_of_contents.md',
           _fill(_template('table_of_contents.md', templates), course=course_name))
    _write('_Structure.md',
           _fill(_template('structure_readme.md', templates), course=course_name,
                 code=code))
    _write('.data/terms.json', '{}\n')
    _write('_Inbox/_filing_log.md', FILING_LOG_HEADER)

    # No empty stubs: the notes skill reads these three as background context,
    # and an empty Learning_objectives.md reads as "this course has none".
    for key, name in PROSE_FILES.items():
        body = (prose or {}).get(key)
        if body:
            _write(name, body if body.endswith('\n') else body + '\n')

    return {'course': str(course), 'created_folders': created_folders,
            'created_files': created_files, 'already_present': sorted(set(skipped))}


def exams_tree(course: Path | str, apply_it: bool = False) -> dict:
    """Whole tree or nothing. A partial Exams/ makes C's gate ambiguous."""
    course = Path(course)
    missing = [f for f in EXAMS_FOLDERS if not (course / f).is_dir()]
    if apply_it:
        for rel in missing:
            (course / rel).mkdir(parents=True, exist_ok=True)
    return {'created': missing if apply_it else [], 'would_create': missing,
            'complete': not missing}


def lesson_folder(course: Path | str, key: str, date: str,
                  apply_it: bool = False) -> dict:
    """Content/ and Final_notes/ always come with a lesson folder.

    The notes skill hard-fails without Content/, so its creation is
    unconditional, including for a lesson whose only material is a book chapter.
    Articles/ is created only when an article is actually filed into it.
    """
    course = Path(course)
    kind = 'Lessons' if key.upper().startswith('L') else 'Tutorials'
    num = key[1:]
    root = course / kind / f'{num}_{date}'
    wanted = [root, root / 'Content', root / 'Final_notes']
    missing = [str(p.relative_to(course)) for p in wanted if not p.is_dir()]
    if apply_it:
        for p in wanted:
            p.mkdir(parents=True, exist_ok=True)
    return {'folder': str(root.relative_to(course)), 'created': missing if apply_it else [],
            'would_create': missing}


def register(vault: Path | str, course: Path | str, code: str,
             apply_it: bool = False) -> dict:
    """Append the course to active_courses and its code to the registry.

    Paths are vault-relative everywhere, one format; a course already listed in
    archived_courses is never re-added to active_courses by this call.
    """
    vault, course = Path(vault), Path(course)
    rel = str(course.resolve().relative_to(vault.resolve()))
    cfg = read_config(vault)
    changes = {}
    if rel in (cfg.get('archived_courses') or []):
        changes['skipped'] = 'course is archived; reactivate it explicitly'
    elif rel not in (cfg.get('active_courses') or []):
        cfg.setdefault('active_courses', []).append(rel)
        changes['active_courses'] = rel
    registry = cfg.setdefault('course_codes', {}) or {}
    if registry.get(code) != rel:
        if code in registry:
            changes['conflict'] = {'code': code, 'registered_to': registry[code]}
        else:
            registry[code] = rel
            changes['course_codes'] = {code: rel}
    cfg['course_codes'] = registry
    if apply_it and 'conflict' not in changes and changes:
        write_config(vault, cfg)
    return {'course': rel, 'changes': changes, 'written': bool(apply_it and changes
                                                               and 'conflict' not in changes)}


def stamp(path: Path | str, value: str = 'course-setup v1') -> dict:
    """Insert or refresh scaffolded_by. Needed because the notes skill may create
    Table_of_contents.md before this skill ever sees the course."""
    path = Path(path)
    if not path.is_file():
        return {'path': str(path), 'exists': False}
    fm, body = read_frontmatter(path)
    if fm.get('scaffolded_by') == value:
        return {'path': str(path), 'changed': False}
    fm['scaffolded_by'] = value
    write_frontmatter(path, fm, body)
    return {'path': str(path), 'changed': True, 'scaffolded_by': value}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--course', required=True); p.add_argument('--exams', action='store_true')
    p = sub.add_parser('apply')
    p.add_argument('--course', required=True)
    p.add_argument('--course-name', required=True); p.add_argument('--code', required=True)
    p.add_argument('--notes-language', default='auto')
    p.add_argument('--exams', action='store_true')
    p.add_argument('--templates')
    p.add_argument('--prose', help='JSON: {"description":..., "objectives":..., "literature":...}')
    p = sub.add_parser('exams')
    p.add_argument('--course', required=True); p.add_argument('--apply', action='store_true')
    p = sub.add_parser('lesson')
    p.add_argument('--course', required=True); p.add_argument('--key', required=True)
    p.add_argument('--date', required=True); p.add_argument('--apply', action='store_true')
    p = sub.add_parser('register')
    p.add_argument('--vault', required=True); p.add_argument('--course', required=True)
    p.add_argument('--code', required=True); p.add_argument('--apply', action='store_true')
    p = sub.add_parser('stamp'); p.add_argument('--path', required=True)

    args = ap.parse_args(argv)
    if args.cmd == 'plan':
        out = plan(args.course, args.exams)
    elif args.cmd == 'apply':
        prose = json.loads(args.prose) if args.prose else None
        out = apply(args.course, args.course_name, args.code, args.notes_language,
                    args.exams, prose, args.templates)
    elif args.cmd == 'exams':
        out = exams_tree(args.course, args.apply)
    elif args.cmd == 'lesson':
        out = lesson_folder(args.course, args.key, args.date, args.apply)
    elif args.cmd == 'register':
        out = register(args.vault, args.course, args.code, args.apply)
    else:
        out = stamp(args.path)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
