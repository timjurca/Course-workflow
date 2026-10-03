#!/usr/bin/env python3
"""`## What to remember`: the one zone of a notes file that is not from a source.

Everything else B writes is traceable to an extracted item. This zone is Claude's
opinion about what matters, and an opinion sitting unmarked in a document whose
whole discipline is traceability is the failure mode the marker families exist to
prevent: a bullet copied out of here into a revision question is indistinguishable
from a sourced claim, and by the time anyone notices, it has been revised from and
tested on as if the lecturer had said it.

So three things are mechanical rather than advisory (note-invariants §2a, §8):

  * **Every bullet carries `[judgement]`, and nothing outside the zone does.**
    Per-line, not per-section, because a line travels and a section boundary does
    not.
  * **Source IDs cited here do not count as cited.** `strip()` is what Pass D uses
    before it computes the cited set, so an opinion can never satisfy the coverage
    guarantee for material the body failed to cover.
  * **The top tier is capped.** Selection is the entire value of the zone; with no
    cap the list grows every run until it is the table of contents again.

The zone also carries a **protected ranking block**, the inverse of a TOC marker
pair: B replaces everything *outside* `<!-- ranking:yours:start/end -->` and never
what is inside it. A judgement cannot be wrong against a source, only disagreed
with, so disagreement is not a correction and D stays out entirely; the block is
the whole mechanism for disagreeing.

`strip()` is also the blinded view C reads before committing its own list, so that
two raters stay independent (note-invariants §8b).

CLI:
    judgement.py parse   --notes <p>
    judgement.py check   --notes <p>
    judgement.py strip   --notes <p> [--out <f>]
    judgement.py ranking --notes <p>
    judgement.py drift   --notes <p> [--previous <p> | --history <dir>]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ZONE_TITLE = 'What to remember'
ZONE_HEAD_RE = re.compile(r'^##\s+What to remember\s*$', re.MULTILINE)
NEXT_H2_RE = re.compile(r'^##\s+(?!#)', re.MULTILINE)

MARKER = '[judgement]'
MARKER_RE = re.compile(r'\[judgement\]', re.IGNORECASE)

TIER_MUST = 'Must know'
TIER_ALSO = 'Also likely'
TIER_RE = re.compile(r'^\*\*(Must know|Also likely)\*\*\s*$', re.MULTILINE)

RANK_START = '<!-- ranking:yours:start -->'
RANK_END = '<!-- ranking:yours:end -->'
RANK_RE = re.compile(re.escape(RANK_START) + r'(.*?)' + re.escape(RANK_END),
                     re.DOTALL)

CALLOUT_RE = re.compile(r'^>\s*\[!warning\]', re.MULTILINE)
BULLET_RE = re.compile(r'^\s*-\s+(?P<text>\S.*)$')
H3_RE = re.compile(r'^###\s+(?!#)', re.MULTILINE)

CAP = 10

# Fenced code and inline code must not be scanned: a snippet documenting the
# marker is not a use of it. Blanking preserves offsets.
FENCE_RE = re.compile(r'^(?:```|~~~).*?^(?:```|~~~)\s*$', re.MULTILINE | re.DOTALL)
INLINE_CODE_RE = re.compile(r'`[^`\n]*`')


def _blank(m):
    return re.sub(r'[^\n]', ' ', m.group(0))


def _scrub(text: str) -> str:
    return INLINE_CODE_RE.sub(_blank, FENCE_RE.sub(_blank, text))


# ------------------------------------------------------------------ locate

def locate(text: str) -> dict:
    """Byte span of the zone, or `present: False`."""
    m = ZONE_HEAD_RE.search(text)
    if not m:
        return {'present': False, 'start': None, 'end': None, 'zone': ''}
    nxt = NEXT_H2_RE.search(text, m.end())
    end = nxt.start() if nxt else len(text)
    return {'present': True, 'start': m.start(), 'end': end,
            'zone': text[m.start():end]}


def strip(text: str) -> str:
    """The notes without the zone. Pass D's cited-set input, and C's blinded view."""
    loc = locate(text)
    if not loc['present']:
        return text
    return text[:loc['start']] + text[loc['end']:]


def ranking_block(text: str) -> str | None:
    """The student's pinned bytes, verbatim, or None when the pair is absent."""
    loc = locate(text)
    if not loc['present']:
        return None
    m = RANK_RE.search(loc['zone'])
    return m.group(1) if m else None


# ------------------------------------------------------------------- parse

def _items(chunk: str, tier: str) -> list[dict]:
    out = []
    for n, line in enumerate(chunk.split('\n'), 1):
        m = BULLET_RE.match(line)
        if not m:
            continue
        raw = m.group('text').strip()
        out.append({'tier': tier, 'text': raw,
                    'marked': bool(MARKER_RE.search(raw)),
                    'key': key_of(raw)})
    return out


DISPLAY_CAP = 110


