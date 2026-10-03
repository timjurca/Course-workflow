#!/usr/bin/env python3
"""What kind of file is this? Shared by A (destination) and B (priority and ID prefix).

A maps the returned kind to a destination folder; B maps the same kind to a
source priority and an extraction ID prefix. One module, because a file that A
files as a handout and B reads as an article is a silent mismatch neither can see.

Confidence, and why it is not a number:

  high  the student said so, or the file already carries a valid prefix, or the
        content ladder gives an unambiguous signal
  med   a filename keyword, or a Weekly_overview row matched on topic or date
  low   extension or an ambiguous sniff only, with no corroboration

**A never applies a `low` row.** It stays in _Inbox until the student confirms.

**Exam and assignment signals cap a row at `low`, whatever else matched.** A past
exam misfiled as a handout becomes a priority-1 lesson source for B and is
invisible to C, and nothing downstream can detect that. A redundant question is
cheaper than that outcome, so the ladder is biased toward asking.

CLI:
    classify.py file --path <p> [--said <kind>] [--peek]
    classify.py batch --paths <p> [<p> ...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from naming import content_prefix  # noqa: E402

KINDS = ['slides', 'transcript', 'notes', 'handout', 'workbook', 'article', 'book',
         'video_list', 'link_list', 'past_exam', 'past_exam_solutions',
         'mock_attempt', 'past_exam_attempt', 'assignment', 'unknown']

# B's priority ladder and ID prefixes, so the two skills cannot drift apart.
# The priority ladder, verbatim from the notes spec. Priority 1 is authoritative:
# definitions are preferred from it and it decides section order. The transcript
# sits at 2 because it is the lecturer *talking about* the authoritative material
# — reasoning, emphasis, worked examples, exam signals — with one sanctioned
# exception: when the transcript explicitly corrects a slide, the transcript wins
# and the claim is marked [S12 corrected by T09].
# Files that are never course material. Documented in shared/formats.md; the
# list lives here because this is the module both A and B already import, and
# two ignore lists would drift with only one of them wrong.
IGNORE_NAMES = {'.ds_store', 'thumbs.db', 'desktop.ini', 'icon\r'}
IGNORE_PREFIXES = ('~$', '._')
IGNORE_SUFFIXES = ('.tmp', '.temp', '.crdownload', '.part', '.swp')


def is_ignored(path) -> bool:
    """Junk a file manager or Office left behind, not a source."""
    name = Path(path).name
    low = name.lower()
    if low in IGNORE_NAMES or name.startswith('.'):
        return True
    return low.startswith(IGNORE_PREFIXES) or low.endswith(IGNORE_SUFFIXES)


B_SOURCE = {
    'book':       {'priority': 1, 'prefix': 'B'},
    'slides':     {'priority': 1, 'prefix': 'S'},
    'handout':    {'priority': 1, 'prefix': 'H'},
    'transcript': {'priority': 2, 'prefix': 'T'},
    'article':    {'priority': 2, 'prefix': 'A'},
    'video_list': {'priority': 2, 'prefix': 'V'},
    'link_list':  {'priority': 2, 'prefix': 'K'},
    'notes':      {'priority': 3, 'prefix': 'N'},
    'workbook':   {'priority': 1, 'prefix': 'H'},      # a lecturer's spreadsheet
    'annotation': {'priority': 3, 'prefix': 'C'},      # sticky notes, margin writing
    'assignment': {'priority': None, 'prefix': 'G'},   # signal only, not in coverage
}

# Any of these caps the row at low and forces the question. Slovenian included,
# because the vault is used in both languages.
EXAM_SIGNAL_WORDS = [
    'exam', 'izpit', 'kolokvij', 'midterm', 'final', 'rok', 'resitve', 'rešitve',
    'solutions', 'mock', 'attempt', 'assignment', 'naloga', 'naloge', 'seminarska',
    'homework', 'domaca naloga', 'domača naloga', 'poskus',
]

FILENAME_KEYWORDS = {
    'slides':     ['slide', 'lecture', 'predavanje', 'prezentacija', 'deck', 'ppt'],
    'transcript': ['transcript', 'transkript', 'recording', 'posnetek', 'captions',
                   'subtitle', 'rec_'],
    'notes':      ['notes', 'zapiski', 'my_notes', 'moji'],
    'handout':    ['handout', 'worksheet', 'problem', 'exercise', 'vaja', 'listic'],
    'article':    ['paper', 'article', 'clanek', 'članek', 'journal', 'arxiv'],
    'book':       ['book', 'textbook', 'knjiga', 'ucbenik', 'učbenik'],
}

# Extensions that settle the kind on their own, and how strongly. A presentation
# file is slides and a caption file is a transcript, whatever the name says; a
# .md could be anything, so it only ever reaches low.
EXT_HINT = {
    '.pptx': ('slides', 'high'), '.ppt': ('slides', 'high'), '.key': ('slides', 'high'),
    '.vtt': ('transcript', 'high'), '.srt': ('transcript', 'high'),
    '.epub': ('book', 'high'),
    '.xlsx': ('workbook', 'med'), '.xlsm': ('workbook', 'med'),
    '.md': ('notes', 'low'), '.txt': ('notes', 'low'),
    '.docx': ('notes', 'low'), '.doc': ('notes', 'low'),
}

RESERVED = {'videos.md': 'video_list', 'video.md': 'video_list'}


def _norm(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower())


def exam_signal(text: str) -> list[str]:
    n = ' ' + _norm(text) + ' '
    return [w for w in EXAM_SIGNAL_WORDS if f' {_norm(w)} ' in n]


def _pdf_shape(path: Path) -> dict:
    """Page count and geometry only. Never retained, never read for meaning."""
    out = {'pages': None, 'landscape': None, 'words_first_page': None,
           'has_abstract': None, 'first_page_text': '', 'error': None}
    try:
        import pdfplumber
    except ImportError as e:
        out['error'] = f'pdfplumber unavailable: {e}'
        return out
    try:
        with pdfplumber.open(str(path)) as pdf:
            out['pages'] = len(pdf.pages)
            first = pdf.pages[0]
            w, h = first.width, first.height
            out['landscape'] = w > h
            text = (first.extract_text() or '')[:4000]
            out['first_page_text'] = text
            out['words_first_page'] = len(text.split())
            head = ' '.join(
                ((pdf.pages[i].extract_text() or '') for i in range(min(3, len(pdf.pages))))
            ).lower()
            out['has_abstract'] = ('abstract' in head or 'references' in head
                                   or 'povzetek' in head)
    except Exception as e:   # a damaged or encrypted PDF is a report, not a crash
        out['error'] = str(e)
    return out


def _pdf_ladder(shape: dict, name: str) -> tuple[str, str, str]:
    """folder-structure companion table in A section 6.2. Returns (kind, conf, why)."""
    pages = shape.get('pages')
    if pages is None:
        return 'unknown', 'low', 'PDF could not be opened'
    if pages >= 150:
        return 'book', 'high', f'{pages} pages'
    if shape.get('landscape') and (shape.get('words_first_page') or 0) < 120:
        return 'slides', 'high', 'landscape geometry, few words per page'
    text = shape.get('first_page_text', '')
    if re.search(r'\b\d+\s*(points?|marks?|tock|točk)\b', text, re.IGNORECASE) or \
       re.search(r'\b(time limit|duration|cas pisanja|čas pisanja)\b', text, re.IGNORECASE):
        return 'past_exam', 'low', 'numbered tasks with point values or a time limit'
    if re.search(r'\b(due|deadline|oddaja|rok oddaje|submit)\b', text, re.IGNORECASE):
        return 'assignment', 'low', 'task list with a due date or submission instructions'
    if 5 <= pages <= 40 and shape.get('has_abstract'):
        return 'article', 'med', f'{pages} pages with an abstract or references'
    if pages < 15:
        return 'handout', 'med', f'{pages} pages, no abstract'
    return 'unknown', 'low', 'the ladder could not separate it'


def classify(path: Path | str, said: str | None = None, peek: bool = True,
             overview_match: str | None = None) -> dict:
    p = Path(path)
    name = p.name
    reasons: list[str] = []

    # Matched case-insensitively: the folder contract says subfolder and reserved
    # names are compared that way, and a vault lives on a case-insensitive disk.
    if name.lower() in RESERVED:
        return {'path': str(p), 'kind': RESERVED[name.lower()], 'confidence': 'high',
                'reasons': ['reserved name'], 'exam_signals': [], 'source': B_SOURCE.get(RESERVED[name])}
    if re.match(r'^links_.*\.md$', name, re.IGNORECASE):
        return {'path': str(p), 'kind': 'link_list', 'confidence': 'high',
                'reasons': ['reserved name'], 'exam_signals': [],
                'source': B_SOURCE.get('link_list')}

    signals = exam_signal(name)

    # 1. the student said so
    if said:
        kind, conf = said, 'high'
        reasons.append('stated by the student')
        if signals:
            reasons.append(f'exam/assignment words in the name: {", ".join(signals)}')
        return {'path': str(p), 'kind': kind, 'confidence': conf, 'reasons': reasons,
                'exam_signals': signals, 'source': B_SOURCE.get(kind)}

    kind, conf = None, None
    ext = p.suffix.lower()

    # 2. an existing valid prefix
    prefix = content_prefix(name)
    if prefix:
        kind, conf = prefix, 'high'
        reasons.append(f'existing valid prefix "{prefix}_"')

    # 3. a decisive extension
    if kind is None and EXT_HINT.get(ext, (None, 'low'))[1] == 'high':
        kind, conf = EXT_HINT[ext]
        reasons.append(f'extension {ext} is decisive')

    # 4. filename keyword
    if kind is None:
        low = _norm(name)
        raw = name.lower()
        for k, words in FILENAME_KEYWORDS.items():
            if any(w in low or w in raw for w in words):
                kind, conf = k, 'med'
                reasons.append('filename keyword')
                break

    # 5. overview row match
    if kind is None and overview_match:
        reasons.append(f'Weekly_overview row matched on {overview_match}')
        conf = 'med'

    # 6. a weak extension hint, last
    if kind is None and ext in EXT_HINT:
        kind, conf = EXT_HINT[ext]
        reasons.append(f'extension {ext}')

    # 7. content ladder, PDFs only
    if ext == '.pdf' and peek and (kind is None or conf != 'high'):
        shape = _pdf_shape(p)
        lk, lc, why = _pdf_ladder(shape, name)
        if lk != 'unknown':
            rank = {'low': 0, 'med': 1, 'high': 2}
            if kind is None or rank[lc] > rank.get(conf or 'low', 0):
                kind, conf = lk, lc
            reasons.append(f'content ladder: {why}')
            if shape.get('error'):
                reasons.append(f'PDF warning: {shape["error"]}')
        signals = sorted(set(signals) | set(exam_signal(shape.get('first_page_text', ''))))

    if kind is None:
        kind, conf = 'unknown', 'low'
        reasons.append('nothing matched')

    # The cap. Applied last, so nothing above can talk its way past it.
    if signals:
        conf = 'low'
        reasons.append('capped at low: exam or assignment signal present '
                       f'({", ".join(signals)}) — ask which of the five kinds it is')

    return {'path': str(p), 'kind': kind, 'confidence': conf, 'reasons': reasons,
            'exam_signals': signals, 'source': B_SOURCE.get(kind)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('file')
    p.add_argument('--path', required=True)
    p.add_argument('--said'); p.add_argument('--no-peek', action='store_true')
    p = sub.add_parser('batch')
    p.add_argument('--paths', nargs='+', required=True)
    p.add_argument('--no-peek', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'file':
        out = classify(args.path, args.said, peek=not args.no_peek)
    else:
        out = {'rows': [classify(x, peek=not args.no_peek) for x in args.paths]}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
