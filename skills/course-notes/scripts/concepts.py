#!/usr/bin/env python3
"""Concept IDs: the identity a section keeps when its heading and wording change.

Notes are fully regenerated on every run. Without a stable identity, every
regeneration is a new set of sections as far as the rest of the plugin is
concerned: skill C's revision history detaches, skill D's corrections lose their
anchor, skill E cannot find the material it was asked about. The heading cannot
serve as that identity, because rewording a heading is exactly the kind of
improvement a re-run is supposed to make.

So a concept ID is the slug of the concept's **first** heading, and then it
never changes, whatever the heading later becomes.

**The reuse rule is set arithmetic, not judgement**, and it is implemented once
here because C, D and E use the same rule to find a successor concept: a node
keeps the ID of the previous section for this lesson whose `source_ids` overlap
it most, when the overlap is at least half of the smaller set. Below that, it is
a different concept and gets a new ID. The threshold is a guess (B §17 item 14)
and it is a flag, not a constant, so it can be tuned against a real re-run.

**Tutorials create no concepts.** A tutorial problem borrows the ID of the
lesson section its `Connects to` link points at, and is appended to that
concept's `sections` with `"lesson": "T02"`. A problem with no such link carries
no ID and is reported — inventing one would create a concept that exists only in
a tutorial and has no lesson material behind it.

**Nothing is ever deleted.** A concept whose last section disappears is marked
`retired: true`, because C's history has to stay resolvable and E has to be able
to explain a retired concept and name its successor.

CLI:
    concepts.py assign --course <c> --lesson L03 --nodes <json> [--apply]
    concepts.py assign --course <c> --lesson T02 --nodes <json> --tutorial [--apply]
    concepts.py get --course <c> --concept instrument-relevance
    concepts.py rebuild --course <c> [--apply]
    concepts.py migrate --course <c> [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import naming                                                      # noqa: E402
import renumber                                                    # noqa: E402

REL = Path('.data') / 'concepts.json'
KEY_RE = re.compile(r'^[LT]\d{2}$')
CONCEPT_RE = re.compile(r'<!--\s*concept:\s*([a-z0-9][a-z0-9-]*)\s*-->')
MARKER_RE = re.compile(r'\[([^\]]+)\]')
ID_RE = re.compile(r'^[SBTAHNCVKG]\d+(?:\.\d+)*n?!?$')

# Fixed sections carry no concept ID: they are containers, not concepts, and an
# ID on one would make "Definitions" a thing C could ask a question about.
FIXED = {'definitions', 'assigned readings', 'assigned videos', 'assigned links',
         'recap', 'uncovered material', 'my additions', 'my notes',
         'my questions', 'core summary', 'external references'}

DEFAULT_OVERLAP = 0.5


# The hyphenation lives in shared/scripts/naming.py, because skill D and skill E
# both resolve a successor concept by the same rule and a second copy here is a
# second behaviour waiting to drift.
concept_id = naming.concept_id


def path_of(course: Path | str) -> Path:
    return Path(course) / REL


def load(course: Path | str) -> dict:
    path = path_of(course)
    if not path.is_file():
        return {'applied_renumbers': [], 'concepts': {}}
    text = path.read_text(encoding='utf-8').strip()
    data = json.loads(text) if text else {}
    data.setdefault('applied_renumbers', [])
    data.setdefault('concepts', {})
    return data


def save(course: Path | str, data: dict) -> str:
    path = path_of(course)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                              sort_keys=True) + '\n', encoding='utf-8')
    os.replace(tmp, path)
    return str(path)


def _overlap_score(a: list, b: list) -> float:
    sa, sb = set(a or []), set(b or [])
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def _unique_id(base: str, taken: set[str]) -> str:
    """A concept ID is never reused for a different concept, so a collision on
    the slug gets a suffix rather than joining the existing concept."""
    if base not in taken:
        return base
    n = 2
    while f'{base}-{n}' in taken:
        n += 1
    return f'{base}-{n}'


def assign(course: Path | str, lesson: str, nodes: list[dict],
           tutorial: bool = False, threshold: float = DEFAULT_OVERLAP,
           apply_it: bool = False) -> dict:
    if not KEY_RE.match(lesson):
        return {'ok': False, 'reason': f'lesson key must be L<NN>/T<NN>: {lesson!r}'}
    data = load(course)
    concepts = data['concepts']
    results, unlinked = [], []
    used_now: set[str] = set()

    previous = {cid: [s for s in c.get('sections', [])
                      if s.get('lesson') == lesson]
                for cid, c in concepts.items()}

    for node in nodes:
        heading = (node.get('heading') or '').strip()
        ids = list(node.get('source_ids') or [])
        if heading.lower() in FIXED:
            results.append({'heading': heading, 'concept': None,
                            'reason': 'fixed section, no concept ID'})
            continue

        if tutorial:
            cid = _tutorial_concept(concepts, node)
            if cid is None:
                unlinked.append(heading)
                results.append({'heading': heading, 'concept': None,
                                'reason': 'no Connects to link into a lesson '
                                          'section, so no concept ID. Tutorials '
                                          'never create concepts of their own.'})
                continue
            row = {'heading': heading, 'concept': cid, 'reused': True,
                   'from': 'tutorial link'}
        else:
            cid, why, prev_heading = _reuse_or_new(concepts, previous, ids,
                                                   heading, threshold,
                                                   used_now)
            row = {'heading': heading, 'concept': cid, 'reused': why != 'new',
                   'from': why}
            if prev_heading and prev_heading != heading:
                # A reused concept keeps its heading; only a material change of
                # subject, or a move to a different zone, sanctions a rename.
                # Either way the change is reported, because inbound links point
                # at the old anchor, and the caller closes the ones it wrote
                # this run with check_links.py retarget.
                row['previous_heading'] = prev_heading
                row['heading_changed'] = True
                row['keep_heading_unless_subject_or_zone_changed'] = prev_heading

        concept = concepts.setdefault(cid, {'title': heading, 'sections': [],
                                            'retired': False})
        concept['retired'] = False
        concept.setdefault('title', heading)
        # One section per lesson per concept. This run owns this lesson's entry
        # and replaces it; every other lesson's entry is left exactly as it was.
        concept['sections'] = [s for s in concept['sections']
                               if s.get('lesson') != lesson]
        concept['sections'].append({'lesson': lesson, 'heading': heading,
                                    'source_ids': ids})
        used_now.add(cid)
        results.append(row)

    # A concept this lesson used to carry and no longer does loses that section.
    # If nothing is left anywhere it is retired, never deleted: C's history and
    # E's successor lookup both have to stay resolvable.
    retired = []
    for cid, concept in concepts.items():
        if cid not in used_now:
            concept['sections'] = [s for s in concept.get('sections', [])
                                   if s.get('lesson') != lesson]
        if not concept.get('sections') and not concept.get('retired'):
            concept['retired'] = True
            retired.append(cid)

    if apply_it:
        data['concepts'] = concepts
        save(course, data)
    return {'lesson': lesson, 'nodes': results, 'retired': retired,
            'unlinked': unlinked, 'applied': apply_it,
            'concepts': len(concepts),
            'new': [r['concept'] for r in results if r.get('from') == 'new'],
            'reused': [r['concept'] for r in results if r.get('reused')]}


def _reuse_or_new(concepts, previous, ids, heading, threshold, used_now):
    best, best_score = None, 0.0
    for cid, sections in previous.items():
        if cid in used_now:
            continue
        for s in sections:
            score = _overlap_score(ids, s.get('source_ids'))
            if score > best_score:
                best, best_score = (cid, s.get('heading')), score
    if best and best_score >= threshold:
        return best[0], f'overlap {best_score:.2f}', best[1]

    slug = concept_id(heading)
    if slug in concepts and slug not in used_now:
        # The same concept taught again in a later lesson: one concept, several
        # lessons, rather than a second ID for the same subject.
        return slug, 'same heading in another lesson', concepts[slug].get('title')
    return _unique_id(slug or 'concept', set(concepts) | used_now), 'new', None


def _tutorial_concept(concepts: dict, node: dict) -> str | None:
    """Follow `Connects to: [[ECON_L03_Final_notes#Instrument relevance]]`."""
    explicit = (node.get('concept') or '').strip()
    if explicit:
        return explicit if explicit in concepts else None
    link = (node.get('connects_to') or '').strip()
    if not link:
        return None
    anchor = link.split('#', 1)[1] if '#' in link else link
    anchor = anchor.strip(' []|')
    for cid, concept in concepts.items():
        for s in concept.get('sections', []):
            if (s.get('heading') or '').strip().lower() == anchor.lower():
                return cid
    slug = concept_id(anchor)
    return slug if slug in concepts else None


def rebuild(course: Path | str, apply_it: bool = False) -> dict:
    """Rebuild the registry from the `<!-- concept: -->` comments in the notes.

    Order matters and is the whole reason this is not a loop over files: pending
    renumber blocks are applied to the files that **survived** first, then the
    registry is rebuilt from them, and `applied_renumbers` is pre-filled with
    every block id in A's log. A rebuild therefore never re-applies an old block
    and never skips a pending one.
    """
    course = Path(course)
    concepts: dict = {}
    for notes in sorted(course.rglob('*_Final_notes.md')):
        if 'Explanations' in notes.parts or '.work' in notes.parts:
            continue
        key = _key_from_name(notes.name)
        if not key:
            continue
        text = notes.read_text(encoding='utf-8', errors='replace')
        for cid, heading, ids in _sections_of(text):
            concept = concepts.setdefault(cid, {'title': heading,
                                                'sections': [],
                                                'retired': False})
            concept['sections'].append({'lesson': key, 'heading': heading,
                                        'source_ids': ids})
    blocks = renumber.renumber_blocks(course)
    data = {'applied_renumbers': [b['id'] for b in blocks],
            'concepts': concepts}
    if apply_it:
        save(course, data)
    return {'concepts': len(concepts), 'applied_renumbers': data['applied_renumbers'],
            'applied': apply_it,
            'note': 'applied_renumbers is pre-filled with every block in A\'s '
                    'log; apply pending blocks to the surviving files before '
                    'rebuilding, not after.'}


def _key_from_name(name: str) -> str | None:
    m = re.search(r'([LT])(\d{2})_Final_notes\.md$', name)
    return f'{m.group(1)}{m.group(2)}' if m else None


def _sections_of(text: str):
    """(concept id, heading, source ids) for each H2 that carries a concept."""
    parts = re.split(r'^(##\s+(?!#).+)$', text, flags=re.MULTILINE)
    heading = None
    for chunk in parts:
        m = re.match(r'^##\s+(?!#)(.+?)\s*$', chunk)
        if m:
            heading = m.group(1).strip()
            continue
        if heading is None:
            continue
        cm = CONCEPT_RE.search(chunk)
        if cm:
            yield cm.group(1), heading, sorted(_ids_in(chunk))
        heading = None


def _ids_in(text: str) -> set[str]:
    out = set()
    for body in MARKER_RE.findall(text):
        for part in body.split(','):
            part = part.strip()
            if ID_RE.match(part):
                out.add(part)
    return out


def migrate(course: Path | str, apply_it: bool = False) -> dict:
    data = load(course)
    blocks = renumber.pending_blocks(course, data.get('applied_renumbers', []))
    if not blocks:
        return {'blocks': 0, 'changed': 0}
    mapping = {}
    for block in blocks:
        mapping.update(renumber.moves_to_mapping(block['moves']))
    changed = 0
    for concept in data['concepts'].values():
        for s in concept.get('sections', []):
            new = renumber.remap_key(s.get('lesson', ''), mapping)
            if new != s.get('lesson'):
                s['lesson'] = new
                changed += 1
    data['applied_renumbers'] = list(data.get('applied_renumbers', [])) + \
        [b['id'] for b in blocks]
    if apply_it:
        save(course, data)
    return {'blocks': len(blocks), 'ids': [b['id'] for b in blocks],
            'changed': changed, 'mapping': mapping, 'applied': apply_it}


def _load_json_arg(raw: str):
    """A path or inline JSON. `Path(raw).is_file()` alone raises ENAMETOOLONG on
    an inline document, which is a crash rather than an error message."""
    text = (raw or '').lstrip()
    if text[:1] in ('[', '{'):
        return json.loads(raw)
    return json.loads(Path(raw).read_text(encoding='utf-8'))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('assign', 'get', 'rebuild', 'migrate', 'list'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True)
        if name in ('assign', 'rebuild', 'migrate'):
            p.add_argument('--apply', action='store_true')
        if name == 'assign':
            p.add_argument('--lesson', required=True)
            p.add_argument('--nodes', required=True)
            p.add_argument('--tutorial', action='store_true')
            p.add_argument('--threshold', type=float, default=DEFAULT_OVERLAP)
        if name == 'get':
            p.add_argument('--concept', required=True)
    args = ap.parse_args(argv)

    if args.cmd == 'assign':
        nodes = _load_json_arg(args.nodes)
        out = assign(args.course, args.lesson, nodes, args.tutorial,
                     args.threshold, args.apply)
    elif args.cmd == 'get':
        out = load(args.course)['concepts'].get(args.concept) or \
            {'missing': args.concept}
    elif args.cmd == 'list':
        data = load(args.course)
        out = {'count': len(data['concepts']),
               'applied_renumbers': data['applied_renumbers'],
               'concepts': sorted(data['concepts'])}
    elif args.cmd == 'rebuild':
        out = rebuild(args.course, args.apply)
    else:
        out = migrate(args.course, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