def key_of(text: str) -> str:
    """A stable-ish identity for a free-text item, for drift only.

    Free text has no id, so drift is matched on the wording itself: markers and
    emphasis removed, collapsed, lowercased. Near-matches are paired by
    similarity afterwards, so this only has to make an unchanged line hash to
    the same thing.

    It is deliberately **not truncated**. It used to keep the first 80
    characters, which made every pair of items agreeing in their opening clause
    identical: on the first regeneration in this vault two `Must know` items
    were rewritten only in their trailing reason and drift reported them as
    unchanged. A drift report that under-reports is worse than none, because
    the whole point is to show what a re-run moved.
    """
    t = re.sub(r'\[[^\]]*\]', ' ', text)
    t = re.sub(r'[*_`>#]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip().lower()


OPENING_CHARS = 80


def _opening(key: str) -> str:
    """The clause that names the item, used to pair an item with its rewrite."""
    return key[:OPENING_CHARS]


def _short(key: str) -> str:
    return key if len(key) <= DISPLAY_CAP else key[:DISPLAY_CAP - 1] + '\u2026' 


def parse(text: str) -> dict:
    loc = locate(text)
    if not loc['present']:
        return {'present': False, 'items': [], 'must': [], 'also': [],
                'ranking': None, 'callout': False}
    zone = loc['zone']
    body = RANK_RE.sub('\n', zone)          # generated part only
    pieces, tiers = TIER_RE.split(body), {}
    # split() gives [before, label, chunk, label, chunk, ...]
    for i in range(1, len(pieces), 2):
        tiers[pieces[i]] = pieces[i + 1]
    must = _items(tiers.get(TIER_MUST, ''), TIER_MUST)
    also = _items(tiers.get(TIER_ALSO, ''), TIER_ALSO)
    return {'present': True, 'must': must, 'also': also, 'items': must + also,
            'ranking': ranking_block(text), 'callout': bool(CALLOUT_RE.search(body)),
            'tiers_found': sorted(tiers), 'zone': zone}


# ------------------------------------------------------------------- check

def check(text: str) -> dict:
    """The judgement gate. Reports; never blocks a write."""
    scrubbed = _scrub(text)
    p = parse(scrubbed)
    rows = []
    if not p['present']:
        return {'present': False, 'problems': [], 'must': 0, 'also': 0,
                'note': 'no `## What to remember` zone in this file'}

    unmarked = [i['text'][:110] for i in p['items'] if not i['marked']]
    for u in unmarked:
        rows.append({'kind': 'unmarked item', 'detail': u,
                     'fix': 'every bullet in the zone carries `[judgement]`'})

    loc = locate(scrubbed)
    outside = strip(scrubbed)
    leaks = len(MARKER_RE.findall(outside))
    if leaks:
        for m in MARKER_RE.finditer(outside):
            line = outside[:m.start()].count('\n') + 1
            rows.append({'kind': 'marker outside the zone', 'detail': f'line {line}',
                         'fix': '`[judgement]` is legal only inside '
                                '`## What to remember`'})

    if len(p['must']) > CAP:
        rows.append({'kind': 'top tier over cap',
                     'detail': f"{len(p['must'])} items, cap is {CAP}",
                     'fix': 'move the weakest items to **Also likely**'})

    if not p['callout']:
        rows.append({'kind': 'no warning callout', 'detail': '',
                     'fix': 'the zone opens with a `> [!warning]` callout saying '
                            'this is judgement, not a source'})

    if p['ranking'] is None:
        rows.append({'kind': 'ranking block missing', 'detail': '',
                     'fix': f'create the empty pair {RANK_START} … {RANK_END} '
                            'directly under the zone heading'})
    else:
        zone = loc['zone']
        if zone.index(RANK_START) > (zone.index('**' + TIER_MUST + '**')
                                     if '**' + TIER_MUST + '**' in zone else len(zone)):
            rows.append({'kind': 'ranking block below the generated list',
                         'detail': '',
                         'fix': 'your pins are read first, so the pair sits above '
                                '**Must know**'})

    if H3_RE.search(loc['zone']):
        rows.append({'kind': 'H3 inside the zone', 'detail': '',
                     'fix': 'tiers are bold labels; an H3 here would enter the '
                            'course table of contents as if it were a concept'})

    if not p['must']:
        rows.append({'kind': 'empty top tier', 'detail': '',
                     'fix': 'a zone with nothing in **Must know** is noise; '
                            'drop the zone or fill it'})

    return {'present': True, 'problems': rows, 'must': len(p['must']),
            'also': len(p['also']), 'cap': CAP,
            'clean': not rows}


# ------------------------------------------------------------------- drift

STAMP_RE = re.compile(r'_(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}(?:-\d{2})?)(?=\.md$)')


def newest_archive(history: Path | str, stem: str) -> Path | None:
    """The most recent archived version, by the timestamp *in the name*.

    Not by name alone: a disambiguating suffix (`..._21-30b.md`) sorts after a
    later file, so a plain name sort can pick an older baseline than the one on
    top. Not by mtime either: this vault syncs through iCloud, which rewrites
    mtimes on files it did not change. The stamp the plugin wrote is the only
    value that means what it says. A name carrying no stamp sorts last among
    the unstamped and never outranks a stamped one.
    """
    history = Path(history)
    if not history.is_dir():
        return None
    # Every `_pre-` archive, not just skill D's. An archive written by another
    # action differs from the current notes only by that action's own edit, so
    # taking one as the drift baseline reports that nothing moved. Demoting it
    # in the sort was not enough: `sorted(...)[-1]` still returns it when it is
    # the *only* candidate, which is exactly a lesson whose first archive the
    # figures pass just created. EBT lesson 3 reported "unchanged: 10" that way.
    cands = [p for p in history.glob(f'{stem}_*.md') if '_pre-' not in p.name]
    if not cands:
        return None
    def key(p):
        # An archive written by another action is not a regeneration baseline.
        # Skill D writes `*_pre-c-<id>.md` and the figures pass writes
        # `*_pre-figures-<stamp>.md`; both differ from the current notes only
        # by that action's own edit, so taking one as the baseline reports that
        # nothing moved and hides the real drift.
        if '_pre-' in p.name:
            return (-1, '', p.name)
        m = STAMP_RE.search(p.name)
        return (1, m.group(1), p.name) if m else (0, '', p.name)
    return sorted(cands, key=key)[-1]


def drift(now: str, before: str | None) -> dict:
    """What entered and left the top tier since the previous run.

    A reworded item must not report as one departure plus one arrival, so keys
    that are close matches are paired first and reported as rewordings.
    """
    cur = [i['key'] for i in parse(_scrub(now))['must']]
    if before is None:
        return {'baseline': False, 'entered': [], 'left': [], 'reworded': [],
                'note': 'no previous version on disk, so nothing to compare'}
    old = [i['key'] for i in parse(_scrub(before))['must']]
    entered = [k for k in cur if k not in old]
    left = [k for k in old if k not in cur]
    # Two keys, on purpose. Whether an item *changed* is decided on its whole
    # text, so a rewritten trailing reason is never missed. Whether two items
    # are the *same item* is decided on the opening clause, because that is
    # what names the subject: an item rewritten only in its reason keeps its
    # subject and must be reported as one rewording, not as a departure plus
    # an unrelated arrival. Using one key for both jobs fails one of them, and
    # the first regeneration in this vault hit both failures in turn.
    reworded = []
    for k in list(entered):
        near = difflib.get_close_matches(k, left, n=1, cutoff=0.75)
        if not near and left:
            by_opening = {}
            for x in left:
                by_opening.setdefault(_opening(x), x)
            hit = difflib.get_close_matches(_opening(k), list(by_opening),
                                            n=1, cutoff=0.80)
            near = [by_opening[hit[0]]] if hit else []
        if near:
            reworded.append({'from': near[0], 'to': k})
            entered.remove(k)
            left.remove(near[0])
    return {'baseline': True,
            'entered': entered, 'left': left, 'reworded': reworded,
            'entered_short': [_short(k) for k in entered],
            'left_short': [_short(k) for k in left],
            'reworded_short': [{'from': _short(r['from']), 'to': _short(r['to'])}
                               for r in reworded],
            'unchanged': len([k for k in cur if k in old])}


# --------------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('parse', 'check', 'ranking'):
        p = sub.add_parser(name)
        p.add_argument('--notes', required=True)
    p = sub.add_parser('strip')
    p.add_argument('--notes', required=True)
    p.add_argument('--out')
    p = sub.add_parser('drift')
    p.add_argument('--notes', required=True)
    p.add_argument('--previous')
    p.add_argument('--history')
    args = ap.parse_args(argv)

    notes_path = Path(args.notes)
    if not notes_path.exists():
        # A first run asks about the zone before the notes exist. SKILL.md
        # names this state ("Absent, or no notes file yet: create the pair
        # empty"), so it is an answer, not an error, and a traceback here
        # reads like a broken tool on the one path every new lesson takes.
        json.dump({'notes': str(notes_path), 'exists': False, 'block': None,
                   'zone': None, 'present': False,
                   'note': 'no notes file yet, so there is no zone to read. '
                           'Create the ranking pair empty (note-invariants '
                           '\u00a78).'},
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write('\n')
        return 0
    text = notes_path.read_text(encoding='utf-8')

    if args.cmd == 'strip':
        out = strip(text)
        if args.out:
            Path(args.out).write_text(out, encoding='utf-8')
            json.dump({'written': args.out, 'bytes': len(out)}, sys.stdout)
            sys.stdout.write('\n')
        else:
            sys.stdout.write(out)
        return 0

    if args.cmd == 'drift':
        prev = None
        if args.previous:
            prev = Path(args.previous).read_text(encoding='utf-8')
        elif args.history:
            p = newest_archive(args.history, Path(args.notes).stem)
            prev = p.read_text(encoding='utf-8') if p else None
        out = drift(text, prev)
    elif args.cmd == 'ranking':
        out = {'ranking': ranking_block(text)}
    elif args.cmd == 'check':
        out = check(text)
    else:
        out = parse(_scrub(text))
        out.pop('zone', None)

    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
