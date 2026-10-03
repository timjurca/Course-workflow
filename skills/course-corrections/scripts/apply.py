#!/usr/bin/env python3
"""Write a confirmed correction, and prove afterwards that nothing else moved.

This is the module that touches the student's notes, so it is built around one
claim it has to be able to make honestly: **only the declared edit set changed.**

The declared edit set is the anchor span, plus — for a gap fill only — the
`## Uncovered material` line being retired, the `coverage:` value and the
warning callout (spec sections 6.3 and 13). Everything else in the file is
required to come back byte-identical, and the check runs against what is
actually on disk after the write, not against what the code believes it wrote.

Ordering, and it is the whole design:

  1. resolve every anchor and refuse the whole run if any of them is unsafe
  2. archive each file, once per run, named after the run's **first** id
  3. build the new text by cutting at the resolved spans
  4. write atomically: `.tmp` beside, then `os.replace`
  5. re-read from disk and verify the edit set, the concept comments, the
     protected blocks and every other frontmatter key
  6. a failed verification restores the archive and reports the fix as dropped

Step 6 is why step 2 is unconditional. A fix is never "repaired" by the model
after a failed check (D-18): a correction that half-landed is a wrong note with
a confident tone, which is the failure this whole skill exists to prevent.

Refusals, all before any write, and any one of them aborts the run:
  * the span touches `## My additions` or `## My notes`
  * the target is an overview, a `Table_of_contents.md`, anything in `.work/`,
    or anything under `Explanations/` (that folder is E's; D never writes there)
  * the anchor is missing, or present several times and no occurrence was chosen
  * two spans in one file overlap

`undo` lives here too, because it is the archive read back: the same pre-images,
the same atomic write. Its refusals are the interesting part and they all say the
same thing — something has happened since, so restoring would put the vault into
a state it was never in. Spec section 22 lists no `undo.py`; this is that action.

CLI:
    apply.py check --course <path> --plan <plan.json>
    apply.py apply --course <path> --plan <plan.json> [--apply]
    apply.py undo  --course <path> [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import anchor                                                     # noqa: E402
import log as dlog                                                # noqa: E402

FRONTMATTER_RE = re.compile(r'\A---\r?\n(.*?)\r?\n---\r?\n', re.DOTALL)
COVERAGE_RE = re.compile(r'^(?P<lead>coverage:\s*)(?P<value>.*?)\s*$', re.MULTILINE)

FORBIDDEN_PARTS = ('.work', 'Explanations')
FORBIDDEN_NAMES = ('Table_of_contents.md',)
OVERVIEW_RE = re.compile(r'_[LT]\d{2}_Overview\.md$')


def _stamp() -> str:
    return datetime.now().strftime('%Y-%m-%dT%H-%M-%S')


def target_problem(course: Path, rel: str) -> str | None:
    """Spec section 6.4 and G20, checked on the path rather than trusted to the plan."""
    p = Path(rel)
    if p.is_absolute():
        return 'the plan must name a course-relative path'
    parts = p.parts
    for bad in FORBIDDEN_PARTS:
        if bad in parts:
            return (f'{bad}/ is not D\'s to write in'
                    + (' — course-explain repairs its own files' if bad == 'Explanations'
                       else ''))
    if p.name in FORBIDDEN_NAMES:
        return ('the table of contents is rebuilt from the headings; correct the '
                'heading instead')
    if OVERVIEW_RE.search(p.name):
        return 'an overview error is fixed by re-running course-notes, not by D'
    if not (course / p).is_file():
        return 'file does not exist'
    return None


def archive_path(course: Path, rel: str, first_id: str) -> Path:
    """Lesson notes to the lesson's `.work/history/`, everything else to `.data/history/`.

    Adding files to B's `.work/history/` is the sanctioned exception in spec
    section 17: D adds versions there and changes nothing else in `.work/`.
    """
    p = Path(rel)
    stem, suffix = Path(p.name).stem, Path(p.name).suffix
    name = f'{stem}_{_stamp()}_pre-{first_id}{suffix}'
    if p.parts and p.parts[0] in ('Lessons', 'Tutorials') and len(p.parts) >= 2:
        return course / p.parts[0] / p.parts[1] / '.work' / 'history' / name
    return course / '.data' / 'history' / name


# --------------------------------------------------------------------------
# resolving the declared edit set


def _line_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Grow a span to the whole line when it already covers one.

    A `delete` that leaves an empty line behind has changed the shape of the
    file in a way the student did not ask for, so the newline is part of the
    declared set rather than collateral.
    """
    ls = text.rfind('\n', 0, start) + 1
    le = text.find('\n', end)
    le = len(text) if le < 0 else le
    if text[ls:start].strip() or text[end:le].strip():
        return start, end
    return ls, min(le + 1, len(text))


