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


def main(argv):
    rom = open(argv[1], "rb").read()
    cs, sc = layout.containers(rom)
    tex, unres, _ = layout.textures(cs, sc)
    out = [fact(cs, c, o, r) for (c, o), r in sorted(tex.items())]
    os.makedirs(os.path.join(HERE, "spec"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "spec", "textures.json"), "w"), separators=(",", ":"))
    nt = sum(1 for t in out if t["kind"] == "tex")
    print(f"spec: {nt} textures, {len(out) - nt} palettes, CI without palette {sum(1 for t in out if t.get('fmt') == 2 and not t.get('pal'))}")


if __name__ == "__main__":
    main(sys.argv)
