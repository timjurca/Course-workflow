#!/usr/bin/env python3
"""Assignment briefs, read as a signal and nothing more.

An assignment tells the notes **what is assessed**. It never becomes notes
content. The distinction is not stylistic: no skill in this plugin solves,
outlines or hints at an assignment, and the cheapest way to keep that true is to
never carry the task wording out of the brief in the first place.

So the only thing that leaves here is a **short title**, hard-capped, per task.
Not the task statement, not worked steps, not the data, not the numbers, not a
sentence that answers anything. `TITLE_WORDS` is the enforcement, applied to
every extracted line, and the cap is deliberately tight enough to be useless as
a prompt.

`G` IDs are excluded from the Pass D coverage arithmetic, because an assignment
task is not lesson material that must appear in the notes. A task matching no
section is listed in the report as "assessed but not covered in this lesson's
material" and is never forced into a section to make a number look better.

**Which tasks are in scope** comes from the `## Assignments` table in
`Weekly_overview.md`, by this lesson's *prefixed* key: `L03`, not `03`. The
brief itself is only consulted for titles, so an unreadable brief degrades to
numbered tasks with no titles rather than to nothing.

Submissions (`_Submission`) and graded feedback (`_Feedback`) are never opened.

CLI:
    extract_assignment.py tasks --course <c> --lesson L03
    extract_assignment.py extract --course <c> --lesson L03 --work <.work> \\
        --run <ts> --hash <h> [--apply]
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
import extraction                                                  # noqa: E402
import extract_pdf                                                 # noqa: E402
import overview as ov                                              # noqa: E402

TITLE_WORDS = 12          # the wording cap; see the module docstring
NEVER_OPEN = ('_Submission', '_Feedback')
TASK_RE = re.compile(
    r'^\s*(?:task|question|exercise|part|naloga|vpra[sš]anje)?\s*'
    r'(?P<n>\d{1,2})\s*[\.\):\-]\s+(?P<text>\S.*)$', re.I)


def _short(text: str) -> str:
    """A title, not a statement. Cut at the cap and at the first sentence end."""
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.split(r'(?<=[.;?])\s', text)[0]
    words = text.split()
    out = ' '.join(words[:TITLE_WORDS])
    return out.rstrip(' ,;:.') + ('…' if len(words) > TITLE_WORDS else '')


def _brief_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        return (extract_pdf.text(path).get('text') or '')
    if suffix == '.docx':
        try:
            import docx                                  # noqa: E402
            return '\n'.join(p.text for p in docx.Document(str(path)).paragraphs)
        except Exception:
            return ''
    if suffix in ('.md', '.txt'):
        return path.read_text(encoding='utf-8', errors='replace')
    return ''


def titles_from_brief(path: Path) -> dict:
    """Task number to short title. Only the first occurrence of each number is
    kept: a brief repeats its numbering in a marking rubric at the end."""
    text = _brief_text(path)
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = TASK_RE.match(line)
        if not m:
            continue
        n = str(int(m.group('n')))
        if n in out:
            continue
        title = _short(m.group('text'))
        if len(title) >= 4:
            out[n] = title
    return out


def _task_numbers(cell_parts: list[str]) -> list[str]:
    """`1: L03` -> `1`. The table is authoritative about which tasks are ours."""
    out = []
    for part in cell_parts:
        m = re.match(r'\s*(\d{1,2})\s*:', part)
        if m:
            out.append(str(int(m.group(1))))
    return out


def tasks(course: Path | str, lesson: str) -> dict:
    course = Path(course)
    data = ov.load(course)
    rows = ov.assignments_for(data, lesson)
    out, notes = [], []
    for row in rows:
        no = (row.get('No') or '').strip()
        brief = (row.get('File') or '').strip()
        path = course / 'Assignments' / brief if brief else None
        titles: dict[str, str] = {}
        if path and path.is_file():
            if any(tok in path.name for tok in NEVER_OPEN):
                notes.append(f'{path.name} is a submission or feedback file and '
                             'is never read; the Assignments row names the wrong '
                             'file.')
            else:
                titles = titles_from_brief(path)
        elif brief:
            notes.append(f'{brief} is named in the Assignments table but is not '
                         'in Assignments/. Tasks are still listed, without titles.')
        for n in _task_numbers(row.get('tasks_for_lesson') or []):
            out.append({'id': f'G{int(no) if no.isdigit() else no}.{n}',
                        'assignment': no, 'task': n,
                        'title': titles.get(n, ''),
                        'file': brief,
                        'callout': f'> [!important] Assessed in '
                                   f'[[{Path(brief).stem}|Assignment {no}]], '
                                   f'task {n}' if brief else ''})
    return {'lesson': lesson, 'rows': len(rows), 'tasks': out, 'notes': notes,
            'assessed_in': [{'assignment': t['assignment'], 'task': int(t['task']),
                             'concept': None} for t in out],
            'coverage': 'G IDs are excluded from Pass D arithmetic'}


def extract(course: Path | str, lesson: str, work: Path | str, run_id: str,
            sources_hash: str, apply_it: bool = False) -> dict:
    found = tasks(course, lesson)
    by_file: dict[str, list[dict]] = {}
    for t in found['tasks']:
        by_file.setdefault(t['file'], []).append(
            {'id': t['id'], 'tags': [],
             'text': t['title'] or f"task {t['task']} (no title extractable "
                                   "from the brief)"})
    written = []
    for brief, items in by_file.items():
        entry = f'Assignments/{brief}' if brief else 'Assignments/unknown'
        written.append(extraction.write(work, entry, run_id, sources_hash,
                                        'assignment', items, None,
                                        apply_it=apply_it))
    found['written'] = written
    found['applied'] = apply_it
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('tasks', 'extract'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True)
        p.add_argument('--lesson', required=True)
        if name == 'extract':
            p.add_argument('--work', required=True)
            p.add_argument('--run', dest='run_id', default='')
            p.add_argument('--hash', default='')
            p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'tasks':
        out = tasks(args.course, args.lesson)
    else:
        out = extract(args.course, args.lesson, args.work, args.run_id,
                      args.hash, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
