#!/usr/bin/env python3
"""Parse the past exams once, and know without reading them whether that still holds.

Past exams are the only raw file C ever opens, and they are the expensive kind:
scans, whole-course coverage, often OCR. Parsing them on every run would make
each request cost minutes and would pull offloaded PDFs out of iCloud onto a
laptop nobody asked. So the result is cached in `.data/exam_profile.json` and
rebuilt only when the folder actually changed.

Change detection is by **name, size and modification time from a directory
listing**, with the course-code token ignored. The token matters: after A
renames a course code every past exam has a new filename, and a detector that
compared full names would declare the whole folder new and re-OCR a semester of
scans for nothing. Only files that changed **and are downloaded** are opened and
hashed; an unchanged offloaded file reuses its stored digest and is never read,
and a *new* offloaded file is reported and parsed once the student downloads it.

What the profile is for, beyond questions: it carries the exam's language, its
format, and the **mark scheme with its provenance**. `printed`, `course_info`
and `estimated` are not interchangeable, and every grade built on an `estimated`
scheme says so, in the feedback and in the readiness verdict. C never presents
its own allocation as the examiner's.

Concept mappings the student has confirmed survive every rebuild. Without that
the first re-OCR would silently discard a term's worth of corrections.

CLI:
    exam_profile.py scan     --course <path>
    exam_profile.py show     --course <path>
    exam_profile.py write    --course <path> --profile <json> [--apply]
    exam_profile.py unmapped --course <path>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import icloud                                                      # noqa: E402
import naming                                                      # noqa: E402
from source_hash import file_digest                                # noqa: E402

PROFILE_REL = Path('.data') / 'exam_profile.json'
PAST_REL = Path('Exams') / 'Past_exams'
MARK_SCHEME_SOURCES = ('printed', 'course_info', 'estimated')
MODES = ('written', 'oral', 'mixed')
SOLUTIONS_MARKER = '_Solutions'


def path_of(course: Path | str) -> Path:
    return Path(course) / PROFILE_REL


def load(course: Path | str) -> dict:
    p = path_of(course)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding='utf-8'))


def save(course: Path | str, data: dict) -> Path:
    p = path_of(course)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    os.replace(tmp, p)
    return p


def key_of(name: str) -> str:
    """The stored name: everything after the course-code token.

    This is what makes a code rename free. `ECON_Past_2024-06-14.pdf` and
    `ECMT_Past_2024-06-14.pdf` are the same exam and must not look like two.
    """
    return naming.strip_code_token(name)


def scan(course: Path | str) -> dict:
    course = Path(course)
    folder = course / PAST_REL
    profile = load(course)
    stored = {row['file']: row for row in (profile.get('files') or [])}

    current, new, changed, unchanged, offloaded_new = {}, [], [], [], []
    if folder.is_dir():
        for p in sorted(folder.iterdir()):
            if not p.is_file() or p.name.startswith('.'):
                continue
            k = key_of(p.name)
            st = p.stat()
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)\
                .strftime('%Y-%m-%dT%H:%M')
            row = {'file': k, 'name_on_disk': p.name, 'size': st.st_size,
                   'mtime': mtime}
            was = stored.get(k)
            same = was and was.get('size') == row['size'] and \
                was.get('mtime') == row['mtime']
            placeholder = icloud.is_placeholder(p)['placeholder']
            row['offloaded'] = placeholder
            if same:
                row['sha256'] = was.get('sha256')
                unchanged.append(k)
            elif placeholder:
                # Never read to find out: opening it is what triggers a download.
                row['sha256'] = was.get('sha256') if was else None
                (changed if was else offloaded_new).append(k)
            else:
                row['sha256'] = file_digest(p)
                (changed if was else new).append(k)
            current[k] = row

    removed = sorted(set(stored) - set(current))
    outer = hashlib.sha256()
    for k in sorted(current):
        outer.update(k.encode('utf-8'))
        outer.update(b'\x00')
        outer.update((current[k].get('sha256') or 'offloaded').encode('utf-8'))
        outer.update(b'\x00')
    files_hash = outer.hexdigest()[:32]

    exams = []
    for k in sorted(current):
        if SOLUTIONS_MARKER in k:
            continue
        stem, ext = os.path.splitext(k)
        sol = next((s for s in current
                    if os.path.splitext(s)[0] == stem + SOLUTIONS_MARKER), None)
        exams.append({'file': k, 'solutions': sol})

    return {'course': str(course), 'folder_exists': folder.is_dir(),
            'files': [current[k] for k in sorted(current)],
            'files_hash': files_hash,
            'stored_files_hash': profile.get('files_hash'),
            'rebuild_needed': files_hash != profile.get('files_hash'),
            'new': new, 'changed': changed, 'unchanged': unchanged,
            'removed': removed, 'new_but_offloaded': offloaded_new,
            'exams': exams,
            'has_profile': bool(profile),
            'note': ('no past exams: the first mock asks the format once and saves '
                     'it with "source": "user". No MCQ without past exams.')
            if not current else
            ('these files are not downloaded; they are reported and parsed once '
             'they are' if offloaded_new else None)}


def write(course: Path | str, profile: dict, apply: bool = False) -> dict:
    """Merge a freshly parsed profile over the stored one, keeping confirmations."""
    course = Path(course)
    old = load(course)
    s = scan(course)

    scheme = ((profile.get('mark_scheme') or {}).get('source')
              or (old.get('mark_scheme') or {}).get('source') or 'estimated')
    if scheme not in MARK_SCHEME_SOURCES:
        raise ValueError(f'mark_scheme.source must be one of '
                         f'{", ".join(MARK_SCHEME_SOURCES)}')
    mode = ((profile.get('format') or {}).get('mode')
            or (old.get('format') or {}).get('mode'))
    if mode is not None and mode not in MODES:
        raise ValueError(f'format.mode must be one of {", ".join(MODES)}')

    confirmed = {}
    for q in (old.get('questions') or []):
        for c in (q.get('concepts') or []):
            if c.get('confirmed'):
                confirmed.setdefault((q.get('file'), q.get('number')), []).append(c)

    questions = []
    kept = 0
    for q in (profile.get('questions') or old.get('questions') or []):
        q = dict(q)
        mine = confirmed.get((q.get('file'), q.get('number')))
        if mine:
            by_id = {c['id']: c for c in (q.get('concepts') or [])}
            for c in mine:
                by_id[c['id']] = c
                kept += 1
            q['concepts'] = list(by_id.values())
        questions.append(q)

    merged = {
        'source': profile.get('source') or old.get('source') or 'past_exams',
        'files_hash': s['files_hash'],
        'files': s['files'],
        'language': profile.get('language') or old.get('language'),
        'format': {**(old.get('format') or {}), **(profile.get('format') or {})},
        'mark_scheme': {**(old.get('mark_scheme') or {}),
                        **(profile.get('mark_scheme') or {}), 'source': scheme},
        'type_mix': profile.get('type_mix') or old.get('type_mix') or {},
        'exams': profile.get('exams') or s['exams'],
        'questions': questions,
        'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M'),
        'generator': 'course-revision v1',
    }
    if apply:
        save(course, merged)
    return {'written': apply, 'questions': len(questions),
            'confirmed_mappings_kept': kept,
            'mark_scheme_source': scheme,
            'mode': merged['format'].get('mode'),
            'mcq_allowed': bool(merged['type_mix'].get('mcq')),
            'caveat': None if scheme == 'printed' else
                      f'the mark scheme is {scheme}: every grade and every '
                      'readiness verdict built on it must say so',
            'oral_caveat': None if merged['format'].get('mode') == 'written' else
                           'this exam is not written-only; C simulates written '
                           'exams only, and every mock and verdict must say so'}


def unmapped(course: Path | str) -> dict:
    """Questions with no concept, or only low-confidence guesses.

    Reported rather than forced: a question mapped to the wrong concept moves
    importance points onto material the exam never asked about.
    """
    profile = load(course)
    rows, low = [], []
    for q in (profile.get('questions') or []):
        cs = q.get('concepts') or []
        if not cs:
            rows.append({'file': q.get('file'), 'number': q.get('number'),
                         'why': 'no concept matched'})
        elif all(c.get('confidence') == 'low' and not c.get('confirmed') for c in cs):
            low.append({'file': q.get('file'), 'number': q.get('number'),
                        'concepts': [c.get('id') for c in cs],
                        'why': 'only low-confidence matches; confirm before scoring'})
    return {'unmapped': rows, 'low_confidence': low,
            'uncertain_readings': [
                {'file': q.get('file'), 'number': q.get('number')}
                for q in (profile.get('questions') or [])
                if q.get('reading') == 'uncertain'],
            'note': 'low-confidence signals are not scored; they are listed for '
                    'the student to confirm'}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('scan', 'show', 'write', 'unmapped'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True)
        if name == 'write':
            p.add_argument('--profile', required=True, help='JSON file or literal')
            p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'scan':
        out = scan(args.course)
    elif args.cmd == 'show':
        out = load(args.course)
    elif args.cmd == 'unmapped':
        out = unmapped(args.course)
    else:
        try:
            q = Path(args.profile)
            raw = q.read_text(encoding='utf-8') if q.is_file() else args.profile
        except OSError:
            raw = args.profile
        out = write(args.course, json.loads(raw), args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
