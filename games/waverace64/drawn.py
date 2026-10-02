"""Textures a coarse colour grid cannot carry: text (re-typeset with our stroke font).

`hook(t)` is called by generate.py for every texture record; it returns an RGBA image or None (= default
regeneration from the kept grid). Words come from text_labels.json (the game's own menu text).
"""
import json
import os

import numpy as np

from cleanroom.gfx import strokefont

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = {k: v for k, v in json.load(open(os.path.join(HERE, "text_labels.json"))).items() if not k.startswith("_")}


def _squeeze(line, w):
    if line.shape[1] <= w:
        return line
    xs = np.linspace(0, line.shape[1] - 1, w)
    x0 = np.floor(xs).astype(int)
    x1 = np.minimum(x0 + 1, line.shape[1] - 1)
    f = (xs - x0)[None, :]
    return line[:, x0] * (1 - f) + line[:, x1] * f


def text_mask(lines, w, h, align="center"):
    """(h, w) coverage 0..1: the lines stacked, each as tall as its row allows, squeezed to the width."""
    m = np.zeros((h, w), np.float32)
    rows = len(lines)
    rh = h / rows
    th = min(20, max(5, int(rh) - (2 if rh >= 9 else 1)))        # glyph height: leave a pixel of air; message boxes stay text-sized
    for i, s in enumerate(lines):
        line = strokefont.render_line(s, th, thickness=max(1.0, th / 7.5))
        line = _squeeze(line, w - 2)
        y = int(round(i * rh + (rh - th) / 2))
        x = (w - line.shape[1]) // 2 if align == "center" else 1
        y = max(0, min(h - th, y))
        m[y:y + th, x:x + line.shape[1]] = np.maximum(m[y:y + th, x:x + line.shape[1]], line[:h - y])
    return np.clip(m, 0, 1)


def label(t, lab):
    w, h = t["w"], t["h"]
    m = text_mask(lab["lines"], w, h, lab.get("align", "center" if len(lab["lines"]) > 1 or h >= 14 else "left"))
    img = np.zeros((h, w, 4), np.float32)
    if t["fmt"] == 4:                                             # intensity only: ink = brightness
        img[..., :3] = (m * 255)[..., None]
        img[..., 3] = 255
    else:                                                         # IA / RGBA: white ink, alpha = coverage
        img[..., :3] = 255
        img[..., 3] = m * 255
    return img.astype(np.uint8)


def banner(t, lab):
    """Big coloured words (FINISH!, WON, 1st...): our lettering, filled with the kept colour grid, dark rim."""
    from scipy.ndimage import binary_dilation
    from cleanroom.decomp import gen
    w, h = t["w"], t["h"]
    rows = len(lab["lines"])
    rh = h // rows
    m = np.zeros((h, w), np.float32)
    for i, s in enumerate(lab["lines"]):
        th = rh - 6
        line = _squeeze(strokefont.render_line(s, th, thickness=max(1.6, th / 8.5)), w - 6)
        x, y = (w - line.shape[1]) // 2, i * rh + 3
        m[y:y + th, x:x + line.shape[1]] = line
    base = np.asarray(gen.from_digest(f"{t['c']:X}_{t['o']:X}", t)).astype(np.float32)
    rgb = base[..., :3]
    lit = rgb / (rgb.max(-1, keepdims=True) + 1) * 255                       # the grid's hue at full brightness
    shade = np.linspace(1.0, 0.7, rh)[np.arange(h) % rh][:, None, None]      # lighter at the top of each word
    rim = binary_dilation(m > 0.4, iterations=1)
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = np.where((m > 0.4)[..., None], lit * shade, 20)
    img[..., 3] = np.where(rim, 255, 0)
    return img.astype(np.uint8)


