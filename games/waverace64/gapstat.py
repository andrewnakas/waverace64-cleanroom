"""Dirty room: classify unknown gaps by byte statistics. Prints one line per gap >= min size."""
import sys

import numpy as np

from games.waverace64 import coverage, layout


def feat(b):
    a = np.frombuffer(b, np.uint8)
    n = len(a) & ~15
    a = a[:n]
    u16 = a.reshape(-1, 2)
    odd = float((u16[:, 1] & 1).mean())
    zero = float((a == 0).mean())
    h = np.bincount(a, minlength=256) / len(a)
    ent = float(-(h[h > 0] * np.log2(h[h > 0])).sum())
    lag16 = float((a[16:] == a[:-16]).mean()) if n > 32 else 0
    lag2 = float((np.abs(a[2:].astype(int) - a[:-2]) < 8).mean())
    lag1 = float((np.abs(a[1:].astype(int) - a[:-1]) < 8).mean())
    r = a.reshape(-1, 16)
    vtxz = float((r[:, 6:8] == 0).all(axis=1).mean())          # Vtx flag word
    return odd, zero, ent, lag16, lag1, lag2, vtxz


def guess(f):
    odd, zero, ent, lag16, lag1, lag2, vtxz = f
    if vtxz > 0.9 and ent > 3:
        return "vtx?"
    if odd > 0.9 and ent > 4:
        return "rgba16"
    if zero > 0.6:
        return "sparse"
    if lag1 > 0.6 and ent > 3:
        return "8bit?"
    return "?"


def main(argv):
    rom = open(argv[1], "rb").read()
    mn = int(argv[2]) if len(argv) > 2 else 1024
    only = int(argv[3], 16) if len(argv) > 3 else None
    cs, sc = layout.containers(rom)
    tex, _, _ = layout.textures(cs, sc)
    cov = coverage.cover(cs, sc, tex)
    tot = {}
    for o in sorted(cs):
        if only and o != only:
            continue
        for a, b in coverage.gaps(cov[o]):
            if b - a < mn:
                tot["small"] = tot.get("small", 0) + b - a
                continue
            f = feat(cs[o]["data"][a:b])
            g = guess(f)
            tot[g] = tot.get(g, 0) + b - a
            if only or len(argv) > 4:
                print(f"{o:06X}+{a:05X} {b - a:6d} {g:7s} odd={f[0]:.2f} zero={f[1]:.2f} ent={f[2]:.1f} l16={f[3]:.2f} l1={f[4]:.2f} l2={f[5]:.2f} vz={f[6]:.2f}")
    print(tot)


if __name__ == "__main__":
    main(sys.argv)