def resolve(course: Path | str, plan: dict) -> dict:
    """Turn every edit into (file, span, replacement), or into a refusal."""
    course = Path(course)
    problems, per_file = [], {}

    for n, edit in enumerate(plan.get('edits') or [], 1):
        rel = edit.get('file')
        eid = edit.get('id') or f'edit {n}'
        if not rel:
            problems.append({'id': eid, 'reason': 'edit names no file'})
            continue
        bad = target_problem(course, rel)
        if bad:
            problems.append({'id': eid, 'reason': bad, 'file': rel})
            continue
        path = course / rel
        text = per_file.setdefault(rel, {'text': path.read_text(encoding='utf-8'),
                                         'spans': [], 'ids': []})['text']

        op = edit.get('operation')
        before = edit.get('before') or ''
        after = edit.get('after') or ''
        hit = anchor.find(text, before, edit.get('concept'), edit.get('heading'))
        if not hit['found']:
            problems.append({'id': eid, 'reason': hit.get('reason') or
                             'anchor text not found; nothing is written and nothing '
                             'is logged', 'file': rel, 'before': before})
            continue
        occurrences = hit['occurrences']
        chosen = edit.get('occurrence')
        if len(occurrences) > 1 and chosen in (None, ''):
            problems.append({'id': eid, 'file': rel,
                             'reason': f'the anchor appears {len(occurrences)} times '
                                       'in this section; say which one, or "all"',
                             'occurrences': occurrences})
            continue
        if chosen == 'all':
            picked = occurrences
        elif len(occurrences) > 1:
            try:
                picked = [occurrences[int(chosen) - 1]]
            except (ValueError, IndexError):
                problems.append({'id': eid, 'file': rel,
                                 'reason': f'occurrence {chosen!r} is out of range'})
                continue
        else:
            picked = occurrences

        for occ in picked:
            start, end = occ['start'], occ['end']
            prot = anchor.protected_hit(text, start, end)
            if prot['protected']:
                problems.append({'id': eid, 'file': rel,
                                 'reason': f'"{prot["heading"]}" is your own writing; '
                                           'D never corrects it'})
                continue
            if op == 'replace':
                span = (start, end, after)
            elif op == 'insert_after':
                span = (end, end, ('\n' if '\n' in text[end:end + 2] else ' ') + after)
            elif op == 'delete':
                ls, le = _line_span(text, start, end)
                span = (ls, le, '')
            else:
                problems.append({'id': eid, 'reason': f'unknown operation {op!r}'})
                continue
            per_file[rel]['spans'].append({'start': span[0], 'end': span[1],
                                           'replacement': span[2], 'id': eid,
                                           'operation': op})
            per_file[rel]['ids'].append(eid)

        gap = edit.get('gap')
        if gap:
            problems.extend(_gap_spans(rel, per_file[rel], gap, eid))

    for rel, blob in per_file.items():
        spans = sorted(blob['spans'], key=lambda s: s['start'])
        for a, b in zip(spans, spans[1:]):
            if a['end'] > b['start']:
                problems.append({'file': rel, 'id': f'{a["id"]} and {b["id"]}',
                                 'reason': 'two corrections touch the same text; '
                                           'apply them one at a time'})
        blob['spans'] = spans

    return {'ok': not problems, 'problems': problems,
            'files': {rel: {'spans': b['spans'], 'ids': sorted(set(b['ids']))}
                      for rel, b in per_file.items()}}


