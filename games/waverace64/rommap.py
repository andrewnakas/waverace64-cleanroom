"""Dirty room: map the retail ROM (MIO0 blocks, raw regions). Prints a one-screen summary.

    python -m games.waverace64.rommap <retail.z64> [dump dir]
"""
import json
import struct
import sys

from cleanroom.codec import mio0

MIO0_FIRST, MIO0_END = 0x1D11D0, 0x40B530
REGIONS = {  # from the decomp's splat yaml
    "ctl": (0x40B530, 0x428C30), "tbl": (0x428C30, 0x7AE8B0), "seq": (0x7AE8B0, 0x7C4B70), "banksets": (0x7C4B70, 0x800000),
    "seg_F6090": (0xF6090, 0xF7440), "assets_seg": (0xF7440, 0x1AE660), "mio0_chunk": (0x1AE660, 0x1B1FB0),
}


def blocks(rom):
    out, o = [], 0
    while True:
        o = rom.find(b"MIO0", o)
        if o < 0:
            break
        if o % 4 == 0:
            size, co, ro = struct.unpack(">3I", rom[o + 4:o + 16])
            if size < 0x400000 and co < ro < 0x400000:
                out.append(dict(off=o, size=size, csize=mio0.compressed_size(rom, o)))
        o += 4
    return out


def main(argv):
    rom = open(argv[1], "rb").read()
    bl = blocks(rom)
    for i, b in enumerate(bl):
        nxt = bl[i + 1]["off"] if i + 1 < len(bl) else None
        b["gap"] = (nxt - b["off"] - b["csize"]) if nxt else 0
        if len(argv) > 2:
            open(f"{argv[2]}/{b['off']:06X}.bin", "wb").write(mio0.decompress(rom, b["off"]))
    print(f"{len(bl)} MIO0 blocks, {sum(b['csize'] for b in bl)} -> {sum(b['size'] for b in bl)} bytes")
    out = [b for b in bl if not MIO0_FIRST <= b["off"] < MIO0_END]
    print("outside main run:", [(hex(b["off"]), b["size"]) for b in out])
    print("gaps > 16:", [(hex(b["off"]), b["gap"]) for b in bl if b["gap"] > 16][:20])
    if len(argv) > 2:
        json.dump(bl, open(f"{argv[2]}/blocks.json", "w"))


if __name__ == "__main__":
    main(sys.argv)
