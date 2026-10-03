#!/usr/bin/env python3
"""EPUB to Pass A items, by spine order, with the highlight gap stated out loud.

**The thing a reader must be told once.** Apple Books and Kindle keep highlights
in their own databases, not in the file. A chapter the student marked heavily in
Books arrives here looking pristine, so an EPUB source silently loses the single
strongest salience signal this skill has. Saying so once, in the run report, is
the whole mitigation — there is no way to read those annotations — and it is
better than notes that quietly treat a marked chapter as unmarked.

`ebooklib` is the documented handler but is not installed in the current runtime
and is never installed without asking. So this reads the package directly when
it is absent: `META-INF/container.xml` names the OPF, the OPF's manifest and
spine give reading order, and `bs4` turns each document into text. The result is
the same shape either way, and which path ran is in the output, because an
unnoticed fallback is how two runs of the same file end up with different IDs.

Page ranges have no meaning in a reflowable book, so a `Chapters` cell resolves
to **section anchors**: ids are taken from the spine position or from a supplied
section list, exactly as in `extract_docx.py`.

CLI:
    extract_epub.py extract --path <book.epub> --entry "Books/x.epub#15.1-15.4" \\
        --prefix B [--sections 15.1,15.2] [--work <.work> --run <ts> --hash <h>] [--apply]
    extract_epub.py toc --path <book.epub>
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import extraction                                                  # noqa: E402

CONTAINER = 'META-INF/container.xml'
OPF_NS = '{http://www.idpf.org/2007/opf}'
CN_NS = '{urn:oasis:names:tc:opendocument:xmlns:container}'

HIGHLIGHT_WARNING = (
    'EPUB highlights are unreadable. Apple Books and Kindle store annotations '
    'in their own databases, not in the file, so if this book is marked there '
    'that signal is invisible to this skill. Stated once, then the run '
    'continues without it.')


def _documents(path: Path) -> list[dict]:
    """Spine order with hrefs resolved, via ebooklib when present, else the zip.

    Both paths return the same list so nothing downstream has to know which ran.
    """
    try:
        import ebooklib                                  # noqa: E402
        from ebooklib import epub                        # noqa: E402
        book = epub.read_epub(str(path))
        out = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            out.append({'name': item.get_name(),
                        'html': item.get_content().decode('utf-8', 'replace')})
        return out
    except ImportError:
        pass
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read(CONTAINER))
        rootfile = root.find(f'.//{CN_NS}rootfile')
        opf_path = rootfile.get('full-path')
        opf = ET.fromstring(z.read(opf_path))
        base = posixpath.dirname(opf_path)
        manifest = {}
        for item in opf.iter(f'{OPF_NS}item'):
            manifest[item.get('id')] = item.get('href')
        out = []
        for ref in opf.iter(f'{OPF_NS}itemref'):
            href = manifest.get(ref.get('idref'))
            if not href:
                continue
            full = posixpath.normpath(posixpath.join(base, href)) if base else href
            try:
                out.append({'name': full,
                            'html': z.read(full).decode('utf-8', 'replace')})
            except KeyError:
                continue
        return out


def _text_of(html: str) -> tuple[str, str]:
    from bs4 import BeautifulSoup                        # noqa: E402
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'nav']):
        tag.decompose()
    head = soup.find(['h1', 'h2', 'h3'])
    title = head.get_text(' ', strip=True) if head else ''
    text = re.sub(r'\n{3,}', '\n\n', soup.get_text('\n', strip=True))
    return title, text


def extract(path: Path | str, entry: str, prefix: str,
            sections: list[str] | None = None) -> dict:
    path = Path(path)
    docs = _documents(path)
    used_ebooklib = 'ebooklib' in sys.modules
    letter = prefix[0]
    items, toc = [], []

    parts = []
    for doc in docs:
        title, text = _text_of(doc['html'])
        if not text.strip():
            continue
        parts.append({'name': doc['name'], 'title': title, 'text': text})
        toc.append({'anchor': doc['name'], 'title': title,
                    'words': len(text.split())})

    if sections:
        # One item per named section, matched positionally to spine documents.
        for i, sid in enumerate(sections):
            part = parts[i] if i < len(parts) else None
            body = f"{part['title']}\n\n{part['text']}" if part else (
                f'(section {sid} has no matching document in the spine; check '
                'the chapter range against the book index)')
            items.append({'id': f'{letter}{sid}', 'tags': [], 'text': body})
    else:
        for i, part in enumerate(parts, 1):
            stem = f'{prefix}.{i}' if prefix[-1].isdigit() else f'{prefix}{i:02d}'
            items.append({'id': stem, 'tags': [],
                          'text': f"{part['title']}\n\n{part['text']}".strip()})

    return {'path': str(path), 'entry': entry, 'items': items, 'toc': toc,
            'handler': 'ebooklib' if used_ebooklib else 'stdlib zip + bs4',
            'documents': len(parts), 'highlight_warning': HIGHLIGHT_WARNING,
            'chunks': _chunk_boundaries(items)}


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
    p = sub.add_parser('toc'); p.add_argument('--path', required=True)
    p = sub.add_parser('extract')
    p.add_argument('--path', required=True); p.add_argument('--entry', required=True)
    p.add_argument('--prefix', default='B'); p.add_argument('--sections')
    p.add_argument('--work'); p.add_argument('--run', default='')
    p.add_argument('--hash', default=''); p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)

    if args.cmd == 'toc':
        out = {'path': args.path,
               'toc': extract(args.path, '', 'B')['toc'],
               'highlight_warning': HIGHLIGHT_WARNING}
    else:
        sections = [s.strip() for s in args.sections.split(',')] if args.sections else None
        out = extract(args.path, args.entry, args.prefix, sections)
        if args.work:
            out['written'] = extraction.write(args.work, args.entry, args.run,
                                              args.hash, 'book', out['items'],
                                              out['chunks'], apply_it=args.apply)
        out['item_count'] = len(out['items'])
        out['ids'] = [i['id'] for i in out['items']][:20]
        del out['items']
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
