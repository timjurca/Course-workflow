#!/usr/bin/env python3
"""The PDF annotation layer: highlights as salience, sticky notes as `C` items.

A highlight is not a source. It is the student saying "this passage, in this
authoritative source, matters" — a stronger signal than a note written later
from memory — so the highlighted text keeps the priority of its host. `B15.2`
stays priority 1; it does not drop to priority 3 because someone marked it.

**Why the snapping matters more than the extraction.** A highlight annotation
stores quad points, not text, so the underlying text has to be pulled from the
rectangles. Raw quad extraction is reliably ragged: partial words at the edges
("diffusion,"), mis-ordered text in two-column layouts, spans broken across a
page boundary. Handing that to the writer produces a quote that is not what the
book says, attributed to the book. So every span is snapped outward to whole
sentences on the page, and the raw text is kept beside it so the snapping itself
stays auditable.

**Span decides treatment** (§5.2), and the script classifies rather than
decides: up to 2 sentences is a verbatim `==mark==` with an exact wording
guarantee; 3 to 8 is concept-level coverage with one mark on the load-bearing
sentence; longer is a salient *region*, a `> [!tip] Heavily marked` callout and
no verbatim reproduction at all. A paragraph-long highlight reproduced verbatim
is a copy of the textbook sitting in the student's notes.

The over-marking ratio is reported because §5.3's selection rubric only applies
when a large share of a chapter is marked, and "large share" should be a number
somebody can see rather than an impression.

Colours carry no meaning (D45) and are recorded only so a re-run is comparable.

CLI:
    extract_annotations.py extract --path <book.pdf> [--pages 5-18] \\
        [--host-prefix B --map '{"15.1": [5,7], "15.2": [8,10]}'] \\
        [--json-out <file>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import extract_pdf                                                 # noqa: E402

HIGHLIGHT_TYPES = {'/Highlight', '/Underline', '/Squiggly', '/StrikeOut'}
NOTE_TYPES = {'/Text', '/FreeText', '/Popup', '/Caret', '/Ink', '/Square',
              '/Circle', '/Polygon', '/PolyLine'}
SENT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z(“"])')
PAD = 1.0                       # quad points sit flush against the glyphs


def _sentences(text: str) -> list[str]:
    text = re.sub(r'\s+', ' ', text or '').strip()
    return [s.strip() for s in SENT_RE.split(text) if s.strip()]


def _snap(raw: str, page_text: str) -> dict:
    """Grow a ragged quad span outward to whole sentences of the page.

    Matching is on a normalised core of the fragment, because the ragged edges
    are exactly the characters that will not match.
    """
    sents = _sentences(page_text)
    core = re.sub(r'\s+', ' ', raw or '').strip().strip('.,;:()"“”')
    if not core or not sents:
        return {'snapped': raw, 'sentences': 0, 'exact': False}
    words = core.split()
    probe = ' '.join(words[:6]) if len(words) >= 6 else core
    hits = [i for i, s in enumerate(sents) if probe.lower() in s.lower()]
    if not hits and len(words) > 3:
        probe = ' '.join(words[1:5])
        hits = [i for i, s in enumerate(sents) if probe.lower() in s.lower()]
    if not hits:
        return {'snapped': core, 'sentences': len(_sentences(core)),
                'exact': False}
    start = hits[0]
    end = start
    tail = ' '.join(words[-5:]).lower() if len(words) >= 5 else core.lower()
    for i in range(start, len(sents)):
        if tail in sents[i].lower():
            end = i
            break
    else:
        end = start
    snapped = ' '.join(sents[start:end + 1])
    return {'snapped': snapped, 'sentences': end - start + 1, 'exact': True}


def span_class(sentences: int) -> str:
    if sentences <= 2:
        return 'short'
    if sentences <= 8:
        return 'medium'
    return 'long'


def _host_id(page: int, prefix: str, mapping: dict) -> str | None:
    """Which book section a page falls in. Without a map there is no host and
    the caller attaches the highlight itself."""
    for sid, rng in (mapping or {}).items():
        try:
            lo, hi = int(rng[0]), int(rng[1])
        except (TypeError, ValueError, IndexError):
            continue
        if lo <= page <= hi:
            return f'{prefix}{sid}'
    return None


def _annots(reader, page_index: int):
    try:
        raw = reader.pages[page_index].get('/Annots')
    except Exception:
        return []
    if not raw:
        return []
    try:
        raw = raw.get_object()
    except Exception:
        pass
    out = []
    for ref in raw:
        try:
            out.append(ref.get_object())
        except Exception:
            continue
    return out


def extract(path: Path | str, pages: str | None = None, host_prefix: str = 'B',
            mapping: dict | None = None) -> dict:
    import pdfplumber                                    # noqa: E402
    from pypdf import PdfReader                          # noqa: E402

    path = Path(path)
    reader = PdfReader(str(path))
    highlights, notes, errors = [], [], []
    marked_chars = total_chars = 0

    with pdfplumber.open(str(path)) as pdf:
        total = len(pdf.pages)
        wanted = extract_pdf.parse_pages(pages, total)
        for n in wanted:
            if n > len(reader.pages):
                continue
            plp = pdf.pages[n - 1]
            height = plp.height
            page_text = plp.extract_text() or ''
            total_chars += len(page_text)
            for a in _annots(reader, n - 1):
                sub = str(a.get('/Subtype') or '')
                contents = str(a.get('/Contents') or '').strip()
                if sub in HIGHLIGHT_TYPES:
                    try:
                        raw = _quad_text(a, plp, height)
                    except Exception as e:
                        errors.append({'page': n, 'error': str(e)})
                        continue
                    snap = _snap(raw, page_text)
                    marked_chars += len(snap['snapped'])
                    row = {'page': n, 'subtype': sub.lstrip('/'),
                           'raw': raw, 'text': snap['snapped'],
                           'sentences': snap['sentences'],
                           'snapped': snap['exact'],
                           'span': span_class(snap['sentences']),
                           'colour': _colour(a),
                           'host': _host_id(n, host_prefix, mapping)}
                    if row['host']:
                        row['id'] = row['host'] + '!'
                    if contents:
                        # A comment attached to a highlight is a C item in its
                        # own right: the student wrote it, it is not the book.
                        notes.append({'page': n, 'subtype': 'HighlightComment',
                                      'text': contents, 'on': row.get('id')})
                    highlights.append(row)
                elif sub in NOTE_TYPES and contents:
                    notes.append({'page': n, 'subtype': sub.lstrip('/'),
                                  'text': contents, 'on': None})

    for i, note in enumerate(notes, 1):
        note['id'] = f'C{i:02d}'

    ratio = round(marked_chars / total_chars, 3) if total_chars else 0.0
    return {
        'path': str(path), 'pages': pages or 'all',
        'highlights': highlights, 'annotations': notes, 'errors': errors,
        'counts': {'highlights': len(highlights), 'annotations': len(notes),
                   'short': sum(1 for h in highlights if h['span'] == 'short'),
                   'medium': sum(1 for h in highlights if h['span'] == 'medium'),
                   'long': sum(1 for h in highlights if h['span'] == 'long'),
                   'unsnapped': sum(1 for h in highlights if not h['snapped'])},
        'marked_ratio': ratio,
        'over_highlighted': ratio > 0.25,
        'rubric_note': ('over a quarter of the text in range is marked; apply the '
                        '§5.3 selection rubric and log every down-weighted '
                        'highlight in D_verification.md') if ratio > 0.25 else None,
    }


def _quad_text(annot, page, height: float) -> str:
    quads = [float(v) for v in (annot.get('/QuadPoints') or [])]
    if not quads:
        rect = [float(v) for v in (annot.get('/Rect') or [])]
        if len(rect) != 4:
            return ''
        bbox = (rect[0] - PAD, height - rect[3] - PAD,
                rect[2] + PAD, height - rect[1] + PAD)
        return (page.crop(bbox, strict=False).extract_text() or '').strip()
    parts = []
    for k in range(0, len(quads) - 7, 8):
        xs = quads[k:k + 8:2]
        ys = quads[k + 1:k + 8:2]
        # QuadPoints are PDF user space, origin bottom-left; pdfplumber's crop
        # is top-left. Flipping is not optional and gets no text if forgotten.
        bbox = (min(xs) - PAD, height - max(ys) - PAD,
                max(xs) + PAD, height - min(ys) + PAD)
        try:
            parts.append((page.crop(bbox, strict=False).extract_text() or '')
                         .replace('\n', ' ').strip())
        except Exception:
            continue
    return re.sub(r'\s+', ' ', ' '.join(p for p in parts if p)).strip()


def _colour(annot) -> str | None:
    try:
        c = [round(float(v), 2) for v in (annot.get('/C') or [])]
        return ','.join(str(x) for x in c) if c else None
    except Exception:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('extract')
    p.add_argument('--path', required=True)
    p.add_argument('--pages')
    p.add_argument('--host-prefix', default='B')
    p.add_argument('--map', help='JSON {section_id: [first_page, last_page]}')
    p.add_argument('--json-out')
    args = ap.parse_args(argv)

    mapping = json.loads(args.map) if args.map else None
    out = extract(args.path, args.pages, args.host_prefix, mapping)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
