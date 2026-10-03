#!/usr/bin/env python3
"""Resolve wikilinks and heading anchors; rewrite link targets after a rename.

Why this exists: **heading anchors break silently.** Obsidian warns about a
missing file and says nothing about a missing heading, so renaming a section in
lesson 3 quietly invalidates lesson 9's "Connects to" link. Over a semester a
vault rots that way without anyone noticing.

Who does what with the result:
  B   runs it at the end of every run and reports. B repairs exactly one kind,
      in retarget mode: a link *it wrote this run* into a section *it renamed
      this run*, inside this lesson's own folder and the overview. Every other
      break is a report.
  D   repairs a broken *heading anchor* as a logged correction on the link
      target, with the right anchor looked up through the concept ID.
  A   runs it in rewrite mode after any folder rename or code rename.
  E   repairs its own links inside Explanations/, because D never writes there.

A broken *file* link is always a report: it means a missing file, which is A's
or B's problem, not a stale anchor.

CLI:
    check_links.py check --vault <path> [--scope <dir>] [--into <file> ...]
    check_links.py rewrite --vault <path> --map old=new [old=new ...] [--apply]
    check_links.py retarget --vault <path> --note <stem> [--scope <dir>] \
        --map "old heading=new heading" [...] [--apply]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

WIKILINK_RE = re.compile(r'(?P<embed>!?)\[\[(?P<target>[^\]\|#]*)'
                         r'(?:#(?P<anchor>[^\]\|]*))?'
                         r'(?:\|(?P<alias>[^\]]*))?\]\]')
MD_LINK_RE = re.compile(r'!?\[[^\]]*\]\((?P<target>[^)\s]+)(?:\s+"[^"]*")?\)')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.*?)\s*$', re.MULTILINE)

SKIP_DIRS = {'.git', '.obsidian', '.trash'}


def _hidden(parts) -> bool:
    """True for anything under a dot-directory, or a dot-file itself.

    Named dot-dirs were never the whole set. The vault also carries `.work`
    (this run's drafts), `.data` (concepts and ledgers), `.course-plugin` (the
    script bundle) and archived copies under them, all full of links that are
    either stale by design or point at paths that were only ever intermediate.
    Scanning them produced phantom broken anchors from draft and archived
    copies of the very file being written. Any dot-directory is machinery.
    """
    return any(x.startswith('.') for x in parts)


FENCE_RE = re.compile(r'^(?:```|~~~).*?^(?:```|~~~)\s*$', re.MULTILINE | re.DOTALL)
INLINE_CODE_RE = re.compile(r'`[^`\n]*`')


def strip_code(text: str) -> str:
    """Blank out fenced blocks and inline code before scanning for links.

    Notes are full of LaTeX, shell snippets and documentation that mentions link
    syntax literally. A checker that reads those as links reports failures the
    student cannot fix, and a rewriter that edits them corrupts the example.
    Replacing with spaces of the same length keeps every offset intact.
    """
    def blank(m):
        return re.sub(r'[^\n]', ' ', m.group(0))
    return INLINE_CODE_RE.sub(blank, FENCE_RE.sub(blank, text))


def _token_pattern(old: str) -> re.Pattern:
    """Word-boundary guards that survive a token ending in an underscore.

    A course-code token is written `ECON_`, and the character after it is `L`,
    so a naive `(?![A-Za-z0-9])` trailing guard never matches and the rename
    silently rewrites nothing. The guard is therefore applied only on the edges
    that are actually alphanumeric.
    """
    left = r'(?<![A-Za-z0-9_])' if old[:1].isalnum() else ''
    right = r'(?![A-Za-z0-9])' if old[-1:].isalnum() else ''
    return re.compile(left + re.escape(old) + right)


def markdown_files(root: Path, skip_hidden: bool = True):
    for p in root.rglob('*.md'):
        parts = p.relative_to(root).parts
        if skip_hidden and _hidden(parts):
            continue
        yield p


def build_index(vault: Path) -> dict:
    """filename stem -> [paths]. Obsidian resolves a wikilink by stem vault-wide
    when the stem is unique, and writes a path-qualified link when it is not."""
    index: dict[str, list[Path]] = {}
    for p in vault.rglob('*'):
        if not p.is_file():
            continue
        parts = p.relative_to(vault).parts
        if _hidden(parts):
            continue
        index.setdefault(p.stem, []).append(p)
    return index


def headings_of(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return set()
    return {m.group(2).strip() for m in HEADING_RE.finditer(text)}


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _target_keys(t: str) -> list[str]:
    """Index keys a wikilink target could mean, most literal first.

    `Ortt_Matta_Reader.index.md` has stem `Ortt_Matta_Reader.index`, and
    Obsidian resolves `[[Ortt_Matta_Reader.index]]` to it. `Path(t).stem`
    strips the `.index` and looks up `Ortt_Matta_Reader`, which is not a key,
    so every link to a book index was reported broken while Obsidian followed
    it happily. Any name carrying two dots hits this.
    """
    name = Path(t).name
    keys = [name]
    if name.lower().endswith('.md'):
        keys.append(name[:-3])
    stem = Path(name).stem
    if stem not in keys:
        keys.append(stem)
    return [k for k in keys if k]


def _resolve_target(vault: Path, source: Path, target: str, index: dict) -> Path | None:
    if not target:
        return source            # a bare #anchor link points inside its own file
    t = target.strip()
    # A target may repeat the vault's own folder name, as
    # `School/Q1/<course>/Weekly_overview` does when the vault is `School`.
    # Obsidian resolves that; joining it onto the vault root a second time
    # yields `School/School/Q1/...`, which exists nowhere, so the link fell
    # through to a bare-stem lookup, matched one `Weekly_overview` per course
    # and was reported ambiguous. It is neither broken nor ambiguous.
    roots = [t]
    first, _, rest = t.partition('/')
    if rest and first == vault.name:
        roots.append(rest)
    cands = [vault / r for r in roots]
    # `.md` is appended as well as substituted: with_suffix on
    # `Ortt_Matta_Reader.index` yields `Ortt_Matta_Reader.md`, a different file.
    for cand in cands:
        for c in (cand, cand.with_suffix('.md'), Path(str(cand) + '.md')):
            if c.is_file():
                return c
    cand = cands[0]
    rel = (source.parent / t)
    for c in (rel, rel.with_suffix('.md'), Path(str(rel) + '.md')):
        if c.is_file():
            return c
    for key in _target_keys(t):
        hits = index.get(key, [])
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None          # ambiguous: Obsidian would have written a path
    return None


def check(vault: Path | str, scope: Path | str | None = None,
          into: list[str] | None = None) -> dict:
    vault = Path(vault)
    index = build_index(vault)
    # A vault-relative scope is the natural thing to pass and used to resolve
    # against the process's working directory, which on a device shell is
    # somewhere else entirely. rglob then yielded nothing, `checked` stayed 0,
    # and the result said `clean: true`. A gate that passes because it looked at
    # nothing is the most dangerous shape a gate can take, so the path is
    # resolved against the vault and an empty scan is a failure (below).
    scope_root = vault
    if scope:
        scope_root = Path(scope)
        if not scope_root.is_absolute():
            scope_root = vault / scope_root
    into_set = {str(Path(x)) for x in (into or [])}

    broken_files, broken_anchors, ambiguous = [], [], []
    checked = 0

    sources = list(markdown_files(scope_root))
    if into_set:
        # inbound: every note in the vault that points into a file this run rewrote
        sources = list(set(sources) | set(markdown_files(vault)))

    for src in sources:
        try:
            text = src.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        for m in WIKILINK_RE.finditer(strip_code(text)):
            # Inside a markdown table cell a literal pipe is escaped as `\|`,
            # which is exactly how the term index writes its links. The regex
            # stops at the pipe but keeps the backslash, so every such anchor
            # came back as "Definitions\" and every term reported broken.
            target = (m.group('target') or '').strip().rstrip('\\').strip()
            anchor = (m.group('anchor') or '').strip().rstrip('\\').strip()
            checked += 1
            resolved = _resolve_target(vault, src, target, index)
            rel_src = str(src.relative_to(vault))
            if resolved is None:
                # `--into` deliberately sweeps the whole vault to find links
                # pointing *into* what this run wrote. That sweep must not turn
                # other courses' pre-existing links into this run's findings: an
                # unresolved link points at nothing, so it cannot be an inbound
                # link to this run's files, and a link outside the scope is
                # somebody else's to fix.
                if into_set and not _under(src, scope_root):
                    continue
                hits = []
                if target:
                    for key in _target_keys(target):
                        hits = index.get(key, [])
                        if hits:
                            break
                row = {'in': rel_src, 'link': m.group(0), 'target': target}
                (ambiguous if len(hits) > 1 else broken_files).append(row)
                continue
            if into_set and str(resolved.relative_to(vault)) not in into_set \
                    and str(src.relative_to(vault)) not in into_set:
                continue
            if anchor and resolved.suffix == '.md':
                if anchor not in headings_of(resolved):
                    broken_anchors.append({
                        'in': rel_src, 'link': m.group(0),
                        'target': str(resolved.relative_to(vault)), 'anchor': anchor})
    # Scanning nothing is a failure, not a pass. `scanned` is reported so the
    # caller can see what the check actually covered rather than inferring it
    # from a link count that is zero for two very different reasons: a scope
    # that matched no files, and a scope whose files contain no links.
    empty = None
    if not sources:
        empty = (f'no markdown files under {scope_root}; nothing was checked, '
                 'so this is not a pass')
    return {'checked': checked, 'scanned': len(sources),
            'scope': str(scope_root), 'empty_scan': empty,
            'broken_file_links': broken_files,
            'broken_heading_anchors': broken_anchors,
            'ambiguous_targets': ambiguous,
            'clean': (not broken_files and not broken_anchors
                      and not ambiguous and empty is None)}


def rewrite(vault: Path | str, mapping: dict, apply: bool = False) -> dict:
    """Mechanical token replacement in link targets only.

    Narrow by design: an exact old-code token or an exact L<NN>/T<NN> lesson
    token, in a link target or a TOC marker pair. Never prose, never an alias,
    never a heading. This is the only operation in the plugin that edits inside
    a file another skill owns, and it is always followed by a re-check.
    """
    vault = Path(vault)
    changes = []
    for src in markdown_files(vault):
        try:
            text = src.read_text(encoding='utf-8')
        except OSError:
            continue
        original = text
        file_hits = 0
        protected = strip_code(text)

        def _wiki(m):
            nonlocal file_hits
            # Only rewrite a link the code-stripped view also sees as a link.
            if protected[m.start():m.end()].strip() != m.group(0).strip():
                return m.group(0)
            target = m.group('target') or ''
            new_target = target
            for old, new in mapping.items():
                new_target = _token_pattern(old).sub(new, new_target)
            if new_target == target:
                return m.group(0)
            file_hits += 1
            anchor = f'#{m.group("anchor")}' if m.group('anchor') else ''
            alias = f'|{m.group("alias")}' if m.group('alias') is not None else ''
            return f'{m.group("embed")}[[{new_target}{anchor}{alias}]]'

        text = WIKILINK_RE.sub(_wiki, text)

        def _toc(m):
            nonlocal file_hits
            token = m.group(1)
            new = token
            for old, repl in mapping.items():
                new = _token_pattern(old).sub(repl, new)
            if new == token:
                return m.group(0)
            file_hits += 1
            return f'<!-- toc:{new}:{m.group(2)} -->'

        text = re.sub(r'<!--\s*toc:([^:]+):(start|end)\s*-->', _toc, text)

        if file_hits:
            changes.append({'file': str(src.relative_to(vault)), 'replacements': file_hits})
            if apply and text != original:
                src.write_text(text, encoding='utf-8')
    return {'applied': apply, 'files_changed': len(changes),
            'replacements': sum(c['replacements'] for c in changes),
            'changes': changes}



def retarget(vault: Path | str, note: str, mapping: dict,
             scope: str | None = None, apply: bool = False) -> dict:
    """Move links from an old heading anchor to a new one, in one file's links.

    `rewrite` deliberately never touches an anchor, because a heading rename
    elsewhere in the vault is D's to repair through the concept ID. This is the
    narrower case D cannot see in time: B renames a section **and writes links
    into it in the same run**, so the broken anchor is B's own, created and
    detectable inside a single pass. Repairing it there costs one call;
    leaving it costs a reported break plus a later D run.

    Narrow by the same design as `rewrite`: only a wikilink whose target
    resolves to `note` (or an empty target inside `note` itself), only when the
    anchor matches an old heading exactly, never prose, never an alias, never a
    heading. `scope` bounds which files may be edited, and B always passes one:
    this lesson's folder plus the overview. Every other file stays a report.
    """
    vault = Path(vault)
    root = (vault / scope) if scope else vault
    stem = Path(note).stem
    changes = []
    stale_aliases = []
    for src in markdown_files(root):
        try:
            text = src.read_text(encoding='utf-8')
        except OSError:
            continue
        original = text
        hits = 0
        protected = strip_code(text)

        def _sub(m):
            nonlocal hits
            if protected[m.start():m.end()].strip() != m.group(0).strip():
                return m.group(0)
            anchor = m.group('anchor')
            if anchor is None or anchor.strip() not in mapping:
                return m.group(0)
            target = (m.group('target') or '').strip()
            # An empty target is a link inside the same file.
            if target:
                if Path(target).stem != stem:
                    return m.group(0)
            elif src.stem != stem:
                return m.group(0)
            hits += 1
            alias_text = m.group('alias')
            if alias_text is not None and alias_text.strip() == anchor.strip():
                # The anchor is repaired; the visible text still reads as the
                # old heading. That text is prose, and this function does not
                # edit prose, so it is handed back as a report for the writer.
                stale_aliases.append({'file': str(src.relative_to(vault)),
                                      'alias': alias_text.strip(),
                                      'should_read': mapping[anchor.strip()]})
            alias = f'|{alias_text}' if alias_text is not None else ''
            return (f'{m.group("embed")}[[{m.group("target") or ""}'
                    f'#{mapping[anchor.strip()]}{alias}]]')

        text = WIKILINK_RE.sub(_sub, text)
        if hits:
            changes.append({'file': str(src.relative_to(vault)),
                            'replacements': hits})
            if apply and text != original:
                src.write_text(text, encoding='utf-8')
    return {'applied': apply, 'note': stem, 'scope': scope or '.',
            'files_changed': len(changes),
            'replacements': sum(c['replacements'] for c in changes),
            'changes': changes, 'stale_aliases': stale_aliases}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('check')
    p.add_argument('--vault', required=True)
    p.add_argument('--scope'); p.add_argument('--into', nargs='*')
    p = sub.add_parser('rewrite')
    p.add_argument('--vault', required=True)
    p.add_argument('--map', nargs='+', required=True, help='old=new')
    p.add_argument('--apply', action='store_true')
    p = sub.add_parser('retarget')
    p.add_argument('--vault', required=True)
    p.add_argument('--note', required=True,
                   help='stem of the file whose headings were renamed')
    p.add_argument('--scope', help='folder the edit is allowed to touch')
    p.add_argument('--map', nargs='+', required=True,
                   help='"old heading=new heading"')
    p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if args.cmd == 'check':
        out = check(args.vault, args.scope, args.into)
    elif args.cmd == 'retarget':
        mapping = dict(x.split('=', 1) for x in args.map)
        out = retarget(args.vault, args.note, mapping, args.scope, args.apply)
    else:
        mapping = dict(x.split('=', 1) for x in args.map)
        out = rewrite(args.vault, mapping, args.apply)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
