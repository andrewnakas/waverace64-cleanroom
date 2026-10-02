"""Dirty room: find the spoken samples and what they say (speech recognition on the retail clips).

    python -m games.waverace64.voice_spec <retail.z64>     -> dirty/voice/<key>.wav, dirty/voice_asr.json, one line per clip

The clips stay in the dirty tree (practice pack source, never published). Only the words go to voice_lines.json,
after a look by hand.
"""
import json
import os
import sys
import wave

import numpy as np

from games.waverace64 import audio, layout

BANKS = ("06D5C0", "2034A0", "2DBA30", "2A99B0")


def main(argv):
    rom = open(argv[1], "rb").read()
    out = layout.W + "voice"
    os.makedirs(out, exist_ok=True)
    from faster_whisper import WhisperModel
    model = WhisperModel("small.en", device="cpu", compute_type="int8", cpu_threads=3)
    res = {}
    for k, s in sorted(audio.parse(rom).items()):
        name = audio.name(k)
        if name.split("_")[0] not in BANKS or s["loop"][2]:
            continue
        pcm = np.asarray(audio.retail_pcm(rom, k, s), np.int16)
        rate = int(round(32000.0 * max(s["tun"])))
        if len(pcm) / rate < 0.35:
            continue
        p = os.path.join(out, name + ".wav")
        with wave.open(p, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm.astype("<i2").tobytes())
        segs, _ = model.transcribe(p, language="en", beam_size=5, condition_on_previous_text=False)
        segs = list(segs)
        text = " ".join(x.text.strip() for x in segs)
        conf = float(np.mean([x.avg_logprob for x in segs])) if segs else -9
        res[name] = dict(text=text, secs=round(len(pcm) / rate, 2), rate=rate, conf=round(conf, 2), nospeech=round(float(np.mean([x.no_speech_prob for x in segs])) if segs else 1, 2))
        print(f"{name} {len(pcm) / rate:4.1f}s {conf:5.2f} {text[:70]}")
    json.dump(res, open(layout.W + "voice_asr.json", "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv)
