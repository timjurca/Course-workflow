#!/usr/bin/env python3
"""Read and write the correction logs, and allocate the ids nothing may reuse.

The log is the **only** record that a correction ever happened. The notes
themselves normally carry no marker (note-invariants section 3), so if a block
here is lost or silently rewritten, the fix disappears from history and the next
B run quietly takes the error back. Three consequences shape this module:

  * **Line-surgical updates, never a re-render.** Changing a status rewrites
    that one `status:` line inside the block's own raw text and leaves every
    other byte alone. A round-trip through a parser is where a quote style, an
    unrecognised key or a hand-added note goes missing.
  * **An unparseable block stops the run.** Spec section 21: report the block,
    never rewrite the file. A log we cannot read is a log we must not touch.
  * **Ids are allocated from a counter that only ever goes up**, and the counter
    is rebuilt from the highest id actually present when `corrections.json` is
    lost. A reused `c-0003` would make two different corrections share one
    archive name, and `undo` would restore the wrong pre-image.

`corrections.json` holds no course code and no lesson number in any **key**
(spec section 4, D-14): a lesson appears only as the value of a `lesson` field,
which is what lets `migrate.py` move it with one field mapper and what makes a
course-code rename cost nothing.

CLI:
    log.py read    --file <log.md>
    log.py open    --file <log.md> --run <notes run>
    log.py append  --file <log.md> --entry <entry.json> [--apply]
    log.py set     --file <log.md> --id c-0003 --field status=applied [...] [--apply]
    log.py state   --course <path>
    log.py rebuild --course <path> [--apply]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))

MIDDOT = '·'

HEADER_LINES = (
    '> [!warning] Written by course-corrections. Never edit this file by hand.\n'
    '> Every block below is replayed into the notes after they are regenerated.\n'
    '<!-- course-corrections:log v1 -->\n'
    '<!-- applied_renumbers: -->\n'
)

HEAD_RE = re.compile(
    r'^##\s+(?P<id>[cg]-\d{4})\s+' + MIDDOT + r'\s+(?P<date>\S+)\s+'
    + MIDDOT + r'\s+(?P<op>\S+)\s*$')
FIELD_RE = re.compile(r'^(?P<key>[a-z_]+):\s?(?P<value>.*)$')
APPLIED_RE = re.compile(r'^<!--\s*applied_renumbers:\s*(?P<ids>.*?)\s*-->\s*$')

# Fixed English, always (spec section 18). A status outside this set is a hand
# edit or a bug, and either way is not something to guess at.
STATUSES = ('applied', 'pending', 'absorbed', 'orphaned', 'withdrawn')
OPERATIONS = ('replace', 'insert_after', 'delete')
BASES = ('source', 'user')
VERIFIED = ('sympy', 'numeric', 'marker', 'not machine-verified')

# Order in which fields are written, so two blocks written months apart look the
# same and a diff of the log stays readable.
FIELD_ORDER = ('group', 'lesson', 'concept', 'section', 'file', 'before', 'after',
               'basis', 'evidence', 'origin', 'errata', 'terms_json', 'verified',
               'status', 'last_replayed')

STATE_NAME = 'corrections.json'


# --------------------------------------------------------------------------
# value encoding


def encode(value) -> str:
    """One line per field where possible; a block scalar when the text has one.

    `before` and `after` are verbatim note text, so they may contain colons,
    quotes and newlines. JSON string form round-trips all of that and is the
    same notation the rest of the plugin already uses.
    """
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if not isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if '\n' in value:
        body = '\n'.join('  ' + ln for ln in value.split('\n'))
        return '|\n' + body
    if value and (value[0] in '"[{' or value != value.strip()
                  or value.startswith('|')):
        return json.dumps(value, ensure_ascii=False)
    return value


def decode(raw: str):
    raw = raw.rstrip('\n')
    if raw in ('true', 'false'):
        return raw == 'true'
    if raw.startswith('"') or raw.startswith('[') or raw.startswith('{'):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


# --------------------------------------------------------------------------
# parsing


def parse_log(path: Path | str) -> dict:
    """Every block, with its raw lines kept so an update can be line-surgical."""
    path = Path(path)
    out = {'file': str(path), 'exists': path.is_file(), 'entries': [],
           'applied_renumbers': [], 'errors': [], 'header': ''}
    if not out['exists']:
        return out
    lines = path.read_text(encoding='utf-8').splitlines()

    current = None
    header: list[str] = []
    pending_key = None
    pending_val: list[str] = []
    in_comment = False

    def close_pending():
        nonlocal pending_key, pending_val
        if current is not None and pending_key is not None:
            current['fields'][pending_key] = '\n'.join(pending_val)
        pending_key, pending_val = None, []

    for no, line in enumerate(lines, 1):
        # An HTML comment is explanatory text, not a field. The template carries
        # one, and a reader who copies it must not end up with an unparseable log.
        if in_comment:
            if current is not None:
                current['raw'].append(line)
            else:
                header.append(line)
            if '-->' in line:
                in_comment = False
            continue
        if line.lstrip().startswith('<!--') and '-->' not in line:
            in_comment = True
            if current is not None:
                current['raw'].append(line)
            else:
                header.append(line)
            continue
        m = APPLIED_RE.match(line)
        if m and current is None:
            out['applied_renumbers'] = [x.strip() for x in m.group('ids').split(',')
                                        if x.strip()]
        head = HEAD_RE.match(line)
        if head:
            close_pending()
            if current:
                out['entries'].append(current)
            current = {'id': head.group('id'), 'date': head.group('date'),
                       'operation': head.group('op'), 'fields': {},
                       'raw': [line], 'line': no}
            continue
        if current is None:
            header.append(line)
            continue
        current['raw'].append(line)
        if pending_key is not None:
            if line.startswith('  ') or not line.strip():
                pending_val.append(line[2:])
                continue
            close_pending()
        if not line.strip():
            continue
        if line.lstrip().startswith('<!--') and line.rstrip().endswith('-->'):
            continue
        fm = FIELD_RE.match(line)
        if fm:
            key, value = fm.group('key'), fm.group('value')
            if value.strip() == '|':
                pending_key, pending_val = key, []
            else:
                current['fields'][key] = value
            continue
        if line.startswith('#'):
            out['errors'].append({'line': no, 'text': line,
                                  'reason': 'a heading inside a correction block'})
        else:
            out['errors'].append({'line': no, 'text': line,
                                  'reason': 'not a "key: value" line'})
    close_pending()
    if current:
        out['entries'].append(current)
    out['header'] = '\n'.join(header)

    for e in out['entries']:
        e['values'] = {k: decode(v) for k, v in e['fields'].items()}
        if e['operation'] not in OPERATIONS:
            out['errors'].append({'line': e['line'], 'text': e['operation'],
                                  'reason': 'unknown operation'})
        st = e['values'].get('status')
        if st is not None and st not in STATUSES:
            out['errors'].append({'line': e['line'], 'text': str(st),
                                  'reason': 'unknown status'})
    seen = {}
    for e in out['entries']:
        if e['id'] in seen:
            out['errors'].append({'line': e['line'], 'text': e['id'],
                                  'reason': f'duplicate id, first seen at line {seen[e["id"]]}'})
        seen[e['id']] = e['line']
    out['ok'] = not out['errors']
    return out


def require_parsable(data: dict) -> None:
    if not data.get('ok', True):
        raise ValueError('correction log cannot be parsed: '
                         + '; '.join(f'line {e["line"]}: {e["reason"]}'
                                     for e in data['errors']))


# --------------------------------------------------------------------------
# derived state


def needs_replay(entry: dict, notes_run: str | None) -> bool:
    """Derived, never stored (note-invariants section 15).

    `applied` plus a `last_replayed` naming a different notes `run` means B has
    rewritten the file since the fix was last present in it.
    """
    v = entry.get('values', entry.get('fields', {}))
    if v.get('status') != 'applied':
        return False
    if not notes_run:
        return False
    recorded = str(v.get('last_replayed') or '')
    m = re.search(r'run\s+(\S+)', recorded)
    if not m:
        return True
    return m.group(1) != str(notes_run)


def open_entries(data: dict, notes_run: str | None) -> list[dict]:
    """What C's gate and D's `review` both mean by "open"."""
    out = []
    for e in data['entries']:
        v = e['values']
        if v.get('status') in ('pending', 'orphaned'):
            why = v['status']
        elif needs_replay(e, notes_run):
            why = 'needs replay'
        else:
            continue
        # `why` is written last on purpose: an entry may carry its own `reason`
        # field, and the caller must still be told which rule made it open.
        out.append({'id': e['id'], **v, 'open_because': why})
    return out


# --------------------------------------------------------------------------
# writing


def render_entry(entry: dict) -> str:
    date = entry.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    head = f'## {entry["id"]} {MIDDOT} {date} {MIDDOT} {entry["operation"]}'
    lines = [head]
    fields = entry.get('values', entry.get('fields', {}))
    for key in FIELD_ORDER:
        if key in fields and fields[key] not in (None, ''):
            lines.append(f'{key}: {encode(fields[key])}')
    for key in sorted(k for k in fields if k not in FIELD_ORDER):
        if fields[key] not in (None, ''):
            lines.append(f'{key}: {encode(fields[key])}')
    return '\n'.join(lines) + '\n'


def _atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)


def ensure_log(path: Path | str, apply: bool = False) -> dict:
    """Created on the first correction for that lesson, never earlier."""
    path = Path(path)
    if path.is_file():
        return {'file': str(path), 'created': False}
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic(path, HEADER_LINES)
    return {'file': str(path), 'created': True, 'written': apply}


def append_entries(path: Path | str, entries: list[dict],
                   apply: bool = False) -> dict:
    path = Path(path)
    data = parse_log(path)
    require_parsable(data)
    known = {e['id'] for e in data['entries']}
    fresh = [e for e in entries if e['id'] not in known]

    # Refuse a stub. `render_entry` reads `entry['values']`, so an entry handed
    # over with flat keys renders as a bare `## c-0001 · date · replace` header
    # and every field is dropped in silence. That log block is unreplayable: the
    # anchor, the corrected text and the basis are all gone, so the next
    # course-notes run takes the error back and nothing reports it. This
    # happened once, to c-0001. note-invariants section 5 says a parser must
    # reject an unknown shape loudly rather than ignore it; so must a writer.
    REQUIRED = ('file', 'before', 'basis', 'origin', 'verified', 'status')
    problems = []
    for e in fresh:
        fields = e.get('values', e.get('fields')) or {}
        if not fields:
            problems.append({'id': e['id'], 'reason':
                             'entry carries no fields: put them under "values"'})
            continue
        missing = [k for k in REQUIRED if not fields.get(k)]
        if e.get('operation') in ('replace', 'insert_after') and not fields.get('after'):
            missing.append('after')
        if missing:
            problems.append({'id': e['id'],
                             'reason': 'missing required field(s): '
                                       + ', '.join(missing)})
    if problems:
        return {'file': str(path), 'ok': False, 'appended': [],
                'problems': problems, 'written': False,
                'note': 'nothing was written: a log block without these fields '
                        'cannot be replayed, which silently loses the correction'}
    text = path.read_text(encoding='utf-8') if path.is_file() else HEADER_LINES
    if not text.endswith('\n'):
        text += '\n'
    blocks = ''.join('\n' + render_entry(e) for e in fresh)
    if apply and fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic(path, text + blocks)
    return {'file': str(path), 'appended': [e['id'] for e in fresh],
            'skipped_existing': [e['id'] for e in entries if e['id'] in known],
            'written': apply and bool(fresh)}


def set_fields(path: Path | str, entry_id: str, changes: dict,
               apply: bool = False) -> dict:
    """Rewrite named `key: value` lines inside one block, and nothing else."""
    path = Path(path)
    data = parse_log(path)
    require_parsable(data)
    target = next((e for e in data['entries'] if e['id'] == entry_id), None)
    if target is None:
        return {'ok': False, 'reason': f'{entry_id} is not in {path.name}'}

    lines = path.read_text(encoding='utf-8').splitlines()
    start = target['line'] - 1
    end = start + len(target['raw'])
    block = lines[start:end]

    for key, value in changes.items():
        encoded = encode(value)
        rendered = (f'{key}: {encoded}').split('\n')
        replaced = False
        out: list[str] = []
        skipping = False
        for ln in block:
            if skipping:
                if ln.startswith('  ') or not ln.strip():
                    continue
                skipping = False
            fm = FIELD_RE.match(ln)
            if fm and fm.group('key') == key and not replaced:
                out.extend(rendered)
                replaced = True
                if fm.group('value').strip() == '|':
                    skipping = True
                continue
            out.append(ln)
        if not replaced:
            while out and not out[-1].strip():
                out.pop()
            out.extend(rendered)
        block = out

    new_lines = lines[:start] + block + lines[end:]
    text = '\n'.join(new_lines) + '\n'
    if apply:
        _atomic(path, text)
    return {'ok': True, 'file': str(path), 'id': entry_id,
            'changed': sorted(changes), 'written': apply}


def set_applied_renumbers(path: Path | str, ids: list[str],
                          apply: bool = False) -> dict:
    """The log's own idempotency marker, so a migration is never applied twice.

    It lives in the file it protects rather than in `corrections.json`, because
    a run interrupted between the two would otherwise remap the same block a
    second time — and a chained renumber (L03->L04, L04->L05) is not idempotent.
    """
    path = Path(path)
    if not path.is_file():
        return {'ok': False, 'reason': 'log does not exist'}
    lines = path.read_text(encoding='utf-8').splitlines()
    marker = f'<!-- applied_renumbers: {", ".join(ids)} -->'
    for i, ln in enumerate(lines):
        if APPLIED_RE.match(ln):
            lines[i] = marker
            break
    else:
        lines.insert(0, marker)
    if apply:
        _atomic(path, '\n'.join(lines) + '\n')
    return {'ok': True, 'file': str(path), 'applied_renumbers': ids,
            'written': apply}


# --------------------------------------------------------------------------
# corrections.json


def state_path(course: Path | str) -> Path:
    return Path(course) / '.data' / STATE_NAME


def blank_state() -> dict:
    return {'applied_renumbers': [], 'counters': {'c': 0, 'e': 0, 'g': 0},
            'fingerprints': [], 'last_run': None}


def read_state(course: Path | str) -> dict:
    path = state_path(course)
    if not path.is_file():
        return blank_state()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return blank_state()
    base = blank_state()
    base.update(data if isinstance(data, dict) else {})
    return base


def write_state(course: Path | str, state: dict, apply: bool = False) -> dict:
    path = state_path(course)
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic(path, json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    return {'file': str(path), 'written': apply}


def allocate(state: dict, kind: str, count: int = 1) -> list[str]:
    """Ids only ever go up. A reused id would collide in the archive names."""
    if kind not in ('c', 'e', 'g'):
        raise ValueError(f'unknown id kind {kind!r}')
    counters = state.setdefault('counters', {'c': 0, 'e': 0, 'g': 0})
    start = int(counters.get(kind, 0))
    ids = [f'{kind}-{start + n:04d}' for n in range(1, count + 1)]
    counters[kind] = start + count
    return ids


def all_logs(course: Path | str) -> list[Path]:
    course = Path(course)
    out = []
    for parent in ('Lessons', 'Tutorials'):
        root = course / parent
        if root.is_dir():
            out.extend(sorted(root.glob('*/notes_corrections.md')))
    shared = course / '.data' / 'shared_corrections.md'
    if shared.is_file():
        out.append(shared)
    return out


def rebuild_state(course: Path | str, apply: bool = False) -> dict:
    """Recover `corrections.json` without ever handing out an id twice.

    Counters come from the highest id **found in the logs**, `applied_renumbers`
    is pre-filled with every block id in A's log (note-invariants section 17: a
    rebuild never re-applies an old block and never skips a pending one), and the
    per-lesson fingerprints are simply gone — they are re-recorded at the next
    write, and until then `scan` honestly reports "no baseline".
    """
    from renumber import renumber_blocks                          # noqa: E402
    course = Path(course)
    state = blank_state()
    highest = {'c': 0, 'e': 0, 'g': 0}
    unreadable = []
    for log in all_logs(course):
        data = parse_log(log)
        if not data['ok']:
            unreadable.append(str(log.relative_to(course)))
            continue
        for e in data['entries']:
            kind, _, num = e['id'].partition('-')
            highest[kind] = max(highest.get(kind, 0), int(num))
            grp = e['values'].get('group')
            if isinstance(grp, str) and grp.startswith('g-'):
                highest['g'] = max(highest['g'], int(grp.split('-')[1]))
            err = e['values'].get('errata')
            if isinstance(err, str) and err.startswith('e-'):
                highest['e'] = max(highest['e'], int(err.split('-')[1]))
    errata = course / '.data' / 'source_errata.json'
    if errata.is_file():
        try:
            blob = json.loads(errata.read_text(encoding='utf-8'))
            for row in (blob.get('errata') or []):
                num = int(str(row.get('id', 'e-0000')).split('-')[1])
                highest['e'] = max(highest['e'], num)
        except (ValueError, OSError, IndexError):
            unreadable.append('.data/source_errata.json')
    state['counters'] = highest
    state['applied_renumbers'] = [b['id'] for b in renumber_blocks(course)]
    write_state(course, state, apply)
    return {'state': state, 'unreadable': unreadable,
            'lost': ['per-lesson fingerprints (scan has no baseline until the '
                     'next write)', 'the last run (undo is not available)'],
            'written': apply}


# --------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('read'); p.add_argument('--file', required=True)
    p = sub.add_parser('open')
    p.add_argument('--file', required=True); p.add_argument('--run')
    p = sub.add_parser('append')
    p.add_argument('--file', required=True); p.add_argument('--entry', required=True)
    p.add_argument('--apply', action='store_true')
    p = sub.add_parser('set')
    p.add_argument('--file', required=True); p.add_argument('--id', required=True)
    p.add_argument('--field', action='append', default=[])
    p.add_argument('--apply', action='store_true')
    p = sub.add_parser('state'); p.add_argument('--course', required=True)
    p = sub.add_parser('rebuild')
    p.add_argument('--course', required=True); p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)

    try:
        out = _run(args)
    except ValueError as exc:
        # A log we cannot parse is reported, never repaired and never rewritten.
        json.dump({'ok': False, 'stop': str(exc)}, sys.stdout,
                  ensure_ascii=False, indent=2)
        sys.stdout.write('\n')
        return 2
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


def _run(args):
    if args.cmd == 'read':
        out = parse_log(args.file)
        for e in out['entries']:
            e.pop('raw', None)
    elif args.cmd == 'open':
        data = parse_log(args.file)
        require_parsable(data)
        out = {'open': open_entries(data, args.run)}
    elif args.cmd == 'append':
        entries = json.loads(Path(args.entry).read_text(encoding='utf-8'))
        if isinstance(entries, dict):
            entries = [entries]
        ensure_log(args.file, args.apply)
        out = append_entries(args.file, entries, args.apply)
    elif args.cmd == 'set':
        changes = {}
        for item in args.field:
            key, _, value = item.partition('=')
            changes[key] = value
        out = set_fields(args.file, args.id, changes, args.apply)
    elif args.cmd == 'state':
        out = read_state(args.course)
    else:
        out = rebuild_state(args.course, args.apply)
    return out


if __name__ == '__main__':
    raise SystemExit(main())
