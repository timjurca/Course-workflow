#!/usr/bin/env python3
"""Everything the condensed notes are allowed to draw on, gathered as one object.

The model does not decide what is important and it does not go looking for
figures. Both were already decided and recorded by B, and re-deciding them here
would produce a second, quieter ranking that disagrees with the one the student
can see in `## What to remember`.

So this script reads, and the model only writes:

  concepts       every concept block, with the rank B's judgement zone implies
  figures        every file already in `Final_notes/attachments/`, with the
                 concepts that cite its source id -- a figure cited by no
                 concept is almost always decoration (a title slide, a logo)
  formulas       every $$ block, with the concept it sits in
  doubt          markers that say a claim may be WRONG, which must survive
  provenance     the count of "read from an image" style markers, which must NOT
                 be repeated inline; one summary line carries them instead
  exam_signals   what the lecturer said is, or is not, on the exam

Rank comes from the source ids cited in the judgement zone: a `Must know` bullet
citing `[S14, B4.2.4]` promotes whichever concepts cite those ids. It is indirect
on purpose. The zone is prose the student may have re-ranked themselves, and the
concept ids are the only stable key the two documents share.
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

import judgement                                                   # noqa: E402
import markers                                                     # noqa: E402
import sections as S                                               # noqa: E402
from vault import read_frontmatter                                 # noqa: E402

FORMULA_RE = re.compile(r'\$\$(.+?)\$\$', re.S)
EMBED_RE = re.compile(r'^[ \t]*(?:>[ \t]?)*!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\][ \t]*$', re.M)
DOUBT_RE = re.compile(r'\[(?:source error|unverified|student, sources differ):[^\]]*\]'
                      r'|\[[^\]]*\btranscript only\b[^\]]*\]')
PROVENANCE_RE = re.compile(r'\[[^\]]*\b(?:OCR, verify|from image, verify)\b[^\]]*\]')
WARN_RE = re.compile(r'^>\s*\[!warning\]\s*(.*)$', re.M)
FIG_ID_RE = re.compile(r'_fig_([SBTAHNCVKG]\d+(?:\.\d+)*)_')

MUST, ALSO, REST = 'must-know', 'also-likely', 'rest'

# B's judgement zone caps `Must know` at 10 bullets, but one bullet can cite ids
# spanning several concepts, so the promotion fans out: measured across 14 real
# lessons it lands at 10 to 14, with one lesson reaching 18 of 27 concepts. Above
# this cap the depth curve flattens and the document stops being a revision aid.
MUST_CAP = 12

# Strong exclusions only. "You do not need to look at X" narrows a detail
# inside a concept; it does not take the concept off the exam.
NOT_EXAM_RE = re.compile(r'not (?:be )?part of the exam|will not be (?:part of|on) '
                         r'the exam|not examinable|not (?:be )?on the exam', re.I)


# Phrases a heading spells out and a ranking bullet abbreviates, or the reverse.
# Folded to ONE token on both sides, so "The incremental IRR" is {increm, irr}
# and does not half-match every bullet that mentions an internal rate of return.
PHRASES = (('internal rate of return', 'irr'), ('net present value', 'npv'),
           ('discounted cash flow', 'dcf'), ('time value of money', 'tvm'),
           ('profitability index', 'pi'), ('present value', 'pv'),
           ('future value', 'fv'))
SHORT_KEEP = {'pv', 'fv', 'pi'}
STOP = set("""the a an and or of to for in on as at by its it is are be with from that
this what when why how which their them these those than into over under one two
three four five actually use used""".split())
NAMED = 0.8          # a heading counts as named when this share of its words appear


def _stems(text: str) -> set[str]:
    t = (text or '').lower()
    for phrase, short in PHRASES:
        t = t.replace(phrase, short)
    out = set()
    for w in re.findall(r'[a-z]+', t):
        if w in STOP or (len(w) < 3 and w not in SHORT_KEEP):
            continue
        if w.endswith('s') and len(w) > 3:
            w = w[:-1]
        out.add(w[:6])
    return out


def _lead(text: str) -> str:
    """The bullet's claim, without its 'Ranked ... because ...' justification,
    which often names neighbouring topics only to compare with them."""
    return re.split(r'\bRanked\b', text or '', maxsplit=1)[0]


def _match_bullet(item_text: str, blocks: list[dict], by_id: dict) -> dict:
    """Which concept(s) one ranking bullet is ABOUT.

    Two kinds of evidence, used asymmetrically.

    **Slides** decide. Each source id the bullet cites votes for the concepts
    that cite it, and a vote is split between them, so a slide five concepts
    share counts a fifth as much as a slide only one concept uses. The concept
    with the strongest vote is the bullet's subject.

    **Naming** can add a second subject, never replace the first: a concept
    whose heading the bullet spells out is included too, but only if the
    bullet's slides also touch it. A bullet that merely mentions a topic in
    passing, with no shared slide, promotes nothing.

    This replaced a rule that promoted every concept citing ANY id the bullet
    cited. On FM L03 that carried the incremental IRR, which the lecturer
    excluded from the exam, into Must know because it shares slide S27 with
    the IRR bullet.
    """
    ids = list(dict.fromkeys(markers.base_id(x) for x in markers.find_ids(item_text)))
    ids = [i for i in ids if i in by_id]
    lead = _stems(_lead(item_text))
    scored = []
    for b in blocks:
        heads = _stems(b['heading'])
        named = len(heads & lead) / max(1, len(heads))
        slide = (sum(1 / len(by_id[i]) for i in ids if b['concept'] in by_id[i])
                 / max(1, len(ids)))
        scored.append({'concept': b['concept'], 'slides': round(slide, 3),
                       'named': round(named, 3)})
    with_slides = [s for s in scored if s['slides'] > 0]
    if with_slides:
        primary = max(with_slides, key=lambda s: (s['slides'], s['named']))
    else:
        best = max(scored, key=lambda s: s['named'], default=None)
        primary = best if best and best['named'] >= NAMED else None
    promotes = [primary['concept']] if primary else []
    for s in scored:
        if s['concept'] not in promotes and s['named'] >= NAMED and s['slides'] > 0:
            promotes.append(s['concept'])
    return {'promotes': promotes,
            'basis': ('slides' if with_slides else 'name') if primary else None}


def _rank_map(text: str, blocks: list[dict],
              exam_signals=None) -> tuple[dict, list[dict], list[dict]]:
    """concept id -> rank, from what each judgement-zone bullet is about.

    Returns the rank map, every demotion, and one row per bullet saying which
    concept(s) it promoted, so the plan can show the student the mapping
    instead of asking them to trust it.

    A concept the lecturer said is **not on the exam** is held at `rest`
    whatever a bullet says. The cap is a safety net: with one subject per
    bullet it should rarely fire, and when it does it drops by position, since
    the zone is an ordered ranking.
    """
    by_id: dict[str, set[str]] = {}
    for b in blocks:
        for sid in b['source_ids']:
            by_id.setdefault(markers.base_id(sid), set()).add(b['concept'])
    rank: dict[str, str] = {}
    first_pos: dict[str, int] = {}
    rows: list[dict] = []
    parsed = judgement.parse(text)
    for pos, item in enumerate(parsed.get('items') or []):
        tier = (item.get('tier') or '').lower()
        want = MUST if 'must' in tier else (ALSO if 'also' in tier else None)
        if want is None:
            continue
        m = _match_bullet(item.get('text') or '', blocks, by_id)
        rows.append({'position': pos + 1, 'tier': want,
                     'bullet': _lead(item.get('text') or '').strip()[:90],
                     'promotes': m['promotes'], 'basis': m['basis']})
        for cid in m['promotes']:
            if rank.get(cid) != MUST:
                rank[cid] = want
            if want == MUST:
                first_pos.setdefault(cid, pos)

    demoted = []
    excluded = {s.get('concept') for s in (exam_signals or [])
                if isinstance(s, dict) and NOT_EXAM_RE.search(s.get('text') or '')}
    for cid in sorted(excluded):
        if cid and rank.get(cid) in (MUST, ALSO):
            demoted.append({'concept': cid, 'from': rank[cid], 'to': REST,
                            'why': 'the lecturer said this is not part of the exam '
                                   '(exam_signals); it stays as one line, flagged'})
            rank[cid] = REST

    must = [c for c, r in rank.items() if r == MUST]
    if len(must) > MUST_CAP:
        order = sorted(must, key=lambda c: (first_pos.get(c, 10**6), c))
        for cid in order[MUST_CAP:]:
            rank[cid] = ALSO
            demoted.append({'concept': cid, 'from': MUST, 'to': ALSO,
                            'first_must_know_bullet': first_pos.get(cid, 0) + 1,
                            'why': f'more than {MUST_CAP} concepts were promoted; this '
                                   'one is first touched lowest in the Must know order'})
    return rank, demoted, rows


def build(notes_path: Path | str) -> dict:
    notes_path = Path(notes_path)
    text = notes_path.read_text(encoding='utf-8')
    fm, _ = read_frontmatter(notes_path)
    blocks = S.concept_blocks(text)
    rank, demoted, bullet_rows = _rank_map(text, blocks, fm.get('exam_signals'))

    embedded = set(EMBED_RE.findall(text))
    att_dir = notes_path.parent / 'attachments'
    figures = []
    for p in sorted(att_dir.iterdir()) if att_dir.is_dir() else []:
        if not p.is_file() or p.name.startswith('.'):
            continue
        m = FIG_ID_RE.search(p.name)
        sid = m.group(1) if m else None
        cites = sorted({b['concept'] for b in blocks
                        if sid and any(markers.base_id(x) == sid
                                       for x in b['source_ids'])})
        figures.append({'file': p.name, 'source_id': sid,
                        'embedded_in_notes': p.name in embedded,
                        'cited_by_concepts': cites,
                        'likely_decoration': not cites,
                        'bytes': p.stat().st_size})

    out_concepts = []
    for b in blocks:
        body = text[b['body_start']:b['end']]
        out_concepts.append({
            'concept': b['concept'], 'heading': b['heading'],
            'rank': rank.get(b['concept'], REST),
            'words': len(body.split()),
            'source_ids': b['source_ids'],
            'formulas': [f.strip() for f in FORMULA_RE.findall(body)],
            'doubt': DOUBT_RE.findall(body),
            'provenance_markers': len(PROVENANCE_RE.findall(body)),
            'figures': [f['file'] for f in figures
                        if b['concept'] in f['cited_by_concepts']],
        })

    counts = {r: sum(1 for c in out_concepts if c['rank'] == r)
              for r in (MUST, ALSO, REST)}
    return {
        'notes': notes_path.name,
        'words': len(text.split()),
        'concepts': out_concepts,
        'rank_counts': counts,
        'rank_demotions': demoted,
        'bullet_matches': bullet_rows,
        'unmatched_bullets': [r for r in bullet_rows if not r['promotes']],
        'figures': figures,
        'figure_counts': {'total': len(figures),
                          'embedded': sum(1 for f in figures if f['embedded_in_notes']),
                          'spare': sum(1 for f in figures
                                       if not f['embedded_in_notes']
                                       and not f['likely_decoration']),
                          'likely_decoration': sum(1 for f in figures
                                                   if f['likely_decoration'])},
        'formulas_total': len(FORMULA_RE.findall(text)),
        'doubt_total': len(DOUBT_RE.findall(text)),
        'provenance_total': len(PROVENANCE_RE.findall(text)),
        'warning_callouts': WARN_RE.findall(text),
        'exam_signals': fm.get('exam_signals') or [],
        'flags': fm.get('flags') or [],
        'language': fm.get('language'),
        'title': fm.get('title'),
        'number': fm.get('number'),
        'date': fm.get('date'),
        'course': fm.get('course'),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--notes', required=True)
    ap.add_argument('--brief', action='store_true',
                    help='counts only, for the plan line')
    args = ap.parse_args(argv)
    out = build(args.notes)
    if args.brief:
        out = {k: out[k] for k in ('notes', 'words', 'rank_counts', 'rank_demotions',
                                   'unmatched_bullets',
                                   'figure_counts', 'formulas_total', 'doubt_total',
                                   'provenance_total')}
    # default=str: frontmatter dates arrive as datetime.date, which json refuses
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
