#!/usr/bin/env python3
"""PDF text, outlines and page ranges. Used by A (book index), B and C (sources), E (rung 3).

Everything here is deterministic. Nothing here decides what a passage *means*;
that is model work in whichever skill called it.

Two properties the callers depend on:

  * **A PDF with no text layer is reported, never silently returned empty.** An
    empty extraction that looks like a thin source is the exact failure this
    plugin exists to prevent, so `text()` says `text_layer: false` and the
    caller routes the file to ocr.py.
  * **Page ranges are 1-based and inclusive**, matching how a book's index and a
    Weekly_overview `Chapters` cell read.

CLI:
    extract_pdf.py text --path <p> [--pages 495-503] [--json]
    extract_pdf.py outline --path <p>
    extract_pdf.py info --path <p>
    extract_pdf.py images --path <p> --out <dir> [--pages 1-10]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

RANGE_RE = re.compile(r'^(\d+)\s*-\s*(\d+)$')


def parse_pages(spec: str | None, total: int) -> list[int]:
    if not spec:
        return list(range(1, total + 1))
    pages: list[int] = []
    for part in spec.split(','):
        part = part.strip()
        m = RANGE_RE.match(part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            pages.extend(range(min(a, b), min(max(a, b), total) + 1))
        elif part.isdigit():
            pages.append(int(part))
    return [p for p in sorted(set(pages)) if 1 <= p <= total]


def _open(path):
    import pdfplumber
    return pdfplumber.open(str(path))


def info(path: Path | str) -> dict:
    out = {'path': str(path), 'pages': None, 'encrypted': False, 'metadata': {},
           'text_layer': None, 'error': None}
    try:
        with _open(path) as pdf:
            out['pages'] = len(pdf.pages)
            out['metadata'] = {k: str(v) for k, v in (pdf.metadata or {}).items()}
            sample = range(0, len(pdf.pages), max(1, len(pdf.pages) // 5))
            chars = sum(len((pdf.pages[i].extract_text() or '').strip())
                        for i in list(sample)[:5])
            out['text_layer'] = chars > 200
            first = pdf.pages[0]
            out['landscape'] = first.width > first.height
            out['page_size'] = [round(first.width), round(first.height)]
    except Exception as e:
        out['error'] = str(e)
    return out


def text(path: Path | str, pages: str | None = None) -> dict:
    out = {'path': str(path), 'pages': [], 'text_layer': True, 'error': None,
           'empty_pages': []}
    try:
        with _open(path) as pdf:
            total = len(pdf.pages)
            wanted = parse_pages(pages, total)
            for n in wanted:
                t = pdf.pages[n - 1].extract_text() or ''
                if not t.strip():
                    out['empty_pages'].append(n)
                out['pages'].append({'page': n, 'text': t})
            # A OneNote or print-to-PDF export often attaches the *whole*
            # text layer to every printed page while only the visuals differ.
            # Extracting each page then triples every item downstream and
            # inflates coverage with nothing. Collapse identical runs.
            seen, kept, repeats = {}, [], []
            for p in out['pages']:
                h = hashlib.sha256(p['text'].encode('utf-8')).hexdigest()
                if h in seen and p['text'].strip():
                    repeats.append({'page': p['page'], 'same_as': seen[h]})
                    continue
                seen[h] = p['page']
                kept.append(p)
            if repeats:
                out['pages'] = kept
                out['repeated_pages'] = repeats
                out['note'] = (f'{len(repeats)} page(s) repeat an earlier page\'s '
                               'text layer verbatim and were extracted once. The '
                               'visual content of those pages may still differ, so '
                               'read the file if figures matter.')
            got = sum(len(p['text'].strip()) for p in out['pages'])
            out['text_layer'] = got > 50 * max(1, len(wanted) // 10)
    except Exception as e:
        out['error'] = str(e)
        out['text_layer'] = False
    if not out['text_layer'] and not out['error']:
        out['note'] = ('no usable text layer: route this file to ocr.py rather than '
                       'treating the empty result as a thin source')
    return out


def outline(path: Path | str) -> dict:
    """The embedded outline, flattened, with 1-based start pages.

    Many textbooks have none. The caller falls back to the printed table of
    contents, and failing that asks the student for the chapter-to-page mapping;
    it never guesses a structure.
    """
    rows, err = [], None
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))

        def walk(items, depth=0):
            for it in items:
                if isinstance(it, list):
                    walk(it, depth + 1)
                    continue
                try:
                    page = reader.get_destination_page_number(it) + 1
                except Exception:
                    page = None
                rows.append({'title': str(it.title).strip(), 'page': page,
                             'depth': depth})
        walk(reader.outline)
    except Exception as e:
        err = str(e)
    # Close each entry's range at the next entry of the same or shallower depth.
    for i, row in enumerate(rows):
        end = None
        for j in range(i + 1, len(rows)):
            if rows[j]['depth'] <= row['depth'] and rows[j]['page']:
                end = rows[j]['page'] - 1 if rows[j]['page'] > row['page'] else row['page']
                break
        row['end_page'] = end
    return {'path': str(path), 'entries': rows, 'has_outline': bool(rows),
            'error': err}


def find_toc_pages(path: Path | str, limit: int = 25) -> dict:
    """Candidate printed-TOC pages, for the fallback when there is no outline."""
    hits = []
    try:
        with _open(path) as pdf:
            for n in range(1, min(limit, len(pdf.pages)) + 1):
                t = (pdf.pages[n - 1].extract_text() or '')
                low = t.lower()
                if re.search(r'\b(contents|table of contents|kazalo|vsebina)\b', low):
                    hits.append(n)
                elif len(re.findall(r'\.{3,}\s*\d+\s*$', t, re.MULTILINE)) >= 4:
                    hits.append(n)
    except Exception as e:
        return {'candidates': [], 'error': str(e)}
    return {'candidates': hits, 'error': None}


def images(path: Path | str, out_dir: Path | str, pages: str | None = None,
           min_px: int = 120) -> dict:
    """Page images for figures and for the OCR fallback. Tiny images are skipped:
    they are rules, bullets and logos, never the figure a slide is about."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written, err = [], None
    try:
        with _open(path) as pdf:
            total = len(pdf.pages)
            for n in parse_pages(pages, total):
                page = pdf.pages[n - 1]
                for i, im in enumerate(page.images):
                    w = abs(im['x1'] - im['x0'])
                    h = abs(im['top'] - im['bottom'])
                    if w < min_px or h < min_px:
                        continue
                    try:
                        crop = page.crop((im['x0'], page.height - im['y1'],
                                          im['x1'], page.height - im['y0']))
                        pil = crop.to_image(resolution=200).original
                        dest = out_dir / f'p{n:04d}_{i}.png'
                        pil.save(dest)
                        written.append({'page': n, 'file': str(dest),
                                        'w': round(w), 'h': round(h)})
                    except Exception:
                        continue
    except Exception as e:
        err = str(e)
    return {'written': written, 'count': len(written), 'error': err}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('text'); p.add_argument('--path', required=True)
    p.add_argument('--pages'); p.add_argument('--plain', action='store_true')
    p = sub.add_parser('outline'); p.add_argument('--path', required=True)
    p = sub.add_parser('info'); p.add_argument('--path', required=True)
    p = sub.add_parser('toc-pages'); p.add_argument('--path', required=True)
    p = sub.add_parser('images')
    p.add_argument('--path', required=True); p.add_argument('--out', required=True)
    p.add_argument('--pages')
    args = ap.parse_args(argv)
    if args.cmd == 'text':
        out = text(args.path, args.pages)
        if args.plain:
            for pg in out['pages']:
                sys.stdout.write(f"\n=== page {pg['page']} ===\n{pg['text']}\n")
            return 0
    elif args.cmd == 'outline':
        out = outline(args.path)
    elif args.cmd == 'info':
        out = info(args.path)
    elif args.cmd == 'toc-pages':
        out = find_toc_pages(args.path)
    else:
        out = images(args.path, args.out, args.pages)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
