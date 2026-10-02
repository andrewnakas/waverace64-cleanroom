"""Dirty room: write the kept facts for every known texture (format, size, 4x4 colour grid, 2-bit alpha).

    python -m games.waverace64.extract_spec <retail.z64>      -> games/waverace64/spec/textures.json

Larger images (>= 128 px on a side) keep a 16x16 grid, as in the SM64 scope. Palettes keep nothing but their
length: new palettes are built from the regenerated images.
"""
import json
import os
import sys

import numpy as np

from cleanroom.decomp import spec as cspec
from cleanroom.gfx import texfmt
from games.waverace64 import layout

HERE = os.path.dirname(os.path.abspath(__file__))


def decode(cs, c, o, r):
    d = cs[c]["data"]
    pal = None
    if r["fmt"] == 2:
        if r.get("pal"):
            pc, po = r["pal"]
            pal = texfmt.decode(cs[pc]["data"][po:po + 512], 256, 1, 0, 2).reshape(256, 4)
        else:
            pal = np.stack([np.arange(256)] * 3 + [np.full(256, 255)], -1).astype(np.uint8)
    img = texfmt.decode(d[o:o + r["n"]], r["w"], r["h"], r["fmt"], r["siz"])
    img = np.asarray(img).reshape(r["h"], r["w"], 4)
    if pal is not None:
        img = pal[img[..., 0]]
    return img


def fact(cs, c, o, r):
    if r["kind"] == "tlut":
        return dict(c=c, o=o, kind="tlut", count=r["count"])
    img = decode(cs, c, o, r)
    n = 16 if max(r["w"], r["h"]) >= 128 else 4
    d = dict(c=c, o=o, kind="tex", fmt=r["fmt"], siz=r["siz"], w=r["w"], h=r["h"], grid=cspec.grid(img.astype(np.float32), n))
    if (img[..., 3] < 250).any():
        d["alpha2"] = cspec.alpha2(img[..., 3])
    if r.get("pal"):
        d["pal"] = r["pal"]
    return d


def strip_pictures(cs, tex, out):
    """A picture stored as a stack of thin strips (title logo, craft thumbnails) keeps ONE coarse grid for the whole
    picture, not one per strip (a grid per 4-pixel strip would keep nearly every row). Each strip's grid is the
    picture grid's row at its height."""
    recs = sorted(((c, o), r) for (c, o), r in tex.items() if r["kind"] == "tex")
    by = {(d["c"], d["o"]): d for d in out}
    groups, cur = [], []
    for k, r in recs:
        thin = r["h"] <= 8 and r["w"] >= 8 * r["h"]
        if cur and thin and k[0] == cur[-1][0][0] and (r["w"], r["fmt"], r["siz"]) == tuple(cur[-1][1][x] for x in ("w", "fmt", "siz"))                 and 0 <= k[1] - (cur[-1][0][1] + cur[-1][1]["n"]) <= 16:
            cur.append((k, r))
            continue
        if len(cur) >= 3:
            groups.append(cur)
        cur = [(k, r)] if thin else []
    if len(cur) >= 3:
        groups.append(cur)
    for g in groups:
        pic = np.concatenate([decode(cs, k[0], k[1], r) for k, r in g]).astype(np.float32)
        n = 16 if max(pic.shape[:2]) >= 128 else 4
        G = np.array(cspec.grid(pic, n)).reshape(n, n, 4)
        y = 0
        for k, r in g:
            d = by[k]
            m = int(round(len(d["grid"]) ** 0.5))
            row = G[min(n - 1, int((y + r["h"] / 2) * n / pic.shape[0]))]
            row = row[(np.arange(m) * n) // m]
            d["grid"] = [[int(v) for v in px] for _ in range(m) for px in row]
            y += r["h"]
    return len(groups), sum(len(g) for g in groups)


def main(argv):
    rom = open(argv[1], "rb").read()
    cs, sc = layout.containers(rom)
    tex, unres, _ = layout.textures(cs, sc)
    out = [fact(cs, c, o, r) for (c, o), r in sorted(tex.items())]
    ng, ns = strip_pictures(cs, tex, out)
    print(f"strip pictures: {ng} ({ns} strips share one grid each)")
    os.makedirs(os.path.join(HERE, "spec"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "spec", "textures.json"), "w"), separators=(",", ":"))
    nt = sum(1 for t in out if t["kind"] == "tex")
    print(f"spec: {nt} textures, {len(out) - nt} palettes, CI without palette {sum(1 for t in out if t.get('fmt') == 2 and not t.get('pal'))}")


if __name__ == "__main__":
    main(sys.argv)
