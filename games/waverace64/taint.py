"""DIRTY-ROOM CHECK: clean ROM vs retail ROM.

    python -m games.waverace64.taint <retail.z64> <clean.z64>

1. Every regenerated stream (texture payload raw + decoded RGBA, palette, ADPCM data, codebook, loop state)
   of the clean ROM is scanned against the retail streams: a shared run >= cleanroom.taint.FAIL_RUN bytes
   (decoded RGBA: >= 32 texels) fails.
2. Everything else must be the kept image: bytes outside the spec regions are compared and reported
   (containers byte for byte; the rest of the ROM except load tables, moved blocks and the header CRC).
Exit code 1 when anything fails.
"""
import json
import os
import struct
import sys

import numpy as np

from cleanroom import taint
from cleanroom.gfx import texfmt
from games.waverace64 import audio, layout

HERE = os.path.dirname(os.path.abspath(__file__))
RGBA_RUN = 4 * taint.FAIL_RUN
BPP = [4, 8, 16, 32]


def nbytes(t):
    return t["count"] * 2 if t["kind"] == "tlut" else (t["w"] * t["h"] * BPP[t["siz"]] + 7) // 8


def offmap(rom, clean):
    """retail container offset -> clean container offset (load tables are parallel)."""
    m = {}
    for s, t in zip(layout.scenes(rom), layout.scenes(clean)):
        for a, b in zip(s, t):
            m[a[0]] = b[0]
    return m


def rgba(cs, t):
    d = cs[t["c"]]["data"]
    img = texfmt.decode(d[t["o"]:t["o"] + nbytes(t)], t["w"], t["h"], t["fmt"], t["siz"])
    img = np.asarray(img).reshape(-1, 4)
    if t["fmt"] == 2 and t.get("pal"):
        pc, po = t["pal"]
        pal = texfmt.decode(cs[pc]["data"][po:po + 512], 256, 1, 0, 2).reshape(256, 4)
        img = pal[img[:, 0]]
    return img.astype(np.uint8).tobytes()


def tex_streams(cs, spec):
    for t in spec:
        k = f"{t['c']:X}+{t['o']:X}"
        yield k, cs[t["c"]]["data"][t["o"]:t["o"] + nbytes(t)]
        if t["kind"] == "tex":
            yield k + ".rgba", rgba(cs, t)


def audio_streams(rom):
    for k, s in audio.parse(rom).items():
        a = audio.TBL + k[0] + k[1]
        n = audio.name(k)
        yield "adpcm" + n, rom[a:a + s["size"]]
        for b in s["books"]:
            yield f"book@{b:X}", rom[b + 8:b + 8 + 32 * s["npred"]]
        if s["loop"][2]:
            for l in s["loops"]:
                yield f"loop@{l:X}", rom[l + 16:l + 48]


def main(argv):
    rom = open(argv[1], "rb").read()
    clean = open(argv[2], "rb").read()
    spec = json.load(open(os.path.join(HERE, "spec", "textures.json")))
    cs, sc = layout.containers(rom)
    cc, _ = layout.containers(clean)
    om = offmap(rom, clean)
    om.update({o: o for o in cs if o not in om})
    ccs = {o: cc[om[o]] for o in cs if om[o] in cc}
    assert len(ccs) == len(cs), "containers missing in the clean ROM"

    retail = list(tex_streams(cs, spec)) + list(audio_streams(rom))
    index = taint.build_index(s for _, s in retail)
    mine = list(tex_streams(ccs, spec)) + list(audio_streams(clean))
    hits = taint.scan(index, mine)
    fail = [h for h in hits if h[3] >= (RGBA_RUN if h[0].endswith(".rgba") else taint.FAIL_RUN)]
    same = sum(1 for (k, a), (_, b) in zip(retail, mine) if a == b and len(set(a)) > 5)

    # kept image: container bytes outside spec regions must be untouched
    diff = 0
    for o, c in cs.items():
        a = np.frombuffer(c["data"], np.uint8)
        b = np.frombuffer(ccs[o]["data"], np.uint8)
        mask = np.ones(len(a), bool)
        for t in spec:
            if t["c"] == o:
                mask[t["o"]:t["o"] + nbytes(t)] = False
        diff += int(((a != b) & mask).sum())
    # ROM outside containers / sample area / tables / header
    a = np.frombuffer(rom, np.uint8)
    b = np.frombuffer(clean, np.uint8)
    mask = np.ones(len(a), bool)
    mask[0x10:0x18] = False
    mask[layout.TABLES[0]:layout.TABLES[1]] = False
    mask[0x1AE660:0x1B1FB0] = False
    mask[0x1D11D0:0x40B530] = False
    mask[audio.CTL:audio.SEQ] = False
    mask[0x7C4C10:] = False
    for o, c in cs.items():
        if not c["mio0"]:
            mask[o:o + len(c["data"])] = False
    rest = int(((a != b) & mask).sum())
    ctl_diff = int((a[audio.CTL:audio.TBL] != b[audio.CTL:audio.TBL]).sum())
    ctl_spec = sum(32 * s["npred"] * len(s["books"]) + (32 * len(s["loops"]) if s["loop"][2] else 0) for s in audio.parse(rom).values())

    print(f"taint: {len(mine)} streams, {len(fail)} failing, {len(hits) - len(fail)} short coincidences, identical streams {same}")
    print(f"kept image: {diff} container bytes and {rest} ROM bytes differ outside spec regions; ctl bytes changed {ctl_diff} (books+loop states span {ctl_spec})")
    for h in fail[:12]:
        print("  FAIL", h)
    ok = not fail and not same and diff == 0 and rest == 0
    print("0 failing" if ok else "TAINT FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv)
