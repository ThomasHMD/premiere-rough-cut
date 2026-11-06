#!/usr/bin/env python3
"""Free zone: no overlay may cut into the box around the speaker's head.

Recurring defect (headband and forehead; stamps on the hair and beard, cards on the ear and
glasses): overlays used to be placed "in the right third" by eye. Here the head is MEASURED on
the clip, segment by segment of the sequence, and every overlay is placed and checked in pixels:
its box (text measured in the real fonts, rotation, animated entrance, stamp ring included)
never cuts the head box, 3% margin included.

Measure (once per sequence, after the rough cut is approved):
    python3 zone_libre.py mesurer <clip.MOV> <clip>_timeline.json <_Illustration_work folder>
        4 frames per segment -> Vision (face + person silhouette, tete.swift) -> tetes.json
        (head box per segment, forbidden zone = box + 3%) and tetes-controle.jpg (contact sheet:
        look at it once, a raised hand or a book in front of the face skews the measure;
        a segment where the face is missing on one frame = median box of the video)

In a plan.py:
    import zone_libre as Z
    Z.charger(work / "tetes.json")
    data, boite = Z.poser("stamp", data, t0, t1)   # places and sizes inside the free zone
    Z.controle(SEG) -> list of overflows (run after habillage.tenue(), which moves the ends)

Check on images (after a test render): Z.boite_alpha(png) gives the box of the visible pixels
(alpha > 0.15) of an overlay; Z.coupe(boite, interdite) compares it.
Geometries: alpha.tsx (Stamp, Slam, StatTag, LienDescription), murs.tsx (Sondages, Gaufre,
Croyance), preuves.tsx (Gif) of motion-design. When a component changes, its geometry here changes too.
"""
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

W, H = 1920, 1080
MARGE = 0.03          # around the head, as a fraction of the width and of the height
BORD = 60             # px between an overlay and the right edge of the frame
ICI = Path(__file__).resolve().parent
FONTS = ICI.parents[1] / "motion-design" / "public" / "fonts"

# --- head --------------------------------------------------------------------------------------
_TETES = []


def charger(chemin):
    """tetes.json: [{clip, seq_in, seq_out, tete, zone_interdite}] in px at 1920x1080."""
    _TETES[:] = json.loads(Path(chemin).read_text())["clips"]
    return _TETES


def interdite(t0, t1):
    """Union of the forbidden zones of the segments that overlap [t0, t1] (sequence time)."""
    zs = [c["zone_interdite"] for c in _TETES if c["seq_out"] > t0 + 1e-3 and c["seq_in"] < t1 - 1e-3]
    if not zs:
        zs = [c["zone_interdite"] for c in _TETES]
    return [min(z[0] for z in zs), min(z[1] for z in zs), max(z[2] for z in zs), max(z[3] for z in zs)]


def coupe(b, z):
    return b[0] < z[2] and b[2] > z[0] and b[1] < z[3] and b[3] > z[1]


# --- text measured in the real fonts (glyph advances, no kerning: slightly wide) ------------------
_POL = {}


def _police(fichier, wght=None, opsz=None):
    k = (fichier, wght, opsz)
    if k not in _POL:
        from fontTools.ttLib import TTFont
        f = TTFont(FONTS / fichier)
        if "fvar" in f:
            from fontTools.varLib.instancer import instantiateVariableFont
            f = instantiateVariableFont(f, {"wght": wght, "opsz": opsz})
        _POL[k] = (f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm)
    return _POL[k]


def largeur(texte, corps, famille="display", poids=400, italique=True, espacement=0.0, majuscules=False):
    """Width in px of one line. display = Source Serif (opsz = size, like the browser),
    sans = Inter. espacement in em (letter-spacing, counted after each character)."""
    if majuscules:
        texte = texte.upper()
    if famille == "display":
        prim = _police("SourceSerif4-Italic.woff2" if italique else "SourceSerif4-Roman.woff2", poids, max(9, min(144, round(corps / 4) * 4)))
    else:
        prim = _police("Inter-Bold.woff2" if poids >= 600 else "Inter-Regular.woff2")
    secours = _police("Inter-Bold.woff2" if poids >= 600 else "Inter-Regular.woff2")
    tot = 0.0
    for ch in texte:
        for cm, hm, upm in (prim, secours):
            g = cm.get(ord(ch))
            if g:
                tot += hm[g][0] / upm
                break
        else:
            tot += 0.5
        tot += espacement
    return tot * corps * 1.02


