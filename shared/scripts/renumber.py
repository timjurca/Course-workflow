#!/usr/bin/env python3
"""One idempotency rule for lesson renumbering, shared by B, C, D and E.

Skill A renumbers a lesson: it renames the folders and the generated files,
rewrites link targets and TOC markers, and writes a `## renumber` block to
`_Inbox/_filing_log.md`. It never edits another skill's data file. Each other
skill migrates its own records from that block and records the block id it has
applied.

Four separate implementations of this rule is how three of them end up subtly
different, so there is one, and each skill supplies only a **field mapper**
saying which of its fields hold `L<NN>`/`T<NN>` values.

The rules that matter:

  * **All moves of a block are applied together**, as one simultaneous mapping.
    Applying `L03 -> L04` and then `L04 -> L05` in sequence would move L03 twice
    and land it on L05. A chain and a swap are both normal.
  * A block is applied **once**; its id then goes into `applied_renumbers`.
  * Migration happens on the next run that gets far enough to write. A run that
    stops earlier applies nothing, so "older than my latest run" always means
    "already applied" — which is what a rebuild relies on.
  * A renumber block is **never undone**. A wrong renumber is fixed by another.

CLI:
    renumber.py blocks --course <path>
    renumber.py pending --course <path> --applied <id> ... [--since <ISO>]
    renumber.py remap --moves "L04->L05,L03->L04" --values L03 T02
    renumber.py migrate --course <path> --file <json> --spec <json> [--apply]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LOG_REL = Path('_Inbox') / '_filing_log.md'

BLOCK_HEAD_RE = re.compile(
    r'^##\s+(?P<kind>batch|renumber|code-rename)\s+(?P<ts>\S+)\s+·\s+id\s+(?P<id>\S+)\s*$')
MOVE_RE = re.compile(r'([LT]\d{2})\s*->\s*([LT]\d{2})')
KEY_RE = re.compile(r'(?<![A-Za-z0-9])([LT]\d{2})(?![A-Za-z0-9])')


def parse_filing_log(course: Path | str) -> list[dict]:
    """Every block in the log, in file order, with its raw lines kept.

    Used by A's undo and trim-log as well as by this module: one parser, so a
    block A wrote is never a block another script fails to see.
    """
    path = Path(course) / LOG_REL
    if not path.is_file():
        return []
    blocks: list[dict] = []
    current: dict | None = None
    for line in path.read_text(encoding='utf-8').splitlines():
        m = BLOCK_HEAD_RE.match(line)
        if m:
            if current:
                blocks.append(current)
            current = {'kind': m.group('kind'), 'timestamp': m.group('ts'),
                       'id': m.group('id'), 'fields': {}, 'lines': [line],
                       'table': []}
            continue
        if current is None:
            continue
        current['lines'].append(line)
        fm = re.match(r'^(?P<k>[a-z_]+):\s*(?P<v>.*)$', line)
        if fm:
            current['fields'][fm.group('k')] = fm.group('v').strip()
        elif line.strip().startswith('|') and '---' not in line:
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            current['table'].append(cells)
    if current:
        blocks.append(current)
    for b in blocks:
        if b['kind'] == 'renumber':
            b['moves'] = MOVE_RE.findall(b['fields'].get('moves', ''))
    return blocks


def renumber_blocks(course: Path | str) -> list[dict]:
    return [b for b in parse_filing_log(course) if b['kind'] == 'renumber']


def pending_blocks(course: Path | str, applied: list[str],
                   since: str | None = None) -> list[dict]:
    """Blocks this skill has not applied yet.

    `since` is the skill's own latest run timestamp. A block older than it was
    necessarily applied by the run that produced that timestamp, so it is not
    pending even if the id is missing — which is what makes a rebuilt data file
    safe.
    """
    applied_set = set(applied or [])
    out = []
    for b in renumber_blocks(course):
        if b['id'] in applied_set:
            continue
        if since and b['timestamp'] <= since:
            continue
        out.append(b)
    return out


def moves_to_mapping(moves) -> dict:
    """Accepts [('L04','L05'), ...] or 'L04->L05,L03->L04'."""
    if isinstance(moves, str):
        moves = MOVE_RE.findall(moves)
    mapping = {}
    for src, dst in moves:
        if src in mapping and mapping[src] != dst:
            raise ValueError(f'two destinations for {src}')
        mapping[src] = dst
    return mapping


def remap_key(value: str, mapping: dict) -> str:
    """One simultaneous substitution, never a chain."""
    if not isinstance(value, str):
        return value
    return KEY_RE.sub(lambda m: mapping.get(m.group(1), m.group(1)), value)


def remap_all(obj, mapping: dict, fields: set[str] | None = None, _key=None):
    """Walk a JSON structure, remapping strings in the named fields.

    `fields=None` remaps every string it meets. A skill normally passes its own
    field list, because a lesson token inside a free-text field is prose and
    must not be touched.
    """
    if isinstance(obj, dict):
        return {k: remap_all(v, mapping, fields, _key=k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [remap_all(v, mapping, fields, _key=_key) for v in obj]
    if isinstance(obj, str):
        if fields is None or _key in fields:
            return remap_key(obj, mapping)
        return obj
    return obj


def migrate_file(course: Path | str, data_file: Path | str, fields: list[str],
                 apply: bool = False, since: str | None = None) -> dict:
    """Apply every pending block to one JSON data file owned by the caller.

    The file must carry a top-level `applied_renumbers` list; it is created if
    absent, which is what makes a first run on an empty course start cleanly.
    """
    path = Path(data_file)
    if not path.is_file():
        return {'file': str(path), 'exists': False, 'applied': [], 'pending': []}
    data = json.loads(path.read_text(encoding='utf-8'))
    already = data.get('applied_renumbers') or []
    blocks = pending_blocks(course, already, since)
    if not blocks:
        return {'file': str(path), 'exists': True, 'applied': [],
                'pending': [], 'changed': False}
    for b in blocks:
        mapping = moves_to_mapping(b.get('moves') or [])
        if mapping:
            data = remap_all(data, mapping, set(fields))
        already.append(b['id'])
    data['applied_renumbers'] = already
    if apply:
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)
    return {'file': str(path), 'exists': True, 'changed': True,
            'applied': [b['id'] for b in blocks],
            'moves': [b.get('moves') for b in blocks], 'written': apply}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('blocks'); p.add_argument('--course', required=True)
    p.add_argument('--kind', default=None)
    p = sub.add_parser('pending')
    p.add_argument('--course', required=True)
    p.add_argument('--applied', nargs='*', default=[]); p.add_argument('--since')
    p = sub.add_parser('remap')
    p.add_argument('--moves', required=True); p.add_argument('--values', nargs='+', required=True)
    p = sub.add_parser('migrate')
    p.add_argument('--course', required=True); p.add_argument('--file', required=True)
    p.add_argument('--fields', nargs='+', required=True)
    p.add_argument('--since'); p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'blocks':
        blocks = parse_filing_log(args.course)
        if args.kind:
            blocks = [b for b in blocks if b['kind'] == args.kind]
        out = {'blocks': [{k: v for k, v in b.items() if k != 'lines'} for b in blocks]}
    elif args.cmd == 'pending':
        out = {'pending': [{k: v for k, v in b.items() if k != 'lines'}
                           for b in pending_blocks(args.course, args.applied, args.since)]}
    elif args.cmd == 'remap':
        mapping = moves_to_mapping(args.moves)
        out = {'mapping': mapping,
               'values': {v: remap_key(v, mapping) for v in args.values}}
    else:
        out = migrate_file(args.course, args.file, args.fields, args.apply, args.since)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
