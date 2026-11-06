#!/usr/bin/env python3
"""Records a web-browsing demo driven by a scenario ("screencast" mode).

A windowless Chromium plays the scenario (go to a page, scroll, hover,
click, type, zoom on an element) and captures the screen at double resolution
(2880 x 1620 for a 1440 x 810 window), so that zooms stay sharp.

Why in slow motion: DevTools' video stream (Page.startScreencast) is capped at the
CSS resolution (1440 px, blurry as soon as you zoom); only the clipped capture at scale 2
gives the true double resolution, but at ~20 frames/s. The scenario is therefore played
`slow` times slower (gestures, scrolls, typing, waits, CSS animations via
Animation.setPlaybackRate) and all timestamps are divided by `slow`: we get
smooth 60 frames/s at normal speed. Page loads are not slowed
(they look `slow` times faster, which is desirable).

Scrolling is driven by the capture loop itself (position set, then clipped
capture at that position): no offset between what is captured and what is
requested, hence no jitter.

Each frame and each gesture (mouse position, click, typing, zoom, caption,
URL change) is timestamped in VIDEO time (seconds since the start). The render
(zooms, cursor, background) is done afterwards by screencast-render.py from this
log: nothing is burned in here.

No cursor in the frames: windowless Chromium does not draw one, the render
draws its own (smoothed, tilted, enlarged, Tella style).

Usage:
    python3 screencast-record.py scenario.json --out /tmp/demo-rec
    python3 screencast-record.py scenario.json --out /tmp/demo-rec --transcript rush_transcription.json

Output: <out>/frames/000000.jpg ... + <out>/recording.json
Scenario format: see SKILL.md, section "Screencast mode".
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import random
import re
import sys
import time
import unicodedata
from pathlib import Path

from playwright.async_api import async_playwright

TICK = 1 / 60  # rate of the logged mouse movements


def ease_in_out_cubic(k: float) -> float:
    return 4 * k * k * k if k < 0.5 else 1 - pow(-2 * k + 2, 3) / 2


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if unicodedata.category(c) != "Mn"))


def resolve_word_anchors(steps: list[dict], transcript: Path | None, rush_start: float) -> None:
    """`"word": "favorites"` (+ `occurrence`, `offset`) -> `at` in seconds since rushStart."""
    words = None
    for st in steps:
        if "word" not in st:
            continue
        if words is None:
            if not transcript:
                sys.exit("ERROR: a step uses `word` but --transcript was not provided.")
            words = json.loads(transcript.read_text())["words"]
        target = [norm(w) for w in st["word"].split()]
        occ = st.get("occurrence", 1)
        found = 0
        for i in range(len(words) - len(target) + 1):
            if words[i]["start"] < rush_start:
                continue
            if all(norm(words[i + j]["word"]) == target[j] for j in range(len(target))):
                found += 1
                if found == occ:
                    st["at"] = round(words[i]["start"] - rush_start + st.get("offset", 0.0), 3)
                    break
        if "at" not in st:
            sys.exit(f"ERROR: word \"{st['word']}\" (occurrence {occ}) not found in the transcript.")


class Recorder:
    def __init__(self, page, cdp, out: Path, vw: int, vh: int, dpr: float, quality: int, slow: float):
        self.page, self.cdp, self.out = page, cdp, out
        self.vw, self.vh, self.dpr, self.quality, self.slow = vw, vh, dpr, quality, slow
        self.frames_dir = out / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.frames: list[dict] = []
        self.events: list[dict] = []
        self.mx, self.my = vw * 0.62, vh * 0.58
        self.rng = random.Random(7)
        self.t_start = 0.0
        self.last_url = ""
        self.running = False
        self.scroll_anim: tuple[float, float, float, float] | None = None  # from, to, real t0, real duration
        self.capture_task = None
        self.last_hash = None

    # ---- clock: everything is logged in VIDEO time
    def now_v(self) -> float:
        return (time.time() - self.t_start) / self.slow

    async def wait_v(self, sec: float) -> None:
        """Wait expressed in video seconds."""
        await asyncio.sleep(max(0.0, sec) * self.slow)

    async def sleep_until_v(self, t_v: float) -> None:
        d = t_v - self.now_v()
        if d > 0:
            await asyncio.sleep(d * self.slow)

    # ---- capture
    async def _capture_loop(self) -> None:
        set_and_read = """(y) => { if (y !== null) window.scrollTo({top: y, left: 0, behavior: 'instant'});
                                   return [window.scrollX, window.scrollY]; }"""
        while self.running:
            want = None
            if self.scroll_anim:
                y0, y1, t0, dur = self.scroll_anim
                k = min(1.0, (time.time() - t0) / dur)
                want = y0 + (y1 - y0) * ease_in_out_cubic(k)
                if k >= 1.0:
                    self.scroll_anim = None
            try:
                sx, sy = await self.page.evaluate(set_and_read, want)
                ta = time.time()
                r = await self.cdp.send("Page.captureScreenshot", {
                    "format": "jpeg", "quality": self.quality,
                    "clip": {"x": sx, "y": sy, "width": self.vw, "height": self.vh, "scale": self.dpr},
                })
                tb = time.time()
            except Exception:
                await asyncio.sleep(0.03)  # navigation in progress: context destroyed, try again
                continue
            data = base64.b64decode(r["data"])
            h = hash(data)
            t_v = ((ta + tb) / 2 - self.t_start) / self.slow if self.t_start else 0.0
            if h == self.last_hash and self.frames:
                self.frames[-1]["until"] = t_v  # identical frame: do not rewrite the file
                continue
            self.last_hash = h
            name = f"{len(self.frames):06d}.jpg"
            (self.frames_dir / name).write_bytes(data)
            self.frames.append({"t": t_v, "file": name})

    async def apply_slow_css(self) -> None:
        try:
            await self.cdp.send("Animation.enable")
            await self.cdp.send("Animation.setPlaybackRate", {"playbackRate": 1 / self.slow})
        except Exception:
            pass

    async def start(self) -> None:
        await self.apply_slow_css()
        self.running = True
        self.capture_task = asyncio.ensure_future(self._capture_loop())
        for _ in range(100):
            if self.frames:
                break
            await asyncio.sleep(0.03)
        self.t_start = time.time()
        self.frames[0]["t"] = 0.0
        self.log("start", x=self.mx, y=self.my, url=self.page.url)
        self.last_url = self.page.url

    async def stop(self) -> None:
        await self.wait_v(0.2)
        self.log("end")
        self.running = False
        await self.capture_task

    def log(self, type_: str, **kw) -> None:
        self.events.append({"t": round(self.now_v(), 4) if self.t_start else 0.0, "type": type_, **kw})

    def on_nav(self, frame) -> None:
        if frame == self.page.main_frame and frame.url != self.last_url and self.t_start:
            self.last_url = frame.url
            self.log("url", url=frame.url)
            asyncio.ensure_future(self.apply_slow_css())

    # ---- gestures (durations in VIDEO seconds)

    async def move_to(self, x: float, y: float, dur: float | None = None) -> None:
        x0, y0 = self.mx, self.my
        d = math.hypot(x - x0, y - y0)
        if d < 2:
            return
        dur = dur or min(1.0, max(0.35, 0.28 + d / 1700))
        # Slightly curved path (quadratic Bezier), like a real hand.
        side = self.rng.choice((-1, 1))
        bend = min(90.0, d * 0.12) * side
        mx, my = (x0 + x) / 2, (y0 + y) / 2
        nx, ny = -(y - y0) / d, (x - x0) / d
        cx, cy = mx + nx * bend, my + ny * bend
        n = max(3, int(dur / TICK))
        t0 = self.now_v()
        for i in range(1, n + 1):
            k = ease_in_out_cubic(i / n)
            px = (1 - k) ** 2 * x0 + 2 * (1 - k) * k * cx + k * k * x
            py = (1 - k) ** 2 * y0 + 2 * (1 - k) * k * cy + k * k * y
            await self.page.mouse.move(px, py)
            self.log("move", x=round(px, 1), y=round(py, 1))
            await self.sleep_until_v(t0 + dur * i / n)
        self.mx, self.my = x, y

    async def box(self, sel: str) -> dict:
        loc = self.page.locator(sel).first
        await loc.wait_for(state="visible", timeout=15000)
        b = await loc.bounding_box()
        if not b:
            raise RuntimeError(f"element without a box: {sel}")
        return b

    async def scroll_to_y(self, y: float, dur: float) -> None:
        cur = await self.page.evaluate("scrollY")
        y = min(y, await self.page.evaluate("document.documentElement.scrollHeight - innerHeight"))
        self.log("scroll", frm=cur, to=y, dur=dur)
        self.scroll_anim = (cur, y, time.time(), dur * self.slow)
        while self.scroll_anim:
            await asyncio.sleep(0.02)

    async def ensure_visible(self, sel: str, block: str = "center", dur: float | None = None) -> dict:
        b = await self.box(sel)
        margin = 70
        if b["y"] >= margin and b["y"] + b["height"] <= self.vh - margin:
            return b
        cur = await self.page.evaluate("scrollY")
        if block == "start":
            target = cur + b["y"] - 90
        else:
            target = cur + b["y"] + b["height"] / 2 - self.vh / 2
        target = max(0, target)
        dist = abs(target - cur)
        await self.scroll_to_y(target, dur or min(2.2, max(0.7, 0.5 + dist / 1800)))
        await self.wait_v(0.15)
        return await self.box(sel)

    async def point_in(self, b: dict, pos: str | None = None) -> tuple[float, float]:
        if pos == "left":
            return b["x"] + min(40, b["width"] * 0.2), b["y"] + b["height"] / 2
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

    async def click(self, sel: str, pos: str | None, auto_zoom: bool) -> None:
        b = await self.ensure_visible(sel)
        x, y = await self.point_in(b, pos)
        await self.move_to(x, y)
        await self.wait_v(0.12)
        url_before = self.page.url
        await self.page.mouse.down()
        self.log("click", x=round(x, 1), y=round(y, 1), zoom=auto_zoom,
                 rect=[b["x"], b["y"], b["width"], b["height"]])
        await self.wait_v(0.09)
        await self.page.mouse.up()
        await self.wait_v(0.35)
        if self.page.url != url_before:
            try:
                await self.page.wait_for_load_state("load", timeout=15000)
            except Exception:
                pass
            await self.wait_v(0.4)

    async def run_step(self, st: dict) -> None:
        do = st["do"]
        if "caption" in st:
            self.log("caption", text=st["caption"], eyebrow=st.get("eyebrow"), sec=st.get("captionSec"))
        if do == "wait":
            await self.wait_v(st.get("sec", 1.0))
        elif do == "goto":
            await self.page.goto(st["url"], wait_until="load")
            await self.wait_v(st.get("sec", 0.6))
        elif do == "back":
            await self.page.go_back(wait_until="load")
            await self.wait_v(st.get("sec", 0.6))
        elif do == "scroll":
            if "to" in st:
                cur = await self.page.evaluate("scrollY")
                b = await self.box(st["to"])
                if st.get("block", "center") == "start":
                    target = cur + b["y"] - st.get("margin", 90)
                else:
                    target = cur + b["y"] + b["height"] / 2 - self.vh / 2
            elif "by" in st:
                target = await self.page.evaluate("scrollY") + st["by"]
            else:
                target = st.get("y", 0)
            target = max(0, target)
            cur = await self.page.evaluate("scrollY")
            dur = st.get("sec") or min(2.4, max(0.7, 0.5 + abs(target - cur) / 1800))
            await self.scroll_to_y(target, dur)
            await self.wait_v(0.1)
        elif do in ("move", "hover"):
            b = await self.ensure_visible(st["target"])
            x, y = await self.point_in(b, st.get("pos"))
            await self.move_to(x, y)
            await self.wait_v(st.get("sec", 0.4 if do == "move" else 1.0))
        elif do == "click":
            await self.click(st["target"], st.get("pos"), st.get("zoom", True))
            await self.wait_v(st.get("sec", 0.3))
        elif do == "type":
            if st.get("target"):
                await self.click(st["target"], "left", st.get("zoom", True))
            b = await self.box(st["target"]) if st.get("target") else None
            self.log("type_start", rect=[b["x"], b["y"], b["width"], b["height"]] if b else None,
                     zoom=st.get("zoom", True))
            for ch in st["text"]:
                await self.page.keyboard.type(ch)
                self.log("key")
                await self.wait_v(st.get("delay", 0.11) * self.rng.uniform(0.6, 1.5))
            self.log("type_end")
            await self.wait_v(st.get("sec", 0.6))
        elif do == "clear":
            await self.page.locator(st["target"]).first.fill("")
            await self.wait_v(st.get("sec", 0.3))
        elif do == "focus":
            b = await self.ensure_visible(st["target"], st.get("block", "center"))
            rect = [b["x"], b["y"], b["width"], b["height"]]
            # Frame the real content (a short paragraph rarely fills the whole
            # width of its block): box of the text and images, bounded by the element.
            tight = await self.page.locator(st["target"]).first.evaluate(
                """el => { const r = document.createRange(); r.selectNodeContents(el);
                           const b = r.getBoundingClientRect(), e = el.getBoundingClientRect();
                           if (!b.width || !b.height) return null;
                           const x0 = Math.max(b.left, e.left), y0 = Math.max(b.top, e.top);
                           const x1 = Math.min(b.right, e.right), y1 = Math.min(b.bottom, e.bottom);
                           return x1 > x0 && y1 > y0 ? [x0, y0, x1 - x0, y1 - y0] : null; }""")
            if tight and not st.get("wholeBox", False):
                rect = tight
            pad = st.get("pad", 14)
            rect = [rect[0] - pad, rect[1] - pad, rect[2] + 2 * pad, rect[3] + 2 * pad]
            self.log("focus", rect=rect, zoom=st.get("zoom"), spotlight=st.get("spotlight", False),
                     hold=st.get("hold", False))
            if st.get("hover", True):
                x, y = await self.point_in(b, st.get("pos"))
                await self.move_to(x, y)
            await self.wait_v(st.get("sec", 2.5))
            if not st.get("hold", False):
                self.log("unfocus")
        elif do == "unfocus":
            self.log("unfocus")
            await self.wait_v(st.get("sec", 0.2))
        else:
            raise ValueError(f"unknown step: {do}")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--transcript", type=Path, help="<rush>_transcription.json for the `word` anchors")
    ap.add_argument("--headed", action="store_true", help="visible window (debugging)")
    args = ap.parse_args()

    sc = json.loads(args.scenario.read_text())
    vw, vh = sc.get("viewport", [1440, 810])
    dpr = sc.get("dpr", 2)
    rush_start = sc.get("rushStart", 0.0)
    slow = sc.get("slow", 4)
    steps = sc["steps"]
    resolve_word_anchors(steps, args.transcript, rush_start)

    args.out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed, args=["--hide-scrollbars"])
        # `geolocation`: simulated [latitude, longitude] + permission granted (for "Near me" buttons).
        geo = sc.get("geolocation")
        geo_kw = {"geolocation": {"latitude": geo[0], "longitude": geo[1]}, "permissions": ["geolocation"]} if geo else {}
        ctx = await browser.new_context(
            viewport={"width": vw, "height": vh}, device_scale_factor=dpr,
            locale="fr-FR", timezone_id="Europe/Paris", color_scheme=sc.get("colorScheme", "light"),
            **geo_kw,
        )
        if sc.get("hide"):
            # Hide what pollutes a demo (cookie banner, newsletter box,
            # chat widget) on every page, even before their first render.
            css = ", ".join(sc["hide"]) + " { display: none !important; }"
            await ctx.add_init_script(script=f"""(() => {{
                const add = () => {{ const s = document.createElement('style');
                    s.textContent = {json.dumps(css)};
                    (document.head || document.documentElement).appendChild(s); }};
                document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', add) : add();
            }})()""")
        page = await ctx.new_page()
        await page.goto(sc["url"], wait_until="load")
        await page.evaluate("document.fonts.ready")
        await asyncio.sleep(sc.get("settle", 1.2))
        cdp = await ctx.new_cdp_session(page)
        rec = Recorder(page, cdp, args.out, vw, vh, dpr, sc.get("quality", 90), slow)
        await page.mouse.move(rec.mx, rec.my)
        page.on("framenavigated", rec.on_nav)
        await rec.start()

        late = []
        for i, st in enumerate(steps):
            if "at" in st:
                if rec.now_v() > st["at"] + 0.05:
                    late.append((i, round(rec.now_v() - st["at"], 2)))
                await rec.sleep_until_v(st["at"])
                rec.log("anchor", at=st["at"], step=i)
            rec.log("step", i=i, do=st["do"])
            try:
                await rec.run_step(st)
            except Exception as e:  # a failed step must not throw away the whole recording
                rec.log("error", i=i, msg=str(e)[:200])
                print(f"  ! step {i} ({st['do']}): {e}", file=sys.stderr)
        await rec.wait_v(sc.get("tail", 1.0))
        await rec.stop()
        await browser.close()

    data = {
        "scenario": str(args.scenario.resolve()),
        "name": args.scenario.stem, "rushStart": rush_start,
        "viewport": [vw, vh], "dpr": dpr, "slow": slow, "url": sc["url"],
        "frames": rec.frames, "events": rec.events, "late": late,
    }
    (args.out / "recording.json").write_text(json.dumps(data))
    dur = rec.events[-1]["t"]
    fps = len(rec.frames) / max(dur, 0.01)
    errs = [e for e in rec.events if e["type"] == "error"]
    print(f"OK {len(rec.frames)} distinct frames for {dur:.1f} s of video (about {fps:.0f} fps on average), "
          f"{len(errs)} step(s) in error -> {args.out}")
    if late:
        print(f"  ⚠ anchors late (step, s): {late}: the render re-times.")
    if errs:
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
