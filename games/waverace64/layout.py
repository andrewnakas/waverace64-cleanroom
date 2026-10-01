"""Dirty room: containers (MIO0 blocks + raw regions), segment map, texture references, coverage.

    python -m games.waverace64.layout <retail.z64>      -> dirty/layout.json + one-screen summary
"""
import collections
import json
import struct
import sys

from cleanroom.codec import mio0
from games.waverace64 import rommap, texscan

W = "D:/n64work/waverace64/dirty/"
TABLES = (0x95310, 0x9F930)
FLAGSEG = {5: 13, 8: 14, 9: 0}
RAW = {0xF6090: (0x165C00, 1, 0)}          # segment 1 = ROM 0xF6090..0x165C00 (sys_main.c); 0x165C00.. is rider animation


def scenes(rom):
    def ent(o):
        return struct.unpack_from(">4I", rom, o)

    def ok(e):
        return 0xF0000 <= e[0] < e[1] <= 0x40B530 and 0 < e[2] <= 12 and e[3] < 0x200000
    o, out = TABLES[0], []
    while o < TABLES[1]:
        if ok(ent(o)):
            s = []
            while ok(ent(o)):
                s.append(ent(o))
                o += 16
            out.append(s)
        else:
            o += 4
    return out


def containers(rom):
    """off -> dict(data, size, places=set((seg, base)), scenes=[idx], flag)"""
    sc = scenes(rom)
    cs = {}
    bl = rommap.blocks(rom)
    for b in bl:
        cs[b["off"]] = dict(off=b["off"], data=mio0.decompress(rom, b["off"]), csize=b["csize"], places=set(), scenes=[], flags=set(), mio0=True)
    for off, (end, seg, base) in RAW.items():
        cs[off] = dict(off=off, data=rom[off:end], csize=end - off, places={(seg, base)}, scenes=[], flags=set(), mio0=False)
    for i, s in enumerate(sc):
        for st, en, flag, dest in s:
            if flag == 6:
                cs.setdefault(st, dict(off=st, data=rom[st:en], csize=en - st, places=set(), scenes=[], flags=set(), mio0=False))
            c = cs[st]
            c["flags"].add(flag)
            c["scenes"].append(i)
            if flag == 9:
                c["places"].add((0x80, 0x29A200))
            elif flag == 6:
                pass
            else:
                c["places"].add((FLAGSEG.get(flag, 8), dest))
    ends = sorted({en for s in sc for st, en, _, _ in s if st in cs and cs[st]["mio0"]})
    for off, c in cs.items():
        if c["mio0"]:                     # slot = up to the table's end address (or the compressed size)
            e = [en for s in sc for st, en, _, _ in s if st == off]
            c["slot"] = (min(e) - off) if e else ((c["csize"] + 15) & ~15)
    return cs, sc


def resolve(cs, sc, src, addr):
    """segmented address used inside container src -> [(container off, offset)]"""
    seg, a = addr >> 24, addr & 0xFFFFFF
    c = cs[src]
    for s, base in c["places"]:
        if s == seg and base <= a < base + len(c["data"]):
            return [(src, a - base)]
    out = []
    for i in c["scenes"] or range(len(sc)):
        for st, en, flag, dest in sc[i]:
            if flag in (6, 9) or st == src:
                continue
            if FLAGSEG.get(flag, 8) == seg and dest <= a < dest + len(cs[st]["data"]) and (st, a - dest) not in out:
                out.append((st, a - dest))
    if not out and seg == 1:
        out = [(0xF6090, a)]
    return out


def textures(cs, sc):
    """-> {(container, offset): record}, unresolved list"""
    tex, unres, multi = {}, [], 0
    for off, c in cs.items():
        last_tlut = None
        for r in texscan.scan(c["data"]):
            if r["kind"] == "tlut":
                rec = dict(kind="tlut", n=r["count"] * 2, count=r["count"])
                t = resolve(cs, sc, off, r["addr"])
                last_tlut = list(t[0]) if t else None
            else:
                fmt, siz = r.get("fmt", r["ifmt"]), r.get("siz", r["isiz"])
                bpp = texscan.BPP[siz]
                if "w" in r:
                    w, h = r["w"], r["h"]
                elif r["kind"] == "block" and r["dxt"]:
                    nb = r["texels"] * texscan.BPP[r["isiz"]] // 8
                    rowb = 8 * (2048 // r["dxt"])
                    w, h = rowb * 8 // bpp, max(1, nb // rowb)
                else:
                    continue
                rec = dict(kind="tex", fmt=fmt, siz=siz, w=w, h=h, n=(w * h * bpp + 7) // 8, sized="w" in r)
                if fmt == 2:
                    rec["pal"] = last_tlut
            where = resolve(cs, sc, off, r["addr"])
            if not where:
                unres.append((off, r["at"], r["addr"]))
                continue
            multi += len(where) > 1
            for key in where:
                if key[1] + rec["n"] > len(cs[key[0]]["data"]):
                    continue
                old = tex.get(key)
                if old is None or (rec.get("sized") and not old.get("sized")) or (rec["kind"] == old["kind"] and rec["n"] > old["n"] and rec.get("sized")):
                    tex[key] = dict(rec, src=off, at=r["at"])
    return tex, unres, multi


def main(argv):
    rom = open(argv[1], "rb").read()
    cs, sc = containers(rom)
    tex, unres, multi = textures(cs, sc)
    per = collections.Counter()
    nb = collections.Counter()
    for (c, o), r in tex.items():
        per[c] += 1
        nb[c] += r["n"]
    print(f"{len(cs)} containers, {len(sc)} scenes, {len(tex)} textures+palettes ({sum(nb.values())} bytes), unresolved refs {len(unres)}, multi {multi}")
    segs = collections.Counter(a >> 24 for _, _, a in unres)
    print("unresolved by segment:", dict(segs))
    tot = sum(len(c["data"]) for c in cs.values())
    print(f"container bytes {tot}; texture share {sum(nb.values()) / tot:.0%}")
    none = [f"{o:X}({len(c['data'])})" for o, c in sorted(cs.items()) if per[o] == 0]
    print("containers without DL-referenced textures:", " ".join(none))
    json.dump(dict(tex=[dict(r, c=c, o=o) for (c, o), r in sorted(tex.items())], unres=unres), open(W + "layout.json", "w"))


if __name__ == "__main__":
    main(sys.argv)
