#!/usr/bin/env python3
"""Read and check the three marker families, and refuse to guess at a fourth.

Every marker in this plugin is a bracketed token inside note prose, and three
families share one namespace: B's source markers, D's correction markers and E's
tier markers. They are separable by shape alone, deliberately, so that a parser
can tell them apart without knowing which skill wrote the file:

    source      one of SBTAHNCVKG, immediately followed by a digit  [S22] [B15.3]
    correction  a lowercase word, then `: `, then a source ID       [unverified: S22]
    tier        the literals [beyond course] and [your note], or
                `differs from course: <ID>`, or W followed by digits

**An unknown shape is reported, never ignored.** A silently skipped marker is a
silently unmarked claim, and in E's files an unmarked claim reads as course
material - which is the one thing the quarantine exists to prevent. So this
module fails loudly on a bracket it cannot place.

The rest is the checks a saved explanation has to pass before it is written:
the banner present verbatim, every `[W<n>]` resolved in `## External
references`, the tier counts that go into frontmatter, and a list of prose
blocks carrying no marker at all. That last one is a **report, not a verdict**:
a paragraph with no marker is usually tier 1 continuing the sentence before it,
and sometimes an unmarked tier-2 claim. Only a reader can tell, which is why
acceptance check 3 is done by hand.

CLI:
    markers.py scan   --file <f>            classify every marker in a file
    markers.py check  --file <f>            full check of a saved explanation
    markers.py banner                       print the banner, verbatim
    markers.py notes  --file <f>            E markers must never be in a notes file
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
from check_links import strip_code                                   # noqa: E402
from vault import parse_frontmatter                                  # noqa: E402

BRACKET_RE = re.compile(r'\[([^\[\]\n]+)\]')
# A wikilink or a markdown link is not a marker: [[x]] and [text](url).
WIKILINK_RE = re.compile(r'\[\[[^\]]*\]\]')
MDLINK_RE = re.compile(r'\[[^\]]*\]\([^)]*\)')

SOURCE_ID_RE = re.compile(r'^[SBTAHNCVKG]\d[\w.!]*$')
CORRECTION_WORDS = ('source error', 'student, sources differ', 'unverified')
W_RE = re.compile(r'^W\d+$')

BANNER = """> [!warning] Not course material
> Written by course-explain. This is a tutor's explanation, not a source.
> It is not examinable content, it is not read by any other skill, and claims
> marked `[beyond course]`, `[differs from course: …]` or `[W<n>]` are not
> from your course material. The notes are the record.
"""

TIER_OF = {'source': 1, 'beyond course': 2, 'differs from course': 3,
           'external': 4, 'your note': None}


def classify_token(token: str) -> dict:
    """One bracket's contents into a family, or 'unknown'."""
    raw = token.strip()
    low = raw.lower()
    if low == 'beyond course':
        return {'family': 'tier', 'tier': 2, 'kind': 'beyond course'}
    if low == 'your note':
        return {'family': 'tier', 'tier': None, 'kind': 'your note',
                'note': 'the student\'s own writing: never a tier, never evidence'}
    if low == 'not machine-verified':
        return {'family': 'verification', 'tier': None, 'kind': 'not machine-verified'}
    if low.startswith('differs from course:'):
        ref = raw.split(':', 1)[1].strip()
        ok = bool(SOURCE_ID_RE.match(ref))
        return {'family': 'tier', 'tier': 3, 'kind': 'differs from course',
                'ref': ref, 'valid_ref': ok}
    if low.startswith('translation'):
        return {'family': 'translation', 'tier': None, 'kind': raw}
    if W_RE.match(raw):
        return {'family': 'tier', 'tier': 4, 'kind': 'external', 'ref': raw}
    for word in CORRECTION_WORDS:
        if low.startswith(word + ':'):
            ref = raw.split(':', 1)[1].strip()
            return {'family': 'correction', 'tier': None, 'kind': word, 'ref': ref,
                    'valid_ref': bool(SOURCE_ID_RE.match(ref))}
    # A compact source marker: several IDs, plus optional qualifiers such as
    # "corrected by T11", "OCR, verify" or "not lectured".
    parts = [p.strip() for p in raw.split(',') if p.strip()]
    ids = [p.split()[0] for p in parts if p and SOURCE_ID_RE.match(p.split()[0])]
    if ids and len(ids) >= 1 and SOURCE_ID_RE.match(parts[0].split()[0]):
        return {'family': 'source', 'tier': 1, 'kind': 'source', 'ids': ids,
                'qualifiers': [p for p in parts if p.split()[0] not in ids]}
    return {'family': 'unknown', 'tier': None, 'kind': raw,
            'error': ('unrecognised marker shape: it belongs to no family in '
                      'note-invariants section 5. Reported, never ignored.')}


