#!/usr/bin/env python3
"""Both tables of contents, built from the headings that were actually written.

Two artefacts, one builder, because two builders drift and nothing detects it:
the collapsed `Contents` callout inside a lesson's notes, and the course-level
`Table_of_contents.md`.

**The in-file TOC is generated last, from the file on disk**, never from the
plan. A TOC built from the outline lists a section the writer merged away, and
the link resolves to nothing. Reading back the H2 headings that exist makes that
impossible rather than unlikely.

**The course TOC is an upsert, never an append.** Only the bytes between this
lesson's own `<!-- toc:L03:start -->` and `<!-- toc:L03:end -->` are touched,
which is what makes a file owned by skill A safe for this skill to write into.
Appending was the first design and it was wrong three ways: re-running a lesson
duplicated its block, a regenerated lesson left its old section list behind, and
a term seen in a second lesson got a second row instead of an updated one. The
term index is therefore rebuilt **wholesale** from `terms.json` every run.

Blocks are inserted in lesson-number order, so processing lesson 9 before lesson
3 still lands lesson 3 above it.

A missing `Table_of_contents.md` is created here rather than stopping the run,
and the bytes are the ones pinned in `shared/note-invariants.md` §12 — skill A's
skeleton, frontmatter stamp included. Two skills each writing their own idea of
a "minimal" file is how it ends up with duplicate sections and no version stamp.

CLI:
    build_toc.py infile --notes <Final_notes/X.md> [--apply]
    build_toc.py init --course <c> [--apply]
    build_toc.py upsert --course <c> --key L03 --code ECON \\
        [--notes <path>] [--overview <path>] [--apply]
    build_toc.py terms --course <c> --code ECON [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import pathlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import terms as terms_mod                                          # noqa: E402
from vault import read_frontmatter                                 # noqa: E402

TOC_NAME = 'Table_of_contents.md'
H2_RE = re.compile(r'^##\s+(?!#)(.+?)\s*$', re.MULTILINE)
# note-invariants §13: zones are H2, concept and case sections are H3 inside
# them. Obsidian anchors match any heading level, so links are unaffected.
HEAD_RE = re.compile(r'^(?P<h>#{2,3})\s+(?!#)(?P<t>.+?)\s*$', re.MULTILINE)
CALLOUT_RE = re.compile(r'^> \[!summary\]- Contents\n(?:^>.*\n)*',
                        re.MULTILINE)
TERMS_START = '<!-- toc:terms:start -->'
TERMS_END = '<!-- toc:terms:end -->'

# Containers, not content: listing them makes the TOC longer without making it
# more useful, and `My additions` is the student's, not an index entry.
SKIP_HEADINGS = {'definitions', 'uncovered material', 'my additions',
                 'my notes', 'my questions', 'contents'}

# note-invariants §12, verbatim. Not reconstructed from memory anywhere.
SKELETON = """---
scaffolded_by: course-setup v1
---

# {course} - Table of contents

## Lessons

## Tutorials

