#!/usr/bin/env python3
"""Check of "proof" scenes (emails, web pages, photos the camera travels across) without rendering:
replays the camera of preuves.tsx (vue0 / viser / transitions) and checks, with the camera set on
each step:
  1. the view fits under the notes banner and inside the frame;
  2. the mark (highlight, strike-through, frame) stays at least 24 px from the edges;
  3. on an email, no visible line of text is cut by the left or right edge;
  4. outside emails (no fade under the notes), no note covers text.
Typical failures found: notes laid over the text in tight shots, frame and highlight stuck to
the edge, email lines cut on the right.
Replicates the camera of preuves.tsx: edit both together with viser() / vue0().
Usage: qc-preuves.py <rush>_animation-script.json <motion-design>/public"""
import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFont

script, public = Path(sys.argv[1]), Path(sys.argv[2])
ANCIEN = "--ancien" in sys.argv   # old camera (marks outside the framing): reference case
# camera from before marks half in the field were pushed out: reference case
AVANT_SORTIE = "--avant-sortie" in sys.argv
TRACE = []   # --trace: the steps whose camera moved for an earlier mark
segs = json.loads(script.read_text())["segments"]
try:
    FONT = ImageFont.truetype(str(public / "fonts" / "Inter-Bold.woff2"), 36)
except Exception:
    FONT = None
MARGE_MARQUE = {"cadre": 26, "surligne": 10, "barre": 6}


def note_w(txt):
    return (FONT.getlength(txt) if FONT else len(txt) * 0.6 * 36) + 60


def cue(cues, i, fb):
    return cues[i] if i < len(cues) and isinstance(cues[i], (int, float)) else fb


def rects(e, avec_marque):
    rs = [e["vue"]] if e.get("vue") else list(e.get("lignes") or ([e["box"]] if e.get("box") else []))
    if avec_marque and e.get("mode"):
        m = MARGE_MARQUE.get(e["mode"], 10)
        rs += [[r[0] - m, r[1] - m, r[2] + 2 * m, r[3] + 2 * m] for r in (e.get("lignes") or ([e["box"]] if e.get("box") else []))]
    return rs


