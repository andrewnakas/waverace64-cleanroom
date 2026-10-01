"""Dev: one contact sheet from a shots directory.  python -m games.waverace64.sheet <dir> [cols]"""
import glob
import os
import sys

from PIL import Image


def main(argv):
    d = argv[1]
    cols = int(argv[2]) if len(argv) > 2 else 4
    fs = sorted(glob.glob(os.path.join(d, "shot_*.png")), key=lambda f: float(os.path.basename(f)[5:-4]))
    ims = [Image.open(f).convert("RGB").crop((0, 0, 960, 640)).resize((480, 320)) for f in fs]
    rows = (len(ims) + cols - 1) // cols
    s = Image.new("RGB", (480 * cols, 320 * rows))
    for i, im in enumerate(ims):
        s.paste(im, (480 * (i % cols), 320 * (i // cols)))
    s.save(os.path.join(d, "sheet.png"))
    print(len(ims), "shots ->", os.path.join(d, "sheet.png"))


if __name__ == "__main__":
    main(sys.argv)
