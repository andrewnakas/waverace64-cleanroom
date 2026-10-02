# Wave Race 64 clean room: status

**Not published yet.** The clean ROM boots and plays in the browser, but menus / fonts / HUD / title logo are still
retail pixels (textures the game loads from code). Publishing waits for those and for taint = 0 failing.

## Decisions (logged as made)
- 2026-10-01 16:05 ROM found at `D:/Wave Race 64 - Kawasaki Jet Ski (USA) (Rev 1).zip` (user pointed to D:). sha1 `508dfc2d…7966a`
  = exactly the decomp's target (US Rev 1 / V1.1). Unpacked to `D:/n64work/waverace64/baserom.us.rev1.z64`.
- Decomp: LLONSIT/Wave-Race-64, LF clone at `D:/n64work/waverace64/pristine`. Its Makefile refuses native Windows
  (needs Linux, IDO recomp, mips binutils) and it keeps **all assets as `bin` blobs** (129 MIO0 blocks + raw segments +
  audio ctl/tbl/seq); only splat offsets are documented.
- **Web route = 3: clean ROM + WASM N64 emulator** (EmulatorJS 4.2.3 + mupen64plus_next/GLideN64, `ports/ejs`, same as
  DK64/Conker/BK). Why: no PC port of Wave Race 64 exists; the decomp is partial and has no web target.
- **Clean ROM = "clean image"**: copy of the ROM with code kept (the decomp's code is the same bytes) and every
  asset region regenerated and patched in at its known offset (MIO0 blocks re-compressed, load tables re-pointed,
  CRC recomputed). Taint scan proves only spec regions differ and no retail pixels/samples remain.
- Core ROM-DB slot: "Wave Race 64 (U) (V1.0) [t1]" (RefMD5 = US, EEPROM 4 KB) is pointed at our ROM's MD5 (`ports/ejs/patch_core.py`).
- Dev server port 8163, CDP port 9363.
- 17:45 **Texture discovery = static display lists + run-time trace + frame-array extension.** The static scan finds
  ~1420 textures (40 % of container bytes) but nothing the code loads itself (fonts, menus, HUD, logo). `trace.py`
  reads RDRAM dumps of the running retail game (dev only), scans the frame's display lists and maps every load back to
  (container, offset, format, size). `layout.extend` fills glyph / animation arrays next to a known texture.
  Rejected: guessing formats from byte statistics alone (gaps are several images back to back; too many wrong guesses).
- 18:40 Headless input is timed by the game's own frame counter (`D_800D4B00`), not wall time: the emulator's speed
  changes with machine load and wall-timed presses were lost (`cdp_shot.py --drive`, `walk.py`).

## Works
- ROM map: 143 containers (129 MIO0 + raw), 84 scene load tables, segment map.
- Texture spec + regeneration (colour grid + 2-bit alpha), palettes rebuilt, MIO0 re-compression, clean image builder.
- Audio: all samples resynthesised from outlines, own codebooks (same predictor count) and loop states.
- Clean ROM boots to title, menus and a race in headless Edge (EmulatorJS).

## Next
- Finish the trace walks (all menus, options, each mode, results), then look at what is still unknown
  (`gapsheet.py`, dirty contact sheets) and add overrides for the rest.
- Re-typeset text textures (menus, HUD, fonts), draw rider portraits / watercraft icons / title logo.
- Taint 0 failing, then publish `andrewnakas/waverace64-cleanroom` + Pages.
- Voices (announcer): Piper placeholders + practice pack `D:/n64work/waverace64/practice/`.
- Check: in headless runs the A button did not always confirm menu items (Start did). Verify on the clean build.

## For the morning
- (nothing to record yet; practice pack not built)
