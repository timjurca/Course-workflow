#!/usr/bin/env python3
"""Pass D: coverage as set arithmetic, not as an instruction to be thorough.

Every other part of this pipeline can be talked into believing it did a good
job. This one cannot, because it subtracts sets:

    unplaced = ids_extracted - ids_placed - ids_discarded
    uncited  = ids_placed   - ids_cited

Both must be empty. That is the whole guarantee the skill offers — nothing
important was dropped — and it only holds because Pass A emits IDs
exhaustively and the notes cite them verbatim. Any decoration inside a written
marker (`[B §15.1]` instead of `[B15.1]`) breaks the string comparison and shows
up as a gap that no repair pass can close, so this also **validates marker shape
loudly** rather than skipping what it does not recognise. A silently skipped
marker is a silently uncovered item.

Three families share the bracket namespace (note-invariants §1) and this
separates them by shape alone: source markers (B), correction markers (D), tier
markers (E). Two rules come out of that separation and are enforced here:

  * an **unknown** bracket shape is reported, never ignored
  * a **tier marker in a notes file** is a quarantine failure, not a style
    problem: nothing skill E writes is ever read back, and a `[beyond course]`
    claim sitting in the notes reads as course material

`G` IDs are excluded from the arithmetic: an assignment task is a signal that a
concept is assessed, not material that must appear.

Incomplete coverage **never blocks the write**. Notes with a flagged gap beat no
notes. The gap goes into `## Uncovered material`, into `coverage:`, into the
warning banner and into `D_verification.md` — which is also the file skill D
reads to find what needs correcting.

CLI:
    verify.py check --work <.work> --notes <notes.md> [--spine <B_spine.md>]
                    [--discarded S03 T09] [--run <ts>] [--hash <h>]
    verify.py report --work <.work> --notes <notes.md> [...] --apply
"""
from __future__ import annotations

import argparse
import collections
import difflib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import extraction                                                  # noqa: E402
import judgement                                                   # noqa: E402
import plain_symbols                                               # noqa: E402
from vault import read_frontmatter                                 # noqa: E402

REPORT_NAME = 'D_verification.md'
SPINE_NAME = 'B_spine.md'

ID_RE = re.compile(r'^[SBTAHNCVKG]\d+(?:\.\d+)*n?!?$')
ID_SCAN_RE = re.compile(r'(?<![A-Za-z0-9])([SBTAHNCVKG]\d+(?:\.\d+)*n?!?)'
                        r'(?![A-Za-z0-9])')
CORRECTED_RE = re.compile(r'^(?P<a>\S+)\s+corrected by\s+(?P<b>\S+)$')

# Annotations that legally live *inside* a source marker (note-invariants §2).
INLINE_WORDS = {'ocr', 'verify', 'not lectured', 'lectured', 'highlight',
                'handwritten', 'n-only', 'unverified', 'errata',
                'transcript only', 'from image'}
CORRECTION_HEADS = ('source error: ', 'student, sources differ: ',
                    'unverified: ')
TIER_LITERALS = {'beyond course', 'your note'}
TIER_HEAD = 'differs from course: '
W_RE = re.compile(r'^W\d+$')

FENCE_RE = re.compile(r'^(?:```|~~~).*?^(?:```|~~~)\s*$', re.MULTILINE | re.DOTALL)
WIKILINK_RE = re.compile(r'!?\[\[[^\]]*\]\]')
MDLINK_RE = re.compile(r'!?\[[^\]\n]*\]\([^)\n]*\)')
CALLOUT_RE = re.compile(r'\[!\w+\]-?')
FOOTNOTE_RE = re.compile(r'\[\^[^\]]*\]')
BRACKET_RE = re.compile(r'\[([^\[\]\n]+)\]')
CONCEPT_RE = re.compile(r'<!--\s*concept:\s*([a-z0-9][a-z0-9-]*)\s*-->')

FIXED_SECTIONS = {'definitions', 'assigned readings', 'assigned videos',
                  'assigned links', 'recap', 'uncovered material',
                  'my additions', 'contents',
                  'check yourself', 'course administration', 'what to remember',
                  # zone headings: they hold sections, they are not sections
                  'concepts', 'cases'}


def _scrub(text: str) -> str:
    """Remove everything that legitimately uses brackets for something else."""
    text = FENCE_RE.sub('', text)
    text = re.sub(r'`[^`\n]*`', '', text)
    text = WIKILINK_RE.sub('', text)
    text = MDLINK_RE.sub('', text)
    text = CALLOUT_RE.sub('', text)
    text = FOOTNOTE_RE.sub('', text)
    return text


