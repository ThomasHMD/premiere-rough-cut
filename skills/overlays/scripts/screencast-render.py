#!/usr/bin/env python3
"""Edits a screencast-record.py recording Tella-style: a ready-to-edit MP4.

What the render does, from the recording's log:
  - background (dark, paper or theme accent) and a rounded, shadowed browser window,
    with an address bar that follows page changes;
  - automatic zooms on the action (click, typing), which start BEFORE the click and
    follow the cursor, then release; explicit zooms (`focus`) framed on
    an element, with an optional spotlight (the rest of the screen darkened);
  - enlarged macOS cursor, tilted according to its speed, which presses down on click, with a
    theme-accent ripple;
  - captions (dark pill, accent eyebrow) when the scenario carries them.

All the dynamics (critically damped camera springs, cursor smoothing) are
precomputed here frame by frame; the Remotion `Screencast` composition only
displays. Zooms stay sharp: the screen is captured at double resolution.

Usage:
    python3 screencast-render.py <recording folder> --out demo.mp4
    python3 screencast-render.py <folder> --out demo.mp4 --fps 30 --background paper
    python3 screencast-render.py <folder> --rush "/path/rush.mp4"
With --rush: the rush's frame rate and resolution, the MP4 stored in <rush folder>/Screencast/
and registered in <rush>_broll-script.json, at the scenario's `rushStart` instant:
render-segments.py then lays it on V2 of the Premiere XML, like a b-roll.
Style options: the scenario's "render" block, overridden by the command line.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ATELIER = SKILL_ROOT.parent / "motion-design"   # Remotion project and fonts

DEFAULTS = {
    "fps": 60,
    "width": 1920,
    "height": 1080,
    "background": "dark",   # dark | paper | accent
    "chrome": True,         # browser bar
    "windowWidth": 1600,    # width of the window in the 1920 frame
    "autoZoom": 1.7,        # automatic zoom on click / typing (0 = disabled)
    "maxZoom": 2.0,
    # Calm camera (editor feedback: it zooms, unzooms, changes area, zooms again, where it could
    # simply glide smoothly): slow springs, close shots chained without going back to the wide shot,
    # no flash close-up.
    "zoomSmooth": 0.55,     # spring time of the zoom (s)
    "panSmooth": 0.50,      # spring time of the reframing (s)
    "zoomLead": 1.1,        # the zoom starts before the click (s)
    "zoomHold": 1.8,        # and holds after (s)
    "glide": 3.5,           # two close-ups less than 3.5 s apart: glide from one to the other, zoom held
    "minShot": 3.0,         # a shorter close-up (or chain) is dropped (or held if it has a spotlight)
    "deadZone": 0.55,       # the camera does not move if the target is within this center of the frame
    "minDuration": 0.0,     # minimum duration of the clip (s): the last frame is held
    "cursorSize": 56,
    "captionSec": 3.2,
    "crf": 16,
}


def smooth_damp(cur: float, target: float, vel: float, st: float, dt: float) -> tuple[float, float]:
    """Critically damped spring (SmoothDamp): no overshoot, soft start and arrival."""
    omega = 2.0 / max(st, 1e-4)
    x = omega * dt
    exp = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x)
    change = cur - target
    temp = (vel + omega * change) * dt
    vel = (vel - omega * temp) * exp
    return target + (change + temp) * exp, vel


def build_remap(events: list[dict]):
    """Late `at` anchors: re-times piecewise (the rest is untouched)."""
    pts = [(0.0, 0.0)]
    for e in events:
        # All anchors count, including those on time: after a delay, the recorder
        # catches up at the next anchor, and that anchor bounds the re-timing.
        if e["type"] == "anchor" and e["t"] > pts[-1][0] and e["at"] > pts[-1][1]:
            pts.append((e["t"], e["at"]))
    if all(abs(a - b) <= 0.05 for a, b in pts):
        return lambda t: t, []
    warn = []
    for (a0, b0), (a1, b1) in zip(pts, pts[1:]):
        r = (b1 - b0) / (a1 - a0)
        if r < 0.4:
            warn.append(f"sped up x{1 / r:.1f} between {b0:.1f} s and {b1:.1f} s")
    xs = [p[0] for p in pts]

    def f(t: float) -> float:
        i = bisect.bisect_right(xs, t) - 1
        if i >= len(pts) - 1:
            return t + (pts[-1][1] - pts[-1][0])
        (a0, b0), (a1, b1) = pts[i], pts[i + 1]
        return b0 + (t - a0) * (b1 - b0) / (a1 - a0)

    return f, warn


def encode_screen(rec: Path, frames: list[dict], dur: float, fps: int, out: Path) -> None:
    lst = out.with_suffix(".txt")
    lines = []
    for i, fr in enumerate(frames):
        t1 = frames[i + 1]["t"] if i + 1 < len(frames) else dur
        d = t1 - fr["t"]
        if d <= 0:
            continue
        lines.append(f"file '{(rec / 'frames' / fr['file']).as_posix()}'\nduration {d:.5f}")
    lines.append(f"file '{(rec / 'frames' / frames[-1]['file']).as_posix()}'")
    lst.write_text("\n".join(lines) + "\n")
    cmd = [
        "nice", "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-vf", f"fps={fps}", "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(out),
    ]
    subprocess.run(cmd, check=True)


def probe_rush(rush: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate,width,height", "-of", "json", str(rush)],
        capture_output=True, text=True, check=True,
    ).stdout
    st = json.loads(out)["streams"][0]
    num, den = (int(x) for x in st["r_frame_rate"].split("/"))
    # NTSC (29.97 / 59.94): exact rate, otherwise the clip drifts by one frame per 33 s
    return {"fps": num / den if den == 1001 else round(num / den), "width": int(st["width"]), "height": int(st["height"])}


def register_broll(rush: Path, out: Path, name: str, rush_start: float, fps: int) -> Path:
    """Registers the screencast in <rush>_broll-script.json (created if needed): it is
    render-segments.py that lays it on V2 of the XML, at `rushStart`, native duration."""
    path = rush.with_name(rush.stem + "_broll-script.json")
    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {"version": 1, "fps": fps, "rush": rush.name, "brolls_dir": None, "brolls": []}
    brolls_dir = Path(data["brolls_dir"]) if data.get("brolls_dir") else rush.parent / "Brolls"
    m, sec = divmod(rush_start, 60)
    entry = {
        "id": f"SC-{name}",
        "kind": "screencast",
        "file": os.path.relpath(out, brolls_dir),
        "timecode": f"{int(m):02d}:{sec:06.3f}",
        "durationSec": None,
    }
    brolls = [b for b in data.get("brolls", []) if b.get("id") != entry["id"]]
    brolls.append(entry)
    data["brolls"] = brolls
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rec", type=Path, help="folder produced by screencast-record.py")
    ap.add_argument("--out", type=Path, default=None,
                    help="output MP4 (default with --rush: <rush folder>/Screencast/<scenario>.mp4)")
    ap.add_argument("--rush", type=Path, default=None,
                    help="rush to illustrate: frame rate and resolution reused, screencast registered "
                         "in <rush>_broll-script.json for the Premiere XML (V2)")
    for k, v in DEFAULTS.items():
        if isinstance(v, bool):
            ap.add_argument(f"--{k}", type=lambda x: x.lower() in ("1", "true", "oui", "yes"), default=None)  # fr-ok: "oui" kept as an accepted value
        else:
            ap.add_argument(f"--{k}", type=type(v), default=None)
    ap.add_argument("--props-only", action="store_true", help="only writes the props (debugging)")
    args = ap.parse_args()

    rec = args.rec.resolve()
    data = json.loads((rec / "recording.json").read_text())
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(Path(data["scenario"]).read_text()).get("render", {}))
    except Exception:
        pass
    # With --rush, the frame rate is the rush's (otherwise the clip drifts in the sequence)
    # and the picture comes out at its resolution (a 1080p laid in a 4K sequence fills a quarter of it).
    out_scale = 1.0
    rush = args.rush.resolve() if args.rush else None
    if rush:
        if not rush.exists():
            sys.exit(f"ERROR: rush not found: {rush}")
        rm = probe_rush(rush)
        cfg["fps"] = rm["fps"]
    for k in DEFAULTS:
        if getattr(args, k) is not None:
            cfg[k] = getattr(args, k)
    if rush:
        if abs(rm["width"] / rm["height"] - cfg["width"] / cfg["height"]) < 0.01:
            out_scale = rm["height"] / cfg["height"]
        else:
            print(f"  ⚠ rush {rm['width']}x{rm['height']}: different ratio from the screencast, "
                  "render-segments.py will lay it fit-cover (edges cropped).")
    sc_name = data.get("name") or Path(data["scenario"]).stem
    if args.out is None:
        if not rush:
            sys.exit("ERROR: --out or --rush required.")
        args.out = rush.parent / "Screencast" / f"{sc_name}.mp4"

    fps, W, H = cfg["fps"], cfg["width"], cfg["height"]
    vw, vh = data["viewport"]
    events = sorted(data["events"], key=lambda e: e["t"])
    remap, warns = build_remap(events)
    for e in events:
        e["t"] = remap(e["t"])
    frames = [dict(f, t=remap(f["t"])) for f in data["frames"]]
    dur = max(max(e["t"] for e in events), cfg["minDuration"])   # --minDuration: hold the last frame
    n = int(math.ceil(dur * fps))

    # ---- stage geometry
    winW = cfg["windowWidth"]
    k = winW / vw
    bar = 44 if cfg["chrome"] else 0
    winH = vh * k + bar
    winX, winY = (W - winW) / 2, (H - winH) / 2
    to_stage = lambda x, y: (winX + x * k, winY + bar + y * k)

    # ---- cursor: logged positions -> per frame
    moves = [(e["t"], e["x"], e["y"]) for e in events if e["type"] in ("start", "move")]
    mt = [m[0] for m in moves]

    def mouse_at(t: float) -> tuple[float, float]:
        i = bisect.bisect_right(mt, t) - 1
        if i < 0:
            return moves[0][1], moves[0][2]
        if i >= len(moves) - 1:
            return moves[-1][1], moves[-1][2]
        (t0, x0, y0), (t1, x1, y1) = moves[i], moves[i + 1]
        a = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
        return x0 + (x1 - x0) * a, y0 + (y1 - y0) * a

    clicks = [e for e in events if e["type"] == "click"]
    urls = [e for e in events if e["type"] == "url"]
    scrolls = [(e["t"], e["t"] + e["dur"]) for e in events if e["type"] == "scroll"]

    # ---- automatic zoom windows (click, typing), cut by scrolls
    auto: list[list] = []
    if cfg["autoZoom"] and cfg["autoZoom"] > 1:
        for c in clicks:
            if not c.get("zoom", True):
                continue
            w0, w1 = c["t"] - cfg["zoomLead"], c["t"] + cfg["zoomHold"]
            nav = [u["t"] for u in urls if c["t"] <= u["t"] <= c["t"] + 1.5]
            if nav:
                w1 = nav[0] + 0.05  # page change: release right away
            X, Y = to_stage(c["x"], c["y"])
            auto.append([w0, w1, "click", [(c["t"], X, Y)]])
        starts = [e for e in events if e["type"] == "type_start" and e.get("zoom", True)]
        for s_ in starts:
            end = next((e["t"] for e in events if e["type"] == "type_end" and e["t"] >= s_["t"]), s_["t"] + 1)
            if s_.get("rect"):
                x, y, w, h = s_["rect"]
                X, Y = to_stage(x + min(w, 320) / 2, y + h / 2)  # start of the field, where the text is written
            else:
                X, Y = None, None
            auto.append([s_["t"] - 0.5, end + 1.0, "type", [(s_["t"], X, Y)] if X is not None else []])
        for w in auto:
            for s0, s1 in scrolls:
                if w[0] < s0 < w[1]:
                    w[1] = s0
                if w[0] < s1 <= w[1] and s0 <= w[0]:
                    w[0] = s1
        auto = sorted([w for w in auto if w[1] - w[0] > 0.2])
        merged: list[list] = []
        for w in auto:
            if merged and w[0] <= merged[-1][1] + 0.5:
                merged[-1][1] = max(merged[-1][1], w[1])
                merged[-1][3] = sorted(merged[-1][3] + w[3])
            else:
                merged.append([w[0], w[1], w[2], list(w[3])])
        auto = merged

    # ---- explicit zooms (focus -> unfocus)
    focus = []
    for i, e in enumerate(events):
        if e["type"] == "focus":
            end = next((x["t"] for x in events[i + 1:] if x["type"] in ("unfocus", "focus")), dur)
            x, y, w, h = e["rect"]
            X0, Y0 = to_stage(x, y)
            focus.append({"t0": e["t"], "t1": end, "rect": (X0, Y0, w * k, h * k),
                          "zoom": e.get("zoom"), "spot": e.get("spotlight", False)})

    def center_range(s: float, lo_edge: float, hi_edge: float, half_stage: float) -> tuple[float, float]:
        """Range of possible centers at zoom s without showing the background outside the window.
        Softened min/max: the range opens without a break when the window exceeds the frame,
        otherwise the reframing starts abruptly (visible jolt)."""
        half = half_stage / s
        kk = 40.0
        smin = lambda x, y: -kk * math.log(math.exp(-x / kk) + math.exp(-y / kk))
        return smin(lo_edge + half, half_stage), -smin(-(hi_edge - half), -half_stage)

    # ---- camera plan: shots (explicit close-ups, zooms on the action) grouped into
    # chains. Within a chain the zoom is ONE (the smallest, so that each target
    # fits) and the camera glides from one target to the next without going back to the wide shot.
    shots = []
    for f in focus:
        X, Y, w, h = f["rect"]
        sz = f["zoom"] or min(cfg["maxZoom"], 0.8 * W / w, 0.8 * H / h)
        shots.append({"t0": f["t0"], "t1": f["t1"], "s": max(1.12, sz), "focus": True, "spot": f["spot"],
                      "c": (X + w / 2, Y + h / 2), "anchors": []})
    for w0, w1, kind, anchors in auto:
        # an action zoom does not cut an explicit close-up: it lives outside its bounds
        for f in focus:
            if f["t0"] < w1 and w0 < f["t1"]:
                if w0 >= f["t0"]:
                    w0 = max(w0, f["t1"])
                else:
                    w1 = min(w1, f["t0"])
        if w1 - w0 > 0.2:
            shots.append({"t0": w0, "t1": w1, "s": cfg["autoZoom"], "focus": False, "spot": False,
                          "c": None, "anchors": anchors})
    shots.sort(key=lambda x: x["t0"])
    plan = shots
    for _ in range(6):                      # until stable: lengthening a shot can bring it closer to the next one
        avant = [(x["t0"], x["t1"]) for x in plan]
        runs: list[list[dict]] = []
        for sh in plan:
            if runs and sh["t0"] - max(x["t1"] for x in runs[-1]) < cfg["glide"]:
                runs[-1].append(sh)
            else:
                runs.append([sh])
        nouveau = []
        for r in runs:
            for a, b in zip(r, r[1:]):      # hold the shot until the next one: glide, do not zoom out
                a["t1"] = max(a["t1"], b["t0"])
            t0, t1 = r[0]["t0"], max(x["t1"] for x in r)
            if t1 - t0 < cfg["minShot"]:
                if any(x["spot"] for x in r):    # spotlight wanted by the scenario: hold it long enough
                    r[-1]["t1"] = t0 + cfg["minShot"]
                else:
                    continue                 # flash close-up: stay wide
            nouveau += r
        stable = [(x["t0"], x["t1"]) for x in nouveau] == avant
        plan = nouveau
        if stable:
            break
    for r in runs:                           # a single zoom per chain: the one where everything fits
        zs = min(x["s"] for x in r)
        for x in r:
            x["s"] = zs
    if args.props_only:
        print("camera plan:", [(round(x["t0"], 2), round(x["t1"], 2), round(x["s"], 2), "focus" if x["focus"] else "action")
                                for x in plan])
    cam_c = {"c": None}                      # target center, kept as long as the target stays in the frame

    def target(t: float, cur_xy: tuple[float, float]) -> tuple[float, float, float]:
        sh = next((x for x in plan if x["t0"] <= t < x["t1"]), None)
        if sh is None:
            cam_c["c"] = None
            return 1.0, W / 2, H / 2
        s = sh["s"]
        if sh["focus"]:
            want = sh["c"]
        else:
            # Aim at the target of the gesture (the next click, the typing field), like Tella,
            # rather than the cursor on its way: no back and forth…
            nxt = [a for a in sh["anchors"] if a[0] >= t - 0.25]
            a = nxt[0] if nxt else (sh["anchors"][-1] if sh["anchors"] else (t, *cur_xy))
            cx, cy = a[1], a[2]
            # …then follow the cursor if it leaves the visible central zone.
            hw, hh = W / (2 * s), H / (2 * s)
            mx_, my_ = 0.72 * hw, 0.66 * hh
            px_, py_ = cur_xy
            want = (min(max(cx, px_ - mx_), px_ + mx_), min(max(cy, py_ - my_), py_ + my_))
        c = cam_c["c"]
        # dead zone: if the new target is already well inside the frame, the camera does not move
        if c is None or abs(want[0] - c[0]) > cfg["deadZone"] * W / (2 * s) or abs(want[1] - c[1]) > cfg["deadZone"] * H / (2 * s):
            cam_c["c"] = want
        return s, cam_c["c"][0], cam_c["c"][1]

    # ---- frame-by-frame simulation
    dt = 1.0 / fps
    # The camera is smoothed in coordinates RELATIVE to the allowed range (u, v in
    # [0, 1]): clamping a smoothed center afterwards created jolts when the range
    # widens at the start of a zoom.
    ls, vs = 0.0, 0.0
    ux, vux, uy, vuy = 0.5, 0.0, 0.5, 0.0
    px, pvx, py, pvy = None, 0.0, None, 0.0
    tilt, vtilt = 0.0, 0.0
    cam, cur = [], []
    prev_x = None
    for i in range(n):
        t = i * dt
        mx, my = to_stage(*mouse_at(t))
        # light smoothing of the path ("smooth movement" style)
        if px is None:
            px, py = mx, my
        px, pvx = smooth_damp(px, mx, pvx, 0.045, dt)
        py, pvy = smooth_damp(py, my, pvy, 0.045, dt)
        ts, tcx, tcy = target(t, (px, py))
        lox, hix = center_range(ts, winX, winX + winW, W / 2)
        loy, hiy = center_range(ts, winY, winY + winH, H / 2)
        tux = min(1.0, max(0.0, (tcx - lox) / (hix - lox))) if hix - lox > 1 else ux
        tuy = min(1.0, max(0.0, (tcy - loy) / (hiy - loy))) if hiy - loy > 1 else uy
        ls, vs = smooth_damp(ls, math.log(ts), vs, cfg["zoomSmooth"], dt)
        ux, vux = smooth_damp(ux, tux, vux, cfg["panSmooth"], dt)
        uy, vuy = smooth_damp(uy, tuy, vuy, cfg["panSmooth"], dt)
        s = math.exp(ls)
        lox, hix = center_range(s, winX, winX + winW, W / 2)
        loy, hiy = center_range(s, winY, winY + winH, H / 2)
        ccx = lox + ux * (hix - lox)
        ccy = loy + uy * (hiy - loy)
        # tilt according to horizontal speed
        vxs = 0.0 if prev_x is None else (px - prev_x) / dt
        prev_x = px
        tilt, vtilt = smooth_damp(tilt, max(-14.0, min(14.0, vxs * 0.012)), vtilt, 0.08, dt)
        press = 0.0
        for c in clicks:
            a = t - c["t"]
            if -0.05 <= a < 0.02:      # pressing down
                press = max(press, (a + 0.05) / 0.07)
            elif 0.02 <= a <= 0.10:    # pressed
                press = 1.0
            elif 0.10 < a <= 0.25:     # release
                press = max(press, 1 - (a - 0.10) / 0.15)
        cam.append([round(s, 4), round(ccx, 1), round(ccy, 1)])
        cur.append([round(px, 1), round(py, 1), round(tilt, 2), round(press, 2)])

    click_list = []
    for c in clicks:
        X, Y = to_stage(c["x"], c["y"])
        click_list.append({"f": int(round(c["t"] * fps)), "x": round(X, 1), "y": round(Y, 1)})

    spots = [
        {"f0": int(f["t0"] * fps), "f1": int(f["t1"] * fps),
         "x": round(f["rect"][0], 1), "y": round(f["rect"][1], 1),
         "w": round(f["rect"][2], 1), "h": round(f["rect"][3], 1)}
        for f in focus if f["spot"]
    ]

    caps = [e for e in events if e["type"] == "caption"]
    captions = []
    for j, c in enumerate(caps):
        t1 = c["t"] + (c.get("sec") or cfg["captionSec"])
        if j + 1 < len(caps):
            t1 = min(t1, caps[j + 1]["t"] - 0.35)
        captions.append({"f0": int(c["t"] * fps), "f1": int(t1 * fps), "text": c["text"], "eyebrow": c.get("eyebrow")})

    url_list = [{"f": 0, "url": data["url"]}] + [{"f": int(u["t"] * fps), "url": u["url"]} for u in urls]

    # ---- work files (outside the synced folder if the recording is in it)
    work = rec / "render"
    pub = work / "public"
    pub.mkdir(parents=True, exist_ok=True)
    for name in ("fonts",):
        link = pub / name
        cible = ATELIER / "public" / name
        if link.is_symlink() and link.resolve() != cible.resolve():
            link.unlink()   # link from before the merge (overlays/public), dead or pointing elsewhere
        if not link.exists():
            link.symlink_to(cible)
    props = {
        "fps": fps, "width": W, "height": H, "durationInFrames": n, "video": "screen.mp4",
        "win": {"x": winX, "y": winY, "w": winW, "h": winH, "bar": bar, "radius": 14, "k": k},
        "background": cfg["background"], "chrome": cfg["chrome"], "cursorSize": cfg["cursorSize"],
        "cam": cam, "cur": cur, "clicks": click_list, "spots": spots, "captions": captions, "urls": url_list,
    }
    props_file = work / "props.json"
    props_file.write_text(json.dumps(props))
    print(f"props: {n} frames at {fps} fps ({dur:.1f} s), {len(auto)} auto zooms, {len(focus)} focus, "
          f"{len(click_list)} clicks, {len(captions)} captions")
    for w in warns:
        print(f"  ⚠ re-timing: {w}")
    if args.props_only:
        return

    screen = pub / "screen.mp4"
    print("encoding the captured screen…")
    encode_screen(rec, frames, dur, fps, screen)

    print("Remotion render…")
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "nice", "npx", "remotion", "render", "src/index.ts", "Screencast", str(out),
        f"--props={props_file}", f"--public-dir={pub}",
        "--codec=h264", f"--crf={cfg['crf']}", "--image-format=jpeg", "--jpeg-quality=95",
        "--concurrency=4", "--muted", "--log=warn",
    ]
    if abs(out_scale - 1.0) > 0.001:
        cmd.append(f"--scale={out_scale:g}")
    r = subprocess.run(cmd, cwd=ATELIER)
    if r.returncode != 0:
        sys.exit("ERROR: Remotion render failed.")
    print(f"OK → {out}")
    # Demo sounds (sound identity, ../motion-design/reference/sound-palette.md): clicks, keys,
    # page change, spotlighted element. render-segments.py mixes them and lays them
    # under the demo; discreet, the voice already tells what we see.
    sons = [{"file": "clic.wav", "at": round(c["t"], 3), "gainDb": 0} for c in clicks]
    sons += [{"file": f"touche-{i % 3 + 1}.wav", "at": round(e["t"], 3), "gainDb": -2}
             for i, e in enumerate(x for x in events if x["type"] == "key")]
    sons += [{"file": "page.wav", "at": round(u["t"], 3), "gainDb": -2} for u in urls]
    sons += [{"file": "af.wav", "at": round(f["t0"], 3), "gainDb": -6} for f in focus if f["spot"]]
    out.with_suffix(".sons.json").write_text(json.dumps(sorted(sons, key=lambda s: s["at"]), indent=1))
    if rush:
        rush_start = data.get("rushStart")
        if rush_start is None:
            try:
                rush_start = json.loads(Path(data["scenario"]).read_text()).get("rushStart", 0.0)
            except Exception:
                rush_start = 0.0
        bs = register_broll(rush, out, sc_name, float(rush_start), round(fps))
        print(f"registered in {bs.name} at {rush_start:.3f} s (V2 of the XML: render-segments.py \"{rush.name}\")")


if __name__ == "__main__":
    main()