def lignes_equilibrees(texte, n, mini=5):
    """Splits texte into n lines, the longest as short as possible; splits at spaces, or
    after the hyphen of a compound word ("mother- / in-law", counted as one more character);
    no line shorter than `mini` characters (no lone "For" at the head of a line)."""
    jet = []   # (chunk, glued to the next one)
    # splits at ordinary spaces only: the non-breaking space ("nul ?") keeps its two words together.
    # A lone punctuation mark or unit (":", "%", "·") stays with the word before it, an opening guillemet with the word after:
    # never "Nikon / : already a look" nor "D200 · 2005 / · CCD"; a "·" that
    # ends a line disappears, the break acts as the separator ("D40 : 70 / D200 : 100").
    mots = []
    for mot in texte.split(" "):
        if mots and re.fullmatch(r"[:;!?»=€%·]+", mot):  # fr-ok
            mots[-1] += " " + mot
        elif mots and mots[-1].endswith("«"):  # fr-ok
            mots[-1] += " " + mot
        elif mot:
            mots.append(mot)
    for mot in mots:
        parts = mot.split("-")
        for i, x in enumerate(parts):
            jet.append((x + ("-" if i < len(parts) - 1 else ""), i < len(parts) - 1))
    if n <= 1 or len(jet) < n:
        return [texte]

    def ligne(i, j):
        return "".join(x + ("" if colle or k == j - 1 else " ") for k, (x, colle) in enumerate(jet[i:j], start=i))

    best = None

    def rec(i, k, acc, pen):
        nonlocal best
        if k == 1:
            l = acc + [ligne(i, len(jet))]
            if min(len(x) for x in l) < mini:
                return
            score = max(len(x) for x in l) + pen
            if best is None or score < best[0]:
                best = (score, l)
            return
        for j in range(i + 1, len(jet) - k + 2):
            rec(j, k - 1, acc + [ligne(i, j)], pen + (1 if jet[j - 1][1] else 0))
    rec(0, n, [], 0)
    if not best:
        return [texte]
    ls = best[1]
    return [re.sub(r"\s*·$", "", x) if k < len(ls) - 1 else x for k, x in enumerate(ls)]


def _rot(w, h, deg):
    a = math.radians(abs(deg))
    return w * math.cos(a) + h * math.sin(a), w * math.sin(a) + h * math.cos(a)


# --- overlay geometry (largest visible box over the whole duration) ---------------------------
def tampon_dims(texte, corps, theme=None):
    """StampMark: unrotated width and height. Lines separated by \\n. "matrix" theme (MxTampon):
    JetBrains Mono, fixed advance of 0.6 em, bar of 0.3 em on each side, 1.2 em per line."""
    ls = texte.split("\n")
    if theme == "matrix":
        return max(len(l) for l in ls) * 0.6 * corps + 0.6 * corps, len(ls) * 1.2 * corps + 0.1 * corps
    lw = max(largeur(l, corps, "sans", 700, False, 0.08, True) for l in ls)
    return lw + corps * (0.92 + 0.2), corps * (len(ls) + 0.32 + 0.2)


def boite_tampon(texte, corps, cx, top, rotate=-9, depart=2.6, anneau=0.35, theme=None):
    w, h = tampon_dims(texte, corps, theme)
    wr, hr = _rot(w, h, rotate)
    # ring: (w + 0.6 size) x (1 + ring x r), opacity (1 - r) x 0.55: visible while r <= 0.8
    ar_w, ar_h = _rot((w + 0.6 * corps) * (1 + anneau * 0.8), (h + 0.6 * corps) * (1 + anneau * 0.8), rotate)
    hw = max(wr * depart, ar_w) / 2 + 6
    hh = max(hr * depart, ar_h) / 2 + 6
    cy = top + h / 2
    return [cx - hw, cy - hh, cx + hw, cy + hh]


# Measured on the rendered frames of a video (alpha > 0.15): the drop shadow of the cards (0 14px 40px)
# and the entrance spring (the card arrives from the right and overshoots a bit to the left) bite
# 6 to 17 px left of the card edge; the verdict pill (spring damped at 0.38) overshoots
# by 28%; the white frame of the GIFs, 4 px. Entrances from the right that leave the frame
# do not count (nothing to the right of the frame).
OMBRE_CARTE = 24
DEPASSE_PASTILLE = 1.3
OMBRE_PASTILLE = 14