def _gap_spans(rel: str, blob: dict, gap: dict, eid: str) -> list[dict]:
    """The three extras a filled gap is allowed to touch, and nothing more."""
    text = blob['text']
    problems = []
    line = gap.get('uncovered_line')
    if line:
        hit = anchor.find(text, line, heading='Uncovered material')
        if not hit['found']:
            problems.append({'id': eid, 'file': rel,
                             'reason': 'the uncovered-material line to retire is not '
                                       'under "## Uncovered material"'})
        else:
            occ = hit['occurrences'][0]
            ls, le = _line_span(text, occ['start'], occ['end'])
            blob['spans'].append({'start': ls, 'end': le, 'replacement': '',
                                  'id': eid, 'operation': 'gap:uncovered'})
    new_coverage = gap.get('coverage')
    if new_coverage:
        fm = FRONTMATTER_RE.match(text)
        m = COVERAGE_RE.search(text, 0, fm.end() if fm else len(text))
        if not m:
            problems.append({'id': eid, 'file': rel,
                             'reason': 'no coverage: key in the frontmatter to update'})
        else:
            quote = '"' if m.group('value').startswith('"') else ''
            blob['spans'].append({'start': m.start('value'), 'end': m.end('value'),
                                  'replacement': f'{quote}{new_coverage}{quote}',
                                  'id': eid, 'operation': 'gap:coverage'})
    callout = gap.get('callout')
    if callout:
        hit = anchor.find(text, callout)
        if not hit['found']:
            problems.append({'id': eid, 'file': rel,
                             'reason': 'the coverage warning callout is not in the file'})
        else:
            occ = hit['occurrences'][0]
            ls, le = _line_span(text, occ['start'], occ['end'])
            blob['spans'].append({'start': ls, 'end': le, 'replacement': '',
                                  'id': eid, 'operation': 'gap:callout'})
    return problems


# --------------------------------------------------------------------------
# writing and verifying


def _splice(text: str, spans: list[dict]) -> str:
    out, at = [], 0
    for s in spans:
        out.append(text[at:s['start']])
        out.append(s['replacement'])
        at = s['end']
    out.append(text[at:])
    return ''.join(out)


def _outside(text: str, spans: list[dict]) -> list[str]:
    out, at = [], 0
    for s in spans:
        out.append(text[at:s['start']])
        at = s['end']
    out.append(text[at:])
    return out


def _concept_comments(text: str) -> list[str]:
    return anchor.CONCEPT_RE.findall(text)


def _protected_blocks(text: str) -> dict:
    return {s['heading']: text[s['start']:s['end']]
            for s in anchor.sections(text) if s['protected']}


def _frontmatter_lines(text: str) -> list[str]:
    m = FRONTMATTER_RE.match(text)
    return m.group(1).splitlines() if m else []


def verify(before_text: str, after_text: str, spans: list[dict],
           allow_coverage: bool) -> dict:
    """Independent re-derivation: the bytes outside the declared spans must match.

    `after_text` is read back from disk, so this compares what the filesystem
    holds with what the declared edit set allows — not with what the code
    believes it produced.
    """
    failures = []
    expected = _splice(before_text, spans)
    if after_text != expected:
        at = next((i for i, (a, b) in enumerate(zip(after_text, expected)) if a != b),
                  min(len(after_text), len(expected)))
        failures.append({'check': 'edit set', 'offset': at,
                         'reason': 'the file on disk differs from the declared edit '
                                   'set; the write did not land as planned',
                         'on_disk': after_text[max(0, at - 40):at + 40],
                         'declared': expected[max(0, at - 40):at + 40]})

    if _concept_comments(before_text) != _concept_comments(after_text):
        failures.append({'check': 'concepts',
                         'reason': 'the concept comments changed; every other skill '
                                   'locates this material by them'})
    if _protected_blocks(before_text) != _protected_blocks(after_text):
        failures.append({'check': 'protected',
                         'reason': 'a protected block changed'})

    old_fm, new_fm = _frontmatter_lines(before_text), _frontmatter_lines(after_text)
    if len(old_fm) != len(new_fm):
        failures.append({'check': 'frontmatter', 'reason': 'frontmatter lines added or removed'})
    else:
        for a, b in zip(old_fm, new_fm):
            if a == b:
                continue
            if allow_coverage and a.lstrip().startswith('coverage:'):
                continue
            failures.append({'check': 'frontmatter',
                             'reason': f'frontmatter changed: {a.strip()!r} -> {b.strip()!r}'})
    return {'ok': not failures, 'failures': failures}


