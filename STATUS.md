# Wave Race 64 clean room: status

## Decisions (logged as made)
- 2026-10-01 16:05 ROM found at `D:/Wave Race 64 - Kawasaki Jet Ski (USA) (Rev 1).zip` (user pointed to D:). sha1 `508dfc2d…7966a`
  = exactly the decomp's target (US Rev 1 / V1.1). Unpacked to `D:/n64work/waverace64/baserom.us.rev1.z64`.
- Decomp: LLONSIT/Wave-Race-64, LF clone at `D:/n64work/waverace64/pristine`. Its Makefile refuses native Windows
  (needs Linux, IDO recomp, mips binutils) and it keeps **all assets as `bin` blobs** (129 MIO0 blocks + raw segments +
  audio ctl/tbl/seq); only splat offsets are documented.
- **Web route = 3: clean ROM + WASM N64 emulator** (EmulatorJS 4.2.3 + mupen64plus_next/GLideN64, `ports/ejs`, same as
  DK64/Conker/BK). Why: no PC port of Wave Race 64 exists; the decomp is partial and has no web target.
  Retail boots to title + main menu in headless Edge with this core (dev-only check, 16:20).
- **Clean ROM = "clean image"**: copy of the ROM with code kept (the decomp's code is the same bytes) and every
  asset region regenerated and patched in at its known offset (MIO0 blocks re-compressed), CRC recomputed.
  Taint scan proves only spec regions differ and no retail pixels/samples remain.
- Core ROM-DB slot: "Wave Race 64 (U) (V1.0) [t1]" (RefMD5 = US, EEPROM 4 KB) is pointed at our ROM's MD5 (`ports/ejs/patch_core.py`).
- Dev server port 8163, CDP port 9363.

## Works
- (in progress) ROM map

## Next
- ROM map: MIO0 blocks, textures via display lists, audio ctl/tbl.
- Generate, taint, publish.

## For the morning
- (nothing yet)
