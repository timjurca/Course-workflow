#!/usr/bin/env python3
"""Exam-language terms, and a hard stop on inventing one.

When the past exams are in a different language from the notes, the questions
follow the exams -- that is the language the student is tested in. The danger is
the obvious one: a model asked to write an exam question in Slovenian will
produce a plausible Slovenian technical term for anything it does not know, and
a plausible wrong term is the worst possible outcome. The student learns it,
writes it in the exam, and the examiner does not recognise it.

So a term reaches an exam question only from a source that can be named:

  1  a translation B already recorded in `terms.json`
  2  a past exam, with the file and question it came from
  3  `exam_glossary.json`, where the student's own corrections live

Anything else is written in the source language with a bracketed guess, marked
`[translation, verify]`, and listed in the run report. The marker is not
decoration: it is the difference between a term the student can rely on and one
they must check.

C never writes a translation into B's `terms.json`. A term the student wants
changed in the notes is a correction, and corrections belong to skill D.

CLI:
    glossary.py lookup --course <path> --lang sl --terms endogeneity,relevance
    glossary.py set    --course <path> --term endogeneity --lang sl
                       --value endogenost --source user [--ref "..."] [--apply]
    glossary.py list   --course <path>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

GLOSSARY_REL = Path('.data') / 'exam_glossary.json'
TERMS_REL = Path('.data') / 'terms.json'
# Ordered best first. `user` wins over everything: the student corrected it.
SOURCES = ('user', 'past_exam', 'terms')


def path_of(course: Path | str) -> Path:
    return Path(course) / GLOSSARY_REL


def load(course: Path | str) -> dict:
    p = path_of(course)
    return json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}


def save(course: Path | str, data: dict) -> Path:
    p = path_of(course)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    os.replace(tmp, p)
    return p


def _terms(course: Path | str) -> dict:
    p = Path(course) / TERMS_REL
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def lookup(course: Path | str, terms: list[str], lang: str) -> dict:
    """Resolve each term, or say plainly that it is unresolved.

    An unresolved term is not an error and does not stop the run. It produces a
    `[translation, verify]` marker in the question and a line in the report,
    which is the only honest handling: C cannot know the word, and silence would
    read as confidence.
    """
    glossary = load(course)
    ledger_terms = _terms(course)
    resolved, unresolved = [], []
    for term in terms:
        entry = glossary.get(term) or {}
        if entry.get(lang):
            resolved.append({'term': term, 'value': entry[lang],
                             'source': entry.get('source', 'user'),
                             'ref': entry.get('ref')})
            continue
        tr = ((ledger_terms.get(term) or {}).get('translations') or {}).get(lang)
        if tr:
            resolved.append({'term': term, 'value': tr, 'source': 'terms',
                             'ref': f'.data/terms.json {term}'})
            continue
        unresolved.append({'term': term,
                           'write_as': f'{term} [translation, verify]',
                           'why': 'no translation from terms.json, a past exam or '
                                  'the glossary'})
    return {'lang': lang, 'resolved': resolved, 'unresolved': unresolved,
            'report_line': None if not unresolved else
            f'{len(unresolved)} translation(s) unverified: '
            + ', '.join(u['term'] for u in unresolved)}


def set_term(course: Path | str, term: str, lang: str, value: str,
             source: str = 'user', ref: str | None = None,
             apply: bool = False) -> dict:
    if source not in SOURCES:
        raise ValueError(f'source must be one of {", ".join(SOURCES)}')
    data = load(course)
    entry = data.setdefault(term, {})
    was = entry.get(lang)
    # A student correction outranks whatever a past exam or the notes said, and
    # is never overwritten by a later automatic reading.
    if entry.get('source') == 'user' and source != 'user':
        return {'term': term, 'kept': was, 'written': False,
                'why': 'a student correction is already recorded for this term'}
    entry[lang] = value
    entry['source'] = source
    entry['ref'] = ref
    entry['date'] = date.today().isoformat()
    if apply:
        save(course, data)
    return {'term': term, 'lang': lang, 'was': was, 'now': value,
            'source': source, 'written': apply,
            'note': 'never written into terms.json: changing a term in the notes '
                    'is a correction, and corrections belong to course-corrections'}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    lk = sub.add_parser('lookup')
    lk.add_argument('--course', required=True)
    lk.add_argument('--lang', required=True)
    lk.add_argument('--terms', required=True)
    st = sub.add_parser('set')
    st.add_argument('--course', required=True)
    st.add_argument('--term', required=True)
    st.add_argument('--lang', required=True)
    st.add_argument('--value', required=True)
    st.add_argument('--source', default='user', choices=list(SOURCES))
    st.add_argument('--ref')
    st.add_argument('--apply', action='store_true')
    ls = sub.add_parser('list')
    ls.add_argument('--course', required=True)
    args = ap.parse_args(argv)
    if args.cmd == 'lookup':
        out = lookup(args.course, [t.strip() for t in args.terms.split(',') if t.strip()],
                     args.lang)
    elif args.cmd == 'set':
        out = set_term(args.course, args.term, args.lang, args.value,
                       args.source, args.ref, args.apply)
    else:
        out = {'glossary': load(args.course)}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
