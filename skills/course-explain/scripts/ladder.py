#!/usr/bin/env python3
"""Which rung E is standing on, and the one thing that is allowed to stop it.

C and D hard-fail when the notes are missing or stale. E must not, and the
reason is the moment it is used: walking out of a lecture, before anything has
been run. A tutor that answers "I do not understand instrumental variables"
with "run the notes pipeline first" is a tutor nobody opens twice.

So staleness here is a **sentence, not a gate**. This module reports which of
four rungs the material supports, and the announcement that goes with it, so
that the student is never told something came from their notes when it came
from a slide, or from a slide when it came from the model:

    1  current notes                  say nothing, this is the normal case
    2  stale or missing notes, but extractions exist
    3  no extractions; the cited location in the raw source only
    4  not in the course material at all

**The one hard failure is the iCloud check**, and it is hard for a reason no
other check shares: an evicted placeholder reads as an empty file rather than an
error, so a lesson whose slides are not downloaded produces a confident
explanation built on nothing, with no sign on screen. A conflicted copy is the
same failure with two candidate truths. `stat` only; nothing here downloads a
file by reading it.

This module does not judge subject adjacency. `fence` gathers the evidence the
course itself provides - the course name, its description, its objectives and
its book titles - and the judgement stays with the model, because "adjacent to
econometrics" is not a string comparison.

CLI:
    ladder.py rung  --course <c> --lesson L03 [--concept <id>]
    ladder.py fence --course <c>
    ladder.py icloud --course <c> --lesson L03
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import icloud                                                        # noqa: E402
import naming                                                        # noqa: E402
import overview as ov                                                # noqa: E402
import source_hash                                                   # noqa: E402
from runstamp import norm_run                                        # noqa: E402
from vault import course_identity, read_frontmatter                  # noqa: E402

ANNOUNCE = {
    1: None,
    2: ('Your notes for {lesson} are stale, so this is from the {sources} '
        'directly. Run notes for {lesson} when you get a chance.'),
    '2_missing': ('You have no notes for {lesson} yet, so this is from the '
                  '{sources} directly. Run notes for {lesson} when you get a '
                  'chance.'),
    3: ('Nothing has been extracted for {lesson} yet, so I read the cited '
        'material directly: {where}.'),
    4: 'This is not in your course material. Here is the answer as background.',
}


def lesson_folder(course: Path | str, key: str) -> Path | None:
    """Find Lessons/NN_DATE or Tutorials/NN_DATE for L03 / T02."""
    course = Path(course)
    kind = 'Lessons' if key.upper().startswith('L') else 'Tutorials'
    num = key[1:]
    root = course / kind
    if not root.is_dir():
        return None
    for p in sorted(root.iterdir()):
        parsed = naming.parse_lesson_folder(p.name) if p.is_dir() else None
        if parsed and parsed['num'] == num.zfill(2):
            return p
    return None


def notes_file(folder: Path, key: str) -> Path | None:
    fn = folder / 'Final_notes'
    if not fn.is_dir():
        return None
    marker = f'_{key.upper()}_Final_notes.md'
    for p in sorted(fn.glob('*_Final_notes.md')):
        if p.name.endswith(marker):
            return p
    return None


def extractions(folder: Path) -> list:
    """B's Pass A files. Every one starts with A_ and nothing else in .work does."""
    work = folder / '.work'
    if not work.is_dir():
        return []
    return sorted(p for p in work.glob('A_*.md') if p.is_file())


def notes_state(course: Path | str, key: str) -> dict:
    """Current, stale or missing - by the same comparison C makes.

    Frontmatter only. E never opens a notes body to decide whether it is fresh.
    """
    course = Path(course)
    folder = lesson_folder(course, key)
    out = {'lesson': key, 'folder': str(folder.relative_to(course)) if folder else None,
           'notes': None, 'state': 'missing', 'reasons': []}
    if folder is None:
        out['reasons'].append('no lesson folder for this key')
        return out
    notes = notes_file(folder, key)
    if notes is None:
        out['reasons'].append('no Final_notes file')
        return out
    out['notes'] = str(notes.relative_to(course))
    try:
        fm, _ = read_frontmatter(notes)
    except Exception as exc:
        out['state'] = 'stale'
        out['reasons'].append(f'frontmatter unreadable: {exc}')
        return out
    out['run'] = norm_run(fm.get('run')) or None
    out['sources'] = fm.get('sources') or []
    out['flags'] = fm.get('flags') or []
    stat_cmp = source_hash.compare_stat(course, fm.get('sources_stat') or [], folder)
    stat_cmp = source_hash.absolve_annotation_changes(
        stat_cmp, fm.get('sources') or [], course, folder, fm.get('highlights'))
    if stat_cmp.get('changed'):
        out['reasons'].append(
            'sources_stat differs: ' + ', '.join(
                sorted({r.get('path', '?') for r in stat_cmp.get('changed', [])})))
    if stat_cmp.get('gone'):
        out['reasons'].append('recorded sources gone: ' + ', '.join(stat_cmp['gone']))
    if stat_cmp.get('freshness_unknown'):
        # An offloaded source is never "unchanged": its freshness is unknown, and
        # that is a reason to say so rather than to claim the notes are current.
        out['reasons'].append('freshness unknown (offloaded): '
                              + ', '.join(stat_cmp['freshness_unknown']))
    recorded = (fm.get('inputs') or {})
    current = ov.inputs_for(course, key)
    rec_row = (recorded.get('overview_row') or '').strip()
    if rec_row and current.get('overview_row') and \
            rec_row != (current['overview_row'] or '').strip():
        out['reasons'].append('the Weekly_overview row changed since the notes ran')
    out['state'] = 'stale' if out['reasons'] else 'current'
    return out


