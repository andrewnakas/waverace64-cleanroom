"""Dirty room (dev only, never published): contact sheets of unknown gaps, drawn with a guessed format + width.

    python -m games.waverace64.gapsheet <retail.z64> <out dir> [min bytes] [container hex]
"""
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

from games.waverace64 import coverage, layout

WIDTHS = [8, 12, 16, 24, 32, 40, 48, 56, 64, 72, 80, 96, 128, 160, 256, 320]


def is_code(b):
    w = np.frombuffer(b[:len(b) & ~3], ">u4")
    op = w >> 26
    return float(np.isin(op, [0x09, 0x23, 0x2B, 0x0F, 0x03, 0x00, 0x05, 0x04, 0x31, 0x39, 0x0D, 0x0C, 0x11]).mean())


def planes(b):
    """candidate decodings -> [(name, bytes per texel numerator/denominator, 2D-able float array)]"""
    a = np.frombuffer(b, np.uint8)
    out = []
    n = len(a) & ~1
    u = a[:n].reshape(-1, 2).astype(np.uint16)
    v = (u[:, 0] << 8) | u[:, 1]
    out.append(("rgba16", 2, ((v >> 11) & 31) * 8.0 * 0.3 + ((v >> 6) & 31) * 8.0 * 0.6 + ((v >> 1) & 31) * 8.0 * 0.1))
    out.append(("ia16", 2, u[:, 0].astype(float)))
    out.append(("i8", 1, a.astype(float)))
    out.append(("ia8", 1, (a >> 4) * 17.0))
    n4 = np.empty(len(a) * 2)
    n4[0::2] = (a >> 4) * 17.0
    n4[1::2] = (a & 15) * 17.0
    out.append(("i4", 0.5, n4))
    return out


def lagdiff(x, k):
    return float(np.abs(x[k:] - x[:-k]).mean()) if len(x) > k + 8 else 1e9


def guess(b):
    """Row width = the lag at which texels match far better than at the lags around it."""
    best = None
    for name, bpt, x in planes(b):
        x = x[:16384]
        if x.std() < 1:
            continue
        for w in WIDTHS:
            if len(x) < 3 * w:
                continue
            around = (lagdiff(x, w - 2) + lagdiff(x, w + 2) + lagdiff(x, w - 3) + lagdiff(x, w + 3)) / 4 + 1e-6
            s = lagdiff(x, w) / around
            if best is None or s < best[0] * 0.9:
                best = (s, name, w)
    return best or (9.0, "i8", 32)


def render(b, name, w):
    a = np.frombuffer(b, np.uint8)
    if name in ("rgba16", "ia16"):
        n = len(a) // 2 // w * w
        u = a[:n * 2].reshape(-1, 2).astype(np.uint16)
        if name == "rgba16":
            v = (u[:, 0] << 8) | u[:, 1]
            rgb = np.stack([(v >> 11) & 31, (v >> 6) & 31, (v >> 1) & 31], -1) * 8
            al = (v & 1)[:, None]
            rgb = np.where(al == 1, rgb, rgb // 3 + np.array([60, 0, 60]))
        else:
            rgb = np.stack([u[:, 0], u[:, 0], u[:, 1]], -1)
        return rgb.reshape(-1, w, 3).astype(np.uint8)
    if name == "i4":
        x = np.empty(len(a) * 2, np.uint8)
        x[0::2] = (a >> 4) * 17
        x[1::2] = (a & 15) * 17
    elif name == "ia8":
        x = (a >> 4) * 17
    else:
        x = a
    n = len(x) // w * w
    return np.repeat(x[:n].reshape(-1, w, 1), 3, 2).astype(np.uint8)


def main(argv):
    rom = open(argv[1], "rb").read()
    out = argv[2]
    mn = int(argv[3]) if len(argv) > 3 else 512
    only = int(argv[4], 16) if len(argv) > 4 else None
    os.makedirs(out, exist_ok=True)
    cs, sc = layout.containers(rom)
    tex, _, _ = layout.textures(cs, sc)
    cov = coverage.cover(cs, sc, tex)
    cells, listing = [], []
    for c in sorted(cs):
        if only and c != only or 6 in cs[c]["flags"]:
            continue
        for a, b in coverage.gaps(cov[c]):
            if b - a < mn:
                continue
            d = cs[c]["data"][a:b]
            code = is_code(d)
            s, name, w = guess(d[:65536])
            img = render(d[:32768], name, w)
            im = Image.fromarray(img).crop((0, 0, w, min(img.shape[0], 96)))
            k = 2 if w <= 64 else 1
            im = im.resize((im.width * k, im.height * k), Image.NEAREST)
            cells.append((f"{c:X}+{a:X} {b - a} {name} w{w}" + (" CODE?" if code > 0.6 else ""), im))
            listing.append(f"{c:06X}+{a:05X} {b - a:6d} {name:6s} w={w:3d} s={s:.2f} code={code:.2f}")
    open(os.path.join(out, "gaps.txt"), "w").write("\n".join(listing))
    page, x, y, rowh, n = None, 0, 0, 0, 0
    PW, PH = 1900, 1400

    def flush():
        nonlocal page, n
        if page:
            page.save(os.path.join(out, f"gaps_{n:02d}.png"))
            n += 1
        page = Image.new("RGB", (PW, PH), (24, 24, 40))

    flush()
    dr = ImageDraw.Draw(page)
    for label, im in cells:
        cw = max(im.width, 190) + 6
        if x + cw > PW:
            x, y, rowh = 0, y + rowh + 16, 0
        if y + im.height + 12 > PH:
            flush()
            dr = ImageDraw.Draw(page)
            x, y, rowh = 0, 0, 0
        dr.text((x, y), label, fill=(255, 255, 0))
        page.paste(im, (x, y + 11))
        x += cw
        rowh = max(rowh, im.height + 11)
    flush()
    print(f"{len(cells)} gaps, {sum(int(l.split()[1]) for l in listing)} bytes -> {n} pages in {out}")


if __name__ == "__main__":
    main(sys.argv)
