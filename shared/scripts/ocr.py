#!/usr/bin/env python3
"""OCR with explicit uncertainty. Used by B and C for scanned pages and slide images.

The design rule: **an uncertain reading is flagged, never cleaned up.** A formula
that OCR half-read and the model then "tidied" is confidently wrong and
undetectable at revision time, which is worse than a visible `[S22, OCR, verify]`
marker the student can check in ten seconds.

So this module returns, per block: the text, a confidence, and whether it needs
human or vision verification. It never rewrites what it read.

Vision fallback: when `--vision-fallback` is set and confidence is low, the block
is written out as a PNG and listed under `needs_vision`. The calling skill looks
at that image itself; no model call happens inside this script.

CLI:
    ocr.py image --path <p> [--lang eng+slv] [--out <dir>]
    ocr.py pdf --path <p> --pages 12-14 [--out <dir>]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_LANG = 'eng'
LOW_CONF = 70          # tesseract word confidence below this is "uncertain"
FORMULA_HINT = re.compile(r'[=∑∫√±≤≥·×÷^_]|\\frac|\\sum|\\int')


def have_tesseract() -> bool:
    return shutil.which('tesseract') is not None


def _tsv(image: Path, lang: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / 'out'
        subprocess.run(['tesseract', str(image), str(base), '-l', lang, 'tsv'],
                       check=True, capture_output=True)
        rows = []
        for line in (base.with_suffix('.tsv')).read_text(encoding='utf-8').splitlines()[1:]:
            parts = line.split('\t')
            if len(parts) < 12:
                continue
            try:
                conf = float(parts[10])
            except ValueError:
                continue
            word = parts[11].strip()
            if not word:
                continue
            # tesseract TSV gives left, top, width, height; store x0,y0,x1,y1
            left, top, w, h = (int(parts[6]), int(parts[7]),
                               int(parts[8]), int(parts[9]))
            rows.append({'block': int(parts[2]), 'line': int(parts[4]),
                         'conf': conf, 'text': word,
                         'bbox': [left, top, left + w, top + h]})
        return rows


def ocr_image(path: Path | str, lang: str = DEFAULT_LANG) -> dict:
    path = Path(path)
    if not have_tesseract():
        return {'path': str(path), 'error': 'tesseract not installed',
                'lines': [], 'needs_vision': [str(path)]}
    try:
        words = _tsv(path, lang)
    except subprocess.CalledProcessError as e:
        return {'path': str(path), 'error': e.stderr.decode('utf-8', 'replace')[:400],
                'lines': [], 'needs_vision': [str(path)]}
    lines: dict[tuple, list] = {}
    for w in words:
        lines.setdefault((w['block'], w['line']), []).append(w)
    out_lines = []
    for key in sorted(lines):
        ws = lines[key]
        txt = ' '.join(w['text'] for w in ws)
        conf = round(sum(w['conf'] for w in ws) / len(ws), 1)
        uncertain = conf < LOW_CONF
        formula = bool(FORMULA_HINT.search(txt))
        out_lines.append({
            'text': txt, 'confidence': conf,
            'uncertain': uncertain,
            'looks_like_formula': formula,
            # A formula is flagged whatever the confidence: OCR reads "F > 1.0"
            # for "F > 10" at high confidence, and that error is invisible.
            'flag': 'verify' if (uncertain or formula) else None,
            'bbox': [min(w['bbox'][0] for w in ws), min(w['bbox'][1] for w in ws),
                     max(w['bbox'][2] for w in ws), max(w['bbox'][3] for w in ws)],
        })
    flagged = [l for l in out_lines if l['flag']]
    return {'path': str(path), 'error': None, 'lines': out_lines,
            'text': '\n'.join(l['text'] for l in out_lines),
            'flagged': len(flagged),
            'needs_vision': [str(path)] if len(flagged) > max(1, len(out_lines) // 3) else [],
            'lang': lang}


def ocr_pdf_pages(path: Path | str, pages: str, out_dir: Path | str | None = None,
                  lang: str = DEFAULT_LANG, dpi: int = 250) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pdfplumber
    from extract_pdf import parse_pages  # noqa: E402

    out_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp())
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    with pdfplumber.open(str(path)) as pdf:
        for n in parse_pages(pages, len(pdf.pages)):
            img = out_dir / f'ocr_p{n:04d}.png'
            pdf.pages[n - 1].to_image(resolution=dpi).original.save(img)
            r = ocr_image(img, lang)
            r['page'] = n
            results.append(r)
    return {'path': str(path), 'pages': results,
            'needs_vision': [p for r in results for p in r.get('needs_vision', [])]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('image')
    p.add_argument('--path', required=True); p.add_argument('--lang', default=DEFAULT_LANG)
    p = sub.add_parser('pdf')
    p.add_argument('--path', required=True); p.add_argument('--pages', required=True)
    p.add_argument('--out'); p.add_argument('--lang', default=DEFAULT_LANG)
    p = sub.add_parser('check')
    args = ap.parse_args(argv)
    if args.cmd == 'check':
        out = {'tesseract': have_tesseract()}
    elif args.cmd == 'image':
        out = ocr_image(args.path, args.lang)
    else:
        out = ocr_pdf_pages(args.path, args.pages, args.out, args.lang)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
