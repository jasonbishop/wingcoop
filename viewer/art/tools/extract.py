#!/usr/bin/env python3
"""Regenerate every component's art from the source concept sheets in art/source.

Everything is driven by art/manifest.json:
  * "outputs"   - one entry per texture: a crop box on a sheet plus a list of ops
  * "die_faces" - composed dice faces (wood square + food token art)

Usage (from the repo root):
    python3 art/tools/extract.py                 # rebuild everything
    python3 art/tools/extract.py --only mat,card_back
    python3 art/tools/extract.py --preview       # also write art/tools/preview.jpg contact sheet

Requires Pillow, numpy and scipy:  pip install pillow numpy scipy

Adding a new element from a new concept sheet:
  1. Put the sheet in art/source/ and register it under "sheets".
  2. Find the element's pixel box (open the sheet in any image editor, or run
     art/tools/find_boxes.py on it to list the bounding boxes of everything drawn on the parchment).
  3. Add an "outputs" entry with the box, any ops, and an "out" path (relative to the repo root);
     run this script.
"""
import argparse, json, os, sys
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repo root


def load_manifest():
    with open(os.path.join(ROOT, 'art', 'manifest.json')) as f:
        return json.load(f)


_sheet_cache = {}
def sheet(manifest, name):
    if name not in _sheet_cache:
        _sheet_cache[name] = Image.open(os.path.join(ROOT, manifest['sheets'][name]['path'])).convert('RGB')
    return _sheet_cache[name]


def crop(img, box, inset=0):
    x0, y0, x1, y1 = box
    return img.crop((x0 + inset, y0 + inset, x1 - inset, y1 - inset))


# ---------- ops ----------
def op_upscale(img, factor=2, sharpen=True):
    out = img.resize((img.width * factor, img.height * factor), Image.LANCZOS)
    if sharpen:
        out = out.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    return out


def op_extend_down(img, ratio=0.4, blend=60):
    """Make a panel taller by repeating its own lower region, with a soft seam."""
    w, h = img.size
    ext = int(h * ratio)
    lower = img.crop((0, h - ext - blend, w, h))
    tall = Image.new('RGB', (w, h + ext))
    tall.paste(img, (0, 0))
    tall.paste(lower.crop((0, blend, w, ext + blend)), (0, h))
    mask = Image.linear_gradient('L').resize((w, blend))
    seam = Image.composite(lower.crop((0, 0, w, blend)), img.crop((0, h - blend, w, h)), mask)
    tall.paste(seam, (0, h - blend))
    return tall


def op_patch(img, center, radius, source_dx):
    """Cover a small blemish with a soft-edged disc copied from beside it.
    center is (u, v) as fractions of width/height; radius and source_dx are fractions of width."""
    w, h = img.size
    cx, cy, r, dx = int(center[0] * w), int(center[1] * h), int(radius * w), int(source_dx * w)
    src = img.crop((cx - r + dx, cy - r, cx + r + dx, cy + r))
    m = Image.new('L', (2 * r, 2 * r), 0)
    ImageDraw.Draw(m).ellipse((8, 8, 2 * r - 8, 2 * r - 8), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(6))
    img = img.copy()
    img.paste(src, (cx - r, cy - r), m)
    return img


def disc_mask(size, inner=0.82, feather=0.02):
    m = Image.new('L', (size, size), 0)
    pad = size * (1 - inner) / 2
    ImageDraw.Draw(m).ellipse((pad, pad, size - pad, size - pad), fill=255)
    return m.filter(ImageFilter.GaussianBlur(size * feather))


def op_circle_mask(img, size=160):
    """Round token -> transparent PNG, trimming the token's dark outer ring."""
    t = img.resize((size, size), Image.LANCZOS).convert('RGBA')
    t.putalpha(disc_mask(size))
    return t


def op_outline_cutout(img, threshold=110, feather=1.2):
    """Cut out an object drawn with a dark outline (eggs, tokens) -> transparent PNG.
    Fills the area inside the outline, keeps the largest blob (drops drop-shadows and specks)."""
    import numpy as np
    from scipy import ndimage
    a = np.asarray(img.convert('RGB')).astype(int)
    inside = ndimage.binary_fill_holes(ndimage.binary_closing(a.mean(2) < threshold, iterations=2))
    lab, n = ndimage.label(inside)
    if n:
        sizes = ndimage.sum(inside, lab, range(1, n + 1))
        inside = lab == (1 + int(np.argmax(sizes)))
    alpha = Image.fromarray((inside * 255).astype('uint8')).filter(ImageFilter.GaussianBlur(feather))
    out = img.convert('RGBA')
    out.putalpha(alpha)
    return out.crop(alpha.getbbox())


