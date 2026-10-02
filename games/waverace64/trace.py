"""Dirty room: texture loads seen at run time (RDRAM dumps of the retail game, dev only).

    python -m games.waverace64.trace <retail.z64> <dir with ram_*.bin> [more dirs]   -> dirty/trace.json (merged)

The game builds many display lists in code (menus, HUD, fonts, sprites); those never appear in the ROM's
static display lists. A RAM dump holds the frame's display lists: the same scan as for static data finds the
loads, the segment table comes from the G_MOVEWORD commands, and the pixels are matched back to their
container by locating each container's copy in RAM. Only (container, offset, format, size) leave this script.
"""
import collections
import glob
import json
import os
import struct
import sys

import numpy as np

from games.waverace64 import layout, texscan

OUT = layout.W + "trace.json"


def ram_be(path):
    return np.frombuffer(open(path, "rb").read(), "<u4").astype(">u4").tobytes()


def locate(ram, cs):
    """-> sorted [(ram start, ram end, container off)] for containers whose data sits in RAM."""
    out = []
    for off, c in cs.items():
        d = c["data"]
        if len(d) < 64:
            continue
        votes = collections.Counter()
        for k in range(8):
            p = (len(d) - 48) * k // 8 & ~7
            probe = d[p:p + 48]
            if len(set(probe)) < 12:
                continue
            a = ram.find(probe)
            while a >= 0:
                votes[a - p] += 1
                a = ram.find(probe, a + 1)
        for base, v in votes.items():
            if v >= 2 and base >= 0:
                out.append((base, base + len(d), off))
    return sorted(out)


def segments(ram):
    """segment -> set of bases seen in G_MOVEWORD segment commands."""
    a = np.frombuffer(ram, ">u4")[: len(ram) // 8 * 2].reshape(-1, 2)
    m = (a[:, 0] & 0xFFFF00FF) == 0xBC000006
    segs = collections.defaultdict(set)
    for w0, w1 in a[m]:
        s = ((int(w0) >> 8) & 0xFF) // 4
        if s < 16 and int(w1) < 0x800000 or (int(w1) >> 24) == 0x80:
            segs[s].add(int(w1) & 0x7FFFFF)
    return segs


def records(ram, cs):
    loc = locate(ram, cs)
    segs = segments(ram)

    def where(addr):
        cands = []
        if addr >> 24 in (0x80, 0x00) and (addr & 0xFFFFFF) < 0x400000 and addr >> 24 == 0x80:
            cands = [addr & 0x7FFFFF]
        elif (addr >> 24) < 16:
            cands = [b + (addr & 0xFFFFFF) for b in segs.get(addr >> 24, ())]
        out = []
        for a in cands:
            for s, e, off in loc:
                if s <= a < e and (off, a - s) not in out:
                    out.append((off, a - s))
        return out

    tex = {}
    last_tlut, waiting = None, []
    stats = collections.Counter()
    for r in texscan.scan(ram):
        w = where(r["addr"])
        if r["kind"] == "tlut":
            if r["count"] < 16:
                continue
            last_tlut = list(w[0]) if len(w) == 1 else None
            if len(w) == 1:
                tex[w[0]] = dict(kind="tlut", count=r["count"], n=r["count"] * 2)
                for k in waiting:                             # palette loaded after its image
                    if tex.get(k, {}).get("fmt") == 2 and not tex[k].get("pal"):
                        tex[k]["pal"] = last_tlut
            waiting = []
            continue
        fmt, siz = r.get("fmt", r["ifmt"]), r.get("siz", r["isiz"])
        bpp = texscan.BPP[siz]
        if "w" in r:
            wd, ht = r["w"], r["h"]
        elif r["kind"] == "block" and r.get("dxt"):
            nb = r["texels"] * texscan.BPP[r["isiz"]] // 8
            rowb = 8 * (2048 // r["dxt"])
            if not rowb:
                stats["nosize"] += 1
                continue
            wd, ht = rowb * 8 // bpp, max(1, nb // rowb)
        else:
            stats["nosize"] += 1
            continue
        if r["kind"] == "block":                              # the load itself bounds the data
            nb = r["texels"] * texscan.BPP[r["isiz"]] // 8
            if wd * ht * bpp // 8 > nb and wd:
                ht = max(1, nb * 8 // bpp // wd)
        if len(w) != 1:
            stats["unresolved" if not w else "ambiguous"] += 1
            continue
        rec = dict(kind="tex", fmt=fmt, siz=siz, w=wd, h=ht, n=(wd * ht * bpp + 7) // 8, sized="w" in r)
        if fmt == 2:
            rec["pal"] = last_tlut
        if w[0][1] + rec["n"] > len(cs[w[0][0]]["data"]) or wd > 1024 or ht > 1024:
            stats["overrun"] += 1
            continue
        old = tex.get(w[0])
        if old is None or (rec["sized"] and not old.get("sized")) or (old["kind"] == "tex" and rec["n"] > old["n"] and rec["sized"] >= old.get("sized", False)):
            tex[w[0]] = rec
            if fmt == 2 and not rec["pal"]:
                waiting.append(w[0])
        stats["ok"] += 1
    return tex, stats, len(loc)


def main(argv):
    rom = open(argv[1], "rb").read()
    cs, sc = layout.containers(rom)
    try:
        merged = {(r["c"], r["o"]): r for r in json.load(open(OUT))}
    except OSError:
        merged = {}
    before = len(merged)
    static, _, _ = layout.textures(cs, sc, use_trace=False)
    for d in argv[2:]:
        for f in sorted(glob.glob(os.path.join(d, "ram_*.bin"))):
            tex, stats, nloc = records(ram_be(f), cs)
            new = 0
            for k, r in tex.items():
                old = merged.get(k)
                if old is None or (r.get("sized") and not old.get("sized")) or (r["kind"] == "tex" and old["kind"] == "tex" and r["n"] > old["n"] and r.get("sized", False) >= old.get("sized", False)):
                    new += k not in merged and k not in static
                    merged[k] = dict(r, c=k[0], o=k[1])
            print(f"{os.path.basename(d)}/{os.path.basename(f)}: containers in RAM {nloc}, {dict(stats)}, new {new}")
    json.dump(list(merged.values()), open(OUT, "w"))
    print(f"trace: {before} -> {len(merged)} records, not in static scan: {sum(1 for k in merged if k not in static)}")


if __name__ == "__main__":
    main(sys.argv)
