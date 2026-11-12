#!/usr/bin/env python3
"""한 장의 그림 PNG(src/.preview/chNN/*.png)를 한 장의 점검표로 모은다.  사용: python3 src/contact.py ch03 [--cols 2]"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

SRC = Path(__file__).resolve().parent


def sheet(cid, cols=2, cell_w=640):
    d = SRC / '.preview' / cid
    files = sorted(p for p in d.glob('*.png') if not p.name.startswith('_') and '.dark' not in p.name)
    if not files:
        print('PNG 없음:', cid)
        return None
    ims = []
    for p in files:
        im = Image.open(p).convert('RGB')
        im = im.resize((cell_w, round(im.height * cell_w / im.width)), Image.LANCZOS)
        ims.append((p.stem, im))
    rows = [ims[i:i + cols] for i in range(0, len(ims), cols)]
    heights = [max(im.height for _, im in r) + 22 for r in rows]
    out = Image.new('RGB', (cell_w * cols, sum(heights)), (255, 255, 255))
    dr = ImageDraw.Draw(out)
    y = 0
    for r, h in zip(rows, heights):
        for i, (name, im) in enumerate(r):
            dr.text((i * cell_w + 8, y + 4), name, fill=(120, 0, 0))
            out.paste(im, (i * cell_w, y + 22))
        y += h
    dst = d / '_sheet.png'
    out.save(dst)
    print(dst.relative_to(SRC.parent), out.size, f'{len(files)}개')
    return dst


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    cols = int(sys.argv[sys.argv.index('--cols') + 1]) if '--cols' in sys.argv else 2
    for c in args:
        sheet(c, cols)
