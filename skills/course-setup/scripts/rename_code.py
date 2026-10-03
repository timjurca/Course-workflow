#!/usr/bin/env python3
"""Rename a course code and repair every reference to it.

This is the most destructive thing this skill can do, so the plan is printed in
full and a dry-run count is shown before anything is written.

It is also the **one sanctioned exception** to the ownership rules: it renames
files owned by the notes, revision, corrections and explain skills, and rewrites
link targets inside them. A mechanical rewrite is defined narrowly — replacing an
exact code token in a file name, a wikilink target or a TOC marker pair, with a
count reported. No prose is read, interpreted or altered.

**No .data/ file is rewritten**, and that is by contract rather than by luck: the
term ledger keys on L03/T02, the concept registry stores no code, the revision
skill keeps no code and no lesson number in its keys, and its exam profile stores
past-exam file names without the code prefix.

CLI:
    rename_code.py plan  --vault <v> --course <c> --from ECON --to ECN
    rename_code.py apply --vault <v> --course <c> --from ECON --to ECN
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import check_links                                                   # noqa: E402
import naming                                                        # noqa: E402
from vault import (read_config, write_config, read_frontmatter,      # noqa: E402
                   write_frontmatter)

# Every location that can hold a <CODE>_ prefixed file, including the private
# history folders of other skills. Renaming an archive file is a file-name
# operation, never a content one.
SEARCH_GLOBS = [
    'Lessons/*/Final_notes/{old}_*', 'Tutorials/*/Final_notes/{old}_*',
    'Lessons/*/Final_notes/attachments/{old}_*',
    'Tutorials/*/Final_notes/attachments/{old}_*',
    'Lessons/*/{old}_*_Overview.md', 'Tutorials/*/{old}_*_Overview.md',
    'Lessons/*/.work/history/{old}_*', 'Tutorials/*/.work/history/{old}_*',
    'Articles/{old}_*', 'Videos/{old}_*', 'Links/{old}_*',
    'Explanations/{old}_*', 'Explanations/.history/{old}_*',
    '.data/history/{old}_*',
    'Exams/Revision_questions/{old}_*', 'Exams/Mock_exams/{old}_*',
    'Exams/Past_exams/{old}_*', 'Exams/.work/history/{old}_*',
    'Assignments/{old}_*',
]


def enumerate_files(course: Path, old: str) -> list[dict]:
    rows = []
    for pattern in SEARCH_GLOBS:
        for p in sorted(course.glob(pattern.format(old=old))):
            if not p.is_file():
                continue
            new_name = p.name.replace(f'{old}_', f'{{new}}_', 1)
            rows.append({'from': str(p.relative_to(course)),
                         'name': p.name, 'new_name_template': new_name})
    return rows


def plan(vault: Path | str, course: Path | str, old: str, new: str) -> dict:
    vault, course = Path(vault), Path(course)
    chk = naming.check_code(new)
    problems = []
    if not chk['ok']:
        problems.append(f'the new code is not conforming: {chk["reason"]}')
    cfg = read_config(vault)
    registry = cfg.get('course_codes') or {}
    if new in registry:
        problems.append(f'{new} is already used by {registry[new]}. A reused code '
                        'produces colliding file names across semesters and Obsidian '
                        'resolves them silently.')

    files = enumerate_files(course, old)
    links = check_links.rewrite(vault, {f'{old}_': f'{new}_'}, apply=False)
    folder_rename = None
    if course.name.startswith(f'{old}_'):
        folder_rename = {'from': course.name,
                         'to': course.name.replace(f'{old}_', f'{new}_', 1)}
    return {'from': old, 'to': new, 'problems': problems,
            'files': len(files), 'file_list': files[:40],
            'file_list_truncated': max(0, len(files) - 40),
            'link_files': links['files_changed'], 'link_replacements': links['replacements'],
            'course_folder_rename': folder_rename,
            'data_files_rewritten': 0,
            'note': 'no .data/ file is rewritten: none of them stores a course code.'}


def apply(vault: Path | str, course: Path | str, old: str, new: str) -> dict:
    vault, course = Path(vault), Path(course)
    pre = plan(vault, course, old, new)
    if pre['problems']:
        return {'applied': False, 'problems': pre['problems']}

    renamed = []
    for row in enumerate_files(course, old):
        src = course / row['from']
        dst = src.with_name(src.name.replace(f'{old}_', f'{new}_', 1))
        if dst.exists():
            return {'applied': False,
                    'problems': [f'{dst.relative_to(course)} already exists; '
                                 'nothing is overwritten']}
        os.replace(src, dst)
        renamed.append({'from': row['from'], 'to': str(dst.relative_to(course))})

    links = check_links.rewrite(vault, {f'{old}_': f'{new}_'}, apply=True)

    overview = course / 'Weekly_overview.md'
    if overview.is_file():
        fm, body = read_frontmatter(overview)
        fm['code'] = new
        body = body.replace(f'{old}_', f'{new}_')      # the Assignments File cells
        write_frontmatter(overview, fm, body)

    new_course = course
    if course.name.startswith(f'{old}_'):
        new_course = course.with_name(course.name.replace(f'{old}_', f'{new}_', 1))
        os.replace(course, new_course)

    cfg = read_config(vault)
    rel_old = str(course.resolve().relative_to(Path(vault).resolve()))
    rel_new = str(new_course.resolve().relative_to(Path(vault).resolve())) \
        if new_course != course else rel_old
    for key in ('active_courses', 'archived_courses'):
        cfg[key] = [rel_new if x == rel_old else x for x in (cfg.get(key) or [])]
    registry = cfg.get('course_codes') or {}
    registry.pop(old, None)
    registry[new] = rel_new
    cfg['course_codes'] = registry
    write_config(vault, cfg)

    ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    log = new_course / '_Inbox' / '_filing_log.md'
    if log.is_file():
        with open(log, 'a', encoding='utf-8') as fh:
            fh.write(f'\n## code-rename {ts} · id {old.lower()}-{new.lower()}\n'
                     f'type: code-rename\nfrom: {old}\nto: {new}\n'
                     f'renamed_files: {len(renamed)}\n'
                     f'rewritten_links: {links["replacements"]}\nstatus: complete\n')

    after = check_links.check(vault)
    return {'applied': True, 'renamed_files': len(renamed), 'renamed': renamed[:40],
            'rewritten_links': links['replacements'],
            'course_folder': str(new_course.relative_to(vault)),
            'unresolved_after': {
                'file_links': len(after['broken_file_links']),
                'heading_anchors': len(after['broken_heading_anchors'])},
            'next': 'the notes bodies still show the old code in their prose; '
                    're-run notes only if that matters to you. No skill needs a '
                    're-run: file-name comparisons ignore the course-code token.'}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('plan', 'apply'):
        p = sub.add_parser(name)
        p.add_argument('--vault', required=True); p.add_argument('--course', required=True)
        p.add_argument('--from', dest='old', required=True)
        p.add_argument('--to', dest='new', required=True)
    args = ap.parse_args(argv)
    fn = plan if args.cmd == 'plan' else apply
    out = fn(args.vault, args.course, args.old, args.new)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
