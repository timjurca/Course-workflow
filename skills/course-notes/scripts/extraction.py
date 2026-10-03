#!/usr/bin/env python3
"""Read and write `.work/A_<source>.md`, the one file format four skills share.

This module exists so the Pass A contract has exactly one implementation. The
format is pinned in `shared/note-invariants.md` §11 and read by C, D and E, so a
second writer that drifts by one character does not fail: it produces a file the
other three parse *almost* correctly, and the damage surfaces weeks later as a
coverage gap nobody can explain. Six scripts in this skill emit extractions; all
six call `write()` here.

Three jobs, all deterministic, none of them model work:

  * **IDs.** `validate_id` is the gate. An ID that does not match the grammar in
    note-invariants §2 is rejected loudly at write time, because a malformed ID
    is silently uncovered in Pass D: it never matches a marker, so it is
    reported as a gap forever and no repair pass can close it.
  * **Errata.** `apply_errata` runs at the *end* of Pass A, after transcript
    normalisation, so no later reader ever sees a known misreading. It repairs
    only what it can prove: an erratum whose `wrong` text is absent applies
    nothing and is reported. Forcing it would rewrite an item from a source that
    has since changed, and the extraction would stop being a record of the
    source.
  * **Headers.** `run` and `sources_hash` are copied from the notes of the same
    run. A reader whose values disagree refuses the set. That is the only thing
    that makes a crashed run detectable: Pass A overwrites the extractions
    before the notes are written, so between the two there is a window where
    the extractions and the notes describe different source bytes.

This skill never writes `source_errata.json`; statuses there are skill D's.

CLI:
    extraction.py read --path <A_x.md>
    extraction.py set --work <lesson/.work> [--run <ts>] [--hash <h>]
    extraction.py name --entry "Content/slides_lecture3.pptx"
    extraction.py errata --work <.work> --course <course> --lesson L03 \
                         --sources <entry> [<entry> ...] [--apply]
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
import naming                                                      # noqa: E402

# note-invariants §2. A single uppercase letter from this set followed at once by
# a digit is what makes a source marker distinguishable from D's and E's markers
# without knowing which skill wrote the file.
PREFIXES = 'SBTAHNCVKG'
ID_RE = re.compile(r'^(?P<prefix>[' + PREFIXES + r'])'
                   r'(?P<num>\d+)'
                   r'(?P<sub>(?:\.\d+)*)'
                   r'(?P<speaker>n?)'
                   r'(?P<highlight>!?)$')

# note-invariants §11. Closed, and closed on purpose: a tag nobody else knows is
# a tag nobody else acts on, and the writer cannot tell the difference.
TAGS = {'lectured', 'summary_slide', 'key_box', 'review_item',
        'lecturer_stress', 'exam_signal', 'not_lectured', 'errata'}

# `lectured` is implicit on these, so writing it is redundant rather than wrong.
IMPLICIT_LECTURED = set('STH')

HEADER_KEYS = ('run', 'sources_hash', 'source', 'kind', 'chunks')
ITEM_RE = re.compile(r'^###\s+(?P<id>\S+)\s*$')
TAGS_RE = re.compile(r'^tags:\s*\[(?P<tags>.*)\]\s*$')


class ExtractionError(RuntimeError):
    pass


# ------------------------------------------------------------------ names

def extraction_name(entry: str) -> str:
    """`Content/slides_lecture3.pptx` -> `A_content_slides_lecture3_pptx.md`.

    The 60-character slug cap does **not** apply here (folder-structure §3 step
    7): two long chapter files under one lesson would truncate to the same name
    and the second extraction would silently overwrite the first.
    """
    path = entry.split('#', 1)[0]
    return 'A_' + naming.slugify(path, cap=False) + '.md'


def validate_id(item_id: str) -> dict:
    m = ID_RE.match(item_id or '')
    if not m:
        return {'ok': False, 'id': item_id,
                'reason': 'does not match the source-marker grammar '
                          '(note-invariants §2)'}
    g = m.groupdict()
    if g['speaker'] and g['prefix'] != 'S':
        return {'ok': False, 'id': item_id,
                'reason': 'the "n" speaker-notes suffix exists only on slides'}
    return {'ok': True, 'id': item_id, 'prefix': g['prefix'],
            'highlight': bool(g['highlight'])}


# ------------------------------------------------------------------ write

def _atomic_write(path: Path, text: str) -> None:
    """Write beside, then rename. A half-written extraction that still carries a
    valid header is worse than no file: the reader trusts the header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


