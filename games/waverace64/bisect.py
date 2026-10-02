"""Dev: find the containers whose regenerated textures hang the boot.  python -m games.waverace64.bisect"""
import json
import os
import subprocess
import sys

W = "D:/n64work/waverace64"
HERE = os.path.dirname(os.path.abspath(__file__))
N = [0]


def hangs(cs):
    N[0] += 1
    env = dict(os.environ, WR_NOAUDIO="1", WR_ONLY=",".join("%X" % c for c in cs) or "-", CDP_MUTE="1")
    subprocess.run([sys.executable, "-m", "games.waverace64.generate", f"{W}/baserom.us.rev1.z64", f"{W}/devsite/bis.z64"],
                   env=env, capture_output=True, check=True)
    out = subprocess.run([sys.executable, "-m", "games.waverace64.bootcheck", "bis.z64"], env=env, capture_output=True, text=True).stdout
    r = "HANG" in out
    print(f"test {N[0]}: {len(cs)} containers {'%X..%X' % (cs[0], cs[-1]) if cs else ''} -> {'HANG' if r else 'boot'}", flush=True)
    return r


def main():
    """ddmin: smallest set of containers that still hangs (hangs can need several containers together)."""
    spec = json.load(open(os.path.join(HERE, "spec", "textures.json")))
    cur = sorted({t["c"] for t in spec})
    n = 2
    while len(cur) >= 2:
        k = max(1, len(cur) // n)
        parts = [cur[i:i + k] for i in range(0, len(cur), k)]
        for p in parts:                                  # a part alone, then a complement
            if hangs(p):
                cur, n = p, 2
                break
        else:
            for p in parts:
                rest = [c for c in cur if c not in p]
                if len(parts) > 2 and hangs(rest):
                    cur, n = rest, max(n - 1, 2)
                    break
            else:
                if n >= len(cur):
                    break
                n = min(len(cur), n * 2)
        print("now", len(cur), " ".join("%X" % c for c in cur)[:300], flush=True)
    print("RESULT minimal hanging set:", " ".join("%X" % c for c in cur))


main()
