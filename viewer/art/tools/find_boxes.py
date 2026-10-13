#!/usr/bin/env python3
"""List bounding boxes of the elements drawn on a concept sheet.

Concept sheets draw each element on a plain parchment background, so anything noticeably
darker or more colourful than the parchment is foreground. This prints one [x0, y0, x1, y1]
box per connected blob, largest first, ready to paste into art/manifest.json.

Usage:
    python3 art/tools/find_boxes.py art/source/texture-sheet.jpg
    python3 art/tools/find_boxes.py art/source/concept-sheet.jpg --region 1050,1800,1780,2300 --min-area 5000
    python3 tools/find_boxes.py SHEET --annotate     # also writes SHEET.boxes.jpg with numbered boxes

Text labels on the sheet also show up as small blobs; use --min-area to drop them.
Round tokens with a dark outline are found more reliably with --outline.

Requires Pillow, numpy and scipy:  pip install pillow numpy scipy
"""
import argparse
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('sheet')
    ap.add_argument('--region', help='x0,y0,x1,y1 to search within (sheet pixels)')
    ap.add_argument('--min-area', type=int, default=20000, help='ignore boxes smaller than this (w*h)')
    ap.add_argument('--outline', action='store_true', help='detect shapes by their dark outline and fill them')
    ap.add_argument('--annotate', action='store_true')
    a = ap.parse_args()

    img = Image.open(a.sheet).convert('RGB')
    arr = np.asarray(img).astype(int)
    ox = oy = 0
    if a.region:
        x0, y0, x1, y1 = map(int, a.region.split(','))
        arr, ox, oy = arr[y0:y1, x0:x1], x0, y0

    lum = arr.mean(2)
    sat = arr.max(2) - arr.min(2)
    if a.outline:
        fg = ndimage.binary_fill_holes(ndimage.binary_closing(lum < 120, iterations=2))
    else:
        fg = ndimage.binary_opening((lum < 200) | (sat > 45), iterations=2)

    lab, _ = ndimage.label(fg)
    boxes = []
    for s in ndimage.find_objects(lab):
        x0, x1, y0, y1 = s[1].start + ox, s[1].stop + ox, s[0].start + oy, s[0].stop + oy
        if (x1 - x0) * (y1 - y0) >= a.min_area:
            boxes.append([x0, y0, x1, y1])
    boxes.sort(key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))

    for i, b in enumerate(boxes):
        print(f'{i:2d}  box {b}   {b[2]-b[0]}x{b[3]-b[1]}')

    if a.annotate:
        out = img.copy()
        d = ImageDraw.Draw(out)
        for i, b in enumerate(boxes):
            d.rectangle(b, outline=(220, 30, 30), width=4)
            d.text((b[0] + 6, b[1] + 6), str(i), fill=(220, 30, 30))
        path = a.sheet.rsplit('.', 1)[0] + '.boxes.jpg'
        out.save(path, quality=85)
        print('annotated ->', path)


if __name__ == '__main__':
    main()
