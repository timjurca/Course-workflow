#!/usr/bin/env python3
"""Tell a hand edit from B's rewrite, and from D's own last write.

The notes sit in the student's vault, so the student edits them. B's next run
discards such an edit without a word. D can only offer to rescue it if D can
**see** it, and seeing it needs a baseline.

The baseline is a fingerprint, not an archive (D-28, spec section 12). The
newest archive is the version from *before* the last write, so diffing against
it reports B's whole rewrite, or D's own corrections, as hand edits — which
trains the student to ignore the report. Instead D records, per lesson, the
notes' `run` plus a hash of the body, and the pair answers the question exactly:

    run unchanged, hash differs   a hand edit
    run changed                   B rewrote the file; replay's case, not scan's
    run changed, an unlogged edit was recorded earlier   the edit is gone, warn
    no fingerprint                first D run here; "no baseline", nothing to say

The hash normalises the same things C's `notes_hash` normalises, for the same
reason: A rewrites link targets mechanically during a code rename or a renumber,
and a plugin that calls its own bookkeeping a hand edit is a plugin nobody
believes. `## My additions` and `## My notes` are excluded because they are the
student's and change freely.

Known blind spot (spec section 12, open item 8): an edit made after a B run and
before D next runs cannot be told from B's own text, because D never saw that
`run`. Replay keeps it small by writing only inside its anchor.

CLI:
    fingerprint.py hash   --notes <file>
    fingerprint.py check  --course <path> --lesson L03 --notes <file>
    fingerprint.py record --course <path> --lesson L03 --notes <file> [--edit-pending] [--apply]
    fingerprint.py diff   --notes <file> --against <file>
    fingerprint.py archives --lesson-dir <path> --notes <file>
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import log as dlog                                               # noqa: E402
from runstamp import norm_run                                      # noqa: E402
from anchor import normalise, sections                           # noqa: E402

WIKILINK_RE = re.compile(r'\[\[(?P<target>[^\]\|#]*)'
                         r'(?P<rest>(?:#[^\]\|]*)?(?:\|[^\]]*)?)\]\]')
CODE_TOKEN_RE = re.compile(r'^[A-Z0-9]{2,8}_')
LESSON_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9])([LT])\d{2}(?![A-Za-z0-9])')
ISO_RE = re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}[:\-]?\d{2}(?:[:\-]?\d{2})?)')


def _normalise_link_targets(text: str) -> str:
    """Placeholders for the two tokens A rewrites mechanically."""
    def sub(m):
        target = CODE_TOKEN_RE.sub('<code>_', m.group('target'))
        target = LESSON_TOKEN_RE.sub(r'\1<nn>', target)
        return '[[' + target + m.group('rest') + ']]'
    return WIKILINK_RE.sub(sub, text)


def body_for_hash(notes: str) -> str:
    """The comparable body: protected blocks out, link tokens placeheld, space flat."""
    cuts = [(s['start'], s['end']) for s in sections(notes) if s['protected']]
    kept, at = [], 0
    for start, end in sorted(cuts):
        kept.append(notes[at:start])
        at = end
    kept.append(notes[at:])
    text = _normalise_link_targets(''.join(kept))
    return normalise(text)[0].strip()


def notes_hash(notes: str) -> str:
    return hashlib.sha256(body_for_hash(notes).encode('utf-8')).hexdigest()


def notes_run(notes: str) -> str | None:
    m = re.search(r'^run:\s*(.+?)\s*$', notes, re.MULTILINE)
    return norm_run(m.group(1)) if m else None


def _entry(state: dict, lesson: str) -> dict | None:
    for row in state.get('fingerprints') or []:
        if row.get('lesson') == lesson:
            return row
    return None


def check(course: Path | str, lesson: str, notes_path: Path | str) -> dict:
    notes = Path(notes_path).read_text(encoding='utf-8')
    state = dlog.read_state(course)
    recorded = _entry(state, lesson)
    now = {'run': notes_run(notes), 'hash': notes_hash(notes)}
    if recorded is None:
        return {'state': 'no_baseline', 'lesson': lesson, 'now': now,
                'hand_edit': False,
                'message': 'first corrections run on this lesson: no baseline, '
                           'nothing to compare'}
    if norm_run(recorded.get('run')) == norm_run(now['run']):
        if recorded.get('hash') == now['hash']:
            return {'state': 'unchanged', 'lesson': lesson, 'now': now,
                    'recorded': recorded, 'hand_edit': False}
        return {'state': 'hand_edit', 'lesson': lesson, 'now': now,
                'recorded': recorded, 'hand_edit': True,
                'message': 'the notes changed while the run did not: this is your '
                           'own edit, not a regeneration'}
    if recorded.get('edit_pending'):
        return {'state': 'edit_lost', 'lesson': lesson, 'now': now,
                'recorded': recorded, 'hand_edit': False,
                'message': 'a hand edit was recorded here and never logged, and the '
                           'notes have since been regenerated: the edit is gone from '
                           'the notes and survives only in the archive'}
    return {'state': 'regenerated', 'lesson': lesson, 'now': now,
            'recorded': recorded, 'hand_edit': False,
            'message': 'B rewrote this file; that is replay\'s case, not scan\'s'}


def record(course: Path | str, lesson: str, notes_path: Path | str,
           edit_pending: bool = False, apply: bool = False) -> dict:
    """Written after each of D's own writes, and at the end of any read-only run.

    Recording after a read-only run is what makes the *next* scan meaningful: it
    pins "the notes as D last saw them", so anything later is the student's.
    """
    notes = Path(notes_path).read_text(encoding='utf-8')
    state = dlog.read_state(course)
    rows = [r for r in (state.get('fingerprints') or [])
            if r.get('lesson') != lesson]
    rows.append({'lesson': lesson, 'run': notes_run(notes),
                 'hash': notes_hash(notes), 'edit_pending': bool(edit_pending)})
    state['fingerprints'] = sorted(rows, key=lambda r: str(r.get('lesson')))
    dlog.write_state(course, state, apply)
    return {'lesson': lesson, 'recorded': rows[-1], 'written': apply}


def archives(lesson_dir: Path | str, notes_path: Path | str) -> dict:
    """Every archived version of this notes file, newest first.

    Both B's `<name>_<ISO>.md` and D's `<name>_<ISO>_pre-c-<id>.md` live in
    `.work/history/`. The code token is ignored when matching the stem, so a
    course-code rename does not hide the history.
    """
    from naming import strip_code_token                          # noqa: E402
    hist = Path(lesson_dir) / '.work' / 'history'
    stem = strip_code_token(Path(notes_path).stem)
    out = []
    if hist.is_dir():
        for p in hist.iterdir():
            if not p.is_file() or p.suffix != '.md':
                continue
            if not strip_code_token(p.stem).startswith(stem):
                continue
            m = ISO_RE.search(p.name)
            out.append({'path': str(p), 'name': p.name,
                        'stamp': m.group(1) if m else None,
                        'mtime': p.stat().st_mtime,
                        'pre': p.stem.split('_pre-')[1] if '_pre-' in p.stem else None})
    out.sort(key=lambda r: (r['stamp'] or '', r['mtime']), reverse=True)
    return {'history': str(hist), 'exists': hist.is_dir(), 'versions': out}


def _blocks(text: str) -> list[str]:
    """Paragraph units, whitespace-flattened, so a re-wrap or a re-pad is not a change."""
    kept = []
    for raw in re.split(r'\n\s*\n', text):
        flat = normalise(raw)[0].strip()
        if flat:
            kept.append(flat)
    return kept


def diff(notes_path: Path | str, against: Path | str) -> dict:
    """Paragraph-level difference with the cosmetic noise filtered out.

    Whitespace, list re-wrapping and table re-padding all disappear in the
    flattening, so what is left is a real change of words (spec section 12).
    """
    new = Path(notes_path).read_text(encoding='utf-8')
    old = Path(against).read_text(encoding='utf-8')
    a, b = _blocks(body_for_hash(old)), _blocks(body_for_hash(new))
    changes = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == 'equal':
            continue
        changes.append({'kind': tag, 'was': a[i1:i2], 'now': b[j1:j2]})
    return {'against': str(against), 'notes': str(notes_path),
            'changes': changes, 'identical': not changes}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('hash'); p.add_argument('--notes', required=True)
    for name in ('check', 'record'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True); p.add_argument('--lesson', required=True)
        p.add_argument('--notes', required=True)
        if name == 'record':
            p.add_argument('--edit-pending', action='store_true')
            p.add_argument('--apply', action='store_true')
    p = sub.add_parser('diff')
    p.add_argument('--notes', required=True); p.add_argument('--against', required=True)
    p = sub.add_parser('archives')
    p.add_argument('--lesson-dir', required=True); p.add_argument('--notes', required=True)
    args = ap.parse_args(argv)

    if args.cmd == 'hash':
        notes = Path(args.notes).read_text(encoding='utf-8')
        out = {'run': notes_run(notes), 'hash': notes_hash(notes)}
    elif args.cmd == 'check':
        out = check(args.course, args.lesson, args.notes)
    elif args.cmd == 'record':
        out = record(args.course, args.lesson, args.notes, args.edit_pending, args.apply)
    elif args.cmd == 'diff':
        out = diff(args.notes, args.against)
    else:
        out = archives(args.lesson_dir, args.notes)

    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
