"""Dirty room: format + width of a single texture whose byte length is known (no display list names it).

The uncompressed asset segment and the menu containers store each image after an end-of-list marker, so an
unknown run between markers is exactly one image: only (format, width) have to be found. Width = the row length
at which texels repeat best; texel size from byte statistics. `layout_overrides.json` corrects wrong guesses.
"""
import numpy as np

RGBA, CI, IA, I = 0, 2, 3, 4


def lagdiff(x, k):
    return float(np.abs(x[k:] - x[:-k]).mean()) if len(x) > k + 4 else 1e9


def width(x, n_tex, nbytes):
    """Best row width (in texels) among the divisors of the texel count."""
    if x.std() < 0.5:
        w = 1 << (int(np.log2(max(1, n_tex))) + 1) // 2
        while n_tex % w:
            w //= 2
        return max(w, 1), 9.0
    cands = {}
    per = max(1, int(round(8 * n_tex / max(1, nbytes))))          # texels per byte
    for w in range(4, min(641, n_tex // 2 + 1)):
        h = n_tex // w
        if h < (6 if n_tex >= 96 else 2) or h > 1024 or w > 40 * h or n_tex - w * h >= 8 * per:           # images are padded to 8 bytes
            continue
        ks = [k for k in (w - 3, w - 2, w + 2, w + 3) if 0 < k < len(x) - 4]
        around = np.median([lagdiff(x, k) for k in ks]) + 1e-3
        s = (lagdiff(x, w) + 0.02 * x.std()) / around
        if w % 4:
            s *= 1.3
        elif w % 8 and per == 1:                                   # 8-bit rows are whole 8-byte words here
            s *= 1.5
        if n_tex != w * h:
            s *= 1.05
        cands[w] = (s, h)
    if not cands:
        return max(1, int(np.sqrt(n_tex))), 9.0
    w = min(cands, key=lambda k: cands[k][0])
    best = cands[w][0]
    alts = [k for k in (w, w * 2, w * 4, w // 2, w // 4) if k in cands and cands[k][0] <= best * 1.25 + 0.02]   # rows also repeat at 2w, w/2
    w = min(alts, key=lambda k: abs(np.log2(k / cands[k][1]) - 0.5))
    return w, cands[w][0]


def guess(b):
    """-> dict(fmt, siz, w, h, score). len(b) must be the whole image."""
    a = np.frombuffer(b, np.uint8).astype(np.float32)
    n = len(a)
    l1, l2, l4 = lagdiff(a, 1), lagdiff(a, 2), lagdiff(a, 4)
    raw = np.frombuffer(b, np.uint8)
    if n % 4 == 0 and l4 < 0.55 * l2 and l4 < 0.55 * l1 and n >= 256:
        x = a.reshape(-1, 4)[:, :3].mean(1)
        w, s = width(x, n // 4, n)
        return dict(fmt=RGBA, siz=3, w=w, h=n // 4 // w, score=s)
    opaque16 = n % 2 == 0 and float((raw[1::2] & 1).mean()) > 0.93 and 0.15 < float((raw[0::2] & 1).mean()) < 0.85
    if n % 2 == 0 and (l2 < 0.7 * l1 or opaque16):
        u = raw.reshape(-1, 2).astype(np.uint16)
        lo = raw[1::2]
        ia = not opaque16 and float(np.isin(lo, (0, 255)).mean()) > 0.6 or not opaque16 and lagdiff(lo.astype(np.float32), 1) < 0.5 * lagdiff((lo & 1).astype(np.float32) * 255, 1)
        v = (u[:, 0] << 8) | u[:, 1]
        x = (((v >> 11) & 31) + ((v >> 6) & 31) + ((v >> 1) & 31)).astype(np.float32) if not ia else u[:, 0].astype(np.float32)
        w, s = width(x, n // 2, n)
        return dict(fmt=IA if ia else RGBA, siz=2, w=w, h=n // 2 // w, score=s)
    hi, lo = (raw >> 4).astype(np.float32), (raw & 15).astype(np.float32)
    nib = np.empty(n * 2, np.float32)
    nib[0::2], nib[1::2] = hi, lo
    d_n, d_hi, d_lo = lagdiff(nib, 1), lagdiff(hi, 1), lagdiff(lo, 1)
    if d_n < 0.8 * min(d_hi, d_lo) + 0.05 and hi.std() > 0.3:
        w, s = width(nib, n * 2, n)
        return dict(fmt=I, siz=0, w=w, h=n * 2 // w, score=s)
    w, s = width(a, n, n)
    smooth_planes = d_hi + d_lo < 0.75 * (l1 / 8 + 0.2) * 16 and lo.std() > 0.3
    ia8 = hi.std() < 0.3 or (smooth_planes and abs(float(np.corrcoef(hi, lo)[0, 1])) < 0.9)
    return dict(fmt=IA if ia8 else I, siz=1, w=w, h=n // w, score=s)