OPS = {'upscale': op_upscale, 'extend_down': op_extend_down, 'patch': op_patch,
       'circle_mask': op_circle_mask, 'outline_cutout': op_outline_cutout}


def build_output(manifest, entry):
    img = crop(sheet(manifest, entry['sheet']), entry['box'], entry.get('inset', 0))
    for step in entry.get('ops', []):
        args = {k: v for k, v in step.items() if k not in ('op',) and not k.startswith('$')}
        img = OPS[step['op']](img, **args)
    path = os.path.join(ROOT, entry['out'])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if path.endswith('.png'):
        img.save(path, optimize=True)
    else:
        img.convert('RGB').save(path, quality=entry.get('quality', 88), optimize=True)
    return path


# ---------- dice faces ----------
def build_die_faces(manifest, only=None):
    spec = manifest['die_faces']
    S = spec['size']
    wspec = spec['wood']
    wood = crop(sheet(manifest, wspec['sheet']), wspec['box']).resize((S, S), Image.LANCZOS)
    wood = ImageEnhance.Brightness(wood).enhance(wspec['brightness'])
    wood = ImageEnhance.Color(wood).enhance(wspec['saturation'])
    wood = Image.blend(wood, Image.new('RGB', (S, S), tuple(wspec['tint'])), wspec['tint_amount'])
    vign = Image.new('L', (S, S), 0)
    ImageDraw.Draw(vign).rounded_rectangle((26, 26, S - 26, S - 26), radius=60, fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(28))
    base = Image.composite(wood, ImageEnhance.Brightness(wood).enhance(wspec['edge_darken']), vign)

    boxes = {e['id']: e for e in manifest['outputs']}

    def token(tid, size):
        e = boxes[tid]
        t = crop(sheet(manifest, e['sheet']), e['box']).resize((size, size), Image.LANCZOS)
        return t, disc_mask(size)

    def multiply_onto(dst, src, mask, pos):
        region = dst.crop((pos[0], pos[1], pos[0] + src.width, pos[1] + src.height))
        mul = Image.blend(ImageChops.multiply(region, src), src, 0.25)
        dst.paste(Image.composite(mul, region, mask), pos)

    written = []
    for face, tokens in spec['faces'].items():
        if face.startswith('$') or (only and f'die_{face}' not in only):
            continue
        f = base.copy()
        if len(tokens) == 1:
            sz = 470
            t, m = token(tokens[0], sz)
            multiply_onto(f, t, m, ((S - sz) // 2, (S - sz) // 2))
        else:  # two foods on one face: diagonal, top-left and bottom-right
            sz = 300
            for i, tid in enumerate(tokens):
                t, m = token(tid, sz)
                p = 10 + i * (S - sz - 20)
                multiply_onto(f, t, m, (p, p))
        path = os.path.join(ROOT, spec['out_pattern'].format(face=face))
        f.save(path, quality=86, optimize=True)
        written.append(path)
    return written


def preview(paths):
    thumbs = []
    for p in paths:
        im = Image.open(p).convert('RGB')
        im.thumbnail((220, 220))
        thumbs.append(im)
    cols = 6
    rows = (len(thumbs) + cols - 1) // cols
    sheet_img = Image.new('RGB', (cols * 230, rows * 230), (236, 230, 216))
    for i, t in enumerate(thumbs):
        sheet_img.paste(t, ((i % cols) * 230 + 5, (i // cols) * 230 + 5))
    out = os.path.join(ROOT, 'art', 'tools', 'preview.jpg')
    sheet_img.save(out, quality=85)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', help='comma-separated output ids (e.g. front,die_fish)')
    ap.add_argument('--preview', action='store_true', help='write tools/preview.jpg')
    a = ap.parse_args()
    only = set(a.only.split(',')) if a.only else None
    m = load_manifest()
    written = []
    for e in m['outputs']:
        if only and e['id'] not in only:
            continue
        written.append(build_output(m, e))
    written += build_die_faces(m, only)
    for p in written:
        im = Image.open(p)
        print(f'{os.path.relpath(p, ROOT):40s} {im.size[0]}x{im.size[1]}')
    if a.preview:
        print('preview ->', os.path.relpath(preview(written), ROOT))
    if not written:
        print('nothing matched --only', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