def classify_bracket(body: str) -> dict:
    """Which of the three marker families this bracket belongs to, by shape."""
    raw = body.strip()
    low = raw.lower()
    if low == 'judgement':
        # B's own marker, and the only one that says "not from a source".
        # Its own family so it is never reported as an unknown shape; whether
        # it is in a legal place is the judgement gate's question, not this
        # function's.
        return {'family': 'judgement', 'ids': [], 'text': raw}
    if low in TIER_LITERALS or low.startswith(TIER_HEAD) or W_RE.match(raw):
        return {'family': 'tier', 'ids': [], 'text': raw}
    for head in CORRECTION_HEADS:
        if low.startswith(head):
            ref = raw[len(head):].strip()
            return {'family': 'correction', 'ids': [ref] if ID_RE.match(ref) else [],
                    'text': raw}
    ids, unknown = [], []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        if ID_RE.match(part):
            ids.append(part)
            continue
        m = CORRECTED_RE.match(part)
        if m and ID_RE.match(m.group('a')) and ID_RE.match(m.group('b')):
            ids += [m.group('a'), m.group('b')]
            continue
        if part.lower() in INLINE_WORDS:
            continue
        unknown.append(part)
    if ids and not unknown:
        return {'family': 'source', 'ids': ids, 'text': raw}
    if ids and unknown:
        return {'family': 'source', 'ids': ids, 'text': raw, 'unknown': unknown}
    return {'family': 'unknown', 'ids': [], 'text': raw}


def scan_markers(text: str) -> dict:
    scrubbed = _scrub(text)
    source_ids, corrections, tiers, unknown, decorated = set(), [], [], [], []
    judgements = []
    for body in BRACKET_RE.findall(scrubbed):
        row = classify_bracket(body)
        if row['family'] == 'source':
            source_ids.update(row['ids'])
            if row.get('unknown'):
                decorated.append(row)
        elif row['family'] == 'correction':
            corrections.append(row['text'])
            source_ids.update(row['ids'])
        elif row['family'] == 'tier':
            tiers.append(row['text'])
        elif row['family'] == 'judgement':
            judgements.append(row['text'])
        else:
            unknown.append(row['text'])
    return {'ids': source_ids, 'corrections': corrections, 'tiers': tiers,
            'unknown': unknown, 'decorated': decorated,
            'judgements': judgements}



SUMMARY_RE = re.compile(r'^\*\*In one line:\*\*\s*(?P<text>.+?)\s*$', re.MULTILINE)


def _overview_for(notes: Path) -> Path:
    """`<lesson>/Final_notes/<CODE>_L03_Final_notes.md` -> `<lesson>/<CODE>_L03_Overview.md`.

    Derived rather than passed, so the check cannot be skipped by forgetting an
    argument. The `<CODE>_` prefix is left alone: file names are compared with it
    ignored elsewhere, but here the two files are siblings by construction.
    """
    return notes.parent.parent / notes.name.replace('_Final_notes.md',
                                                    '_Overview.md')


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip().rstrip('.').lower()


def summary_line(notes: Path, body: str) -> dict:
    """The one-line summary, and whether the notes and the overview agree.

    Two summaries of one lesson that drift apart are worse than one: neither can
    be trusted afterwards and nothing on screen says which is current. So the
    identity is checked rather than asked for.
    """
    m = SUMMARY_RE.search(body)
    here = m.group('text') if m else None
    ov = _overview_for(notes)
    there = None
    if ov.is_file():
        mo = SUMMARY_RE.search(ov.read_text(encoding='utf-8', errors='replace'))
        there = mo.group('text') if mo else None
    problems = []
    if here is None:
        problems.append({'kind': 'missing in the notes',
                         'fix': 'one sentence under the H1, stating what the '
                                'lesson claims'})
    if not ov.is_file():
        problems.append({'kind': 'no overview file', 'fix': f'expected {ov.name}'})
    elif there is None:
        problems.append({'kind': 'missing in the overview',
                         'fix': 'the same sentence goes in both files'})
    elif here is not None and _norm(here) != _norm(there):
        problems.append({'kind': 'notes and overview disagree',
                         'fix': 'write one sentence and put it in both',
                         'notes': here[:160], 'overview': there[:160]})
    return {'notes': here, 'overview': there, 'overview_path': str(ov),
            'problems': problems, 'clean': not problems}



# --- the formula gate --------------------------------------------------------
# Two rules, one check. A formula is reproduced in the source's own notation,
# like a table, and every symbol in it is explained. Restating a book's worked
# arithmetic in symbols the book never used produces a line wearing a source
# marker while saying something the source does not say, and a symbol nobody
# defined is a formula the student cannot use under exam conditions.
#
# Only *notation* is checked. Words inside \text{} are prose, not symbols: a
# step labelled "personal tax" is presentation, and demanding that the phrase
# appear verbatim in the book flags honest writing.
#
# Reach, stated so nobody over-trusts it: identifiers of one or two characters
# and Greek macros are checked. A word-like identifier such as `NPV` or `WACC`
# is not, because at three characters or more it is indistinguishable from
# prose and would flag every sentence that happens to contain it. Those read as
# words and are normally defined in the surrounding text anyway, so the gate
# catches the dangerous case (bare symbols) and misses the safe one.

DISPLAY_RE = re.compile(r'\$\$(?P<body>.+?)\$\$', re.DOTALL)
TEXT_MACRO_RE = re.compile(r'\\(?:text|mathrm|mathbf|operatorname)\s*\{[^}]*\}')
GREEK_RE = re.compile(r'\\([a-zA-Z]+)')
IDENT_RE = re.compile(r'(?<![A-Za-z\\])([A-Za-z][A-Za-z]?)(?![A-Za-z])')