def icloud_check(course: Path | str, key: str) -> dict:
    """The one hard failure. stat only, before anything is read."""
    course = Path(course)
    folder = lesson_folder(course, key)
    roots = [p for p in [folder, course / 'Books'] if p and p.is_dir()]
    placeholders, conflicts = [], []
    for root in roots:
        res = icloud.scan(root)
        for row in res.get('placeholders', []):
            placeholders.append(row if isinstance(row, str) else row.get('path', str(row)))
        for row in res.get('conflicts', []):
            conflicts.append(row if isinstance(row, str) else row.get('path', str(row)))
    ok = not placeholders and not conflicts
    return {'ok': ok, 'placeholders': placeholders, 'conflicts': conflicts,
            'scanned': [str(r) for r in roots],
            'rule': ('a placeholder reads as empty content and a conflicted copy '
                     'has two candidate truths: hard fail, list the files, never '
                     'merge')}


def rung(course: Path | str, key: str, concept: str | None = None) -> dict:
    """Pick the rung and hand back the sentence that must precede the answer."""
    course = Path(course)
    ic = icloud_check(course, key)
    state = notes_state(course, key)
    folder = lesson_folder(course, key)
    extract = [str(p.relative_to(course)) for p in extractions(folder)] if folder else []
    reading = {}
    try:
        reading = ov.resolve_reading(ov.load(course), key)
    except Exception:
        reading = {'status': 'unknown'}

    if not ic['ok']:
        return {'rung': None, 'hard_fail': 'icloud', 'icloud': ic,
                'lesson': key, 'concept': concept,
                'say': ('Some of the files for this lesson are not downloaded or '
                        'exist as conflicted copies. I will not guess at their '
                        'contents. Listed below.')}

    if state['state'] == 'current':
        n = 1
    elif extract:
        n = 2
    elif folder is not None and (reading.get('status') == 'resolved'
                                 or any((folder / 'Content').glob('*'))):
        n = 3
    else:
        n = 4

    say = ANNOUNCE[n]
    if n == 2:
        # "stale" and "missing" are different facts and the student acts on them
        # differently: one means the notes moved on, the other means there are
        # none. One sentence covering both would say neither.
        template = ANNOUNCE[2] if state['state'] == 'stale' else ANNOUNCE['2_missing']
        kinds = sorted({Path(e).stem.replace('A_content_', '').split('_')[0]
                        for e in extract})
        say = template.format(lesson=key,
                              sources=' and '.join(kinds) if kinds else 'extractions')
    elif n == 3:
        where = []
        if reading.get('status') == 'resolved':
            where.append(f"{reading.get('book')} {reading.get('chapters')}")
        if folder is not None and (folder / 'Content').is_dir():
            where.extend(sorted(p.name for p in (folder / 'Content').iterdir()
                                if p.is_file())[:3])
        say = say.format(lesson=key, where=', '.join(where) or 'the cited location')

    return {
        'rung': n, 'lesson': key, 'concept': concept, 'hard_fail': None,
        'say': say, 'notes': state, 'extractions': extract,
        'reading': reading, 'icloud': ic,
        'reads_allowed': {
            1: 'the matching notes sections, concepts.json, terms.json, and the '
               'extraction items cited in those sections',
            2: 'the extraction items for this lesson, nothing else',
            3: 'the cited location only: the named slide, the chapter range, the '
               'transcript segment. Never a whole source.',
            4: 'nothing local; the two fences apply',
        }[n],
        'next': ('name course-notes as the next step' if n in (2, 3) else None),
    }


def fence(course: Path | str) -> dict:
    """The evidence for fence 1. The judgement is the model's, not a script's."""
    course = Path(course)
    ident = course_identity(course)
    out = {'course': ident.get('course'), 'code': ident.get('code'),
           'folder': course.name, 'notes_language': ident.get('notes_language'),
           'description': None, 'objectives': None, 'books': []}
    for rel, key in (('Course_description.md', 'description'),
                     ('Learning_objectives.md', 'objectives')):
        p = course / rel
        if p.is_file():
            text = p.read_text(encoding='utf-8', errors='replace').strip()
            out[key] = text[:1500]
    books = course / 'Books'
    if books.is_dir():
        out['books'] = sorted(p.stem for p in books.iterdir()
                              if p.is_file() and not p.name.endswith('.index.md'))
    out['fence_1'] = ('answer at rung 4 when the question is in or adjacent to this '
                      'subject; otherwise one line: outside this course, and E only '
                      'covers this course\'s subject')
    out['fence_2'] = ('E explains and does nothing else. No document, email, CV, '
                      'summary file, presentation or code meant to be used rather '
                      'than understood - inside the subject as much as outside it')
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('rung'); p.add_argument('--course', required=True)
    p.add_argument('--lesson', required=True); p.add_argument('--concept')
    p = sub.add_parser('fence'); p.add_argument('--course', required=True)
    p = sub.add_parser('icloud'); p.add_argument('--course', required=True)
    p.add_argument('--lesson', required=True)
    args = ap.parse_args(argv)
    if args.cmd == 'rung':
        out = rung(args.course, args.lesson, args.concept)
    elif args.cmd == 'fence':
        out = fence(args.course)
    else:
        out = icloud_check(args.course, args.lesson)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
