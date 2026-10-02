"""Dev (dirty room): scripted walk through the retail game with a screenshot + RAM dump after every step.

    python -m games.waverace64.walk <name> "<steps>" [--rom clean.z64] [--noram]

Steps (space separated): S start, A, B, Z, R, U/D/L/RT stick, each optionally with hold seconds (A20 = hold A 20 s,
dumping every 6 s), W<n> wait n seconds. The title is reached with the first S at 22 s.
"""
import subprocess
import sys

from games.waverace64 import sheet

W = "D:/n64work/waverace64"
CTR, FPS = 0xD4B00, 30          # D_800D4B00: game frame counter
PAD = {"S": 3, "A": 0, "B": 1, "Z": 12, "R": 11, "U": 19, "D": 18, "L": 17, "RT": 16}


def main(argv):
    name, steps = argv[1], argv[2].split()
    rom = argv[argv.index("--rom") + 1] if "--rom" in argv else "retail.z64"
    ram = "--noram" not in argv
    import json
    steps_js = [[-1, 0, int(argv[argv.index("--lead") + 1]) if "--lead" in argv else 500]]      # boot -> title
    for s in steps:
        k = "RT" if s.startswith("RT") else s[0]
        n = float(s[len(k):] or 0)
        if k == "W":
            steps_js.append([-1, 0, int(n * FPS)])
        elif n > 6:                                          # long hold: a snap every 5 s of it
            for _ in range(int(n // 5)):
                steps_js.append([PAD[k], 5 * FPS, 0])
        else:
            steps_js.append([PAD[k], int(n * FPS) or 8, 100])
    cmd = [sys.executable, "ports/ejs/cdp_shot.py", f"{W}/shots/{name}", "--url", f"http://localhost:8163/index.html?rom={rom}",
           "--gpu", "--port", "9363", "--drive", json.dumps(steps_js), "--ctr", hex(CTR), "--rom", f"{W}/baserom.us.rev1.z64"]
    if not ram:
        cmd += ["--noram"]
    subprocess.run(cmd, check=True)
    sheet.main(["", f"{W}/shots/{name}", "6"])
    if ram and rom == "retail.z64":
        out = subprocess.run([sys.executable, "-m", "games.waverace64.trace", f"{W}/baserom.us.rev1.z64", f"{W}/shots/{name}"],
                             capture_output=True, text=True).stdout.strip().splitlines()
        print(out[-1] if out else "trace: no output")
        import glob
        import os
        for f in glob.glob(f"{W}/shots/{name}/ram_*.bin"):          # 4 MB each: keep the disk free
            os.remove(f)


if __name__ == "__main__":
    main(sys.argv)
