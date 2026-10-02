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


def hook(t):
    lab = LABELS.get(f"{t['c']:X}+{t['o']:X}")
    if lab and t["fmt"] in (3, 4):
        return label(t, lab)
    return None
