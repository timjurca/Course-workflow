#!/usr/bin/env python3
"""Keep assignment tasks out of the question bank, in either direction.

Two separate obligations meet here, and only one of them is obvious.

The obvious one: **no skill in this plugin solves an assignment.** A question
that restates, paraphrases or re-parameterises a task is a solved assignment
with an extra step, because C writes the model answer directly underneath it.
Re-parameterising is the interesting case: the same task with different numbers
is still the same task, so the comparison strips numerals before it runs. A
student who "revised" with that question has submitted the skill's work.

The less obvious one: C must know the tasks **without ever opening an assignment
file.** It reads only the `G` items B extracted, and holds them in a course-wide
index at `Exams/.work/assignment_tasks.json`, built a lesson at a time as each
lesson is revised. That index is a pinned read-only interface: skill E reads it,
that file and no other, so E can decline an assignment question too. A brief
whose lessons have no current notes is therefore not in the index yet, and both
`mock` and `status` say so -- the filter cannot cover what it has not seen, and
the honest answer is to name the gap rather than pass silently.

The thresholds are a first guess and are meant to be calibrated against one real
brief (spec open item 7). Borderline cases are handed to model judgement on
purpose: word overlap cannot tell "compute the first-stage F for these data"
from "compute the first-stage F for the data in task 3".

CLI:
    lookalike.py index  --course <path> --lesson L03 [--apply]
    lookalike.py show   --course <path>
    lookalike.py briefs --course <path>
    lookalike.py check  --course <path> --questions <json>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import gate                                                        # noqa: E402
import overview as ov                                              # noqa: E402
from vault import read_frontmatter                                 # noqa: E402

INDEX_REL = Path('Exams') / '.work' / 'assignment_tasks.json'
G_ITEM_RE = re.compile(r'^###\s+(G\d+(?:\.\d+)?)\s*$')

DISCARD_AT = 0.50        # speculative, spec open item 7
BORDERLINE_AT = 0.30
STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'is',
    'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'use', 'using', 'with',
    'which', 'when', 'what', 'why', 'how', 'your', 'you', 'we', 'its', 'not',
    'given', 'each', 'these', 'those', 'has', 'have', 'was', 'were', 'will',
}


def index_path(course: Path | str) -> Path:
    return Path(course) / INDEX_REL


def tokens(text: str) -> set:
    """Content words, numerals removed.

    Dropping numerals is the whole point of the filter: re-parameterising a task
    changes the numbers and nothing else, and a comparison that keeps them
    scores the copy as a different question.
    """
    text = re.sub(r'[0-9]+(?:[.,][0-9]+)?', ' ', text.lower())
    words = re.findall(r'[a-zÀ-ɏ]+', text)
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def similarity(a: str, b: str) -> dict:
    """Jaccard over content words, plus the share of the *question's* words that
    the task already contains. The second number is what catches a paraphrase
    that adds scaffolding around a copied task."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return {'jaccard': 0.0, 'contained': 0.0, 'shared': []}
    inter = ta & tb
    return {'jaccard': round(len(inter) / len(ta | tb), 3),
            'contained': round(len(inter) / len(ta), 3),
            'shared': sorted(inter)}


# ---------------------------------------------------------------- the index

def load(course: Path | str) -> dict:
    p = index_path(course)
    if not p.is_file():
        return {'generated': None, 'tasks': {}, 'conflicts': []}
    data = json.loads(p.read_text(encoding='utf-8'))
    data.setdefault('tasks', {})
    data.setdefault('conflicts', [])
    return data


def save(course: Path | str, data: dict) -> Path:
    p = index_path(course)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    os.replace(tmp, p)
    return p


def g_items(work: Path) -> list[dict]:
    """The G items of one lesson's extractions. Never an assignment file."""
    out = []
    for p in sorted(work.glob('A_*.md')):
        current, buf = None, []
        for line in p.read_text(encoding='utf-8').splitlines():
            m = G_ITEM_RE.match(line)
            if m:
                if current:
                    out.append({'id': current, 'text': ' '.join(buf).strip(),
                                'extraction': p.name})
                current, buf = m.group(1), []
                continue
            if line.startswith('### '):
                if current:
                    out.append({'id': current, 'text': ' '.join(buf).strip(),
                                'extraction': p.name})
                current, buf = None, []
                continue
            if current and not line.startswith('tags:') and line.strip():
                buf.append(line.strip())
        if current:
            out.append({'id': current, 'text': ' '.join(buf).strip(),
                        'extraction': p.name})
    return out


