#!/usr/bin/env python3
"""Propose Topic and Chapters for a lesson, from its filed content vs the book index.

Why this is not a title match: a slide deck headed "Endogeneity in practice"
commonly maps to a book section headed "Motivation: Omitted Variables". So the
comparison is on **subject matter** — defined terms, notation, named results,
worked examples — against the section *descriptions* the book index carries,
which is why those descriptions are built eagerly for the whole book.

This script does the measuring; the skill does the judging. It returns scored
candidates and a proposed contiguous range, and **nothing is ever written
unconfirmed**: the proposal goes into the same filing plan the student already
approves. A wrong range makes the notes skill extract the wrong pages, and the
notes skill cannot detect that.

A blank cell is not a neutral outcome. Declining leaves the cells blank, and
validate reports the row as incomplete on every later run until it is filled.

CLI:
    infer_row.py suggest --course <path> --lesson-dir <rel> --index <index.md>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
import book_index                                              # noqa: E402
import extract_pdf                                             # noqa: E402
import naming                                                  # noqa: E402

STOPWORDS = set('''
a an the and or of to in for on with by is are was were be been this that these those
it its as at from we you they he she not no but if then than so such which who whom
will would can could may might shall should must do does did done have has had here
there when where how why what into over under between about also more most other some
any each both few many own same very just only own s t don now
'''.split())

WORD_RE = re.compile(r"[A-Za-zČŠŽčšžĆĐćđ][A-Za-zČŠŽčšžĆĐćđ'-]{2,}")


def _tokens(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text or '')
            if w.lower() not in STOPWORDS]


def lesson_text(course: Path, lesson_dir: str, max_chars: int = 60000) -> dict:
    """Slides and transcript only: the two sources that say what the lecture was
    about. Articles and handouts describe one corner of it and skew the match."""
    base = Path(course) / lesson_dir / 'Content'
    chunks, used = [], []
    if not base.is_dir():
        return {'text': '', 'sources': [], 'error': f'{lesson_dir}/Content is missing'}
    for p in sorted(base.iterdir()):
        if p.is_dir() or p.name.startswith('.'):
            continue
        prefix = naming.content_prefix(p.name)
        if prefix not in ('slides', 'transcript'):
            continue
        try:
            if p.suffix.lower() in {'.md', '.txt', '.vtt', '.srt'}:
                chunks.append(p.read_text(encoding='utf-8', errors='replace'))
            elif p.suffix.lower() == '.pdf':
                res = extract_pdf.text(p)
                chunks.append('\n'.join(x['text'] for x in res['pages']))
            elif p.suffix.lower() == '.pptx':
                from pptx import Presentation
                pres = Presentation(str(p))
                parts = []
                for slide in pres.slides:
                    for shape in slide.shapes:
                        if shape.has_text_frame:
                            parts.append(shape.text_frame.text)
                    if slide.has_notes_slide:
                        parts.append(slide.notes_slide.notes_text_frame.text)
                chunks.append('\n'.join(parts))
            else:
                continue
            used.append(p.name)
        except Exception as e:
            used.append(f'{p.name} (unreadable: {e})')
    return {'text': '\n'.join(chunks)[:max_chars], 'sources': used, 'error': None}


def score_sections(text: str, index_path: Path) -> list[dict]:
    data = book_index.load_index(index_path)
    if not data['exists']:
        return []
    body = data['body']
    lesson_counts = Counter(_tokens(text))
    if not lesson_counts:
        return []
    total = sum(lesson_counts.values())
    rows = []
    for sec in data['sections']:
        m = re.search(rf'^##\s+{re.escape(sec["id"])}\s*$\n(.*?)(?=^##\s|\Z)',
                      body, re.MULTILINE | re.DOTALL)
        desc = (m.group(1) if m else '') + ' ' + sec['title']
        desc_tokens = set(_tokens(desc))
        if not desc_tokens:
            rows.append({**sec, 'score': 0.0, 'described': False, 'hits': []})
            continue
        hits = [(w, lesson_counts[w]) for w in desc_tokens if w in lesson_counts]
        score = sum(c for _, c in hits) / total
        rows.append({**sec, 'score': round(score, 4), 'described': bool(m),
                     'hits': [w for w, _ in sorted(hits, key=lambda x: -x[1])[:8]]})
    return rows


def contiguous_range(rows: list[dict], floor_ratio: float = 0.35) -> dict:
    """The contiguous run of sections that accounts for the deck.

    Contiguous rather than top-N, because a Chapters cell is read as a range and
    a lecture normally walks a book forward. Sections scoring below a fraction of
    the best one are outside the run.
    """
    scored = [r for r in rows if r['score'] > 0]
    if not scored:
        return {'range': None, 'reason': 'no overlap between the lesson and the index'}
    best = max(r['score'] for r in scored)
    floor = best * floor_ratio

    def key(sid):
        return [int(x) for x in sid.split('.')]

    ordered = sorted(rows, key=lambda r: key(r['id']))
    runs, current = [], []
    for r in ordered:
        if r['score'] >= floor:
            current.append(r)
        elif current:
            runs.append(current); current = []
    if current:
        runs.append(current)
    if not runs:
        return {'range': None, 'reason': 'nothing cleared the score floor'}
    run = max(runs, key=lambda x: sum(r['score'] for r in x))
    lo, hi = run[0]['id'], run[-1]['id']
    undescribed = [r['id'] for r in run if not r['described']]
    coverage = sum(r['score'] for r in run)
    confidence = 'high' if coverage > 0.25 and not undescribed else \
                 'med' if coverage > 0.10 else 'low'
    return {'range': lo if lo == hi else f'{lo}-{hi}',
            'sections': [{'id': r['id'], 'title': r['title'], 'score': r['score']}
                         for r in run],
            'coverage': round(coverage, 3), 'confidence': confidence,
            'undescribed_sections': undescribed,
            'caveat': ('some sections in this range have no description, so the '
                       'match rests on their titles alone') if undescribed else None}


def suggest_topic(text: str, sections: list[dict]) -> dict:
    """Topic from the dominant subject of the deck; the best-matching section
    title is the first proposal, because it is already the book's own wording."""
    if sections:
        top = max(sections, key=lambda s: s['score'])
        if top['score'] > 0:
            return {'topic': top['title'], 'basis': f'best matching section {top["id"]}'}
    words = [w for w, _ in Counter(_tokens(text)).most_common(6)]
    return {'topic': ' '.join(words[:3]).title() if words else None,
            'basis': 'most frequent terms in the deck; weak, confirm it'}


def suggest(course, lesson_dir, index) -> dict:
    lt = lesson_text(Path(course), lesson_dir)
    if lt['error']:
        return {'error': lt['error']}
    if not lt['text'].strip():
        return {'error': 'no slides or transcript in this lesson to infer from',
                'sources': lt['sources']}
    rows = score_sections(lt['text'], Path(index))
    if not rows:
        return {'error': 'the book index has no sections to match against',
                'sources': lt['sources']}
    rng = contiguous_range(rows)
    topic = suggest_topic(lt['text'], rows)
    return {'sources_read': lt['sources'], 'topic': topic, 'chapters': rng,
            'top_sections': sorted(rows, key=lambda r: -r['score'])[:6],
            'note': 'proposed only. Put it in the filing plan and let the student '
                    'confirm or correct it; never write an unconfirmed row.'}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('suggest')
    p.add_argument('--course', required=True)
    p.add_argument('--lesson-dir', required=True)
    p.add_argument('--index', required=True)
    args = ap.parse_args(argv)
    out = suggest(args.course, args.lesson_dir, args.index)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
