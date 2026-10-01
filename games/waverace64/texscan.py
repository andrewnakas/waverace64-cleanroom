"""Dirty room: find texture loads in display-list data (F3D, RDP load commands).

A linear scan over 8-byte commands: SETTIMG followed by SETTILE / LOADBLOCK / LOADTLUT /
SETTILESIZE. Returns records dict(addr, fmt, siz, w, h, tlut) with segmented addresses.
"""
import struct

FMT = {0: "rgba", 1: "yuv", 2: "ci", 3: "ia", 4: "i"}
BPP = {0: 4, 1: 8, 2: 16, 3: 32}


def scan(data, start=0, end=None):
    end = len(data) if end is None else end
    out = []
    o = start
    while o + 8 <= end:
        if data[o] != 0xFD or data[o + 2] != 0 or data[o + 3] != 0 or data[o + 4] >= 0x10:
            o += 8
            continue
        w0, addr = struct.unpack_from(">II", data, o)
        rec = dict(at=o, addr=addr, ifmt=(w0 >> 21) & 7, isiz=(w0 >> 19) & 3, kind=None)
        tiles = {}
        p = o + 8
        for _ in range(10):
            if p + 8 > end:
                break
            c = data[p]
            a, b = struct.unpack_from(">II", data, p)
            if c == 0xF5:
                tiles[(b >> 24) & 7] = dict(fmt=(a >> 21) & 7, siz=(a >> 19) & 3, line=(a >> 9) & 0x1FF, pal=(b >> 20) & 15,
                                             maskt=(b >> 14) & 15, masks=(b >> 4) & 15)
            elif c == 0xF3:
                rec.update(kind="block", texels=((b >> 12) & 0xFFF) + 1, dxt=b & 0xFFF)
            elif c == 0xF4:
                rec.update(kind="tile", lw=(((b >> 12) & 0xFFF) >> 2) + 1, lh=((b & 0xFFF) >> 2) + 1)
            elif c == 0xF0:
                rec.update(kind="tlut", count=(((b >> 12) & 0xFFF) >> 2) + 1)
                break
            elif c == 0xF2:
                rec.update(w=(((b >> 12) & 0xFFF) >> 2) + 1, h=((b & 0xFFF) >> 2) + 1, rtile=(b >> 24) & 7)
                break
            elif c in (0xFD, 0xB8, 0xBF, 0x04, 0x06):
                break
            p += 8
        if "w" not in rec and rec["kind"] != "tlut":      # SM64 order: render tile + size come before SETTIMG
            p = o - 8
            for _ in range(6):
                if p < start:
                    break
                c = data[p]
                a, b = struct.unpack_from(">II", data, p)
                if c == 0xF5 and ((b >> 24) & 7) != 7:
                    tiles.setdefault((b >> 24) & 7, dict(fmt=(a >> 21) & 7, siz=(a >> 19) & 3, line=(a >> 9) & 0x1FF,
                                                          pal=(b >> 20) & 15, maskt=(b >> 14) & 15, masks=(b >> 4) & 15))
                elif c == 0xF2 and "w" not in rec:
                    rec.update(w=(((b >> 12) & 0xFFF) >> 2) + 1, h=((b & 0xFFF) >> 2) + 1, rtile=(b >> 24) & 7)
                elif c in (0xFD, 0xB8, 0xF3, 0x06):
                    break
                p -= 8
        rt = tiles.get(rec.get("rtile", 0)) or next((t for k, t in sorted(tiles.items()) if k != 7), None) or tiles.get(7)
        if rt:
            rec.update(fmt=rt["fmt"], siz=rt["siz"], line=rt["line"], pal=rt["pal"], masks=rt["masks"], maskt=rt["maskt"])
        if rec["kind"] is not None:
            out.append(rec)
        o += 8
    return out


def nbytes(rec):
    if rec["kind"] == "tlut":
        return rec["count"] * 2
    if "w" in rec and "siz" in rec:
        return rec["w"] * rec["h"] * BPP[rec["siz"]] // 8
    if rec["kind"] == "block":
        return rec["texels"] * BPP[rec["isiz"]] // 8
    return 0
