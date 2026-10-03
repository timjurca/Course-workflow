#!/usr/bin/env python3
"""The figures pass: add pictures to notes that already describe them.

A curve's shape, a flow with branches and a mapping of one structure onto
another are things prose can describe and cannot show. Notes written before
that rule existed describe them and leave them out: LTM lesson 3 carried 43
`from image, verify` readings and embedded nothing, so every picture it had
read was available to its writer and to no one else.

This action fixes that **without rewriting the document**. The judgement about
which figures earn a place is model work, in `SKILL.md`. What lives here is the
part that must not be left to good intentions: an edit contract that is
*checked* rather than promised.

**The contract.** Between the old notes and the new ones, only two kinds of
change are legal:

1. whole inserted lines, which is how an image and its caption arrive, and
2. markers added to a line, either into an existing bracket group or as a new
   group, which is how a claim that was read off an image gets said so.

Nothing may be deleted, and no word outside a bracket may change. That is
strong enough to make the pass safe on a finished document and weak enough to
let it repair the missing markers, which is the other half of what the flagged
lessons need.

The test is deliberately blunt: strip every bracket group from both versions of
a line, normalise whitespace, and require the remainders to be equal. A changed
word survives stripping and fails. It also refuses to let a marker be dropped,
because a repair pass that silently removes provenance is worse than no pass.

CLI:
    figures.py check --before <old.md> --after <new.md>
    figures.py apply --before <old.md> --after <new.md> --notes <dest> \\
        --work <lesson/.work> [--apply]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import json
import os
import re
import sys
from pathlib import Path

BRACKET_RE = re.compile(r'\[[^\[\]\n]*\]')
WS_RE = re.compile(r'\s+')

# An inserted line may only be part of a figure. The contract used to count
# insertions without reading them, which left the whole of Pass B and C legal
# under a name that promises pictures: a new paragraph, a new section, a new
# argument would all have passed. These four shapes are what a figure is made
# of, including inside a callout, which is where a student's own drawing goes.
QUOTE_RE = re.compile(r'^\s*>\s?')
EMBED_LINE_RE = re.compile(r'^!\[\[[^\]]+\]\]\s*$')
CAPTION_LINE_RE = re.compile(r'^\s*[*_].+')
CALLOUT_OPEN_RE = re.compile(r'^\[![a-zA-Z]+\]')


def _insertion_ok(line: str) -> bool:
    body = QUOTE_RE.sub('', line, count=1) if line.lstrip().startswith('>') else line
    if not body.strip():
        return True
    return bool(EMBED_LINE_RE.match(body.strip())
                or CAPTION_LINE_RE.match(body)
                or CALLOUT_OPEN_RE.match(body.strip()))


def _skeleton(line: str) -> str:
    """The line with every bracket group removed, whitespace collapsed.

    This is the part of a line the pass may not touch. Two lines with the same
    skeleton differ only in their markers.
    """
    return WS_RE.sub(' ', BRACKET_RE.sub(' ', line)).strip()


def _items(line: str) -> set:
    """Every comma-separated item inside every bracket group on the line."""
    out = set()
    for group in BRACKET_RE.findall(line):
        for part in group[1:-1].split(','):
            part = part.strip()
            if part:
                out.add(part)
    return out


def check(before: str, after: str) -> dict:
    a = before.splitlines()
    b = after.splitlines()
    inserted, marker_lines, violations = 0, [], []

    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        if tag == 'insert':
            for k in range(j1, j2):
                if _insertion_ok(b[k]):
                    inserted += 1
                else:
                    violations.append({
                        'kind': 'inserted line is not part of a figure',
                        'line': k + 1, 'detail': b[k].strip()[:110],
                        'fix': 'this action inserts an image, its caption, a '
                               'callout wrapper and blank lines. Prose belongs '
                               'to a regeneration'})
            continue
        if tag == 'delete':
            for k in range(i1, i2):
                violations.append({
                    'kind': 'line deleted', 'line': k + 1,
                    'detail': a[k][:120],
                    'fix': 'the figures pass adds; it never removes'})
            continue
        # replace: pair by skeleton, not by position.
        #
        # Zipping old and new lines positionally made two legal edits exclude
        # each other: an inserted figure block landing at an index an old line
        # still occupies was compared against that prose and failed. On FM
        # lesson 3 that made "embed slide 32 under Pitfall 3" and "mark S33 on
        # the Pitfall 4 lead-in" mutually exclusive, so the contract was
        # penalising putting a figure exactly where the prose argues from it,
        # which is the one placement rule the skill insists on. Matching each
        # old line to the new line that has its skeleton, and treating what is
        # left over as an insertion, describes what actually happened.
        old, new_lines = a[i1:i2], b[j1:j2]
        taken = set()
        for n, o in enumerate(old):
            hit = None
            for m, w in enumerate(new_lines):
                if m in taken:
                    continue
                if _skeleton(o) == _skeleton(w):
                    hit = m
                    break
            if hit is None:
                violations.append({
                    'kind': 'line deleted', 'line': i1 + n + 1,
                    'detail': a[i1 + n][:120],
                    'fix': 'the figures pass adds; it never removes'})
                continue
            taken.add(hit)
            o_line, w_line = o, new_lines[hit]
            if o_line == w_line:
                continue
            if not _items(o_line) <= _items(w_line):
                lost = sorted(_items(o_line) - _items(w_line))
                violations.append({
                    'kind': 'marker removed', 'line': i1 + n + 1,
                    'detail': f'{lost} no longer on the line',
                    'fix': 'a repair pass that drops provenance is worse than '
                           'no pass; keep every existing marker'})
            else:
                marker_lines.append({'line': j1 + hit + 1,
                                     'added': sorted(_items(w_line) - _items(o_line))})
        for m, w in enumerate(new_lines):
            if m in taken:
                continue
            if _insertion_ok(w):
                inserted += 1
            else:
                violations.append({
                    'kind': 'inserted line is not part of a figure',
                    'line': j1 + m + 1, 'detail': w.strip()[:110],
                    'fix': 'this action inserts an image, its caption, a '
                           'callout wrapper and blank lines. Prose belongs to '
                           'a regeneration'})

    return {'ok': not violations, 'inserted_lines': inserted,
            'marker_edits': marker_lines, 'violations': violations}


def _archive(notes: Path, work: Path, apply_it: bool) -> str | None:
    hist = work / 'history'
    stamp = _dt.datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
    # `_pre-figures-` and not a bare timestamp, because `judgement.drift` takes
    # the newest archive as its baseline. A figures archive differs from the
    # current notes only by the figures, so using it as the baseline reports
    # "nothing moved" and buries the real record: on LTM lesson 3 it turned
    # 3 entered, 3 left and 4 reworded into unchanged: 10.
    dest = hist / f'{notes.stem}_pre-figures-{stamp}.md'
    if apply_it:
        hist.mkdir(parents=True, exist_ok=True)
        dest.write_text(notes.read_text(encoding='utf-8'), encoding='utf-8')
    return str(dest)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('check', 'apply'):
        p = sub.add_parser(name)
        p.add_argument('--before', required=True)
        p.add_argument('--after', required=True)
        if name == 'apply':
            p.add_argument('--notes', required=True)
            p.add_argument('--work', required=True)
            p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)

    before = Path(args.before).read_text(encoding='utf-8', errors='replace')
    after = Path(args.after).read_text(encoding='utf-8', errors='replace')
    out = check(before, after)

    if args.cmd == 'apply':
        if not out['ok']:
            out['written'] = False
            out['refused'] = ('the edit breaks the figures contract, so nothing '
                              'was written')
        else:
            notes = Path(args.notes)
            out['archived'] = _archive(notes, Path(args.work), args.apply)
            if args.apply:
                tmp = notes.with_name(notes.name + '.tmp')
                tmp.write_text(after, encoding='utf-8')
                os.replace(tmp, notes)
            out['written'] = args.apply
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0 if out['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
