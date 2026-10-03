#!/usr/bin/env python3
"""sources_hash: one value over the contents of every source a run used.

Written by B into the notes frontmatter. C never recomputes it; C compares the
cheaper `sources_stat` instead, which is why B records size and mtime per file.

Two properties matter:

  * It covers **file contents**, PDF annotation layers included, because those
    are hashed as part of the bytes. Annotating a book chapter is therefore
    itself a reason to re-run the notes -- but only the notes that cite that
    chapter. A textbook the student highlights changes its bytes on every save,
    so a whole-file comparison declares every lesson citing it stale for good
    and blocks corrections, revision and explain permanently. See
    `absolve_annotation_changes`, which judges a ranged book entry on the
    lesson's own cited pages.
  * It covers **nothing else**. A folder rename or a lesson renumber changes no
    bytes, so the hash does not move. That is caught by `inputs` instead, whose
    overview row carries the lesson number.

A book entry may carry a page range (`Books/X.pdf#15.1-15.4`); the range is part
of the hashed identity, since the same file read over a different range is a
different source.

CLI:
    source_hash.py hash --base <dir> --sources <rel> [<rel> ...]
    source_hash.py stat --base <dir> --sources <rel> [<rel> ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CHUNK = 1 << 20


def split_entry(entry: str) -> tuple[str, str | None]:
    if '#' in entry:
        path, _, frag = entry.partition('#')
        return path, frag
    return entry, None


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def resolve_entry(base: Path, entry: str, lesson_base: Path | None = None) -> Path | None:
    """A `sources:` list mixes two bases, so resolution has to try both.

    Content and the lesson's own Articles are **lesson-relative**; books and
    assignment briefs are **course-relative**. A single-base resolver silently
    drops every `Books/` entry into `missing`, and a hash computed over a subset
    is a hash that says "unchanged" while a chapter is being re-read.
    """
    rel, _ = split_entry(entry)
    for root in ([lesson_base] if lesson_base else []) + [base]:
        if root is None:
            continue
        cand = Path(root) / rel
        if cand.is_file():
            return cand
    return None


def sources_hash(base: Path | str, sources: list[str],
                 lesson_base: Path | str | None = None) -> dict:
    base = Path(base)
    lesson_base = Path(lesson_base) if lesson_base else None
    per_file, missing = [], []
    outer = hashlib.sha256()
    for entry in sorted(sources):
        p = resolve_entry(base, entry, lesson_base)
        if p is None:
            missing.append(entry)
            continue
        digest = file_digest(p)
        per_file.append({'entry': entry, 'sha256': digest})
        outer.update(entry.encode('utf-8'))
        outer.update(b'\x00')
        outer.update(digest.encode('ascii'))
        outer.update(b'\x00')
    return {'sources_hash': outer.hexdigest()[:32], 'per_file': per_file,
            'missing': missing, 'complete': not missing}


def sources_stat(base: Path | str, sources: list[str],
                 lesson_base: Path | str | None = None) -> dict:
    """{path, size, mtime} per source. mtime to the minute: iCloud does not
    preserve sub-second times across devices, and a spurious difference would
    make C declare every lesson stale on a second machine."""
    base = Path(base)
    rows, missing = [], []
    lesson_base = Path(lesson_base) if lesson_base else None
    for entry in sources:
        rel, _ = split_entry(entry)
        p = resolve_entry(base, entry, lesson_base)
        if p is None:
            missing.append(entry)
            continue
        st = p.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        rows.append({'path': rel, 'size': st.st_size,
                     'mtime': mtime.strftime('%Y-%m-%dT%H:%M')})
    return {'sources_stat': rows, 'missing': missing}


def compare_stat(base: Path | str, recorded: list[dict],
                 lesson_base: Path | str | None = None) -> dict:
    """C's freshness check. File names are matched ignoring the course-code token,
    so a course-code rename never forces a re-run.

    `sources_stat` rows are written by `sources_stat()`, which resolves through
    `resolve_entry` and records each path relative to **whichever base resolved
    it**: `Content/...` against the lesson, `Books/...` against the course. So
    this has to try both bases in the same order, or every lesson citing a book
    reports that book as `gone` and its freshness gate fails for good.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from naming import strip_code_token  # noqa: E402

    base = Path(base)
    lesson_base = Path(lesson_base) if lesson_base else None
    roots = ([lesson_base] if lesson_base else []) + [base]
    changed, gone, unknown = [], [], []
    for row in recorded:
        rel = row.get('path')
        p = next((r / rel for r in roots if (r / rel).is_file()), None)
        if p is None:
            stem = strip_code_token(Path(rel).name)
            for r in roots:
                d = r / Path(rel).parent
                if not d.is_dir():
                    continue
                matches = [q for q in d.glob('*')
                           if q.is_file() and strip_code_token(q.name) == stem]
                if len(matches) == 1:
                    p = matches[0]
                    break
            if p is None:
                gone.append(rel)
                continue
        st = p.stat()
        if st.st_size == 0 and getattr(st, 'st_blocks', 1) == 0:
            unknown.append(rel)  # offloaded: freshness unknown, never "unchanged"
            continue
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)\
            .strftime('%Y-%m-%dT%H:%M')
        if st.st_size != row.get('size') or mtime != row.get('mtime'):
            changed.append({'path': rel, 'was': {'size': row.get('size'),
                                                 'mtime': row.get('mtime')},
                            'now': {'size': st.st_size, 'mtime': mtime}})
    return {'changed': changed, 'gone': gone, 'freshness_unknown': unknown,
            'fresh': not changed and not gone}


