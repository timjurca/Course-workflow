#!/usr/bin/env python3
"""Correct a definition once, everywhere it is repeated, and nowhere else.

A wrong definition is the most contagious error in this plugin. `terms.json`
feeds the `## Definitions` block of **every** lesson that uses the term, B
repeats the text in full in each of them, and C writes questions from it. Fix it
in one lesson and the other lessons keep teaching the old one.

So a term correction is one group (spec section 16):

  1. only the `definition` field of the entry changes; the previous text is
     appended to `history` and `corrected_by` is set to the correction id
  2. every lesson in `seen_in` gets its Definitions block corrected, under one
     `group: g-NNNN`, so each lesson still replays on its own
  3. the entry for the lesson in `first_defined` carries `terms_json: true`,
     which is how `undo` and `replay` know which log entry owns the JSON change
  4. **translations are untouched.** D never changes the language of a definition
  5. a `verbatim: true` entry is a quotation. It can only be corrected as a
     **misreading**. If the book really says it, the quote stays and the
     correction becomes a `[source error: <ID>]` note beside it — changing a
     quotation to what it should have said is not a correction, it is a forgery
  6. B keeps a definition carrying `corrected_by` on its next run, unless the
     source behind it changed, in which case B reports the conflict

Everything here archives `terms.json` to `.data/history/` before it writes, the
same rule as every other D write.

CLI:
    terms.py show    --course <path> --term <key>
    terms.py plan    --course <path> --term <key> --definition <text>
                     [--correction c-0003] [--group g-0004]
    terms.py correct --course <path> --term <key> --definition <text>
                     --correction c-0003 [--apply]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import anchor                                                     # noqa: E402
import apply as dapply                                            # noqa: E402
import gate as dgate                                              # noqa: E402

TERMS_NAME = 'terms.json'
# The only key D may change, plus the two it may add. Everything else in an
# entry belongs to course-notes.
WRITABLE = ('definition', 'history', 'corrected_by')


def terms_path(course: Path | str) -> Path:
    return Path(course) / '.data' / TERMS_NAME


def load(course: Path | str) -> dict:
    path = terms_path(course)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def show(course: Path | str, term: str) -> dict:
    data = load(course)
    if not data:
        return {'ok': False, 'reason': 'no terms.json: run course-notes first'}
    entry = data.get(term)
    if entry is None:
        near = sorted(k for k in data if term.lower() in k.lower())
        return {'ok': False, 'reason': f'{term!r} is not in terms.json', 'near': near}
    return {'ok': True, 'term': term, 'entry': entry}


def plan(course: Path | str, term: str, definition: str,
         correction: str | None = None, group: str | None = None) -> dict:
    """Every place the new definition has to land, before anything is written."""
    course = Path(course)
    found = show(course, term)
    if not found['ok']:
        return found
    entry = found['entry']

    if entry.get('verbatim'):
        return {'ok': False, 'term': term, 'verbatim': True,
                'reason': 'this definition is a verbatim quotation. It can only be '
                          'corrected as a misreading (an erratum plus the repaired '
                          'quote). If the book really says this, the quote stays and '
                          'the correction becomes a [source error: '
                          + str(entry.get('source') or '<ID>') + '] note beside it.'}

    lessons = entry.get('seen_in') or ([entry['first_defined']]
                                       if entry.get('first_defined') else [])
    old = entry.get('definition') or ''
    edits, missing = [], []
    for lesson in lessons:
        notes = dgate.notes_path(course, lesson)
        if notes is None:
            missing.append(lesson)
            continue
        text = notes.read_text(encoding='utf-8')
        hit = anchor.find(text, old, heading='Definitions')
        if not hit['found']:
            missing.append(lesson)
            continue
        edits.append({'id': correction, 'lesson': lesson,
                      'file': str(notes.relative_to(course)),
                      'operation': 'replace', 'heading': 'Definitions',
                      'before': old, 'after': definition,
                      'occurrences': hit['count']})

    return {'ok': True, 'term': term, 'group': group,
            'first_defined': entry.get('first_defined'),
            'seen_in': lessons, 'old': old, 'new': definition,
            'edits': edits,
            'terms_json_entry': entry.get('first_defined'),
            'not_found_in': missing,
            'translations': entry.get('translation') or {},
            'note': 'translations are untouched; D never changes the language of a '
                    'definition. Each lesson gets its own log entry under one group, '
                    'so each replays on its own.'}


def correct(course: Path | str, term: str, definition: str, correction: str,
            apply: bool = False) -> dict:
    """Change the `definition` field, keep the old one in `history`, archive first."""
    course = Path(course)
    found = show(course, term)
    if not found['ok']:
        return found
    data = load(course)
    entry = data[term]
    if entry.get('verbatim'):
        return plan(course, term, definition, correction)

    before = json.loads(json.dumps(entry))
    history = list(entry.get('history') or [])
    history.append({'definition': entry.get('definition'),
                    'replaced': date.today().isoformat(), 'by': correction})
    entry['definition'] = definition
    entry['history'] = history
    entry['corrected_by'] = correction

    outside = [k for k in set(before) | set(entry)
               if before.get(k) != entry.get(k) and k not in WRITABLE]
    if outside:
        return {'ok': False,
                'reason': f'refusing to write {", ".join(sorted(outside))}: D may '
                          'change only ' + ', '.join(WRITABLE)}

    path = terms_path(course)
    archive = dapply.archive_path(course, str(path.relative_to(course)), correction)
    if apply:
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, archive)
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                       encoding='utf-8')
        tmp.replace(path)

    return {'ok': True, 'term': term, 'corrected_by': correction,
            'archive': str(archive.relative_to(course)),
            'history_len': len(history), 'written': apply,
            'reminder': 'the log entry for the lesson in first_defined carries '
                        'terms_json: true, and every lesson in seen_in is corrected '
                        'in the same group'}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('show')
    p.add_argument('--course', required=True); p.add_argument('--term', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--course', required=True); p.add_argument('--term', required=True)
    p.add_argument('--definition', required=True); p.add_argument('--correction')
    p.add_argument('--group')
    p = sub.add_parser('correct')
    p.add_argument('--course', required=True); p.add_argument('--term', required=True)
    p.add_argument('--definition', required=True)
    p.add_argument('--correction', required=True)
    p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'show':
        out = show(args.course, args.term)
    elif args.cmd == 'plan':
        out = plan(args.course, args.term, args.definition, args.correction, args.group)
    else:
        out = correct(args.course, args.term, args.definition, args.correction,
                      args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
