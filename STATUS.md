# Wave Race 64 clean room: status

**Published 2026-10-02:** https://andrewnakas.github.io/waverace64-cleanroom/ (repo `andrewnakas/waverace64-cleanroom`).
Boots, menus readable, championship race starts (headless walk `D:/n64work/waverace64/shots/v3/sheet.png`), taint 0 failing of 5655.

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

- 2026-10-02 09:50 New session, user said "go": browser checks resumed (one headless Edge at a time, server only while a check runs).
- 11:50 **Boot hang found and fixed.** The 22:10 clean ROM stopped on frame 3 (divide by zero, `break 7` at 0x8009FDCC):
  8 guessed "images" in course containers were display lists + model pointer tables. Found by RDRAM dump of the hung game
  (thread PC, then the pointer table traced back to container 3E17A0). `layout.structured` now rejects guesses holding
  display-list commands or segment-8 pointer runs. Container bisecting (`bisect.py`) did not find it: it needed two containers.
- 12:15 **Grey shards over every scene fixed**: rider / craft model containers (351260..35FCB0) were guessed as tall images
  (vertex data). `layout.vertices` rejects guesses that are >= 85 % vertex-like records. Spec: 2011 textures, 149 palettes.

- 12:45 Dark polygons in menu backdrops fixed: 13 more records (trace / static scan) were display lists or lit vertices
  (`layout.notimage`, applied to every source; an image followed by a display list keeps its image half). Spec: 1998 textures.
  Walk `shots/v4/sheet.png` (title, menus, watercraft select; timed out before the race, emulator slow), taint 0 failing. Pushed to Pages.

- 13:35 Watercraft select fixed (labels readable, four craft thumbnails shown): `layout.resolve_overlaps` drops records that
  share bytes with another (71 wrong-container trace records in 8 containers). Spec: 1943 textures, 133 palettes. Taint 0 failing,
  walk `shots/v5/sheet.png`. Pushed to Pages.

- 13:50 Title text question closed: "(c) 1996 Nintendo", the trademark line and "TM" are spec textures (`2F9BE0+16E0`, `+34E8`...)
  regenerated from their kept 2-bit alpha outline (in scope), not leftover retail pixels. Found with a title-screen memory dump.
- 14:10 **Strip pictures**: 6 pictures stored as stacks of thin strips (title logo 256x104, small logo 84x28, craft thumbnails,
  3 bars) kept a grid per strip = nearly every row. They now keep one 16x16 (or 4x4) grid per whole picture (`extract_spec.strip_pictures`).
- 14:20 Title logo, maker banner and small corner logo drawn by us (`drawn._title_logo`, `_badge`); preview `shots/logo_clean.png`.
  Leftover pictures added by override: `F6090+13BA8` (32x32) and three flat fills. Spec 1947 textures. Taint 0 failing of 5511.
  Walk `shots/v6/sheet.png`: title, menus, watercraft select, Dolphin Park warm-up with HUD. Pushed to Pages.

- 15:00 Glyph arrays re-typeset (`drawn.ARRAYS`: name-entry keyboard 16x12, small 8x8 font, time digits, speed digits) and
  cut-short label widths fixed by override (GLACIER COAST, TO ADVANCE, 2ND OR BETTER, 3 more; the partial last row is its own
  record). Walk `shots/v8/sheet.png`: options, change names (typing works), view records all readable. Taint 0 failing. Pushed.

## Works
- ROM map: 143 containers (129 MIO0 + raw), 84 scene load tables, segment map.
- Texture spec: 2042+ textures and ~150 palettes (static display lists + run-time trace + frame arrays + guessed
  single images). Regeneration from colour grid + 2-bit alpha, palettes rebuilt, MIO0 re-compression, clean image builder.
- Text labels re-typeset (menus, course names, messages, tutorial lines), word banners (FINISH!, WON, LOST, DRAW, RETIRE,
  1st-4th, NEW RECORD, TIME UP) and the HUD font strip (0-9 A-Z) redrawn. Previews: `D:/n64work/waverace64/shots/labels_clean.png`,
  `banners.png`, `digits_clean.png` (rendered from our generator, not from the game).
- Audio: all 309 samples resynthesised from outlines, own codebooks and loop states; 155 announcer lines = TTS placeholders.
- **Taint: 0 failing** on the published clean ROM (2026-10-02 12:45).
- Published ROM: title, menus, watercraft select in headless Edge; the build before it also ran a Dolphin Park race.

## Known rough spots
- The rider name under the select-screen preview is unreadable; stat bars on that screen are missing.
- Options screens: background is black (retail: blue gradient); the Change Names backdrop is a garbled red/teal pattern.
- Attract demo: some scenes show large pale planes over the water (fog or damaged geometry, not compared with retail yet).
- Rider helmet icons, flags and small HUD icons (F6090+40FE0.., +2DF50..) are colour-grid blur.
- Headless Edge failed once with "out of memory" (PC commit space low); checks wait when that happens.
- `29F7E0+0`, `2A2150+0` are several images guessed as one tall image (regenerated, but as one blur).
- The headless emulator sometimes runs at a few frames per second (machine load); one check hung and had to be stopped.

## Next
- Trace walks (championship, time trials, stunt, 2P, options, results) to confirm guessed sizes and find CI palettes.
- Pictures still colour-grid blur: rider portraits, HUD speed digits / small icons, course maps: draw briefs.
- 8 KB of small unknown gaps (< 64 bytes each or not after a marker): check for pixels. The code segments' data
  was scanned (23:05, byte statistics in 2 KB windows): no pixel-like region found.

## For the morning
- **Record the announcer**: practice pack at `D:/n64work/waverace64/practice/` (`practice_announcer_call_and_response.wav`,
  16 min, 155 lines, `SCRIPT.txt`). One voice: the race announcer. Takes go through the voice kit as usual.
- Play the published build: check sound, the menu backdrops and a full race.
