#!/usr/bin/env python3
"""Parse Weekly_overview.md: the lesson table, the Assignments table, cont. chains.

Used by A (writes rows), B (reads its lesson's row), C (freshness) and E (scope).
`cont.` chains are resolved here and nowhere else: four implementations of one
chain rule would disagree on the first lesson that continues a lesson that itself
continues another.

Cell vocabulary, from folder-structure.md:
  a value   the reading for this lesson
  cont.     same reading as the previous lesson of the same type
  -         no reading at all (a guest lecture); set only on the student's word
  blank     not filled in yet. Never neutral: B would pass its chapter check
            vacuously and write notes with a whole priority-1 source missing.

CLI:
    overview.py rows --course <path>
    overview.py row --course <path> --type lesson --no 03
    overview.py assignments --course <path>
    overview.py for-lesson --course <path> --lesson L03
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vault import read_frontmatter  # noqa: E402

OVERVIEW_NAME = 'Weekly_overview.md'
LESSON_COLUMNS = ['Type', 'No', 'Date', 'Topic', 'Book', 'Chapters', 'Lesson']
ASSIGNMENT_COLUMNS = ['No', 'File', 'Due', 'Lessons', 'Tasks']

CONT = 'cont.'
NONE_MARK = '-'

SEP_RE = re.compile(r'^\s*\|?[\s:|-]+\|?\s*$')


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    return [c.strip() for c in line.split('|')]


def _is_separator(line: str) -> bool:
    return bool(SEP_RE.match(line)) and '-' in line


def parse_tables(body: str) -> list[dict]:
    """Every markdown table in the body, **each on its own**, with the heading
    above it.

    Returned as a list rather than a map keyed by heading, because a heading can
    hold more than one table and they are not the same table. A course schedule
    written by hand routinely has the machine table and the lecturer's own table
    under one heading; merging them by heading makes the first table's columns
    decide the fate of the second, and the lecturer's rows arrive as unkeyed
    junk in the schedule.
    """
    tables: list[dict] = []
    heading = ''
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#'):
            heading = line.lstrip('#').strip()
            i += 1
            continue
        if line.strip().startswith('|') and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            header = _split_row(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = _split_row(lines[i])
                cells += [''] * (len(header) - len(cells))
                row = {header[j]: cells[j] for j in range(len(header))}
                row['_raw'] = lines[i].rstrip()
                rows.append(row)
                i += 1
            tables.append({'heading': heading, 'columns': header, 'rows': rows})
            continue
        i += 1
    return tables


def lesson_table_end(body: str) -> int | None:
    """Index in `body.splitlines()` **just past** the lesson table's last row.

    That is where a new lesson row is inserted. It lives here because this module
    already owns what counts as the lesson table, and it identifies it the way
    `load()` does: by its columns, never by its position in the file.

    course-setup used to anchor an appended row on the last line in the whole
    file beginning with `|`. A Weekly_overview routinely keeps the lecturer's own
    published schedule below the machine-readable one, so the row landed at the
    bottom of *that* table, where this parser never looked. The row was written,
    the filing log recorded it, and the lesson still had no schedule entry.

    An empty lesson table returns the index after its separator, so the first row
    of a freshly scaffolded table goes in the right place too.

    Returns None when there is no lesson table to extend.
    """
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if not line.strip().startswith('|'):
            continue
        if i + 1 >= len(lines) or not _is_separator(lines[i + 1]):
            continue
        if not {'Type', 'No'} <= set(_split_row(line)):
            continue
        j = i + 2
        while j < len(lines) and lines[j].strip().startswith('|'):
            j += 1
        return j
    return None


def _overview_path(course: Path | str) -> Path:
    return Path(course) / OVERVIEW_NAME


def load(course: Path | str) -> dict:
    path = _overview_path(course)
    if not path.is_file():
        return {'exists': False, 'frontmatter': {}, 'rows': [], 'assignments': []}
    fm, body = read_frontmatter(path)
    rows, assignments = [], []
    for table in parse_tables(body):
        if not table['rows']:
            continue
        cols = set(table['columns'])
        if {'Type', 'No'} <= cols:
            rows.extend(table['rows'])
        elif {'No', 'File'} <= cols or table['heading'].strip().lower() == 'assignments':
            assignments.extend(table['rows'])
    # A row that yields no key is not a lesson row. Keeping it would put a null
    # into the schedule that every later lookup has to defend against.
    dropped = [r for r in rows if lesson_key(r) is None]
    rows = [r for r in rows if lesson_key(r) is not None]
    for r in rows:
        r['key'] = lesson_key(r)
    return {'exists': True, 'frontmatter': fm, 'rows': rows,
            'assignments': assignments, 'unkeyed_rows': len(dropped),
            'path': str(path)}


def lesson_key(row: dict) -> str | None:
    t = (row.get('Type') or '').strip().lower()
    n = (row.get('No') or '').strip()
    if not n:
        return None
    if t.startswith('lesson'):
        return f'L{int(n):02d}' if n.isdigit() else f'L{n}'
    if t.startswith('tutorial'):
        return f'T{int(n):02d}' if n.isdigit() else f'T{n}'
    return None


def find_row(data: dict, key: str) -> dict | None:
    for r in data['rows']:
        if r.get('key') == key:
            return r
    return None


def resolve_reading(data: dict, key: str) -> dict:
    """Resolve Book and Chapters, following cont. back through same-type rows.

    Returns status: resolved | none | incomplete | missing_row | broken_chain.
    A broken chain is a cont. row with no earlier row of its own type; that is a
    real defect in the table, not a reading of "nothing".
    """
    row = find_row(data, key)
    if row is None:
        return {'status': 'missing_row', 'key': key, 'book': None, 'chapters': None,
                'resolved_from': None, 'chain': []}

    same_type = [r for r in data['rows'] if (r.get('key') or ' ')[0] == key[0]]

    def _num(r):
        n = (r.get('No') or '').strip()
        return int(n) if n.isdigit() else -1

    same_type.sort(key=_num)
    chain = []
    current = row
    seen = set()
    while True:
        book = (current.get('Book') or '').strip()
        chapters = (current.get('Chapters') or '').strip()
        chain.append(current.get('key'))
        if current.get('key') in seen:
            return {'status': 'broken_chain', 'key': key, 'book': None,
                    'chapters': None, 'resolved_from': None, 'chain': chain,
                    'reason': 'cont. loop'}
        seen.add(current.get('key'))
        if book == NONE_MARK or chapters == NONE_MARK:
            return {'status': 'none', 'key': key, 'book': None, 'chapters': None,
                    'resolved_from': current.get('key'), 'chain': chain}
        if not book or not chapters:
            return {'status': 'incomplete', 'key': key, 'book': book or None,
                    'chapters': chapters or None,
                    'resolved_from': current.get('key'), 'chain': chain}
        if book != CONT and chapters != CONT:
            return {'status': 'resolved', 'key': key, 'book': book,
                    'chapters': chapters, 'resolved_from': current.get('key'),
                    'chain': chain}
        # A tutorial continues the lesson it covers, not the previous tutorial.
        # The Lesson column says which one, and following it is what a reader
        # means by "same reading as the lecture". Only when that column is empty
        # does a tutorial fall back to the previous tutorial.
        nxt = None
        if current.get('key', ' ')[0] == 'T':
            linked = (current.get('Lesson') or '').strip()
            if linked:
                lesson_key = f'L{int(linked):02d}' if linked.isdigit() else f'L{linked}'
                nxt = find_row(data, lesson_key)
                if nxt is None:
                    return {'status': 'broken_chain', 'key': key, 'book': None,
                            'chapters': None, 'resolved_from': None, 'chain': chain,
                            'reason': f'cont. points at {lesson_key} via the Lesson '
                                      'column, and that row does not exist'}
        if nxt is None:
            idx = [i for i, r in enumerate(same_type)
                   if r.get('key') == current.get('key')]
            if not idx or idx[0] == 0:
                return {'status': 'broken_chain', 'key': key, 'book': None,
                        'chapters': None, 'resolved_from': None, 'chain': chain,
                        'reason': 'cont. on the first row of its type, and no Lesson '
                                  'column to follow'}
            nxt = same_type[idx[0] - 1]
        current = nxt


def assignments_for(data: dict, key: str) -> list[dict]:
    """Assignment rows that list this lesson, with only this lesson's tasks kept.

    Only No, File and this lesson's own tasks are comparable, so renumbering
    another lesson never makes this one stale.
    """
    out = []
    token = re.compile(rf'\b{re.escape(key)}\b')
    for row in data.get('assignments', []):
        lessons = row.get('Lessons') or ''
        if not token.search(lessons):
            continue
        mine = []
        for part in (row.get('Tasks') or '').split('·'):
            part = part.strip()
            if not part:
                continue
            if token.search(part):
                mine.append(part)
        out.append({'No': row.get('No', '').strip(),
                    'File': row.get('File', '').strip(),
                    'Due': row.get('Due', '').strip(),
                    'tasks_for_lesson': mine,
                    '_raw': row.get('_raw')})
    return out


def normalised_row(row: dict, columns: list[str] | None = None) -> str:
    """Comparable form of a row: parsed cells, spaces trimmed.

    Never compare raw text. Obsidian re-pads a table on save, and a re-padded
    table is not a change.
    """
    columns = columns or LESSON_COLUMNS
    return '|'.join((row.get(c) or '').strip() for c in columns)


def inputs_for(course: Path | str, key: str) -> dict:
    """The non-file inputs B records in frontmatter for one lesson."""
    data = load(course)
    row = find_row(data, key)
    reading = resolve_reading(data, key)
    out = {
        'overview_row': row.get('_raw') if row else None,
        'overview_row_normalised': normalised_row(row) if row else None,
        'assignment_rows': [a['_raw'] for a in assignments_for(data, key)],
        'resolved_book': reading.get('book'),
        'resolved_chapters': reading.get('chapters'),
        'reading_status': reading.get('status'),
    }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('rows', 'assignments'):
        p = sub.add_parser(name); p.add_argument('--course', required=True)
    p = sub.add_parser('row')
    p.add_argument('--course', required=True)
    p.add_argument('--key', required=True)
    p = sub.add_parser('reading')
    p.add_argument('--course', required=True); p.add_argument('--key', required=True)
    p = sub.add_parser('for-lesson')
    p.add_argument('--course', required=True); p.add_argument('--key', required=True)

    args = ap.parse_args(argv)
    data = load(args.course)
    if args.cmd == 'rows':
        out = {'exists': data['exists'], 'frontmatter': data['frontmatter'],
               'rows': data['rows']}
    elif args.cmd == 'assignments':
        out = {'assignments': data['assignments']}
    elif args.cmd == 'row':
        out = {'row': find_row(data, args.key)}
    elif args.cmd == 'reading':
        out = resolve_reading(data, args.key)
    else:
        out = inputs_for(args.course, args.key)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
