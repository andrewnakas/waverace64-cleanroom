"""Rebuild the ROM image from containers (MIO0 blocks re-compressed, load tables re-pointed, CRC).

Code and kept data stay as they are. Every MIO0 block is re-compressed and the blocks of each run are laid
out again one after another; what does not fit goes to the free tail of the ROM (0x7C4C10..0x800000).
"""
import hashlib
import os
import struct

from cleanroom import rom as crom
from cleanroom.codec import mio0
from games.waverace64 import layout

TAIL = (0x7C4C10, 0x800000)
SPANS = [(0x1D11D0, 0x2A4ED0), (0x2E5FB0, 0x40B530)]      # the two runs of MIO0 blocks (raw course data sits between)
CACHE = "D:/n64work/waverace64/build/mio0cache"


def compress(data):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, hashlib.sha1(data).hexdigest())
    if os.path.exists(p):
        return open(p, "rb").read()
    c = mio0.compress(data)
    assert mio0.decompress(c) == data
    open(p, "wb").write(c)
    return c


def build(rom, cs, new):
    """rom: retail image; cs: layout.containers(rom)[0]; new: {off: bytes} replaced container data."""
    out = bytearray(rom)
    where = {}
    tail = TAIL[0]
    for a, b in SPANS:
        out[a:b] = bytes(b - a)
    cur = {a: a for a, b in SPANS}
    for off in sorted(cs):
        c = cs[off]
        data = new.get(off, c["data"])
        assert len(data) == len(c["data"]), hex(off)
        if not c["mio0"]:
            out[off:off + len(data)] = data
            continue
        comp = compress(data)
        n = (len(comp) + 15) & ~15
        span = next(((a, b) for a, b in SPANS if a <= off < b), None)
        if span and cur[span[0]] + n <= span[1]:
            at = cur[span[0]]
            cur[span[0]] += n
        elif not span and n <= c["slot"]:
            at = off
            out[off:off + c["slot"]] = bytes(c["slot"])
        else:
            assert tail + n <= TAIL[1], "ROM tail full"
            at = tail
            tail += n
            if not span:
                out[off:off + c["slot"]] = bytes(c["slot"])
        out[at:at + n] = comp.ljust(n, bytes(1))
        where[off] = (at, at + n)
    o = layout.TABLES[0]
    patched = 0
    while o < layout.TABLES[1]:
        st, en, flag, dest = struct.unpack_from(">4I", rom, o)
        if st in where and 0 < flag <= 12 and st < en <= 0x40B530:
            struct.pack_into(">II", out, o, *where[st])
            patched += 1
            o += 16
        else:
            o += 4
    crom.finalize_crc(out)
    return bytes(out), dict(blocks=len(where), patched=patched, tail_used=tail - TAIL[0],
                            free=[b - cur[a] for a, b in SPANS])
