#!/usr/bin/env python3
"""The gate that runs before any extraction. Ordered, fail fast, nothing written.

Every check here exists because of a failure that is **silent** without it. That
is the selection rule: a problem that announces itself does not need a gate.

  * An iCloud placeholder reads as an empty file. Notes get written with an
    entire source missing and coverage reports 100%, because there were no IDs
    to miss. Hard fail.
  * A conflicted copy means writes are landing in a branch nobody will open
    again. Hard fail.
  * A **blank** `Chapters` cell is not "no reading" — that is `-`. Treating a
    blank as satisfied writes notes without a whole priority-1 source while the
    arithmetic still balances. Stop and ask.
  * A missing `code:` makes every generated filename collide vault-wide, and
    Obsidian resolves the collision silently.

**Scope, not the whole course.** Checks 2 and 3 cover only material this lesson
depends on. The course-wide version of this gate deadlocked: `_Inbox/` is the
most conflict-prone folder in the vault and A will not delete a conflicted copy,
so one stray conflict there blocked every lesson of the course with no exit.

**`Explanations/` is never in scope, at any point.** It is tutor output. If it
ever entered a source list it would enter `sources_hash`, become notes, and the
student would revise from model prose believing it was the lecturer's. The scope
builder asserts its absence and the result says so, so a regression here is
visible rather than theoretical.

Check 9 is **detection only**: the presence of `notes_corrections.md` is read
from the filesystem, never from inside the file. The count of corrections is
skill D's to report, not this skill's.

CLI:
    preflight.py check --course <path> --lesson L03 [--batch] [--sources ...]
    preflight.py scope --course <path> --lesson L03
    preflight.py sources --course <path> --lesson L03 --sources <rel> [...]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import book_index                                                  # noqa: E402
import classify                                                    # noqa: E402
import extraction                                                  # noqa: E402
import icloud                                                      # noqa: E402
import naming                                                      # noqa: E402
import overview as ov                                              # noqa: E402
import presence                                                    # noqa: E402
import source_hash as sh                                           # noqa: E402
from vault import read_config, read_frontmatter                    # noqa: E402

PROSE_FILES = ['Course_description.md', 'Learning_objectives.md', 'Literature.md']
RESERVED_CONTENT = {'videos.md', 'video.md', 'notes_corrections.md'}
MISFILED_KINDS = {'past_exam', 'past_exam_solutions', 'mock_attempt',
                  'past_exam_attempt', 'assignment'}

# shared/formats.md. An extension outside this set stops the run: a guessed
# handler produces an empty extraction that looks like a thin source.
KNOWN_EXT = {'.pdf', '.pptx', '.docx', '.epub', '.md', '.txt', '.vtt', '.srt',
             '.png', '.jpg', '.jpeg', '.tiff', '.webp', '.html', '.htm',
             '.xlsx', '.xlsm'}
DEPS = {'.pptx': ('pptx', 'python-pptx'), '.docx': ('docx', 'python-docx'),
        '.epub': ('ebooklib', 'ebooklib'), '.pdf': ('pdfplumber', 'pdfplumber'),
        '.html': ('bs4', 'beautifulsoup4'), '.htm': ('bs4', 'beautifulsoup4'),
        '.xlsx': ('openpyxl', 'openpyxl'), '.xlsm': ('openpyxl', 'openpyxl')}

LINK_RE = re.compile(r'https?://\S+')


def _row(n, name, status, severity, detail, **extra):
    out = {'check': n, 'name': name, 'status': status, 'severity': severity,
           'detail': detail}
    out.update(extra)
    return out


def _lesson_folder(course: Path, key: str) -> Path | None:
    kind = 'Lessons' if key.startswith('L') else 'Tutorials'
    root = course / kind
    if not root.is_dir():
        return None
    num = key[1:]
    for p in sorted(root.iterdir()):
        parsed = naming.parse_lesson_folder(p.name)
        if p.is_dir() and parsed and parsed['num'] == num:
            return p
    return None


def _content_dir(folder: Path) -> Path | None:
    for p in folder.iterdir():
        if p.is_dir() and p.name.lower() == 'content':
            return p
    return None


def _subdir(folder: Path, name: str) -> Path | None:
    for p in folder.iterdir():
        if p.is_dir() and p.name.lower() == name.lower():
            return p
    return None


# ------------------------------------------------------------------ books

ROW_RE = re.compile(r'^\|\s*[\w.]+\s*\|', re.MULTILINE)


def _index_rows(body: str) -> int:
    """Chapter rows in an index, excluding the header and separator lines."""
    n = 0
    for line in body.split('\n'):
        s = line.strip()
        if not s.startswith('|'):
            continue
        first = s.strip('|').split('|')[0].strip()
        if not first or set(first) <= set('-: '):
            continue
        if first.lower() in ('id', 'no', '#'):
            continue
        if first[0].isdigit():
            n += 1
    return n


def match_index(course: Path, book_value: str) -> dict:
    """Resolve the `Book` cell against each index's `book:` frontmatter.

    By frontmatter, not by filename: a student writes "Wooldridge" in the table
    and the file is `Wooldridge_Introductory.index.md`. The filename is only a
    secondary key, and two genuine matches is a question, never a guess.

    Three rules decide between candidates, because a bare substring test makes
    a course with a solutions manual permanently ambiguous. A manual is titled
    as a *superstring* of the textbook it answers ("Corporate Finance -
    Solutions Manual"), so every short form of the textbook's name is also
    inside the manual's name, and no rewording of either title escapes it:
    moving "Solutions" to the front changes nothing, because the test scans the
    whole string. The student is then forced to write the full edition line in
    a table cell, which is exactly the "longer form" the old error asked for
    and exactly the thing a short form exists to avoid.

    1. **An index that cannot resolve a range is not a candidate.** A stub with
       no chapter rows could never answer the question being asked, so it must
       not be allowed to block it. Kept only when nothing else matched at all,
       so the error can say the one match has no chapters built.
    2. **Exact beats prefix beats substring.** One title equal to the cell ends
       it. Otherwise a title *starting* with the cell is a stronger claim than
       one merely containing it.
    3. Only within the strongest surviving tier does a tie become a question.
    """
    books = course / 'Books'
    if not books.is_dir():
        return {'matched': None, 'candidates': [], 'reason': 'no Books/ folder'}
    want = (book_value or '').strip().lower()
    hits = []
    for idx in sorted(books.glob('*.index.md')):
        try:
            fm, body = read_frontmatter(idx)
        except Exception:
            continue
        title = str(fm.get('book') or '').strip().lower()
        if not title or not want:
            continue
        if want == title:
            tier = 'exact'
        elif title.startswith(want):
            tier = 'prefix'
        elif want in title:
            tier = 'substring'
        else:
            continue
        hits.append({'index': str(idx.relative_to(course)),
                     'book': fm.get('book'), 'file': fm.get('file'),
                     'folder': fm.get('folder'), 'match': tier,
                     'rows': _index_rows(body)})

    usable = [h for h in hits if h['rows'] > 0]
    pool, dropped = (usable, [h for h in hits if h['rows'] == 0]) \
        if usable else (hits, [])
    for tier in ('exact', 'prefix', 'substring'):
        tier_hits = [h for h in pool if h['match'] == tier]
        if len(tier_hits) == 1:
            out = {'matched': tier_hits[0], 'candidates': hits, 'by': tier}
            if dropped:
                out['ignored_empty'] = [h['index'] for h in dropped]
            return out
        if tier_hits:
            return {'matched': None, 'candidates': tier_hits,
                    'reason': f'{len(tier_hits)} indexes match this Book value '
                              f'equally well ({tier}); ask which one'}
    if not hits:
        # filename is the secondary key
        stem = naming.slugify(want)
        alt = [p for p in books.glob('*.index.md')
               if stem and stem in naming.slugify(p.stem)]
        if len(alt) == 1:
            fm, body = read_frontmatter(alt[0])
            return {'matched': {'index': str(alt[0].relative_to(course)),
                                'book': fm.get('book'), 'file': fm.get('file'),
                                'folder': fm.get('folder'), 'match': 'filename',
                                'rows': _index_rows(body)},
                    'candidates': [], 'by': 'filename'}
    return {'matched': None, 'candidates': hits,
            'reason': 'no index matches this Book value'}


# ------------------------------------------------------------------ scope

def build_scope(course: Path | str, key: str) -> dict:
    """Every file this run depends on, and nothing else.

    Out of scope by design: other lessons, books this lesson does not cite,
    everything under `_Inbox/` except the filing log, and `Explanations/` at all
    times.
    """
    course = Path(course)
    folder = _lesson_folder(course, key)
    files: list[Path] = []
    notes: list[str] = []

    if folder:
        # A file manager's leftovers are not sources. Handing a 165-byte
        # Office lock file to python-pptx fails mid-run for no reason.
        files += [p for p in folder.rglob('*')
                  if p.is_file() and not classify.is_ignored(p)]

    data = ov.load(course)
    reading = ov.resolve_reading(data, key)
    book = None
    if reading.get('status') == 'resolved':
        book = match_index(course, reading['book'])
        if book.get('matched'):
            idx = course / book['matched']['index']
            files.append(idx)
            pdf_name = book['matched'].get('file')
            if pdf_name:
                pdf = course / 'Books' / pdf_name
                if pdf.is_file():
                    files.append(pdf)
                else:
                    notes.append(f'the index names {pdf_name}, which is not in Books/')

    for rel in ['Weekly_overview.md', 'Table_of_contents.md',
                '.data/terms.json', '.data/concepts.json'] + PROSE_FILES:
        p = course / rel
        if p.is_file():
            files.append(p)
    for name in ('Articles', 'Videos', 'Links'):
        d = course / name
        if d.is_dir():
            files += [p for p in d.glob('*.md') if p.is_file()]
    for row in ov.assignments_for(data, key):
        p = course / 'Assignments' / row['File']
        if row['File'] and p.is_file():
            files.append(p)
    log = course / '_Inbox' / '_filing_log.md'
    if log.is_file():
        files.append(log)

    files = sorted({p.resolve() for p in files})
    # The quarantine, asserted rather than assumed (folder-structure §9).
    breach = [str(p) for p in files if 'Explanations' in p.parts]
    files = [p for p in files if 'Explanations' not in p.parts]
    return {'lesson_folder': str(folder) if folder else None,
            'files': [str(p) for p in files],
            'book': book, 'reading': reading, 'notes': notes,
            'explanations_excluded': True, 'quarantine_breach': breach}


# ------------------------------------------------------------------ checks

def _check_1(course: Path, key: str, folder: Path | None, rows: list) -> Path | None:
    kind = 'Lessons' if key.startswith('L') else 'Tutorials'
    if folder is None:
        rows.append(_row(1, 'folder', 'fail', 'hard',
                         f'no {kind}/NN_YYYY-MM-DD folder for {key}. Skill A '
                         'creates a lesson folder when material is first filed '
                         'into it, so its absence means nothing is filed yet.'))
        return None
    content = _content_dir(folder)
    if content is None:
        rows.append(_row(1, 'folder', 'fail', 'hard',
                         f'{folder.name}/Content/ does not exist. It is created '
                         'unconditionally with the lesson; run course-setup '
                         'validate.', path=str(folder)))
        return None
    rows.append(_row(1, 'folder', 'pass', 'hard',
                     f'{kind}/{folder.name} with Content/', path=str(folder)))
    return content


def _check_1b(course: Path, vault: Path | None, data: dict, rows: list) -> str | None:
    fm = data.get('frontmatter') or {}
    code = fm.get('code')
    if not data.get('exists'):
        rows.append(_row('1b', 'code', 'fail', 'ask',
                         'Weekly_overview.md is missing. It is mandatory and '
                         'skill A owns it.'))
        return None
    if not code:
        rows.append(_row('1b', 'code', 'fail', 'ask',
                         'Weekly_overview.md carries no code:. Every generated '
                         'filename depends on it.'))
        return None
    # The contract is `[NN_]<CODE>_<Name>`: the sort prefix is optional, so a
    # bare startswith fails on every numbered folder (`01_EBT_...`). Use the
    # shared parser, which is the same one skill A names folders with.
    if not naming.course_folder_matches_code(course.name, code):
        rows.append(_row('1b', 'code', 'fail', 'ask',
                         f'code: is "{code}" but the folder is "{course.name}". '
                         'Skill A keeps them in sync, so one was hand-edited and '
                         'either could be the intended value.', code=code))
        return code
    if vault:
        try:
            registry = (read_config(vault) or {}).get('course_codes') or {}
        except Exception:
            registry = {}
        mapped = registry.get(code)
        if mapped is None:
            rows.append(_row('1b', 'code', 'fail', 'ask',
                             f'"{code}" is not in course_codes in _config.md. The '
                             'registry is the uniqueness check; run course-setup '
                             'validate to register it.', code=code))
            return code
        try:
            rel = str(course.resolve().relative_to(Path(vault).resolve()))
        except ValueError:
            rel = None
        if rel and str(mapped).strip('/') != rel:
            rows.append(_row('1b', 'code', 'fail', 'ask',
                             f'course_codes maps "{code}" to {mapped!r}, not to '
                             'this course. A reused code produces colliding '
                             'filenames that Obsidian resolves silently.',
                             code=code))
            return code
    rows.append(_row('1b', 'code', 'pass', 'ask', f'code: {code}', code=code))
    return code


def _check_2_3(scope: dict, rows: list):
    paths = [Path(p) for p in scope['files']]
    placeholders = [str(p) for p in paths if icloud.is_placeholder(p).get('placeholder')]
    if placeholders:
        rows.append(_row(2, 'icloud_placeholder', 'fail', 'hard',
                         'these files are not downloaded. Reading one returns '
                         'empty content and the notes would be missing a whole '
                         'source while coverage still reported 100%.',
                         files=placeholders))
    else:
        rows.append(_row(2, 'icloud_placeholder', 'pass', 'hard',
                         f'{len(paths)} files in scope, all materialised'))

    conflicts = []
    for p in paths:
        if icloud.looks_conflicted(p.name, p.parent):
            conflicts.append(str(p))
    for p in paths:
        for sib in p.parent.glob('*'):
            if sib.is_file() and sib != p and \
                    icloud.looks_conflicted(sib.name, sib.parent) and \
                    icloud.original_of(sib.name, sib.parent) == p.name:
                conflicts.append(str(sib))
    conflicts = sorted(set(conflicts))
    if conflicts:
        rows.append(_row(3, 'icloud_conflict', 'fail', 'hard',
                         'conflicted copies in scope. Writes are landing in a '
                         'branch that may never be opened again.', files=conflicts))
    else:
        rows.append(_row(3, 'icloud_conflict', 'pass', 'hard', 'none in scope'))


def _check_4(content: Path, folder: Path, rows: list):
    unresolved, misfiled, unknown_ext = [], [], []
    for p in sorted(content.iterdir()):
        # formats.md: junk is excluded at scope construction, before any check
        # runs. A dotfile test alone let a 165-byte `~$handout_x.xlsx` Excel
        # owner file through to the prefix check, which then stopped the whole
        # run over a lock file the student cannot even see in Obsidian.
        if not p.is_file() or classify.is_ignored(p):
            continue
        name = p.name
        if name in RESERVED_CONTENT or re.match(r'^links_.*\.md$', name):
            continue
        if name.lower().startswith('book_'):
            misfiled.append({'file': name, 'why': 'there is no book_ prefix; '
                             'books live in Books/ at course root'})
            continue
        if p.suffix.lower() not in KNOWN_EXT:
            unknown_ext.append(name)
            continue
        # Every content file needs a prefix, not only the .md ones. The prefix
        # is how the rest of the pipeline finds a file at all: check 2b selects
        # decks by it, and the source hierarchy assigns priority by it. A
        # prefixless `.pptx` used to pass here, and then 2b honestly reported
        # "no slide deck in Content/" because nothing it could see was one, so
        # the lesson would have been written without its slides while every
        # check showed green. That is the worst shape a miss can take.
        if not naming.content_prefix(name):
            unresolved.append(name)
            continue
        try:
            row = classify.classify(p, peek=True)
        except Exception:
            row = {}
        kind = row.get('kind')
        if kind in MISFILED_KINDS:
            misfiled.append({'file': name, 'why': f'classified as {kind}; it is '
                             'never a lesson source. Refile it through '
                             'course-setup.'})
        elif row.get('exam_signals'):
            # Any exam or assignment signal is enough, whatever the sniff said.
            # A past exam misfiled as a handout becomes a priority-1 lesson
            # source here and is invisible to course-revision, and nothing
            # downstream can detect that.
            misfiled.append({'file': name, 'why':
                             'exam or assignment words in the name '
                             f'({", ".join(row["exam_signals"])}); sniffed as '
                             f'{kind}. Confirm what it is, or refile it through '
                             'course-setup.'})
    for p in sorted((_subdir(folder, 'Articles') or content).glob('*')):
        if p.is_file() and p.parent.name.lower() == 'articles' and \
                p.suffix.lower() not in KNOWN_EXT:
            unknown_ext.append(p.name)

    if unresolved or misfiled:
        rows.append(_row(4, 'content_names', 'fail', 'ask',
                         'every content file needs its prefix: it is how the '
                         'deck scan and the source hierarchy find the file at '
                         'all, so an unprefixed file is silently invisible '
                         'rather than merely untidy. Rename through '
                         'course-setup; an exam or assignment file here is a '
                         'misfiling.',
                         unprefixed=unresolved, misfiled=misfiled))
    else:
        rows.append(_row(4, 'content_names', 'pass', 'ask', 'every file resolved'))
    if unknown_ext:
        rows.append(_row('4b', 'unknown_extension', 'fail', 'ask',
                         'no handler is defined for these. Propose a row for '
                         'shared/formats.md and apply it only after approval; '
                         'never guess a handler.', files=sorted(set(unknown_ext))))
    else:
        rows.append(_row('4b', 'unknown_extension', 'pass', 'ask',
                         'every extension has a handler'))


def _has_link(path: Path) -> bool:
    try:
        return bool(LINK_RE.search(path.read_text(encoding='utf-8', errors='replace')))
    except OSError:
        return False


# The presence evidence table now lives in shared/scripts/presence.py: skill A
# needs it too, to propose what a course should declare in `expects`.
present = presence.present


def _check_5(course: Path, key: str, folder: Path, content: Path, data: dict,
             rows: list):
    fm = data.get('frontmatter') or {}
    expects = fm.get('expects') or []
    if isinstance(expects, str):
        expects = [x.strip() for x in expects.strip('[]').split(',') if x.strip()]
    legal = {'slides', 'transcript', 'book', 'notes', 'handouts', 'articles',
             'videos', 'links'}
    illegal = [t for t in expects if t not in legal]
    if illegal:
        rows.append(_row(5, 'expects', 'fail', 'ask',
                         f'expects contains tokens outside the closed vocabulary: '
                         f'{illegal}. Rejected rather than silently ignored.'))
        return
    ev = present(course, key, folder, content, data)
    missing = [t for t in expects if not ev.get(t)]
    reading = ov.resolve_reading(data, key)
    if 'book' in missing and reading.get('status') == 'none':
        missing.remove('book')      # a `-` row is exempt, not incomplete
    if missing:
        rows.append(_row(5, 'expects', 'fail', 'ask',
                         'this course declares these categories as always '
                         'present, and they are not. Offer to proceed without '
                         'them.', missing=missing, evidence=ev))
    else:
        rows.append(_row(5, 'expects', 'pass', 'ask',
                         f'{", ".join(expects) or "nothing declared"}',
                         evidence=ev))


# Per-lesson staples: a lesson either has these or is missing something. The
# other four tokens are sporadic -- reading assigned in lecture N is filed under
# lesson N+1, so the lesson that assigns it looks like it is missing articles.
COHORT_TOKENS = presence.STAPLES


def _cohort(course: Path, key: str, data: dict) -> dict:
    """What the course's *other* lessons and tutorials have, per token."""
    rows = presence.across_lessons(Path(course), data, skip=key)
    counts = {}
    for ev in rows.values():
        for tok, has in ev.items():
            if has:
                counts[tok] = counts.get(tok, 0) + 1
    return {'total': len(rows), 'counts': counts}


def _check_5b(course: Path, key: str, ev: dict, data: dict, rows: list):
    """A source kind this lesson lacks that most of its siblings have.

    `expects` only covers what skill A declared, and a category nobody declared
    is exactly the one that goes missing unnoticed: the student's own notes sit
    in five lessons out of six and the sixth is processed in silence, with a
    whole priority-3 layer absent and coverage still reporting 100%.
    """
    cohort = _cohort(course, key, data)
    total = cohort['total']
    if total < 2:
        rows.append(_row('5b', 'cohort', 'skip', 'ask',
                         'fewer than two sibling lessons to compare against'))
        return
    declared = set((data.get('frontmatter') or {}).get('expects') or [])
    odd = []
    for tok, n in sorted(cohort['counts'].items()):
        if tok not in COHORT_TOKENS:
            continue          # sporadic by nature; absence carries no signal
        if ev.get(tok) or tok in declared:
            continue          # present here, or already check 5's business
        if n >= 2 and n * 2 > total:
            odd.append({'token': tok, 'in_siblings': n, 'of': total})
    if odd:
        rows.append(_row('5b', 'cohort', 'fail', 'ask',
                         'this lesson is missing a source kind that most of the '
                         'other lessons in this course have. Say what is missing '
                         'and ask, before writing notes that silently omit a '
                         'whole layer. If it is expected from now on, skill A '
                         'adds it to `expects`.', missing=odd))
    else:
        rows.append(_row('5b', 'cohort', 'pass', 'ask',
                         f'nothing the other {total} lesson(s) have is missing here'))


PAGENUM_RE = re.compile(r'^\s*\d{1,3}\s*$')
CID_RE = re.compile(r'\(cid:\d+\)')
BOILER_FRAC = 0.6      # a line on this share of pages is the deck's furniture
THIN_WORDS = 12        # distinctive words below which a page says nothing
IMG_MARGIN = 8.0       # percentage points of page area above the deck's own norm
VEC_MARGIN = 8         # drawn objects above the deck's own norm
VEC_WORDS = 70         # ... and only when the page is not already text-rich


def pdf_slide_stats(path: Path | str) -> list[dict]:
    """Per-page measures for a PDF deck, taken against the deck's own baseline.

    A deck exported through "Print to PDF" carries the lecture title, the
    section footer and the page number as live text on *every* page, so a
    per-page "does this page have text?" test can never fail, however empty the
    slide is. Slide 19 of the FM lecture 2 deck extracts to `MOT111A: Financial
    Management / 3.1 NPV / 19` while the image carries the only fully worked NPV
    example in the course, six rows of discount factors and the result.

    So nothing here is measured in the absolute. A line that repeats across most
    pages is furniture and is subtracted before the words are counted; the page
    logo sets an image baseline that real pictures are measured against; and the
    rectangles and lines that draw every slide's frame set a baseline that a
    drawn table or an NPV profile stands out from. What survives subtraction is
    what this page has and its neighbours do not.
    """
    import collections
    import statistics
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        pages = pdf.pages
        n = len(pages) or 1
        lines = [[ln.strip() for ln in (pg.extract_text() or '').splitlines()
                  if ln.strip()] for pg in pages]
        freq = collections.Counter()
        for ls in lines:
            for ln in set(ls):
                freq[ln] += 1
        boiler = {ln for ln, c in freq.items() if c > 1 and c >= BOILER_FRAC * n}
        rows = []
        for i, pg in enumerate(pages):
            area = (pg.width or 1) * (pg.height or 1)
            img = 0.0
            for im in (pg.images or []):
                try:
                    img += abs((im['x1'] - im['x0']) * (im['bottom'] - im['top']))
                except Exception:
                    pass
            kept = [ln for ln in lines[i]
                    if ln not in boiler and not PAGENUM_RE.match(ln)]
            cids = len(CID_RE.findall(' '.join(kept)))
            kept = [CID_RE.sub('', ln).strip() for ln in kept]
            kept = [ln for ln in kept if ln]
            rows.append({'page': i + 1, 'cids': cids,
                         'words': sum(len(ln.split()) for ln in kept),
                         'img_pct': round(100 * img / area, 1),
                         'vec': len(pg.rects or []) + len(pg.lines or []),
                         'title': (kept[0] if kept else '')[:60]})

    img_base = statistics.median(r['img_pct'] for r in rows) if rows else 0
    vec_base = statistics.median(r['vec'] for r in rows) if rows else 0
    for r in rows:
        why = []
        if r['words'] < THIN_WORDS:
            why.append('almost no text of its own')
        if r['cids']:
            why.append(f"{r['cids']} unmapped glyph codes: a formula or symbol "
                       'on this page did not extract at all, however much '
                       'ordinary text sits beside it')
        if r['img_pct'] - img_base >= IMG_MARGIN:
            why.append(f"image covers {r['img_pct']}% of the page "
                       f"against {img_base}% on a normal page here")
        if r['vec'] - vec_base >= VEC_MARGIN and r['words'] < VEC_WORDS:
            why.append(f"{r['vec']} drawn objects against {vec_base}, "
                       'so a table or chart is drawn rather than written')
        r['why'] = '; '.join(why)
    return rows


def _check_2b(content: Path, rows: list):
    """Slides whose content is a picture, so extraction sees nothing.

    Slide 11 of EBT lecture 1 is the course schedule as an image: one word of
    text and 45% of the slide area. Nothing downstream could see that it
    contradicted Weekly_overview, because there was no text to compare.

    **Scanning nothing is a failure.** This check once looked only at `.pptx`
    and reported "every slide has a text layer" for a lesson whose only deck was
    a PDF, having measured zero files. Both FM lectures passed it that way while
    sixteen of forty-three slides carried their content as pictures.
    """
    import importlib.util

    decks = [p for p in sorted(content.glob('*'))
             if p.is_file() and not classify.is_ignored(p)
             and p.suffix.lower() in ('.pptx', '.pdf')
             and (naming.content_prefix(p.name) or '') == 'slides']
    if not decks:
        rows.append(_row('2b', 'image_slides', 'pass', 'ask',
                         'no slide deck in Content/, so there was nothing to '
                         'measure. This is not a statement about any slide.'))
        return

    flagged, skipped, measured, pages = [], [], 0, 0
    for p in decks:
        try:
            if p.suffix.lower() == '.pptx':
                if importlib.util.find_spec('pptx') is None:
                    skipped.append({'file': p.name,
                                    'why': 'python-pptx is not installed'})
                    continue
                import extract_pptx
                stats = extract_pptx.slide_text_stats(p)
                measured += 1
                pages += len(stats)
                for st in stats:
                    # PowerPoint has no per-page furniture to subtract, so the
                    # deck-baseline trick used for PDFs does not transfer: on a
                    # picture-rich deck the median image area is itself large.
                    # The old rule also required `words < 25`, which is why
                    # slide 22 of EBT lecture 2, the V-model diagram with a
                    # 42-word summary beside it, was never flagged while its
                    # ninth phase existed only inside the picture.
                    why = []
                    if st['words'] < THIN_WORDS:
                        why.append('almost no text of its own')
                    if st['picture_area_pct'] >= 15:
                        why.append(f"a picture covers {st['picture_area_pct']}% "
                                   'of the slide')
                    if st.get('groups') and st['words'] < VEC_WORDS:
                        why.append(f"{st['groups']} grouped shape(s), so a "
                                   'diagram is drawn rather than written')
                    if st.get('mute_shapes', 0) >= 8 and st['words'] < VEC_WORDS:
                        why.append(f"{st['mute_shapes']} shapes carry no text")
                    if why:
                        flagged.append({'file': p.name, 'page': st['slide'],
                                        'why': '; '.join(why), **st})
            else:
                if importlib.util.find_spec('pdfplumber') is None:
                    skipped.append({'file': p.name,
                                    'why': 'pdfplumber is not installed'})
                    continue
                stats = pdf_slide_stats(p)
                measured += 1
                pages += len(stats)
                for st in stats:
                    if st['why']:
                        flagged.append({'file': p.name, **st})
        except Exception as exc:
            skipped.append({'file': p.name, 'why': str(exc)})

    if not measured:
        rows.append(_row('2b', 'image_slides', 'fail', 'ask',
                         f'{len(decks)} slide deck(s) are present and none could '
                         'be measured, so nothing was checked. That is not a '
                         'pass: read the deck yourself before writing.',
                         decks=[p.name for p in decks], skipped=skipped))
        return

    if flagged:
        flagged.sort(key=lambda r: (not r.get('cids'), r.get('words', 0),
                                    -r.get('img_pct', 0)))
        rows.append(_row('2b', 'image_slides', 'fail', 'ask',
                         f'{len(flagged)} of {pages} slides carry content the '
                         'text layer does not hold. Render each one and read it, '
                         'tagging what you extract `[<id>, from image, verify]`. '
                         'A page listed here with plenty of text still has a '
                         'picture worth reading.',
                         slides=flagged[:40], pages_flagged=[r['page'] for r in flagged],
                         measured=measured, skipped=skipped))
    else:
        rows.append(_row('2b', 'image_slides', 'pass', 'ask',
                         f'measured {measured} deck(s), {pages} slides; none is '
                         'picture-heavy against its own deck baseline',
                         skipped=skipped))


def _check_6(course: Path, key: str, data: dict, rows: list):
    reading = ov.resolve_reading(data, key)
    status = reading.get('status')
    if status == 'none':
        rows.append(_row(6, 'chapters', 'pass', 'ask',
                         'the row reads "-": this lesson runs without a book '
                         'source, and the report says so.'))
        return
    if status == 'missing_row':
        rows.append(_row(6, 'chapters', 'fail', 'ask',
                         f'{key} has no row in Weekly_overview.md. Skill A owns '
                         'that file; this skill never fills a gap in it.'))
        return
    if status == 'incomplete':
        rows.append(_row(6, 'chapters', 'fail', 'ask',
                         'the Book or Chapters cell is blank. A blank cell is '
                         'not "no reading" (that is "-"): it is a row skill A '
                         'flagged as needing completion, and treating it as '
                         'satisfied writes notes with a whole priority-1 source '
                         'missing while coverage reports 100%.', chain=reading.get('chain')))
        return
    if status == 'broken_chain':
        rows.append(_row(6, 'chapters', 'fail', 'ask',
                         f'the cont. chain is broken: {reading.get("reason")}',
                         chain=reading.get('chain')))
        return
    book = match_index(course, reading['book'])
    if not book.get('matched'):
        rows.append(_row(6, 'chapters', 'fail', 'ask',
                         f'{book.get("reason")}. This skill never builds or '
                         'extends a book index; run course-setup on that book.',
                         candidates=book.get('candidates')))
        return
    res = book_index.resolve_range(course / book['matched']['index'],
                                   reading['chapters'])
    if not res.get('resolved'):
        rows.append(_row(6, 'chapters', 'fail', 'ask',
                         f'{reading["chapters"]}: {res.get("reason")}',
                         index=book['matched']['index']))
        return
    # A serialised book (a folder of chapter files) has no page range at all:
    # resolve_range returns `files` and no `pages` key. Reading res['pages']
    # unconditionally raised KeyError and took down the whole pre-flight, so a
    # course whose reader is serialised could never be processed.
    if res.get('serialised'):
        files = res.get('files') or []
        rows.append(_row(6, 'chapters', 'pass', 'ask',
                         f'{reading["book"]} {reading["chapters"]} -> '
                         f'{len(files)} chapter file(s), serialised '
                         f'({len(res["sections"])} sections)',
                         index=book['matched']['index'],
                         serialised=True,
                         files=[f['path'] for f in files],
                         sections=[s['id'] for s in res['sections']],
                         resolved_from=reading.get('resolved_from')))
        return
    rows.append(_row(6, 'chapters', 'pass', 'ask',
                     f'{reading["book"]} {reading["chapters"]} -> pages '
                     f'{res["pages"]} ({len(res["sections"])} sections)',
                     index=book['matched']['index'], pages=res['pages'],
                     sections=[s['id'] for s in res['sections']],
                     resolved_from=reading.get('resolved_from')))


def _check_7(scope: dict, content: Path, rows: list):
    exts = {Path(p).suffix.lower() for p in scope['files']}
    missing = []
    for ext, (mod, pkg) in DEPS.items():
        if ext in exts and importlib.util.find_spec(mod) is None:
            missing.append({'for': ext, 'package': pkg,
                            'install': f'pip install {pkg}'})
    if missing:
        rows.append(_row(7, 'dependencies', 'fail', 'ask',
                         'a source in scope has no handler without these. Ask '
                         'before installing anything.', missing=missing))
    else:
        rows.append(_row(7, 'dependencies', 'pass', 'ask', 'all present'))

    # yt-dlp is the one dependency whose absence is not a gate: §4.4 tier 3 says
    # an unfetchable video is listed and flagged, and the run continues. Making
    # it blocking would stop a lesson over a link the student may never watch.
    videos = [p for p in content.iterdir()
              if p.is_file() and p.name in ('videos.md', 'video.md')]
    if any(_has_link(p) for p in videos) and not shutil.which('yt-dlp'):
        rows.append(_row('7b', 'captions', 'warn', 'warn',
                         'yt-dlp is not installed, so assigned videos degrade to '
                         'metadata or link-only. Offer the install; never block '
                         'on it.', install='pip install yt-dlp'))


def _notes_path(course: Path, key: str, code: str, folder: Path) -> Path:
    return folder / 'Final_notes' / f'{code}_{key}_Final_notes.md'


def _check_8(course: Path, key: str, code: str | None, folder: Path,
             sources: list[str] | None, batch: bool, rows: list):
    if not batch:
        rows.append(_row(8, 'freshness', 'skip', 'skip',
                         'batch mode only; a single-lesson run always rebuilds'))
        return
    notes = _notes_path(course, key, code or '', folder)
    if not code or not notes.is_file():
        rows.append(_row(8, 'freshness', 'pass', 'skip', 'no previous notes'))
        return
    fm, _ = read_frontmatter(notes)
    recorded = fm.get('sources_hash')
    current = sh.sources_hash(folder if folder else course, sources or [])
    # Rows are compared by parsed, trimmed cells. Obsidian re-pads a table on
    # save and a re-padded table is not a change; comparing raw text would make
    # every lesson stale the first time the file is opened.
    want = ov.inputs_for(course, key)
    had = fm.get('inputs') or {}
    same_inputs = (
        had.get('overview_row_normalised') == want.get('overview_row_normalised')
        and list(had.get('assignment_rows') or []) == list(want.get('assignment_rows') or [])
        and list(had.get('errata') or []) ==
            list(extraction.errata_for(course, key, sources or [])['inputs']))
    if recorded == current['sources_hash'] and same_inputs:
        rows.append(_row(8, 'freshness', 'fail', 'skip',
                         'sources_hash and inputs both match the last run; this '
                         'lesson is skipped and reported.',
                         sources_hash=recorded))
    else:
        rows.append(_row(8, 'freshness', 'pass', 'skip',
                         'inputs changed since the last run',
                         was=recorded, now=current['sources_hash'],
                         inputs_changed=not same_inputs))


def _check_9(folder: Path, rows: list):
    """Detection only. The file is never opened: D87 stands, and the count of
    corrections is skill D's to report."""
    path = folder / 'notes_corrections.md'
    if path.is_file():
        rows.append(_row(9, 'corrections', 'warn', 'warn',
                         'this lesson has corrections. Regenerating the notes '
                         'overwrites them, so they will need replaying. The file '
                         'is detected, never opened; run course-corrections '
                         'replay after this run.', path=str(path)))
    else:
        rows.append(_row(9, 'corrections', 'pass', 'warn', 'no correction log'))


def _check_structure(course: Path, rows: list):
    missing = [n for n in ('Articles', 'Videos', 'Links')
               if not (course / n).is_dir()]
    if missing:
        rows.append(_row('S1', 'course_folders', 'fail', 'ask',
                         f'{", ".join(missing)}/ missing at course root. This '
                         'skill writes shared notes into them and creates no '
                         'visible folder; run course-setup validate.'))
    has_notes = any(course.rglob('*_Final_notes.md'))
    for name, why in (('terms.json',
                       'definitions in this lesson would drift from every '
                       'earlier lesson, invisibly'),
                      ('concepts.json',
                       'skill C keys its revision history on concept IDs; '
                       'starting empty silently orphans that history')):
        p = course / '.data' / name
        if p.is_file():
            try:
                json.loads(p.read_text(encoding='utf-8') or '{}')
                continue
            except json.JSONDecodeError:
                rows.append(_row('S2', name, 'fail', 'ask',
                                 f'{name} is corrupt. {why}. Offer to rebuild it; '
                                 'never start empty silently.'))
                continue
        if has_notes:
            rows.append(_row('S2', name, 'fail', 'ask',
                             f'{name} is missing while this course already has '
                             f'notes. {why}. Offer to start a new one only on '
                             'confirmation.'))
        else:
            rows.append(_row('S2', name, 'pass', 'ask',
                             f'{name} absent on a course with no notes yet; it '
                             'is created empty without stopping.',
                             create='{}'))


# ------------------------------------------------------------------ driver

def check(course: Path | str, key: str, vault: Path | str | None = None,
          sources: list[str] | None = None, batch: bool = False) -> dict:
    course = Path(course)
    rows: list[dict] = []
    data = ov.load(course)
    folder = _lesson_folder(course, key)
    content = _check_1(course, key, folder, rows)
    code = _check_1b(course, Path(vault) if vault else None, data, rows)
    if content is None:
        return _finish(course, key, rows, None)

    scope = build_scope(course, key)
    _check_2_3(scope, rows)
    _check_2b(content, rows)
    _check_4(content, folder, rows)
    _check_5(course, key, folder, content, data, rows)
    _check_5b(course, key, present(course, key, folder, content, data), data, rows)
    _check_6(course, key, data, rows)
    _check_7(scope, content, rows)
    _check_8(course, key, code, folder, sources, batch, rows)
    _check_9(folder, rows)
    _check_structure(course, rows)
    if scope['quarantine_breach']:
        rows.append(_row('Q', 'quarantine', 'fail', 'hard',
                         'a file under Explanations/ reached the scope builder. '
                         'It is tutor output and must never be a lesson source.',
                         files=scope['quarantine_breach']))
    return _finish(course, key, rows, scope)


def _finish(course: Path, key: str, rows: list, scope: dict | None) -> dict:
    hard = [r for r in rows if r['status'] == 'fail' and r['severity'] == 'hard']
    ask = [r for r in rows if r['status'] == 'fail' and r['severity'] == 'ask']
    skip = [r for r in rows if r['status'] == 'fail' and r['severity'] == 'skip']
    warn = [r for r in rows if r['status'] == 'warn']
    return {'course': str(course), 'lesson': key, 'checks': rows,
            'hard_fail': hard, 'stop_and_ask': ask, 'skip': skip, 'warn': warn,
            'proceed': not hard and not ask and not skip,
            'scope_files': len(scope['files']) if scope else 0,
            'explanations_excluded': True,
            'lesson_folder': scope['lesson_folder'] if scope else None}


def sources_record(course: Path | str, key: str, sources: list[str]) -> dict:
    """`sources_hash`, `sources_stat` and `inputs` for the notes frontmatter.

    Lesson-relative entries resolve against the lesson folder, course-relative
    ones (`Books/`, `Assignments/`) against the course; one base cannot serve
    both, so each entry is resolved before hashing.
    """
    course = Path(course)
    folder = _lesson_folder(course, key)
    staged, base_map = [], {}
    for entry in sources:
        rel = entry.split('#', 1)[0]
        head = rel.split('/', 1)[0].lower()
        base = course if head in ('books', 'assignments') else folder
        base_map[entry] = base
        staged.append(entry)
    # source_hash takes one base, so group by base and fold the two digests.
    out_hash, stat_rows, missing = [], [], []
    for base in {str(v) for v in base_map.values()}:
        subset = [e for e in staged if str(base_map[e]) == base]
        h = sh.sources_hash(base, subset)
        out_hash.append(h)
        s = sh.sources_stat(base, subset)
        stat_rows += s['sources_stat']
        missing += h['missing']
    per_file = sorted((f for h in out_hash for f in h['per_file']),
                      key=lambda r: r['entry'])
    import hashlib
    outer = hashlib.sha256()
    for row in per_file:
        outer.update(row['entry'].encode('utf-8')); outer.update(b'\x00')
        outer.update(row['sha256'].encode('ascii')); outer.update(b'\x00')
    errata = extraction.errata_for(course, key, sources)
    inputs = ov.inputs_for(course, key)
    inputs['errata'] = errata['inputs']
    return {'sources': sources, 'sources_hash': outer.hexdigest()[:32],
            'per_file': per_file, 'sources_stat': stat_rows,
            'missing': sorted(set(missing)), 'inputs': inputs,
            'complete': not missing}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('check', 'scope', 'sources'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True)
        p.add_argument('--lesson', required=True)
        if name != 'scope':
            p.add_argument('--sources', nargs='*', default=[])
        if name == 'check':
            p.add_argument('--vault')
            p.add_argument('--batch', action='store_true')
    args = ap.parse_args(argv)

    if args.cmd == 'check':
        out = check(args.course, args.lesson, args.vault, args.sources, args.batch)
    elif args.cmd == 'scope':
        out = build_scope(args.course, args.lesson)
    else:
        out = sources_record(args.course, args.lesson, args.sources)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
