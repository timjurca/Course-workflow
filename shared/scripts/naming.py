#!/usr/bin/env python3
"""Names: slugify, validation, course codes, lesson folders.

Normative source for all of it is shared/folder-structure.md sections 2 and 3.
This module is the only implementation; nothing else re-derives a slug, because
two slug functions produce two file names for the same source and neither side
notices until a link breaks.

CLI:
    naming.py slugify "Some Text"            [--no-cap]
    naming.py check-code ECON
    naming.py parse-folder 03_2026-03-12
    naming.py strip-code ECON_L03_Final_notes.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

# Obsidian and the filesystem both choke on these; see folder-structure.md section 2.
FORBIDDEN = set('#^[]|:')

SLUG_MAX = 60

LESSON_FOLDER_RE = re.compile(r'^(?P<num>\d{2})_(?P<date>\d{4}-\d{2}-\d{2})$')
CODE_RE = re.compile(r'^[A-Z0-9]{2,8}$')
# A course folder is <CODE>_<Course_Name>, optionally preceded by a two-digit sort
# prefix: 01_EBT_Emerging_and_breakthrough_Technologies. The prefix carries the
# teaching order within a term, which alphabetical sorting alone would lose, and
# nothing in the plugin reads the folder name for meaning: every skill keys on
# `code:` in the overview frontmatter.
COURSE_FOLDER_RE = re.compile(
    r'^(?:(?P<order>\d{2})_)?(?P<code>[A-Z0-9]{2,8})_(?P<name>.+)$')
# A leading course-code token: uppercase/digits, then an underscore.
CODE_TOKEN_RE = re.compile(r'^[A-Z0-9]{2,8}_')
LESSON_TOKEN_RE = re.compile(r'\b([LT])(\d{2})\b')

CONTENT_PREFIXES = ('slides_', 'transcript_', 'notes_', 'handout_')

FIXED_FOLDERS = (
    'Lessons', 'Tutorials', 'Books', 'Articles', 'Videos', 'Links', 'Explanations',
    'Content', 'Final_notes', 'Assignments', 'Exams', 'Past_exams', 'Mock_exams',
    'Revision_questions',
)

# Folders whose canonical spelling we can recognise through a common mis-spelling.
# Used by A's validate to propose a rename rather than to apply one.
FOLDER_ALIASES = {
    'content': 'Content', 'final notes': 'Final_notes', 'finalnotes': 'Final_notes',
    'final_notes': 'Final_notes', 'lessons': 'Lessons', 'predavanja': 'Lessons',
    'tutorials': 'Tutorials', 'vaje': 'Tutorials', 'books': 'Books', 'knjige': 'Books',
    'articles': 'Articles', 'clanki': 'Articles', 'videos': 'Videos',
    'links': 'Links', 'povezave': 'Links', 'assignments': 'Assignments',
    'naloge': 'Assignments', 'exams': 'Exams', 'izpiti': 'Exams',
    'past_exams': 'Past_exams', 'mock_exams': 'Mock_exams',
    'revision_questions': 'Revision_questions', 'explanations': 'Explanations',
}


def transliterate(text: str) -> str:
    """Diacritics to ASCII. Handled explicitly where NFKD alone gets it wrong."""
    explicit = {
        'đ': 'd', 'Đ': 'D', 'ø': 'o', 'Ø': 'O', 'ß': 'ss',
        'æ': 'ae', 'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE', 'ł': 'l', 'Ł': 'L',
    }
    text = ''.join(explicit.get(ch, ch) for ch in text)
    decomposed = unicodedata.normalize('NFKD', text)
    return ''.join(ch for ch in decomposed if not unicodedata.combining(ch))


def strip_forbidden(name: str) -> str:
    return ''.join(ch for ch in name if ch not in FORBIDDEN)


def slugify(text: str, cap: bool = True) -> str:
    """folder-structure.md section 3, in order.

    `cap=False` is for extraction file names, which must stay unique per source
    and are therefore exempt from the length cap.
    """
    s = transliterate(text).lower()
    s = re.sub(r'[\s\-./\\]+', '_', s)
    s = strip_forbidden(s)
    s = re.sub(r'[^a-z0-9_]+', '', s)
    s = re.sub(r'_+', '_', s).strip('_')
    if cap and len(s) > SLUG_MAX:
        cut = s[:SLUG_MAX]
        if '_' in cut:
            cut = cut.rsplit('_', 1)[0]
        s = cut.strip('_')
    return s


def clean_title(text: str) -> str:
    """Book and article names: transliterate and strip, keep capitalisation."""
    s = transliterate(text)
    s = re.sub(r'[\s]+', '_', s)
    s = strip_forbidden(s)
    return re.sub(r'_+', '_', s).strip('_')


def check_code(code: str) -> dict:
    ok = bool(CODE_RE.match(code or ''))
    reason = None
    if not ok:
        if not code:
            reason = 'empty'
        elif not code.isupper():
            reason = 'must be uppercase A-Z and digits'
        elif len(code) < 2 or len(code) > 8:
            reason = 'must be 2 to 8 characters'
        else:
            reason = 'only A-Z and digits are allowed'
    return {'code': code, 'ok': ok, 'reason': reason}


def suggest_code(course_name: str, taken: set[str] | None = None) -> str:
    """A first guess only; A always shows it and the student may change it."""
    taken = {c.upper() for c in (taken or set())}
    words = [w for w in re.split(r'[^A-Za-z0-9]+', transliterate(course_name)) if w]
    candidates = []
    if len(words) >= 2:
        candidates.append(''.join(w[0] for w in words)[:8].upper())
    if words:
        candidates.append(words[0][:4].upper())
        candidates.append(words[0][:6].upper())
    candidates = [c for c in candidates if CODE_RE.match(c)]
    for cand in candidates:
        if cand not in taken:
            return cand
    base = candidates[0] if candidates else 'CRS'
    for n in range(2, 100):
        cand = f'{base[:6]}{n}'
        if CODE_RE.match(cand) and cand not in taken:
            return cand
    return base


def concept_id(heading: str) -> str:
    """A concept ID from a section heading. **Hyphenated, not slugified.**

    `slugify` maps spaces and hyphens to underscores, which is right for file
    names. A concept ID is not a file name: it appears inside
    `<!-- concept: instrument-relevance -->`, inside
    `Explanations/<CODE>_<concept-id>_Explained.md`, and in a JSON key, and every
    one of those is matched as `[a-z0-9-]+`. An underscored id would be rejected
    by the stray-explain-file check in course-setup's validate, so the two forms
    are deliberately different functions rather than one with a flag.
    """
    return slugify(heading).replace('_', '-').strip('-')


def parse_course_folder(name: str) -> dict | None:
    """Split a course folder name into its optional sort prefix, code and name."""
    m = COURSE_FOLDER_RE.match(name)
    if not m:
        return None
    return {'order': m.group('order'), 'code': m.group('code'),
            'name': m.group('name')}


def course_folder_matches_code(name: str, code: str) -> bool:
    """Does this folder name belong to this course code?

    Used by validate to catch a hand-edited disagreement between the folder and
    `code:`. Either value could be the intended one, so a mismatch is always a
    proposal and never a silent repair.
    """
    parsed = parse_course_folder(name)
    return bool(parsed and parsed['code'] == code)


def parse_lesson_folder(name: str) -> dict | None:
    m = LESSON_FOLDER_RE.match(name)
    if not m:
        return None
    return {'num': m.group('num'), 'date': m.group('date')}


def strip_code_token(name: str) -> str:
    """Drop a leading <CODE>_ so a course-code rename costs no comparison.

    Path-aware: the token is stripped from the **last segment**, and the
    directory part is kept. Called on a path (`Content/ECON_x.md`) an
    anchored-at-the-start version silently does nothing, which reads as "this
    file is unchanged" and makes a renamed source look newly filed.
    """
    head, sep, tail = str(name).rpartition('/')
    return head + sep + CODE_TOKEN_RE.sub('', tail, count=1)


def names_match(a: str, b: str) -> bool:
    """Compare two file names ignoring the course-code token."""
    return strip_code_token(a) == strip_code_token(b)


def canonical_folder(name: str) -> str | None:
    """The canonical spelling of a fixed folder name, or None if unrecognised."""
    if name in FIXED_FOLDERS:
        return name
    return FOLDER_ALIASES.get(name.strip().lower().replace('-', '_'))


def content_prefix(filename: str) -> str | None:
    for p in CONTENT_PREFIXES:
        if filename.lower().startswith(p):
            return p[:-1]
    return None


def has_forbidden(name: str) -> list[str]:
    return sorted({ch for ch in name if ch in FORBIDDEN})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('slugify')
    p.add_argument('text')
    p.add_argument('--no-cap', action='store_true')

    p = sub.add_parser('clean-title')
    p.add_argument('text')

    p = sub.add_parser('check-code')
    p.add_argument('code')

    p = sub.add_parser('suggest-code')
    p.add_argument('course_name')
    p.add_argument('--taken', nargs='*', default=[])

    p = sub.add_parser('parse-folder')
    p.add_argument('name')

    p = sub.add_parser('strip-code')
    p.add_argument('filename')

    p = sub.add_parser('concept-id')
    p.add_argument('heading')

    p = sub.add_parser('canonical-folder')
    p.add_argument('name')

    p = sub.add_parser('parse-course-folder')
    p.add_argument('name')

    args = ap.parse_args(argv)
    if args.cmd == 'slugify':
        out = {'slug': slugify(args.text, cap=not args.no_cap)}
    elif args.cmd == 'clean-title':
        out = {'name': clean_title(args.text)}
    elif args.cmd == 'check-code':
        out = check_code(args.code)
    elif args.cmd == 'suggest-code':
        out = {'code': suggest_code(args.course_name, set(args.taken))}
    elif args.cmd == 'parse-folder':
        out = {'parsed': parse_lesson_folder(args.name)}
    elif args.cmd == 'strip-code':
        out = {'stripped': strip_code_token(args.filename)}
    elif args.cmd == 'concept-id':
        out = {'concept_id': concept_id(args.heading)}
    elif args.cmd == 'parse-course-folder':
        out = {'parsed': parse_course_folder(args.name)}
    else:
        out = {'canonical': canonical_folder(args.name)}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
