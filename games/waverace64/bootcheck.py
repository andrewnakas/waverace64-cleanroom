"""Dev: does a ROM in the dev site boot?  python -m games.waverace64.bootcheck <name.z64> [...]

Serves the dev site, opens each ROM in headless Edge for ~45 s and prints BOOT / HANG (screen at 35 s is not black).
"""
import subprocess
import sys

from PIL import Image

W = "D:/n64work/waverace64"


def main(argv):
    srv = subprocess.Popen([sys.executable, "ports/wasm/serve.py", f"{W}/devsite", "8163"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for rom in argv[1:]:
            out = f"{W}/shots/boot_{rom.split('.')[0]}"
            subprocess.run([sys.executable, "ports/ejs/cdp_shot.py", out, "--url", f"http://localhost:8163/index.html?rom={rom}",
                            "--gpu", "--port", "9363", "--script", "35:shot", "--wait", "50"], capture_output=True)
            try:
                im = Image.open(f"{out}/shot_35.png").convert("L").crop((60, 40, 900, 560))
                lit = sum(1 for v in im.resize((84, 52)).getdata() if v > 40)
                print(f"{rom}: {'BOOT' if lit > 400 else 'HANG'} (lit {lit})", flush=True)
            except OSError:
                print(f"{rom}: no shot", flush=True)
    finally:
        srv.kill()


if __name__ == "__main__":
    main(sys.argv)
