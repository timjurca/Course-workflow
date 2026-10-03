#!/usr/bin/env python3
"""The presence evidence table, `folder-structure.md` §8.

One predicate, and it lives in `shared/` because two skills ask the question.
Skill B gates a run on it (`expects`, and the cohort check); skill A uses it to
propose what a course should declare in `expects` in the first place.

It asks `classify.py` for every kind. It used to test file *names* for lowercase
prefixes for three of the eight tokens while asking the classifier for a fourth
— two predicates inside the one function whose whole purpose is that there is
only one. Every capitalised file in the vault (`Notes_03.pdf`, `Transcript_1.md`)
was invisible as a result: the student's own notes were never ingested anywhere,
and a course declaring `notes` or `transcript` failed pre-flight with the file
sitting in front of it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import classify                                                    # noqa: E402
import overview as ov                                              # noqa: E402

TOKENS = ('slides', 'transcript', 'book', 'notes', 'handouts', 'articles',
          'videos', 'links')

# Per-lesson staples: a lesson either has these or is missing something. The
# other four are sporadic — reading assigned in lecture N is filed under lesson
# N+1, so the lesson that assigns it looks as though it is missing articles.
STAPLES = ('slides', 'transcript', 'notes', 'book')

LINK_RE = re.compile(r'https?://\S+')


def _subdir(folder: Path, name: str) -> Path | None:
    for p in folder.iterdir():
        if p.is_dir() and p.name.lower() == name.lower():
            return p
    return None


def _has_link(path: Path) -> bool:
    try:
        return bool(LINK_RE.search(path.read_text(encoding='utf-8',
                                                  errors='replace')))
    except OSError:
        return False


def present(course: Path, key: str, folder: Path, content: Path,
            data: dict) -> dict:
    files = [p for p in content.iterdir()
             if p.is_file() and not classify.is_ignored(p)]
    kinds = {}
    for p in files:
        try:
            kinds[p.name] = classify.classify(p, peek=True).get('kind')
        except Exception:
            kinds[p.name] = None
    articles = _subdir(folder, 'Articles')
    reading = ov.resolve_reading(data, key)
    videos = [p for p in files if p.name.lower() in ('videos.md', 'video.md')]
    links = [p for p in files if re.match(r'^links_.*\.md$', p.name, re.I)]
    return {
        'slides': any(k == 'slides' for k in kinds.values()),
        'transcript': any(k == 'transcript' for k in kinds.values()),
        'book': reading.get('status') == 'resolved',
        'notes': any(k == 'notes' and n.lower() != 'notes_corrections.md'
                     for n, k in kinds.items()),
        # A lecturer's spreadsheet classifies as `workbook`: priority 1, prefix
        # H, and no token of its own in the closed vocabulary. Excluding it
        # would make a lecturer's workbook impossible to declare or gate on.
        'handouts': any(k in ('handout', 'workbook') for k in kinds.values()),
        'articles': bool(articles and any(p.is_file() for p in articles.iterdir())),
        'videos': any(_has_link(p) for p in videos),
        'links': any(_has_link(p) for p in links),
    }


def across_lessons(course: Path, data: dict, skip: str | None = None) -> dict:
    """Presence per lesson/tutorial key, for the cohort check and for `expects`."""
    out = {}
    for kind in ('Lessons', 'Tutorials'):
        root = Path(course) / kind
        if not root.is_dir():
            continue
        pre = 'L' if kind == 'Lessons' else 'T'
        for folder in sorted(root.iterdir()):
            content = folder / 'Content'
            if not folder.is_dir() or not content.is_dir():
                continue
            key = pre + folder.name.split('_')[0]
            if skip and key == skip:
                continue
            try:
                out[key] = present(Path(course), key, folder, content, data)
            except Exception:
                continue
    return out
