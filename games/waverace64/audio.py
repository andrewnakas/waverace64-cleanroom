"""Sound banks (SM64-style ctl/tbl): kept facts and regeneration.

    python -m games.waverace64.audio spec <retail.z64>     dirty room -> spec/samples.json
    (generate.py calls regenerate())

Kept per sample (user scope): length, rate, loop points, coarse spectral outline (cleanroom.audio.descriptor),
median pitch. Everything audible is resynthesised from that outline, encoded with our own VADPCM codebooks
(same predictor count, so the bank layout and pool sizes are unchanged) and our own loop states.
Instrument tables, envelopes, tunings and the note sequences are kept as they are.
"""
import hashlib
import json
import os
import pickle
import struct
import sys

import numpy as np

from cleanroom.audio import descriptor, vadpcm
from cleanroom.audio.pitch import median_f0

HERE = os.path.dirname(os.path.abspath(__file__))
CTL, TBL, SEQ = 0x40B530, 0x428C30, 0x7AE8B0
CACHE = "D:/n64work/waverace64/build/audio_cache.pkl"
PRED = {2: [(1.0, 0.0), (1.8, -0.82)], 4: vadpcm.PREDICTORS}


def parse(rom):
    """-> {(tbl bank offset, sample addr): dict(size, tunings, books=[rom offsets], loops=[rom offsets], npred, loop)}"""
    n = struct.unpack_from(">H", rom, CTL + 2)[0]
    ents = [struct.unpack_from(">II", rom, CTL + 4 + 8 * i) for i in range(n)]
    tents = [struct.unpack_from(">II", rom, TBL + 4 + 8 * i) for i in range(n)]
    out = {}
    for bi, (off, ln) in enumerate(ents):
        base = CTL + off
        ninst, ndrum = struct.unpack_from(">II", rom, base)
        d = base + 16
        drumptr = struct.unpack_from(">I", rom, d)[0]
        snds = []
        for i in range(ninst):
            ip = struct.unpack_from(">I", rom, d + 4 + 4 * i)[0]
            if ip:
                for k in (8, 16, 24):
                    sp, tun = struct.unpack_from(">If", rom, d + ip + k)
                    if sp:
                        snds.append((sp, tun))
        if ndrum and drumptr:
            for i in range(ndrum):
                dp = struct.unpack_from(">I", rom, d + drumptr + 4 * i)[0]
                if dp:
                    sp, tun = struct.unpack_from(">If", rom, d + dp + 4)
                    if sp:
                        snds.append((sp, tun))
        for sp, tun in snds:
            zero, addr, loop, book, size = struct.unpack_from(">5I", rom, d + sp)
            order, npred = struct.unpack_from(">ii", rom, d + book)
            ls, le, lc = struct.unpack_from(">IIi", rom, d + loop)
            s = out.setdefault((tents[bi][0], addr), dict(size=size, tun=[], books=[], loops=[], npred=npred, order=order, loop=[ls, le, lc]))
            assert s["size"] == size and s["npred"] == npred and s["loop"] == [ls, le, lc], (bi, hex(addr))
            if round(tun, 4) not in s["tun"]:
                s["tun"].append(round(tun, 4))
            if d + book not in s["books"]:
                s["books"].append(d + book)
            if d + loop not in s["loops"]:
                s["loops"].append(d + loop)
    return out


def name(k):
    return f"{k[0]:06X}_{k[1]:06X}"


def retail_pcm(rom, k, s):
    o = s["books"][0]
    book = dict(order=s["order"], npred=s["npred"],
                book=list(struct.unpack_from(">%dh" % (16 * s["npred"]), rom, o + 8)))
    a = TBL + k[0] + k[1]
    nfr = s["size"] // 9
    return vadpcm.decode(rom[a:a + nfr * 9], book, nfr * 16)


def spec_main(rom_path):
    rom = open(rom_path, "rb").read()
    smp = parse(rom)
    out = {}
    for k, s in sorted(smp.items()):
        pcm = np.asarray(retail_pcm(rom, k, s), np.float64)
        rate = 32000.0 * max(s["tun"])
        d = dict(size=s["size"], nframes=len(pcm), rate=rate, npred=s["npred"], loop=s["loop"], desc=descriptor.describe(pcm, rate))
        f0 = median_f0((pcm / 32768).astype(np.float32), rate)
        if f0:
            d["f0"] = round(f0, 1)
        out[name(k)] = d
    json.dump(out, open(os.path.join(HERE, "spec", "samples.json"), "w"), separators=(",", ":"))
    secs = sum(d["nframes"] / d["rate"] for d in out.values())
    print(f"spec: {len(out)} samples, {sum(d['size'] for d in out.values())} bytes, {secs:.0f} s of sound, looped {sum(1 for d in out.values() if d['loop'][2])}")


