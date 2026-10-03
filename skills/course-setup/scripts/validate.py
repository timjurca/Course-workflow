#!/usr/bin/env python3
"""Scan a course against the naming contract and return findings by class.

Runs on **every** invocation of this skill, not only when asked: as the first
step of init (to detect an existing course) and as the last step of file.

Three classes, and the split is the whole point:

  auto     cannot lose data. Applied without asking.
  propose  touches an existing file. Shown, confirmed, then applied.
  report   not this skill's to touch, or needs a decision.

**Read-only mode is not optional on a non-conforming folder.** When the resolved
folder is not yet a course, every finding becomes a proposal instead, because
init and adoption both promise that nothing is written before approval and
validate runs before that approval.

Two of the report rows are a **standing tripwire** rather than a check
(quarantine breach, stray explain file). They verify a boundary maintained in
other skills' specs, so a later edit to the notes skill can break it without
touching the explain skill. A check run once at install cannot catch a
regression arriving in month four; this one runs every time.

CLI:
    validate.py scan --course <path> [--vault <path>] [--read-only] [--apply-auto]
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
import classify                                                    # noqa: E402
import icloud                                                      # noqa: E402
import naming
import presence                                                      # noqa: E402
import overview as ov                                              # noqa: E402
import scaffold                                                    # noqa: E402
from vault import (course_kind, read_config, read_frontmatter,     # noqa: E402
                   write_config, write_frontmatter)

STAMPED_FILES = ['Weekly_overview.md', 'Table_of_contents.md', '_Structure.md']
ARCHIVE_LIMIT_MB = 50
EXPLAIN_NAME_RE = re.compile(r'^[A-Z0-9]{2,8}_[a-z0-9-]+_Explained\.md$')
NOTES_NAME_RE = re.compile(r'^[A-Z0-9]{2,8}_[LT]\d{2}_Final_notes\.md$')
ARTICLE_EXT = {'.pdf'}


def _check_expects(course: Path, data: dict, fm: dict, findings: list):
    """Propose `expects` entries the course clearly has but never declared.

    `expects` is what skill B gates a run on, and a category nobody declared is
    exactly the one that goes missing unnoticed. EBT carries a transcript and
    the student's own notes in nearly every lesson and declares neither, so a
    lesson missing them was processed in silence with a whole priority layer
    absent and coverage still reporting 100%.

    Proposal only: this rewrites the student's own Weekly_overview.
    """
    declared = fm.get('expects') or []
    if isinstance(declared, str):
        declared = [x.strip() for x in declared.strip('[]').split(',') if x.strip()]
    declined = fm.get('expects_declined') or []
    if isinstance(declined, str):
        declined = [x.strip() for x in declined.strip('[]').split(',') if x.strip()]
    rows = presence.across_lessons(Path(course), data)
    if len(rows) < 2:
        return                      # nothing to generalise from yet
    counts = {}
    for ev in rows.values():
        for tok, has in ev.items():
            if has:
                counts[tok] = counts.get(tok, 0) + 1
    missing = [{'token': t, 'in': n, 'of': len(rows)}
               for t, n in sorted(counts.items())
               if t not in declared and t not in declined
               and t in presence.STAPLES and n == len(rows)]
    if missing:
        names = ', '.join(m['token'] for m in missing)
        findings.append(_f('propose', 'expects_incomplete',
                           f'every lesson in this course has {names}, and '
                           'Weekly_overview declares neither it nor a decline. '
                           'Until it is declared, a lesson that loses it is '
                           'processed without anyone being told.',
                           path='Weekly_overview.md', tokens=missing,
                           fix=f'add {names} to expects:, or to expects_declined:'))


def _f(cls, code, message, **extra):
    row = {'class': cls, 'code': code, 'message': message}
    row.update(extra)
    return row


def _lesson_dirs(course: Path):
    for kind in ('Lessons', 'Tutorials'):
        root = course / kind
        if not root.is_dir():
            continue
        for p in sorted(root.iterdir()):
            if p.is_dir() and not p.name.startswith('.'):
                yield kind, p


def _has_notes(course: Path) -> bool:
    return any(course.rglob('*_Final_notes.md'))


def _dir_size_mb(path: Path) -> float:
    total = 0
    for p in path.rglob('*'):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return round(total / (1024 * 1024), 1)


# ---------------------------------------------------------------- the checks

def check_scaffolding(course: Path, findings: list, has_notes: bool):
    for rel in ['_Inbox', '_Inbox/_conflicts', '_Inbox/_undone',
                'Articles', 'Videos', 'Links']:
        if not (course / rel).is_dir():
            findings.append(_f('auto', 'missing_folder',
                               f'{rel}/ is missing', path=rel, fix='create'))
    if not (course / 'Table_of_contents.md').is_file():
        findings.append(_f('auto', 'missing_toc', 'Table_of_contents.md is missing',
                           path='Table_of_contents.md', fix='create skeleton'))
    if not (course / '_Structure.md').is_file():
        findings.append(_f('auto', 'missing_structure', '_Structure.md is missing',
                           path='_Structure.md', fix='create'))
    terms = course / '.data' / 'terms.json'
    if not terms.is_file():
        if has_notes:
            findings.append(_f('report', 'terms_lost',
                               'the term ledger is missing while notes exist. It is '
                               'never recreated silently: an empty ledger would let '
                               'every later lesson redefine terms the earlier ones '
                               'already fixed. Decide whether to rebuild it.',
                               path='.data/terms.json'))
        else:
            findings.append(_f('auto', 'missing_terms',
                               '.data/terms.json is missing and the course has no '
                               'notes yet', path='.data/terms.json',
                               fix='create empty'))
    exams = course / 'Exams'
    if exams.is_dir():
        for sub in ('Past_exams', 'Mock_exams', 'Revision_questions'):
            if not (exams / sub).is_dir():
                findings.append(_f('auto', 'partial_exams_tree',
                                   f'Exams/{sub}/ is missing from an existing Exams tree',
                                   path=f'Exams/{sub}', fix='create'))
    for rel in STAMPED_FILES:
        p = course / rel
        if not p.is_file():
            continue
        try:
            fm, _ = read_frontmatter(p)
        except Exception:
            continue
        if fm.get('scaffolded_by') != 'course-setup v1':
            findings.append(_f('auto', 'stamp', f'{rel} has no current scaffolded_by',
                               path=rel, fix='set scaffolded_by: course-setup v1'))
    for rel in ['Course_description.md', 'Learning_objectives.md', 'Literature.md']:
        p = course / rel
        if p.is_file() and not p.read_text(encoding='utf-8', errors='replace').strip():
            findings.append(_f('propose', 'empty_prose_file',
                               f'{rel} is empty. The notes skill reads it as '
                               'background context, and an empty file reads as '
                               '"this course has none".', path=rel,
                               fix='delete it or fill it in'))


def check_identity(course: Path, data: dict, findings: list):
    fm = data.get('frontmatter') or {}
    code = fm.get('code')
    if not code:
        findings.append(_f('propose', 'no_code',
                           'Weekly_overview.md has no code:. Every generated file '
                           'name depends on it.', path='Weekly_overview.md',
                           fix='ask for a code and write it'))
        return
    _check_expects(course, data, fm, findings)
    chk = naming.check_code(str(code))
    if not chk['ok']:
        findings.append(_f('propose', 'bad_code',
                           f'code: "{code}" is not conforming ({chk["reason"]})',
                           path='Weekly_overview.md',
                           fix=f'propose {naming.suggest_code(str(fm.get("course") or code))}'))
    if not naming.course_folder_matches_code(course.name, str(code)):
        findings.append(_f('propose', 'code_folder_mismatch',
                           f'the folder is "{course.name}" but code: is "{code}". '
                           'A course folder is <CODE>_<Course_Name>, optionally with '
                           'a two-digit sort prefix (01_EBT_...). One of them was '
                           'edited by hand and either could be the intended value, so '
                           'this is never repaired silently.',
                           path=str(course.name), fix='ask which is intended'))


def check_lessons(course: Path, data: dict, findings: list):
    rows = {r.get('key'): r for r in data.get('rows', []) if r.get('key')}
    seen_numbers: dict[str, list[str]] = {}
    on_disk = set()

    for kind, folder in _lesson_dirs(course):
        parsed = naming.parse_lesson_folder(folder.name)
        prefix = 'L' if kind == 'Lessons' else 'T'
        if not parsed:
            findings.append(_f('propose', 'lesson_folder_name',
                               f'{kind}/{folder.name} does not match NN_YYYY-MM-DD',
                               path=f'{kind}/{folder.name}',
                               fix='rename; a folder rename is followed by a link '
                                   'rewrite and check'))
            continue
        key = f'{prefix}{parsed["num"]}'
        on_disk.add(key)
        seen_numbers.setdefault(key, []).append(folder.name)

        for sub in ('Content', 'Final_notes'):
            if not (folder / sub).is_dir():
                findings.append(_f('auto', 'missing_lesson_subfolder',
                                   f'{kind}/{folder.name}/{sub}/ is missing',
                                   path=f'{kind}/{folder.name}/{sub}', fix='create'))

        row = rows.get(key)
        if row is None:
            same = [r for r in data.get('rows', []) if r.get('key') == key]
            findings.append(_f('auto', 'missing_overview_row',
                               f'{key} has a folder but no Weekly_overview row',
                               path=f'{kind}/{folder.name}', lesson=key,
                               date=parsed['date'],
                               fix='append the row with Topic, Book and Chapters '
                                   'blank, then report it as needing completion'))
        elif (row.get('Date') or '').strip() != parsed['date']:
            findings.append(_f('propose', 'date_mismatch',
                               f'{key}: the folder says {parsed["date"]}, the '
                               f'overview row says {row.get("Date")!r}. A rescheduled '
                               'lecture updates the existing row; it never gets a '
                               'second row with the same number.',
                               path=f'{kind}/{folder.name}', lesson=key))
        else:
            reading = ov.resolve_reading(data, key)
            if reading['status'] in ('incomplete', 'missing_row'):
                findings.append(_f('report', 'row_incomplete',
                                   f'{key}: the overview row has no reading. A blank '
                                   'cell is not neutral — the notes skill would pass '
                                   'its chapter check vacuously and write notes with a '
                                   'whole priority-1 source missing, while coverage '
                                   'reported 100%.', lesson=key,
                                   row=row.get('_raw')))
            elif reading['status'] == 'broken_chain':
                findings.append(_f('propose', 'broken_cont_chain',
                                   f'{key}: "cont." cannot be resolved '
                                   f'({reading.get("reason")})', lesson=key,
                                   fix='fill in the reading, or point cont. at a row '
                                       'that has one'))

    for key, folders in seen_numbers.items():
        if len(folders) > 1:
            findings.append(_f('propose', 'duplicate_lesson_number',
                               f'{key}: two folders resolve to the same number '
                               f'({", ".join(folders)}). Stop and ask — this cannot '
                               'be chosen automatically, and it breaks the L<NN> '
                               'file-name scheme.', lesson=key))

    counts: dict[str, int] = {}
    for r in data.get('rows', []):
        if r.get('key'):
            counts[r['key']] = counts.get(r['key'], 0) + 1
    for key, n in counts.items():
        if n > 1:
            findings.append(_f('propose', 'duplicate_overview_row',
                               f'{key}: {n} rows with the same Type and No. The notes '
                               'skill reads "the current lesson\'s row" and would pick '
                               'one arbitrarily.', lesson=key,
                               fix='merge into the row whose date matches a folder'))
    for key in rows:
        if key not in on_disk:
            findings.append(_f('report', 'row_without_folder',
                               f'{key}: a row with no folder on disk. Normal for a '
                               'future lesson.', lesson=key))



LESSON_ROOT_DIRS = {'content', 'articles', 'final_notes'}
LESSON_ROOT_FILES = {'notes_corrections.md'}
OVERVIEW_RE = re.compile(r'^[A-Z0-9]{2,8}_[LT]\d{2}_Overview\.md$')


def check_lesson_root_files(course: Path, findings: list):
    """Anything unrecognised sitting at a lesson or tutorial folder root.

    The dangerous case is lecturer-published material dropped beside `Content/`
    rather than inside it: a week description listing the required reading, a
    briefing, an errata note. Nothing reads a lesson folder's root except this
    check, so such a file is invisible to the notes skill, which then produces
    notes missing a priority-1 source **while reporting complete coverage**. The
    coverage guarantee is over what Pass A extracted, and Pass A never saw it.

    Observed twice in one vault: `week_overview.md` at the root of two different
    lessons in two different courses, both carrying the week's required reading,
    neither ever read.
    """
    for kind, folder in _lesson_dirs(course):
        rel_base = f'{kind}/{folder.name}'
        for p in sorted(folder.iterdir()):
            if p.name.startswith('.') or classify.is_ignored(p):
                continue
            if p.is_dir():
                if p.name.lower() not in LESSON_ROOT_DIRS:
                    findings.append(_f('report', 'unknown_lesson_folder',
                                       f'{rel_base}/{p.name}/ is not one of '
                                       'Content/, Articles/ or Final_notes/',
                                       path=f'{rel_base}/{p.name}'))
                continue
            if p.name.lower() in LESSON_ROOT_FILES or OVERVIEW_RE.match(p.name):
                continue
            findings.append(_f('propose', 'stray_lesson_file',
                               f'{rel_base}/{p.name} sits at the lesson root, '
                               'where nothing reads it. Only the overview, '
                               'notes_corrections.md and the three subfolders '
                               'belong here.',
                               path=f'{rel_base}/{p.name}',
                               fix='classify it and move it into Content/ under '
                                   'the matching prefix, or say it is not course '
                                   'material'))


def check_content_files(course: Path, findings: list):
    for kind, folder in _lesson_dirs(course):
        content = folder / 'Content'
        if not content.is_dir():
            continue
        rel_base = f'{kind}/{folder.name}'
        for p in sorted(content.iterdir()):
            # Same exclusion as check_lesson_root above and as formats.md
            # requires. Without it an Office lock file is reported as no_prefix
            # on every run, for as long as it sits there.
            if p.is_dir() or classify.is_ignored(p):
                continue
            rel = f'{rel_base}/Content/{p.name}'
            if p.name in ('videos.md', 'video.md') or re.match(r'^links_.*\.md$', p.name):
                continue
            bad = naming.has_forbidden(p.name)
            if bad:
                findings.append(_f('propose', 'forbidden_characters',
                                   f'{rel} contains {" ".join(bad)}', path=rel,
                                   fix='replace each with _'))
            if p.name.lower().startswith('book_'):
                findings.append(_f('propose', 'book_prefix',
                                   f'{rel} uses the retired book_ prefix. Books are '
                                   'identified by living in Books/, never by a prefix.',
                                   path=rel, fix='move to Books/'))
                continue
            if naming.content_prefix(p.name):
                continue
            findings.append(_f('propose', 'no_prefix',
                               f'{rel} has no recognised prefix '
                               '(slides_, transcript_, notes_, handout_)', path=rel,
                               fix='classify it and rename with the inferred prefix'))
        for p in sorted(content.glob('*.pdf')):
            findings.append(_f('report', 'pdf_in_content',
                               f'{rel_base}/Content/{p.name} is a PDF in Content/. '
                               'Often legitimate (the student\'s own notes or a '
                               'handout exported as PDF, which belong here with a '
                               'notes_ or handout_ prefix), but an assigned article '
                               'belongs in the lesson\'s Articles/ and a book in '
                               'Books/. Classify it before proposing a move.',
                               path=f'{rel_base}/Content/{p.name}'))
        for p in sorted(folder.rglob('*')):
            if p.is_file() and p.suffix.lower() == '.pdf' \
                    and p.parent.name != 'Articles' and not classify.is_ignored(p):
                # `import classify` used to sit here, which made the name local to
                # this whole function and shadowed the module-level import above.
                # Harmless while nothing earlier in the function touched it; an
                # UnboundLocalError the moment anything did.
                try:
                    kindinfo = classify.classify(p, peek=True)
                except Exception:
                    continue
                if kindinfo['kind'] == 'book' and kindinfo['confidence'] == 'high':
                    findings.append(_f('propose', 'book_in_lesson',
                                       f'{p.relative_to(course)} looks like a book '
                                       f'({kindinfo["reasons"][-1]}). Books live in '
                                       'Books/ at the course root, never in a lesson.',
                                       path=str(p.relative_to(course)),
                                       fix='move to Books/'))


def check_folder_spellings(course: Path, findings: list):
    for p in sorted(course.iterdir()):
        if not p.is_dir() or p.name.startswith('.') or p.name.startswith('_'):
            continue
        canon = naming.canonical_folder(p.name)
        if canon and canon != p.name:
            findings.append(_f('propose', 'folder_spelling',
                               f'{p.name}/ should be {canon}/. A localised or re-cased '
                               'folder name is invisible to every later run of every '
                               'skill.', path=p.name, fix=f'rename to {canon}'))


def check_books(course: Path, findings: list):
    books = course / 'Books'
    if not books.is_dir():
        return
    # A serialised book is a folder of chapter files, so a book with no index is
    # not only a loose .pdf. Missed here, a reader delivered chapter by chapter
    # would silently never get an index and every Chapters cell would resolve to
    # a chapter number with no pages behind it.
    for d in sorted(books.iterdir()):
        if not d.is_dir() or d.name.startswith('.'):
            continue
        chapters = [f for f in d.iterdir()
                    if f.is_file() and f.suffix.lower() in {'.pdf', '.docx', '.epub', '.md'}]
        if not chapters:
            continue
        index = books / f'{d.name}.index.md'
        if index.is_file():
            continue
        findings.append(_f('propose', 'serialised_book_without_index',
                           f'Books/{d.name}/ holds {len(chapters)} chapter files but has '
                           f'no Books/{d.name}.index.md. Without it a Chapters cell '
                           'resolves to a chapter number with no file or page range '
                           'behind it.', path=f'Books/{d.name}',
                           fix='build the serialised index'))
    for p in sorted(books.iterdir()):
        if p.suffix.lower() not in {'.pdf', '.epub'} or p.name.startswith('.'):
            continue
        # A *_ocr.pdf is a searchable copy of the book beside it, not a second
        # book. It shares the original's index, so proposing one of its own
        # would be a standing false finding for the life of the course.
        if p.stem.endswith('_ocr') and (books / f'{p.stem[:-4]}.index.md').is_file():
            continue
        index = p.with_suffix('.index.md')
        if index.is_file():
            try:
                fm, _ = read_frontmatter(index)
            except Exception:
                fm = {}
            if fm.get('descriptions') == 'partial':
                findings.append(_f('report', 'index_partial',
                                   f'Books/{index.name}: the description pass was '
                                   'interrupted. It resumes from the last written '
                                   'section; it never restarts.',
                                   path=f'Books/{index.name}'))
            continue
        declined = False
        for other in books.glob('*.index.md'):
            try:
                fm, _ = read_frontmatter(other)
            except Exception:
                continue
            if fm.get('file') == p.name and fm.get('descriptions') == 'declined':
                declined = True
        if not declined:
            findings.append(_f('propose', 'book_without_index',
                               f'Books/{p.name} has no index. The notes skill resolves '
                               'chapter ranges through it. Building it is proposed, '
                               'never automatic: it can need a chapter-to-page mapping '
                               'from you, and this scan runs on every invocation.',
                               path=f'Books/{p.name}', fix='build the index'))


def check_icloud(course: Path, findings: list):
    res = icloud.scan(course, exclude=['.work/**', '.data/history/**'])
    for row in res['placeholders']:
        findings.append(_f('report', 'icloud_placeholder',
                           f'{row["path"]} is not downloaded ({", ".join(row["signals"])}). '
                           'Reading it would return empty content. The fix is in Finder.',
                           path=row['path']))
    for row in res['conflicts']:
        where = 'inside a lesson folder' if '/Lessons/' in row['path'] or \
            '/Tutorials/' in row['path'] else 'in _Inbox/'
        if where.endswith('_Inbox/'):
            findings.append(_f('propose', 'icloud_conflict_inbox',
                               f'{row["path"]} is an iCloud conflicted copy in _Inbox/',
                               path=row['path'],
                               fix='quarantine it and its original into _Inbox/_conflicts/'))
        else:
            findings.append(_f('report', 'icloud_conflict_filed',
                               f'{row["path"]} is a conflicted copy of a file that is '
                               'already filed. It is reported and not moved: a filed '
                               'file is content the notes may depend on, and moving it '
                               'would change a lesson\'s source set.',
                               path=row['path']))


def check_archives(course: Path, findings: list):
    roots = []
    for kind, folder in _lesson_dirs(course):
        h = folder / '.work' / 'history'
        if h.is_dir():
            roots.append(h)
    for rel in ['Exams/.work/history', '.data/history', 'Explanations/.history']:
        p = course / rel
        if p.is_dir():
            roots.append(p)
    total = sum(_dir_size_mb(r) for r in roots)
    if total > ARCHIVE_LIMIT_MB:
        findings.append(_f('report', 'archives_large',
                           f'archive folders total {total} MB across '
                           f'{len(roots)} locations, including the corrections skill\'s '
                           '_pre-c-<id> versions and the explain skill\'s history. '
                           'No skill prunes archives automatically. A cleanup of '
                           'everything older than the last 5 versions can be run on '
                           'request, and it needs a per-session delete grant first.',
                           size_mb=total,
                           locations=[str(r.relative_to(course)) for r in roots]))


def check_quarantine(course: Path, findings: list):
    """The standing tripwire. Two rows, reported and never auto-fixed.

    Row 1 is load-bearing: if the notes skill ever ingests a saved explanation,
    model prose enters sources_hash, becomes notes, the revision skill writes
    exam questions from it, and the corrections skill corrects against it. The
    student then revises from model output believing it is the lecturer's.

    It is not auto-fixed because deleting the path from the frontmatter would
    not remove the ingested prose from the body. The remedy is to restore the
    quarantine rule in the notes skill and re-run notes for that lesson.
    """
    for notes in course.rglob('Final_notes/*_Final_notes.md'):
        try:
            fm, _ = read_frontmatter(notes)
        except Exception:
            continue
        blob = json.dumps({k: fm.get(k) for k in ('sources', 'sources_stat', 'inputs')},
                          default=str)
        if 'Explanations/' in blob:
            findings.append(_f('report', 'quarantine_breach',
                               f'WARNING: {notes.relative_to(course)} names a path under '
                               'Explanations/ in sources, sources_stat or inputs. Tutor '
                               'prose has been ingested as course material. Not '
                               'auto-fixed: removing the path would not remove the '
                               'prose from the body. Restore the quarantine rule in the '
                               'notes skill, then re-run notes for that lesson.',
                               path=str(notes.relative_to(course)), severity='warning'))
    expl = course / 'Explanations'
    if expl.is_dir():
        for p in sorted(expl.rglob('*')):
            if p.is_dir() or '.history' in p.parts:
                continue
            if not EXPLAIN_NAME_RE.match(p.name):
                findings.append(_f('report', 'stray_explain_file',
                                   f'WARNING: Explanations/{p.relative_to(expl)} does '
                                   'not match <CODE>_<concept-id>_Explained.md and is '
                                   'not under .history/.',
                                   path=str(p.relative_to(course)), severity='warning'))
    for name in ('explain_findings.json', 'explain_state.json'):
        for p in course.rglob(name):
            if p.parent.name != '.data':
                findings.append(_f('report', 'stray_explain_file',
                                   f'WARNING: {p.relative_to(course)} is outside .data/',
                                   path=str(p.relative_to(course)), severity='warning'))


def check_foreign_files(course: Path, findings: list):
    for p in course.rglob('notes_corrections.md'):
        parent = p.parent
        ok = (naming.parse_lesson_folder(parent.name) is not None
              and parent.parent.name in ('Lessons', 'Tutorials'))
        if not ok:
            findings.append(_f('report', 'misplaced_correction_log',
                               f'{p.relative_to(course)} is not at a lesson or tutorial '
                               'folder root, which is its pinned location. Reported '
                               'only, never moved: this file belongs to the corrections '
                               'skill and is never opened here.',
                               path=str(p.relative_to(course))))
    inbox = course / '_Inbox'
    if inbox.is_dir():
        for p in sorted(inbox.iterdir()):
            if p.is_dir() or p.name == '_filing_log.md' or p.name.startswith('.'):
                continue
            findings.append(_f('report', 'unfiled',
                               f'_Inbox/{p.name} is waiting to be filed',
                               path=f'_Inbox/{p.name}'))


def check_registration(vault: Path | None, course: Path, data: dict, findings: list):
    if vault is None:
        return
    try:
        cfg = read_config(vault)
    except Exception:
        findings.append(_f('report', 'no_config',
                           'no _config.md at the vault root', path='_config.md'))
        return
    try:
        rel = str(course.resolve().relative_to(Path(vault).resolve()))
    except ValueError:
        return
    if rel in (cfg.get('archived_courses') or []):
        findings.append(_f('report', 'archived_course',
                           'this course is archived. Validate never re-adds an '
                           'archived course to active_courses.', path=rel))
    elif rel not in (cfg.get('active_courses') or []):
        findings.append(_f('auto', 'not_registered',
                           'the course is not in active_courses', path=rel,
                           fix='append it'))
    code = (data.get('frontmatter') or {}).get('code')
    registry = cfg.get('course_codes') or {}
    if code and code not in registry:
        findings.append(_f('auto', 'code_not_registered',
                           f'code {code} is not in the code registry', path='_config.md',
                           fix=f'append {code} -> {rel}'))
    elif code and registry.get(code) != rel:
        findings.append(_f('report', 'code_registry_conflict',
                           f'the registry maps {code} to {registry.get(code)}, not to '
                           'this course. The notes and revision skills stop until this '
                           'is resolved.', path='_config.md'))
    dupes = [c for c, path in registry.items() if c != code and path == rel]
    if dupes:
        findings.append(_f('report', 'duplicate_registry_entry',
                           f'the registry also maps {", ".join(dupes)} to this course',
                           path='_config.md'))


# ---------------------------------------------------------------- driver

def scan(course: Path | str, vault: Path | str | None = None,
         read_only: bool = False, apply_auto: bool = False) -> dict:
    course = Path(course)
    kind = course_kind(course)
    findings: list[dict] = []

    if kind == 'missing':
        return {'course': str(course), 'kind': kind, 'findings': [],
                'read_only': True,
                'note': 'the folder does not exist. Ask before creating anything: '
                        'never create a course folder from what may be a typo.'}

    conforming = kind == 'conforming'
    read_only = read_only or not conforming

    data = ov.load(course)
    has_notes = _has_notes(course)

    check_scaffolding(course, findings, has_notes)
    if conforming:
        check_identity(course, data, findings)
    check_lessons(course, data, findings)
    check_lesson_root_files(course, findings)
    check_content_files(course, findings)
    check_folder_spellings(course, findings)
    check_books(course, findings)
    check_icloud(course, findings)
    check_archives(course, findings)
    check_quarantine(course, findings)
    check_foreign_files(course, findings)
    check_registration(Path(vault) if vault else None, course, data, findings)

    applied = []
    if read_only:
        for f in findings:
            if f['class'] == 'auto':
                f['class'] = 'propose'
                f['note'] = ('read-only: this folder is not yet a conforming course, '
                             'so nothing is written before you approve the plan')
    elif apply_auto:
        applied = _apply_auto(course, vault, data, findings)

    by_class = {'auto': [], 'propose': [], 'report': []}
    for f in findings:
        by_class[f['class']].append(f)
    return {'course': str(course), 'kind': kind, 'read_only': read_only,
            'conforming': conforming and not by_class['propose'],
            'counts': {k: len(v) for k, v in by_class.items()},
            'findings': by_class, 'applied': applied}


def _apply_auto(course: Path, vault, data, findings) -> list:
    """Only the class that cannot lose data. Everything else waits for approval."""
    applied = []
    fm = data.get('frontmatter') or {}
    course_name = fm.get('course') or course.name
    code = fm.get('code') or ''
    for f in list(findings):
        if f['class'] != 'auto':
            continue
        code_name = f['code']
        try:
            if code_name in ('missing_folder', 'missing_lesson_subfolder',
                             'partial_exams_tree'):
                (course / f['path']).mkdir(parents=True, exist_ok=True)
            elif code_name == 'missing_toc':
                text = scaffold._fill(scaffold._template('table_of_contents.md'),
                                      course=course_name)
                (course / 'Table_of_contents.md').write_text(text, encoding='utf-8')
            elif code_name == 'missing_structure':
                text = scaffold._fill(scaffold._template('structure_readme.md'),
                                      course=course_name, code=code)
                (course / '_Structure.md').write_text(text, encoding='utf-8')
            elif code_name == 'missing_terms':
                (course / '.data').mkdir(parents=True, exist_ok=True)
                (course / '.data' / 'terms.json').write_text('{}\n', encoding='utf-8')
            elif code_name == 'stamp':
                scaffold.stamp(course / f['path'])
            elif code_name in ('not_registered', 'code_not_registered') and vault:
                scaffold.register(vault, course, code, apply_it=True)
            elif code_name == 'missing_overview_row':
                _append_row(course, f)
            else:
                continue
            f['applied'] = True
            applied.append({'code': code_name, 'path': f.get('path')})
        except Exception as e:                       # a failed auto-fix is a report
            f['applied'] = False
            f['error'] = str(e)
    return applied



MACHINE_COLS = ('type', 'no', 'date', 'topic', 'book', 'chapters')


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip('|').split('|')]


def _machine_table(lines: list[str]):
    """Locate the machine-readable schedule: header index, first and last row.

    Found by its column names, never by position. `Weekly_overview.md` holds two
    tables under one heading, the machine table and the lecturer's own, and the
    lecturer's is normally the longer and the later one. Appending after "the
    last line starting with a pipe" therefore dropped the row into the
    lecturer's table, or into a "Rooms at a glance" table below it, where no
    reader of the schedule will ever see it and where it corrupts a table the
    student maintains by hand. `overview.py` parses the two apart for exactly
    this reason; the writer has to do the same.
    """
    for i, line in enumerate(lines):
        if not line.strip().startswith('|'):
            continue
        cols = [c.lower() for c in _cells(line)]
        if all(want in cols for want in MACHINE_COLS):
            j = i + 1
            if j < len(lines) and set(lines[j].replace('|', '').strip()) <= set('-: '):
                j += 1
            first = j
            while j < len(lines) and lines[j].strip().startswith('|'):
                j += 1
            return i, first, j - 1
    return None, None, None


def _row_slot(lines, first, last, row_type: str, number: str) -> int:
    """Where the new row goes: in number order, among rows of its own type.

    Out-of-order rows are legal and read badly; a lesson filed late belongs
    beside its neighbours, not at the bottom.
    """
    try:
        n = int(number)
    except ValueError:
        return last + 1
    slot = last + 1
    seen_type = False
    for i in range(first, last + 1):
        cells = _cells(lines[i])
        if len(cells) < 2:
            continue
        if cells[0].lower() != row_type:
            if seen_type:
                return i
            continue
        seen_type = True
        try:
            other = int(cells[1])
        except ValueError:
            continue
        if other > n:
            return i
    return slot


def _append_row(course: Path, finding: dict):
    """Append a row derived from the folder, with the inferable cells only.

    Topic, Book and Chapters are left blank and the row is reported as needing
    completion: they can only be inferred from the lesson's own sources against a
    book index, and outside a filing run those are usually not both available.
    Presenting a blank row as "fixed" would be a lie the notes skill pays for.
    """
    path = course / 'Weekly_overview.md'
    fm, body = read_frontmatter(path)
    key = finding['lesson']
    row_type = 'lesson' if key.startswith('L') else 'tutorial'
    row = f"| {row_type} | {key[1:]} | {finding['date']} |  |  |  |  |"
    lines = body.rstrip('\n').splitlines()
    head, first, last = _machine_table(lines)
    if head is None:
        lines += ['', '| Type     | No | Date       | Topic | Book | Chapters | Lesson |',
                  '|----------|----|------------|-------|------|----------|--------|', row]
    else:
        lines.insert(_row_slot(lines, first, last, row_type, key[1:]), row)
    write_frontmatter(path, fm, '\n'.join(lines) + '\n')
    finding['appended_row'] = row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('scan')
    p.add_argument('--course', required=True)
    p.add_argument('--vault')
    p.add_argument('--read-only', action='store_true')
    p.add_argument('--apply-auto', action='store_true')
    args = ap.parse_args(argv)
    out = scan(args.course, args.vault, args.read_only, args.apply_auto)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
