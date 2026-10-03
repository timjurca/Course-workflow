#!/usr/bin/env python3
"""Turn a syllabus or weekly plan into Weekly_overview rows. Parsed, shown, never written.

This is reading exception 1: the supplied file only, once, at init. The output is
printed back to the student in full and written only after confirmation, because
a malformed table silently becomes the schedule every later run depends on.

It handles the three shapes that actually turn up: a real table (Markdown, DOCX
or PDF), a list of "week N — date — topic" lines, and a bare list of topics with
no dates. The last one yields rows with no date, which is honest: a date invented
from a term start is a date every folder name will then be wrong about.

CLI:
    parse_syllabus.py parse --path <file> [--start-date 2026-02-19] [--weekly]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
import extract_pdf                                                  # noqa: E402

DATE_PATTERNS = [
    (re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b'), lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r'\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\b'), lambda m: date(int(m[3]), int(m[2]), int(m[1]))),
    (re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b'), lambda m: date(int(m[3]), int(m[1]), int(m[2]))),
]
# "Tutorial 2" numbers a tutorial, not a week, so the tutorial words belong here
# too; otherwise the row falls through to positional numbering and lands on the
# wrong number, which is the one cell a folder name is built from.
WEEK_RE = re.compile(
    r'\b(?:week|teden|lesson|lecture|predavanje|tutorial|vaje|vaja|seminar|lab)'
    r'\s*[:#]?\s*(\d{1,2})\b', re.IGNORECASE)
CHAPTER_RE = re.compile(r'\b(?:ch(?:apter)?s?\.?|pogl\.?)\s*([\d.]+(?:\s*[-–]\s*[\d.]+)?)',
                        re.IGNORECASE)
TUTORIAL_RE = re.compile(r'\b(tutorial|seminar|vaje|vaja|lab)\b', re.IGNORECASE)


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {'.md', '.txt', '.csv'}:
        return path.read_text(encoding='utf-8', errors='replace')
    if suffix == '.pdf':
        res = extract_pdf.text(path)
        if not res['text_layer']:
            raise RuntimeError('this PDF has no text layer; it needs OCR before parsing')
        return '\n'.join(p['text'] for p in res['pages'])
    if suffix == '.docx':
        from docx import Document
        doc = Document(str(path))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(' | '.join(c.text.strip() for c in row.cells))
        return '\n'.join(parts)
    raise RuntimeError(f'unsupported syllabus format: {suffix}. Convert it to PDF, '
                       'DOCX or Markdown first; nothing is guessed from an unknown '
                       'format.')


def find_date(text: str):
    for pat, build in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return build(m)
            except ValueError:
                continue
    return None


def parse(path: Path | str, start_date: str | None = None,
          weekly: bool = False) -> dict:
    path = Path(path)
    try:
        text = read_text(path)
    except Exception as e:
        return {'ok': False, 'error': str(e), 'rows': []}

    rows, unparsed = [], []
    for raw in text.splitlines():
        line = raw.strip().strip('|').strip()
        if not line or len(line) < 4:
            continue
        cells = [c.strip() for c in line.split('|')] if '|' in raw else [line]
        joined = ' '.join(cells)
        if set(joined) <= set('-: '):
            continue
        num_m = WEEK_RE.search(joined)
        d = find_date(joined)
        if not num_m and not d:
            unparsed.append(raw.strip())
            continue
        topic = None
        if len(cells) > 1:
            candidates = [c for c in cells
                          if c and not find_date(c) and not c.isdigit()
                          and not WEEK_RE.fullmatch(c or '')]
            topic = max(candidates, key=len) if candidates else None
        if not topic:
            topic = WEEK_RE.sub('', joined)
            for pat, _ in DATE_PATTERNS:
                topic = pat.sub('', topic)
            topic = topic.strip(' -–—:\t')
        ch = CHAPTER_RE.search(joined)
        rows.append({
            'Type': 'tutorial' if TUTORIAL_RE.search(joined) else 'lesson',
            'No': f'{int(num_m.group(1)):02d}' if num_m else None,
            'Date': d.isoformat() if d else None,
            'Topic': topic or None,
            'Book': None,
            'Chapters': ch.group(1).replace(' ', '') if ch else None,
            'Lesson': None,
            'source_line': raw.strip(),
        })

    if weekly and start_date:
        base = datetime.strptime(start_date, '%Y-%m-%d').date()
        for i, r in enumerate(x for x in rows if x['Type'] == 'lesson'):
            if not r['Date']:
                r['Date'] = (base + timedelta(weeks=i)).isoformat()
                r['date_basis'] = 'derived from the weekly cadence, confirm it'

    # Positional numbering is per type: lessons and tutorials each run 01, 02, ...
    counters = {'lesson': 0, 'tutorial': 0}
    for r in rows:
        counters[r['Type']] += 1
        if not r['No']:
            r['No'] = f"{counters[r['Type']]:02d}"
            r['number_basis'] = 'position in the file, confirm it'

    missing_dates = [r['No'] for r in rows if not r['Date']]
    return {
        'ok': bool(rows), 'rows': rows, 'count': len(rows),
        'rows_without_date': missing_dates,
        'unparsed_lines': unparsed[:20],
        'unparsed_count': len(unparsed),
        'warning': ('some rows have no date. A folder is named NN_YYYY-MM-DD, so a '
                    'row with no date cannot produce one. Ask, or leave the row and '
                    'let the first filing supply the date.') if missing_dates else None,
        'note': 'print this table back in full and write it only after confirmation.',
    }


def to_markdown(rows: list[dict]) -> str:
    out = ['| Type     | No | Date       | Topic | Book | Chapters | Lesson |',
           '|----------|----|------------|-------|------|----------|--------|']
    for r in rows:
        out.append('| {Type} | {No} | {Date} | {Topic} | {Book} | {Chapters} | {Lesson} |'
                   .format(**{k: (r.get(k) or '') for k in
                              ('Type', 'No', 'Date', 'Topic', 'Book', 'Chapters', 'Lesson')}))
    return '\n'.join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('parse')
    p.add_argument('--path', required=True)
    p.add_argument('--start-date'); p.add_argument('--weekly', action='store_true')
    p.add_argument('--markdown', action='store_true')
    args = ap.parse_args(argv)
    out = parse(args.path, args.start_date, args.weekly)
    if args.markdown and out['rows']:
        out['markdown'] = to_markdown(out['rows'])
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
