"""Announcer voice: placeholder TTS and the practice pack.

    python -m games.waverace64.voices build [key ...]     Piper placeholders -> games/waverace64/voices/<key>.wav
    python -m games.waverace64.voices practice             D:/n64work/waverace64/practice (PERSONAL: retail clips, never published)

The placeholders are our own TTS performance of the words (no cloning, nothing trained on the game's audio).
The practice pack is the standard layout the voice kit reads: clip, 0.3 s, 80 ms 880 Hz beep, gap 1.5x + 1.5 s.
"""
import json
import os
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["CLEANROOM_GAME"] = HERE
from cleanroom.voice import voices as vv      # noqa: E402

vv._name = lambda p: os.path.basename(p)      # sample keys have no extension
vv.TAKES = 2                                  # placeholders: do not spend long
DIRTY = "D:/n64work/waverace64/dirty/voice"
OUT = "D:/n64work/waverace64/practice"
HZ = 22050


def practice():
    S = json.load(open(os.path.join(HERE, "spec", "samples.json")))
    L = [(k, v) for k, v in json.load(open(os.path.join(HERE, "voice_lines.json"))).items() if not k.startswith("_")]
    os.makedirs(os.path.join(OUT, "clips"), exist_ok=True)

    def load(k):
        with wave.open(os.path.join(DIRTY, k + ".wav")) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
            sr = w.getframerate()
        return np.interp(np.arange(0, len(x) * HZ / sr) * sr / HZ, np.arange(len(x)), x).astype(np.float32)

    def wr(path, x):
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(HZ)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())

    beep = (0.2 * np.sin(2 * np.pi * 880 * np.arange(int(0.08 * HZ)) / HZ)).astype(np.float32)
    tracks, lines = {}, ["Voice practice script: record in this order, 2-3 takes each, in character.",
                         "Play practice_<character>_call_and_response.wav and speak after each beep.", ""]
    who = None
    for i, (k, v) in enumerate(L, 1):
        if v["who"] != who:
            who = v["who"]
            lines.append(f"== {who}")
        x = load(k)
        wr(os.path.join(OUT, "clips", f"{i:03d}_{k}.wav"), x)
        gap = np.zeros(int((len(x) / HZ * 1.5 + 1.5) * HZ), np.float32)
        tracks.setdefault(who, []).extend([x, np.zeros(int(0.3 * HZ), np.float32), beep, gap])
        lines.append(f"{i:03d}  {k:16s} max {S[k]['nframes'] / S[k]['rate']:.1f}s  \"{v['text']}\"")
    for w_, parts in tracks.items():
        wr(os.path.join(OUT, f"practice_{w_}_call_and_response.wav"), np.concatenate(parts))
    lines += ["", "These clips come from your own ROM: practice only, do not share or commit them."]
    open(os.path.join(OUT, "SCRIPT.txt"), "w", encoding="utf8").write("\n".join(lines))
    mins = sum(len(np.concatenate(p)) for p in tracks.values()) / HZ / 60
    print(f"practice pack: {len(L)} clips, tracks {sorted(tracks)}, {mins:.0f} min -> {OUT}")


if __name__ == "__main__":
    if sys.argv[1] == "practice":
        practice()
    else:
        vv.build(sys.argv[2:] or None)