def render(run: str, sources_hash: str, source: str, kind: str,
           items: list[dict], chunks: list[str] | None = None) -> str:
    bad = [validate_id(i.get('id')) for i in items]
    bad = [b for b in bad if not b['ok']]
    if bad:
        raise ExtractionError(f'{len(bad)} malformed IDs, first: {bad[0]}')
    unknown = sorted({t for i in items for t in (i.get('tags') or [])} - TAGS)
    if unknown:
        raise ExtractionError(f'tags outside the closed list: {unknown}')

    out = [f'run: {run}', f'sources_hash: {sources_hash}',
           f'source: {source}', f'kind: {kind}']
    if chunks:
        out.append('chunks: [' + ', '.join(chunks) + ']')
    out.append('')
    for item in items:
        out.append(f'### {item["id"]}')
        tags = [t for t in (item.get('tags') or []) if t]
        if tags:
            out.append('tags: [' + ', '.join(tags) + ']')
        out.append((item.get('text') or '').strip())
        out.append('')
    return '\n'.join(out).rstrip('\n') + '\n'


def write(work: Path | str, entry: str, run: str, sources_hash: str,
          kind: str, items: list[dict], chunks: list[str] | None = None,
          apply_it: bool = True) -> dict:
    path = Path(work) / extraction_name(entry)
    text = render(run, sources_hash, entry, kind, items, chunks)
    if apply_it:
        _atomic_write(path, text)
    return {'path': str(path), 'items': len(items), 'written': apply_it,
            'bytes': len(text.encode('utf-8'))}


# ------------------------------------------------------------------- read

def read(path: Path | str) -> dict:
    path = Path(path)
    text = path.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines()
    header, i = {}, 0
    while i < len(lines) and lines[i].strip():
        key, _, value = lines[i].partition(':')
        if key.strip() in HEADER_KEYS:
            header[key.strip()] = value.strip()
        i += 1

    items, current, body = [], None, []

    def _flush():
        if current is not None:
            current['text'] = '\n'.join(body).strip()
            items.append(current)

    for line in lines[i:]:
        m = ITEM_RE.match(line)
        if m:
            _flush()
            current, body[:] = {'id': m.group('id'), 'tags': []}, []
            continue
        if current is not None and not body:
            t = TAGS_RE.match(line)
            if t:
                current['tags'] = [x.strip() for x in t.group('tags').split(',')
                                   if x.strip()]
                continue
        if current is not None:
            body.append(line)
    _flush()

    malformed = [validate_id(it['id']) for it in items]
    malformed = [m for m in malformed if not m['ok']]
    return {'path': str(path), 'header': header, 'items': items,
            'malformed': malformed}


def read_set(work: Path | str, run: str | None = None,
             sources_hash: str | None = None) -> dict:
    """Every extraction of one run, with the header agreement checked.

    A mismatched set is never silently used. C refuses it for the same reason
    this does: the notes and the extractions would be describing different
    bytes, and every ID comparison between them would be meaningless.
    """
    work = Path(work)
    files = sorted(p for p in work.glob('A_*.md') if p.is_file())
    sets, mismatched, malformed = [], [], []
    runs, hashes = set(), set()
    for p in files:
        data = read(p)
        h = data['header']
        runs.add(h.get('run'))
        hashes.add(h.get('sources_hash'))
        if (run and h.get('run') != run) or \
           (sources_hash and h.get('sources_hash') != sources_hash):
            mismatched.append({'path': str(p), 'run': h.get('run'),
                               'sources_hash': h.get('sources_hash')})
        malformed.extend(data['malformed'])
        sets.append(data)
    consistent = len(runs) <= 1 and len(hashes) <= 1 and not mismatched
    return {'work': str(work), 'files': len(files), 'extractions': sets,
            'run': sorted(x for x in runs if x),
            'sources_hash': sorted(x for x in hashes if x),
            'consistent': consistent, 'mismatched': mismatched,
            'malformed': malformed,
            'ids': [it['id'] for d in sets for it in d['items']]}


# ----------------------------------------------------------------- errata

def _course_level(source_entry: str) -> bool:
    """A source outside the lesson folder reaches every lesson citing it.

    Anything recorded course-relative rather than lesson-relative is course
    level: `Books/...`, `Assignments/...`. `Content/...` and the lesson's own
    `Articles/...` are lesson local (note-invariants §14).
    """
    head = source_entry.split('/', 1)[0].lower()
    return head not in ('content', 'articles')


