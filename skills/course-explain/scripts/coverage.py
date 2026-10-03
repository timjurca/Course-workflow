#!/usr/bin/env python3
"""E's own memory: the coverage index, the rejected list and the depth setting.

Three facts live in `.data/explain_state.json` and nowhere else, and each of
them exists because the alternative fails silently.

**The coverage index** maps every concept an explanation *covers* to the primary
concept whose file *holds* it. Without it, lookup would be a directory listing,
and a directory listing answers the wrong question: a concept explained inside
another concept's file has no file of its own, so listing `Explanations/` would
report it as unexplained and E would rebuild an explanation that already exists
three paragraphs down another page. Concept IDs sit on both sides, never
filenames, which is what makes a course-code rename touch nothing in here.

**The rejected list** is the record of E's own bad answers. It is the one
failure surface no script in this plugin can reach: `verify_calc.py` checks
arithmetic, nothing checks a wrong analogy. Without this list E would be told an
analogy is bad, adapt for the rest of that conversation, and reach for the same
framing three weeks later, because a re-save replaces the body and nothing
survives. It records that **E's output** was poor, never anything about the
student, so C's no-self-assessment wall is untouched.

**`explain_depth`** is the student's standing answer to the assignment-depth
question. A default that was never asked is `concept`, the safer of the two.

Retired-key sweeping lives here too, for both maps, and so does the successor
rule: a retired concept's successor is the surviving concept whose `source_ids`
overlap it most, with the overlap at least half of the smaller set. That is B's
own ID-reuse rule from note-invariants section 6, and D and E are required to
use the same one so that three skills agree on where a retired concept went.

CLI:
    coverage.py show     --course <c>
    coverage.py lookup   --course <c> --concept <id>
    coverage.py record   --course <c> --primary <id> --covers <id> [<id>...] [--apply]
    coverage.py sweep    --course <c> [--apply]
    coverage.py rebuild  --course <c> [--apply]
    coverage.py rejected --course <c> [--concept <id>]
    coverage.py reject   --course <c> --concept <id> --kind analogy --what <t> --why <t> [--apply]
    coverage.py depth    --course <c> [--set concept|analogous] [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
from vault import read_frontmatter                                   # noqa: E402

STATE_REL = Path('.data') / 'explain_state.json'
EXPLANATIONS = 'Explanations'
REJECTION_KINDS = ('analogy', 'framing', 'example', 'emphasis')
DEPTHS = ('concept', 'analogous')

# Everything the state file holds. A key outside this set is either a typo or a
# later version's; it is kept on write rather than dropped, but it is reported.
KNOWN_KEYS = {'applied_renumbers', 'explain_depth', 'depth_set', 'next_finding_id',
              'coverage', 'rejected'}


def default_state() -> dict:
    return {'applied_renumbers': [], 'explain_depth': None, 'depth_set': None,
            'next_finding_id': 1, 'coverage': {}, 'rejected': {}}


def state_path(course: Path | str) -> Path:
    return Path(course) / STATE_REL


def load_state(course: Path | str) -> dict:
    """Read the state, or hand back a usable default.

    A missing or corrupt state file never stops E explaining. It costs the
    coverage index and the rejected list, and section 18 requires E to say the
    rejected list is empty rather than imply it is complete, so the caller is
    told which of the two it got.
    """
    path = state_path(course)
    out = default_state()
    out['_status'] = 'missing'
    out['_path'] = str(path)
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        out['_status'] = 'corrupt'
        out['_error'] = str(exc)
        return out
    if not isinstance(data, dict):
        out['_status'] = 'corrupt'
        out['_error'] = 'top level is not an object'
        return out
    merged = default_state()
    merged.update(data)
    merged['_status'] = 'ok'
    merged['_path'] = str(path)
    merged['_unknown_keys'] = sorted(set(data) - KNOWN_KEYS)
    return merged


def write_state(course: Path | str, state: dict) -> Path:
    """Atomic: a half-written state file would lose the rejected list."""
    path = state_path(course)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in state.items() if not k.startswith('_')}
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    os.replace(tmp, path)
    return path


# ------------------------------------------------------------------ concepts

def load_concepts(course: Path | str) -> dict:
    path = Path(course) / '.data' / 'concepts.json'
    if not path.is_file():
        return {}
    try:
        return (json.loads(path.read_text(encoding='utf-8')) or {}).get('concepts', {})
    except Exception:
        return {}


def source_ids_of(entry: dict) -> set:
    ids = set()
    for sec in entry.get('sections') or []:
        ids.update(sec.get('source_ids') or [])
    return ids


def successor_of(concepts: dict, retired_id: str) -> dict:
    """B's ID-reuse rule, applied backwards to find where a concept went.

    Overlap of at least half the smaller source-ID set, best overlap wins. D and
    E are both required to use this rule rather than invent one, so that a
    retired concept resolves to the same successor in both skills.
    """
    entry = concepts.get(retired_id) or {}
    mine = source_ids_of(entry)
    best, best_score = None, 0.0
    for cid, other in concepts.items():
        if cid == retired_id or other.get('retired'):
            continue
        theirs = source_ids_of(other)
        if not mine or not theirs:
            continue
        overlap = len(mine & theirs)
        smaller = min(len(mine), len(theirs))
        if overlap and overlap >= smaller / 2 and overlap > best_score:
            best, best_score = cid, overlap
    return {'successor': best, 'overlap': best_score,
            'basis': 'source_ids overlap >= half of the smaller set'}


# ------------------------------------------------------------------- the index

def lookup(course: Path | str, concept: str) -> dict:
    """Where an explanation of this concept lives, if one does."""
    state = load_state(course)
    concepts = load_concepts(course)
    cov = state.get('coverage') or {}
    primary = cov.get(concept)
    entry = concepts.get(concept) or {}
    out = {'concept': concept, 'covered': primary is not None,
           'primary': primary, 'own_file': primary == concept,
           'known_concept': concept in concepts,
           'retired': bool(entry.get('retired')),
           'state_status': state.get('_status'),
           'rejected': (state.get('rejected') or {}).get(concept, [])}
    if out['retired']:
        out.update(successor_of(concepts, concept))
    if primary:
        out['file'] = f'{EXPLANATIONS}/<CODE>_{primary}_Explained.md'
    return out


def record(course: Path | str, primary: str, covers: list, apply: bool = False) -> dict:
    """Point every covered concept at the primary, except one with its own file.

    Own file always wins: a concept maps elsewhere only while it has no file of
    its own, and saving its own explanation re-points its entry at itself.
    """
    state = load_state(course)
    cov = dict(state.get('coverage') or {})
    changes, kept = [], []
    targets = [primary] + [c for c in covers if c != primary]
    for cid in targets:
        current = cov.get(cid)
        if cid != primary and current == cid:
            kept.append(cid)                       # it has its own file already
            continue
        if current != primary:
            changes.append({'concept': cid, 'from': current, 'to': primary})
        cov[cid] = primary
    state['coverage'] = cov
    if apply and changes:
        write_state(course, state)
    return {'primary': primary, 'changes': changes, 'kept_own_file': kept,
            'written': bool(apply and changes), 'coverage_size': len(cov)}


def sweep(course: Path | str, apply: bool = False) -> dict:
    """Re-point retired keys at their successor, or drop them and say so.

    Runs on save and on status, for the coverage index and the rejected list
    alike. A retired key left in place makes E offer an explanation of a concept
    the notes no longer have.
    """
    state = load_state(course)
    concepts = load_concepts(course)
    if not concepts:
        return {'swept': [], 'dropped': [], 'written': False,
                'note': 'concepts.json is missing; nothing swept'}
    swept, dropped = [], []
    cov = dict(state.get('coverage') or {})
    rej = dict(state.get('rejected') or {})
    for mapping, label in ((cov, 'coverage'), (rej, 'rejected')):
        for cid in list(mapping):
            entry = concepts.get(cid)
            if entry is None or not entry.get('retired'):
                continue
            succ = successor_of(concepts, cid)['successor']
            value = mapping.pop(cid)
            if succ:
                if label == 'rejected':
                    mapping.setdefault(succ, []).extend(value)
                else:
                    mapping[succ] = value if value != cid else succ
                swept.append({'map': label, 'from': cid, 'to': succ})
            else:
                dropped.append({'map': label, 'concept': cid,
                                'reason': 'retired with no resolvable successor'})
    state['coverage'], state['rejected'] = cov, rej
    if apply and (swept or dropped):
        write_state(course, state)
    return {'swept': swept, 'dropped': dropped,
            'written': bool(apply and (swept or dropped))}


def rebuild(course: Path | str, apply: bool = False) -> dict:
    """Rebuild the coverage index from the saved files' own frontmatter.

    The index is rebuildable because every saved file names its primary concept
    and every concept it covers. The rejected list is **not**: nothing else
    records it, so a lost rejected list is lost, and E says it is empty rather
    than implying it is complete.
    """
    course = Path(course)
    state = load_state(course)
    expl = course / EXPLANATIONS
    cov, files, tombstones = {}, [], []
    if expl.is_dir():
        for p in sorted(expl.glob('*_Explained.md')):
            try:
                fm, _ = read_frontmatter(p)
            except Exception:
                continue
            primary = fm.get('concept')
            if not primary:
                continue
            if fm.get('superseded_by'):
                tombstones.append({'file': p.name, 'concept': primary,
                                   'superseded_by': fm.get('superseded_by')})
                continue
            files.append(p.name)
            for cid in [primary] + list(fm.get('concepts') or []):
                # own file always wins, whatever order the files are read in
                if cov.get(cid) == cid:
                    continue
                cov[cid] = primary if cid != primary else primary
    state['coverage'] = cov
    if apply:
        write_state(course, state)
    return {'rebuilt_from': files, 'tombstones': tombstones, 'coverage': cov,
            'written': apply,
            'rejected_list': 'not rebuildable; it is empty unless it survived',
            'rejected_present': bool(state.get('rejected'))}


# ---------------------------------------------------------- the rejected list

def rejected(course: Path | str, concept: str | None = None) -> dict:
    state = load_state(course)
    rej = state.get('rejected') or {}
    out = {'state_status': state.get('_status'),
           'complete': state.get('_status') == 'ok'}
    if concept:
        out['concept'] = concept
        out['rejections'] = rej.get(concept, [])
    else:
        out['rejections'] = rej
        out['concepts'] = len(rej)
        out['total'] = sum(len(v) for v in rej.values())
    if state.get('_status') != 'ok':
        out['note'] = ('the state file is missing or corrupt, so this list is '
                       'empty rather than complete; say so')
    return out


def reject(course: Path | str, concept: str, kind: str, what: str, why: str,
           apply: bool = False, date: str | None = None) -> dict:
    """Record one rejected framing. Opt-in only, and never inferred.

    A rejection is written on the student's word and on nothing else: not on a
    follow-up question, not on a re-ask, not on a rephrasing request. An
    inferred rejection is a silent write about a judgement the student never
    made, and it would quietly remove a framing that was working.

    This write deliberately does **not** apply A's pending renumber blocks. The
    list is keyed by concept ID, which carries no lesson number, so no renumber
    block can affect it; migrating everything E owns in the middle of a tutoring
    turn, for a one-line note about a bad analogy, would be a disproportionate
    write with nothing to migrate.
    """
    if kind not in REJECTION_KINDS:
        return {'error': f'kind must be one of {", ".join(REJECTION_KINDS)}',
                'written': False}
    state = load_state(course)
    rej = dict(state.get('rejected') or {})
    row = {'date': date or datetime.now().strftime('%Y-%m-%d'),
           'kind': kind, 'what': what, 'why': why}
    rej.setdefault(concept, []).append(row)
    state['rejected'] = rej
    if apply:
        write_state(course, state)
    return {'concept': concept, 'recorded': row, 'written': apply,
            'count_for_concept': len(rej[concept]),
            'renumber': 'deliberately not applied; the list holds no lesson numbers'}


# -------------------------------------------------------------------- depth

def depth(course: Path | str, set_to: str | None = None,
          apply: bool = False) -> dict:
    """Read or set explain_depth. Default before it is answered: concept."""
    state = load_state(course)
    current = state.get('explain_depth')
    out = {'explain_depth': current or 'concept',
           'answered': current is not None, 'set_on': state.get('depth_set'),
           'written': False}
    if set_to is None:
        return out
    if set_to not in DEPTHS:
        out['error'] = f'depth must be one of {", ".join(DEPTHS)}'
        return out
    out['previous'] = current
    out['explain_depth'] = set_to
    out['answered'] = True
    # A switch to analogous resets the loaded scope: context does not unload by
    # itself, so the rule is structural. A switch back needs no reset, because
    # the task index is a negative filter and acquiring it late is harmless.
    out['reset_required'] = (set_to == 'analogous' and current != 'analogous')
    out['task_index_readable'] = (set_to == 'concept')
    if apply:
        state['explain_depth'] = set_to
        state['depth_set'] = datetime.now().strftime('%Y-%m-%d')
        write_state(course, state)
        out['written'] = True
        out['set_on'] = state['depth_set']
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('show', 'lookup', 'record', 'sweep', 'rebuild', 'rejected',
                 'reject', 'depth'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True)
        if name in ('record', 'sweep', 'rebuild', 'reject', 'depth'):
            p.add_argument('--apply', action='store_true')
        if name in ('lookup', 'rejected', 'reject'):
            p.add_argument('--concept', required=(name != 'rejected'))
        if name == 'record':
            p.add_argument('--primary', required=True)
            p.add_argument('--covers', nargs='*', default=[])
        if name == 'reject':
            p.add_argument('--kind', required=True, choices=REJECTION_KINDS)
            p.add_argument('--what', required=True)
            p.add_argument('--why', required=True)
        if name == 'depth':
            p.add_argument('--set', dest='set_to', choices=DEPTHS)
    args = ap.parse_args(argv)

    if args.cmd == 'show':
        st = load_state(args.course)
        out = {'status': st.get('_status'), 'path': st.get('_path'),
               'explain_depth': st.get('explain_depth') or 'concept',
               'depth_answered': st.get('explain_depth') is not None,
               'next_finding_id': st.get('next_finding_id'),
               'applied_renumbers': st.get('applied_renumbers'),
               'coverage': st.get('coverage'),
               'rejected_concepts': sorted((st.get('rejected') or {})),
               'unknown_keys': st.get('_unknown_keys', [])}
    elif args.cmd == 'lookup':
        out = lookup(args.course, args.concept)
    elif args.cmd == 'record':
        out = record(args.course, args.primary, args.covers, args.apply)
    elif args.cmd == 'sweep':
        out = sweep(args.course, args.apply)
    elif args.cmd == 'rebuild':
        out = rebuild(args.course, args.apply)
    elif args.cmd == 'rejected':
        out = rejected(args.course, getattr(args, 'concept', None))
    elif args.cmd == 'reject':
        out = reject(args.course, args.concept, args.kind, args.what, args.why,
                     args.apply)
    else:
        out = depth(args.course, args.set_to, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