def boite(comp, d):
    """Box [x0, y0, x1, y1] of an overlay from its data (the JSON ones)."""
    if comp == "stamp":
        return boite_tampon(d["text"], d["size"], d["cx"], d["y"], d.get("rotate", -9), d.get("depart", 2.6), d.get("anneau", 0.35), d.get("theme"))
    if comp == "slam":
        s, dep, right = d["size"], d.get("depart", 2.2), d.get("right", 90)
        ws = [largeur(l["text"], s, "display", 500, True) + 0.72 * s for l in d["lines"]]
        wr, hr = _rot(max(ws), 1.35 * s, 1.8)
        n = len(d["lines"])
        x1 = W - right + 8
        return [x1 - wr * dep - 8, d["y"] - (dep - 1) * 0.75 * s, x1, d["y"] + n * 1.5 * s + (n - 1) * 0.2 * s + (dep - 1) * 0.75 * s]
    if comp == "stat-tag":
        right = d.get("right", 90)
        v = f"{d['value']:,}".replace(",", " ")
        wv = largeur(v, d.get("size", 190), "display", 300, False) + (16 + largeur(d["suffix"], 80, "display", 400, True) if d.get("suffix") else 0)
        wl = largeur(d["label"], d.get("labelSize", 38), "sans", 700, False)
        if d.get("labelWidth"):
            wl = min(wl, d["labelWidth"])
        wp = largeur(d["prefix"], 44, "display", 400, True) if d.get("prefix") else 0
        w = 10 + 88 + max(wv, wl, wp)
        h = 50 + (53 if d.get("prefix") else 0) + d.get("size", 190) + 38 * 1.3 * (2 if d.get("labelWidth") and wl >= d["labelWidth"] else 1)
        wr, hr = _rot(w, h, 1.5)
        return [W - right - wr - OMBRE_CARTE, d["y"] - (hr - h) / 2, W - right + (wr - w) / 2, d["y"] + hr]
    if comp == "croyance":
        x, w, s = d["x"], d["w"], d.get("size", 62)
        lw = max(largeur(l, s, "display", 400, True) for l in d["lignes"]) + 82 + 14
        wc = max(w, lw)
        h = 56 + 24 * 1.4 + 10 + len(d["lignes"]) * 1.12 * s
        wr, hr = _rot(wc, h, 1)
        x0, x1 = x - (wr - wc) / 2 - OMBRE_CARTE, x + wc + (wr - wc) / 2
        if d.get("verdict"):
            pw = largeur(d["verdict"], d.get("verdictSize", 40), "sans", 700, False) + 60
            x0 = min(x0, x + w - pw * DEPASSE_PASTILLE - OMBRE_PASTILLE)   # pill aligned right
            h += 18 + d.get("verdictSize", 40) * 1.3 + 28
        return [x0, d["y"] - (hr - h) / 2 - 4, x1, d["y"] + h + 8]
    if comp == "gaufre":
        x, w = d["x"], d.get("w", 460)
        h = 56 + 24 * 1.4 + 4 + 140 + 14 + 354 + 20 + 2 * 34 * 1.2
        wr, hr = _rot(w, h, 1.2)
        return [x - (wr - w) / 2 - OMBRE_CARTE, d["y"] - (hr - h) / 2, x + w + (wr - w) / 2, d["y"] + hr]
    if comp == "gif":
        w = d["w"] + 28
        h = d["w"] * d["srcH"] / d["srcW"] + 28 + (50 if d.get("caption") else 0)
        wr, hr = _rot(w * 1.035, h * 1.035, 2.5)
        cx = d["x"] + w / 2
        return [cx - wr / 2 - 8, d["y"] - (hr - h) / 2 - 30, cx + wr / 2, d["y"] + hr]
    if comp == "sondages":
        if d.get("variante") == "reponse":
            return [d["x"] - OMBRE_CARTE, d["y"], d["x"] + d["w"], d["y"] + 360]
        k = d["w"] / SOND_W
        b = [d["x"], 150 * k + d.get("dy", 0), d["x"] + d["w"], (150 + 400 * (len(d["piles"]) - 1) + 340) * k + d.get("dy", 0)]
        if d.get("tampon"):
            t = boite_tampon(d["tampon"], d["tamponSize"], d["tamponCx"], d["tamponY"], -7, d.get("tamponDepart", 2.6), d.get("anneau", 0.35))
            b = [min(b[0], t[0]), min(b[1], t[1]), max(b[2], t[2]), max(b[3], t[3])]
        return b
    if comp == "lien-description":
        s = d.get("size", 58)
        w = largeur(d.get("text", "Lien en description"), s, "display", 400, True) + 80
        h = 44 + s * 1.15 + 10 + 96 + 12
        x1 = W - d.get("right", 90)
        return [x1 - w - 8, H - d.get("bottom", 120) - h, x1 + 8, H - d.get("bottom", 120) + 12]   # shadow
    raise KeyError(f"unknown geometry for overlay '{comp}'")