def glyphs(t, lab):
    """A column of font cells (HUD font): one bold stroke glyph per cell, centred. IA: white ink, alpha = coverage."""
    w, h, ch = t["w"], t["h"], lab["cell"]
    m = np.zeros((h, w), np.float32)
    for i, c in enumerate(lab["chars"]):
        if (i + 1) * ch > h:
            break
        gh = ch - 3
        if c in "'\"":
            g = strokefont.render_line(c, gh, thickness=gh / 8.0)
        elif c in ".-":
            g = strokefont.render_line(c, gh, thickness=gh / 7.0)
        else:
            g = strokefont.render_line(c, gh, thickness=gh / 8.0)
        g = _squeeze(g, w - 2)
        x = (w - g.shape[1]) // 2
        m[i * ch + 1:i * ch + 1 + gh, x:x + g.shape[1]] = g
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = 255
    img[..., 3] = np.clip(m, 0, 1) * 255
    return img.astype(np.uint8)


# Pictures stored as stacks of strips, drawn by us as one image and cut into the strips.
# container -> (first offset, strip bytes, strips, painter)
def _title_logo(w, h):
    """Our own badge: gold oval, dark rim, a big red 64 behind WAVE RACE in sea-blue letters with a navy edge."""
    from scipy.ndimage import binary_dilation
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = ((xx - w / 2 + 0.5) / (w / 2 - 3)) ** 2 + ((yy - h / 2 + 0.5) / (h / 2 - 3)) ** 2
    img = np.zeros((h, w, 4), np.float32)
    inside, rim = r <= 1.0, (r <= 1.0) & (r > 0.86)
    gold = np.stack([205 - 40 * yy / h, 165 - 35 * yy / h, 95 - 20 * yy / h], -1) + (np.sin(yy / 2.3) * 6)[..., None]
    img[..., :3] = np.where(inside[..., None], gold, 0)
    img[rim, :3] = (95, 35, 22)
    img[..., 3] = inside * 255

    def put(text, th, thick, y, colour, edge=None, maxw=None):
        line = _squeeze(strokefont.render_line(text, th, thickness=thick), maxw or w - 20)
        m = np.zeros((h, w), np.float32)
        x = (w - line.shape[1]) // 2
        m[y:y + th, x:x + line.shape[1]] = line[:h - y]
        if edge is not None:
            e = binary_dilation(m > 0.3, iterations=2)
            img[e, :3] = edge
            img[e, 3] = 255
        k = np.clip(m, 0, 1)[..., None]
        img[..., :3] = img[..., :3] * (1 - k) + np.array(colour, np.float32) * k
        img[..., 3] = np.maximum(img[..., 3], k[..., 0] * 255)

    put("64", int(h * 0.80), h * 0.11, int(h * 0.10), (215, 40, 30), maxw=int(w * 0.40))
    put("WAVE RACE", int(h * 0.36), h * 0.062, int(h * 0.32), (70, 215, 235), edge=(20, 40, 110), maxw=int(w * 0.84))
    return np.clip(img, 0, 255).astype(np.uint8)


def _maker_banner(w, h):
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = (38, 36, 150)
    img[..., 3] = 255
    m = text_mask(["KAWASAKI JET SKI"], w * 2, h // 2)                 # shown twice as wide and half as tall
    m = np.repeat((m[:, 0::2] + m[:, 1::2]) / 2, 2, axis=0)[:h, :w, None]
    img[..., :3] = img[..., :3] * (1 - m) + 255 * m
    return img.astype(np.uint8)


STRIPS = {0x2F9BE0: [(0x6220, 0x1000, 28, _title_logo), (0x20228, 0x540, 7, _maker_banner)]}
_PICS = {}


def strip(t):
    for first, step, count, paint in STRIPS.get(t["c"], ()):
        i, rem = divmod(t["o"] - first, step)
        if rem == 0 and 0 <= i < count:
            key = (t["c"], first)
            if key not in _PICS:
                _PICS[key] = paint(t["w"], t["h"] * count)
            return _PICS[key][i * t["h"]:(i + 1) * t["h"]]
    return None


def hook(t):
    if t["c"] in STRIPS:
        img = strip(t)
        if img is not None:
            return img
    lab = LABELS.get(f"{t['c']:X}+{t['o']:X}")
    if lab and lab.get("style") == "banner" and t["fmt"] == 0:
        return banner(t, lab)
    if lab and lab.get("style") == "glyphs":
        return glyphs(t, lab)
    if lab and t["fmt"] in (3, 4):
        return label(t, lab)
    return None