# Layout, relations and arithmetic carry no notation of their own.
FORMULA_NOISE = {
    'frac', 'times', 'cdot', 'div', 'pm', 'mp', 'quad', 'qquad', 'left', 'right',
    'Rightarrow', 'rightarrow', 'Leftarrow', 'leftarrow', 'to', 'approx', 'neq',
    'leq', 'geq', 'ldots', 'dots', 'cdots', 'text', 'mathrm', 'mathbf', 'sum',
    'prod', 'int', 'sqrt', 'displaystyle', 'begin', 'end', 'align', 'aligned',
    'array', 'hline', 'label', 'notag', 'big', 'Big', 'bigg', 'Bigg', 'space',
    'operatorname', 'mbox', 'hspace', 'vspace', 'over', 'atop', 'log', 'ln',
    'exp', 'min', 'max', 'infty', 'partial', 'cap', 'cup', 'in', 'forall',
}
# How far below a formula its legend may sit.
LEGEND_WINDOW = 12


def _symbols(body: str) -> set[str]:
    """Symbol tokens in a formula: Greek macros and identifiers, never prose."""
    stripped = TEXT_MACRO_RE.sub(' ', body)
    toks = {'\\' + n for n in GREEK_RE.findall(stripped)
            if n not in FORMULA_NOISE}
    bare = GREEK_RE.sub(' ', stripped)
    toks |= set(IDENT_RE.findall(bare))
    return toks


def _token_in(token: str, haystack: str) -> bool:
    if token.startswith('\\'):
        name = token[1:]
        return (re.search(rf'\b{re.escape(name)}\b', haystack, re.I) is not None
                or name.lower() in haystack.lower())
    return re.search(rf'(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])',
                     haystack) is not None


def _legend_after(body: str, end: int) -> str:
    """The lines following a formula, where its variable legend belongs."""
    tail = body[end:].split('\n')[:LEGEND_WINDOW]
    out, seen_list = [], False
    for line in tail:
        s = line.strip()
        if not s:
            if seen_list:
                break
            continue
        if s.startswith(('-', '*', '|')) or re.match(r'^\$?[A-Za-z\\]', s):
            out.append(s)
            seen_list = seen_list or s.startswith(('-', '*', '|'))
            continue
        break
    return '\n'.join(out)


def formula_check(body: str, p1_text: str) -> list[dict]:
    """Unsourced notation, and symbols left unexplained."""
    out = []
    for m in DISPLAY_RE.finditer(body):
        raw = m.group('body')
        syms = _symbols(raw)
        if not syms:
            continue                      # arithmetic in words needs no legend
        line = body[:m.start()].count('\n') + 1
        shown = ' '.join(raw.split())[:150]
        unsourced = sorted(s for s in syms if not _token_in(s, p1_text))
        if unsourced:
            out.append({'line': line, 'kind': 'unsourced notation',
                        'symbols': unsourced, 'formula': shown})
        legend = _legend_after(body, m.end())
        undefined = sorted(s for s in syms if not _token_in(s, legend))
        if undefined:
            out.append({'line': line, 'kind': 'symbols not explained',
                        'symbols': undefined, 'formula': shown})
    return out


def _host(item_id: str) -> str:
    """`B15.2!` is a highlight inside `B15.2`; citing the host covers both."""
    return item_id[:-1] if item_id.endswith('!') else item_id


def spine_ids(path: Path | str) -> dict:
    path = Path(path)
    if not path.is_file():
        return {'exists': False, 'ids': set(), 'discarded': set()}
    text = path.read_text(encoding='utf-8', errors='replace')
    discarded = set()
    m = re.search(r'^##\s+Discarded\s*$(.*?)(?=^##\s|\Z)', text,
                  re.MULTILINE | re.DOTALL)
    if m:
        discarded = set(ID_SCAN_RE.findall(m.group(1)))
        text = text[:m.start()] + text[m.end():]
    return {'exists': True, 'ids': set(ID_SCAN_RE.findall(text)),
            'discarded': discarded}


# --- the writing gates -------------------------------------------------------
# (`Plain symbols` lives in shared/scripts/plain_symbols.py, because
# course-condense runs the same check on the revision sheet.)
# Pass C is model work, so these exist for the same reason Pass D does: an
# instruction in SKILL.md is advice, and advice decays. Each rule below is
# written by the model and checked here.

P1_KINDS = {'slides', 'book', 'handout', 'workbook'}

# A specific is a number, a year, a percentage or a quantity. Prose claims that
# rest only on a transcript are normal and mostly fine; a *number* that rests
# only on ASR is the failure mode (1982, 96%, 1960 in EBT L01).
SPECIFIC_RE = re.compile(r"\b\d[\d.,]*\s?%|\b(?:1[5-9]|20)\d{2}s?\b|\b\d[\d.,]*\b")

ATTRIBUTION_RE = re.compile(
    # (?!'s) keeps possessives out: "a student's own company" is content.
    r"\b(the lecturer|a student|the students|the room|the slide notes|"
    r"the teaching assistant|the professor|"
    r"he (?:says|said|adds|added|frames|framed|notes|noted|calls|called|is|was)|"
    r"she (?:says|said|adds|added|frames|framed|notes|noted|calls|called|is|was))(?!'s)\b",
    re.I)

MARKER_ID_RE = re.compile(r"[SBTAHNCVKG]\d+(?:\.\d+)*n?!?")


