"""Dirty room: display-list commands that the game's code writes with constant operands.

    python -m games.waverace64.mipsscan <retail.z64>      -> summary (and dirty/codeloads.json)

Code that builds display lists stores constant words (lui/ori/addiu -> sw). The stream of stored constants of a
function is a display list with holes; texscan reads the texture loads out of it. Loads whose image address is a
constant are resolved to (container, offset); loads through a pointer / table are listed as "variable".
"""
import collections
import json
import struct
import sys

from games.waverace64 import layout, texscan

CODE = [(0x1050, 0xF6090), (0x1B1FB0, 0x1D11D0)]
W0 = {0xFD, 0xF5, 0xF3, 0xF4, 0xF2, 0xF0, 0xE6, 0xE7, 0xE8, 0xBA, 0xB9, 0xFC, 0xFB, 0xFA, 0xF9, 0xF8, 0xB6, 0xB7, 0xBB, 0x06, 0x04, 0xB8, 0xE4, 0xB4, 0xB3, 0xB2, 0xB1, 0x01, 0x03, 0xBC, 0xBD}


def stores(rom, a, b):
    """-> [(pc, value or None)] for every sw in code order; None = value not a known constant."""
    reg = {0: 0}
    out = []
    for pc in range(a, b, 4):
        w = struct.unpack_from(">I", rom, pc)[0]
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        if w == 0x03E00008:                                  # jr ra
            reg = {0: 0}
        elif op == 0x0F:
            reg[rt] = imm << 16
        elif op == 0x0D and rs in reg:
            reg[rt] = reg[rs] | imm
        elif op == 0x09 and rs in reg:
            reg[rt] = (reg[rs] + simm) & 0xFFFFFFFF
        elif op == 0x2B:
            out.append((pc, reg.get(rt)))
        elif op == 0 and (w & 0x3F) in (0x21, 0x25) and rt == 0 and rs in reg and ((w >> 11) & 31):     # move
            reg[(w >> 11) & 31] = reg[rs]
        elif op == 0:
            rd = (w >> 11) & 31
            if rd:
                reg.pop(rd, None)
        elif op in (0x23, 0x20, 0x21, 0x24, 0x25, 0x08, 0x0A, 0x0B, 0x0C, 0x0E, 0x0D, 0x09):
            if rt:
                reg.pop(rt, None)
        elif op == 0x03:                                     # jal: caller-saved registers die
            for r in list(reg):
                if r and not 16 <= r <= 23:
                    reg.pop(r)
        reg[0] = 0
    return out


def commands(st):
    """stored words -> pseudo display list bytes (w0 constant followed by its w1; unknown w1 = 0xFFFFFFFF)."""
    buf = bytearray()
    i = 0
    while i < len(st):
        v = st[i][1]
        if v is not None and (v >> 24) in W0 and v > 0xFFFF:
            w1 = st[i + 1][1] if i + 1 < len(st) and st[i + 1][0] - st[i][0] < 0x60 else None
            if w1 is not None and (w1 >> 24) in W0 and w1 > 0xFFFFFF and (v >> 24) != 0xFD and (w1 >> 24) != (v >> 24) and (v >> 24) in (0xE6, 0xE7, 0xE8, 0xB8):
                w1 = 0                                       # the zero word was stored elsewhere
                i += 1
            else:
                i += 2
            buf += struct.pack(">II", v, 0xFFFFFFFF if w1 is None else w1)
        else:
            i += 1
    return bytes(buf)


def main(argv):
    rom = open(argv[1], "rb").read()
    out, kinds = [], collections.Counter()
    for a, b in CODE:
        dl = commands(stores(rom, a, b))
        for r in texscan.scan(dl):
            fmt, siz = r.get("fmt", r["ifmt"]), r.get("siz", r["isiz"])
            var = r["addr"] == 0xFFFFFFFF or not 0 < (r["addr"] >> 24) < 16
            kinds["variable" if var else "const"] += 1
            out.append(dict(r, var=var, fmt=fmt, siz=siz))
    print(dict(kinds))
    shapes = collections.Counter((r["kind"], r["fmt"], r["siz"], r.get("w"), r.get("h"), r.get("count"), r["var"]) for r in out)
    for k, n in shapes.most_common(60):
        print(n, k)
    segs = collections.Counter(r["addr"] >> 24 for r in out if not r["var"])
    print("segments:", dict(segs))
    json.dump(out, open(layout.W + "codeloads.json", "w"))


if __name__ == "__main__":
    main(sys.argv)
