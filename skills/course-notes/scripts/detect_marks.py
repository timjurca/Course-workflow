#!/usr/bin/env python3
"""Tier 1 highlight detection on scans: a saturation mask, aligned to OCR lines.

Some sources are paper. A book chapter photocopied and scanned carries the
student's marks as *pixels*, with no annotation layer to read, and those marks
are the same signal a PDF highlight is: the student saying this passage matters.
Without this pass, a scanned chapter loses every highlight silently and the
notes look complete.

The method is deliberately cheap and deliberately dumb. Coloured highlighter has
a saturation signature that printed text and paper do not: convert to HSV, keep
pixels that are saturated **and** bright (dark saturated pixels are ink, not
highlighter), group them into boxes, and intersect those boxes with the line
boxes tesseract reports. What comes back is text, not coordinates.

**It fails on purpose rather than quietly.** Three cases are detected and
reported instead of returning an empty result that reads as "nothing was
marked":

  * a greyscale or photocopied page — yellow highlighter photocopies as light
    grey, indistinguishable from paper texture, and tier 1 has no chance
  * a page with text but no mask hits — a candidate for the tier 2 vision pass,
    which is the only thing that catches pen underlines, margin brackets,
    circled terms and asterisks, none of which have a saturation signature
  * a page with no text layer at all

Precision is mediocre by design. Over-capture (a whole line when half was
marked) is preferred to a miss, so everything derived here carries
`[highlight, handwritten, verify]` in the notes and its span is listed in the
verification report.

CLI:
    detect_marks.py detect --path <scan.pdf> --pages 5-18 [--dpi 150]
                           [--saturation 55] [--value 120] [--lang eng]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import extract_pdf                                                 # noqa: E402

SAT_MIN = 55          # below this, paper and grey text
VAL_MIN = 120         # below this, ink: dark and saturated is a pen stroke
CELL = 8              # mask is grouped on an 8px grid; finer is noise
MIN_CELLS = 6         # a box smaller than this is a stray coloured glyph
VISION_CONFIRM_PAGES = 20


def _page_images(path: Path, pages: str | None, dpi: int):
    import pdfplumber                                    # noqa: E402
    with pdfplumber.open(str(path)) as pdf:
        for n in extract_pdf.parse_pages(pages, len(pdf.pages)):
            page = pdf.pages[n - 1]
            text = page.extract_text() or ''
            yield n, page.to_image(resolution=dpi).original.convert('RGB'), text


def _mask(img, sat_min: int, val_min: int):
    import numpy as np                                   # noqa: E402
    hsv = img.convert('HSV')
    arr = np.asarray(hsv, dtype='uint8')
    sat, val = arr[:, :, 1], arr[:, :, 2]
    return (sat >= sat_min) & (val >= val_min)


def _is_greyscale(img, sample: int = 40000) -> bool:
    import numpy as np                                   # noqa: E402
    arr = np.asarray(img.convert('HSV'), dtype='uint8')[:, :, 1]
    flat = arr.reshape(-1)
    if flat.size > sample:
        flat = flat[:: max(1, flat.size // sample)]
    # A colour page has a tail of saturated pixels; a photocopy does not.
    return float((flat >= 40).mean()) < 0.002


def _boxes(mask, cell: int = CELL, min_cells: int = MIN_CELLS) -> list[tuple]:
    """Connected groups of mask cells, as pixel boxes.

    The grid is what makes this cheap enough to run on a whole chapter: a
    per-pixel labelling of a 150 dpi page is two million nodes, and highlighter
    marks are centimetres wide.
    """
    import numpy as np                                   # noqa: E402
    h, w = mask.shape
    gh, gw = (h + cell - 1) // cell, (w + cell - 1) // cell
    grid = np.zeros((gh, gw), dtype=bool)
    for gy in range(gh):
        for gx in range(gw):
            block = mask[gy * cell:(gy + 1) * cell, gx * cell:(gx + 1) * cell]
            grid[gy, gx] = bool(block.any()) and block.mean() > 0.25

    seen = np.zeros_like(grid)
    out = []
    for y in range(gh):
        for x in range(gw):
            if not grid[y, x] or seen[y, x]:
                continue
            q, cells = deque([(y, x)]), []
            seen[y, x] = True
            while q:
                cy, cx = q.popleft()
                cells.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1),
                               (cy, cx + 1)):
                    if 0 <= ny < gh and 0 <= nx < gw and grid[ny, nx] \
                            and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            if len(cells) < min_cells:
                continue
            ys = [c[0] for c in cells]; xs = [c[1] for c in cells]
            out.append((min(xs) * cell, min(ys) * cell,
                        (max(xs) + 1) * cell, (max(ys) + 1) * cell))
    return out


def _lines(img, lang: str) -> list[dict]:
    try:
        import pytesseract                               # noqa: E402
    except ImportError:
        return []
    try:
        data = pytesseract.image_to_data(
            img, lang=lang, output_type=pytesseract.Output.DICT)
    except Exception:
        return []
    lines: dict[tuple, dict] = {}
    for i, text in enumerate(data['text']):
        text = (text or '').strip()
        if not text:
            continue
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        x, y = data['left'][i], data['top'][i]
        w, h = data['width'][i], data['height'][i]
        row = lines.setdefault(key, {'x0': x, 'y0': y, 'x1': x + w,
                                     'y1': y + h, 'words': []})
        row['x0'] = min(row['x0'], x); row['y0'] = min(row['y0'], y)
        row['x1'] = max(row['x1'], x + w); row['y1'] = max(row['y1'], y + h)
        row['words'].append(text)
    return [{'bbox': (r['x0'], r['y0'], r['x1'], r['y1']),
             'text': ' '.join(r['words'])} for r in lines.values()]


def _overlap(box, line, min_frac: float = 0.25) -> bool:
    bx0, by0, bx1, by1 = box
    lx0, ly0, lx1, ly1 = line
    ix = max(0, min(bx1, lx1) - max(bx0, lx0))
    iy = max(0, min(by1, ly1) - max(by0, ly0))
    area = max(1, (lx1 - lx0) * (ly1 - ly0))
    return (ix * iy) / area >= min_frac


def detect(path: Path | str, pages: str | None = None, dpi: int = 150,
           sat_min: int = SAT_MIN, val_min: int = VAL_MIN,
           lang: str = 'eng') -> dict:
    path = Path(path)
    results, needs_vision, greyscale = [], [], []
    for n, img, text in _page_images(path, pages, dpi):
        if _is_greyscale(img):
            greyscale.append(n)
            needs_vision.append(n)
            results.append({'page': n, 'greyscale': True, 'boxes': 0,
                            'marks': [],
                            'note': 'photocopy or greyscale scan: yellow '
                                    'highlighter is indistinguishable from paper '
                                    'texture here. Tier 1 cannot work; go '
                                    'straight to the vision pass.'})
            continue
        boxes = _boxes(_mask(img, sat_min, val_min))
        lines = _lines(img, lang)
        marks = []
        for box in boxes:
            hit = [ln['text'] for ln in lines if _overlap(box, ln['bbox'])]
            if hit:
                marks.append({'bbox': box, 'text': ' '.join(hit),
                              'lines': len(hit)})
        if not marks and text.strip():
            needs_vision.append(n)
        results.append({'page': n, 'greyscale': False, 'boxes': len(boxes),
                        'ocr_lines': len(lines), 'marks': marks,
                        'has_text_layer': bool(text.strip())})

    return {
        'path': str(path), 'pages': pages or 'all', 'dpi': dpi,
        'results': results,
        'marks': sum(len(r['marks']) for r in results),
        'greyscale_pages': greyscale,
        'needs_vision': needs_vision,
        'vision_confirm': len(needs_vision) > VISION_CONFIRM_PAGES,
        'flag': '[highlight, handwritten, verify]',
        'note': ('every span here is over-captured by design and carries '
                 '[highlight, handwritten, verify]; list each one with its span '
                 'in D_verification.md'),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('detect')
    p.add_argument('--path', required=True)
    p.add_argument('--pages')
    p.add_argument('--dpi', type=int, default=150)
    p.add_argument('--saturation', type=int, default=SAT_MIN)
    p.add_argument('--value', type=int, default=VAL_MIN)
    p.add_argument('--lang', default='eng')
    args = ap.parse_args(argv)
    out = detect(args.path, args.pages, args.dpi, args.saturation,
                 args.value, args.lang)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
