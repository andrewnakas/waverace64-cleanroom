"""Clean room: build the clean ROM image.

    python -m games.waverace64.generate <retail.z64> <clean.z64>

Code, geometry and other kept data come from the ROM image as they are (the decomp builds the same bytes).
Every texture and palette in `spec/textures.json` is regenerated from its kept facts (format, size, colour
grid, 2-bit alpha) and written over the retail pixels; MIO0 blocks are re-compressed.
"""
import collections
import json
import os
import sys

import numpy as np

from cleanroom.decomp import gen
from cleanroom.gfx import texfmt
from games.waverace64 import layout, romtool

HERE = os.path.dirname(os.path.abspath(__file__))
BPP = [4, 8, 16, 32]


def key(t):
    return f"{t['c']:X}_{t['o']:X}"


def image(t, hooks=None):
    """Regenerated RGBA (h, w, 4) uint8 for one texture record."""
    if hooks:
        for h in hooks:
            img = h(t)
            if img is not None:
                return img
    return gen.from_digest(key(t), t)


def rgba16(px):
    """(n, 4) uint8 -> big-endian RGBA5551 bytes."""
    r, g, b, a = (px[:, i].astype(np.uint32) for i in range(4))
    return (((r >> 3) << 11) | ((g >> 3) << 6) | ((b >> 3) << 1) | (a >= 128)).astype(">u2").tobytes()


def build_palette(images, count):
    """Median-cut style palette from the regenerated images that share it. -> (count, 4) uint8"""
    from PIL import Image
    px = np.concatenate([im.reshape(-1, 4) for im in images]) if images else np.zeros((0, 4), np.uint8)
    solid = px[px[:, 3] >= 128]
    clear = len(solid) < len(px)
    k = count - (1 if clear else 0)
    pal = np.zeros((count, 4), np.uint8)
    if len(solid):
        im = Image.fromarray(solid[:, :3].reshape(1, -1, 3), "RGB").quantize(colors=max(1, min(k, 256)), method=Image.Quantize.MEDIANCUT)
        p = np.array(im.getpalette()[:3 * k], np.uint8).reshape(-1, 3)
        used = int(np.array(im).max()) + 1
        p = p[:used]
        base = 1 if clear else 0
        pal[base:base + len(p), :3] = p
        pal[base:base + len(p), 3] = 255
        if base + len(p) < count:                      # unused entries repeat the last colour
            pal[base + len(p):, :3] = p[-1]
            pal[base + len(p):, 3] = 255
    return pal, (1 if clear else 0), (len(p) if len(solid) else 0)


def index(img, pal, base, used):
    px = img.reshape(-1, 4).astype(np.int32)
    p = pal[base:base + max(1, used), :3].astype(np.int32)
    idx = np.empty(len(px), np.int32)
    for i in range(0, len(px), 256):                   # small chunks: the PC is short on memory
        d = ((px[i:i + 256, None, :3] - p[None]) ** 2).sum(-1)
        idx[i:i + 256] = d.argmin(1) + base
    if base:
        idx[px[:, 3] < 128] = 0
    return idx.astype(np.uint8)


def regenerate(spec, sizes, hooks=None):
    """-> {container: [(offset, bytes)]} patches for every texture and palette in the spec."""
    patches = collections.defaultdict(list)
    by_pal = collections.defaultdict(list)
    imgs = {}
    for t in spec:
        if t["kind"] != "tex":
            continue
        img = image(t, hooks)
        imgs[key(t)] = img
        if t["fmt"] == 2:
            by_pal[tuple(t["pal"]) if t.get("pal") else None].append(t)
        else:
            patches[t["c"]].append((t["o"], texfmt.encode(img, t["fmt"], t["siz"])))
    pals = {(t["c"], t["o"]): t for t in spec if t["kind"] == "tlut"}
    for pk, t in pals.items():
        users = by_pal.get(pk, [])
        pal, base, used = build_palette([imgs[key(u)] for u in users], t["count"])
        if not users:                                   # nothing known uses it: a grey ramp
            ramp = np.linspace(0, 255, t["count"]).astype(np.uint8)
            pal = np.stack([ramp, ramp, ramp, np.full(t["count"], 255, np.uint8)], -1)
        patches[pk[0]].append((pk[1], rgba16(pal)))
        for u in users:
            idx = index(imgs[key(u)], pal, base, used)
            data = idx.tobytes() if u["siz"] == 1 else texfmt.encode(np.repeat(idx.reshape(u["h"], u["w"], 1), 4, 2), 2, 0)
            patches[u["c"]].append((u["o"], data))
    for u in by_pal.get(None, []):                      # CI image whose palette is unknown: luminance as index
        img = imgs[key(u)]
        lum = img[..., :3].mean(-1).astype(np.uint8)
        idx = lum if u["siz"] == 1 else lum >> 4
        patches[u["c"]].append((u["o"], texfmt.encode(np.repeat(idx[..., None], 4, 2), 2, u["siz"])))
    return patches


def hooks():
    hs = []
    try:
        from games.waverace64 import drawn
        hs.append(drawn.hook)
    except ImportError:
        pass
    return hs


def main(argv):
    rom = open(argv[1], "rb").read()
    cs, sc = layout.containers(rom)
    spec = json.load(open(os.path.join(HERE, "spec", "textures.json")))
    patches = regenerate(spec, None, hooks())
    new = {}
    nbytes = 0
    for c, ps in patches.items():
        d = bytearray(cs[c]["data"])
        for o, b in ps:
            d[o:o + len(b)] = b
            nbytes += len(b)
        assert len(d) == len(cs[c]["data"])
        new[c] = bytes(d)
    out, info = romtool.build(rom, cs, new)
    extra = []
    try:
        from games.waverace64 import audio
        out, ainfo = audio.regenerate(out)
        extra.append(ainfo)
    except ImportError:
        pass
    if extra:
        from cleanroom import rom as crom
        out = bytearray(out)
        crom.finalize_crc(out)
        out = bytes(out)
    os.makedirs(os.path.dirname(argv[2]), exist_ok=True)
    open(argv[2], "wb").write(out)
    print(f"textures: {sum(1 for t in spec if t['kind'] == 'tex')} + {sum(1 for t in spec if t['kind'] == 'tlut')} palettes, {nbytes} bytes in {len(new)} containers")
    print("rom:", info, *extra)


if __name__ == "__main__":
    main(sys.argv)