def _texts_by_priority(work: Path | str) -> tuple[str, str]:
    """Extraction text split by the A_ file's own `kind` header."""
    p1, rest = [], []
    for f in sorted(Path(work).glob('A_*.md')):
        try:
            d = extraction.read(f)
        except Exception:
            continue
        kind = (d.get('header') or {}).get('kind', '')
        bucket = p1 if kind in P1_KINDS else rest
        bucket.extend(i['text'] for i in d['items'])
    return '\n'.join(p1), '\n'.join(rest)


def unsupported_specifics(body: str, p1_text: str) -> list[dict]:
    """Numbers whose only support is a priority 2-3 source."""
    out = []
    for raw in re.split(r'(?<=[.!?])\s+|\n', _scrub(body)):
        line = raw.strip()
        if not line or 'transcript only' in line:
            continue          # already marked by Pass C
        if line.startswith('>'):
            # A blockquote is a verbatim quote or a callout: the number is
            # framed there, not asserted by the notes in their own voice.
            continue
        ids = MARKER_ID_RE.findall(line)
        if not ids:
            continue
        if {i[0] for i in ids} & set('SBH'):
            continue          # a priority-1 source backs this sentence
        # Strip the markers first: their own digits are not claims. Without
        # this every `[T1.02, T1.03]` reports "02" and "03" as unsupported.
        prose = re.sub(r'\[[^\]]*\]', ' ', line)
        for tok in {t.strip() for t in SPECIFIC_RE.findall(prose)}:
            if len(tok) < 2 or tok in p1_text:
                continue
            out.append({'token': tok, 'markers': sorted(set(ids)),
                        'text': line[:150]})
    # "1982 or 1983" must not also report "83". Drop any token that is a
    # substring of a longer token flagged on the same line.
    keep = []
    for x in out:
        longer = [y['token'] for y in out
                  if y['text'] == x['text'] and y['token'] != x['token']
                  and x['token'] in y['token']]
        if not longer:
            keep.append(x)
    return keep


# Suffixes that make one word family, not two spellings.
FAMILY_SUFFIXES = ("'s", "s'", "es", "al", "ly", "ing", "ed", "s")


def _family_stems(word: str) -> set:
    """Every stem this token could reduce to, not just the greediest one.

    Stripping only the longest matching suffix is wrong: `S-curves` loses `es`
    and becomes `s-curv`, which no longer matches `S-curve`. Keeping every
    candidate lets the comparison succeed on whichever reduction is the real
    one, without having to know which suffix was actually applied.
    """
    base = word.lower().rstrip("'-")
    out = {base}
    for suf in FAMILY_SUFFIXES:
        if len(base) > len(suf) + 2 and base.endswith(suf):
            stem = base[: -len(suf)].rstrip("'-")
            out.add(stem)
            for suf2 in FAMILY_SUFFIXES:      # `Organisationals` -> `organisation`
                if len(stem) > len(suf2) + 2 and stem.endswith(suf2):
                    out.add(stem[: -len(suf2)].rstrip("'-"))
    return out


def _same_word_family(a: str, b: str) -> bool:
    """True when the two tokens are inflections of one word, or two different
    compounds sharing a tail.

    The gate exists to catch a source spelling one *name* two ways, like
    `Pahos` against `Pachos`. Four lessons running it instead reported
    `Dickmann` against `Dickmann's`, `LinkedIn` against `LinkedIn's`,
    `S-curve` against `S-curves`, `Organisational` against `Organisations`
    and `Extra-organisational` against `Intra-organisational`. None is a
    disagreement: the first four are one word inflected, and the last is two
    named categories that share a tail. A gate whose rows are mostly noise
    gets skimmed, which is how the one real row gets missed.
    """
    if _family_stems(a) & _family_stems(b):
        return True
    if '-' in a and '-' in b:
        if a.split('-', 1)[1].lower() == b.split('-', 1)[1].lower():
            return True
    return False


def spelling_conflicts(p1_text: str) -> list[dict]:
    """Near-duplicate proper nouns *within* the authoritative sources.

    Both sides must be outside the general word list, or every singular/plural
    pair in the deck is reported and the real finding drowns.
    """
    try:
        import normalize_transcript as nt
        lexicon = nt.load_lexicon()
        known = lambda w: nt._known(w, lexicon)
    except Exception:
        return []
    if not lexicon:
        return []
    counts = collections.Counter(re.findall(r"\b[A-Z][a-zA-Z'\-]{3,}\b", p1_text))
    keys = sorted(counts)
    seen, out = set(), []
    for w in keys:
        for m in difflib.get_close_matches(w, keys, n=4, cutoff=0.88):
            if m == w or m.lower() == w.lower():
                continue
            pair = tuple(sorted((w, m)))
            if pair in seen:
                continue
            seen.add(pair)
            a, b = pair
            if known(a) or known(b):
                continue
            if _same_word_family(a, b):
                continue
            out.append({'a': a, 'a_count': counts[a], 'b': b, 'b_count': counts[b],
                        'majority': a if counts[a] >= counts[b] else b})
    return out


