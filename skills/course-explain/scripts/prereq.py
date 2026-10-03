#!/usr/bin/env python3
"""What a concept rests on, inferred and labelled as inferred.

`concepts.json` carries no dependency edges, so every edge here is inferred from
three weaker signals B does leave behind:

  * a `**Connects to:**` link out of one of the concept's own sections
  * `source_ids` shared with a concept that appeared in an earlier lesson
  * a term used in this concept's sections whose `first_defined` lesson is
    earlier than this concept's first appearance

The first and third are **strong**: B wrote the link, or the term ledger
records where a definition was fixed. The second is **weak**: two sections can
cite the same slide without one depending on the other.

The labelling is the point. An inferred dependency presented as a fact sends a
student back to revise a concept the course never said was a prerequisite, and
the cost of that is a wasted evening. So every edge comes back with its evidence
and its strength, `prereq` prints them, and the explain path pulls **one** hop
on a yes rather than walking a chain: a chain of inferred edges compounds a
heuristic three times over and arrives somewhere the course never went.

CLI:
    prereq.py chain --course <c> --concept <id>
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
import ladder                                                        # noqa: E402
import overview as ov                                                # noqa: E402
import scope                                                         # noqa: E402
from coverage import load_concepts, load_state, source_ids_of        # noqa: E402
from locate import load_terms, tokens                                # noqa: E402
from vault import read_frontmatter                                   # noqa: E402

CONNECTS_RE = re.compile(r'\*\*Connects to:\*\*\s*(?P<rest>.+)', re.MULTILINE)
WIKILINK_RE = re.compile(r'\[\[(?P<target>[^\]\|#]+)(?:#(?P<anchor>[^\]\|]+))?'
                         r'(?:\|(?P<alias>[^\]]+))?\]\]')


def lesson_dates(course: Path | str) -> dict:
    """L<NN>/T<NN> -> date, from the Weekly_overview table.

    "Earlier" has to mean earlier in the course, not a smaller number. A
    tutorial numbered 02 can sit after lesson 03 in the calendar - that is the
    normal case, since a tutorial follows the lecture it covers - and ordering
    by the number alone would report the tutorial as a prerequisite of the
    lecture it depends on.
    """
    try:
        data = ov.load(course)
    except Exception:
        return {}
    out = {}
    for row in data.get('rows') or []:
        if row.get('key') and (row.get('Date') or '').strip():
            out[row['key']] = row['Date'].strip()
    return out


def _lesson_order(key: str | None, dates: dict | None = None) -> tuple:
    """Sort by date when the overview gives one, by number otherwise."""
    if not key or len(key) < 2 or not key[1:].isdigit():
        return ('9999-99-99', 999)
    date = (dates or {}).get(key) or '9999-99-99'
    return (date, int(key[1:]) * 2 + (1 if key[0].upper() == 'T' else 0))


def _first_lesson(entry: dict, dates: dict | None = None) -> str | None:
    keys = [s.get('lesson') for s in entry.get('sections') or [] if s.get('lesson')]
    return min(keys, key=lambda k: _lesson_order(k, dates)) if keys else None


def chain(course: Path | str, concept: str) -> dict:
    course = Path(course)
    concepts = load_concepts(course)
    terms = load_terms(course)
    state = load_state(course)
    cov_index = state.get('coverage') or {}
    entry = concepts.get(concept)
    out = {'concept': concept, 'edges': [], 'inference': 'heuristic',
           'note': ('these edges are inferred, not declared: concepts.json carries '
                    'no dependency list. Say so when reporting them.')}
    if entry is None:
        out['error'] = 'not in concepts.json'
        return out
    out['title'] = entry.get('title')
    dates = lesson_dates(course)
    mine_first = _first_lesson(entry, dates)
    out['first_lesson'] = mine_first
    mine_ids = source_ids_of(entry)
    edges = {}

    def add(cid, strength, evidence):
        if cid == concept or cid not in concepts:
            return
        row = edges.setdefault(cid, {'concept': cid, 'title': concepts[cid].get('title'),
                                     'lesson': _first_lesson(concepts[cid], dates),
                                     'strength': 'weak', 'evidence': []})
        row['evidence'].append(evidence)
        if strength == 'strong':
            row['strength'] = 'strong'

    # 1. Connects to: links, read out of the concept's own sections only
    sec = scope.section(course, concept)
    heading_to_concept = {}
    for cid, e in concepts.items():
        for s in e.get('sections') or []:
            if s.get('heading'):
                heading_to_concept.setdefault(s['heading'].strip().lower(), cid)
    for s in sec.get('sections') or []:
        for m in CONNECTS_RE.finditer(s['text']):
            for link in WIKILINK_RE.finditer(m.group('rest')):
                anchor = (link.group('anchor') or '').strip()
                alias = (link.group('alias') or '').strip()
                target = heading_to_concept.get(anchor.lower()) \
                    or heading_to_concept.get(alias.lower()) \
                    or (alias if alias in concepts else None)
                if target:
                    add(target, 'strong',
                        f'Connects to link from {s["lesson"]} ({link.group(0)})')

    # 2. shared source IDs with an earlier concept: real, but weak
    for cid, other in concepts.items():
        if cid == concept or other.get('retired'):
            continue
        theirs = source_ids_of(other)
        shared = sorted(mine_ids & theirs)
        if not shared:
            continue
        if _lesson_order(_first_lesson(other, dates), dates) >= \
                _lesson_order(mine_first, dates):
            continue
        add(cid, 'weak',
            f'shares {", ".join(shared)} with the {mine_first} section')

    # 3. terms used here and first defined earlier
    text = ' '.join(s['text'] for s in sec.get('sections') or [])
    body_tokens = set(tokens(text))
    for term, info in terms.items():
        if not body_tokens.issuperset(set(tokens(term))):
            continue
        defined = (info or {}).get('first_defined')
        if _lesson_order(defined, dates) >= _lesson_order(mine_first, dates):
            continue
        for cid, e in concepts.items():
            if e.get('retired'):
                continue
            if any(s.get('lesson') == defined for s in e.get('sections') or []):
                add(cid, 'strong',
                    f'uses "{term}", defined in terms.json at {defined}')

    for row in edges.values():
        row['explained'] = cov_index.get(row['concept'])
        out['edges'].append(row)
    out['edges'].sort(key=lambda r: (_lesson_order(r['lesson'], dates), r['concept']))
    out['strong'] = sum(1 for r in out['edges'] if r['strength'] == 'strong')
    out['weak'] = len(out['edges']) - out['strong']
    out['explained_already'] = [r['concept'] for r in out['edges'] if r['explained']]
    out['not_explained'] = [r['concept'] for r in out['edges'] if not r['explained']]
    out['one_hop_rule'] = ('pull at most one of these into an explanation, named '
                           'aloud, on a yes - or unassisted only when the '
                           'explanation is plainly incoherent without it')
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('chain'); p.add_argument('--course', required=True)
    p.add_argument('--concept', required=True)
    args = ap.parse_args(argv)
    out = chain(args.course, args.concept)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