def camera(d, cues, nnotes):
    kind = d.get("kind", "mail"); W = d.get("w", 2200); H = d.get("h", 1400)
    chrome = 110 if kind == "web" else 0
    border = round(max(W, H) * 0.035) if kind == "photo" else 0
    DW = W + 2 * border
    DH = H + chrome + 2 * border + (round(DW * 0.06) if kind == "photo" and d.get("caption") else 0)
    etapes = d.get("etapes", [])
    sMax = d.get("zoomMax") or (1.0 if kind == "photo" else 1.45)
    s0 = min((1480 if kind == "photo" else 1600) / DW, (940 if kind == "photo" else 4000) / DH)
    bande = 70 + nnotes * 71 + (nnotes - 1) * 16 + 20 if nnotes else 0
    haut = bande if nnotes else 70

    def vue0():
        cy = DH / 2 - (haut - 70) / s0 / 2 if DH * s0 <= 960 - (haut - 70) else (540 - haut) / s0
        return (s0, DW / 2, cy)

    def marques(j):
        e = etapes[j]
        if not e.get("mode"):
            return []
        m = MARGE_MARQUE.get(e["mode"], 10)
        return [[r[0] - m, r[1] - m, r[2] + 2 * m, r[3] + 2 * m] for r in (e.get("lignes") or ([e["box"]] if e.get("box") else []))]

    def viser(e, i):
        base = rects(e, False)
        if not base:
            return vue0()
        by0 = min(r[1] for r in base)
        libre = min(760, 1080 - bande - 110) if bande else 760
        yc = (bande + 1080) / 2 if bande else 540
        large = 1860 if ANCIEN else 1800

        def cadrer(rs):
            x0 = min(r[0] for r in rs); y0 = min(r[1] for r in rs)
            x1 = max(r[0] + r[2] for r in rs); y1 = max(r[1] + r[3] for r in rs)
            bw, bh = x1 - x0, y1 - y0
            s = e.get("zoom") or min(large / (bw + 60) if e.get("vue") else 1640 / (bw + 120), libre / (bh + 120), sMax)
            s = max(s, s0)
            cx = border + (x0 + x1) / 2; cy = border + chrome + (y0 + y1) / 2 - (yc - 540) / s
            hw, hh = 960 / s, 540 / s
            cx = DW / 2 if DW * s <= 1920 else min(max(cx, hw - 40 / s), DW - hw + 40 / s)
            cy = DH / 2 - (yc - 540) / s if DH * s <= 1080 - bande else min(max(cy, hh - (60 + bande) / s), DH - hh + 60 / s)
            return (s, cx, cy)
        if ANCIEN:
            return cadrer(base)
        rs = base + marques(i)
        c1 = cadrer(rs)
        s1, _, cy1 = c1
        h0, b0 = cy1 - 540 / s1 - border - chrome, cy1 + 540 / s1 - border - chrome
        prev = [r for j in range(i) for r in marques(j)]
        avant = [[r[0], by0, r[2], 0] for r in prev if r[1] >= h0 and r[1] + r[3] <= b0]
        c = cadrer(rs + avant) if avant else c1
        if AVANT_SORTIE:
            return c
        # earlier mark half in the field: push it out by shifting the camera, otherwise
        # bring it in whole (replica of viser() in preuves.tsx)
        M = 36

        def ec(k, r):
            s, cx, cy = k
            return (960 + (r[0] + border - cx) * s, 540 + (r[1] + border + chrome - cy) * s,
                    960 + (r[0] + r[2] + border - cx) * s, 540 + (r[1] + r[3] + border + chrome - cy) * s)

        def coupees(k):
            out = []
            for r in prev:
                X0, Y0, X1, Y1 = ec(k, r)
                if X1 > 0 and X0 < 1920 and Y1 > 0 and Y0 < 1080 and (X0 < M or X1 > 1920 - M or Y0 < M or Y1 > 1080 - M):
                    out.append(r)
            return out

        def tient(k):
            return (all(ec(k, r)[1] >= (bande + 50 if bande else 0) and ec(k, r)[3] <= 1050 for r in base)
                    and all(ec(k, r)[1] >= M and ec(k, r)[3] <= 1080 - M for r in marques(i)))
        cut = coupees(c)
        if not cut:
            return c
        s, cx, cy = c
        hh = 540 / s
        dys = sorted((d for r in cut for d in (-ec(c, r)[3] - 2, 1080 - ec(c, r)[1] + 2)), key=abs)
        for dy in dys:
            cy2 = cy - dy / s
            if DH * s <= 1080 - bande or cy2 < hh - (60 + bande) / s or cy2 > DH - hh + 60 / s:
                continue
            c2 = (s, cx, cy2)
            if tient(c2) and not coupees(c2):
                TRACE.append(f"step {i}: camera shifted by {dy:+.0f} px to push an earlier mark out")
                return c2
        inc = rs + avant + cut
        c3 = cadrer(inc)
        for _ in range(3):
            plus = coupees(c3)
            if not plus:
                break
            inc = inc + plus
            c3 = cadrer(inc)
        TRACE.append(f"step {i}: zoom {s:.2f} -> {c3[0]:.2f} to bring an earlier mark in")
        return c3

    plans = [vue0()] + [viser(e, i) for i, e in enumerate(etapes)]

    def at(t):
        cam = plans[0]
        for i in range(len(etapes)):
            a0 = cue(cues, i, 1 + i * 3) - 0.6
            k = min(1, max(0, (t - a0) / 0.9))
            if k <= 0:
                continue
            k = 1 - (1 - k) ** 3; a, b = cam, plans[i + 1]
            cam = (math.exp(math.log(a[0]) + (math.log(b[0]) - math.log(a[0])) * k),
                   a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k)
        return cam
    return at, border, chrome, bande, plans, s0, marques


DERIVE = 1 + 0.018 * 0.6   # Paper drift={0.6}: the paper grows up to +1.08% (center 960, 594)


def ecran(r, cam, border, chrome):
    s, cx, cy = cam
    X0, Y0 = 960 + (r[0] + border - cx) * s, 540 + (r[1] + border + chrome - cy) * s
    X1, Y1 = 960 + (r[0] + r[2] + border - cx) * s, 540 + (r[1] + r[3] + border + chrome - cy) * s
    g = lambda v, c: c + (v - c) * DERIVE
    return (g(X0, 960), g(Y0, 594), g(X1, 960), g(Y1, 594))


