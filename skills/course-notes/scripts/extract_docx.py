#!/usr/bin/env python3
"""DOCX to Pass A items, with the comment layer read as `C` items.

Two things here are not obvious and both are load-bearing.

**Comments are a source, not metadata.** A margin comment in a chapter the
lecturer distributed as .docx is the student's own annotation, priority 3, ID
prefix `C`, and it carries a coverage guarantee exactly like a sticky note in a
PDF. `python-docx` has no API for them, so the comment part is read straight out
of the package zip. Dropping them would lose the student's own thinking while
reporting complete coverage of the file.

**Granularity depends on what the file is.** A book chapter's atom is a
*section*, because that is what the book index numbers and what a marker like
`[B15.2]` means; a handout's atom is a *block*, because a handout has no section
numbering to borrow. Passing `--sections` selects the first, its absence the
second. Guessing between them produces IDs that no marker in the notes will ever
match, and Pass D cannot tell that from a genuine coverage gap.

Tables are reproduced as Markdown, structurally. A table summarised into prose
is a table the student cannot check a number against.

CLI:
    extract_docx.py extract --path <f.docx> --entry Content/handout_x.docx \\
        --prefix H --work <.work> --run <ts> --hash <h> [--apply]
    extract_docx.py extract --path <ch.docx> --prefix B \\
        --sections 15.1,15.2,15.3 ...
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import extraction                                                  # noqa: E402

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
COMMENT_PARTS = ('word/comments.xml', 'word/commentsExtended.xml')
KEYBOX_RE = re.compile(r'^\s*(definition|theorem|proposition|lemma|corollary|'
                       r'key (concept|idea|point)|box)\b', re.I)
REVIEW_RE = re.compile(r'\b(review questions?|exercises?|problems?|'
                       r'end[- ]of[- ]chapter|summary)\b', re.I)


def _item_id(prefix: str, n: int) -> str:
    """`A2` + 4 -> `A2.4`; `H` + 4 -> `H04`.

    A prefix ending in a digit already identifies one source among several (the
    second article), so its items are subdivisions of it. A bare letter numbers
    its items directly.
    """
    return f'{prefix}.{n}' if prefix[-1].isdigit() else f'{prefix}{n:02d}'


def _table_markdown(table) -> str:
    rows = [[c.text.replace('\n', ' ').strip() for c in r.cells] for r in table.rows]
    if not rows:
        return ''
    out = ['| ' + ' | '.join(rows[0]) + ' |', '|' + '---|' * len(rows[0])]
    out += ['| ' + ' | '.join(r) + ' |' for r in rows[1:]]
    return '\n'.join(out)


def read_comments(path: Path) -> list[dict]:
    """The comment layer, straight out of the package. Never fatal: a document
    with no comment part is the normal case, not an error."""
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            if COMMENT_PARTS[0] not in z.namelist():
                return out
            root = ET.fromstring(z.read(COMMENT_PARTS[0]))
    except (OSError, zipfile.BadZipFile, ET.ParseError):
        return out
    for c in root.findall(f'{W}comment'):
        text = ' '.join(t.text or '' for t in c.iter(f'{W}t')).strip()
        if text:
            out.append({'author': c.get(f'{W}author') or '',
                        'date': c.get(f'{W}date') or '', 'text': text})
    return out


def _blocks(doc):
    """Paragraphs and tables in document order.

    `doc.paragraphs` and `doc.tables` are two separate lists, so iterating them
    in turn silently moves every table to the end of the chapter.
    """
    from docx.table import Table                        # noqa: E402
    from docx.text.paragraph import Paragraph           # noqa: E402
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == f'{W}p':
            yield Paragraph(child, doc)
        elif child.tag == f'{W}tbl':
            yield Table(child, doc)


def extract(path: Path | str, entry: str, prefix: str,
            sections: list[str] | None = None) -> dict:
    import docx                                          # noqa: E402

    path = Path(path)
    doc = docx.Document(str(path))
    items: list[dict] = []
    letter = prefix[0]

    if sections:
        items = _by_section(doc, letter, sections)
    else:
        n = 0
        for block in _blocks(doc):
            if hasattr(block, 'rows'):
                md = _table_markdown(block)
                if md:
                    n += 1
                    items.append({'id': _item_id(prefix, n), 'tags': [],
                                  'text': 'Table:\n' + md})
                continue
            text = (block.text or '').strip()
            if not text:
                continue
            n += 1
            tags = []
            if KEYBOX_RE.match(text):
                tags.append('key_box')
            elif REVIEW_RE.search(text) and len(text) < 120:
                tags.append('review_item')
            items.append({'id': _item_id(prefix, n), 'tags': tags, 'text': text})

    comments = read_comments(path)
    for i, c in enumerate(comments, 1):
        items.append({'id': f'C{i:02d}', 'tags': [],
                      'text': c['text'] + (f"  ({c['author']})" if c['author'] else '')})

    return {'path': str(path), 'entry': entry, 'items': items,
            'comments': len(comments), 'sectioned': bool(sections),
            'chunks': _chunk_boundaries(items)}


def _by_section(doc, letter: str, sections: list[str]) -> list[dict]:
    """One item per book section, in the order the index lists them.

    Headings are matched to the supplied section list positionally, because a
    chapter's headings rarely repeat their own numbers in the text. A section
    that never opens (fewer headings than ids) is still emitted, empty and
    flagged, rather than dropped: a missing ID is an uncoverable gap.
    """
    from docx.table import Table                         # noqa: E402
    bodies: dict[str, list[str]] = {s: [] for s in sections}
    titles: dict[str, str] = {}
    idx, current = -1, None
    for block in _blocks(doc):
        if isinstance(block, Table):
            md = _table_markdown(block)
            if md and current:
                bodies[current].append('Table:\n' + md)
            continue
        style = (getattr(block.style, 'name', '') or '')
        text = (block.text or '').strip()
        if not text:
            continue
        if style.lower().startswith('heading') and idx + 1 < len(sections):
            idx += 1
            current = sections[idx]
            titles[current] = text
            continue
        if current:
            bodies[current].append(text)

    out = []
    for s in sections:
        body = '\n\n'.join(bodies[s]).strip()
        title = titles.get(s, '')
        tags = ['key_box'] if KEYBOX_RE.match(title or body[:60]) else []
        if REVIEW_RE.search(title):
            tags = ['review_item']
        out.append({'id': f'{letter}{s}', 'tags': tags,
                    'text': (f'{title}\n\n{body}' if title else body) or
                            f'(section {s} produced no text from this file; '
                            'check the chapter range and the heading styles)'})
    return out


def _chunk_boundaries(items: list[dict], limit: int = 8000) -> list[str]:
    out, words = [], 0
    for item in items:
        n = len(item['text'].split())
        if words and words + n > limit:
            out.append(item['id'])
            words = 0
        words += n
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('extract')
    p.add_argument('--path', required=True)
    p.add_argument('--entry', required=True)
    p.add_argument('--prefix', required=True,
                   help='ID stem: H, N, A2, B ...')
    p.add_argument('--sections', help='comma-separated book section ids; '
                                      'switches granularity to one item per section')
    p.add_argument('--kind', default='handout')
    p.add_argument('--work'); p.add_argument('--run', default='')
    p.add_argument('--hash', default=''); p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)

    sections = [s.strip() for s in args.sections.split(',')] if args.sections else None
    out = extract(args.path, args.entry, args.prefix, sections)
    if args.work:
        out['written'] = extraction.write(args.work, args.entry, args.run,
                                          args.hash, args.kind, out['items'],
                                          out['chunks'], apply_it=args.apply)
    out['item_count'] = len(out['items'])
    out['ids'] = [i['id'] for i in out['items']][:20]
    del out['items']
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
