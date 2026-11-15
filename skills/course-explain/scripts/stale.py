#!/usr/bin/env python3
"""Detect that a saved explanation has fallen behind. Never repair it silently.

A saved explanation is a snapshot of material that keeps moving: B re-runs the
notes, D lands a correction, a concept is retired, a source ID disappears. The
file itself says nothing about any of that, so a student opening it in June gets
a confident page built on March's material with no sign on screen.

The rule here is **detect and offer, never repair and never serve quietly**. A
stale explanation is still often the right answer; what is not acceptable is
serving it as current. Regeneration is the student's call, every time, because
regenerating throws away prose they may have been relying on.

The one thing E does repair by itself is **its own broken heading anchors**.
D repairs anchors everywhere else in the vault, and D never writes into
`Explanations/`; if E did not repair its own, nobody would, and the link into
the notes would rot where it is least visible.

Five checks, and each maps to something that actually changed:

    notes_run      B re-ran the notes this file was built from
    dead ids       a cited source ID is gone from concepts.json
    corrections    a correction or erratum has landed on a cited ID
    retired        the primary concept was retired
    anchors        a heading this file links to has been renamed

CLI:
    stale.py check --course <c> --concept <id>
    stale.py all   --course <c>
    stale.py links --course <c> [--apply]
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
import coverage as cov                                               # noqa: E402
import ladder                                                        # noqa: E402
import scope                                                         # noqa: E402
from vault import course_identity, parse_frontmatter                 # noqa: E402
from runstamp import norm_run                                        # noqa: E402

ANCHOR_LINK_RE = re.compile(r'\[\[(?P<target>[^\]\|#]+)#(?P<anchor>[^\]\|]+)'
                            r'(?:\|(?P<alias>[^\]]+))?\]\]')


def _saved_files(course: Path) -> list:
    expl = course / 'Explanations'
    return sorted(expl.glob('*_Explained.md')) if expl.is_dir() else []


def check(course: Path | str, concept: str) -> dict:
    course = Path(course)
    code = course_identity(course).get('code')
    path = course / 'Explanations' / f'{code}_{concept}_Explained.md'
    out = {'concept': concept, 'file': str(path.name), 'exists': path.is_file(),
           'stale': False, 'reasons': [], 'offer': None}
    if not path.is_file():
        index = cov.lookup(course, concept)
        out['covered_by'] = index.get('primary')
        out['note'] = ('no file of its own; the coverage index is the truth, not a '
                       'directory listing')
        return out
    fm, body = parse_frontmatter(path.read_text(encoding='utf-8', errors='replace'))
    out['tombstone'] = bool(fm.get('superseded_by'))
    if out['tombstone']:
        out['superseded_by'] = fm['superseded_by']
        out['note'] = 'a tombstone is never regenerated and is listed separately'
        return out

    concepts = cov.load_concepts(course)
    entry = concepts.get(concept) or {}
    out['lessons'] = fm.get('lessons') or []
    out['notes_run'] = norm_run(fm.get('notes_run')) or None

    # 1. the notes moved on
    for key in out['lessons']:
        state = ladder.notes_state(course, key)
        current = norm_run(state.get('run'))
        if current and out['notes_run'] and current != out['notes_run']:
            out['reasons'].append({
                'code': 'notes_rerun', 'lesson': key,
                'message': (f'the notes for {key} were re-run '
                            f'({out["notes_run"]} -> {current})'),
                'say': 'your saved explanation predates the current notes'})

    # 2. a cited source ID no longer exists
    live = cov.source_ids_of(entry)
    dead = [i for i in (fm.get('source_ids') or []) if live and i not in live]
    if dead:
        out['reasons'].append({'code': 'dead_source_ids', 'ids': dead,
                               'message': ('cited source IDs that are no longer in '
                                           'this concept: ' + ', '.join(dead))})

    # 3. a correction or an erratum landed on a cited ID
    cited = set(fm.get('source_ids') or [])
    for key in out['lessons']:
        corr = scope.corrections(course, key)
        for row in corr.get('entries', []):
            if row.get('concept') == concept and not row.get('already_in_the_notes'):
                what = ('needs replay after the notes were re-run'
                        if row.get('needs_replay') else row['status'])
                out['reasons'].append({
                    'code': 'correction_landed', 'lesson': key, 'id': row['id'],
                    'status': row['status'], 'needs_replay': row.get('needs_replay'),
                    'message': (f'correction {row["id"]} on this concept {what}: '
                                'the notes this explanation quotes may no longer '
                                'carry the corrected text')})
        err = scope.errata(course, key)
        for e in err.get('relevant', []):
            if e.get('item') in cited:
                out['reasons'].append({
                    'code': 'erratum_landed', 'lesson': key, 'id': e.get('id'),
                    'item': e.get('item'),
                    'message': ('a correction has landed on material this '
                                'explanation used (' + str(e.get('item')) + ')')})

    # 4. retired
    if entry.get('retired'):
        succ = cov.successor_of(concepts, concept)['successor']
        out['reasons'].append({'code': 'retired', 'successor': succ,
                               'message': ('the primary concept is retired; '
                                           'regenerate against ' + str(succ)
                                           + ' and leave a tombstone')})

    # 5. broken anchors into the notes
    out['broken_anchors'] = broken_anchors(course, path)
    if out['broken_anchors']:
        out['reasons'].append({
            'code': 'broken_anchor', 'links': out['broken_anchors'],
            'message': ('a heading this file links to has been renamed; E repairs '
                        'its own links, D never writes here')})

    out['stale'] = bool(out['reasons'])
    if out['stale']:
        out['offer'] = ('say what changed and offer to regenerate. Never serve it '
                        'as current, and never regenerate without being asked.')
    return out


def _headings(path: Path) -> set:
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return set()
    return {m.group(2).strip() for m in re.finditer(r'^(#{1,6})\s+(.*?)\s*$', text,
                                                    re.MULTILINE)}


def broken_anchors(course: Path | str, path: Path) -> list:
    """Anchors in one saved file that no longer exist in their target."""
    course = Path(course)
    text = path.read_text(encoding='utf-8', errors='replace')
    index = {}
    for md in course.rglob('*.md'):
        if any(p.startswith('.') for p in md.relative_to(course).parts[:-1]):
            continue
        index.setdefault(md.stem, []).append(md)
    out = []
    for m in ANCHOR_LINK_RE.finditer(text):
        target = m.group('target').strip()
        anchor = m.group('anchor').strip()
        hits = index.get(target) or []
        if len(hits) != 1:
            out.append({'link': m.group(0), 'problem': 'file link unresolved',
                        'repairable_by_E': False,
                        'note': 'a missing file belongs to course-setup or course-notes'})
            continue
        if anchor not in _headings(hits[0]):
            out.append({'link': m.group(0), 'target': hits[0].name,
                        'anchor': anchor, 'problem': 'anchor missing',
                        'repairable_by_E': True})
    return out


def repair_links(course: Path | str, apply: bool = False) -> dict:
    """Re-point E's own anchors by concept lookup, not by guessing a heading.

    The concept ID is the stable identity; the heading text is not. Looking the
    anchor up through `concepts.json` is what makes this a repair rather than a
    rename that happens to match.
    """
    course = Path(course)
    concepts = cov.load_concepts(course)
    changes = []
    for path in _saved_files(course):
        fm, _ = parse_frontmatter(path.read_text(encoding='utf-8', errors='replace'))
        primary = fm.get('concept')
        entry = concepts.get(primary) or {}
        headings = {s.get('lesson'): s.get('heading')
                    for s in entry.get('sections') or []}
        text = path.read_text(encoding='utf-8', errors='replace')
        new = text
        for row in broken_anchors(course, path):
            if not row.get('repairable_by_E'):
                continue
            lesson = None
            m = re.search(r'_([LT]\d{2})_Final_notes', row.get('target', ''))
            if m:
                lesson = m.group(1)
            want = headings.get(lesson)
            if not want:
                continue
            fixed = row['link'].replace('#' + row['anchor'], '#' + want)
            new = new.replace(row['link'], fixed)
            changes.append({'file': path.name, 'from': row['link'], 'to': fixed,
                            'via': f'concepts.json heading for {primary} in {lesson}'})
        if apply and new != text:
            tmp = path.with_name(path.name + '.tmp')
            tmp.write_text(new, encoding='utf-8')
            os.replace(tmp, path)
    return {'changes': changes, 'written': apply,
            'rule': 'E repairs its own links; D never writes into Explanations/'}


def all_saved(course: Path | str) -> dict:
    """The `status` report's data: saved, stale, tombstones, archive size."""
    course = Path(course)
    state = cov.load_state(course)
    rows, tombstones = [], []
    for path in _saved_files(course):
        fm, _ = parse_frontmatter(path.read_text(encoding='utf-8', errors='replace'))
        concept = fm.get('concept')
        if not concept:
            continue
        if fm.get('superseded_by'):
            tombstones.append({'concept': concept, 'file': path.name,
                               'superseded_by': fm['superseded_by']})
            continue
        res = check(course, concept)
        rows.append({'concept': concept, 'file': path.name,
                     'stale': res['stale'],
                     'reasons': [r['code'] for r in res.get('reasons', [])]})
    hist = course / 'Explanations' / '.history'
    archives = sorted(hist.glob('*.md')) if hist.is_dir() else []
    rejected = state.get('rejected') or {}
    return {
        'saved': len(rows), 'current': sum(1 for r in rows if not r['stale']),
        'stale': [r for r in rows if r['stale']],
        'covers': len(state.get('coverage') or {}),
        'tombstones': tombstones,
        'rejected': {'concepts': len(rejected),
                     'total': sum(len(v) for v in rejected.values()),
                     'complete': state.get('_status') == 'ok'},
        'archive': {'versions': len(archives),
                    'mb': round(sum(p.stat().st_size for p in archives) / 1048576, 2)},
        'explain_depth': state.get('explain_depth') or 'concept',
        'depth_set': state.get('depth_set'),
        'rows': rows,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('check'); p.add_argument('--course', required=True)
    p.add_argument('--concept', required=True)
    p = sub.add_parser('all'); p.add_argument('--course', required=True)
    p = sub.add_parser('links'); p.add_argument('--course', required=True)
    p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'check':
        out = check(args.course, args.concept)
    elif args.cmd == 'all':
        out = all_saved(args.course)
    else:
        out = repair_links(args.course, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