def attribution_in_prose(body: str) -> list[dict]:
    """Who said it is not the content; the marker already carries provenance.

    Allowed, and therefore skipped: blockquote lines, which is where quotes,
    callouts, exam signals and student-note callouts live, and the Definitions
    block, whose entries are quoted source text.
    """
    out = []
    in_defs = False
    for n, line in enumerate(body.splitlines(), 1):
        if line.startswith('## '):
            in_defs = line.strip() == '## Definitions'
        if in_defs or line.lstrip().startswith('>'):
            continue
        for m in ATTRIBUTION_RE.finditer(line):
            out.append({'line': n, 'phrase': m.group(0), 'text': line.strip()[:120]})
    return out


# The `> ` prefix is not optional decoration: note-invariants requires a
# student's own figure to sit inside its priority-3 callout, and an anchored
# pattern cannot see it there. FM lesson 3 placed five figures and this gate
# counted four, missing the one the rule exists to govern.
# `[ \t]*`, never `\s*`: under re.MULTILINE `\s` matches a newline, so a
# leading `\s*` swallows the blank line above the embed, the match starts on
# the wrong line, and the caption lookup reads the wrong line entirely. That
# turned every correctly captioned figure in the vault into 'no caption'.
EMBED_RE = re.compile(r'^[ \t]*(?:>[ \t]?)*!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\][ \t]*$',
                      re.MULTILINE)
# A single `*` or `_`, not a doubled one: `**Bold lead-in.** [S9]` starts with
# `*` and carries a marker, so it used to satisfy the caption check while
# saying nothing about the picture above it.
CAPTION_RE = re.compile(r'^[ \t]*(?:>[ \t]?)*(?:\*(?!\*)|_(?!_)).+')
FROM_IMAGE_RE = re.compile(r'\[[^\]]*\bfrom image, verify\b[^\]]*\]')


def figure_check(body: str, notes: Path, body_fm: dict | None = None) -> dict:
    """Figures the reader can actually see, and that carry their provenance.

    A figure is not decoration in these notes: a curve's shape, a flow with
    branches, a mapping of one structure onto another and a table whose
    alignment is the point are all things prose can describe but cannot show.
    Describing one and not showing it asks the student to trust a paraphrase of
    exactly the thing a paraphrase loses.

    The rule this enforces is deliberately *not* "embed every extracted image".
    Most of what a deck carries is a portrait, a stock photo or a section
    divider, and a notes file padded with those is worse than one with none.
    What it checks is the three ways an embed goes wrong mechanically, plus the
    one imbalance that showed up across this vault: LTM lesson 3 carried 45
    `from image, verify` readings and embedded no figure at all, so every
    picture it had read was available to its writer and to no one else.
    """
    d = notes.parent
    embeds, problems = [], []
    lines = body.splitlines()
    for m in EMBED_RE.finditer(body):
        target = m.group(1).strip()
        line_no = body[:m.start()].count('\n') + 1
        embeds.append(target)
        hits = list(d.rglob(target)) if target else []
        if not hits:
            problems.append({'kind': 'missing file', 'line': line_no,
                             'detail': target,
                             'fix': 'the embed renders as nothing in Obsidian; '
                                    'point it at a file under attachments/'})
            continue
        nxt = lines[line_no] if line_no < len(lines) else ''
        if not nxt.strip():
            nxt = lines[line_no + 1] if line_no + 1 < len(lines) else ''
        if not CAPTION_RE.match(nxt):
            problems.append({'kind': 'no caption', 'line': line_no,
                             'detail': target,
                             'fix': 'one italic sentence under the image saying '
                                    'what it shows, so the point survives even '
                                    'if the file is lost'})
        elif not BRACKET_RE.search(nxt):
            problems.append({'kind': 'caption carries no source marker',
                             'line': line_no, 'detail': target,
                             'fix': 'a figure is a source like any other; the '
                                    'caption ends with its id'})
    read_from_image = len(FROM_IMAGE_RE.findall(body))
    # A lesson that says in its frontmatter it read N slides as images, and
    # marks none of them in the body, has made those readings untraceable: no
    # reader can tell which claim rests on someone's reading of a picture, and
    # skill D cannot re-check them. Two lessons in this vault did exactly that.
    claimed = 0
    for f in (body_fm or {}).get('flags') or []:
        m = re.search(r'(\d+)\s+slide items read', str(f))
        if m:
            claimed = max(claimed, int(m.group(1)))
    if claimed and not read_from_image:
        problems.append({
            'kind': 'image readings claimed but never marked', 'line': 0,
            'detail': f'frontmatter flags say {claimed} slide items were read '
                      'from images; the body marks none',
            'fix': 'tag each one `[<id>, from image, verify]` where it is used, '
                   'so the reading is traceable and D can re-check it'})
    if read_from_image >= 5 and not embeds:
        problems.append({
            'kind': 'read from images, showed none', 'line': 0,
            'detail': f'{read_from_image} items were read off a rendered image '
                      'and no figure is embedded',
            'fix': 'embed the ones whose content is spatial or relational, a '
                   'curve, a flow, a mapping or an aligned table, and say in '
                   'the run report why the rest were not worth showing'})
    return {'embedded': len(embeds), 'read_from_image': read_from_image,
            'problems': problems, 'clean': not problems}


