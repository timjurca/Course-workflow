#!/usr/bin/env python3
"""The durable term ledger: why every lesson's definition of a word is the same one.

`.data/terms.json` accumulates across a whole course and is never auto-cleaned.
Its purpose is easy to state backwards: without it, lesson 3 defines endogeneity
one way, lesson 9 defines it slightly differently, and nothing in the vault ever
notices. A student revising in June reads two definitions of one term and cannot
tell which is the course's.

So definitions are **repeated in full in every lesson where the term appears**.
The ledger exists so the repeated text is identical, not so it can be omitted
and linked to.

Two rules here are not bookkeeping and are worth stating:

**A definition carrying `corrected_by` is never overwritten.** Skill D corrected
it against the sources, and a re-derived definition from a later run would
silently undo that work and force another correction cycle. The one exception is
a *changed source behind it* — a new file, or a new erratum for the cited ID —
and even then the entry is left alone and the conflict is reported, because
either version could be right and only the student knows which.

**A materially different later definition is a refinement, not a replacement.**
The old text moves into `history` and the notes link back, so the earlier
lesson's wording stays reachable. Overwriting would make the earlier lesson's
notes disagree with the ledger they were generated from.

`first_defined` and `seen_in` are prefixed `L`/`T`, because lessons and
tutorials share one numbering and `03` alone is ambiguous.

CLI:
    terms.py list --course <c>
    terms.py get --course <c> --term endogeneity
    terms.py upsert --course <c> --term endogeneity --lesson L03 --json <f> [--apply]
    terms.py seen --course <c> --lesson L03 --terms a b c [--apply]
    terms.py index --course <c> --code ECON
    terms.py migrate --course <c> [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import renumber                                                    # noqa: E402

REL = Path('.data') / 'terms.json'
KEY_RE = re.compile(r'^[LT]\d{2}$')


def path_of(course: Path | str) -> Path:
    return Path(course) / REL


def load(course: Path | str) -> dict:
    path = path_of(course)
    if not path.is_file():
        return {}
    text = path.read_text(encoding='utf-8').strip()
    return json.loads(text) if text else {}


def save(course: Path | str, data: dict) -> str:
    path = path_of(course)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                              sort_keys=True) + '\n', encoding='utf-8')
    os.replace(tmp, path)
    return str(path)


def _blank(term: str) -> dict:
    return {'definition': '', 'verbatim': False, 'source': '', 'language': '',
            'translation': {}, 'first_defined': '', 'seen_in': [],
            'history': []}


def upsert(course: Path | str, term: str, lesson: str, entry: dict,
           source_changed: bool = False, apply_it: bool = False) -> dict:
    """Add a term, or refine one, or refuse because skill D owns this text."""
    if not KEY_RE.match(lesson):
        return {'ok': False, 'reason': f'lesson key must be L<NN> or T<NN>, '
                                       f'got {lesson!r}'}
    data = load(course)
    key = term.strip()
    row = data.get(key)
    result = {'term': key, 'lesson': lesson}

    if row is None:
        row = _blank(key)
        row.update({k: v for k, v in entry.items() if v not in (None, '')})
        row['first_defined'] = lesson
        row['seen_in'] = [lesson]
        data[key] = row
        result.update({'ok': True, 'action': 'created'})
    elif row.get('corrected_by'):
        # Skill D's text stands. The only thing this run may do is note the
        # conflict; resolving it needs a person, because either could be right.
        if lesson not in row['seen_in']:
            row['seen_in'].append(lesson)
        result.update({
            'ok': True, 'action': 'preserved',
            'corrected_by': row['corrected_by'],
            'conflict': bool(source_changed),
            'reason': 'this definition carries corrected_by, so it is kept as '
                      'skill D left it' + (
                          '. The source behind it changed (a new file or a new '
                          'erratum for the cited ID): report the conflict and '
                          'leave the entry untouched until the student decides.'
                          if source_changed else '.')})
    else:
        new_def = (entry.get('definition') or '').strip()
        old_def = (row.get('definition') or '').strip()
        if new_def and _materially_different(old_def, new_def):
            row.setdefault('history', []).append(
                {'definition': old_def, 'source': row.get('source'),
                 'lesson': row.get('first_defined'),
                 'superseded_in': lesson})
            row.update({k: v for k, v in entry.items() if v not in (None, '')})
            result.update({'ok': True, 'action': 'refined',
                           'earlier_in': row.get('first_defined')})
        else:
            for k, v in entry.items():
                if v not in (None, '') and not row.get(k):
                    row[k] = v
            result.update({'ok': True, 'action': 'unchanged'})
        if lesson not in row['seen_in']:
            row['seen_in'].append(lesson)

    data[key] = row
    if apply_it:
        result['path'] = save(course, data)
    result['applied'] = apply_it
    result['entry'] = row
    return result


def _materially_different(old: str, new: str) -> bool:
    """Whitespace and punctuation churn is not a refinement.

    Anything stricter would log a refinement every run and fill `history` with
    the same sentence; anything looser would hide a real change.
    """
    def norm(s):
        return re.sub(r'[^a-z0-9 ]', '', re.sub(r'\s+', ' ', s.lower())).strip()
    return bool(old) and bool(new) and norm(old) != norm(new)


def seen(course: Path | str, lesson: str, terms: list[str],
         apply_it: bool = False) -> dict:
    data = load(course)
    added, unknown = [], []
    for t in terms:
        row = data.get(t)
        if row is None:
            unknown.append(t)
            continue
        if lesson not in row.get('seen_in', []):
            row.setdefault('seen_in', []).append(lesson)
            added.append(t)
    if apply_it:
        save(course, data)
    return {'lesson': lesson, 'recorded': added, 'unknown': unknown,
            'applied': apply_it}


def index_rows(course: Path | str, code: str) -> dict:
    """The term index of `Table_of_contents.md`, rebuilt wholesale every run.

    Never appended to: a term seen in a second lesson needs its row updated, and
    appending would give it two.
    """
    data = load(course)
    rows = []
    for term in sorted(data, key=str.lower):
        row = data[term]
        first = row.get('first_defined') or ''
        notes = f'{code}_{first}_Final_notes' if first else ''
        link = f'[[{notes}#Definitions\\|{first}]]' if notes else ''
        also = [k for k in row.get('seen_in', []) if k != first]
        rows.append({'term': term, 'defined_in': first, 'link': link,
                     'also': also})
    return {'rows': rows, 'count': len(rows)}


def migrate(course: Path | str, applied: list[str] | None = None,
            apply_it: bool = False) -> dict:
    """Apply A's renumber blocks to `first_defined` and `seen_in`.

    The applied-ids list lives in `concepts.json`, because one skill keeps one
    list; this function takes it as an argument rather than reading a file it
    does not own.
    """
    blocks = renumber.pending_blocks(course, applied or [])
    if not blocks:
        return {'blocks': 0, 'changed': 0, 'applied': []}
    data = load(course)
    mapping = {}
    for block in blocks:
        mapping.update(renumber.moves_to_mapping(block['moves']))
    changed = 0
    for term, row in data.items():
        first = row.get('first_defined')
        new_first = renumber.remap_key(first, mapping) if first else first
        if new_first != first:
            row['first_defined'] = new_first
            changed += 1
        seen_in = row.get('seen_in') or []
        new_seen = [renumber.remap_key(k, mapping) for k in seen_in]
        if new_seen != seen_in:
            row['seen_in'] = new_seen
            changed += 1
    if apply_it and changed:
        save(course, data)
    return {'blocks': len(blocks), 'ids': [b['id'] for b in blocks],
            'changed': changed, 'applied': apply_it, 'mapping': mapping}


def _load_json_arg(raw: str):
    """A path or inline JSON. `Path(raw).is_file()` alone raises ENAMETOOLONG on
    an inline document, which is a crash rather than an error message."""
    text = (raw or '').lstrip()
    if text[:1] in ('[', '{'):
        return json.loads(raw)
    return json.loads(Path(raw).read_text(encoding='utf-8'))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('list', 'get', 'upsert', 'seen', 'index', 'migrate'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True)
        if name in ('get', 'upsert'):
            p.add_argument('--term', required=True)
        if name in ('upsert', 'seen', 'migrate'):
            p.add_argument('--apply', action='store_true')
        if name in ('upsert', 'seen'):
            p.add_argument('--lesson', required=True)
        if name == 'upsert':
            p.add_argument('--json', required=True,
                           help='file or inline JSON with the entry fields')
            p.add_argument('--source-changed', action='store_true')
        if name == 'seen':
            p.add_argument('--terms', nargs='+', required=True)
        if name == 'index':
            p.add_argument('--code', required=True)
        if name == 'migrate':
            p.add_argument('--applied', nargs='*', default=[])
    args = ap.parse_args(argv)

    if args.cmd == 'list':
        data = load(args.course)
        out = {'count': len(data), 'terms': sorted(data)}
    elif args.cmd == 'get':
        out = load(args.course).get(args.term) or {'missing': args.term}
    elif args.cmd == 'upsert':
        entry = _load_json_arg(args.json)
        out = upsert(args.course, args.term, args.lesson, entry,
                     args.source_changed, args.apply)
    elif args.cmd == 'seen':
        out = seen(args.course, args.lesson, args.terms, args.apply)
    elif args.cmd == 'index':
        out = index_rows(args.course, args.code)
    else:
        out = migrate(args.course, args.applied, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