def run(course: Path | str, plan: dict, apply: bool = False) -> dict:
    course = Path(course)
    resolved = resolve(course, plan)
    if not resolved['ok']:
        return {'applied': False, 'aborted': True, **resolved}

    ids = sorted({s['id'] for b in resolved['files'].values() for s in b['spans']})
    first_id = plan.get('run_id') or (ids[0] if ids else 'c-0000')

    written, archived, dropped = [], [], []
    for rel, blob in resolved['files'].items():
        path = course / rel
        original = path.read_text(encoding='utf-8')
        spans = blob['spans']
        allow_coverage = any(s['operation'] == 'gap:coverage' for s in spans)
        new_text = _splice(original, spans)

        arc = archive_path(course, rel, first_id)
        if apply:
            arc.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, arc)
        archived.append({'file': rel, 'archive': str(arc.relative_to(course)),
                         'name': arc.name})

        if not apply:
            check = verify(original, new_text, spans, allow_coverage)
            (written if check['ok'] else dropped).append(
                {'file': rel, 'ids': blob['ids'], **check})
            continue

        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(new_text, encoding='utf-8')
        os.replace(tmp, path)

        on_disk = path.read_text(encoding='utf-8')
        check = verify(original, on_disk, spans, allow_coverage)
        missing = [s['id'] for s in spans
                   if s['replacement'].strip()
                   and not anchor.find(on_disk, s['replacement'])['found']]
        if missing:
            check['ok'] = False
            check['failures'].append({'check': 'after text',
                                      'reason': f'the corrected text is not in the '
                                                f'file for {", ".join(sorted(set(missing)))}'})
        if check['ok']:
            written.append({'file': rel, 'ids': blob['ids'], **check})
        else:
            shutil.copy2(arc, path)
            dropped.append({'file': rel, 'ids': blob['ids'],
                            'restored_from': str(arc.relative_to(course)), **check})

    if apply and written:
        _record_run(course, plan, first_id, written, archived)

    return {'applied': apply, 'aborted': False, 'run_id': first_id,
            'written': written, 'dropped': dropped, 'archived': archived,
            'note': 'a dropped fix is never repaired by the model; it is reported '
                    'and counted' if dropped else None}


def _record_run(course: Path, plan: dict, first_id: str, written: list,
                archived: list) -> None:
    """What `undo` needs, and nothing more.

    Paths are stored as a `lesson` plus a path **relative to the lesson folder**,
    never as `Lessons/03_2026-03-12/...`. A renumber renames that folder, and a
    stored absolute-ish path would then point at nothing while looking valid.
    The field names are the ones `migrate.py`'s field mapper knows.
    """
    state = dlog.read_state(course)
    arcs = {a['file']: a for a in archived}
    rows = []
    for w in written:
        rel = Path(w['file'])
        arc = arcs.get(w['file'], {})
        if rel.parts and rel.parts[0] in ('Lessons', 'Tutorials') and len(rel.parts) > 2:
            lesson = plan.get('lesson') or _lesson_token(rel.parts[1], rel.parts[0])
            file_rel = str(Path(*rel.parts[2:]))
        else:
            lesson, file_rel = None, str(rel)
        rows.append({'lesson': lesson, 'file_rel': file_rel,
                     'archive_name': Path(arc.get('name', '')).name,
                     'corrections': w['ids']})
    state['last_run'] = {
        'timestamp': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'run_id': first_id,
        'lessons': sorted({r['lesson'] for r in rows if r['lesson']}),
        'corrections': sorted({i for w in written for i in w['ids']}),
        'errata': list(plan.get('errata') or []),
        'files': rows}
    dlog.write_state(course, state, apply=True)


def _lesson_token(folder_name: str, parent: str) -> str | None:
    import naming
    parsed = naming.parse_lesson_folder(folder_name)
    if not parsed:
        return None
    return ('L' if parent == 'Lessons' else 'T') + parsed['num']