def check(work: Path | str, notes: Path | str, spine: Path | str | None = None,
          discarded: list[str] | None = None, run: str | None = None,
          sources_hash: str | None = None) -> dict:
    work = Path(work)
    notes = Path(notes)
    ext = extraction.read_set(work, run, sources_hash)

    extracted = {i for i in ext['ids'] if not i.startswith('G')}
    signals = {i for i in ext['ids'] if i.startswith('G')}

    spine_path = Path(spine) if spine else work / SPINE_NAME
    sp = spine_ids(spine_path)
    dropped = set(discarded or []) | sp['discarded']

    body_fm, body = ({}, '')
    if notes.is_file():
        body_fm, body = read_frontmatter(notes)
    markers = scan_markers(body)
    # `## What to remember` is Claude's opinion, not the material
    # (note-invariants §2a). An ID cited there must never satisfy coverage for
    # something the body failed to cover, so the cited set is computed from the
    # notes *without* the zone. Markers are still scanned over the whole file,
    # because marker shape has to be validated everywhere.
    sourced = scan_markers(judgement.strip(body))
    cited = {_host(i) for i in sourced['ids']} | sourced['ids']

    placed = {i for i in sp['ids'] if not i.startswith('G')} if sp['exists'] \
        else set()
    # No spine on disk means Pass B left no file. Treating "placed" as empty
    # would report every item unplaced, which hides the real problem, so the
    # cited set stands in and the substitution is stated in the report.
    spine_missing = not sp['exists']
    if spine_missing:
        placed = cited & extracted

    # Scanning nothing is a failure, not a pass. With no extractions on disk
    # every set is empty, so `unplaced` and `uncited` are empty too and the run
    # reports `0/0, complete: true` for notes that could be about anything. The
    # same shape as a link check over an empty scope.
    empty_scan = None
    if not extracted:
        empty_scan = (f'no extracted items under {work}: either Pass A never '
                      'ran or its files do not match this run, so coverage '
                      'proves nothing')

    unplaced = sorted(extracted - placed - dropped)
    uncited = sorted(placed - cited - dropped)
    orphan_cites = sorted(cited - extracted - signals)

    covered = len(extracted) - len(unplaced) - len(uncited)
    structure = _structure(body, body_fm, notes)
    p1_text, _rest = _texts_by_priority(work)
    writing = {
        'unsupported_specifics': unsupported_specifics(body, p1_text),
        'spelling_conflicts': spelling_conflicts(p1_text),
        'attribution': attribution_in_prose(body),
        'formulas': formula_check(body, p1_text),
        'plain_symbols': plain_symbols.scan(body),
    }
    figures = figure_check(body, notes, body_fm)
    gate = judgement.check(body)
    summary = summary_line(notes, body)
    previous = judgement.newest_archive(work / 'history', notes.stem)
    drift = judgement.drift(
        body, previous.read_text(encoding='utf-8', errors='replace')
        if previous else None)
    if previous:
        drift['baseline_file'] = previous.name

    return {
        'notes': str(notes), 'work': str(work),
        'extraction_set': {'files': ext['files'], 'consistent': ext['consistent'],
                           'mismatched': ext['mismatched'],
                           'malformed': ext['malformed']},
        'counts': {'extracted': len(extracted), 'placed': len(placed),
                   'cited': len(cited & extracted), 'discarded': len(dropped),
                   'signals': len(signals)},
        'writing': writing,
        'judgement': gate,
        'figures': figures,
        'judgement_drift': drift,
        'summary_line': summary,
        'coverage': f'{max(covered, 0)}/{len(extracted)}',
        'complete': not unplaced and not uncited and empty_scan is None,
        'empty_scan': empty_scan,
        'unplaced': unplaced, 'uncited': uncited,
        'discarded': sorted(dropped),
        'orphan_citations': orphan_cites,
        'spine_missing': spine_missing,
        'markers': {'unknown': markers['unknown'],
                    'decorated': markers['decorated'],
                    'corrections': markers['corrections'],
                    'tier_markers_in_notes': markers['tiers']},
        'structure': structure,
        'blocks_write': False,
    }


def _structure(body: str, fm: dict, notes: Path) -> dict:
    """Invariants that are cheap to check and expensive to notice by eye."""
    out = {}
    sections, missing_concept = [], []
    parts = re.split(r'^(##\s+(?!#).+)$', body, flags=re.MULTILINE)
    heading = None
    for chunk in parts:
        m = re.match(r'^##\s+(?!#)(.+?)\s*$', chunk)
        if m:
            heading = m.group(1).strip()
            continue
        if heading is None:
            continue
        sections.append(heading)
        if heading.lower() not in FIXED_SECTIONS and \
                not CONCEPT_RE.search(chunk):
            missing_concept.append(heading)
        heading = None
    out['sections'] = sections
    out['sections_without_concept_id'] = missing_concept
    out['numbered_headings'] = [h for h in sections if re.match(r'^\d+[.)]\s', h)]
    out['my_additions'] = '## My additions' in body
    # The quarantine, checked where the evidence would actually appear.
    breach = []
    for key in ('sources', 'sources_stat', 'inputs'):
        if 'Explanations' in json.dumps(fm.get(key), default=str):
            breach.append(key)
    out['quarantine_breach'] = breach
    return out