SOND_W = 640   # width of the stack drawing at scale 1 (cards from -25 to 615 px)


# --- placement: sizes and places inside the free zone ------------------------------------------
def zone(t0, t1):
    """[x_left, x_right] free for [t0, t1]: from the head (margin included) to the edge."""
    return interdite(t0, t1)[2], W - BORD


def poser(comp, d, t0, t1):
    """Returns (placed data, box). For each component, the largest size that fits
    (capped at the requested one); a text that is too long goes on several lines."""
    xa, xb = zone(t0, t1)
    Zw = xb - xa
    d = dict(d)
    if comp == "stamp":
        # the largest size (72 at most); one more line only if it gains 12 px;
        # the drop (start scale) goes from 1.3 down to 1.1 before the size goes under 56 px
        texte = d["text"].replace("\n", " ")
        maxi = min(72, d.get("size", 72))
        d.setdefault("anneau", 0.15)
        if d.get("theme") == "matrix":   # selection bar: no rotation, no drop, no ring
            d["rotate"], d["anneau"] = 0, 0
        rot = d.get("rotate", -9)
        best = None
        for n in (1, 2, 3):
            t = "\n".join(lignes_equilibrees(texte, n, mini=1))
            if t.count("\n") != n - 1:
                continue
            for dep in ((1.0,) if d.get("theme") == "matrix" else (1.3, 1.2, 1.1)):
                s = maxi
                while s > 30 and (lambda b: b[2] - b[0])(boite_tampon(t, s, 0, 0, rot, dep, d["anneau"], d.get("theme"))) > Zw:
                    s -= 1
                if s >= 56:
                    break
            if best is None or s >= best[0] + 12:
                best = (s, t, dep)
        d["size"], d["text"], d["depart"] = best
        d["cx"] = round((xa + xb) / 2)
        d.pop("x", None)
    elif comp == "slam":
        right = W - xb
        d["right"] = right
        s = d.get("size", 84)
        d.setdefault("depart", 1.3)
        while s > 30:
            d["size"] = s
            b = boite("slam", d)
            if b[0] >= xa:
                break
            s -= 1
    elif comp == "stat-tag":
        d["right"] = W - xb
        lw = d.get("labelWidth", 520)
        while lw > 200:
            d["labelWidth"] = lw
            if boite("stat-tag", d)[0] >= xa:
                break
            lw -= 10
        s = d.get("size", 190)
        while boite("stat-tag", d)[0] < xa and s > 90:
            s -= 5
            d["size"] = s
    elif comp == "croyance":
        maxi = d.get("size", 62)
        brut = " ".join(d["lignes"])
        n0 = len(d["lignes"])
        orig = list(d["lignes"])
        d["w"] = min(d.get("w", 560), Zw)
        while True:
            d["x"] = xb - d["w"]
            best = None
            for n in range(n0, n0 + 3):
                ls = orig if n == n0 else lignes_equilibrees(brut, n)
                s = maxi
                while s > 32 and max(largeur(l, s, "display", 400, True) for l in ls) + 96 > d["w"]:
                    s -= 1
                if best is None or s > best[0] + 4:
                    best = (s, ls)
            d["size"], d["lignes"] = best
            if boite("croyance", {**d, "verdict": None})[0] >= xa or d["w"] < 300:
                break
            d["w"] -= 2
        if d.get("verdict"):
            vs = 40
            while vs > 24 and boite("croyance", {**d, "verdictSize": vs})[0] < xa:
                vs -= 1
            d["verdictSize"] = vs
    elif comp == "gaufre":
        d["w"] = min(d.get("w", 460), Zw)
        while True:
            d["x"] = xb - d["w"]
            if boite("gaufre", d)[0] >= xa or d["w"] <= 432:
                break
            d["w"] -= 2
    elif comp == "gif":
        w = d.get("w", 440)
        while True:
            d["w"] = w
            d["x"] = round(xb - (w + 28) - 8)
            if boite("gif", d)[0] >= xa or w < 240:
                break
            w -= 4
    elif comp == "sondages":
        if d.get("variante") == "reponse":
            d["w"] = min(d.get("w", 560), Zw - OMBRE_CARTE)
            d["x"] = xb - d["w"]
        else:
            d["w"] = min(SOND_W, Zw)
            d["x"] = xb - d["w"]
            if d.get("tampon"):
                d["tamponCx"] = round((xa + xb) / 2)
                d.setdefault("tamponY", 470)
                d.setdefault("tamponDepart", 1.3)
                d.setdefault("anneau", 0.15)
                st, _ = poser("stamp", {"text": d["tampon"], "size": d.get("tamponSize", 66), "y": d["tamponY"], "rotate": -7,
                                        "depart": d["tamponDepart"], "anneau": d["anneau"]}, t0, t1)
                d["tampon"], d["tamponSize"], d["tamponDepart"] = st["text"], st["size"], st["depart"]
    elif comp == "lien-description":
        d["right"] = W - xb
        d.setdefault("bottom", 50)
        s = d.get("size", 52)
        while s > 30:
            d["size"] = s
            if boite("lien-description", d)[0] >= xa:
                break
            s -= 1
    return d, boite(comp, d)


