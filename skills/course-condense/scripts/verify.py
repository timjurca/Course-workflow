#!/usr/bin/env python3
"""Prove the condensed notes are a projection, and never a second opinion.

`course-condense` promises one thing that is easy to say and easy to violate:
**every claim is already in the final notes.** A model asked to compress 18,000
words will, unprompted, tidy a number, round a figure, or supply the connective
that "obviously" belongs. Each of those turns a summary into a second source
that quietly disagrees with the first, and nothing downstream would notice.

Nine checks, all mechanical. None of them reads for meaning; they read for
presence, which is the part a script can actually settle.

  concepts     every concept id in the notes appears in the condensed file
  formulas     every $$ block in the notes appears
  doubt        every marker saying a claim may be WRONG is carried verbatim
  figures      every embed resolves to a file that exists
  numbers      every numeric token in the condensed file occurs in the notes
  hash         notes_hash is recorded and matches the notes as they are now
  provenance   when the notes carry image/OCR readings, the summary line exists
  render       nothing Obsidian would draw wrongly: an indented line after a
               blank line (a code block, not a sub-bullet) or a currency $
               that opens an inline-math span and swallows the sentence
  contents     contents, not calculations: no data table, no arithmetic, no worked
               $$ block and no computed amount in inline maths

`formulas` counts only general formulas. A `$$` block holding a currency sign or
a decimal number is a worked calculation; it is exempt from coverage and is a
`contents` failure if it appears.

`numbers` is the projection check with teeth. A fabricated statistic, a rounded
percentage or a transposed year fails it, and those are the compression errors
that matter in an exam. It cannot catch a fabricated *sentence* built only from
words already present, which is why the SKILL.md also requires a human read of
the first lesson in a batch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))

import sections as S                                               # noqa: E402
from vault import read_frontmatter                                 # noqa: E402

FORMULA_RE = re.compile(r'\$\$(.+?)\$\$', re.S)
EMBED_RE = re.compile(r'^[ \t]*(?:>[ \t]?)*!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\][ \t]*$', re.M)
DOUBT_RE = re.compile(r'\[(?:source error|unverified|student, sources differ):[^\]]*\]'
                      r'|\[[^\]]*\btranscript only\b[^\]]*\]')
PROVENANCE_RE = re.compile(r'\[[^\]]*\b(?:OCR, verify|from image, verify)\b[^\]]*\]')
CONCEPT_RE = re.compile(r'^<!--\s*concept:\s*([^\s>]+)\s*-->\s*$', re.M)
NUM_RE = re.compile(r'(?<![\w.])(\d[\d,.]*\s?%?)(?![\w])')
WS = re.compile(r'\s+')
WORKED_RE = re.compile(r'\\\$|\d\.\d|\d,\d{3}')
TABLE_RE = re.compile(r'^[ \t]*\|.*\|[ \t]*$')
ARITH_RE = re.compile(r'\d[\d,.]*%?\s*(?:[+×*÷=]|\s[-−]\s)\s*[\\$€£]*\d')
INLINE_MATH_RE = re.compile(r'(?<![\\$])\$(?=\S)((?:\\\$|[^$])+?)(?<=\S)\$(?!\d)')


def _body(text: str) -> str:
    return text.split('---', 2)[2] if text.startswith('---') else text


def _norm(s: str) -> str:
    return WS.sub(' ', s).strip()


def _num_key(tok: str) -> str:
    """Compare 1,250 with 1250 and 12.5 % with 12.5%, but never 12.5 with 125."""
    # All whitespace, not just spaces: the pattern's \s? can capture a newline,
    # and a number ending a line ("$243.43\n") then never matched its twin in
    # the notes. Found on the first real run, where 10 of 156 numbers failed
    # for that reason alone.
    return WS.sub('', tok).replace(',', '').rstrip('.')


def _render_problems(cbody: str) -> list[dict]:
    """Two layout errors that pass every other check and wreck the page.

    An indented line straight after a blank line is an indented code block in
    Obsidian, so a sub-bullet placed after a `$$` block renders as grey code.
    A currency `$` can open an inline-math span: in "$120,000 ... index $x$"
    the first `$` pairs with the closing one and the sentence turns to maths.
    The rules follow Obsidian: `\\$` is literal; an opener is not followed by
    a space; a closer is not preceded by a space and not followed by a digit.
    """
    out, prev, fence = [], None, False
    for n, ln in enumerate(cbody.split('\n'), 1):
        if ln.lstrip().startswith('```'):
            fence = not fence
        if fence:
            prev = ln
            continue
        if prev == '' and ln.startswith('    ') and ln.strip():
            out.append({'check': 'render', 'line': n, 'text': ln.strip()[:60],
                        'why': 'indented line after a blank line renders as a code '
                               'block; outdent it or remove the blank line'})
        prev = ln
        if ln.lstrip().startswith('$$'):
            continue
        dollars = [i for i, ch in enumerate(ln) if ch == '$'
                   and (i == 0 or ln[i - 1] != '\\')
                   and ln[i + 1:i + 2] != '$' and (i == 0 or ln[i - 1] != '$')]
        k = 0
        while k < len(dollars):
            o = dollars[k]
            if ln[o + 1:o + 2] in ('', ' '):
                k += 1
                continue
            close = next((c for c in dollars[k + 1:]
                          if ln[c - 1] != ' ' and not ln[c + 1:c + 2].isdigit()), None)
            if close is None:
                break
            if ln[o + 1:o + 2].isdigit():
                out.append({'check': 'render', 'line': n, 'text': ln[o:close + 1][:60],
                            'why': 'a currency $ opens an inline-math span; escape '
                                   'it as \\$ on any line that also has inline maths'})
            k = dollars.index(close) + 1
    return out


def _contents_problems(cbody: str) -> list[dict]:
    """Contents, not calculations. The student revises what the lesson says;
    worked examples stay in the full notes. `## My additions` is the student's
    and is never checked."""
    body = cbody.split('\n## My additions', 1)[0]
    body = re.sub(r'<!--.*?-->', '', body, flags=re.S)
    out = []
    for f in FORMULA_RE.findall(body):
        if WORKED_RE.search(f):
            out.append({'check': 'contents', 'text': _norm(f)[:60],
                        'why': 'a worked $$ block is a calculation; keep the general '
                               'formula and drop the numbers'})
    flat = FORMULA_RE.sub('', body)
    for n, ln in enumerate(flat.split('\n'), 1):
        if TABLE_RE.match(ln):
            cells = INLINE_MATH_RE.sub(' ', ln)
            if re.search(r'\d', cells):
                out.append({'check': 'contents', 'text': ln.strip()[:60],
                            'why': 'a data table: drop it (the link leads to it). '
                                   'Only rule tables, with no digits outside '
                                   'inline maths, stay'})
            continue
        for m in INLINE_MATH_RE.finditer(ln):
            if WORKED_RE.search(m.group(1)):
                out.append({'check': 'contents', 'text': m.group(0)[:60],
                            'why': 'a computed amount in inline maths'})
        text = INLINE_MATH_RE.sub(' ', ln).replace('\\$', '$')
        m = ARITH_RE.search(text)
        if m:
            out.append({'check': 'contents', 'text': text.strip()[:70],
                        'why': 'arithmetic between numbers: a calculation, not content'})
    return out


def check(notes_path: Path | str, condensed_path: Path | str) -> dict:
    notes_path, condensed_path = Path(notes_path), Path(condensed_path)
    ntext = notes_path.read_text(encoding='utf-8')
    ctext = condensed_path.read_text(encoding='utf-8')
    nbody, cbody = _body(ntext), _body(ctext)
    cfm, _ = read_frontmatter(condensed_path)
    problems: list[dict] = []

    # concepts --------------------------------------------------------------
    want = [b['concept'] for b in S.concept_blocks(ntext)]
    have = set(CONCEPT_RE.findall(ctext))
    missing_c = [c for c in want if c not in have]
    extra_c = sorted(have - set(want))
    for c in missing_c:
        problems.append({'check': 'concepts', 'concept': c,
                         'why': 'in the final notes, absent from the condensed notes'})
    for c in extra_c:
        problems.append({'check': 'concepts', 'concept': c,
                         'why': 'in the condensed notes, not a concept of the final notes'})

    # formulas --------------------------------------------------------------
    nform = [_norm(f) for f in FORMULA_RE.findall(nbody) if not WORKED_RE.search(f)]
    cnorm = _norm(cbody)
    missing_f = [f for f in dict.fromkeys(nform) if f not in cnorm]
    for f in missing_f:
        problems.append({'check': 'formulas', 'formula': f[:90],
                         'why': 'a formula in the final notes does not appear'})

    # doubt markers ---------------------------------------------------------
    ndoubt = list(dict.fromkeys(DOUBT_RE.findall(nbody)))
    missing_d = [d for d in ndoubt if d not in cbody]
    for d in missing_d:
        problems.append({'check': 'doubt', 'marker': d,
                         'why': 'a marker saying a claim may be wrong was dropped; '
                                'these are carried verbatim, never summarised'})

    # figures ---------------------------------------------------------------
    att = condensed_path.parent / 'attachments'
    for name in EMBED_RE.findall(ctext):
        if not (att / name).is_file():
            problems.append({'check': 'figures', 'file': name,
                             'why': 'embedded but not present in attachments/'})

    # numbers ---------------------------------------------------------------
    nnums = {_num_key(t) for t in NUM_RE.findall(nbody)}
    # The one number F is told to write that the notes cannot contain: the count
    # of image readings in the banner. It is derived, so it is exempt -- that
    # exact value and nothing else.
    nnums.add(str(len(PROVENANCE_RE.findall(nbody))))
    seen, bad = set(), []
    for tok in NUM_RE.findall(cbody):
        k = _num_key(tok)
        if len(k.rstrip('%')) < 2 or k in seen:
            continue
        seen.add(k)
        if k not in nnums:
            bad.append(tok.strip())
    for tok in bad:
        problems.append({'check': 'numbers', 'token': tok,
                         'why': 'this number does not occur anywhere in the final '
                                'notes, so it was introduced here'})

    # hash ------------------------------------------------------------------
    recorded = str(cfm.get('notes_hash') or '')
    current = hashlib.sha256(nbody.encode('utf-8')).hexdigest()
    if not recorded:
        problems.append({'check': 'hash', 'why': 'notes_hash is not recorded, so '
                                                 'staleness can never be detected'})
    elif recorded != current:
        problems.append({'check': 'hash', 'recorded': recorded[:16],
                         'current': current[:16],
                         'why': 'notes_hash does not match the notes on disk'})

    # provenance ------------------------------------------------------------
    nprov = len(PROVENANCE_RE.findall(nbody))
    if nprov and not re.search(r'read from (?:slide |an )?image', cbody, re.I):
        problems.append({'check': 'provenance', 'count': nprov,
                         'why': 'the final notes carry image or OCR readings and the '
                                'condensed notes carry no summary line saying so'})

    # render ----------------------------------------------------------------
    problems.extend(_render_problems(cbody))

    # contents --------------------------------------------------------------
    problems.extend(_contents_problems(cbody))

    return {
        'ok': not problems,
        'notes': notes_path.name, 'condensed': condensed_path.name,
        'counts': {
            'concepts_expected': len(want), 'concepts_present': len(have),
            'formulas_expected': len(set(nform)), 'formulas_missing': len(missing_f),
            'doubt_expected': len(ndoubt), 'doubt_missing': len(missing_d),
            'numbers_checked': len(seen), 'numbers_unmatched': len(bad),
            'provenance_in_notes': nprov,
            'words_notes': len(nbody.split()), 'words_condensed': len(cbody.split()),
            'compression': (round(len(nbody.split()) / max(1, len(cbody.split())), 1)),
        },
        'problems': problems,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--notes', required=True)
    ap.add_argument('--condensed', required=True)
    args = ap.parse_args(argv)
    out = check(args.notes, args.condensed)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0 if out['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
