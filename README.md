# Wave Race 64: clean-room web build

Play: https://andrewnakas.github.io/waverace64-cleanroom/

The game program runs in the browser (EmulatorJS + mupen64plus-next) from a ROM image in which **every art and
sound asset has been regenerated** from coarse facts: texture format, size, a 4x4 colour grid and 2-bit alpha;
sample length, rate, loop points and a coarse outline; note sequences. Text inside pictures is re-typeset, the
announcer is a text-to-speech placeholder. No retail pixels or samples are in the published files (checked by a
taint scan: 0 failing streams). Asset layout from the [LLONSIT/Wave-Race-64](https://github.com/LLONSIT/Wave-Race-64) decomp.

Controls: arrows / left stick = steer, X = A (throttle), C = B, Z = Z, Enter = Start. Gamepads work.

- `games/waverace64/`: the game module (layout, spec extraction, regeneration, taint scan).
- `cleanroom/`: shared library. `ports/ejs/`: web page and site builder.
- `STATUS.md`: what works and what is still rough.

You need your own ROM to rebuild; no ROM is in this repository.
