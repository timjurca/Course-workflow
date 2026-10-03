#!/usr/bin/env python3
"""Find a passage again, exactly, and refuse to guess when it has moved.

Everything D writes is written **inside an anchor**: a span of the notes located
by matching the recorded `before` text. The anchor is the only thing standing
between a replay and the silent change this plugin exists to avoid, so this
module has two jobs and they pull in opposite directions.

  * **Match through cosmetic churn.** Obsidian re-pads tables and re-wraps list
    items on save; a paragraph that is byte-different is usually the same
    paragraph. Matching therefore runs on a whitespace-collapsed copy, with a
    character map back to the raw offsets, so the *write* still lands on the
    real bytes.
  * **Never match through a rewrite.** A near miss returns **candidates**, not a
    result. Picking the most similar sentence automatically is how a correction
    gets re-applied into a paragraph that no longer says what it said, and
    nothing on screen would show it. Candidates go into the plan and the student
    decides (spec section 11, D-19).

Two matches are as much a failure as none: section 21 says show every occurrence
and ask which. So `find` always returns the full list and never picks.

It also owns the concept registry reads that the anchor depends on — which H2 a
concept currently lives under, and which concept succeeded a retired one — so
`replay.py` and `links.py` resolve a successor by the **same** rule B uses to
reuse an id (note-invariants section 6): the candidate whose `source_ids`
overlap most, when the overlap is at least half the smaller set.

CLI:
    anchor.py sections  --notes <file>
    anchor.py find      --notes <file> --text <str> [--concept <id>]
    anchor.py candidates --notes <file> --text <str> [--concept <id>] [--ids S22 ...]
    anchor.py protected --notes <file> --start <n> --end <n>
    anchor.py collapse  --notes <file> --items <items.json>
    anchor.py successor --concepts <concepts.json> --concept <id> --lesson L03
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

import markers as _markers                                       # noqa: E402
import sections as _sections                                     # noqa: E402

H2_RE = re.compile(r'^##\s+(?P<title>.+?)\s*$', re.MULTILINE)
CONCEPT_RE = re.compile(r'^<!--\s*concept:\s*(?P<id>[^\s>]+)\s*-->\s*$', re.MULTILINE)
# The canonical parser. The local copy this replaced truncated `B4.2.11` to a
# phantom `B4.2` and never captured the `!` suffix; see shared/scripts/markers.py.
SOURCE_ID_RE = _markers.SOURCE_ID_RE

# Structural headings are fixed English whatever notes_language says
# (note-invariants section 7), so matching them as literals is correct.
PROTECTED_HEADINGS = ('My additions', 'My notes', 'My questions')
FIXED_SECTIONS = ('Definitions', 'Assigned readings', 'Assigned videos',
                  'Assigned links', 'Recap', 'Uncovered material',
                  'My additions', 'My notes', 'My questions', 'Core summary',
                  'External references')

# One-for-one character folds only. A fold that changed the length would break
# the offset map, and the offset map is what makes the write land on real bytes.
FOLD = {'‘': "'", '’': "'", '“': '"', '”': '"',
        '–': '-', '—': '-', '−': '-', ' ': ' ',
        ' ': ' ', ' ': ' ', '′': "'"}


def normalise(text: str) -> tuple[str, list[int]]:
    """Whitespace-collapsed copy plus, for each of its characters, its raw index.

    The map is what separates matching from writing: we compare the collapsed
    form and then cut the original at the recovered offsets.
    """
    out: list[str] = []
    index: list[int] = []
    in_space = False
    for i, ch in enumerate(text):
        ch = FOLD.get(ch, ch)
        if ch.isspace():
            if not in_space:
                out.append(' ')
                index.append(i)
                in_space = True
            continue
        in_space = False
        out.append(ch)
        index.append(i)
    index.append(len(text))
    return ''.join(out), index


def _span(index: list[int], start: int, end: int, text: str) -> tuple[int, int]:
    raw_start = index[start]
    raw_end = index[end] if end < len(index) else len(text)
    # A collapsed run that ended the match stands for trailing whitespace in the
    # raw text; excluding it keeps the replacement from eating the line break.
    while raw_end > raw_start and text[raw_end - 1].isspace():
        raw_end -= 1
    return raw_start, raw_end


def sections(notes: str) -> list[dict]:
    """Every H2 with its concept id and its raw span, frontmatter excluded."""
    out = []
    heads = list(H2_RE.finditer(notes))
    for n, m in enumerate(heads):
        start = m.start()
        end = heads[n + 1].start() if n + 1 < len(heads) else len(notes)
        block = notes[m.end():end]
        cm = CONCEPT_RE.search(block)
        title = m.group('title').strip()
        out.append({'heading': title,
                    'concept': cm.group('id') if cm else None,
                    'fixed': title in FIXED_SECTIONS,
                    'protected': title in PROTECTED_HEADINGS,
                    'start': start, 'end': end,
                    'body_start': m.end(), 'source_ids':
                        sorted(set(SOURCE_ID_RE.findall(block)))})
    return out


def section_for(notes: str, concept: str | None = None,
                heading: str | None = None) -> dict | None:
    """The span to scope a match to.

    A **concept** is resolved through `shared/sections.concept_blocks`, because
    concepts sit on H3 and `sections()` only sees H2: it used to return the
    whole `## Concepts` block for the first concept and None for every other
    one, which orphaned every replay. A **heading** is still resolved through
    `sections()`, because the headings callers pass (`Uncovered material`,
    `Definitions`) are H2 containers by construction.
    """
    if concept:
        return _sections.block_for(notes, concept)
    for s in sections(notes):
        if heading and s['heading'] == heading:
            return s
    return None


def find(notes: str, text: str, concept: str | None = None,
         heading: str | None = None) -> dict:
    """Every occurrence of `text`, as raw spans. Never picks between them."""
    scope_start, scope_end, scope = 0, len(notes), None
    if concept or heading:
        scope = section_for(notes, concept, heading)
        if scope is None:
            return {'found': False, 'reason': 'concept section not in this file',
                    'concept': concept, 'occurrences': []}
        scope_start, scope_end = scope['start'], scope['end']

    hay, index = normalise(notes[scope_start:scope_end])
    needle, _ = normalise(text)
    needle = needle.strip()
    if not needle:
        return {'found': False, 'reason': 'empty anchor text', 'occurrences': []}

    hits = []
    at = hay.find(needle)
    while at >= 0:
        s, e = _span(index, at, at + len(needle), notes[scope_start:scope_end])
        hits.append({'start': scope_start + s, 'end': scope_start + e,
                     'raw': notes[scope_start + s:scope_start + e]})
        at = hay.find(needle, at + 1)

    return {'found': bool(hits), 'occurrences': hits, 'count': len(hits),
            'concept': concept or (scope or {}).get('concept'),
            'heading': (scope or {}).get('heading'),
            'unique': len(hits) == 1,
            'reason': None if hits else 'anchor text not present'}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r'[a-z0-9]+', text.lower()))


def candidates(notes: str, text: str, concept: str | None = None,
               source_ids: list[str] | None = None, limit: int = 5) -> dict:
    """Paragraphs that might be the same passage after a rewrite. Ranked, never chosen.

    The ranking is deliberately crude and the output deliberately a list: this
    feeds a plan row that a human answers. A single confident answer here would
    be the automation this module exists to refuse.
    """
    scope = section_for(notes, concept) if concept else None
    if concept and scope is None:
        return {'concept': concept, 'section_present': False, 'candidates': []}
    start = scope['body_start'] if scope else 0
    end = scope['end'] if scope else len(notes)
    wanted_ids = set(source_ids or SOURCE_ID_RE.findall(text))
    want = _tokens(text)

    out = []
    for m in re.finditer(r'[^\n]+(?:\n[^\n]+)*', notes[start:end]):
        para = m.group(0)
        if para.lstrip().startswith(('## ', '<!--')):
            continue
        ids = set(SOURCE_ID_RE.findall(para))
        have = _tokens(para)
        overlap = len(want & have) / max(1, len(want | have))
        shared = wanted_ids & ids
        out.append({'start': start + m.start(), 'end': start + m.end(),
                    'text': para.strip(),
                    'shared_source_ids': sorted(shared),
                    'token_overlap': round(overlap, 3),
                    'score': round(len(shared) * 1.0 + overlap, 3)})
    out.sort(key=lambda r: -r['score'])
    return {'concept': concept, 'section_present': True,
            'candidates': out[:limit]}


def protected_hit(notes: str, start: int, end: int) -> dict:
    """Does a span touch a block that is the student's own writing?

    `## My additions` and `## My notes` are preserved verbatim by every skill
    (note-invariants section 8). D refuses rather than asking, because there is
    no correct way to correct someone's own notes.
    """
    for s in sections(notes):
        if s['protected'] and start < s['end'] and end > s['start']:
            return {'protected': True, 'heading': s['heading']}
    return {'protected': False}


def collapse(notes: str, items: list[dict]) -> dict:
    """Merge findings that point at one passage; keep findings on adjacent ones apart.

    The key is (`concept`, `source`, anchor) from note-invariants section 16, and
    "anchor" is resolved here to a **located span**, not to the quoted string.
    That is the whole subtlety: C's `contradiction` and E's `differs` quote the
    same sentence in different words, so string equality would miss the merge;
    two findings about neighbouring sentences quote different text in the same
    section, so section equality would merge them wrongly. Overlapping spans is
    the rule that gets both right.

    Two spans in **one sentence** count as one passage even when they do not
    overlap, because C quotes the clause it can check and E quotes the claim it
    disagrees with, and those are often two halves of the same sentence. The
    test is what sits between them: no line break and no sentence terminator
    means one passage; a full stop, or the source marker that ends a sentence,
    means the next one.

    An item whose quote cannot be located keeps its own group unless another
    unlocatable item quotes exactly the same text.
    """
    enriched = []
    for n, item in enumerate(items):
        quote = item.get('quote') or item.get('notes_text') or ''
        hit = find(notes, quote, item.get('concept')) if quote else {'found': False}
        occ = hit['occurrences'][0] if hit.get('occurrences') else None
        enriched.append({'index': n, 'item': item,
                         'concept': item.get('concept'), 'source': item.get('source'),
                         'quote': quote,
                         'span': [occ['start'], occ['end']] if occ else None,
                         'located': occ is not None,
                         'ambiguous': hit.get('count', 0) > 1})

    def same_passage(a, b):
        if a[0] < b[1] and b[0] < a[1]:
            return True
        lo, hi = (a, b) if a[1] <= b[0] else (b, a)
        gap = notes[lo[1]:hi[0]]
        if '\n' in gap:
            return False
        return not re.search(r'[.!?;]', gap)

    parent = list(range(len(enriched)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for i, a in enumerate(enriched):
        for j in range(i + 1, len(enriched)):
            b = enriched[j]
            if a['concept'] != b['concept'] or a['source'] != b['source']:
                continue
            if a['span'] and b['span']:
                if same_passage(a['span'], b['span']):
                    union(i, j)
            elif not a['located'] and not b['located']:
                if normalise(a['quote'])[0].strip() == normalise(b['quote'])[0].strip():
                    union(i, j)

    # Second pass, for the items the span rule cannot reach. A finding about
    # something that is **not in the notes yet** — an uncovered extraction item,
    # or B's flag on an item rather than on a sentence — has no anchor, so its
    # key degenerates to its source. Such an item joins an existing group only
    # when exactly **one** group could take it. Two candidates is the case that
    # matters: an unanchored flag on S22 must not become the bridge that merges
    # two findings about different sentences, both citing S22, into one wrong
    # proposal. Ambiguity leaves it standing alone, where it is visible.
    def compatible(a_concept, b_concept):
        return not a_concept or not b_concept or a_concept == b_concept

    for i, a in enumerate(enriched):
        if a['located'] or not a['source']:
            continue
        mine = root(i)
        if any(enriched[k]['located'] for k in range(len(enriched))
               if root(k) == mine):
            continue
        candidates_ = {root(j) for j, b in enumerate(enriched)
                       if root(j) != mine and b['source'] == a['source']
                       and compatible(a['concept'], b['concept'])}
        if len(candidates_) == 1:
            union(i, candidates_.pop())

    groups: dict[int, dict] = {}
    for i, e in enumerate(enriched):
        g = groups.setdefault(root(i), {'concept': e['concept'], 'source': e['source'],
                                        'span': None, 'origins': [], 'evidence': [],
                                        'items': [], 'located': False,
                                        'ambiguous': False})
        g['concept'] = g['concept'] or e['concept']
        g['items'].append(e['item'])
        g['ambiguous'] = g['ambiguous'] or e['ambiguous']
        if e['span']:
            g['located'] = True
            g['span'] = ([min(g['span'][0], e['span'][0]),
                          max(g['span'][1], e['span'][1])] if g['span'] else e['span'])
        origin = e['item'].get('origin')
        if not origin:
            fid = str(e['item'].get('id') or '')
            origin = ('finding ' + fid if fid.startswith('f-') else
                      'explain ' + fid if fid.startswith('x-') else
                      fid or 'verification')
        g['origins'].append(origin)
        ev = e['item'].get('evidence') or e['item'].get('explain_claim') or ''
        if ev:
            g['evidence'].append(ev)

    return {'groups': [dict(g, origins=sorted(set(g['origins'])))
                       for g in groups.values()],
            'collapsed': len(items) - len(groups)}


# --------------------------------------------------------------------------
# concept registry


def load_concepts(path: Path | str) -> dict:
    path = Path(path)
    if not path.is_file():
        return {'concepts': {}, 'exists': False}
    data = json.loads(path.read_text(encoding='utf-8'))
    data.setdefault('concepts', {})
    data['exists'] = True
    return data


def current_heading(registry: dict, concept: str, lesson: str) -> str | None:
    entry = (registry.get('concepts') or {}).get(concept)
    if not entry:
        return None
    for s in entry.get('sections') or []:
        if s.get('lesson') == lesson:
            return s.get('heading')
    return None


def successor(registry: dict, concept: str, lesson: str) -> dict:
    """B's own reuse rule, applied backwards, and only when it is unambiguous.

    Note-invariants section 6: overlap at least half of the smaller `source_ids`
    set. Two candidates that both qualify is not a tie to break — it is the case
    where replay asks and, failing an answer, marks the entry `orphaned`.
    """
    concepts = registry.get('concepts') or {}
    entry = concepts.get(concept)
    old_ids = set()
    if entry:
        for s in entry.get('sections') or []:
            if s.get('lesson') == lesson:
                old_ids |= set(s.get('source_ids') or [])
    if not old_ids:
        return {'concept': concept, 'candidates': [],
                'reason': 'the retired concept has no recorded source ids for this '
                          'lesson, so there is nothing to match a successor on'}
    out = []
    for cid, data in concepts.items():
        if cid == concept or data.get('retired'):
            continue
        for s in data.get('sections') or []:
            if s.get('lesson') != lesson:
                continue
            ids = set(s.get('source_ids') or [])
            if not ids:
                continue
            overlap = len(ids & old_ids)
            if overlap * 2 >= min(len(ids), len(old_ids)):
                out.append({'concept': cid, 'heading': s.get('heading'),
                            'overlap': overlap,
                            'shared': sorted(ids & old_ids)})
    out.sort(key=lambda r: -r['overlap'])
    return {'concept': concept, 'candidates': out,
            'unique': len(out) == 1,
            'reason': None if len(out) == 1 else
                      ('no candidate reaches the overlap rule' if not out else
                       'more than one candidate reaches the overlap rule; ask')}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('sections', 'find', 'candidates', 'protected', 'collapse'):
        p = sub.add_parser(name)
        p.add_argument('--notes', required=True)
        if name in ('find', 'candidates'):
            p.add_argument('--text', required=True)
            p.add_argument('--concept'); p.add_argument('--heading')
        if name == 'candidates':
            p.add_argument('--ids', nargs='*', default=None)
        if name == 'protected':
            p.add_argument('--start', type=int, required=True)
            p.add_argument('--end', type=int, required=True)
        if name == 'collapse':
            p.add_argument('--items', required=True)
    p = sub.add_parser('successor')
    p.add_argument('--concepts', required=True); p.add_argument('--concept', required=True)
    p.add_argument('--lesson', required=True)
    args = ap.parse_args(argv)

    if args.cmd == 'successor':
        out = successor(load_concepts(args.concepts), args.concept, args.lesson)
    else:
        notes = Path(args.notes).read_text(encoding='utf-8')
        if args.cmd == 'sections':
            out = {'sections': sections(notes)}
        elif args.cmd == 'find':
            out = find(notes, args.text, args.concept, args.heading)
        elif args.cmd == 'candidates':
            out = candidates(notes, args.text, args.concept, args.ids)
        elif args.cmd == 'protected':
            out = protected_hit(notes, args.start, args.end)
        else:
            items = json.loads(Path(args.items).read_text(encoding='utf-8'))
            out = collapse(notes, items)

    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