def undo(course: Path | str, apply: bool = False) -> dict:
    """Reverse the most recent D run from the archive, or refuse and say why.

    Scope is the whole run, all of its corrections together. Earlier runs are
    not reachable: a single earlier correction is withdrawn with `correct`
    (`withdraw c-0003`), which is a normal, logged, verified change.

    Every refusal has the same shape — something downstream now depends on the
    corrected text, so restoring the pre-image would leave a note, a question
    bank or an extraction referring to a version that is gone.
    """
    import fingerprint
    import gate as dgate
    course = Path(course)
    state = dlog.read_state(course)
    last = state.get('last_run')
    if not last:
        return {'can_undo': False,
                'reason': 'no corrections run is recorded. corrections.json may have '
                          'been rebuilt, which does not recover the last run.'}

    refusals, restores = [], []
    for row in last['files']:
        lesson = row.get('lesson')
        if lesson:
            folder = dgate.lesson_dir(course, lesson)
            if folder is None:
                refusals.append(f'the folder for {lesson} is gone')
                continue
            target = folder / row['file_rel']
            archive = folder / '.work' / 'history' / row['archive_name']
        else:
            target = course / row['file_rel']
            archive = course / '.data' / 'history' / row['archive_name']
        if not archive.is_file():
            refusals.append(
                f'the pre-image {row["archive_name"]} is gone (an archive cleanup '
                'removed it). Reverse the correction with `correct` instead.')
            continue
        if not target.is_file():
            refusals.append(f'{row["file_rel"]} is no longer where it was')
            continue
        restores.append({'lesson': lesson, 'target': str(target),
                         'archive': str(archive), 'corrections': row['corrections']})

    for lesson in last.get('lessons') or []:
        notes = dgate.notes_path(course, lesson)
        if notes is None:
            continue
        text = notes.read_text(encoding='utf-8')
        check = fingerprint.check(course, lesson, notes)
        if check['state'] == 'regenerated':
            refusals.append(f'course-notes has re-run {lesson} since; replay, do not '
                            'undo')
        elif check['state'] == 'hand_edit':
            refusals.append(f'the notes for {lesson} were edited by hand since; run '
                            'scan first, then correct')
        revision = course / 'Exams' / 'Revision_questions'
        if revision.is_dir():
            for q in revision.glob(f'*_{lesson}_Revision.md'):
                if q.stat().st_mtime > _epoch(last['timestamp']):
                    refusals.append(f'course-revision wrote {q.name} after this run; '
                                    'its questions were built on the corrected notes')

    if refusals:
        return {'can_undo': False, 'run_id': last['run_id'],
                'refusals': sorted(set(refusals)),
                'instead': 'reverse the correction with `correct` (withdraw c-NNNN), '
                           'which is a normal, logged, verified change'}

    if apply:
        for r in restores:
            tmp = Path(r['target']).with_name(Path(r['target']).name + '.tmp')
            shutil.copy2(r['archive'], tmp)
            os.replace(tmp, r['target'])
        for lesson in last.get('lessons') or []:
            folder = dgate.lesson_dir(course, lesson)
            log_path = folder / 'notes_corrections.md' if folder else None
            if log_path and log_path.is_file():
                for cid in last['corrections']:
                    dlog.set_fields(log_path, cid,
                                    {'status': 'withdrawn',
                                     'reason': f'reversed by undo of run '
                                               f'{last["run_id"]}'}, apply=True)
            if folder:
                notes = dgate.notes_path(course, lesson)
                if notes:
                    fingerprint.record(course, lesson, notes, apply=True)
        if last.get('errata'):
            import errata as derrata
            for eid in last['errata']:
                derrata.withdraw(course, eid, apply=True)
        state['last_run'] = None
        dlog.write_state(course, state, apply=True)

    return {'can_undo': True, 'run_id': last['run_id'], 'restored': restores,
            'corrections_withdrawn': last['corrections'],
            'errata_withdrawn': last.get('errata') or [],
            'written': apply,
            'caveat': 'a withdrawn erratum returns the extraction to its previous '
                      'state only when course-notes runs again'
                      if last.get('errata') else None}


def _epoch(stamp: str) -> float:
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(stamp, fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('check', 'apply'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True); p.add_argument('--plan', required=True)
        if name == 'apply':
            p.add_argument('--apply', action='store_true')
    p = sub.add_parser('undo')
    p.add_argument('--course', required=True); p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'undo':
        out = undo(args.course, args.apply)
    else:
        plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
        out = resolve(args.course, plan) if args.cmd == 'check' \
            else run(args.course, plan, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