def errata_for(course: Path | str, lesson_key: str,
               sources: list[str]) -> dict:
    """Active errata reaching this lesson's sources, by name with the code token
    ignored. Missing or empty file is not a warning: most courses have none."""
    path = Path(course) / '.data' / 'source_errata.json'
    if not path.is_file():
        return {'exists': False, 'errata': [], 'inputs': []}
    try:
        data = json.loads(path.read_text(encoding='utf-8') or '{}')
    except json.JSONDecodeError as e:
        return {'exists': True, 'error': f'unreadable: {e}', 'errata': [],
                'inputs': []}

    by_name = {}
    for entry in sources:
        rel = entry.split('#', 1)[0]
        by_name.setdefault(naming.strip_code_token(Path(rel).name), []).append(rel)

    out = []
    for e in data.get('errata', []):
        if e.get('status') not in (None, 'active'):
            continue
        src = (e.get('source') or '')
        key = naming.strip_code_token(Path(src).name)
        if key not in by_name:
            continue
        # Reach follows the source, not the lesson: a lesson-local erratum is
        # only for its own lesson, a course-level one for every lesson citing it.
        if not _course_level(src) and (e.get('lesson') or lesson_key) != lesson_key:
            continue
        row = dict(e)
        row['_targets'] = by_name[key]
        out.append(row)
    return {'exists': True, 'errata': out,
            'inputs': [{'id': e.get('id'), 'right': e.get('right')} for e in out]}


def apply_errata(items: list[dict], errata: list[dict],
                 source_entry: str) -> dict:
    """Replace `wrong` with `right` in the item carrying the erratum's ID.

    Three outcomes and no fourth (note-invariants §14): the text is there and is
    repaired; the text is already `right` and nothing happens because the source
    itself was fixed; neither is present and nothing happens because the source
    changed under the erratum. The third is reported, never forced.
    """
    by_id = {}
    for it in items:
        by_id.setdefault(it['id'], []).append(it)
    applied, already, not_applied = [], [], []
    key = naming.strip_code_token(Path(source_entry.split('#', 1)[0]).name)

    for e in errata:
        if naming.strip_code_token(Path(e.get('source', '')).name) != key:
            continue
        targets = by_id.get(e.get('item'), [])
        wrong, right = e.get('wrong') or '', e.get('right') or ''
        hit = False
        for it in targets:
            if wrong and wrong in it['text']:
                it['text'] = it['text'].replace(wrong, right)
                if 'errata' not in it['tags']:
                    it['tags'] = list(it['tags']) + ['errata']
                applied.append({'id': e.get('id'), 'item': e.get('item')})
                hit = True
            elif right and right in it['text']:
                already.append({'id': e.get('id'), 'item': e.get('item'),
                                'reason': 'the source already carries the right '
                                          'text; nothing applied'})
                hit = True
        if not hit:
            not_applied.append({
                'id': e.get('id'), 'item': e.get('item'),
                'reason': 'neither the wrong nor the right text is in that item'
                          + ('' if targets else ' (no item carries that ID)')
                          + '. The source changed; skill D resolves it.'})
    return {'items': items, 'applied': applied, 'already_correct': already,
            'not_applied': not_applied}


def apply_errata_to_work(work: Path | str, course: Path | str, lesson_key: str,
                         sources: list[str], apply_it: bool = False) -> dict:
    """Run the errata pass over an existing extraction set, in place."""
    found = errata_for(course, lesson_key, sources)
    work = Path(work)
    report = {'errata': len(found['errata']), 'applied': [], 'not_applied': [],
              'already_correct': [], 'files': [], 'inputs': found['inputs'],
              'applied_flag': apply_it}
    if found.get('error'):
        report['error'] = found['error']
        return report
    for entry in sources:
        path = work / extraction_name(entry)
        if not path.is_file():
            continue
        data = read(path)
        res = apply_errata(data['items'], found['errata'], entry)
        report['applied'] += res['applied']
        report['not_applied'] += res['not_applied']
        report['already_correct'] += res['already_correct']
        if res['applied'] and apply_it:
            h = data['header']
            chunks = None
            if h.get('chunks'):
                chunks = [c.strip() for c in h['chunks'].strip('[]').split(',')
                          if c.strip()]
            _atomic_write(path, render(h.get('run', ''), h.get('sources_hash', ''),
                                       h.get('source', entry), h.get('kind', ''),
                                       data['items'], chunks))
            report['files'].append(str(path))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('read'); p.add_argument('--path', required=True)
    p = sub.add_parser('set')
    p.add_argument('--work', required=True)
    p.add_argument('--run'); p.add_argument('--hash')
    p = sub.add_parser('name'); p.add_argument('--entry', required=True)
    p = sub.add_parser('errata')
    p.add_argument('--work', required=True)
    p.add_argument('--course', required=True)
    p.add_argument('--lesson', required=True)
    p.add_argument('--sources', nargs='+', required=True)
    p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)

    if args.cmd == 'read':
        out = read(args.path)
    elif args.cmd == 'set':
        out = read_set(args.work, args.run, args.hash)
    elif args.cmd == 'name':
        out = {'entry': args.entry, 'file': extraction_name(args.entry)}
    else:
        out = apply_errata_to_work(args.work, args.course, args.lesson,
                                   args.sources, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
