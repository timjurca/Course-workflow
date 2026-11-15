#!/usr/bin/env python3
"""One string form for a `run` timestamp, whoever read it and however.

A run id reaches a comparison by three routes, and they disagree:

  * from an extraction header or a correction log line, as raw text:
    `2026-11-13T15:31:51`
  * from notes frontmatter where it was written **quoted**, through YAML:
    the same string
  * from notes frontmatter where it was written **bare with seconds**, through
    YAML: a `datetime`, whose `str()` is `2026-11-13 15:31:51`

The third route made `course-corrections` gate check 4 report every extraction
as `from_another_run`, and made revision's correction check report every
applied correction as needing replay. Quoting the value at the source stops new
notes from taking that route; normalising **both sides** of every comparison
keeps notes written before the quoting rule working (note-invariants §10).

`norm_run` is for comparison and for passing a run on. It never invents
precision: a minute-only run stays minute-only.

CLI:
    runstamp.py norm --value "<run>"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime

_DT_SEP_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})(?:[ \t]+|t)(\d)')
_FRACTION_RE = re.compile(r'(\d{2}:\d{2}:\d{2})\.(\d+)')


def norm_run(value) -> str:
    """`datetime`, `date`, quoted or spaced text -> `YYYY-MM-DDTHH:MM[:SS]`.

    Rules, applied to both sides of any comparison:
      * a datetime or date is written in ISO form with a `T` separator
      * surrounding whitespace and one pair of quotes are dropped
      * a space (or a lowercase `t`) between date and time becomes `T`
      * a trailing `Z` is written `+00:00`, as `isoformat()` writes UTC
      * a fractional second loses its trailing zeros, so `.5` equals `.500000`
    `None` and the empty string give ''.
    """
    if value is None:
        return ''
    if isinstance(value, datetime):
        s = value.isoformat()
    elif isinstance(value, date):
        s = value.isoformat()
    else:
        s = str(value).strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in '"\'':
            s = s[1:-1].strip()
    s = _DT_SEP_RE.sub(r'\1T\2', s)
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'

    def _frac(m):
        digits = m.group(2).rstrip('0')
        return m.group(1) + ('.' + digits if digits else '')
    return _FRACTION_RE.sub(_frac, s)


def same_run(a, b) -> bool:
    """True when two run values name the same run. Two empty values do not."""
    na, nb = norm_run(a), norm_run(b)
    return bool(na) and na == nb


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('norm')
    p.add_argument('--value', required=True)
    args = ap.parse_args(argv)
    json.dump({'value': args.value, 'norm': norm_run(args.value)}, sys.stdout)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
