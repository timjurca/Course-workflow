#!/usr/bin/env python3
"""The one parser for source markers. Every skill that scans them uses this.

There were four copies of this idea in the plugin and two of them were wrong,
which is the same disease that produced `sections.py`: one rule, copied, drifted.

The broken pair (course-corrections `anchor.py`, course-revision `findings.py`)
read `r'\\b([SBTAHNCVKG]\\d+(?:\\.\\d+)?!?)\\b'`, which fails twice:

  * `(?:\\.\\d+)?` allows **one** dotted part, so a three-part book id is
    truncated: `[B4.2.11]` yielded `B4.2`, an id that does not exist. A phantom
    id matches nothing in the extraction, so `verify_fix.marker` **dropped**
    otherwise valid gap fills, and `candidates()` ranked on ids that were never
    written.
  * a trailing `\\b` after `!?` can never hold, because `!` is not a word
    character and a marker is followed by `,` or `]`. So the highlight suffix
    was **never** captured and `B15.7!` was indistinguishable from `B15.7`.

note-invariants section 5 is explicit that a parser must reject an unknown shape
loudly rather than ignore it; silently truncating is the opposite of that. The
behaviour below is course-notes', which was the only correct copy, kept
byte-for-byte so the coverage counts it produces do not move.
"""
from __future__ import annotations

import re

# A source marker: one uppercase letter from SBTAHNCVKG, a digit, then any
# number of dotted parts, an optional `n`, an optional `!` (the student
# highlighted it). The lookarounds replace \b, which cannot see past `!`.
SOURCE_ID_RE = re.compile(r'(?<![A-Za-z0-9])([SBTAHNCVKG]\d+(?:\.\d+)*n?!?)'
                          r'(?![A-Za-z0-9])')

# The same shape, anchored, for validating a single token.
SOURCE_ID_FULL_RE = re.compile(r'^[SBTAHNCVKG]\d+(?:\.\d+)*n?!?$')


def find_ids(text: str) -> list[str]:
    """Every source id in `text`, in order, duplicates kept.

    Duplicates are kept because callers differ: a coverage count wants them all,
    a section listing wraps this in `sorted(set(...))`. Deciding here would
    silently change one of them.
    """
    return SOURCE_ID_RE.findall(text or '')


def is_id(token: str) -> bool:
    return bool(SOURCE_ID_FULL_RE.match((token or '').strip()))


def base_id(token: str) -> str:
    """The id without the highlight suffix. `B4.2.11!` -> `B4.2.11`.

    Only for comparing a highlighted citation with a plain one. It is never
    written back into notes: the `!` is part of the recorded id.
    """
    token = (token or '').strip()
    return token[:-1] if token.endswith('!') else token
