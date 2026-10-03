#!/usr/bin/env python3
"""Detect iCloud placeholders and conflicted copies. stat only, never a read.

Two silent-data-loss modes, described in folder-structure.md section 10:

  evicted    reading the file returns empty content, so a whole source vanishes
             from the notes while coverage still reports 100%
  conflicted writes are landing in a branch nobody will open again

Detection is deliberately a pattern *set* rather than one literal, because the
exact form depends on the filesystem and the macOS version. Nothing here opens a
file: opening an evicted file is what triggers the download this plugin must
never trigger on its own.

CLI:
    icloud.py check --paths <p> [<p> ...]
    icloud.py scan --root <dir> [--exclude <glob> ...]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# "name (Matjaz's conflicted copy 2026-03-12).ext", Obsidian's "name (conflict).md",
# and the plain " 2" suffix iCloud adds when it cannot merge.
# Unambiguous: nothing legitimate is named this way.
CONFLICT_PATTERNS = [
    re.compile(r'\(.*conflicted copy.*\)', re.IGNORECASE),
    re.compile(r'\(conflict(ed)?\)', re.IGNORECASE),
    re.compile(r'\bconflicted[ _-]copy\b', re.IGNORECASE),
    re.compile(r'\s\d{4}-\d{2}-\d{2}\s+\d{1,2}-\d{2}-\d{2}$'),  # Obsidian sync style
]

# Ambiguous on its own: iCloud appends " 2" when it cannot merge, but "Chapter 5.pdf"
# and "Lecture 3.pptx" are ordinary names and there are far more of those. A bare
# trailing digit is therefore treated as a conflict **only when the un-suffixed
# sibling is actually there**, which is the real signature of a duplicate.
#
# The asymmetry decides it: a false conflict hard-fails the notes skill's
# pre-flight and blocks that lesson until someone works out why, while a missed
# one shows up as a second copy the student can see in Finder.
SUFFIX_RE = re.compile(r'^(?P<base>.+?)\s(?P<n>[2-9])$')

PLACEHOLDER_SUFFIX = '.icloud'


def is_placeholder(path: Path | str) -> dict:
    """Three signals, any of which means the bytes are not on this machine."""
    p = Path(path)
    signals = []
    sidecar = p.with_name('.' + p.name + PLACEHOLDER_SUFFIX)
    if sidecar.exists():
        signals.append('sidecar')
    if p.name.startswith('.') and p.name.endswith(PLACEHOLDER_SUFFIX):
        signals.append('is_sidecar')
    try:
        st = p.stat()
    except OSError as e:
        return {'path': str(p), 'placeholder': True, 'signals': ['unstatable'],
                'error': str(e)}
    blocks = getattr(st, 'st_blocks', None)
    if st.st_size > 0 and blocks == 0:
        signals.append('dataless')
    if st.st_size == 0 and p.suffix.lower() in {'.pdf', '.pptx', '.docx', '.epub',
                                                '.png', '.jpg', '.jpeg'}:
        # A zero-byte binary source is never legitimate.
        signals.append('zero_byte_binary')
    return {'path': str(p), 'placeholder': bool(signals), 'signals': signals,
            'size': st.st_size, 'blocks': blocks}


def looks_conflicted(name: str, directory: Path | str | None = None) -> bool:
    stem = Path(name).stem
    if any(pat.search(stem) for pat in CONFLICT_PATTERNS):
        return True
    m = SUFFIX_RE.match(stem)
    if m and directory is not None:
        sibling = Path(directory) / (m.group('base') + Path(name).suffix)
        return sibling.exists()
    return False


def original_of(name: str, directory: Path | str | None = None) -> str | None:
    """The name a conflicted copy was made from, when it can be derived."""
    p = Path(name)
    stem = p.stem
    for pat in CONFLICT_PATTERNS:
        new = pat.sub('', stem).strip()
        if new and new != stem:
            return new + p.suffix
    m = SUFFIX_RE.match(stem)
    if m and directory is not None:
        sibling = Path(directory) / (m.group('base') + p.suffix)
        if sibling.exists():
            return sibling.name
    return None


def scan(root: Path | str, exclude: list[str] | None = None,
         recursive: bool = True) -> dict:
    root = Path(root)
    exclude = exclude or []
    placeholders, conflicts, errors = [], [], []
    if not root.exists():
        return {'root': str(root), 'exists': False, 'placeholders': [],
                'conflicts': [], 'errors': []}
    it = root.rglob('*') if recursive else root.glob('*')
    for p in it:
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if any(rel.match(g) for g in exclude):
            continue
        if p.is_dir():
            continue
        try:
            info = is_placeholder(p)
        except OSError as e:
            errors.append({'path': str(rel), 'error': str(e)})
            continue
        if info['placeholder']:
            placeholders.append({'path': str(rel), 'signals': info['signals']})
        if looks_conflicted(p.name, p.parent):
            conflicts.append({'path': str(rel),
                              'original': original_of(p.name, p.parent)})
    return {'root': str(root), 'exists': True, 'placeholders': placeholders,
            'conflicts': conflicts, 'errors': errors,
            'clean': not placeholders and not conflicts}


def check(paths: list[str]) -> dict:
    placeholders, conflicts, missing = [], [], []
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            missing.append(str(p))
            continue
        info = is_placeholder(p)
        if info['placeholder']:
            placeholders.append({'path': str(p), 'signals': info['signals']})
        if looks_conflicted(p.name, p.parent):
            conflicts.append({'path': str(p),
                              'original': original_of(p.name, p.parent)})
    return {'placeholders': placeholders, 'conflicts': conflicts,
            'missing': missing,
            'clean': not placeholders and not conflicts and not missing}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('check'); p.add_argument('--paths', nargs='+', required=True)
    p = sub.add_parser('scan')
    p.add_argument('--root', required=True)
    p.add_argument('--exclude', nargs='*', default=[])
    p.add_argument('--flat', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'check':
        out = check(args.paths)
    else:
        out = scan(args.root, args.exclude, recursive=not args.flat)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