bad = 0
n_scenes = 0
for sg in segs:
    d = sg.get("data") or {}
    if sg.get("component") != "preuve":
        continue
    n_scenes += 1
    kind = d.get("kind", "mail")
    g = np.asarray(Image.open(public / d["src"]).convert("RGBA"))
    px = (g[..., 3] > 128) & (g[..., :3].mean(axis=2) < 150)
    cues = sg.get("cues", []); notes = d.get("notes", []); dur = sg["durationSec"]
    at, border, chrome, bande, plans, s0, marques = camera(d, cues, len(notes))
    defauts = []
    for i, e in enumerate(d.get("etapes", [])):
        cam = plans[i + 1]
        vr = rects(e, False)
        if not vr:
            continue
        X0 = min(ecran(r, cam, border, chrome)[0] for r in vr); Y0 = min(ecran(r, cam, border, chrome)[1] for r in vr)
        X1 = max(ecran(r, cam, border, chrome)[2] for r in vr); Y1 = max(ecran(r, cam, border, chrome)[3] for r in vr)
        if Y0 < (bande + 50 if bande else 0) or Y1 > 1050 or X0 < 0 or X1 > 1920:   # 1
            defauts.append(f"step {i}: view x {X0:.0f}-{X1:.0f}, y {Y0:.0f}-{Y1:.0f}")
        # 1 bis. photo or screenshot: the paper fits in width, otherwise its caption (aligned
        # left) and its edges are cut (a screenshot zoomed to 1.6)
        if kind == "photo" and (d.get("w", 0) + 2 * border) * cam[0] * DERIVE > 1920 - 48:
            defauts.append(f"step {i}: photo {(d.get('w', 0) + 2 * border) * cam[0]:.0f} px wide, caption and edges cut")
        # 2. any visible mark, even from an earlier step and even half visible: a mark
        # cut by the top or bottom edge (an underlined headline) shows as much
        # as a mark cut on the right
        mr = [ecran(r, cam, border, chrome) for j in range(i + 1) for r in marques(j)]
        mr = [m for m in mr if m[2] > 0 and m[0] < 1920 and m[3] > 0 and m[1] < 1080]
        for m in mr:
            if m[0] < 24 or m[2] > 1896 or m[1] < 24 or m[3] > 1056:
                defauts.append(f"step {i}: mark on screen x {m[0]:.0f}-{m[2]:.0f}, y {m[1]:.0f}-{m[3]:.0f} (cut or within 24 px of the edge)")
                break
        if kind == "mail":                                                         # 3
            s, cx, cy = cam
            top = bande + 50 if bande else 0
            iy0 = int(max(0, cy + (top - 540) / s - border - chrome)); iy1 = int(min(px.shape[0], cy + (1080 - 540) / s - border - chrome))
            for xe, cote in ((960 - 960 / DERIVE, "left"), (960 + 960 / DERIVE, "right")):
                ix = int(cx + (xe - 960) / s - border)
                col = px[iy0:iy1, max(0, ix - 3):max(0, ix + 3)] if 0 < ix < px.shape[1] else None
                if col is not None and col.size and col.sum() > 4:
                    defauts.append(f"step {i}: text cut by the {cote} edge")
    if kind != "mail" and notes:                                                   # 4
        t = 1.0
        while t < dur - 0.3:
            s, cx, cy = at(t); y = 70
            for n in notes:
                na = 0.15 if n["k"] < 0 else cue(cues, n["k"], 1)
                if t >= na + 0.3:
                    w = note_w(n["text"])
                    ix0 = int(cx + (80 - 960) / s - border); ix1 = int(cx + (80 + w - 960) / s - border)
                    iy0 = int(cy + (y - 540) / s - border - chrome); iy1 = int(cy + (y + 71 - 540) / s - border - chrome)
                    sub = px[max(0, iy0):max(0, iy1), max(0, ix0):max(0, ix1)]
                    if sub.size and sub.sum() * s * s > 150:
                        defauts.append(f"note \"{n['text']}\" over text at {t:.1f} s"); break
                y += 87
            else:
                t += 0.1; continue
            break
    if "--trace" in sys.argv:
        for x in dict.fromkeys(TRACE):
            print(f"   {sg['id']:<18} {x}")
    TRACE.clear()
    for x in dict.fromkeys(defauts):
        print(f"!! {sg['id']:<18} {x}")
    bad += bool(defauts)
print(f"{n_scenes} proofs, {bad} with defects")
sys.exit(1 if bad else 0)
