#!/usr/bin/env python3
"""Slides to Pass A items: one ID per slide, per bullet, per speaker note, per figure.

The reason this is a script and not model reading is coverage. Pass D subtracts
the set of IDs cited in the notes from the set Pass A emitted, and that only
means anything if the emitting is exhaustive and repeatable. A model reading a
deck decides what is worth an ID, which makes the arithmetic measure the model's
attention rather than the deck's content.

The subtle failure this guards against: **a slide whose whole content is one
equation or one figure extracts to almost no text.** Without an explicit item
for the picture and the table, Pass D reports full coverage while the densest
slide in the lecture is missing from the notes. So a picture gets an ID, a table
gets an ID and is reproduced structurally, and a slide with neither text nor
shapes still gets an ID saying it is empty — an empty ID that must be placed is
better than a silent hole.

Reading order is top-to-bottom, then left-to-right, by shape position rather
than by XML order: PowerPoint stores shapes in z-order, which is the order they
were added, and on a hand-edited deck that is frequently backwards.

IDs (note-invariants §2):
    S12     slide 12, its title or its first line
    S12.3   third text item on slide 12
    S12n    speaker notes on slide 12

CLI:
    extract_pptx.py extract --path <deck.pptx> --entry Content/slides_x.pptx \\
        --work <lesson/.work> --run <ts> --hash <h> \\
        [--images-dir <Final_notes/attachments>] [--code ECON --lesson L03] [--apply]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import extraction                                                  # noqa: E402
import naming                                                      # noqa: E402

CHUNK_WORDS = 8000

# A slide the lecturer wrote as a summary is worth more at revision time than a
# slide in the middle of a derivation. The tag is what carries that forward.
SUMMARY_RE = re.compile(
    r'\b(summary|recap|takeaway|takeaways|key points?|wrap[- ]up|conclusions?|'
    r'overview|agenda|outline|what we learned|povzetek|zaklju)\b', re.I)
KEYBOX_RE = re.compile(r'\b(definition|theorem|proposition|lemma|key concept|'
                       r'rule|assumption)s?\b', re.I)


def _shapes_in_reading_order(slide):
    # A shape with no explicit position is a placeholder laid out by the
    # template; putting it first matches how the slide actually reads.
    return _in_reading_order(list(slide.shapes))


GROUP = 6          # MSO_SHAPE_TYPE.GROUP, compared by value to avoid the import


def _leaves(shape):
    """Every non-group shape inside `shape`, however deeply nested."""
    if getattr(shape, 'shape_type', None) == GROUP:
        for child in shape.shapes:
            yield from _leaves(child)
    else:
        yield shape


def _in_reading_order(shapes):
    def key(s):
        top, left = getattr(s, 'top', None), getattr(s, 'left', None)
        return (top if top is not None else -1, left if left is not None else -1)
    return sorted(shapes, key=key)


def _group_text(shape) -> str:
    """A grouped diagram's labels, in reading order, repeats collapsed.

    PowerPoint diagrams are groups of shapes, and every label in one is live
    text. Walking only the top level dropped all of it: slide 23 of the EBT
    lecture 1 deck is the advanced stage-gate model and yielded nothing at all.
    One item per top-level group keeps the diagram legible as a single object
    instead of scattering it over ~25 near-duplicate ids.
    """
    parts = []
    for leaf in _in_reading_order(list(_leaves(shape))):
        if not getattr(leaf, 'has_text_frame', False):
            continue
        t = ' '.join((leaf.text_frame.text or '').split())
        if t:
            parts.append(t)
    out, seen = [], {}
    for t in parts:
        if t in seen:
            seen[t] += 1
        else:
            seen[t] = 1
            out.append(t)
    return ' \u00b7 '.join(f'{t} \u00d7{seen[t]}' if seen[t] > 1 else t for t in out)


def slide_text_stats(path: Path | str) -> list[dict]:
    """Per-slide text and picture measures, for pre-flight's image-slide check.

    Lives here so there is one shape walk, not two that disagree. Table cell
    text counts as text: without it a slide carrying only a table reads as
    empty and is flagged as an image slide.
    """
    from pptx import Presentation                       # noqa: E402
    prs = Presentation(str(path))
    sw, sh = prs.slide_width or 1, prs.slide_height or 1
    out = []
    for n, slide in enumerate(prs.slides, 1):
        words = pics = 0
        area = 0
        groups = mute = 0
        for shape in slide.shapes:
            if getattr(shape, 'shape_type', None) == GROUP:
                groups += 1
            for leaf in _leaves(shape):
                if getattr(leaf, 'image', None) is None \
                        and not getattr(leaf, 'has_table', False) \
                        and not (getattr(leaf, 'has_text_frame', False)
                                 and (leaf.text_frame.text or '').strip()):
                    mute += 1
                if getattr(leaf, 'has_text_frame', False):
                    words += len((leaf.text_frame.text or '').split())
                if getattr(leaf, 'has_table', False):
                    for r in leaf.table.rows:
                        for c in r.cells:
                            words += len((c.text or '').split())
                if getattr(leaf, 'image', None) is not None:
                    pics += 1
                    try:
                        area += (leaf.width or 0) * (leaf.height or 0)
                    except Exception:
                        pass
        out.append({'slide': n, 'words': words, 'pictures': pics,
                    'groups': groups, 'mute_shapes': mute,
                    'picture_area_pct': round(100 * area / (sw * sh), 1)})
    return out


def _table_markdown(table) -> str:
    rows = []
    for r in table.rows:
        rows.append([c.text.replace('\n', ' ').strip() for c in r.cells])
    if not rows:
        return ''
    out = ['| ' + ' | '.join(rows[0]) + ' |',
           '|' + '---|' * len(rows[0])]
    for r in rows[1:]:
        out.append('| ' + ' | '.join(r) + ' |')
    return '\n'.join(out)


def _title_of(slide) -> str:
    try:
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            return slide.shapes.title.text.strip()
    except Exception:
        pass
    return ''


def extract(path: Path | str, entry: str, images_dir: Path | str | None = None,
            code: str = '', lesson: str = '') -> dict:
    from pptx import Presentation                       # noqa: E402

    prs = Presentation(str(path))
    items, figures, warnings = [], [], []
    images_dir = Path(images_dir) if images_dir else None
    if images_dir:
        images_dir.mkdir(parents=True, exist_ok=True)

    for n, slide in enumerate(prs.slides, 1):
        title = _title_of(slide)
        tags = []
        if SUMMARY_RE.search(title):
            tags.append('summary_slide')
        elif KEYBOX_RE.search(title):
            tags.append('key_box')

        body, sub = [], 0
        items.append({'id': f'S{n}', 'tags': tags,
                      'text': title or f'(slide {n}, no title)'})
        head = items[-1]

        for shape in _shapes_in_reading_order(slide):
            if shape == getattr(slide.shapes, 'title', None):
                continue
            if getattr(shape, 'has_table', False):
                md = _table_markdown(shape.table)
                if md:
                    sub += 1
                    items.append({'id': f'S{n}.{sub}', 'tags': [],
                                  'text': 'Table:\n' + md})
                continue
            if getattr(shape, 'shape_type', None) == GROUP:
                text = _group_text(shape)
                if text:
                    sub += 1
                    items.append({'id': f'S{n}.{sub}', 'tags': [],
                                  'text': text})
                    body.append(text)
                for leaf in _in_reading_order(list(_leaves(shape))):
                    if getattr(leaf, 'image', None) is None:
                        continue
                    sub += 1
                    fid = f'S{n}.{sub}'
                    name, saved = _save_image(leaf, images_dir, code, lesson,
                                              fid, title or f'slide_{n}')
                    figures.append({'id': fid, 'slide': n, 'file': saved})
                    items.append({'id': fid, 'tags': [],
                                  'text': f'[figure on slide {n}: {name}]'})
                continue
            if getattr(shape, 'shape_type', None) is not None and \
                    getattr(shape, 'image', None) is not None:
                sub += 1
                fid = f'S{n}.{sub}'
                name, saved = _save_image(shape, images_dir, code, lesson, fid,
                                          title or f'slide_{n}')
                figures.append({'id': fid, 'slide': n, 'file': saved})
                items.append({'id': fid, 'tags': [],
                              'text': f'[figure on slide {n}: {name}]'})
                continue
            if not getattr(shape, 'has_text_frame', False):
                continue
            for para in shape.text_frame.paragraphs:
                text = ''.join(r.text for r in para.runs).strip() or para.text.strip()
                if not text or text == title:
                    continue
                sub += 1
                items.append({'id': f'S{n}.{sub}', 'tags': [], 'text': text})
                body.append(text)

        if not body and not title:
            head['text'] = (f'(slide {n} has no extractable text; it is a figure, '
                            'an equation or an image. Read the slide image.)')
            warnings.append({'slide': n, 'why': 'no text layer on this slide'})

        try:
            if slide.has_notes_slide:
                notes = (slide.notes_slide.notes_text_frame.text or '').strip()
                if notes:
                    items.append({'id': f'S{n}n', 'tags': [], 'text': notes})
        except Exception:
            pass

    chunks = _chunk_boundaries(items)
    return {'path': str(path), 'entry': entry, 'slides': len(prs.slides),
            'items': items, 'figures': figures, 'chunks': chunks,
            'warnings': warnings}


def _save_image(shape, images_dir, code, lesson, fid, caption) -> tuple:
    try:
        image = shape.image
        name = getattr(shape, 'name', '') or image.filename or 'figure'
    except Exception:
        return ('figure', None)
    if images_dir is None:
        return (name, None)
    ext = (image.ext or 'png').lstrip('.')
    slug = naming.slugify(caption)[:40] or 'figure'
    prefix = f'{code}_{lesson}_' if code and lesson else ''
    dest = images_dir / f'{prefix}fig_{fid}_{slug}.{ext}'
    try:
        dest.write_bytes(image.blob)
    except OSError:
        return (name, None)
    return (name, dest.name)


def _chunk_boundaries(items: list[dict]) -> list[str]:
    """First ID of each chunk. An ID is never split, so boundaries fall between
    items; recording them lets Pass D tell a lost item from a boundary artefact."""
    out, words = [], 0
    for item in items:
        n = len(item['text'].split())
        if words and words + n > CHUNK_WORDS:
            out.append(item['id'])
            words = 0
        words += n
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('extract')
    p.add_argument('--path', required=True)
    p.add_argument('--entry', required=True)
    p.add_argument('--work')
    p.add_argument('--run', default=''); p.add_argument('--hash', default='')
    p.add_argument('--images-dir'); p.add_argument('--code', default='')
    p.add_argument('--lesson', default='')
    p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)

    out = extract(args.path, args.entry, args.images_dir, args.code, args.lesson)
    if args.work:
        out['written'] = extraction.write(
            args.work, args.entry, args.run, args.hash, 'slides',
            out['items'], out['chunks'], apply_it=args.apply)
    out['items'] = len(out['items'])
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
