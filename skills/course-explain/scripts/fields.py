#!/usr/bin/env python3
"""E's renumber field mapper: which of E's records hold L<NN>/T<NN> values.

A renumbered lesson is the one vault event that silently invalidates records
nobody is looking at. A's log says `L03 -> L04`; every skill migrates its own
files from that block, and a skill that forgets leaves a finding pointing at a
lesson that no longer carries that number and a saved explanation whose link
resolves to someone else's notes. The idempotency rule itself is shared
(`shared/scripts/renumber.py`); what is E-specific is the list of places a
lesson key can hide, and there are three:

  * `.data/explain_findings.json`  - the `lesson` field of every entry
  * `.data/explain_state.json`     - the bookkeeping ledger (no lesson keys of
                                     its own, and that is deliberate: the
                                     coverage index and the rejected list are
                                     keyed by concept ID)
  * `Explanations/*.md`            - the `lessons:` frontmatter list, and every
                                     `[[<CODE>_L<NN>_Final_notes…]]` wikilink,
                                     in **every** file, not only the one being
                                     written

The markdown pass is why this module exists at all. `renumber.migrate_file`
handles JSON; a saved explanation is prose with links in it, and a link left
pointing at `ECON_L03_Final_notes` after L03 became L04 lands the student on the
wrong lesson's notes without an error anywhere.

`explain_state.json` is the **single ledger**: one `applied_renumbers` list
decides what is pending for everything E owns, so the three surfaces can never
drift apart into "migrated" and "not migrated". A block is applied to all of
them together or to none, which is the rule in note-invariants section 17.

CLI:
    fields.py pending  --course <c>
    fields.py migrate  --course <c> [--apply]
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
import renumber                                                      # noqa: E402
from coverage import load_state, write_state                         # noqa: E402

# The JSON fields that hold a lesson key. `lessons` is listed as well as
# `lesson` because note-invariants section 17 names both for E and the cost of a
# field that never appears is nothing, while the cost of a missing one is a
# stale reference nobody sees.
JSON_FIELDS = ['lesson', 'lessons']

FINDINGS_REL = Path('.data') / 'explain_findings.json'
STATE_REL = Path('.data') / 'explain_state.json'

# [[ECON_L03_Final_notes#Heading|alias]] and [[ECON_L03_Overview]] alike: the
# lesson token inside a wikilink **target**. Prose is never touched; a sentence
# reading "as in L03" is the model's words about a lesson, not a reference that
# has to follow the renumber.
# The boundary is the same one renumber.KEY_RE uses: not alphanumeric on
# either side. A plain \b fails here, because the character before the key is
# the underscore in `ECON_L03` and an underscore is a word character.
WIKILINK_TOKEN_RE = re.compile(
    r'(\[\[[^\]\|#]*?)(?<![A-Za-z0-9])([LT])(\d{2})(?![A-Za-z0-9])')
FM_LESSONS_RE = re.compile(r'^(lessons:\s*)(.+)$', re.MULTILINE)


def field_mapper() -> dict:
    """What E hands the shared renumber machinery."""
    return {'skill': 'course-explain', 'json_fields': JSON_FIELDS,
            'json_files': [str(FINDINGS_REL), str(STATE_REL)],
            'markdown': 'Explanations/**/*.md: lessons: frontmatter and wikilink targets'}


def pending(course: Path | str) -> dict:
    state = load_state(course)
    blocks = renumber.pending_blocks(course, state.get('applied_renumbers') or [])
    return {'applied_renumbers': state.get('applied_renumbers') or [],
            'pending': [{'id': b['id'], 'timestamp': b['timestamp'],
                         'moves': b.get('moves')} for b in blocks],
            'state_status': state.get('_status')}


def _remap_markdown(text: str, mapping: dict) -> tuple[str, int]:
    """Lesson keys in wikilink targets and in the `lessons:` frontmatter line."""
    hits = 0

    def link(m):
        nonlocal hits
        key = f'{m.group(2)}{m.group(3)}'
        new = mapping.get(key)
        if not new or new == key:
            return m.group(0)
        hits += 1
        return f'{m.group(1)}{new}'

    out = WIKILINK_TOKEN_RE.sub(link, text)

    def lessons(m):
        nonlocal hits
        before = m.group(2)
        after = renumber.remap_key(before, mapping)
        if after != before:
            hits += 1
        return f'{m.group(1)}{after}'

    # Only the first frontmatter block: a `lessons:` line in the body is prose.
    parts = out.split('---\n')
    if out.startswith('---\n') and len(parts) >= 3:
        parts[1] = FM_LESSONS_RE.sub(lessons, parts[1])
        out = '---\n'.join(parts)
    return out, hits


def migrate(course: Path | str, apply: bool = False) -> dict:
    """Apply every pending block to everything E owns, together, once.

    Called before `save` and before a confirmed finding is written, which are
    two of the three things E writes. The third, a recorded rejection, is
    deliberately exempt: it is keyed by concept ID and no renumber block can
    touch it.
    """
    course = Path(course)
    state = load_state(course)
    blocks = renumber.pending_blocks(course, state.get('applied_renumbers') or [])
    out = {'pending': [b['id'] for b in blocks], 'json': [], 'markdown': [],
           'written': False, 'state_status': state.get('_status')}
    if not blocks:
        out['note'] = 'nothing pending'
        return out

    mapping = {}
    for b in blocks:
        for src, dst in renumber.moves_to_mapping(b.get('moves') or []).items():
            mapping[src] = dst
    out['mapping'] = mapping
    if not mapping:
        out['note'] = 'blocks carry no moves'

    # 1. the findings file
    findings = course / FINDINGS_REL
    if findings.is_file() and mapping:
        try:
            data = json.loads(findings.read_text(encoding='utf-8'))
            new = renumber.remap_all(data, mapping, set(JSON_FIELDS))
            changed = new != data
            new['applied_renumbers'] = sorted(
                set(new.get('applied_renumbers') or []) | {b['id'] for b in blocks})
            out['json'].append({'file': str(FINDINGS_REL), 'changed': changed})
            if apply:
                tmp = findings.with_name(findings.name + '.tmp')
                tmp.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
                os.replace(tmp, findings)
        except Exception as exc:
            out['json'].append({'file': str(FINDINGS_REL), 'error': str(exc)})
            out['halted'] = ('explain_findings.json is unparseable; nothing was '
                             'migrated and no block was marked applied')
            return out
    else:
        out['json'].append({'file': str(FINDINGS_REL),
                            'exists': findings.is_file(), 'changed': False})

    # 2. every saved explanation, tombstones and archives included
    expl = course / 'Explanations'
    if expl.is_dir() and mapping:
        for p in sorted(expl.rglob('*.md')):
            try:
                text = p.read_text(encoding='utf-8')
            except OSError:
                continue
            new_text, hits = _remap_markdown(text, mapping)
            if not hits:
                continue
            out['markdown'].append({'file': str(p.relative_to(course)), 'edits': hits})
            if apply:
                tmp = p.with_name(p.name + '.tmp')
                tmp.write_text(new_text, encoding='utf-8')
                os.replace(tmp, p)

    # 3. the ledger last, so an interrupted run re-applies rather than skips
    if apply:
        state['applied_renumbers'] = sorted(
            set(state.get('applied_renumbers') or []) | {b['id'] for b in blocks})
        write_state(course, state)
        out['written'] = True
        out['applied_renumbers'] = state['applied_renumbers']
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('pending'); p.add_argument('--course', required=True)
    p = sub.add_parser('migrate'); p.add_argument('--course', required=True)
    p.add_argument('--apply', action='store_true')
    p = sub.add_parser('mapper')
    args = ap.parse_args(argv)
    if args.cmd == 'pending':
        out = pending(args.course)
    elif args.cmd == 'mapper':
        out = field_mapper()
    else:
        out = migrate(args.course, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