REFS_HEADING_RE = re.compile(r'^##\s+External references\s*$', re.MULTILINE)


def body_of(text: str) -> str:
    """The prose, without frontmatter.

    Frontmatter is YAML, and `concepts: [a, b]` is a list, not a marker. Scanning
    it would report every list in the header as an unrecognised marker shape and
    bury the one that matters.
    """
    _, body = parse_frontmatter(text)
    return body


def scan(text: str) -> dict:
    """Every marker in a body, classified. Code, wikilinks and md links excluded."""
    body = strip_code(text)
    body = WIKILINK_RE.sub(' ', body)
    body = MDLINK_RE.sub(' ', body)
    # Obsidian callouts open with [!warning]; they are syntax, not markers.
    rows = []
    for m in BRACKET_RE.finditer(body):
        token = m.group(1)
        if token.startswith('!') or token.strip() in ('x', ' ', ''):
            continue
        row = classify_token(token)
        row['raw'] = f'[{token}]'
        rows.append(row)
    tiers = {'course': 0, 'beyond': 0, 'differs': 0, 'external': 0}
    for r in rows:
        if r.get('tier') == 1:
            tiers['course'] += 1
        elif r.get('tier') == 2:
            tiers['beyond'] += 1
        elif r.get('tier') == 3:
            tiers['differs'] += 1
        elif r.get('tier') == 4:
            tiers['external'] += 1
    cited = []
    for r in rows:
        for i in r.get('ids') or []:
            if i not in cited:
                cited.append(i)
    # tiers counts *claims*, one per bracket: a compact marker like [B15.1, S12]
    # is one claim resting on two items, and that is what the frontmatter records.
    return {'markers': rows, 'tiers': tiers, 'source_ids_cited': cited,
            'unknown': [r['raw'] for r in rows if r['family'] == 'unknown'],
            'your_note': sum(1 for r in rows if r.get('kind') == 'your note'),
            'not_machine_verified': sum(1 for r in rows
                                        if r.get('kind') == 'not machine-verified'),
            'external_ids': sorted({r['ref'] for r in rows
                                    if r.get('kind') == 'external'})}


def unmarked_blocks(text: str) -> list:
    """Prose blocks carrying no marker at all. A report, never a verdict."""
    body = strip_code(text)
    out = []
    for block in re.split(r'\n\s*\n', body):
        b = block.strip()
        if not b or b.startswith(('#', '>', '|', '---', '<!--', '$$', '*')):
            continue
        if b.startswith(('- ', '1.', '**In the notes', '**Rests on', '**Also covers')):
            continue
        if BRACKET_RE.search(WIKILINK_RE.sub(' ', b)):
            continue
        out.append(b[:160])
    return out