def build(course: Path | str, lesson: str, apply: bool = False) -> dict:
    course = Path(course)
    lesson = lesson.upper()
    folder = gate.lesson_folder(course, lesson)
    if folder is None:
        raise FileNotFoundError(f'no folder for {lesson}')
    data = load(course)
    added, updated, conflicts = [], [], []
    rows = ov.assignments_for(ov.load(course), lesson)
    assignment = rows[0]['No'] if rows else None
    for item in g_items(folder / '.work'):
        entry = data['tasks'].get(item['id'])
        if entry is None:
            data['tasks'][item['id']] = {
                'text': item['text'], 'lessons': [lesson],
                'assignment': assignment, 'extraction': item['extraction']}
            added.append(item['id'])
            continue
        if lesson not in entry['lessons']:
            entry['lessons'].append(lesson)
            entry['lessons'].sort()
            updated.append(item['id'])
        if entry['text'] != item['text']:
            # Two briefs numbered their tasks the same way. Both texts are kept:
            # dropping one would leave a task the filter cannot see.
            entry.setdefault('variants', [])
            if item['text'] not in entry['variants']:
                entry['variants'].append(item['text'])
            row = {'id': item['id'], 'lesson': lesson,
                   'why': 'the same G id carries different text in two lessons'}
            conflicts.append(row)
            data['conflicts'].append(row)
    data['generated'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M')
    if apply:
        save(course, data)
    return {'lesson': lesson, 'added': added, 'lessons_extended': updated,
            'conflicts': conflicts, 'tasks': len(data['tasks']),
            'written': apply,
            'path': str(INDEX_REL),
            'note': 'read-only interface: course-explain may read this file, and '
                    'no other file of C'}


def briefs(course: Path | str) -> dict:
    """Briefs in the Assignments table whose tasks the index has never seen.

    Named by `mock` and `status` rather than silently ignored: the look-alike
    filter cannot cover a brief it has no tasks for, and a student told
    "no look-alikes found" would reasonably assume it could.
    """
    course = Path(course)
    data = load(course)
    seen = {(t.get('assignment') or '') for t in data['tasks'].values()}
    rows = []
    for row in ov.load(course).get('assignments') or []:
        no = (row.get('No') or '').strip()
        rows.append({'No': no, 'File': (row.get('File') or '').strip(),
                     'Lessons': (row.get('Lessons') or '').strip(),
                     'in_index': no in seen})
    return {'briefs': rows,
            'not_indexed': [r for r in rows if not r['in_index']],
            'tasks_indexed': len(data['tasks'])}


def check(course: Path | str, questions: list[dict]) -> dict:
    data = load(course)
    tasks = data['tasks']
    results = []
    for q in questions:
        text = q.get('text') or ''
        worst = None
        for tid, t in tasks.items():
            for candidate in [t.get('text', '')] + list(t.get('variants') or []):
                s = similarity(text, candidate)
                score = max(s['jaccard'], s['contained'] * 0.9)
                if worst is None or score > worst['score']:
                    worst = {'task': tid, 'assignment': t.get('assignment'),
                             'score': round(score, 3), **s}
        if worst is None:
            results.append({'id': q.get('id'), 'verdict': 'clear',
                            'why': 'the assignment task index is empty'})
            continue
        if worst['score'] >= DISCARD_AT:
            verdict, why = 'discard', 'too close to an assignment task'
        elif worst['score'] >= BORDERLINE_AT:
            verdict, why = ('borderline',
                            'decide by reading both: word overlap cannot tell a '
                            'shared topic from a copied task')
        else:
            verdict, why = 'clear', 'no meaningful overlap with any indexed task'
        results.append({'id': q.get('id'), 'verdict': verdict, 'why': why,
                        'closest': worst})
    return {'checked': len(questions), 'results': results,
            'discard': [r['id'] for r in results if r['verdict'] == 'discard'],
            'borderline': [r['id'] for r in results if r['verdict'] == 'borderline'],
            'thresholds': {'discard_at': DISCARD_AT, 'borderline_at': BORDERLINE_AT,
                           'note': 'speculative; calibrate against one real brief'},
            'tasks_indexed': len(tasks),
            'briefs_not_indexed': [b['No'] for b in briefs(course)['not_indexed']]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('index', 'show', 'briefs', 'check'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True)
        if name == 'index':
            p.add_argument('--lesson', required=True)
            p.add_argument('--apply', action='store_true')
        if name == 'check':
            p.add_argument('--questions', required=True, help='JSON file or literal')
    args = ap.parse_args(argv)
    if args.cmd == 'index':
        out = build(args.course, args.lesson, args.apply)
    elif args.cmd == 'show':
        out = load(args.course)
    elif args.cmd == 'briefs':
        out = briefs(args.course)
    else:
        try:
            q = Path(args.questions)
            raw = q.read_text(encoding='utf-8') if q.is_file() else args.questions
        except OSError:
            raw = args.questions
        out = check(args.course, json.loads(raw))
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