def waveform(key, d, supplied=None):
    n, rate = d["nframes"], d["rate"]
    seed = int.from_bytes(hashlib.sha1(("smp/" + key).encode()).digest()[:4], "little")
    x = supplied if supplied is not None else descriptor.synthesize(d["desc"], n, rate, seed=seed)
    x = np.asarray(x, np.float32)[:n]
    x = np.pad(x, (0, n - len(x)))
    ls, le, lc = d["loop"]
    if lc and supplied is None and le > ls + 32 and le <= n:
        x = descriptor.make_loop_seamless(x, ls, le)
    dither = np.random.default_rng(seed ^ 0x5A5A).integers(-1, 2, n)
    return np.clip(np.round(np.clip(x, -1, 1) * 32000) + dither, -32768, 32767).astype(np.int16)


def supplied_voices():
    """{sample key: float waveform} from games/waverace64/voices/*.wav (TTS placeholders or the user's takes)."""
    out = {}
    vd = os.path.join(HERE, "voices")
    if os.path.isdir(vd):
        import wave
        for f in os.listdir(vd):
            if f.endswith(".wav"):
                with wave.open(os.path.join(vd, f)) as w:
                    out[f[:-4]] = (np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768, w.getframerate())
    return out


def fit(x, rate, d):
    """Resample a supplied take to the slot's rate and length."""
    from scipy.signal import resample_poly
    from math import gcd
    a, b = int(round(d["rate"])), int(rate)
    g = gcd(a, b)
    y = resample_poly(x, a // g, b // g) if a != b else x
    n = d["nframes"]
    if len(y) > n:                               # too long: speed up to fit (keeps the whole word)
        y = resample_poly(y, n, len(y))
    y = np.pad(y[:n], (0, max(0, n - len(y))))
    peak = np.abs(y).max()
    return (y / peak * 0.85).astype(np.float32) if peak > 0 else y


def encode_all(spec):
    try:
        cache = pickle.load(open(CACHE, "rb"))
    except Exception:
        cache = {}
    voices = supplied_voices()
    out, dirty = {}, False
    for key, d in spec.items():
        v = voices.get(key)
        h = hashlib.sha1((json.dumps(d, sort_keys=True) + (hashlib.sha1(v[0].tobytes()).hexdigest() if v else "")).encode()).hexdigest()
        if key in cache and cache[key][0] == h:
            out[key] = cache[key][1:]
            continue
        pcm = waveform(key, d, fit(v[0], v[1], d) if v else None)
        book = vadpcm.make_book(PRED[d["npred"]])
        data, _, dec = vadpcm.encode(pcm, book)
        fs = d["loop"][0] & ~15
        state = [int(x) for x in dec[fs - 16:fs]] if d["loop"][2] and fs >= 16 else [0] * 16
        cache[key] = (h, data, book["book"], state)
        out[key] = cache[key][1:]
        dirty = True
    if dirty:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        pickle.dump(cache, open(CACHE, "wb"))
    return out, len(voices)


def regenerate(rom):
    spec = json.load(open(os.path.join(HERE, "spec", "samples.json")))
    smp = parse(rom)
    assert {name(k) for k in smp} == set(spec), "sample set changed"
    enc, nvoice = encode_all(spec)
    out = bytearray(rom)
    lo, hi = min(e[0] for e in _tbl_entries(rom)), TBL + max(e[0] + e[1] for e in _tbl_entries(rom))
    out[TBL + lo:hi] = bytes(hi - TBL - lo)                 # nothing of the retail sample area survives
    for k, s in smp.items():
        data, book, state = enc[name(k)]
        a = TBL + k[0] + k[1]
        n = s["size"] // 9 * 9
        out[a:a + n] = data[:n]
        for b in s["books"]:
            struct.pack_into(">%dh" % len(book), out, b + 8, *book)
        if s["loop"][2]:
            for l in s["loops"]:
                struct.pack_into(">16h", out, l + 16, *state)
    return bytes(out), dict(samples=len(smp), voices=nvoice)


def _tbl_entries(rom):
    n = struct.unpack_from(">H", rom, TBL + 2)[0]
    return [struct.unpack_from(">II", rom, TBL + 4 + 8 * i) for i in range(n)]


if __name__ == "__main__":
    if sys.argv[1] == "spec":
        spec_main(sys.argv[2])