## Term index
<!-- toc:terms:start -->
<!-- toc:terms:end -->
"""


def _atomic(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)
    return str(path)


def sections(text: str) -> list[dict]:
    """Every zone (H2) and section (H3), in document order."""
    out = []
    for m in HEAD_RE.finditer(_strip_code(text)):
        t = m.group('t').strip()
        if t.lower() in SKIP_HEADINGS:
            continue
        out.append({'level': len(m.group('h')), 'title': t})
    return out


def headings(text: str) -> list[str]:
    """The linkable sections: H3s where the document uses zones, else H2s.

    A zone heading (`## Concepts`) is not worth a link from the course table of
    contents; the concepts inside it are.
    """
    secs = sections(text)
    if any(s['level'] == 3 for s in secs):
        return [s['title'] for s in secs if s['level'] == 3]
    return [s['title'] for s in secs]


def _strip_code(text: str) -> str:
    """Fenced blocks can contain lines starting with `## `; a template quoted in
    the notes would otherwise appear in the TOC as a section."""
    return re.sub(r'^(?:```|~~~).*?^(?:```|~~~)\s*$', '', text,
                  flags=re.MULTILINE | re.DOTALL)


# --------------------------------------------------------------- in-file TOC

def infile(notes: Path | str, apply_it: bool = False) -> dict:
    notes = Path(notes)
    text = notes.read_text(encoding='utf-8', errors='replace')
    secs = sections(text)
    nested = any(s['level'] == 3 for s in secs)
    lines = []
    for sec in secs:
        indent = '  ' if nested and sec['level'] == 3 else ''
        lines.append(f"> {indent}- [[#{sec['title']}]]\n")
    heads = headings(text)
    block = '> [!summary]- Contents\n' + ''.join(lines)
    if CALLOUT_RE.search(text):
        new = CALLOUT_RE.sub(lambda _: block, text, count=1)
    else:
        new = _insert_before_definitions(text, block)
    if apply_it and new != text:
        _atomic(notes, new)
    return {'notes': str(notes), 'headings': heads, 'count': len(heads),
            'changed': new != text, 'applied': apply_it}


def _insert_before_definitions(text: str, block: str) -> str:
    """After the warning banner, before `## Definitions` (§13.1)."""
    m = re.search(r'^##\s+Definitions\s*$', text, re.MULTILINE)
    if m:
        return text[:m.start()] + block + '\n' + text[m.start():]
    m = H2_RE.search(text)
    if m:
        return text[:m.start()] + block + '\n' + text[m.start():]
    return text.rstrip('\n') + '\n\n' + block


# -------------------------------------------------------------- course TOC

def toc_path(course: Path | str) -> Path:
    return Path(course) / TOC_NAME


def init(course: Path | str, apply_it: bool = False) -> dict:
    course = Path(course)
    path = toc_path(course)
    if path.is_file():
        return {'path': str(path), 'created': False}
    try:
        fm, _ = read_frontmatter(course / 'Weekly_overview.md')
        name = fm.get('course') or course.name
    except Exception:
        name = course.name
    text = SKELETON.format(course=name)
    if apply_it:
        _atomic(path, text)
    return {'path': str(path), 'created': True, 'applied': apply_it,
            'course': name}


def _block(key: str, code: str, title: str, date: str, heads: list[str],
           covers: str | None) -> str:
    notes = f'{code}_{key}_Final_notes'
    num = key[1:]
    head = f'### [[{notes}|{num} - {title}]] · {date}'
    if covers:
        head += f' · covers [[{code}_{covers}_Final_notes|{covers}]]'
    lines = [f'<!-- toc:{key}:start -->', head]
    lines += [f'- [[{notes}#{h}|{h}]]' for h in heads]
    lines.append(f'<!-- toc:{key}:end -->')
    return '\n'.join(lines)


def upsert(course: Path | str, key: str, code: str,
           notes: Path | str | None = None,
           overview: Path | str | None = None,
           apply_it: bool = False) -> dict:
    course = Path(course)
    path = toc_path(course)
    created = init(course, apply_it)
    text = path.read_text(encoding='utf-8', errors='replace') if path.is_file() \
        else SKELETON.format(course=course.name)

    meta = _meta(notes, overview)
    heads = meta['headings']
    rebuilt_from_overview = meta['from'] == 'overview'
    block = _block(key, code, meta['title'], meta['date'], heads,
                   meta.get('covers'))

    section = 'Lessons' if key.startswith('L') else 'Tutorials'
    new, how = _splice(text, section, key, block)
    if apply_it:
        _atomic(path, new)
    return {'path': str(path), 'key': key, 'headings': len(heads),
            'action': how, 'created_toc': created.get('created'),
            'rebuilt_from_overview': rebuilt_from_overview,
            'changed': new != text, 'applied': apply_it}


def _meta(notes, overview) -> dict:
    """Prefer the notes; fall back to the overview when the block has to be
    rebuilt for a lesson whose markers were damaged (§13.2)."""
    if notes and Path(notes).is_file():
        fm, body = read_frontmatter(Path(notes))
        return {'title': fm.get('title') or '', 'date': str(fm.get('date') or ''),
                'headings': headings(body), 'from': 'notes',
                'covers': fm.get('covers')}
    if overview and Path(overview).is_file():
        fm, body = read_frontmatter(Path(overview))
        heads = []
        m = re.search(r'^##\s+Topics covered\s*$(.*?)(?=^##\s|\Z)', body,
                      re.MULTILINE | re.DOTALL)
        if m:
            heads = [ln.lstrip('- ').strip() for ln in m.group(1).splitlines()
                     if ln.strip().startswith('-')]
        return {'title': fm.get('title') or '', 'date': str(fm.get('date') or ''),
                'headings': heads, 'from': 'overview',
                'covers': fm.get('covers')}
    return {'title': '', 'date': '', 'headings': [], 'from': 'nothing'}


def _splice(text: str, section: str, key: str, block: str) -> tuple[str, str]:
    start = f'<!-- toc:{key}:start -->'
    end = f'<!-- toc:{key}:end -->'
    pat = re.compile(re.escape(start) + r'.*?' + re.escape(end), re.DOTALL)
    if pat.search(text):
        return pat.sub(lambda _: block, text, count=1), 'replaced'

    lines = text.splitlines()
    try:
        head = next(i for i, ln in enumerate(lines)
                    if ln.strip() == f'## {section}')
    except StopIteration:
        # The section heading is missing: append it rather than dropping the
        # block into whatever happens to be last.
        lines += ['', f'## {section}', '', *block.splitlines()]
        return '\n'.join(lines) + '\n', 'section created'

    # Blocks are ordered by number, so an out-of-order run still lands right.
    insert_at = len(lines)
    for i in range(head + 1, len(lines)):
        if lines[i].startswith('## '):
            insert_at = i
            break
        m = re.match(r'<!-- toc:([LT])(\d+):start -->', lines[i].strip())
        if m and m.group(2) > key[1:]:
            insert_at = i
            break
    else:
        insert_at = len(lines)
    chunk = block.splitlines() + ['']
    lines[insert_at:insert_at] = chunk
    return '\n'.join(lines).rstrip('\n') + '\n', 'inserted'


# -------------------------------------------------------------- term index

def term_index(course: Path | str, code: str, apply_it: bool = False) -> dict:
    course = Path(course)
    path = toc_path(course)
    init(course, apply_it)
    text = path.read_text(encoding='utf-8', errors='replace') if path.is_file() \
        else SKELETON.format(course=course.name)
    rows = terms_mod.index_rows(course, code)['rows']
    body = [TERMS_START]
    if rows:
        body += ['| Term | Defined in | Also appears in |', '|---|---|---|']
        for r in rows:
            body.append(f"| {r['term']} | {r['link']} | "
                        f"{', '.join(r['also'])} |")
    body.append(TERMS_END)
    block = '\n'.join(body)
    pat = re.compile(re.escape(TERMS_START) + r'.*?' + re.escape(TERMS_END),
                     re.DOTALL)
    if pat.search(text):
        new = pat.sub(lambda _: block, text, count=1)
    else:
        new = text.rstrip('\n') + '\n\n## Term index\n' + block + '\n'
    if apply_it:
        _atomic(path, new)
    return {'path': str(path), 'terms': len(rows), 'changed': new != text,
            'applied': apply_it}


GOALS_NAME = 'Learning_objectives.md'
GOALS_START = '<!-- goals:slides:start -->'
GOALS_END = '<!-- goals:slides:end -->'



GOALS_HEADING = '## From the lecture slides'


def _strip_own_heading(body: str) -> str:
    """Drop a leading copy of the heading this function supplies itself.

    This is a marker-pair upsert, so the obvious way to call it is to read the
    existing block off disk and feed it back as `--body`. That produced the
    heading twice, because the caller's body already contained the one this
    function adds. An upsert that is not idempotent under its own output is a
    trap, so the duplicate is removed here rather than documented away.
    """
    stripped = body.lstrip()
    if stripped.startswith(GOALS_HEADING):
        return stripped[len(GOALS_HEADING):].lstrip('\n')
    return body


def goals(course: Path | str, body: str, apply_it: bool = False) -> dict:
    """Upsert the slide-borne course-level goals into A's Learning_objectives.md.

    The ~50 level-1/2/3 goals are identical in every lecture that shows them, so
    repeating them in all thirteen lesson notes is ~900 duplicated words each and
    a thirteen-file edit whenever they change. They belong once, at course level.

    They do **not** belong in a new file: `Learning_objectives.md` already exists
    and already holds the official catalogue objectives, and a second goals file
    at course root is the rival-index problem this plugin avoids elsewhere. So B
    writes between its own markers inside A's file, exactly as it does for the
    lesson blocks in `Table_of_contents.md` (note-invariants §13).
    """
    path = Path(course) / GOALS_NAME
    body = _strip_own_heading(body)
    block = f'{GOALS_START}\n\n## From the lecture slides\n\n{body.strip()}\n\n{GOALS_END}'
    if path.is_file():
        text = path.read_text(encoding='utf-8', errors='replace')
    else:
        text = '# Learning objectives\n'
    if GOALS_START in text and GOALS_END in text:
        a = text.index(GOALS_START)
        b = text.index(GOALS_END) + len(GOALS_END)
        new_text = text[:a] + block + text[b:]
        action = 'replaced'
    else:
        new_text = text.rstrip('\n') + '\n\n' + block + '\n'
        action = 'inserted'
    if apply_it and new_text != text:
        _atomic(path, new_text)
    return {'path': str(path), 'action': action,
            'changed': new_text != text, 'applied': apply_it}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('infile')
    p.add_argument('--notes', required=True); p.add_argument('--apply', action='store_true')
    p = sub.add_parser('init')
    p.add_argument('--course', required=True); p.add_argument('--apply', action='store_true')
    p = sub.add_parser('upsert')
    p.add_argument('--course', required=True); p.add_argument('--key', required=True)
    p.add_argument('--code', required=True); p.add_argument('--notes')
    p.add_argument('--overview'); p.add_argument('--apply', action='store_true')
    g = sub.add_parser('goals')
    g.add_argument('--course', required=True)
    g.add_argument('--body', required=True,
                   help='markdown, or @file. This command supplies the '
                        '"## From the lecture slides" heading itself; a '
                        'leading copy in the body is dropped, so feeding '
                        'the existing block back in is safe.')
    g.add_argument('--apply', action='store_true')
    p = sub.add_parser('terms')
    p.add_argument('--course', required=True); p.add_argument('--code', required=True)
    p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)

    if args.cmd == 'infile':
        out = infile(args.notes, args.apply)
    elif args.cmd == 'init':
        out = init(args.course, args.apply)
    elif args.cmd == 'upsert':
        out = upsert(args.course, args.key, args.code, args.notes,
                     args.overview, args.apply)
    elif args.cmd == 'goals':
        body = args.body
        if body.startswith('@'):
            body = pathlib.Path(body[1:]).read_text(encoding='utf-8')
        out = goals(args.course, body, args.apply)
    else:
        out = term_index(args.course, args.code, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
