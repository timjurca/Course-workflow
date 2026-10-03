#!/usr/bin/env python3
"""Write a saved explanation: archive, check for a hand edit, replace, protect.

There is exactly **one write mode: full replace**. A save writes one file and
the state, and nothing else, so an interrupted run cannot leave two files
disagreeing about what covers what. Partial edits to a second file are what
turn a crash into a corruption.

Four things this module refuses to do, and each refusal is the interesting part:

**It never creates `Explanations/`.** A creates every visible folder, on demand,
at E's first save. If the folder is missing the save stops and names the A
request - and explaining continues regardless, because a missing folder is a
reason not to write a file, not a reason not to answer a question.

**It never invents a concept ID.** Every saved file is named after a concept
that exists in `concepts.json`. That is what keeps rung-4 material out of the
folder as a file of its own: background attaches to a course concept or it stays
in the conversation, and there are never orphan IDs in `Explanations/`.

**It never overwrites `## My notes`.** The block is read out of the old file and
put back verbatim, and created empty when absent.

**It never replaces a hand-edited file silently.** Nothing else in the plugin
writes here, so the last thing E wrote is a reliable baseline and no content
fingerprint is needed, unlike D's: a plain hash in the frontmatter is enough.
When it does not match, the student edited the file, and the difference shown is
between what is on disk now and what E is about to write - which is exactly what
they are about to lose.

A save applies A's outstanding renumber blocks first, across everything E owns,
because writing a new file next to records that still say `L03` would leave the
folder internally inconsistent at the one moment E is holding it open.

CLI:
    save.py plan      --course <c> --concept <id> --body <file> [--covers ...]
    save.py apply     --course <c> --concept <id> --body <file> [--covers ...]
                      [--confirm-hand-edit] [--meta <json>]
    save.py tombstone --course <c> --concept <id> --successor <id> [--apply]
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import coverage as cov                                               # noqa: E402
import fields                                                        # noqa: E402
import markers                                                       # noqa: E402
from vault import (course_identity, dump_frontmatter,                # noqa: E402
                   parse_frontmatter)

PROTECTED = '## My notes'
PROTECTED_COMMENT = '<!-- protected, never overwritten -->'
H2_RE = re.compile(r'^##\s+(.+?)\s*$', re.MULTILINE)

# Frontmatter order, so two saves of the same file produce the same header and a
# diff shows content rather than a reshuffled block. Keys not listed keep their
# own order, after these.
FM_ORDER = ['course', 'concept', 'concepts', 'title', 'lessons', 'language',
            'explain_depth', 'notes_run', 'source_ids', 'external', 'tiers',
            'verified', 'superseded_by', 'body_sha', 'generated', 'generator']


def ordered(fm: dict) -> dict:
    out = {k: fm[k] for k in FM_ORDER if k in fm}
    out.update({k: v for k, v in fm.items() if k not in out})
    return out


def explanations_dir(course: Path | str) -> Path:
    return Path(course) / 'Explanations'


def target(course: Path | str, code: str, concept: str) -> Path:
    return explanations_dir(course) / f'{code}_{concept}_Explained.md'


def body_sha(body: str) -> str:
    """Hash of the body with trailing whitespace normalised.

    Whitespace, list re-wrapping and table re-padding are noise: Obsidian
    re-pads a file on save and that is not a hand edit.
    """
    norm = '\n'.join(l.rstrip() for l in (body or '').strip().splitlines())
    norm = re.sub(r'\n{3,}', '\n\n', norm)
    return hashlib.sha256(norm.encode('utf-8')).hexdigest()[:16]


def split_protected(body: str) -> tuple:
    """(everything before `## My notes`, the protected block's own content)."""
    marks = list(H2_RE.finditer(body))
    for i, m in enumerate(marks):
        if m.group(1).strip() != 'My notes':
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        return body[:m.start()].rstrip(), body[m.end():end].strip()
    return body.rstrip(), ''


def _assemble(new_body: str, protected: str) -> str:
    """The new body, with the student's block put back verbatim underneath."""
    stripped, _ = split_protected(new_body)
    keep = protected.strip()
    if PROTECTED_COMMENT not in keep:
        keep = (PROTECTED_COMMENT + '\n' + keep).strip() if keep else PROTECTED_COMMENT
    return f'{stripped.rstrip()}\n\n{PROTECTED}\n{keep}\n'


def _diff(old: str, new: str) -> list:
    """Unified diff, whitespace noise filtered out."""
    def norm(t):
        return [l.rstrip() for l in t.strip().splitlines() if l.strip()]
    return list(difflib.unified_diff(norm(old), norm(new), 'on disk now',
                                     'what I would write', lineterm='', n=1))[:80]


def plan(course: Path | str, concept: str, body_file: str | None = None,
         covers: list | None = None) -> dict:
    course = Path(course)
    ident = course_identity(course)
    code = ident.get('code')
    concepts = cov.load_concepts(course)
    out = {'concept': concept, 'code': code, 'covers': covers or [],
           'blockers': [], 'warnings': []}

    if not code:
        out['blockers'].append({'code': 'no_course_code',
                                'message': 'Weekly_overview.md carries no code:'})
    if concept not in concepts:
        out['blockers'].append({
            'code': 'unknown_concept',
            'message': ('this concept is not in concepts.json. A filename needs a '
                        'concept ID and E never invents one: attach the material to '
                        'an existing concept, or leave it in the conversation.')})
    elif concepts[concept].get('retired'):
        succ = cov.successor_of(concepts, concept)['successor']
        out['warnings'].append({
            'code': 'retired_concept',
            'message': ('the primary concept is retired; write to the successor '
                        f'({succ}) and leave a tombstone here'),
            'successor': succ})
    expl = explanations_dir(course)
    if not expl.is_dir():
        out['blockers'].append({
            'code': 'explanations_missing',
            'message': ('Explanations/ does not exist. E never creates a visible '
                        'folder: ask course-setup to create it. Explaining is '
                        'unaffected; only the save stops.')})

    path = target(course, code or 'CODE', concept)
    out['path'] = str(path.relative_to(course)) if code else None
    out['exists'] = path.is_file()
    out['pending_renumbers'] = fields.pending(course)['pending']

    new_body = Path(body_file).read_text(encoding='utf-8') if body_file else ''
    if path.is_file():
        fm, old = parse_frontmatter(path.read_text(encoding='utf-8', errors='replace'))
        old_visible, protected = split_protected(old)
        recorded = fm.get('body_sha')
        current = body_sha(old_visible)
        out['hand_edited'] = bool(recorded and recorded != current)
        out['baseline'] = 'frontmatter body_sha' if recorded else 'none recorded'
        out['protected_block_kept'] = bool(protected)
        if out['hand_edited']:
            out['diff'] = _diff(old_visible, new_body)
            out['ask'] = ('this file has been edited by hand since I wrote it. The '
                          'diff above is what a replace would change. Replace, or '
                          'leave it?')
        out['archive'] = (f'Explanations/.history/{path.stem}_'
                          f'{datetime.now().strftime("%Y-%m-%dT%H-%M")}.md')
        out['is_tombstone'] = bool(fm.get('superseded_by'))
        if out['is_tombstone']:
            out['blockers'].append({'code': 'tombstone',
                                    'message': 'a tombstone is never regenerated'})
    else:
        out['hand_edited'] = False
        out['archive'] = None

    if body_file:
        tmp = Path(body_file)
        check = markers.check(tmp)
        out['markers'] = {'ok': check['ok'], 'tiers': check['tiers'],
                          'problems': check['problems'],
                          'unmarked_blocks': check['unmarked_blocks']}
        for p in check['problems']:
            if p['code'] in ('banner_missing', 'unknown_marker', 'bad_tier3_ref',
                             'unresolved_external'):
                out['blockers'].append(p)
    out['ok'] = not out['blockers']
    out['index_changes'] = cov.record(course, concept, covers or [], apply=False)
    return out


def apply(course: Path | str, concept: str, body_file: str, covers: list | None = None,
          confirm_hand_edit: bool = False, meta: dict | None = None) -> dict:
    course = Path(course)
    pre = plan(course, concept, body_file, covers)
    if not pre['ok']:
        return {'written': False, 'blockers': pre['blockers'], 'plan': pre}
    if pre.get('hand_edited') and not confirm_hand_edit:
        return {'written': False, 'hand_edited': True, 'diff': pre.get('diff'),
                'ask': pre['ask'], 'plan': pre}

    # Renumber blocks first: a new file written beside records that still say the
    # old lesson number leaves the folder internally inconsistent.
    migration = fields.migrate(course, apply=True)

    ident = course_identity(course)
    code = ident['code']
    path = target(course, code, concept)
    new_body = Path(body_file).read_text(encoding='utf-8')
    protected = ''
    archived = None
    previous_fm = {}
    if path.is_file():
        old_text = path.read_text(encoding='utf-8', errors='replace')
        previous_fm, old_body = parse_frontmatter(old_text)
        previous_fm = {k: v for k, v in (previous_fm or {}).items()
                       if k not in ('body_sha', 'generated', 'superseded_by')}
        _, protected = split_protected(old_body)
        hist = explanations_dir(course) / '.history'
        hist.mkdir(parents=True, exist_ok=True)     # E's one private folder
        stamp = datetime.now().strftime('%Y-%m-%dT%H-%M')
        archive = hist / f'{path.stem}_{stamp}.md'
        archive.write_text(old_text, encoding='utf-8')
        archived = str(archive.relative_to(course))

    fm_in, body_in = parse_frontmatter(new_body)
    body = _assemble(body_in or new_body, protected)
    visible, _ = split_protected(body)

    # A re-save starts from the file's existing header, not from an empty one.
    # `lessons`, `notes_run` and `source_ids` are exactly what staleness is
    # computed from, and a re-save that quietly dropped them would leave a file
    # that can never be detected as stale again - the failure would be silence.
    fm = dict(previous_fm)
    fm.update(fm_in)
    fm.update(meta or {})
    fm.setdefault('course', ident.get('course'))
    fm['concept'] = concept
    fm['concepts'] = sorted({concept, *(covers or []), *(fm.get('concepts') or [])})
    fm['generator'] = 'course-explain v1'
    fm['generated'] = datetime.now().strftime('%Y-%m-%dT%H:%M')
    fm['body_sha'] = body_sha(visible)
    fm.pop('superseded_by', None)

    text = '---\n' + dump_frontmatter(ordered(fm)) + '\n---\n\n' + body.lstrip('\n')
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)

    index = cov.record(course, concept, covers or [], apply=True)
    swept = cov.sweep(course, apply=True)
    return {'written': True, 'file': str(path.relative_to(course)),
            'archived': archived, 'protected_kept': bool(protected),
            'body_sha': fm['body_sha'], 'index': index, 'swept': swept,
            'renumbers_applied': migration.get('pending'),
            'say': ('name the file that was written, and which concepts it now '
                    'covers')}