def controle(SEG, tc=lambda t: f"{t:.2f}"):
    """Overflows onto the head: [(id, box, forbidden zone)]. The overlays of the plan are the alpha
    scenes and the lower thirds; run after habillage.tenue()."""
    fautes = []
    for x in SEG:
        if x.get("type") == "scene" and not x.get("alpha"):
            continue
        if x.get("component") == "volet":
            continue
        comp = x.get("component") or x.get("kind")
        t0 = x["_start"]
        t1 = t0 + x["durationSec"]
        b = boite(comp, x["data"])
        z = interdite(t0, t1)
        if coupe(b, z) or b[0] < 0 or b[2] > W or b[1] < 0 or b[3] > H:
            fautes.append((x["id"], [round(v) for v in b], z, tc(t0)))
    return fautes


# --- check on rendered frames ----------------------------------------------------------------
def boite_alpha(png, seuil=0.15):
    """Box of the visible pixels of a rendered overlay (RGBA PNG, scaled to 1920×1080)."""
    from PIL import Image
    im = Image.open(png)
    if im.mode != "RGBA":
        return None
    a = im.getchannel("A").point(lambda v: 255 if v > seuil * 255 else 0)
    bb = a.getbbox()
    if not bb:
        return None
    k = W / im.width
    return [bb[0] * k, bb[1] * k, bb[2] * k, bb[3] * k]


# --- head measure ----------------------------------------------------------------------------
def _binaire():
    src = ICI / "tete.swift"
    cache = Path.home() / "Library" / "Caches" / "overlays"
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"tete-{int(src.stat().st_mtime)}"
    if not out.exists():
        subprocess.run(["swiftc", "-O", str(src), "-o", str(out)], check=True)
    return out


