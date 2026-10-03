#!/usr/bin/env python3
"""Find a concept's own block, at whatever heading level it sits on.

Two skills each had their own heading splitter and both split on **H2 only**,
taking the first `<!-- concept: -->` comment inside each H2 as that section's
concept (course-corrections `anchor.sections`, course-explain `scope.split_h2`).
Concepts do not live on H2. Across 13 real lessons, 360 of 364 sit on H3 and the
other 4 on H2, so the H2-only reading returned the whole `## Concepts` block --
70,788 characters in one measured case -- labelled with whichever concept
happened to come first, and **nothing at all** for every other concept in it.

What that broke: `replay` re-anchors a logged correction by its concept, found
no section, and orphaned it, which is the one promise course-corrections exists
to keep. `links.repair` could not locate a heading to repair. Concept-scoped
`find` returned "concept section not in this file" for every concept.
course-explain answered 22 of 23 concepts per lesson with nothing.

The boundary rule is forced by the notes, not chosen: a concept block runs from
**its own heading** to the next heading of the **same or higher level**. All 38
H4 headings in the corpus sit inside concept sections, so ending at the next
heading of any level would cut a concept off at its first sub-heading; and the
4 H2-level concepts mean the rule cannot assume H3.

This does **not** replace `anchor.sections()`. That one answers a different
question -- which H2 structural block is this -- for protecting `## My
additions` and for finding `## Uncovered material` and `## Definitions`, whose
headings are fixed English. Keeping them apart is deliberate: the protection
check needs the whole H2 span, and re-deriving it from sub-blocks is exactly the
kind of quiet mistake that would let a write land in the student's own writing.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import markers  # noqa: E402

HEAD_RE = re.compile(r'^(?P<hashes>#{1,6})[ \t]+(?P<title>.+?)[ \t]*$', re.MULTILINE)
CONCEPT_RE = re.compile(r'^<!--\s*concept:\s*(?P<id>[^\s>]+)\s*-->\s*$', re.MULTILINE)
FENCE_RE = re.compile(r'^[ \t]*(?:```|~~~)', re.MULTILINE)


def _fenced_spans(text: str) -> list[tuple[int, int]]:
    """Byte ranges inside fenced code blocks, so a `## ` in a code sample is not
    read as a heading. The corpus has none today; this keeps it that way."""
    marks = [m.start() for m in FENCE_RE.finditer(text)]
    return [(marks[i], marks[i + 1]) for i in range(0, len(marks) - 1, 2)]


def headings(text: str) -> list[dict]:
    """Every markdown heading, any level, with its span start and body start."""
    fenced = _fenced_spans(text)
    out = []
    for m in HEAD_RE.finditer(text):
        if any(a <= m.start() < b for a, b in fenced):
            continue
        out.append({'level': len(m.group('hashes')),
                    'heading': m.group('title').strip(),
                    'start': m.start(), 'body_start': m.end()})
    return out


def concept_blocks(text: str) -> list[dict]:
    """One block per `<!-- concept: -->` comment, bounded by heading level."""
    heads = headings(text)
    fenced = _fenced_spans(text)
    out = []
    for m in CONCEPT_RE.finditer(text):
        if any(a <= m.start() < b for a, b in fenced):
            continue
        prior = [h for h in heads if h['start'] < m.start()]
        if not prior:
            continue                      # a concept before any heading: not a section
        owner = prior[-1]
        end = next((h['start'] for h in heads
                    if h['start'] > owner['start'] and h['level'] <= owner['level']),
                   len(text))
        body = text[owner['body_start']:end]
        out.append({'concept': m.group('id'), 'heading': owner['heading'],
                    'level': owner['level'], 'start': owner['start'],
                    'body_start': owner['body_start'], 'end': end,
                    'source_ids': sorted(set(markers.find_ids(body)))})
    return out


def blocks_for(text: str, concept: str) -> list[dict]:
    return [b for b in concept_blocks(text) if b['concept'] == concept]


def block_for(text: str, concept: str) -> dict | None:
    """The one block for this concept, or None when absent **or duplicated**.

    Two matches is as much a failure as none (note-invariants section 21). No
    lesson in the corpus repeats a concept id, so returning None on a duplicate
    reports a real defect rather than papering over it.
    """
    hits = blocks_for(text, concept)
    return hits[0] if len(hits) == 1 else None


def concept_of(text: str, source_id: str) -> dict:
    """Which concept cites this source id.

    Returns `{'concept': id|None, 'candidates': [...]}`. When several concepts
    cite it -- 106 ids across the corpus do, one of them in 11 blocks -- the
    concept is **None** and every candidate is listed, so the plan can show them
    and the student chooses. Picking the first would label a finding with a
    concept that may be wrong and show nothing on screen to say it guessed.
    """
    hits = sorted({b['concept'] for b in concept_blocks(text)
                   if source_id in b['source_ids']})
    return {'concept': hits[0] if len(hits) == 1 else None, 'candidates': hits}