def render_report(result: dict, extras: dict | None = None) -> str:
    extras = extras or {}
    r = result
    lines = ['# Pass D verification', '',
             f"Notes: `{r['notes']}`", '',
             f"Coverage: **{r['coverage']}**"
             + ('' if r['complete'] else '  ⚠️ gaps below'), '',
             '| Set | Count |', '|---|---|',
             f"| extracted (G excluded) | {r['counts']['extracted']} |",
             f"| placed in the spine | {r['counts']['placed']} |",
             f"| cited in the notes | {r['counts']['cited']} |",
             f"| discarded, non-content | {r['counts']['discarded']} |",
             f"| assignment signals (G, not in coverage) | {r['counts']['signals']} |",
             '']
    if r['spine_missing']:
        lines += ['> No `B_spine.md` on disk, so "placed" was taken from what '
                  'the notes cite. Unplaced items cannot be distinguished from '
                  'uncited ones in this run.', '']
    for name, key, why in [
            ('Unplaced', 'unplaced',
             'extracted by Pass A, in no spine node, not discarded'),
            ('Uncited', 'uncited',
             'in the spine, never cited in the written notes'),
            ('Citations with no extraction', 'orphan_citations',
             'a marker in the notes naming an ID Pass A never emitted. Either '
             'the ID was invented or the extraction set is from another run.')]:
        if r[key]:
            lines += [f'## {name} ({len(r[key])})', '', f'_{why}_', '']
            lines += [f'- `{i}`' for i in r[key]] + ['']
    m = r['markers']
    if m['unknown']:
        lines += ['## Unrecognised markers', '',
                  'These match no family in `note-invariants.md` §1. A marker '
                  'nothing can parse is an item nothing can verify.', '']
        lines += [f'- `[{t}]`' for t in m['unknown']] + ['']
    if m['decorated']:
        lines += ['## Decorated markers', '',
                  'Extra text inside a source marker. Pass D matches IDs by '
                  'exact string, so decoration reads as a coverage gap.', '']
        lines += [f"- `[{d['text']}]` -> unknown parts: {d['unknown']}"
                  for d in m['decorated']] + ['']
    if m['tier_markers_in_notes']:
        lines += ['## Quarantine: tier markers in a notes file', '',
                  'Tier markers belong to course-explain and never appear in '
                  'notes. Their presence means tutor prose reached this file.', '']
        lines += [f'- `[{t}]`' for t in m['tier_markers_in_notes']] + ['']
    s = r['structure']
    if s['quarantine_breach']:
        lines += ['## Quarantine breach in frontmatter', '',
                  'A path under `Explanations/` appears in '
                  + ', '.join(f'`{k}`' for k in s['quarantine_breach'])
                  + '. Tutor output has been ingested as a lesson source.', '']
    if s['sections_without_concept_id']:
        lines += ['## Sections with no concept ID', '']
        lines += [f'- {h}' for h in s['sections_without_concept_id']] + ['']
    if s['numbered_headings']:
        lines += ['## Numbered headings', '',
                  'A numbered heading breaks every link into it the moment a '
                  'section is inserted above.', '']
        lines += [f'- {h}' for h in s['numbered_headings']] + ['']
    if not r['extraction_set']['consistent']:
        lines += ['## Extraction set disagrees with this run', '',
                  'Some `A_*.md` carry a different `run` or `sources_hash`. A '
                  'reader must refuse a mismatched set.', '']
        lines += [f'- {x}' for x in r['extraction_set']['mismatched']] + ['']
    if r['extraction_set']['malformed']:
        lines += ['## Malformed IDs', '']
        lines += [f"- `{x['id']}`: {x['reason']}"
                  for x in r['extraction_set']['malformed']] + ['']
    w = r.get('writing') or {}
    if w.get('unsupported_specifics'):
        lines += ['## Unsupported specifics', '',
                  'A number whose only support is a priority 2-3 source, and '
                  'which appears in no slide, book or handout extraction. Mark '
                  'it `[<id>, transcript only]` or drop it.', '']
        lines += [f"- `{x['token']}` in {', '.join(x['markers'])}: {x['text']}"
                  for x in w['unsupported_specifics']] + ['']
    if w.get('spelling_conflicts'):
        lines += ['## Source spelling disagreements', '',
                  'Two authoritative sources spell the same name differently. '
                  'Use the majority form and say so in the notes.', '']
        lines += [f"- `{x['a']}` x{x['a_count']} vs `{x['b']}` x{x['b_count']} "
                  f"-> use **{x['majority']}**" for x in w['spelling_conflicts']] + ['']
    if w.get('attribution'):
        lines += [f"## Attribution in prose ({len(w['attribution'])})", '',
                  'Notes state facts and their explanations; the source marker '
                  'carries provenance. Attribution belongs only in a quote, a '
                  'callout, a cross-source conflict or a transcript-only claim.', '']
        lines += [f"- `{x['phrase']}` line {x['line']}: {x['text']}"
                  for x in w['attribution'][:40]] + ['']
        if len(w['attribution']) > 40:
            lines += [f"- ... {len(w['attribution']) - 40} more", '']
    g = r.get('judgement') or {}
    if g.get('present') and g.get('problems'):
        lines += [f"## Judgement zone ({len(g['problems'])})", '',
                  '`## What to remember` is the one zone that is not from a '
                  'source, so its discipline is checked rather than trusted '
                  '(note-invariants §2a).', '']
        lines += [f"- `{x['kind']}`{': ' + x['detail'] if x['detail'] else ''} "
                  f"-> {x['fix']}" for x in g['problems']] + ['']
    if w.get('formulas'):
        lines += [f"## Formulas ({len(w['formulas'])})", '',
                  "A formula is reproduced in the source's own notation, like a "
                  "table, and every symbol in it is explained directly below "
                  "it.", '']
        for x in w['formulas']:
            lines += [f"- `{x['kind']}` line {x['line']}: {x['symbols']} "
                      f"-> `{x['formula']}`"]
        lines += ['']
    if w.get('plain_symbols'):
        ps = w['plain_symbols']
        lines += [f"## Plain symbols ({len(ps)})", '',
                  'A mathematical symbol in running text is inline math '
                  '(note-invariants §2d). Written as plain text, Obsidian shows '
                  'it literally, and two underscores on one line can turn the '
                  'words between them italic.', '']
        lines += [f"- `{x['token']}` line {x['line']} -> {x['fix']}: {x['text']}"
                  for x in ps[:60]] + ['']
        if len(ps) > 60:
            lines += [f'- ... {len(ps) - 60} more', '']
    f = r.get('figures') or {}
    if f.get('problems'):
        lines += [f"## Figures ({len(f['problems'])})", '',
                  'A curve, a flow, a mapping or an aligned table is shown, not '
                  'only described: a paraphrase loses exactly what the picture '
                  'carries. Decoration is not shown. Every figure keeps a '
                  'caption and its source id.', '']
        for x in f['problems']:
            where = f" line {x['line']}" if x.get('line') else ''
            lines += [f"- `{x['kind']}`{where}: {x['detail']} -> {x['fix']}"]
        lines += ['']
    s = r.get('summary_line') or {}
    if s.get('problems'):
        lines += [f"## Summary line ({len(s['problems'])})", '',
                  'The notes and the overview carry the same one-sentence '
                  'summary, byte for byte. Two that drift apart are worse than '
                  'one.', '']
        for x in s['problems']:
            extra = ''
            if 'notes' in x:
                extra = (f"\n  - notes: {x['notes']}\n  - overview: "
                         f"{x['overview']}")
            lines += [f"- `{x['kind']}` -> {x['fix']}{extra}"]
        lines += ['']
    d = r.get('judgement_drift') or {}
    if d.get('baseline') and (d.get('entered') or d.get('left') or d.get('reworded')):
        lines += ['## Judgement drift', '',
                  'What changed in **Must know** since the previous run. '
                  'Model judgement is not deterministic, so a reshuffle you '
                  'cannot see is a reshuffle you cannot question.',
                  f"Baseline: `{d.get('baseline_file', 'previous version')}`.", '']
        for k in d.get('entered') or []:
            lines += [f'- `entered` {k}']
        for k in d.get('left') or []:
            lines += [f'- `left` {k}']
        for x in d.get('reworded') or []:
            lines += [f"- `reworded` {x['from']} -> {x['to']}"]
        lines += ['']
    for title, rows in (('Down-weighted highlights', extras.get('down_weighted')),
                        ('Transcript corrections', extras.get('transcript_corrections')),
                        ('Discarded, non-content', extras.get('non_content')),
                        ('Verify flags', extras.get('flags')),
                        ('Broken links', extras.get('broken_links'))):
        if rows:
            # `extras` values are row lists. A caller passing a bare count used
            # to raise TypeError here and produce no report at all -- and this
            # file is a contract skill D reads, so no report is worse than a
            # thin one. Accept a scalar as a count and say so.
            if isinstance(rows, int):
                lines += [f'## {title} ({rows})', '',
                          '_Count only; the caller passed a number rather than '
                          'the rows._', '']
                continue
            if isinstance(rows, (str, bytes)):
                rows = [rows]
            lines += [f'## {title} ({len(rows)})', '']
            lines += [f'- {json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else x}'
                      for x in rows] + ['']
    lines += ['---', '',
              'Incomplete coverage never blocks the write. Notes with a flagged '
              'gap beat no notes.', '']
    return '\n'.join(lines)


def write_report(work: Path | str, result: dict, extras: dict | None = None,
                 apply_it: bool = False) -> str:
    path = Path(work) / REPORT_NAME
    text = render_report(result, extras)
    if apply_it:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(text, encoding='utf-8')
        os.replace(tmp, path)
    return str(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('check', 'report'):
        p = sub.add_parser(name)
        p.add_argument('--work', required=True)
        p.add_argument('--notes', required=True)
        p.add_argument('--spine')
        p.add_argument('--discarded', nargs='*', default=[])
        p.add_argument('--run'); p.add_argument('--hash')
        if name == 'report':
            p.add_argument('--extras', help='JSON with down_weighted, '
                                            'transcript_corrections, '
                                            'non_content, flags, broken_links')
            p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)

    out = check(args.work, args.notes, args.spine, args.discarded,
                args.run, args.hash)
    if args.cmd == 'report':
        extras = json.loads(args.extras) if args.extras else {}
        out['report'] = write_report(args.work, out, extras, args.apply)
        out['applied'] = args.apply
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
