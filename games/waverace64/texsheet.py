"""Dirty room (dev only): contact sheets of textures by how they were found, or of the regenerated ones.

    python -m games.waverace64.texsheet <rom.z64> <out dir> [src: guess|override|trace|extend|all] [container hex]

With a clean ROM the same sheet shows the regenerated images (layout comes from the spec then).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from cleanroom.gfx import texfmt
from games.waverace64 import layout

FN = {0: "rgba", 2: "ci", 3: "ia", 4: "i"}


def decode(cs, c, o, r):
    d = cs[c]["data"]
    img = np.asarray(texfmt.decode(d[o:o + r["n"]], r["w"], r["h"], r["fmt"], r["siz"])).reshape(r["h"], r["w"], 4)
    if r["fmt"] == 2:
        if r.get("pal"):
            pc, po = r["pal"]
            pal = np.asarray(texfmt.decode(cs[pc]["data"][po:po + 512], 256, 1, 0, 2)).reshape(256, 4)
            img = pal[img[..., 0]]
    img = img.astype(np.float32)
    a = img[..., 3:4] / 255
    yy, xx = np.mgrid[:r["h"], :r["w"]]
    bg = np.where(((yy // 4 + xx // 4) & 1)[..., None] == 1, 70.0, 40.0) * np.array([1.0, 0.6, 1.0])
    return (img[..., :3] * a + bg * (1 - a)).astype(np.uint8)


def sheet(cs, items, out, prefix):
    PW, PH = 1900, 1400
    pages, page, x, y, rowh = 0, Image.new("RGB", (PW, PH), (24, 24, 40)), 0, 0, 0
    dr = ImageDraw.Draw(page)
    for c, o, r in items:
        try:
            im = Image.fromarray(decode(cs, c, o, r))
        except Exception as e:
            print("skip", hex(c), hex(o), e)
            continue
        if im.height > 200:
            im = im.crop((0, 0, im.width, 200))
        k = 3 if im.width <= 40 else 2 if im.width <= 100 else 1
        im = im.resize((im.width * k, im.height * k), Image.NEAREST)
        cw = max(im.width, 150) + 6
        if x + cw > PW:
            x, y, rowh = 0, y + rowh + 6, 0
        if y + im.height + 22 > PH:
            page.save(os.path.join(out, f"{prefix}_{pages:02d}.png"))
            pages += 1
            page, x, y, rowh = Image.new("RGB", (PW, PH), (24, 24, 40)), 0, 0, 0
            dr = ImageDraw.Draw(page)
        dr.text((x, y), f"{c:X}+{o:X}", fill=(255, 255, 0))
        dr.text((x, y + 10), f"{FN[r['fmt']]}{4 << r['siz']} {r['w']}x{r['h']}" + (f" s{r['score']}" if r.get("score") else ""),
                fill=(255, 120, 120) if r.get("score", 0) > 0.6 else (160, 220, 255))
        page.paste(im, (x, y + 21))
        x += cw
        rowh = max(rowh, im.height + 21)
    page.save(os.path.join(out, f"{prefix}_{pages:02d}.png"))
    return pages + 1


def candidates(cs, tex, out, thr=0.6):
    """One row per doubtful guess: the same bytes at every plausible width (pick by eye -> layout_overrides.json)."""
    items = []
    for (c, o), r in sorted(tex.items()):
        if r.get("src") != "guess" or r.get("score", 0) <= thr:
            continue
        n, bpp = r["gap"], 4 << r["siz"]
        ntex = n * 8 // bpp
        for w in range(8, 513, 4 if bpp >= 16 else 8):
            h = ntex // w
            if 6 <= h <= 200 and ntex - w * h < 64 // bpp * 8 + 1 and w <= 30 * h:
                items.append((c, o, dict(r, w=w, h=h, n=w * h * bpp // 8, score=0)))
    return sheet(cs, items, out, "cand"), len(items)


def main(argv):
    rom = open(argv[1], "rb").read()
    out = argv[2]
    src = argv[3] if len(argv) > 3 else "guess"
    only = int(argv[4], 16) if len(argv) > 4 else None
    os.makedirs(out, exist_ok=True)
    cs, sc = layout.containers(rom)
    tex, _, _ = layout.textures(cs, sc)
    items = [(c, o, r) for (c, o), r in sorted(tex.items())
             if r["kind"] == "tex" and (src == "all" or r.get("src") in src.split(",")) and (only is None or c == only)]
    if src == "cand":
        print("candidate pages, images:", candidates(cs, tex, out))
        return
    n = sheet(cs, items, out, src.replace(",", "_"))
    print(f"{len(items)} textures -> {n} pages {out}/{src.replace(',', '_')}_NN.png")


if __name__ == "__main__":
    main(sys.argv)
