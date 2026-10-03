#!/usr/bin/env python3
"""Resolve a question to concept IDs, before anything at all is loaded.

Every read E performs is concept-scoped, so the concept ID is the key to the
whole run: it selects the notes sections, the extraction items, the ledger entry
and the filename a save would use. Resolving it by opening files and reading
prose would defeat the scoping it exists to enable, so resolution runs against
the two small registries B maintains, `concepts.json` and `terms.json`, and
nothing else.

Three things make this more than a string match.

**The coverage index is consulted first.** A concept may already have a saved
explanation, and an explanation that already exists is offered rather than
rebuilt. Crucially, coverage is not the same thing as a file: a concept
explained inside another concept's file has no file of its own, and a directory
listing would report it as unexplained.

**The rejected list is consulted too.** E has to know, before it starts
choosing a framing, which framings this student has already rejected for this
concept. Consulting it afterwards is consulting it too late.

**A term is not a concept.** `## Definitions` carries no concept ID, so a
question about a single term is attached to the concept where the term is
`first_defined`, which is C's rule and is followed here so that two skills
answer "where does this term live" identically.

Resolution never picks between two plausible candidates: it ranks them and the
caller asks. A wrong concept ID is a wrong filename on save and a wrong section
loaded for the answer, and neither shows up as an error.

CLI:
    locate.py match   --course <c> --question "<text>" [--limit 5]
    locate.py concept --course <c> --concept <id>
    locate.py terms   --course <c> --question "<text>"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
from coverage import (load_concepts, load_state, source_ids_of,      # noqa: E402
                      successor_of)

# Words that carry no subject content. Kept deliberately short: an aggressive
# stop list throws away the one distinguishing word in a short question.
STOP = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'do', 'does', 'did',
    'i', 'me', 'my', 'you', 'it', 'this', 'that', 'these', 'those', 'of', 'in',
    'on', 'to', 'for', 'with', 'and', 'or', 'but', 'not', 'why', 'how', 'what',
    'when', 'which', 'who', 'can', 'could', 'would', 'should', 'explain',
    'understand', 'mean', 'means', 'about', 'again', 'please', 'tell', 'show',
    'lesson', 'lecture', 'notes', 'from', 'at', 'by', 'as', 'so', 'if',
}


# A concept ID is a hyphenated slug, the shape A's validate matches in
# <CODE>_<concept-id>_Explained.md. It is deliberately not naming.slugify's
# output, which turns hyphens into underscores.
CONCEPT_ID_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def _fold(text: str) -> str:
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def tokens(text: str) -> list:
    return [t for t in re.split(r'[^a-z0-9]+', _fold(text)) if t and t not in STOP]


def load_terms(course: Path | str) -> dict:
    path = Path(course) / '.data' / 'terms.json'
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}
    return data.get('terms', data if 'terms' not in data else {}) or {}


def _score(question_tokens: list, phrase: str) -> float:
    """Overlap, weighted so that matching a whole multi-word phrase wins.

    A question mentioning "instrument relevance" must beat one that merely
    contains "instrument", or every IV question resolves to every IV concept.
    """
    target = tokens(phrase)
    if not target:
        return 0.0
    qset, tset = set(question_tokens), set(target)
    overlap = qset & tset
    if not overlap:
        return 0.0
    score = len(overlap) / len(tset)
    joined = ' '.join(question_tokens)
    if ' '.join(target) in joined:
        score += 1.0                      # the whole phrase, in order
    return round(score, 4)


def match(course: Path | str, question: str, limit: int = 5) -> dict:
    concepts = load_concepts(course)
    terms = load_terms(course)
    state = load_state(course)
    cov = state.get('coverage') or {}
    rejected = state.get('rejected') or {}
    qt = tokens(question)

    out = {'question': question, 'tokens': qt, 'candidates': [],
           'degraded': False, 'can_save': True, 'state_status': state.get('_status')}

    if not concepts:
        # A filename needs a concept ID, so without the registry E may still
        # explain from heading text but must refuse to save.
        out['degraded'] = True
        out['can_save'] = False
        out['reason'] = ('concepts.json is missing or empty: resolution falls back '
                         'to heading text, and save is refused because a filename '
                         'needs a concept ID')

    scored = {}
    for cid, entry in concepts.items():
        s = max(_score(qt, entry.get('title') or ''), _score(qt, cid.replace('-', ' ')))
        if s > 0:
            scored[cid] = {'score': s, 'via': 'concept'}

    # A term attaches to the concept where it is first_defined (C's rule).
    term_hits = []
    for term, info in terms.items():
        s = _score(qt, term)
        if s <= 0:
            continue
        lesson = (info or {}).get('first_defined')
        # Retired concepts are excluded here: a term resolving onto one would
        # send a live question to a concept the notes no longer carry. Asking
        # about a retired concept by name still reaches it, through the title
        # match above, and that path names the successor.
        owners = [cid for cid, e in concepts.items()
                  if not e.get('retired')
                  and any((sec.get('lesson') == lesson) for sec in e.get('sections') or [])]
        term_hits.append({'term': term, 'score': s, 'first_defined': lesson,
                          'translation': (info or {}).get('translation'),
                          'definition': (info or {}).get('definition'),
                          'attaches_to': owners})
        for cid in owners:
            prev = scored.get(cid)
            # A term match is weaker evidence than a concept-title match: it
            # says the concept owns the lesson, not that it owns the question.
            bump = s * 0.5
            if prev is None:
                scored[cid] = {'score': round(bump, 4), 'via': f'term:{term}'}
            elif bump > prev['score']:
                scored[cid] = {'score': round(bump, 4), 'via': f'term:{term}'}

    for cid, hit in sorted(scored.items(), key=lambda kv: -kv[1]['score'])[:limit]:
        entry = concepts.get(cid) or {}
        row = {
            'concept': cid, 'title': entry.get('title'), 'score': hit['score'],
            'via': hit['via'],
            'lessons': [s.get('lesson') for s in entry.get('sections') or []],
            'headings': sorted({s.get('heading') for s in entry.get('sections') or []
                                if s.get('heading')}),
            'source_ids': sorted(source_ids_of(entry)),
            'retired': bool(entry.get('retired')),
            'explained_in': cov.get(cid),
            'has_own_file': cov.get(cid) == cid,
            'rejected_framings': rejected.get(cid, []),
        }
        if row['retired']:
            row['successor'] = successor_of(concepts, cid)['successor']
        out['candidates'].append(row)

    out['terms'] = sorted(term_hits, key=lambda r: -r['score'])[:limit]
    top = out['candidates'][0]['score'] if out['candidates'] else 0
    runner = out['candidates'][1]['score'] if len(out['candidates']) > 1 else 0
    if not out['candidates']:
        out['resolution'] = 'none'
        out['next'] = ('name the near misses and ask; if nothing is close, this is '
                       'rung 4 under the two fences')
    elif runner and top - runner < 0.25:
        out['resolution'] = 'ambiguous'
        out['next'] = 'list the candidates and ask; never load all of them'
    else:
        out['resolution'] = 'resolved'
    return out


def concept(course: Path | str, cid: str) -> dict:
    """Everything E knows about one concept before any file is opened."""
    concepts = load_concepts(course)
    state = load_state(course)
    entry = concepts.get(cid)
    if entry is None:
        return {'concept': cid, 'known': False,
                'note': 'not in concepts.json; E never invents a concept ID'}
    cov = state.get('coverage') or {}
    out = {'concept': cid, 'known': True, 'title': entry.get('title'),
           'retired': bool(entry.get('retired')),
           'sections': entry.get('sections') or [],
           'source_ids': sorted(source_ids_of(entry)),
           'lessons': [s.get('lesson') for s in entry.get('sections') or []],
           'explained_in': cov.get(cid), 'has_own_file': cov.get(cid) == cid,
           'rejected_framings': (state.get('rejected') or {}).get(cid, []),
           'filename': f'<CODE>_{cid}_Explained.md'}
    if out['retired']:
        succ = successor_of(concepts, cid)
        out['successor'] = succ['successor']
        out['note'] = ('retired: explain it and name the successor'
                       if succ['successor'] else
                       'retired with no resolvable successor; say so')
    if not CONCEPT_ID_RE.match(cid):
        out['warning'] = ('this concept ID is not of the form a-b-c; the filename '
                          'is derived from it and A validates the shape with '
                          '<CODE>_[a-z0-9-]+_Explained.md')
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('match'); p.add_argument('--course', required=True)
    p.add_argument('--question', required=True); p.add_argument('--limit', type=int, default=5)
    p = sub.add_parser('concept'); p.add_argument('--course', required=True)
    p.add_argument('--concept', required=True)
    p = sub.add_parser('terms'); p.add_argument('--course', required=True)
    p.add_argument('--question', required=True)
    args = ap.parse_args(argv)
    if args.cmd == 'match':
        out = match(args.course, args.question, args.limit)
    elif args.cmd == 'concept':
        out = concept(args.course, args.concept)
    else:
        out = {'terms': match(args.course, args.question)['terms']}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
