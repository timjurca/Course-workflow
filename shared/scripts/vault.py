#!/usr/bin/env python3
"""Locate the vault, the config and the course; read and write frontmatter.

One resolution ladder for all five skills (folder-structure.md section 11). Two
skills resolving the same request differently is not a tolerable outcome, and A
is the skill that moves files.

CLI:
    vault.py find --start <path>
    vault.py config --vault <path>
    vault.py resolve --vault <path> [--hint <text>] [--cwd <path>]
    vault.py kind --path <course path>
    vault.py frontmatter --path <file>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

CONFIG_NAME = '_config.md'
OVERVIEW_NAME = 'Weekly_overview.md'

FM_RE = re.compile(r'\A---\r?\n(.*?)\r?\n---\r?\n?', re.DOTALL)


class VaultError(RuntimeError):
    pass


# --------------------------------------------------------------------------- frontmatter

def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (raw frontmatter, body). Raw is '' when there is none."""
    m = FM_RE.match(text)
    if not m:
        return '', text
    return m.group(1), text[m.end():]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    raw, body = split_frontmatter(text)
    if not raw:
        return {}, body
    if yaml is None:
        raise VaultError('PyYAML is required to read frontmatter')
    data = yaml.safe_load(raw)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise VaultError('frontmatter is not a mapping')
    return data, body


def read_frontmatter(path: Path) -> tuple[dict, str]:
    return parse_frontmatter(Path(path).read_text(encoding='utf-8'))


def dump_frontmatter(data: dict) -> str:
    if yaml is None:
        raise VaultError('PyYAML is required to write frontmatter')
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True,
                          default_flow_style=False).rstrip('\n')


def write_frontmatter(path: Path, data: dict, body: str) -> None:
    """Atomic: write beside, then replace. A half-written config is unrecoverable."""
    path = Path(path)
    text = '---\n' + dump_frontmatter(data) + '\n---\n' + body.lstrip('\n')
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


def update_frontmatter(path: Path, changes: dict) -> dict:
    data, body = read_frontmatter(path)
    data.update(changes)
    write_frontmatter(path, data, body)
    return data


# --------------------------------------------------------------------------- vault

def find_vault(start: Path | str) -> Path | None:
    """Walk up from `start` looking for _config.md. Returns None if not found."""
    p = Path(start).expanduser().resolve()
    if p.is_file():
        p = p.parent
    for candidate in [p, *p.parents]:
        if (candidate / CONFIG_NAME).is_file():
            return candidate
    return None


def default_config() -> dict:
    return {
        'courses_root': '',
        'default_notes_language': 'auto',
        'active_courses': [],
        'archived_courses': [],
        'course_codes': {},
        'scaffolded_by': 'course-setup v1',
    }


def read_config(vault: Path | str) -> dict:
    cfg_path = Path(vault) / CONFIG_NAME
    if not cfg_path.is_file():
        raise VaultError(f'no {CONFIG_NAME} at {vault}')
    data, _ = read_frontmatter(cfg_path)
    merged = default_config()
    merged.update(data)
    return merged


def write_config(vault: Path | str, data: dict) -> None:
    cfg_path = Path(vault) / CONFIG_NAME
    body = ''
    if cfg_path.is_file():
        _, body = read_frontmatter(cfg_path)
    if not body.strip():
        body = ('\n# Vault configuration\n\nMaintained by the course-setup skill. '
                'Edit by asking it, not by hand.\n')
    write_frontmatter(cfg_path, data, body)


# --------------------------------------------------------------------------- courses

def course_kind(path: Path | str) -> str:
    """conforming | content-no-overview | empty | missing"""
    p = Path(path)
    if not p.exists():
        return 'missing'
    overview = p / OVERVIEW_NAME
    if overview.is_file():
        try:
            fm, _ = read_frontmatter(overview)
        except Exception:
            fm = {}
        if fm.get('code'):
            return 'conforming'
        return 'content-no-overview'
    visible = [c for c in p.iterdir() if not c.name.startswith('.')]
    return 'empty' if not visible else 'content-no-overview'


def course_identity(path: Path | str) -> dict:
    """code and display name of a course folder, from its overview frontmatter."""
    p = Path(path)
    overview = p / OVERVIEW_NAME
    out = {'path': str(p), 'folder': p.name, 'code': None, 'course': None,
           'notes_language': None, 'expects': [], 'expects_declined': []}
    if overview.is_file():
        try:
            fm, _ = read_frontmatter(overview)
        except Exception:
            fm = {}
        out['code'] = fm.get('code')
        out['course'] = fm.get('course')
        out['notes_language'] = fm.get('notes_language')
        out['expects'] = fm.get('expects') or []
        out['expects_declined'] = fm.get('expects_declined') or []
    return out


def _norm(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (text or '').lower())