def tombstone(course: Path | str, concept: str, successor: str,
              apply_it: bool = False) -> dict:
    """Leave the retired concept's file as a pointer, `## My notes` intact.

    Links keep resolving, the student's own block survives, the full text is in
    the archive and nothing is deleted. A tombstone is never regenerated.
    """
    course = Path(course)
    ident = course_identity(course)
    code = ident.get('code')
    path = target(course, code or 'CODE', concept)
    out = {'concept': concept, 'successor': successor,
           'file': str(path.relative_to(course)) if code else None,
           'exists': path.is_file(), 'written': False}
    if not path.is_file():
        out['note'] = 'nothing to tombstone: no file for this concept'
        return out
    old_text = path.read_text(encoding='utf-8', errors='replace')
    fm, old_body = parse_frontmatter(old_text)
    _, protected = split_protected(old_body)
    title = fm.get('title') or concept
    body = (markers.BANNER + '\n'
            f'# {title}\n\n'
            'This concept was retired in the notes. The current explanation lives '
            f'at [[{code}_{successor}_Explained|{successor}]].\n\n'
            'The full previous text is archived in `Explanations/.history/`.\n'
            'A tombstone is never regenerated.\n')
    # The tombstone is the retired concept's file, whatever the old header said:
    # a copied or repaired file must not leave the pointer naming its source.
    fm['concept'] = concept
    fm['concepts'] = [concept]
    fm['title'] = title
    fm['superseded_by'] = successor
    fm['generated'] = datetime.now().strftime('%Y-%m-%dT%H:%M')
    fm['generator'] = 'course-explain v1'
    fm.pop('body_sha', None)
    text = ('---\n' + dump_frontmatter(ordered(fm)) + '\n---\n\n'
            + _assemble(body, protected))
    out['preview'] = text[:400]
    if apply_it:
        hist = explanations_dir(course) / '.history'
        hist.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y-%m-%dT%H-%M')
        (hist / f'{path.stem}_{stamp}.md').write_text(old_text, encoding='utf-8')
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(text, encoding='utf-8')
        os.replace(tmp, path)
        state = cov.load_state(course)
        index = dict(state.get('coverage') or {})
        for key, value in list(index.items()):
            if value == concept:
                index[key] = successor
        index[concept] = successor
        state['coverage'] = index
        cov.write_state(course, state)
        out['written'] = True
        out['archived'] = f'Explanations/.history/{path.stem}_{stamp}.md'
        out['index_repointed'] = True
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('plan', 'apply'):
        p = sub.add_parser(name)
        p.add_argument('--course', required=True); p.add_argument('--concept', required=True)
        p.add_argument('--body', required=(name == 'apply'))
        p.add_argument('--covers', nargs='*', default=[])
        if name == 'apply':
            p.add_argument('--confirm-hand-edit', dest='confirm', action='store_true')
            p.add_argument('--meta', help='extra frontmatter as JSON')
    p = sub.add_parser('tombstone')
    p.add_argument('--course', required=True); p.add_argument('--concept', required=True)
    p.add_argument('--successor', required=True); p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'plan':
        out = plan(args.course, args.concept, args.body, args.covers)
    elif args.cmd == 'apply':
        out = apply(args.course, args.concept, args.body, args.covers, args.confirm,
                    json.loads(args.meta) if args.meta else None)
    else:
        out = tombstone(args.course, args.concept, args.successor, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