def mesurer(rush, timeline, work):
    from PIL import Image, ImageDraw
    import statistics as st
    clips = json.loads(Path(timeline).read_text())
    tmp = Path(tempfile.mkdtemp(prefix="tetes-"))
    jobs = []
    for i, c in enumerate(clips):
        d = c["src_out"] - c["src_in"]
        for f in (0.1, 0.35, 0.6, 0.9):
            out = tmp / f"c{i:02d}-{f:.2f}.jpg"
            # several clips in the sequence: each segment carries its media, stored next to the first clip
            src = Path(rush).with_name(c["media"]) if c.get("media") else Path(rush)
            subprocess.run(["nice", "-n", "10", "ffmpeg", "-v", "error", "-ss", f"{c['src_in'] + f * d:.3f}", "-i", str(src),
                            "-frames:v", "1", "-q:v", "3", "-vf", f"scale={W}:{H}", str(out)], check=True)
            jobs.append([i, f, 0, 0, str(out)])
    (tmp / "frames.json").write_text(json.dumps(jobs))
    subprocess.run(["nice", "-n", "10", str(_binaire()), str(tmp / "frames.json"), str(tmp / "vision.json")], check=True)
    vis = {r["file"]: r for r in json.loads((tmp / "vision.json").read_text())}
    GW, GH = 384, 216
    CX, CY = W / GW, H / GH
    par_image = []
    for i, f, _, _, path in jobs:
        r = vis.get(path)
        if not r or not r["faces"]:
            par_image.append({"clip": i, "f": f, "path": path})
            continue
        fx0, fy0, fx1, fy1, _ = max(r["faces"], key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        fx0, fx1, fy0, fy1 = fx0 * W, fx1 * W, fy0 * H, fy1 * H
        fw, fh = fx1 - fx0, fy1 - fy0
        m = r.get("mask") or []
        # top of the hair: middle columns of the face (a raised hand at the side does not count)
        cx0, cx1 = int((fx0 + 0.2 * fw) / CX), int((fx1 - 0.2 * fw) / CX)
        top = next((gy for gy in range(GH) if m and m[gy][cx0:cx1 + 1].count("1") >= 2), None)
        # width: hair and ears, from the top to the eyes, continuous run around the middle of the
        # face (a hand that does not touch the head does not enter), at most ±45% of the face
        hx0, hx1 = fx0, fx1
        lim0, lim1 = max(0, int((fx0 - 0.45 * fw) / CX)), min(GW - 1, int((fx1 + 0.45 * fw) / CX))
        mid = int((fx0 + fx1) / 2 / CX)
        if top is not None:
            for gy in range(top, min(GH, int((fy0 + 0.35 * fh) / CY))):
                row = m[gy]
                if row[mid] != "1":
                    continue
                a = b = mid
                while a - 1 >= lim0 and row[a - 1] == "1":
                    a -= 1
                while b + 1 <= lim1 and row[b + 1] == "1":
                    b += 1
                hx0, hx1 = min(hx0, a * CX), max(hx1, (b + 1) * CX)
        ht = top * CY if top is not None else fy0 - 0.45 * fh
        par_image.append({"clip": i, "f": f, "path": path, "tete": [round(hx0), round(ht), round(hx1), round(fy1 + 0.3 * fh)]})
    boites = {}
    for p in par_image:
        if "tete" in p:
            c = boites.get(p["clip"], [9e9, 9e9, -9e9, -9e9])
            t = p["tete"]
            boites[p["clip"]] = [min(c[0], t[0]), min(c[1], t[1]), max(c[2], t[2]), max(c[3], t[3])]
    med = [round(st.median(b[k] for b in boites.values())) for k in range(4)]
    out = []
    for i, c in enumerate(clips):
        imgs = [p for p in par_image if p["clip"] == i]
        repli = any("tete" not in p for p in imgs) or i not in boites
        b = med if repli else boites[i]
        mx, my = MARGE * W, MARGE * H
        out.append({"clip": i, "seq_in": round(c["seq_in"], 3), "seq_out": round(c["seq_out"], 3), "tete": b, "repli": repli,
                    "zone_interdite": [round(max(0, b[0] - mx)), round(max(0, b[1] - my)), round(min(W, b[2] + mx)), round(min(H, b[3] + my))]})
    work = Path(work)
    (work / "tetes.json").write_text(json.dumps({"rush": Path(rush).name, "marge": MARGE, "clips": out}, indent=0))
    # contact sheet: boxes per frame (yellow) and forbidden zone of the segment (red)
    w, h, cols = 320, 180, 6
    sheet = Image.new("RGB", (cols * (w + 4) + 4, ((len(out) + cols - 1) // cols) * (h + 16) + 4), (30, 30, 30))
    dr = ImageDraw.Draw(sheet)
    for k, c in enumerate(out):
        imgs = [p for p in par_image if p["clip"] == k]
        best = max(imgs, key=lambda p: (p.get("tete", [0, 0, 0, 0])[2] - p.get("tete", [0, 0, 0, 0])[0]))
        im = Image.open(best["path"]).convert("RGB")
        d = ImageDraw.Draw(im)
        for p in imgs:
            if "tete" in p and not c["repli"]:
                d.rectangle(p["tete"], outline=(255, 255, 0), width=4)
        d.rectangle(c["zone_interdite"], outline=(255, 0, 0), width=7)
        x, y = 4 + (k % cols) * (w + 4), 4 + (k // cols) * (h + 16)
        sheet.paste(im.resize((w, h)), (x, y))
        dr.text((x + 2, y + h + 2), f"segment {k} seq {c['seq_in']:.0f}s zone {c['zone_interdite']}" + (" fallback" if c["repli"] else ""), fill=(230, 230, 230))
    sheet.save(work / "tetes-controle.jpg", quality=80)
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()
    xs = [c["zone_interdite"][2] for c in out]
    print(f"{len(out)} segments, {sum(c['repli'] for c in out)} on fallback; right edge of the forbidden zone: "
          f"median {sorted(xs)[len(xs) // 2]} px, maximum {max(xs)} px -> {work / 'tetes.json'}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 4 and a[0] == "mesurer":
        mesurer(*a[1:])
    else:
        print(__doc__)
        sys.exit(1)
