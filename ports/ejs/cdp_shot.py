"""Dev tool: drive the EmulatorJS page in headless Edge over CDP; real key events, page screenshots.

    python ports/ejs/cdp_shot.py <out dir> --url http://localhost:8093/index.html?rom=clean.z64
        --script "10:shot,12:Enter:0.2,14:shot,16:x:0.2,..." [--webgl] [--wait 60]

Times are seconds after the page logs "WR64: game started". Keys: Enter, x, c, z, s, q,
ArrowUp/Down/Left/Right, i, j, k, l (see ports/ejs/index.html for the N64 mapping).
Writes shot_<t>.png, console.txt and prints a one-line summary.
"""
import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.request

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
VK = {"Enter": 13, "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40, "Shift": 16, " ": 32}
CODE = {"Enter": "Enter", "ArrowLeft": "ArrowLeft", "ArrowUp": "ArrowUp", "ArrowRight": "ArrowRight",
        "ArrowDown": "ArrowDown", " ": "Space"}


# dev: find the emulated RDRAM in the wasm heap (the boot code copy of ROM 0x1000.. sits at the entry point) -> base64 of 4 MB
RAMJS = """(function(){try{const T0=performance.now();
const M=EJS_emulator.gameManager.Module,H=M.HEAPU8;
if(!window.__ram){const R=window.__romsig;if(!R)return 'ERR no sig';
 const U=new Uint32Array(H.buffer,0,H.length>>2);const s=R.sig,n=U.length-8;let found=[];
 for(let i=0;i<n;i++){if(U[i]===s[0]&&U[i+1]===s[1]&&U[i+2]===s[2]&&U[i+3]===s[3])found.push(i*4);}
 const c=found.filter(o=>o-R.entry>=0&&!(U[(o-0x1000)>>2]===0x80371240));
 if(!c.length)return 'ERR not found '+found.length;window.__ram=c[c.length-1]-R.entry;window.__ramc=c.length+'/'+found.length;}
const b=H.subarray(window.__ram,window.__ram+0x400000);let s='';
for(let i=0;i<b.length;i+=0x8000)s+=String.fromCharCode.apply(null,b.subarray(i,i+0x8000));
const r=btoa(s);console.log('RAMT '+(performance.now()-T0).toFixed(0)+' base '+window.__ram+' '+window.__ramc);return r;}catch(e){return 'ERR '+e}})()"""


# dev: frame-driven input. Steps [[pad id or -1, hold frames, wait frames], ...] are timed by a game frame counter
# in RDRAM (wall time is useless: the emulator's speed varies with the machine load). Logs WRSNAP <i> after each step.
DRIVEJS = """(function(steps,ctr){try{
const M=EJS_emulator.gameManager.Module,G=EJS_emulator.gameManager,R=window.__romsig;
const find=()=>{const H=M.HEAPU8,U=new Uint32Array(H.buffer,0,H.length>>2),s=R.sig,n=U.length-8;let f=[];
 for(let i=0;i<n;i++){if(U[i]===s[0]&&U[i+1]===s[1]&&U[i+2]===s[2]&&U[i+3]===s[3])f.push(i*4);}
 const c=f.filter(o=>o-R.entry>=0&&!(U[(o-0x1000)>>2]===0x80371240));
 if(c.length){window.__ram=c[c.length-1]-R.entry;window.__ramc=c.length+'/'+f.length;}};
const cnt=()=>new Uint32Array(M.HEAPU8.buffer,window.__ram+ctr,1)[0];
let i=0,ph=0,f0=0,last=-1,stall=0;
const iv=setInterval(()=>{try{
 if(window.__ram===undefined){find();if(window.__ram===undefined)return;f0=cnt();console.log('WRDRIVE ram '+window.__ram+' ctr '+f0);}
 const f=cnt();if(f===last){if(++stall===3000){console.log('WRSTALL '+f);}}else{stall=0;last=f;}
 if(i>=steps.length)return;const s=steps[i];
 if(ph===0){if(f-f0>=0){if(s[0]>=0)G.simulateInput(0,s[0],s[0]>=16?0x7fff:1);ph=1;f0=f;}}
 else if(ph===1){if(f-f0>=s[1]){if(s[0]>=0)G.simulateInput(0,s[0],0);ph=2;f0=f;}}
 else if(f-f0>=s[2]){console.log('WRSNAP '+i+' f='+f);ph=0;f0=f;i++;if(i>=steps.length){console.log('WRDONE');clearInterval(iv);}}
}catch(e){console.log('WRERR '+e);}},8);return 'ok';}catch(e){return 'ERR '+e}})"""


def keyinfo(k):
    if len(k) == 1:
        return dict(key=k, code="Key" + k.upper(), windowsVirtualKeyCode=ord(k.upper()), nativeVirtualKeyCode=ord(k.upper()))
    return dict(key=k, code=CODE.get(k, k), windowsVirtualKeyCode=VK[k], nativeVirtualKeyCode=VK[k])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--url", required=True)
    ap.add_argument("--script", default="10:shot")
    ap.add_argument("--webgl", action="store_true", help="software WebGL (SwiftShader, slow)")
    ap.add_argument("--gpu", action="store_true", help="hardware WebGL via ANGLE/D3D11 (fast)")
    ap.add_argument("--wait", type=float, default=None)
    ap.add_argument("--port", type=int, default=9341)
    ap.add_argument("--drive", help="JSON steps [[pad, hold frames, wait frames], ...]: frame-driven input, shot (+ram) per step")
    ap.add_argument("--ctr", type=lambda x: int(x, 0), default=0, help="RDRAM offset of a frame counter (u32)")
    ap.add_argument("--noram", action="store_true")
    ap.add_argument("--rom", help="ROM file (for ram dumps: locates RDRAM in the heap)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for f in os.listdir(a.out):
        if f.startswith("shot_"):
            os.remove(os.path.join(a.out, f))
    ev = []
    for item in a.script.split(","):
        parts = item.split(":")
        t = float(parts[0])
        if parts[1] in ("shot", "ram"):
            ev.append((t, parts[1], parts[0]))
        else:
            dur = float(parts[2]) if len(parts) > 2 else 0.15
            ev.append((t, "down", parts[1]))
            ev.append((t + dur, "up", parts[1]))
    ev.sort(key=lambda e: e[0])
    if a.drive:
        ev = []
    wait = a.wait or ((ev[-1][0] + 30) if ev else 900)
    prof = tempfile.mkdtemp(prefix="cdpshot_")
    args = [EDGE, "--headless=new", f"--user-data-dir={prof}", f"--remote-debugging-port={a.port}", "--remote-allow-origins=*",
            "--no-first-run", "--autoplay-policy=no-user-gesture-required", "--window-size=960,760",
            "--disable-renderer-backgrounding", "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows", "--disable-features=CalculateNativeWinOcclusion"]
    if os.environ.get("CDP_MUTE"):
        args.append("--mute-audio")
    if a.webgl:
        args += ["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"]
    if a.gpu:
        args += ["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-webgl"]
    p = subprocess.Popen(args + ["about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    console, shots, rams = [], 0, 0
    pending_ram = {}
    done = False
    try:
        for _ in range(480):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{a.port}/json"))
                break
            except OSError:
                time.sleep(0.25)
        tab = next(t for t in tabs if t.get("type") == "page")
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30)
        n = [0]
        pending = {}

        def send(method, **params):
            n[0] += 1
            ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
            return n[0]

        send("Runtime.enable")
        send("Page.enable")
        # headless pages can look hidden/unfocused and EmulatorJS then pauses: pin them visible + focused
        send("Emulation.setFocusEmulationEnabled", enabled=True)
        send("Page.addScriptToEvaluateOnNewDocument", source=(
            "Object.defineProperty(document,'hidden',{get:()=>false});"
            "Object.defineProperty(document,'visibilityState',{get:()=>'visible'});"
            "document.hasFocus=()=>true;"
            "for (const t of ['visibilitychange','blur','pagehide','freeze'])"
            "{window.addEventListener(t,e=>e.stopImmediatePropagation(),true);"
            "document.addEventListener(t,e=>e.stopImmediatePropagation(),true);}"))
        if a.rom:
            import struct
            with open(a.rom, "rb") as f:
                head = f.read(0x1010)
            sig = list(struct.unpack(">4I", head[0x1000:0x1010]))
            entry = struct.unpack(">I", head[8:12])[0] & 0x7FFFFF
            send("Page.addScriptToEvaluateOnNewDocument", source=f"window.__romsig={{sig:{sig},entry:{entry}}};")
        send("Page.navigate", url=a.url)
        t_start = time.time()
        t0 = None
        ws.settimeout(0.05)
        i = 0
        while time.time() - t_start < wait:
            try:
                m = json.loads(ws.recv())
                if m.get("method") == "Runtime.consoleAPICalled":
                    txt = " ".join(str(x.get("value", x.get("description", ""))) for x in m["params"]["args"])
                    if "Translation not found" not in txt:
                        console.append(f"{time.time() - t_start:6.1f} {txt[:300]}")
                    if txt.startswith("WRSNAP "):
                        tag = "%03d" % int(txt.split()[1])
                        pending[send("Page.captureScreenshot", format="png")] = tag
                        if not a.noram:
                            pending_ram[send("Runtime.evaluate", expression=RAMJS, returnByValue=True)] = tag
                    if txt.startswith("WRDONE"):
                        done = True
                    if t0 is None and "WR64: game started" in txt:
                        t0 = time.time()
                        if a.drive:
                            send("Runtime.evaluate", expression=f"{DRIVEJS}({a.drive},{a.ctr})", returnByValue=True)
                        for typ in ("mousePressed", "mouseReleased"):      # focus the game element
                            send("Input.dispatchMouseEvent", type=typ, x=480, y=300, button="left", clickCount=1)
                elif m.get("method") == "Runtime.exceptionThrown":
                    console.append("EXCEPTION " + m["params"]["exceptionDetails"].get("text", "")[:200])
                elif m.get("id") in pending_ram and "result" in m:
                    tag = pending_ram.pop(m["id"])
                    v = m["result"].get("result", {}).get("value", "")
                    if v.startswith("ERR") or not v:
                        console.append(f"RAM {tag}: {v}")
                    else:
                        open(os.path.join(a.out, f"ram_{tag}.bin"), "wb").write(base64.b64decode(v))
                        rams += 1
                elif m.get("id") in pending and "result" in m:
                    tag = pending.pop(m["id"])
                    open(os.path.join(a.out, f"shot_{tag}.png"), "wb").write(base64.b64decode(m["result"]["data"]))
                    shots += 1
            except websocket.WebSocketTimeoutException:
                pass
            if t0 is None:
                continue
            while i < len(ev) and time.time() - t0 >= ev[i][0]:
                t, kind, arg = ev[i]
                if kind == "shot":
                    pending[send("Page.captureScreenshot", format="png")] = arg
                elif kind == "ram":
                    pending_ram[send("Runtime.evaluate", expression=RAMJS, returnByValue=True)] = arg
                elif arg[0] == "p" and arg[1:].isdigit():        # p<id>: EmulatorJS pad input (0 A, 1 B, 3 Start, 4-7 d-pad, 16-19 stick)
                    v = (0x7FFF if int(arg[1:]) >= 16 else 1) if kind == "down" else 0
                    send("Runtime.evaluate", expression=f"EJS_emulator.gameManager.simulateInput(0,{int(arg[1:])},{v})")
                else:
                    info = keyinfo(arg)
                    send("Input.dispatchKeyEvent", type="keyDown" if kind == "down" else "keyUp", **info)
                i += 1
            if i >= len(ev) and not pending and not pending_ram and (done or not a.drive):
                break
    finally:
        p.kill()
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    open(os.path.join(a.out, "console.txt"), "w", encoding="utf-8").write("\n".join(console))
    print(f"{shots} screenshots, {rams} ram dumps, {len(console)} console lines, started={'yes' if t0 else 'NO'} -> {a.out}")


if __name__ == "__main__":
    main()