def check(path: Path | str) -> dict:
    """Everything a saved explanation must satisfy before it is written."""
    path = Path(path)
    text = path.read_text(encoding='utf-8', errors='replace')
    body = body_of(text)
    # The reference block *declares* W ids; it does not *claim* with them. Counting
    # both would double every external claim in the frontmatter tier counts.
    split = REFS_HEADING_RE.search(body)
    claims = body[:split.start()] if split else body
    res = scan(claims)
    out = {'file': str(path), 'tiers': res['tiers'], 'unknown_markers': res['unknown'],
           'your_note': res['your_note'],
           'not_machine_verified': res['not_machine_verified'], 'problems': []}

    # The banner is matched as bytes, not as a paraphrase: it is the one line in
    # the file that tells a reader the page is not course material.
    normalised = '\n'.join(l.rstrip() for l in body.splitlines())
    if '\n'.join(l.rstrip() for l in BANNER.strip().splitlines()) not in normalised:
        out['problems'].append({'code': 'banner_missing',
                                'message': ('the not-course-material banner is '
                                            'missing or altered; it is verbatim '
                                            'bytes, pinned in note-invariants '
                                            'section 4')})
    out['banner'] = not any(p['code'] == 'banner_missing' for p in out['problems'])

    if res['unknown']:
        out['problems'].append({'code': 'unknown_marker',
                                'message': 'unrecognised marker shapes: '
                                           + ', '.join(res['unknown'])})
    bad_ref = [r['raw'] for r in res['markers']
               if r.get('kind') == 'differs from course' and not r.get('valid_ref')]
    if bad_ref:
        out['problems'].append({'code': 'bad_tier3_ref',
                                'message': ('a differs-from-course marker must name '
                                            'a B source ID: ' + ', '.join(bad_ref))})

    # Every [W<n>] used must be resolved in the reference block, or the snapshot
    # that keeps the citation from rotting is not there at all.
    declared = set(re.findall(r'^\*\*\[(W\d+)\]\*\*', body, re.MULTILINE))
    used = set(res['external_ids'])
    out['external'] = {'used': sorted(used), 'resolved': sorted(declared)}
    missing = sorted(used - declared)
    if missing:
        out['problems'].append({'code': 'unresolved_external',
                                'message': ('used but not resolved in ## External '
                                            'references: ' + ', '.join(missing))})
    orphan = sorted(declared - used)
    if orphan:
        out['problems'].append({'code': 'orphan_external',
                                'message': ('listed in ## External references but '
                                            'never cited: ' + ', '.join(orphan))})
    out['unmarked_blocks'] = unmarked_blocks(claims)
    out['ok'] = not out['problems']
    out['note'] = ('unmarked_blocks is a report for a human reader, not a failure: '
                   'a block continuing a tier-1 passage legitimately carries no '
                   'marker of its own')
    return out


def notes_check(path: Path | str) -> dict:
    """E's markers must never appear in a notes file. The reverse quarantine.

    A's validate catches E's *prose* reaching the notes through `sources:`. This
    catches the other direction: an E marker written into a file B owns, which
    would make a tutor's claim look like an extraction the next time anything
    parses that file.
    """
    path = Path(path)
    rows = [r for r in scan(body_of(path.read_text(encoding='utf-8',
                                                   errors='replace')))['markers']
            if r['family'] == 'tier' or r.get('kind') == 'your note']
    return {'file': str(path), 'e_markers_found': [r['raw'] for r in rows],
            'ok': not rows,
            'rule': ('E\'s tier markers appear only in chat answers and in files '
                     'under Explanations/. They never appear in a notes file.')}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('scan', 'check', 'notes'):
        p = sub.add_parser(name); p.add_argument('--file', required=True)
    sub.add_parser('banner')
    args = ap.parse_args(argv)
    if args.cmd == 'banner':
        sys.stdout.write(BANNER)
        return 0
    if args.cmd == 'scan':
        out = scan(body_of(Path(args.file).read_text(encoding='utf-8',
                                                     errors='replace')))
    elif args.cmd == 'check':
        out = check(args.file)
    else:
        out = notes_check(args.file)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0 if out.get('ok', True) else 1


if __name__ == '__main__':
    raise SystemExit(main())
