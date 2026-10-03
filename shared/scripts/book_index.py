#!/usr/bin/env python3
"""Build and maintain Books/<Slug>.index.md. Skill A owns it entirely; B reads it.

Two layers, deliberately separate:

  structure    chapter and section numbers, titles, page ranges. Deterministic,
               from the PDF outline, falling back to the printed contents pages.
               **Written first**, so B's page-range resolution works immediately
               even if the run is interrupted.
  descriptions one paragraph per section, written by the model, saved as they go.

Descriptions are built **eagerly for the whole book**, because A infers a lesson's
chapters by matching its slides against these descriptions. Lazy descriptions make
that circular: you would need to know which sections a lesson cites in order to
write the descriptions that tell you which sections it cites.

A book is filed once per course, so the cost lands on day one and never again.
An interrupted build resumes from the last described section; it never restarts.

CLI:
    book_index.py structure --pdf <p> --out <index.md> --book "Title" [--apply]
    book_index.py status --index <index.md>
    book_index.py next --index <index.md> [--count 5]
    book_index.py describe --index <index.md> --id 15.1 --text "..."
    book_index.py resolve --index <index.md> --range 15.1-15.4
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vault import read_frontmatter, write_frontmatter  # noqa: E402
import extract_pdf  # noqa: E402

# "15.1 Motivation: ..." or "Chapter 15 Instrumental Variables"
# "15.1 Title", "15.1. Title", "Chapter 15: Title". The trailing dot or colon
# after the number is optional and is not part of the id.
NUMBERED_RE = re.compile(
    r'^\s*(?:chapter\s+|poglavje\s+)?(\d+(?:\.\d+)*)[.:]?\s+(.{2,120})$',
    re.IGNORECASE)
ROW_RE = re.compile(r'^\|\s*([0-9.]+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$')
# A serialised book: four columns, the third naming the file the section is in.
ROW_FILE_RE = re.compile(
    r'^\|\s*([0-9.]+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$')
CHAPTER_NUM_RE = re.compile(r'(?:chapter|ch|pogl)[ _-]*(\d+)', re.IGNORECASE)
DESC_HEAD_RE = re.compile(r'^##\s+([0-9.]+)\s*$', re.MULTILINE)


def _title_of(entry: str) -> tuple[str | None, str]:
    m = NUMBERED_RE.match(entry.strip())
    if m:
        return m.group(1), m.group(2).strip()
    return None, entry.strip()


def structure_from_folder(folder: Path | str) -> dict:
    """A book delivered one chapter at a time, as a folder of files.

    Common when the lecturer is writing the book as the course runs. The model
    still needs one book with one index, because that is what a Chapters cell
    resolves through and what gives the reader its `B` marker family; without it
    each chapter classifies as a handout and cites as `H`, indistinguishable from
    a worksheet.

    The difference from a single-file book is only *where* a section lives: a row
    carries a file as well as a page range, and page numbers restart at 1 in each
    file. Sub-sections are read from each chapter's own outline when it has one.
    """
    folder = Path(folder)
    rows, problems = [], []
    files = [p for p in sorted(folder.iterdir())
             if p.is_file() and not p.name.startswith('.')
             and p.suffix.lower() in {'.pdf', '.docx', '.epub', '.md'}]
    if not files:
        return {'source': None, 'sections': [], 'complete': False,
                'reason': f'no chapter files in {folder}'}
    for p in files:
        m = CHAPTER_NUM_RE.search(p.stem)
        if not m:
            problems.append(f'{p.name}: no chapter number in the file name')
            continue
        num = str(int(m.group(1)))
        pages = None
        title = p.stem
        if p.suffix.lower() == '.pdf':
            info = extract_pdf.info(p)
            if info.get('pages'):
                pages = (1, info['pages'])
            if not info.get('text_layer'):
                problems.append(f'{p.name}: no text layer, it will need OCR')
        # "Chapter_02" is a file name, not a title. Until the description pass
        # gives the chapter meaning, say plainly what it is.
        if re.fullmatch(r'(?:chapter|ch|pogl)[ _-]*\d+', p.stem, re.IGNORECASE):
            title = f'Chapter {num}'
        rows.append({'id': num, 'title': title, 'file': p.name,
                     'start': pages[0] if pages else None,
                     'end': pages[1] if pages else None})
        # sub-sections from this chapter's own outline, if it has one
        if p.suffix.lower() == '.pdf':
            out = extract_pdf.outline(p)
            for e in out['entries']:
                sub, sub_title = _title_of(e['title'])
                if sub is None or not sub.startswith(num + '.'):
                    continue
                rows.append({'id': sub, 'title': sub_title, 'file': p.name,
                             'start': e.get('page'), 'end': e.get('end_page')})
    rows.sort(key=lambda r: [int(x) for x in r['id'].split('.')])
    return {'source': 'chapter folder', 'sections': rows, 'complete': bool(rows),
            'serialised': True, 'problems': problems,
            'reason': None if rows else 'no chapter number could be read from any file'}


def structure_from_pdf(pdf: Path | str) -> dict:
    """Outline first, printed contents second, ask third. Never a guess."""
    out = extract_pdf.outline(pdf)
    rows = []
    for e in out['entries']:
        num, title = _title_of(e['title'])
        if num is None:
            continue
        rows.append({'id': num, 'title': title, 'start': e.get('page'),
                     'end': e.get('end_page')})
    if rows:
        return {'source': 'pdf outline', 'sections': rows, 'complete': True}

    toc = extract_pdf.find_toc_pages(pdf)
    if toc['candidates']:
        pages = ','.join(str(p) for p in toc['candidates'])
        text = extract_pdf.text(pdf, pages)
        for page in text['pages']:
            for line in page['text'].splitlines():
                line = re.sub(r'\.{2,}', ' ', line)
                m = re.match(r'^\s*(\d+(?:\.\d+)*)[.:]?\s+(.+?)\s+(\d{1,4})\s*$', line)
                if m:
                    rows.append({'id': m.group(1), 'title': m.group(2).strip(),
                                 'start': int(m.group(3)), 'end': None})
        if rows:
            rows.sort(key=lambda r: [int(x) for x in r['id'].split('.')])
            for i, r in enumerate(rows[:-1]):
                nxt = rows[i + 1]['start']
                r['end'] = max(r['start'], nxt - 1) if nxt else None
            return {'source': 'printed contents', 'sections': rows,
                    'complete': True}

    return {'source': None, 'sections': [], 'complete': False,
            'reason': ('no PDF outline and no findable contents page: ask the '
                       'student for the chapter-to-page mapping. Do not invent one.')}


def render_index(book: str, pdf_name: str, pages: int, struct: dict,
                 built: str, descriptions: str = 'partial') -> tuple[dict, str]:
    serialised = bool(struct.get('serialised'))
    fm = {'book': book,
          ('folder' if serialised else 'file'): pdf_name,
          'pages': pages,
          'structure_built': built, 'descriptions': descriptions,
          'structure_source': struct.get('source'),
          'scaffolded_by': 'course-setup v1'}
    if serialised:
        fm['serialised'] = True
        lines = [f'# {book} - index', '',
                 'A serialised book: one file per chapter, page numbers restart in '
                 'each. A section resolves to a file **and** a range.', '',
                 '| ID | Title | File | Pages |', '|---|---|---|---|']
    else:
        lines = [f'# {book} - index', '', '| ID | Title | Pages |', '|---|---|---|']
    for sec in struct['sections']:
        rng = ''
        if sec.get('start'):
            rng = (f"{sec['start']}-{sec['end']}" if sec.get('end')
                   else str(sec['start']))
        if serialised:
            lines.append(f"| {sec['id']} | {sec['title']} | {sec.get('file','')} | {rng} |")
        else:
            lines.append(f"| {sec['id']} | {sec['title']} | {rng} |")
    lines.append('')
    return fm, '\n'.join(lines) + '\n'


def load_index(index: Path | str) -> dict:
    path = Path(index)
    if not path.is_file():
        return {'exists': False, 'sections': [], 'described': set()}
    fm, body = read_frontmatter(path)
    serialised = bool(fm.get('serialised'))
    sections = []
    for line in body.splitlines():
        m = (ROW_FILE_RE if serialised else ROW_RE).match(line)
        if m and m.group(1)[0].isdigit():
            fname = m.group(3) if serialised else None
            rng = m.group(4) if serialised else m.group(3)
            start = end = None
            rm = re.match(r'^(\d+)(?:-(\d+))?$', rng)
            if rm:
                start = int(rm.group(1))
                end = int(rm.group(2)) if rm.group(2) else start
            sections.append({'id': m.group(1), 'title': m.group(2),
                             'file': fname, 'start': start, 'end': end})
    described = {m.group(1) for m in DESC_HEAD_RE.finditer(body)}
    return {'exists': True, 'frontmatter': fm, 'body': body,
            'sections': sections, 'described': described, 'path': str(path)}


def status(index: Path | str) -> dict:
    data = load_index(index)
    if not data['exists']:
        return {'exists': False}
    total = len(data['sections'])
    done = len([s for s in data['sections'] if s['id'] in data['described']])
    return {'exists': True, 'book': data['frontmatter'].get('book'),
            'sections': total, 'described': done,
            'remaining': total - done,
            'descriptions': data['frontmatter'].get('descriptions'),
            'complete': total > 0 and done == total}


def next_sections(index: Path | str, count: int = 5) -> dict:
    """What to describe next, with the page range to read. Resume, never restart."""
    data = load_index(index)
    todo = [s for s in data['sections'] if s['id'] not in data['described']]
    return {'next': todo[:count], 'remaining': len(todo),
            'pdf': data.get('frontmatter', {}).get('file')}


def add_description(index: Path | str, section_id: str, text: str) -> dict:
    """Append one description block and save immediately.

    Saved per section rather than per book: an interrupted build of an 878-page
    textbook must not lose an hour of work.
    """
    path = Path(index)
    fm, body = read_frontmatter(path)
    if re.search(rf'^##\s+{re.escape(section_id)}\s*$', body, re.MULTILINE):
        return {'written': False, 'reason': 'already described'}
    body = body.rstrip('\n') + f'\n\n## {section_id}\n{text.strip()}\n'
    total = len(load_index(path)['sections'])
    described = len(DESC_HEAD_RE.findall(body))
    fm['descriptions'] = 'complete' if described >= total > 0 else 'partial'
    write_frontmatter(path, fm, body)
    return {'written': True, 'described': described, 'of': total,
            'descriptions': fm['descriptions']}


def resolve_range(index: Path | str, spec: str) -> dict:
    """A Weekly_overview Chapters cell to a page range. B's pre-flight check 6.

    `15.1-15.4` covers every section from 15.1 through 15.4 inclusive; `15`
    covers the whole chapter, subsections included.
    """
    data = load_index(index)
    if not data['exists']:
        return {'resolved': False, 'reason': 'no index for this book'}

    def key(sid):
        return [int(x) for x in sid.split('.')]

    # A Chapters cell is whatever the lecturer wrote: "15.1-15.4", "2", or a
    # comma-separated mix like "2, 3.1-3.2". Each part is resolved and the parts
    # are unioned, because a lecturer assigning a chapter plus two sections of
    # the next one is entirely normal and a resolver that only understands one
    # range silently returns nothing for it.
    wanted, unresolved = [], []
    for part in [x.strip() for x in str(spec).split(',') if x.strip()]:
        m = re.match(r'^([\d.]+)\s*-\s*([\d.]+)$', part)
        hits = []
        if m:
            lo, hi = key(m.group(1)), key(m.group(2))
            for sec in data['sections']:
                k = key(sec['id'])
                if lo <= k[:len(lo)] and k[:len(hi)] <= hi:
                    hits.append(sec)
        elif re.match(r'^[\d.]+$', part):
            pref = key(part)
            hits = [sec for sec in data['sections'] if key(sec['id'])[:len(pref)] == pref]
        else:
            unresolved.append(part)
            continue
        if not hits:
            unresolved.append(part)
        for h in hits:
            if h not in wanted:
                wanted.append(h)
    if not wanted:
        return {'resolved': False, 'reason': f'no section matches "{spec}"',
                'sections': [], 'unresolved_parts': unresolved}
    if data['frontmatter'].get('serialised'):
        # Page numbers restart in every file, so one merged range would be a lie.
        by_file = {}
        for sec in wanted:
            if not sec.get('file'):
                continue
            rng = by_file.setdefault(sec['file'], [])
            if sec.get('start'):
                rng.append(sec['start'])
            if sec.get('end'):
                rng.append(sec['end'])
        if not by_file:
            return {'resolved': False, 'sections': wanted,
                    'reason': 'sections found but no file named for any of them'}
        folder = data['frontmatter'].get('folder')
        return {'resolved': True, 'serialised': True, 'sections': wanted,
                'unresolved_parts': unresolved,
                'files': [{'file': f, 'path': f'{folder}/{f}' if folder else f,
                           'pages': (f'{min(r)}-{max(r)}' if r else None)}
                          for f, r in by_file.items()],
                'undescribed': [s['id'] for s in wanted
                                if s['id'] not in data['described']]}
    pages = [s['start'] for s in wanted if s['start']] + \
            [s['end'] for s in wanted if s['end']]
    if not pages:
        return {'resolved': False, 'reason': 'sections found but no page ranges '
                '(scanned book, titles only)', 'sections': wanted}
    return {'resolved': True, 'sections': wanted, 'unresolved_parts': unresolved,
            'pages': f'{min(pages)}-{max(pages)}',
            'undescribed': [s['id'] for s in wanted
                            if s['id'] not in data['described']]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('structure')
    p.add_argument('--pdf'); p.add_argument('--folder',
                                            help='a serialised book: one file per chapter')
    p.add_argument('--out', required=True)
    p.add_argument('--book', required=True); p.add_argument('--apply', action='store_true')
    p = sub.add_parser('status'); p.add_argument('--index', required=True)
    p = sub.add_parser('next')
    p.add_argument('--index', required=True); p.add_argument('--count', type=int, default=5)
    p = sub.add_parser('describe')
    p.add_argument('--index', required=True); p.add_argument('--id', required=True)
    p.add_argument('--text', required=True)
    p = sub.add_parser('resolve')
    p.add_argument('--index', required=True); p.add_argument('--range', required=True)
    args = ap.parse_args(argv)

    if args.cmd == 'structure':
        if args.folder:
            struct = structure_from_folder(args.folder)
            total = sum((s.get('end') or 0) - (s.get('start') or 0) + 1
                        for s in struct['sections'] if s.get('start')
                        and '.' not in s['id'])
            name = Path(args.folder).name
        else:
            struct = structure_from_pdf(args.pdf)
            total = extract_pdf.info(args.pdf).get('pages') or 0
            name = Path(args.pdf).name
        out = {'sections': len(struct['sections']), 'source': struct.get('source'),
               'complete': struct['complete'], 'pages': total,
               'problems': struct.get('problems'), 'reason': struct.get('reason')}
        if struct['complete'] and args.apply:
            from datetime import date
            fm, body = render_index(args.book, name, total, struct,
                                    date.today().isoformat())
            write_frontmatter(Path(args.out), fm, body)
            out['written'] = args.out
        elif args.apply:
            out['written'] = None
    elif args.cmd == 'status':
        out = status(args.index)
    elif args.cmd == 'next':
        out = next_sections(args.index, args.count)
    elif args.cmd == 'describe':
        out = add_description(args.index, args.id, args.text)
    else:
        out = resolve_range(args.index, getattr(args, 'range'))
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
