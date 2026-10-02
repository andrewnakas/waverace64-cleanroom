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

- 19:10 The system stopped my background dev server and retail walk-throughs (PC critically low on memory) and
  told me not to restart them unasked. Everything since is offline work; **no browser check has been run on the
  current clean ROM**.
- 20:00 Code-loaded art found offline instead: the asset segment and the menu containers store each image after an
  end-of-list marker, so an unknown run between markers is exactly one image. `guess.py` finds format + width
  (row repeat, 8-byte padding), `layout_overrides.json` corrects by hand, the run-time trace overrides both when
  it has seen the texture. Unknown container bytes: 1.88 MB -> 8 KB (plus 266 KB of course path data, kept as geometry).
- 20:30 Label words read with Windows OCR in the dirty room (`text_labels.json`, 190 labels), re-typeset by `drawn.py`.
- Announcer: 155 lines found by speech recognition on the retail clips (dirty room), words in `voice_lines.json`,
  placeholders by Piper TTS (`voices.py build`), practice pack written.

## Works
- ROM map: 143 containers (129 MIO0 + raw), 84 scene load tables, segment map.
- Texture spec: 2042+ textures and ~150 palettes (static display lists + run-time trace + frame arrays + guessed
  single images). Regeneration from colour grid + 2-bit alpha, palettes rebuilt, MIO0 re-compression, clean image builder.
- Text labels re-typeset (menus, course names, messages, tutorial lines).
- Audio: all 309 samples resynthesised from outlines, own codebooks and loop states; 155 announcer lines = TTS placeholders.
- **Taint: 0 failing of 5717 streams** (current clean ROM, labels re-typeset, 21:00).
- Earlier clean ROM booted to title, menus and a race in headless Edge (EmulatorJS). The current one is unverified.

## BLOCKED (needs the user)
- **Browser checks are paused.** To verify the current clean ROM (boot, menus readable, race) and to finish the
  run-time trace I need the dev server on port 8163 and one headless Edge. Say "restart the browser checks" (or
  start Claude Code with `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP=1`). Until verified, nothing is published.

## Next
- Verify the clean ROM in the browser, then publish `andrewnakas/waverace64-cleanroom` + Pages.
- Trace walks (championship, time trials, stunt, 2P, options, results) to confirm guessed sizes and find CI palettes.
- Pictures: title logo, rider portraits, watercraft icons, FINISH / LOST / WON / RETIRE / 1st-4th banners, HUD digits
  (currently colour-grid blur): draw briefs.
- 8 KB of small unknown gaps and the main code segment's data section: check for pixels.
- Check the A button in menus on the clean build (earlier wall-clock runs lost presses; probably timing).

## For the morning
- **Record the announcer**: practice pack at `D:/n64work/waverace64/practice/` (`practice_announcer_call_and_response.wav`,
  16 min, 155 lines, `SCRIPT.txt`). One voice: the race announcer. Takes go through the voice kit as usual.
- Decide about the browser checks (see BLOCKED).