def resolve_course(vault: Path | str, hint: str | None = None,
                   cwd: Path | str | None = None) -> dict:
    """The ladder in folder-structure.md section 11.

    Returns {'status': ..., 'path': ..., 'candidates': [...], 'step': ...}.
    status is one of: resolved, ambiguous, none.
    Never picks between two candidates; that is the caller's cue to ask.
    """
    vault = Path(vault)

    # 1. explicit path
    if hint:
        cand = Path(hint).expanduser()
        if not cand.is_absolute():
            cand = vault / hint
        if cand.exists() and cand.is_dir():
            return {'status': 'resolved', 'path': str(cand), 'step': 'explicit path',
                    'candidates': []}

    # 2. current folder, when the session is rooted in a single course
    if cwd:
        p = Path(cwd).expanduser().resolve()
        for candidate in [p, *p.parents]:
            if (candidate / OVERVIEW_NAME).is_file():
                return {'status': 'resolved', 'path': str(candidate),
                        'step': 'current folder', 'candidates': []}
            if candidate == vault:
                break

    # 3. active_courses
    cfg = read_config(vault)
    actives = [vault / rel for rel in cfg.get('active_courses', [])]
    actives = [a for a in actives if a.exists()]
    if not hint:
        if len(actives) == 1:
            return {'status': 'resolved', 'path': str(actives[0]),
                    'step': 'only active course', 'candidates': []}
        return {'status': 'none', 'path': None, 'step': 'no hint',
                'candidates': [str(a) for a in actives]}

    h = _norm(hint)
    by_folder = [a for a in actives if h and h in _norm(a.name)]
    if len(by_folder) == 1:
        return {'status': 'resolved', 'path': str(by_folder[0]),
                'step': 'folder name', 'candidates': []}
    if len(by_folder) > 1:
        return {'status': 'ambiguous', 'path': None, 'step': 'folder name',
                'candidates': [str(a) for a in by_folder]}

    by_display = []
    for a in actives:
        ident = course_identity(a)
        if h and (h in _norm(ident['course'] or '') or h == _norm(ident['code'] or '')):
            by_display.append(a)
    if len(by_display) == 1:
        return {'status': 'resolved', 'path': str(by_display[0]),
                'step': 'course display name', 'candidates': []}
    if len(by_display) > 1:
        return {'status': 'ambiguous', 'path': None, 'step': 'course display name',
                'candidates': [str(a) for a in by_display]}

    return {'status': 'none', 'path': None, 'step': 'no match',
            'candidates': [str(a) for a in actives]}


def scan_codes(vault: Path | str, skip_placeholders: bool = True) -> dict:
    """Every code: in every Weekly_overview.md under the vault root.

    Vault-wide, not semester-wide: last autumn's ECON produces exactly the same
    file names as this spring's ECON, and Obsidian resolves the collision
    silently. Used only on structural events (init, adoption, rename, new
    semester); routine runs read course_codes from _config.md.
    """
    vault = Path(vault)
    found: dict[str, list[str]] = {}
    skipped: list[str] = []
    for overview in vault.rglob(OVERVIEW_NAME):
        if any(part.startswith('.') for part in overview.relative_to(vault).parts[:-1]):
            continue
        if skip_placeholders:
            try:
                st = overview.stat()
                if st.st_size > 0 and getattr(st, 'st_blocks', 1) == 0:
                    skipped.append(str(overview.relative_to(vault)))
                    continue
            except OSError:
                skipped.append(str(overview.relative_to(vault)))
                continue
        try:
            fm, _ = read_frontmatter(overview)
        except Exception:
            continue
        code = fm.get('code')
        if code:
            found.setdefault(str(code), []).append(
                str(overview.parent.relative_to(vault)))
    duplicates = {c: paths for c, paths in found.items() if len(paths) > 1}
    return {'codes': found, 'duplicates': duplicates, 'skipped_placeholders': skipped}


def code_taken(vault: Path | str, code: str) -> dict:
    """Registry first, then a full scan: the registry covers archived courses
    whose overview files may be offloaded to iCloud."""
    cfg = read_config(vault)
    registry = cfg.get('course_codes') or {}
    if code in registry:
        return {'taken': True, 'where': registry[code], 'source': 'registry'}
    scan = scan_codes(vault)
    if code in scan['codes']:
        return {'taken': True, 'where': scan['codes'][code][0], 'source': 'scan'}
    return {'taken': False, 'where': None, 'source': 'scan',
            'skipped_placeholders': scan['skipped_placeholders']}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('find'); p.add_argument('--start', required=True)
    p = sub.add_parser('config'); p.add_argument('--vault', required=True)
    p = sub.add_parser('resolve')
    p.add_argument('--vault', required=True)
    p.add_argument('--hint'); p.add_argument('--cwd')
    p = sub.add_parser('kind'); p.add_argument('--path', required=True)
    p = sub.add_parser('identity'); p.add_argument('--path', required=True)
    p = sub.add_parser('frontmatter'); p.add_argument('--path', required=True)
    p = sub.add_parser('scan-codes'); p.add_argument('--vault', required=True)
    p = sub.add_parser('code-taken')
    p.add_argument('--vault', required=True); p.add_argument('--code', required=True)

    args = ap.parse_args(argv)
    try:
        if args.cmd == 'find':
            v = find_vault(args.start)
            out = {'vault': str(v) if v else None}
        elif args.cmd == 'config':
            out = read_config(args.vault)
        elif args.cmd == 'resolve':
            out = resolve_course(args.vault, args.hint, args.cwd)
        elif args.cmd == 'kind':
            out = {'kind': course_kind(args.path)}
        elif args.cmd == 'identity':
            out = course_identity(args.path)
        elif args.cmd == 'frontmatter':
            fm, body = read_frontmatter(Path(args.path))
            out = {'frontmatter': fm, 'body_chars': len(body)}
        elif args.cmd == 'scan-codes':
            out = scan_codes(args.vault)
        else:
            out = code_taken(args.vault, args.code)
    except VaultError as e:
        json.dump({'error': str(e)}, sys.stdout); sys.stdout.write('\n')
        return 2
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