def pdf_signature(path: Path | str, lo: int | None = None,
                  hi: int | None = None) -> dict | None:
    """Page count, and highlight-type annotations inside the cited page range.

    Returns None when pypdf is unavailable or the file will not parse, and the
    caller then keeps whatever verdict it already had. Never guesses.
    """
    try:
        import pypdf
    except Exception:
        return None
    try:
        reader = pypdf.PdfReader(str(path))
        pages = len(reader.pages)
        lo = 1 if lo is None else max(1, lo)
        hi = pages if hi is None else min(pages, hi)
        n = 0
        for i in range(lo, hi + 1):
            for ref in (reader.pages[i - 1].get('/Annots') or []):
                try:
                    obj = ref.get_object()
                except Exception:
                    continue
                if obj.get('/Subtype') in ('/Highlight', '/Underline',
                                           '/StrikeOut', '/Squiggly'):
                    n += 1
        return {'pages': pages, 'highlights': n, 'range': [lo, hi]}
    except Exception:
        return None


def absolve_annotation_changes(stat: dict, sources: list, base: Path | str,
                               lesson_base: Path | str | None,
                               recorded_highlights) -> dict:
    """Move a highlighted textbook out of `changed` when the lesson's own cited
    pages are untouched.

    The student highlights the book as they study, which rewrites its bytes and
    makes size+mtime report it changed for every lesson that cites it, forever.
    What a lesson actually reads is its cited page range, and B records the
    in-range highlight count as `highlights:`. So when the page count and that
    count both still hold, the change is annotation work in other chapters and
    this lesson is not stale.

    Deliberately narrow: it applies only when the lesson cites exactly one
    ranged PDF, because `highlights:` is a single number and could not be
    attributed if there were two.
    """
    changed = list(stat.get('changed') or [])
    if not changed or recorded_highlights is None:
        return stat
    ranged = []
    for entry in sources:
        rel, frag = split_entry(str(entry))
        if Path(rel).suffix.lower() != '.pdf' or not frag:
            continue
        m = re.fullmatch(r'\s*(\d+)\s*-\s*(\d+)\s*', str(frag))
        if m:
            ranged.append((rel, int(m.group(1)), int(m.group(2))))
    if len(ranged) != 1:
        return stat
    rel, lo, hi = ranged[0]
    roots = ([Path(lesson_base)] if lesson_base else []) + [Path(base)]
    path = next((r / rel for r in roots if (r / rel).is_file()), None)
    kept, absolved = [], []
    for row in changed:
        if row.get('path') != rel or path is None:
            kept.append(row)
            continue
        sig = pdf_signature(path, lo, hi)
        if sig is None:
            kept.append({**row, 'note': 'pypdf unavailable: not assessed'})
        elif sig['highlights'] == int(recorded_highlights):
            absolved.append({**row, 'cited_range': [lo, hi],
                             'pages': sig['pages'],
                             'highlights': sig['highlights'],
                             'why': 'the bytes changed, but the cited pages still '
                                    'carry the recorded highlight count: the '
                                    'annotation work was in other chapters'})
        else:
            kept.append({**row, 'cited_range': [lo, hi],
                         'highlights_recorded': int(recorded_highlights),
                         'highlights_now': sig['highlights']})
    out = dict(stat)
    out['changed'] = kept
    out['annotations_elsewhere'] = absolved
    out['fresh'] = not kept and not out.get('gone')
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('hash', 'stat'):
        p = sub.add_parser(name)
        p.add_argument('--base', required=True, help='the course root')
        p.add_argument('--lesson-base',
                       help='the lesson folder; Content/ and the lesson Articles/ '
                            'resolve against it first')
        p.add_argument('--sources', nargs='+', required=True)
    p = sub.add_parser('compare')
    p.add_argument('--base', required=True)
    p.add_argument('--recorded', required=True, help='JSON file or inline JSON list')
    args = ap.parse_args(argv)
    if args.cmd == 'hash':
        out = sources_hash(args.base, args.sources, args.lesson_base)
    elif args.cmd == 'stat':
        out = sources_stat(args.base, args.sources, args.lesson_base)
    else:
        raw = args.recorded
        recorded = json.loads(Path(raw).read_text()) if Path(raw).is_file() \
            else json.loads(raw)
        out = compare_stat(args.base, recorded)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
