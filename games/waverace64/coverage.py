"""Dirty room: per-container coverage (texture / vertex / display list / unknown gaps)."""
import struct
import sys

import numpy as np

from games.waverace64 import layout

OPS = {0x01, 0x03, 0x04, 0x06, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF,
       0xE4, 0xE6, 0xE7, 0xE8, 0xE9, 0xED, 0xEE, 0xEF, 0xF0, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF, 0xC0}


def valid(d, o):
    """Strict check that the 8 bytes at o are a plausible F3D / RDP command (texel bytes rarely pass)."""
    c = d[o]
    if c not in OPS:
        return False
    low24 = d[o + 1] | d[o + 2] | d[o + 3]
    if c in (0xB8, 0xE6, 0xE7, 0xE8, 0xE9):
        return d[o + 1:o + 8] == bytes(7)
    if c in (0xB6, 0xB7, 0xBF, 0xB5, 0xBD):
        return low24 == 0
    if c in (0xF7, 0xF8, 0xF9, 0xFB):                 # colour registers: nothing in the low 24 bits (image bytes often start with these)
        return low24 == 0
    if c == 0xFA:
        return d[o + 1] == 0
    if c in (0xFD, 0xFF, 0xFE):
        return d[o + 2] & 0xF0 == 0 and d[o + 4] < 0x10
    if c in (0xF5, 0xF3, 0xF4, 0xF2, 0xF0):
        return d[o + 4] <= 7
    if c in (0xB9, 0xBA, 0xBB, 0xBC):
        return d[o + 1] == 0
    if c in (0x04, 0x01, 0x03):
        return d[o + 4] < 0x10
    if c == 0x06:
        return d[o + 1] in (0, 1) and d[o + 2] == 0 and d[o + 3] == 0 and d[o + 4] < 0x10
    return True


def dl_mask(d):
    """bool array: bytes that belong to display lists (runs of valid commands ending in ENDDL)."""
    m = np.zeros(len(d), bool)
    for o in range(0, len(d) - 7, 8):
        if d[o] == 0xB8 and d[o + 1:o + 8] == bytes(7):
            p = o
            while p - 8 >= 0 and not m[p - 8] and valid(d, p - 8) and not (d[p - 8] == 0xB8 and d[p - 7:p] == bytes(7)):
                p -= 8
            m[p:o + 8] = True
    return m


def cover(cs, sc, tex):
    """-> {off: uint8 array: 0 unknown, 1 tex, 2 vtx, 3 dl}"""
    cov = {o: np.zeros(len(c["data"]), np.uint8) for o, c in cs.items()}
    for off, c in cs.items():
        cov[off][dl_mask(c["data"])] = 3
    for off, c in cs.items():
        d = c["data"]
        for o in range(0, len(d) - 7, 8):
            if d[o] == 0x04 and cov[off][o] == 3:
                lo = struct.unpack_from(">H", d, o + 2)[0]         # F3D_OLD: n << 9 | (n * 16 - 1)
                n, ln = lo >> 9, (lo & 0x1FF) + 1
                if ln != n * 16 or n == 0:
                    continue
                for cc, a in layout.resolve(cs, sc, off, struct.unpack_from(">I", d, o + 4)[0]):
                    if a + ln <= len(cov[cc]):
                        cov[cc][a:a + ln] = np.where(cov[cc][a:a + ln] == 0, 2, cov[cc][a:a + ln])
    for (c, o), r in tex.items():
        cov[c][o:o + r["n"]] = 1
    return cov


def gaps(a):
    z = np.flatnonzero(np.diff(np.concatenate(([1], (a != 0).astype(np.int8), [1]))))
    return [(int(z[i]), int(z[i + 1])) for i in range(0, len(z), 2)]


def main(argv):
    rom = open(argv[1], "rb").read()
    cs, sc = layout.containers(rom)
    tex, _, _ = layout.textures(cs, sc)
    cov = cover(cs, sc, tex)
    tot = np.zeros(4, np.int64)
    rows = []
    for o in sorted(cs):
        cnt = np.bincount(cov[o], minlength=4)
        tot += cnt
        g = gaps(cov[o])
        big = sorted(g, key=lambda x: x[0] - x[1])[:3]
        rows.append((cnt[0], f"{o:06X} fl={sorted(cs[o]['flags'])} size={len(cov[o]):6d} tex={cnt[1]:6d} vtx={cnt[2]:6d} dl={cnt[3]:6d} unk={cnt[0]:6d} gaps={len(g)} big={[(hex(a), b - a) for a, b in big]}"))
    print("totals unknown/tex/vtx/dl:", tot.tolist())
    for _, r in sorted(rows, reverse=True)[:int(argv[2]) if len(argv) > 2 else 45]:
        print(r)


if __name__ == "__main__":
    main(sys.argv)
