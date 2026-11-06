#!/usr/bin/env python3
"""Edits a 3-file OBS shoot (cam and screen recorded separately) Tella-style,
as a Premiere (FCP7) XML: the head full frame when the speaker talks to the audience, the screen large
with its thumbnail when they operate it, the image next to their face when they comment on it,
zooms into the image. The rough-cut cuts are applied to both files.

Usage, layout grammar and pitfalls: section "Tella-style edit" of the overlays SKILL.md.

    python3 montage-tella.py --cam "<... 3 cam.mov>" --ecran "<... 2 screen.mov>" \\
        --derush "<... 3 cam_Derush_v1_work>" --plan plan-dispositions.json \\
        --out "<video folder>/<title>_Montage_v1.xml" [--apercu <folder>]

Tracks (bottom to top): V1 background, V2 screen, V3 cam, V4 corners (rounds the cards during the
still shots, absent during the moves).
Animated background by default (`--fond papier|nuit|brume`, FondAnime composition of the
motion-design workshop, seamless loop of `--periode` s): V1 = the background loop, or during
the still shots the "background + card shadows" loop of the layout; V4 = the loop
of the corners alone (ProRes 4444, transparent elsewhere). All loops are placed in
phase: in point = start of the clip modulo the period. `--fond fixe`: the old
dark gradient as a PNG and the PNG frame with holes (background + shadows + corners).
A1-A2: voice of the cam. Markers: one per layout, plus the rough-cut doubts.
`--habillage <xml>`: the XML of `render-segments.py --no-rush` (b-rolls, scenes, wipes,
sound effects) goes on top, V5 and up, A3 and up: a single sequence to import.
With `--apercu` and without `--instants`, the contact sheet shows each overlay element composited
on the edit (one thumbnail per element, 12 per sheet).
`--sequence <name>` (+ `--prproj`, default: the .prproj of the folder): the cuts come from the
editor's sequence after their pass, not from the rough cut; re-cut at the rough-cut boundaries to keep
the 100/112% alternation of the cam.

Layouts (3840×2160 canvas):
  CAM    full-frame cam; at each rough-cut cut, the cam alternates 100% and 112% (centered
         on the face) to hide the jump cut.
  ECRAN  whole screen as a card on the left, 4:5 portrait thumbnail of the cam on the right, at the bottom.
  ZOOM   same cards as ECRAN, the screen zooms into the photo area (Lightroom Loupe).
  COTE   the photo (Loupe area) and the face side by side, same heights.

Keyframes (matched to a real Premiere export):
  center.horiz = offset of the clip center in sequence pixels / width of the SOURCE,
  center.vert  = vertical offset / height of the SOURCE (negative = upward).
  The reference of <when> (start of the clip, media, or sequence) is not documented: each
  keyframe is written in all three references, in three disjoint blocks. Only the block
  of the right reference falls inside the clip; the others stay outside the clip, without effect.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import math
import subprocess
import sys
import urllib.parse
import uuid
import wave
from datetime import date
from pathlib import Path

import numpy as np

W, H, FPS = 3840, 2160, 30
TICKS = 254016000000
ATELIER = Path(__file__).resolve().parents[2] / "motion-design"
FOND_TSX = ATELIER / "src" / "illustration" / "compositions" / "FondAnime.tsx"

# --- geometry (sequence pixels; sources: screen 2560×1440, cam 3840×2160) -----------
# FACE, CAM_CARTE, LOUPE and ECRAN_SRC were measured on the original setup: measure them again
# on a frame of YOUR take (face position, area of the app shown, bars to remove).
M, G = 120, 72                     # outer margin, gap between cards
RAYON = 40                         # a single corner radius for all the cards
FACE = (2000.0, 1000.0)            # face in the cam (measured on 9 frames of the take)
CAM_CARTE = (1250, 150, 2750, 2025)  # 4:5 crop around the face (cam source)
LOUPE = (368, 120, 2188, 1144)     # Lightroom Loupe area in 16:9 (screen source)
ECRAN_SRC = (55, 62, 2505, 1440)   # screen without the macOS menu bar (white, rows 0 to 61), 16:9
PUNCH = 1.12

def _ecran_layout():
    wc = 600; hc = wc * 5 / 4
    ws = W - 2 * M - G - wc; hs = ws * 9 / 16
    y0 = (H - hs) / 2
    ecran = (M, y0, M + ws, y0 + hs)
    cam = (M + ws + G, y0 + hs - hc, M + ws + G + wc, y0 + hs)
    return ecran, cam

def _cote_layout():
    ws = (W - 2 * M - G) / 1.45; wc = 0.45 * ws; h = ws * 9 / 16
    y0 = (H - h) / 2
    return (M, y0, M + ws, y0 + h), (M + ws + G, y0, M + ws + G + wc, y0 + h)

E_DST, C_DST = _ecran_layout()
CO_E_DST, CO_C_DST = _cote_layout()

def rects(layout: str, src_e: tuple, src_c: tuple, interval: int):
    """(screen src, screen dst, cam src, cam dst) of a layout."""
    if layout == "CAM":
        if interval % 2:
            fx, fy = FACE
            cam_src = (fx - fx / PUNCH, fy - fy / PUNCH, fx + (src_c[0] - fx) / PUNCH, fy + (src_c[1] - fy) / PUNCH)
        else:
            cam_src = (0, 0, src_c[0], src_c[1])
        return None, None, cam_src, (0, 0, W, H)
    if layout == "ECRAN":
        return ECRAN_SRC, E_DST, CAM_CARTE, C_DST
    if layout == "ZOOM":
        return LOUPE, E_DST, CAM_CARTE, C_DST
    if layout == "COTE":
        return LOUPE, CO_E_DST, CAM_CARTE, CO_C_DST
    raise ValueError(layout)

# --- curves --------------------------------------------------------------------------------
def bezier(x1, y1, x2, y2):
    def f(t):
        lo, hi = 0.0, 1.0
        for _ in range(40):
            u = (lo + hi) / 2
            x = 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u ** 2 * x2 + u ** 3
            lo, hi = (u, hi) if x < t else (lo, u)
        u = (lo + hi) / 2
        return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u ** 2 * y2 + u ** 3
    return f

DOUX = bezier(0.42, 0, 0.58, 1)

def ressort_table(n=19, m=2.25, k=200.0, c=40.0):
    """Spring of the Cap zoom sampled over n frames, last one forced to 1."""
    x, v, out, sub = 0.0, 0.0, [], 40
    dt = 1 / FPS / sub
    for _ in range(n):
        for _ in range(sub):
            a = (-k * (x - 1) - c * v) / m
            v += a * dt; x += v * dt
        out.append(x)
    out[-1] = 1.0
    return out

RESSORT = ressort_table()

def duree_transition(a: str, b: str) -> int:
    if {a, b} == {"ECRAN", "ZOOM"}:
        return len(RESSORT)
    return 15 if "CAM" in (a, b) else 12

def courbe(a: str, b: str, i: int, n: int) -> float:
    if {a, b} == {"ECRAN", "ZOOM"}:
        return RESSORT[min(i, n) - 1]
    return DOUX(min(1.0, i / n))

# --- Basic Motion -----------------------------------------------------------------------------
def lerp(a, b, e):
    return a + (b - a) * e

def etat(src, dst):
    s = (dst[2] - dst[0]) / (src[2] - src[0])
    c = ((src[0] + src[2]) / 2, (src[1] + src[3]) / 2)
    return src, dst, s, c

def melange(A, B, e):
    (_, da, sa, ca), (_, db, sb, cb) = A, B
    d = tuple(lerp(x, y, e) for x, y in zip(da, db))
    s = math.exp(lerp(math.log(sa), math.log(sb), e))
    c = (lerp(ca[0], cb[0], e), lerp(ca[1], cb[1], e))
    hw, hh = (d[2] - d[0]) / s / 2, (d[3] - d[1]) / s / 2
    return (c[0] - hw, c[1] - hh, c[0] + hw, c[1] + hh), d, s, c

def params(st, sw, sh):
    """State (src, dst, scale, src center) -> Premiere parameters."""
    src, d, s, c = st
    px = (d[0] + d[2]) / 2 - s * (c[0] - sw / 2)
    py = (d[1] + d[3]) / 2 - s * (c[1] - sh / 2)
    x0, y0 = max(0.0, src[0]), max(0.0, src[1])
    x1, y1 = min(float(sw), src[2]), min(float(sh), src[3])
    return {
        "scale": round(100 * s, 4),
        "h": round((px - W / 2) / sw, 6), "v": round((py - H / 2) / sh, 6),
        "l": round(100 * x0 / sw, 4), "t": round(100 * y0 / sh, 4),
        "r": round(100 * (sw - x1) / sw, 4), "b": round(100 * (sh - y1) / sh, 4),
    }

# --- inputs -----------------------------------------------------------------------------------
def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate,nb_frames,channels,sample_rate",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True)
    st = json.loads(out.stdout)["streams"]
    v = next(s for s in st if s["codec_type"] == "video")
    a = next((s for s in st if s["codec_type"] == "audio"), None)
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    return {"w": int(v["width"]), "h": int(v["height"]), "fps": num / den, "frames": int(v["nb_frames"]),
            "ch": int(a["channels"]) if a else 0, "sr": int(a["sample_rate"]) if a else 48000}

def decalage_voix(cam: Path, ecran: Path, t0: float = 300.0, dur: float = 90.0) -> float:
    """Delay of the screen voice behind the cam voice (s): correlation over 90 s."""
    def lire(p):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t0), "-t", str(dur), "-i", str(p),
                            "-map", "0:a:0", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                           capture_output=True, check=True)
        return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32)
    a, b = lire(cam), lire(ecran)
    n = min(len(a), len(b))
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    m = 2 * 8000
    best = max(range(-m, m + 1, 2), key=lambda L: float(np.dot(a[m:n - m], b[m + L:n - m + L])))
    return best / 8000

def intervalles(work: Path, duree: float):
    cuts = sorted((c for c in json.loads((work / "cuts_final.json").read_text())["cuts"]
                   if c["decision"] == "disable"), key=lambda c: c["start"])
    keep, pos = [], 0.0
    for c in cuts:
        a = max(c["start"], pos)
        if a > pos:
            keep.append((pos, a))
        pos = max(pos, c["end"])
    if duree - pos > 0.07:
        keep.append((pos, duree))
    out, seq = [], 0
    for a, b in keep:
        if b - a < 0.07:
            continue
        i0, i1 = round(a * FPS), round(b * FPS)
        out.append({"in": i0, "out": i1, "start": seq, "end": seq + i1 - i0})
        seq += i1 - i0
    return out

def clips_de_sequence(prproj: Path, sequence: str, media: str, bornes=()):
    """The rough-cut clips as the editor left them in a sequence of the project (rule zero:
    after their pass, the reference timeline is the .prproj, no longer the rough cut). Reads the track
    that carries the most pieces of `media` (the cam), glues back contiguous pieces (same cuts
    as the rough cut, plus those they added): same shape as `intervalles()`.
    `bornes`: ins and outs of the rough-cut clips (frames of the clip). Two rough-cut clips
    may follow each other without a gap in the clip: glued, they would make only one, and
    the 100/112% alternation of the cam (one per clip) would be shifted for all the rest. So we re-cut
    at these boundaries: the editor's untouched sequence gives back exactly the rough cut."""
    spec = importlib.util.spec_from_file_location("tlp", Path(__file__).resolve().parent / "timeline-from-prproj.py")
    tlp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tlp)
    root, by_id, by_uid = tlp.load(prproj)
    seqs = [x for x in root.iter("Sequence") if (x.findtext("Name") or "") == sequence]
    if len(seqs) != 1:
        sys.exit(f"sequence '{sequence}': {len(seqs)} found in {prproj.name}")
    pistes = []
    for items in tlp.video_tracks(seqs[0], by_id, by_uid):
        rows = [r for r in (tlp.clip_info(it, by_id, by_uid) for it in items) if r and r[4] == media]
        pistes.append(sorted(rows))
    rows = max(pistes, key=len)
    if not rows:
        sys.exit(f"no clip of {media} in '{sequence}'")
    out = []
    for s0, s1, ip, _, _ in rows:
        f0, f1, i0 = round(s0 * FPS), round(s1 * FPS), round(ip * FPS)
        if out and out[-1]["end"] == f0 and out[-1]["out"] == i0:
            out[-1]["end"], out[-1]["out"] = f1, i0 + f1 - f0
        else:
            out.append({"in": i0, "out": i0 + f1 - f0, "start": f0, "end": f1})
    coupes = []
    for c in out:
        cuts = sorted(b for b in bornes if c["in"] < b < c["out"])
        for a, b in zip([c["in"]] + cuts, cuts + [c["out"]]):
            coupes.append({"in": a, "out": b, "start": c["start"] + a - c["in"], "end": c["start"] + b - c["in"]})
    out = coupes
    if out[0]["start"] != 0 or any(a["end"] != b["start"] for a, b in zip(out, out[1:])):
        sys.exit(f"'{sequence}': gap in the {media} track, the cam must cover the whole sequence")
    return out


def rush_vers_montage(t: float, clips) -> int:
    f = round(t * FPS)
    for c in clips:
        if f < c["in"]:
            return c["start"]
        if f < c["out"]:
            return c["start"] + f - c["in"]
    return clips[-1]["end"]

# --- plan -------------------------------------------------------------------------------------
def construire_plan(plan: dict, mots: list, clips) -> list[dict]:
    segs = []
    for s in plan["segments"]:
        t = mots[s["mot"]]["start"] if "mot" in s else s["rush"]
        segs.append({"f": rush_vers_montage(t, clips), "layout": s["disposition"],
                     "texte": s.get("texte") or " ".join(m["text"] for m in mots[s["mot"]:s["mot"] + 6])})
    segs.sort(key=lambda s: s["f"])
    segs[0]["f"] = 0
    fusion = [segs[0]]
    for s in segs[1:]:
        if s["layout"] != fusion[-1]["layout"]:
            fusion.append(s)
    total = clips[-1]["end"]
    for k, s in enumerate(fusion):
        s["fin"] = fusion[k + 1]["f"] if k + 1 < len(fusion) else total
    # transitions: 0.25 s ahead, inside a single rough-cut clip, otherwise a hard cut
    for k, s in enumerate(fusion):
        if k == 0:
            s["t0"] = s["t1"] = 0
            continue
        n = duree_transition(fusion[k - 1]["layout"], s["layout"])
        cible = s["f"] - 8
        choix = None
        for c in clips:
            for depart in (cible, max(c["start"], s["f"] - 8)):
                if c["start"] <= depart and depart + n <= c["end"] and abs(depart - cible) <= 20:
                    choix = depart
                    break
            if choix is not None:
                break
        if choix is None:   # hard cut at the nearest clip edge
            choix = min((c["start"] for c in clips), key=lambda x: abs(x - s["f"]))
            n = 0
        s["t0"], s["t1"] = choix, choix + n
    return fusion

# --- XML --------------------------------------------------------------------------------------
def url(p: Path) -> str:
    return "file://localhost" + urllib.parse.quote(str(p.resolve()))

def rate(tb=FPS, ntsc="FALSE"):
    return f"<rate><timebase>{tb}</timebase><ntsc>{ntsc}</ntsc></rate>"

def fichier_video(fid: str, p: Path, m: dict) -> str:
    audio = (f"<audio><channelcount>{m['ch']}</channelcount><samplecharacteristics><depth>16</depth>"
             f"<samplerate>{m['sr']}</samplerate></samplecharacteristics></audio>") if m["ch"] else ""
    return (f'<file id="{fid}"><name>{p.name}</name><pathurl>{url(p)}</pathurl>{rate()}'
            f"<duration>{m['frames']}</duration><media><video><samplecharacteristics>{rate()}"
            f"<width>{m['w']}</width><height>{m['h']}</height><anamorphic>FALSE</anamorphic>"
            f"<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>"
            f"</samplecharacteristics></video>{audio}</media></file>")

def fichier_image(fid: str, p: Path) -> str:
    return (f'<file id="{fid}"><name>{p.name}</name><pathurl>{url(p)}</pathurl>{rate(30, "TRUE")}'
            f"<timecode>{rate(30, 'TRUE')}<string>00;00;00;00</string><frame>0</frame>"
            f"<displayformat>DF</displayformat></timecode><media><video><samplecharacteristics>"
            f"{rate(30, 'TRUE')}<width>{W}</width><height>{H}</height><anamorphic>FALSE</anamorphic>"
            f"<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>"
            f"</samplecharacteristics></video></media></file>")

class Fichiers:
    def __init__(self):
        self.vus: set[str] = set()

    def ref(self, fid: str, complet: str) -> str:
        if fid in self.vus:
            return f'<file id="{fid}"/>'
        self.vus.add(fid)
        return complet

def param(pid, nom, valeur, cles=None, vmin=None, vmax=None):
    borne = f"<valuemin>{vmin}</valuemin><valuemax>{vmax}</valuemax>" if vmin is not None else ""
    if isinstance(valeur, tuple):
        val = f"<value><horiz>{valeur[0]}</horiz><vert>{valeur[1]}</vert></value>"
        kf = "".join(f"<keyframe><when>{w}</when><value><horiz>{x[0]}</horiz><vert>{x[1]}</vert></value></keyframe>"
                     for w, x in (cles or []))
    else:
        val = f"<value>{valeur}</value>"
        kf = "".join(f"<keyframe><when>{w}</when><value>{x}</value></keyframe>" for w, x in (cles or []))
    return (f'<parameter authoringApp="PremierePro"><parameterid>{pid}</parameterid><name>{nom}</name>'
            f"{borne}{val}{kf}</parameter>")

def basic_motion(p0: dict, serie: list[dict] | None, decal: list[int]) -> str:
    """p0: fixed values; serie: one value per frame of the clip (transition), written in
    each of the references `decal` (0 = start of the clip, in = media, start = sequence)."""
    def cles(k):
        if not serie or all(x[k] == serie[0][k] for x in serie):
            return None
        return [(d + i, x[k]) for d in decal for i, x in enumerate(serie)]
    def cles_c():
        if not serie or all((x["h"], x["v"]) == (serie[0]["h"], serie[0]["v"]) for x in serie):
            return None
        return [(d + i, (x["h"], x["v"])) for d in decal for i, x in enumerate(serie)]
    return ("<filter><effect><name>Basic Motion</name><effectid>basic</effectid>"
            "<effectcategory>motion</effectcategory><effecttype>motion</effecttype>"
            "<mediatype>video</mediatype><pproBypass>false</pproBypass>"
            + param("scale", "Scale", p0["scale"], cles("scale"), 0, 1000)
            + param("rotation", "Rotation", 0, None, -8640, 8640)
            + param("center", "Center", (p0["h"], p0["v"]), cles_c())
            + param("centerOffset", "Anchor Point", (0, 0))
            + param("antiflicker", "Anti-flicker Filter", 0, None, "0.0", "1.0")
            + param("leftcrop", "Left", p0["l"], cles("l"), "0.0", "100.0")
            + param("topcrop", "Top", p0["t"], cles("t"), "0.0", "100.0")
            + param("rightcrop", "Right", p0["r"], cles("r"), "0.0", "100.0")
            + param("bottomcrop", "Bottom", p0["b"], cles("b"), "0.0", "100.0")
            + "</effect></filter>")

def clipitem(cid, nom, fichier, i0, i1, s0, s1, filtre="", piste_audio=None, alpha=None):
    src = (f"<sourcetrack><mediatype>audio</mediatype><trackindex>{piste_audio}</trackindex></sourcetrack>"
           if piste_audio else "")
    al = (f"<alphatype>{'straight' if alpha else 'none'}</alphatype><pixelaspectratio>square</pixelaspectratio>"
          "<anamorphic>FALSE</anamorphic>") if alpha is not None else ""
    return (f'<clipitem id="{cid}"><name>{nom}</name><enabled>TRUE</enabled><duration>{i1 - i0}</duration>'
            f"{rate()}<start>{s0}</start><end>{s1}</end><in>{i0}</in><out>{i1}</out>"
            f"<pproTicksIn>{i0 * TICKS // FPS}</pproTicksIn><pproTicksOut>{i1 * TICKS // FPS}</pproTicksOut>"
            f"{al}{fichier}{src}{filtre}</clipitem>")

def still(cid, fid, nom, fichier, s0, s1, alpha=False):
    i0 = 90000
    i1 = i0 + max(1, round((s1 - s0) / FPS * 25))
    return (f'<clipitem id="{cid}"><masterclipid>master-{fid}</masterclipid><name>{nom}</name>'
            f"<enabled>TRUE</enabled><duration>1080000</duration>{rate(25)}<start>{s0}</start><end>{s1}</end>"
            f"<in>{i0}</in><out>{i1}</out><pproTicksIn>{i0 * TICKS // 25}</pproTicksIn>"
            f"<pproTicksOut>{i1 * TICKS // 25}</pproTicksOut><alphatype>{'straight' if alpha else 'none'}</alphatype>"
            f"<pixelaspectratio>square</pixelaspectratio><anamorphic>FALSE</anamorphic>{fichier}</clipitem>")

# --- decor ------------------------------------------------------------------------------------
def fond_png(path: Path):
    """Dark radial gradient of the brand (`dark` in Screencast.tsx)."""
    from PIL import Image
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - 0.30 * W) / (1.2 * W)) ** 2 + ((yy - 0.10 * H) / (0.9 * H)) ** 2)
    stops = [(0.0, (0x2E, 0x2B, 0x29)), (0.55, (0x1A, 0x1A, 0x1A)), (1.0, (0x0E, 0x0E, 0x0E))]
    img = np.zeros((H, W, 3), np.float32)
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        m = (d >= p0) & (d <= p1) if p1 < 1 else d >= p0
        e = np.clip((d - p0) / (p1 - p0), 0, 1)[..., None]
        img = np.where(m[..., None], np.array(c0) + (np.array(c1) - np.array(c0)) * e, img)
    bruit = np.random.default_rng(7).normal(0, 0.6, (H, W, 1))   # anti-banding
    Image.fromarray(np.clip(img + bruit, 0, 255).astype(np.uint8)).save(path)
    return Image.open(path).convert("RGBA")

def cadre_png(path: Path, fond, cartes: list[tuple]):
    """Background + shadows, with a rounded-corner hole per card: placed on top of the cards."""
    from PIL import Image, ImageDraw, ImageFilter
    ombre = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(ombre)
    for x0, y0, x1, y1 in cartes:
        d.rounded_rectangle((x0, y0 + 80, x1, y1 + 80), RAYON, fill=115)
    ombre = ombre.filter(ImageFilter.GaussianBlur(90))
    noir = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    img = Image.composite(noir, fond, ombre)
    trou = Image.new("L", (W, H), 255)
    dt = ImageDraw.Draw(trou)
    for x0, y0, x1, y1 in cartes:
        dt.rounded_rectangle((round(x0), round(y0), round(x1) - 1, round(y1) - 1), RAYON, fill=0)
    img.putalpha(trou)
    img.save(path)

# --- animated background (motion-design workshop) ----------------------------------------------
def fichier_de_travail(dossier: Path, nom: str) -> Path:
    """Pass-through file, like render-segments.py: in MONTAGE_DEPOT (NOT a synced folder,
    same disk, atomic final rename) if the variable is set, otherwise hidden in dossier."""
    depot = os.environ.get("MONTAGE_DEPOT")
    if depot and Path(depot).is_dir():
        d = Path(depot) / f"{date.today():%Y-%m-%d}-rendus"
        d.mkdir(exist_ok=True)
        return d / f"{uuid.uuid4().hex[:8]}-{nom}"
    return dossier / f".{nom}"

def rendre_boucle(sortie: Path, props: dict, alpha: bool) -> None:
    """Renders a FondAnime loop, unless the same one (props + code + grain) is already there.
    A redone file keeps its name (atomic replacement): Premiere reloads it."""
    grain = ATELIER / "public" / "fond" / "grain.png"
    if not grain.exists():  # the kit does not ship the grain (7 MB): its synth recipes build it once
        subprocess.run([sys.executable, str(ATELIER / "scripts" / "make-grain.py")], check=True)
    sig = hashlib.sha1((json.dumps(props, sort_keys=True) + FOND_TSX.read_text()
                        + str(grain.stat().st_size)).encode()).hexdigest()[:16]
    registre = sortie.parent / "fonds.json"
    vus = json.loads(registre.read_text()) if registre.exists() else {}
    if sortie.exists() and vus.get(sortie.name) == sig:
        return
    pj = fichier_de_travail(sortie.parent, f"props-{sortie.stem}.json")
    pj.write_text(json.dumps(props))
    tmp = fichier_de_travail(sortie.parent, f"rendu-{sortie.name}")
    cmd = ["npx", "remotion", "render", str(ATELIER / "src" / "index.ts"), "FondAnime", f"--output={tmp}",
           f"--props={pj}", "--muted", "--log=warn", "--image-format=png", "--concurrency=4"]
    cmd += (["--codec=prores", "--prores-profile=4444", "--pixel-format=yuva444p10le"] if alpha
            else ["--codec=h264", "--crf=16"])
    print(f"  render {sortie.name} ...", flush=True)
    r = subprocess.run(["nice"] + cmd, cwd=ATELIER, capture_output=True, text=True)
    pj.unlink(missing_ok=True)
    if r.returncode:
        tmp.unlink(missing_ok=True)
        sys.exit(f"FondAnime render failed:\n{r.stderr[-2000:]}")
    os.replace(tmp, sortie)
    vus[sortie.name] = sig
    registre.write_text(json.dumps(vus, indent=1, ensure_ascii=False))

def boucle(cid: str, fichier_def, nom: str, s0: int, s1: int, n: int, alpha: bool) -> list[str]:
    """Clips of a loop of n frames between s0 and s1, in phase with the sequence
    (in point = s modulo n), cut at each end of loop."""
    out, s = [], s0
    while s < s1:
        i0 = s % n
        e = min(s1, s + n - i0)
        out.append(clipitem(f"{cid}-{s}", nom, fichier_def(), i0, i0 + e - s, s, e, alpha=alpha))
        s = e
    return out

# --- edit -------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam", required=True, type=Path)
    ap.add_argument("--ecran", required=True, type=Path)
    ap.add_argument("--derush", required=True, type=Path)
    ap.add_argument("--plan", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--decalage-ecran", default="auto")
    ap.add_argument("--nom", default=None)
    ap.add_argument("--apercu", type=Path, default=None, help="contact sheet of composited frames for checking")
    ap.add_argument("--instants", type=float, nargs="*", default=None,
                    help="with --apercu: edit seconds to composite (instead of the first 12 shots)")
    ap.add_argument("--reduction", type=int, default=4, help="with --apercu: 1 = full resolution")
    ap.add_argument("--fond", default="papier", choices=["papier", "nuit", "brume", "fixe"],
                    help="animated background (FondAnime variant) or 'fixe' (dark gradient as a PNG)")
    ap.add_argument("--periode", type=float, default=20.0, help="length of the animated background loop (s)")
    ap.add_argument("--prproj", type=Path, default=None,
                    help="with --sequence: take the cuts from this sequence of the project (the editor's pass)")
    ap.add_argument("--sequence", default=None, help="name of the project sequence that is authoritative")
    ap.add_argument("--habillage", type=Path, default=None,
                    help="XML of render-segments --no-rush: its tracks go on top of the edit")
    a = ap.parse_args()

    mc, me = probe(a.cam), probe(a.ecran)
    for m in (mc, me):
        if abs(m["fps"] - FPS) > 0.01:
            sys.exit(f"frame rate {m['fps']}: only 30 fps is supported")
    dec = decalage_voix(a.cam, a.ecran) if a.decalage_ecran == "auto" else float(a.decalage_ecran)
    off = round(dec * FPS)
    print(f"screen lags {dec:+.3f} s behind the cam: screen in = cam in {off:+d} frame(s)")

    meta = json.loads((a.derush / "meta.json").read_text())
    if a.sequence:
        bornes = {x for c in intervalles(a.derush, meta["duration_seconds"]) for x in (c["in"], c["out"])}
        clips = clips_de_sequence(a.prproj or next(a.out.parent.glob("*.prproj")), a.sequence, a.cam.name, bornes)
        print(f"cuts read from '{a.sequence}': {len(clips)} clips, {clips[-1]['end'] / FPS:.2f} s")
    else:
        clips = intervalles(a.derush, meta["duration_seconds"])
    mots = json.loads((a.derush / "words_premiere.json").read_text())
    plan = json.loads(a.plan.read_text())
    segs = construire_plan(plan, mots, clips)
    total = clips[-1]["end"]
    se, sc = (me["w"], me["h"]), (mc["w"], mc["h"])

    def clip_de(f):
        for k, c in enumerate(clips):
            if c["start"] <= f < c["end"]:
                return k
        return len(clips) - 1

    def ecran_tenu(k):
        """The screen of a segment; under a full-frame CAM, that of the next layout."""
        if segs[k]["layout"] != "CAM":
            return segs[k]["layout"]
        for j in list(range(k + 1, len(segs))) + list(range(k - 1, -1, -1)):
            if segs[j]["layout"] != "CAM":
                return segs[j]["layout"]
        return "ECRAN"

    def etats(f):
        ci = clip_de(f)
        k = max(i for i, s in enumerate(segs) if s["t0"] <= f)
        s = segs[k]
        lb = s["layout"]
        se_b, de_b, scs_b, dc_b = rects(ecran_tenu(k), se, sc, ci)
        _, _, csrc_b, cdst_b = rects(lb, se, sc, ci)
        E_b, C_b = etat(se_b, de_b), etat(csrc_b, cdst_b)
        if f >= s["t1"] or k == 0:
            return E_b, C_b, lb, False
        la = segs[k - 1]["layout"]
        se_a, de_a, _, _ = rects(ecran_tenu(k - 1), se, sc, ci)
        _, _, csrc_a, cdst_a = rects(la, se, sc, ci)
        E_a, C_a = etat(se_a, de_a), etat(csrc_a, cdst_a)
        if lb == "CAM":  # the cam covers the screen: the screen does not move
            E_b = E_a
        n = s["t1"] - s["t0"]
        e = courbe(la, lb, f - s["t0"] + 1, n)
        return melange(E_a, E_b, e), melange(C_a, C_b, e), lb, True

    # splitting: boundaries of the rough-cut clips + starts/ends of transitions
    coupes = sorted({s["t0"] for s in segs} | {s["t1"] for s in segs})
    morceaux = []
    for c in clips:
        bornes = [c["start"]] + [x for x in coupes if c["start"] < x < c["end"]] + [c["end"]]
        for s0, s1 in zip(bornes, bornes[1:]):
            morceaux.append((c, s0, s1))

    dossier = a.out.parent / "Montage"
    dossier.mkdir(exist_ok=True)
    anime = a.fond != "fixe"
    CARTES = {"ECRAN": [E_DST, C_DST], "COTE": [CO_E_DST, CO_C_DST]}
    if anime:
        n_boucle = round(a.periode * FPS)
        boucles = {}
        for cle, mode, cartes, alpha in (("fond", "fond", [], False),
                                         ("ombre-ecran", "ombre", CARTES["ECRAN"], False),
                                         ("ombre-cote", "ombre", CARTES["COTE"], False),
                                         ("coins-ecran", "coins", CARTES["ECRAN"], True),
                                         ("coins-cote", "coins", CARTES["COTE"], True)):
            sortie = dossier / f"{cle}-{a.fond}.{'mov' if alpha else 'mp4'}"
            rendre_boucle(sortie, {"variante": a.fond, "mode": mode, "cartes": [list(c) for c in cartes],
                                   "rayon": RAYON, "periode": a.periode, "ondes": True}, alpha)
            m = probe(sortie)
            if m["frames"] != n_boucle or (m["w"], m["h"]) != (W, H):
                sys.exit(f"{sortie.name}: {m['frames']} frames {m['w']}×{m['h']}, expected {n_boucle} at {W}×{H}")
            boucles[cle] = (sortie, m)
        fond_p, pngs = None, {}
    else:
        fond_p = dossier / "fond.png"
        fond = fond_png(fond_p)
        pngs = {"ECRAN": dossier / "cadre-ecran.png", "COTE": dossier / "cadre-cote.png"}
        cadre_png(pngs["ECRAN"], fond, CARTES["ECRAN"])
        cadre_png(pngs["COTE"], fond, CARTES["COTE"])
        pngs["ZOOM"] = pngs["ECRAN"]

    F = Fichiers()
    fc, fe = fichier_video("file-cam", a.cam, mc), fichier_video("file-ecran", a.ecran, me)
    v_ecran, v_cam, a1, a2 = [], [], [], []
    n_cles = 0
    for i, (c, s0, s1) in enumerate(morceaux):
        i0 = c["in"] + s0 - c["start"]
        i1 = i0 + s1 - s0
        Es, Cs, lay, trans = etats(s0)
        if trans:
            serie = [etats(f) for f in range(s0, s1)]
            pe = [params(x[0], *se) for x in serie]
            pc = [params(x[1], *sc) for x in serie]
            n_cles += len(serie)
        else:
            pe = pc = None
        ie0, ie1 = i0 + off, i1 + off
        nom = f"{lay}{' (transition)' if trans else ''}"
        v_ecran.append(clipitem(f"ecran-{i}", f"{nom} · {a.ecran.name}", F.ref("file-ecran", fe), ie0, ie1, s0, s1,
                                basic_motion(params(Es, *se), pe, [0, ie0, s0])))
        v_cam.append(clipitem(f"cam-{i}", f"{nom} · {a.cam.name}", F.ref("file-cam", fc), i0, i1, s0, s1,
                              basic_motion(params(Cs, *sc), pc, [0, i0, s0])))
    for k, c in enumerate(clips):
        a1.append(clipitem(f"a1-{k}", a.cam.name, F.ref("file-cam", fc), c["in"], c["out"], c["start"], c["end"], "", 1))
        a2.append(clipitem(f"a2-{k}", a.cam.name, F.ref("file-cam", fc), c["in"], c["out"], c["start"], c["end"], "", 2))

    # frame: during the still shots (± 2 frames), continuous between ECRAN and ZOOM (same cards)
    plages = []
    for k, s in enumerate(segs):
        if s["layout"] == "CAM":
            continue
        png = "COTE" if s["layout"] == "COTE" else "ECRAN"
        d0 = max(0, s["t1"] - (1 if s["t1"] > s["t0"] else 0))
        if k + 1 < len(segs):
            nx = segs[k + 1]
            if {nx["layout"], s["layout"]} == {"ECRAN", "ZOOM"}:   # same cards: the frame stays
                d1 = nx["t1"]
            else:
                d1 = nx["t0"] + (1 if nx["t1"] > nx["t0"] else 0)
        else:
            d1 = total
        if plages and plages[-1][2] == png and plages[-1][1] >= d0:
            plages[-1][1] = max(plages[-1][1], d1)
        else:
            if plages and plages[-1][1] > d0:
                plages[-1][1] = d0
            plages.append([d0, d1, png])
    v_cadre, v_fond = [], []
    if anime:
        def fdef(cle):
            fid = f"file-{cle}"
            return lambda: F.ref(fid, fichier_video(fid, *boucles[cle]))
        t = 0
        for d0, d1, lay in plages + [[total, total, None]]:
            if d0 > t:
                v_fond += boucle(f"fond-{t}", fdef("fond"), boucles["fond"][0].name, t, d0, n_boucle, False)
            if lay:
                cle = lay.lower()
                v_fond += boucle(f"ombre-{d0}", fdef(f"ombre-{cle}"), boucles[f"ombre-{cle}"][0].name, d0, d1, n_boucle, False)
                v_cadre += boucle(f"coins-{d0}", fdef(f"coins-{cle}"), boucles[f"coins-{cle}"][0].name, d0, d1, n_boucle, True)
            t = max(t, d1)
    else:
        for k, (d0, d1, lay) in enumerate(plages):
            png = pngs[lay]
            fid = "file-cadre-cote" if lay == "COTE" else "file-cadre-ecran"
            v_cadre.append(still(f"cadre-{k}", fid, png.name, F.ref(fid, fichier_image(fid, png)), d0, d1, alpha=True))
        v_fond = [still("fond-0", "file-fond", fond_p.name, F.ref("file-fond", fichier_image("file-fond", fond_p)), 0, total)]

    # markers: layouts + rough-cut doubts
    marq = []
    for s in segs:
        marq.append((s["f"], f"{s['layout']}", s["texte"][:80]))
    for cut in json.loads((a.derush / "cuts_final.json").read_text())["cuts"]:
        if cut["decision"] == "flag":
            marq.append((rush_vers_montage(cut["start"], clips), "Doubt",
                         f"DOUBT {cut['type']}: {cut['reason']}"))
    marq.sort()
    markers = "".join(f"<marker><comment>{x[2].replace('&', 'and').replace('<', '')}</comment><name>{x[1]}</name>"
                      f"<in>{x[0]}</in><out>{x[0] + 1}</out></marker>" for x in marq)

    def piste(items):
        return f"<track>{''.join(items)}<enabled>TRUE</enabled><locked>FALSE</locked></track>"

    hab_v, hab_a, hab = habillage(a.habillage, total) if a.habillage else ([], [], [])
    nom = a.nom or a.out.stem
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="5">'
           f'<sequence id="seq-montage"><name>{nom}</name><duration>{total}</duration>{rate()}'
           f"<in>-1</in><out>-1</out><timecode>{rate()}<string>00:00:00:00</string><frame>0</frame>"
           f"<displayformat>NDF</displayformat></timecode><media><video><format><samplecharacteristics>"
           f"{rate()}<width>{W}</width><height>{H}</height><anamorphic>FALSE</anamorphic>"
           f"<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>"
           f"</samplecharacteristics></format>"
           + piste(v_fond) + piste(v_ecran) + piste(v_cam) + piste(v_cadre) + "".join(hab_v)
           + f"</video><audio><numOutputChannels>2</numOutputChannels><format><samplecharacteristics>"
           f"<depth>16</depth><samplerate>{mc['sr']}</samplerate></samplecharacteristics></format>"
           + piste(a1) + piste(a2) + "".join(hab_a) + f"</audio></media>{markers}</sequence></xmeml>\n")

    # safeguards: bounds, then garde_premiere (the HIDDEN check ignores Basic Motion: irrelevant here)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml.split("\n", 2)[2])
    for c in root.iter("clipitem"):
        i0, i1 = int(c.findtext("in")), int(c.findtext("out"))
        s0, s1 = int(c.findtext("start")), int(c.findtext("end"))
        if i1 - i0 < 1 or s1 - s0 < 1 or (c.findtext("rate/timebase") == "30" and i1 - i0 != s1 - s0):
            sys.exit(f"invalid clip {c.get('id')} in={i0} out={i1} start={s0} end={s1}")
    tmp = a.out.with_name(f".{a.out.stem}.verif.xml")
    tmp.write_text(xml)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from garde_premiere import valider_xml
    err = [e for e in valider_xml(tmp) if not e.startswith("HIDDEN")]
    if err:
        tmp.rename(a.out.with_name(f"{a.out.stem}.REFUSE.xml"))
        sys.exit("XML refused:\n  " + "\n  ".join(err))
    tmp.replace(a.out)
    a.out.with_name(f"{a.out.stem}.REFUSE.xml").unlink(missing_ok=True)   # refusal of a previous attempt

    durees = {}
    for k, s in enumerate(segs):
        durees[s["layout"]] = durees.get(s["layout"], 0) + (s["fin"] - s["f"]) / FPS
    secs = sum(1 for s in segs[1:] if s["t1"] == s["t0"])
    print(f"{a.out.name}: {total / FPS / 60:.2f} min, {len(segs)} shots, {len(segs) - 1} changes "
          f"({secs} hard cuts), {len(morceaux)} pieces, {n_cles} transition frames")
    print("  time per layout: " + ", ".join(f"{k} {v / 60:.1f} min" for k, v in durees.items()))
    courts = [(s["f"] / FPS, s["layout"], (s["fin"] - s["f"]) / FPS) for s in segs if s["fin"] - s["f"] < 3 * FPS]
    for t, l, d in courts:
        print(f"  ⚠ short shot: {l} at {t:.1f} s ({d:.1f} s)")

    if hab:
        print(f"  overlays: {len(hab_v)} video tracks ({sum(len(x) for x in hab)} elements), "
              f"{len(hab_a)} sound effect tracks")
    if a.apercu:
        apercu(a, segs, etats, clips, off, se, sc, fond_p, pngs, plages, boucles if anime else None, hab)


def habillage(xml_path: Path, total: int):
    """Tracks of the XML of render-segments --no-rush, ready to lay on top of the edit.
    V1 (empty: the place of the clip) and A1-A2 (empty) are skipped; the other non-empty
    video tracks keep their order. Also returns, for the preview, the clips of each track."""
    import xml.etree.ElementTree as ET
    seq = ET.parse(xml_path).getroot().find("sequence")
    larg = int(seq.findtext("media/video/format/samplecharacteristics/width"))
    haut = int(seq.findtext("media/video/format/samplecharacteristics/height"))
    if (larg, haut) != (W, H) or int(seq.findtext("rate/timebase")) != FPS:
        sys.exit(f"overlays are {larg}×{haut}, expected {W}×{H} at {FPS} fps")
    chemins = {}
    for f in seq.iter("file"):
        if f.findtext("pathurl"):
            chemins[f.get("id")] = Path(urllib.parse.unquote(urllib.parse.urlparse(f.findtext("pathurl")).path))
    vids = seq.findall("media/video/track")[1:]
    auds = seq.findall("media/audio/track")[2:]
    v_xml, a_xml, clips_v = [], [], []
    for t in vids:
        items = t.findall("clipitem") + t.findall("generatoritem")
        if not items:
            continue
        v_xml.append(ET.tostring(t, encoding="unicode"))
        piste = []
        for c in t.findall("clipitem"):
            s0, s1 = int(c.findtext("start")), int(c.findtext("end"))
            if s1 > total:
                sys.exit(f"overlays: {c.findtext('name')} ends at {s1 / FPS:.2f} s, after the end of the edit")
            piste.append({"start": s0, "end": s1, "in": int(c.findtext("in")),
                          "rate": int(c.findtext("rate/timebase")), "nom": c.findtext("name"),
                          "chemin": chemins[c.find("file").get("id")]})
        clips_v.append(piste)
    for t in auds:
        if t.find("clipitem") is not None:
            a_xml.append(ET.tostring(t, encoding="unicode"))
    return v_xml, a_xml, clips_v


def apercu(a, segs, etats, clips, off, se, sc, fond_p, pngs, plages, boucles, hab=()):
    """Contact sheet: each frame is recomposed FROM THE PREMIERE PARAMETERS
    (crop, scale around the clip center, position), as Premiere would do."""
    from PIL import Image, ImageDraw
    k = a.reduction   # 4 : 3840 -> 960
    a.apercu.mkdir(parents=True, exist_ok=True)
    from io import BytesIO

    def image_brute(p: Path, t: float):
        # right at the end of a file (last frame of a loop), -ss sometimes returns
        # nothing: step back one frame, then two
        for recul in (0, 1, 2):
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t - recul / FPS):.3f}", "-i", str(p),
                                  "-frames:v", "1", "-pix_fmt", "rgba", "-f", "image2pipe", "-vcodec", "png", "-"],
                                 capture_output=True, check=True).stdout
            if raw:
                return Image.open(BytesIO(raw)).convert("RGBA")
        sys.exit(f"preview: no frame of {p.name} at {t:.3f} s")

    def image(p: Path, t: float):
        return image_brute(p, t).resize((W // k, H // k))

    def plage(f):
        return next((x[2] for x in plages if x[0] <= f < x[1]), None)

    if boucles:
        n = boucles["fond"][1]["frames"]
        def fond_de(f):
            lay = plage(f)
            return image(boucles[f"ombre-{lay.lower()}" if lay else "fond"][0], (f % n) / FPS)
        def cadre_de(f):
            lay = plage(f)
            return image(boucles[f"coins-{lay.lower()}"][0], (f % n) / FPS) if lay else None
    else:
        fond0 = Image.open(fond_p).convert("RGBA").resize((W // k, H // k))
        cadres = {nm: Image.open(p).convert("RGBA").resize((W // k, H // k)) for nm, p in pngs.items()}
        def fond_de(f):
            return fond0.copy()
        def cadre_de(f):
            lay = plage(f)
            return cadres[lay] if lay else None
    def couvrir(im):
        """Like Premiere with the "cover" Basic Motion of render-segments: fills the frame."""
        w, h = im.size
        e = max(W // k / w, H // k / h)
        im = im.resize((max(1, round(w * e)), max(1, round(h * e))))
        x, y = (im.width - W // k) // 2, (im.height - H // k) // 2
        return im.crop((x, y, x + W // k, y + H // k))

    def habillage_de(f):
        return [c for piste in hab for c in piste if c["start"] <= f < c["end"]]

    choix = [(round(t * FPS), "instant") for t in (a.instants or [])]
    if hab and not a.instants:   # one thumbnail per element, once all its text is in
        for piste in hab:        # (70% of its duration, before the fade-out); wipes: skipped
            for c in piste:
                if "volet" in c["nom"]:
                    continue
                d = c["end"] - c["start"]
                choix.append((c["start"] + max(min(round(d * 0.7), d - 20), d // 2), Path(c["nom"]).stem[-28:]))
        choix.sort()
    for i, s in enumerate([] if (a.instants or hab) else segs[1:13], 1):
        if s["t1"] > s["t0"]:
            choix.append((s["t0"] + (s["t1"] - s["t0"]) // 2, "mid-transition"))
        choix.append((min(s["t1"] + 45, s["fin"] - 1), "still"))
    vignettes = []
    for f, quoi in choix:
        ci = next(c for c in clips if c["start"] <= f < c["end"])
        t = (ci["in"] + f - ci["start"]) / FPS
        E, C, lay, trans = etats(f)
        img = fond_de(f)
        for src_path, st, (sw, sh), dt in ((a.ecran, E, se, off / FPS), (a.cam, C, sc, 0.0)):
            p = params(st, sw, sh)
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t + dt:.3f}", "-i", str(src_path),
                                  "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                                 capture_output=True, check=True).stdout
            im = Image.open(BytesIO(raw)).convert("RGBA")
            l, tp = p["l"] / 100 * sw, p["t"] / 100 * sh
            r, b = sw - p["r"] / 100 * sw, sh - p["b"] / 100 * sh
            if r - l < 2 or b - tp < 2:
                continue
            crop = im.crop((round(l), round(tp), round(r), round(b)))
            s = p["scale"] / 100
            cx, cy = W / 2 + p["h"] * sw, H / 2 + p["v"] * sh   # clip center in the sequence
            x0 = cx + (l - sw / 2) * s
            y0 = cy + (tp - sh / 2) * s
            ww, hh = max(1, round((r - l) * s / k)), max(1, round((b - tp) * s / k))
            tuile = crop.resize((ww, hh))
            img.paste(tuile, (round(x0 / k), round(y0 / k)), tuile)
        cadre = cadre_de(f)
        if cadre is not None:
            img.alpha_composite(cadre)
        for c in habillage_de(f):
            couche = couvrir(image_brute(c["chemin"], (c["in"] + f - c["start"]) / c["rate"]))
            img.alpha_composite(couche)
        d = ImageDraw.Draw(img)
        d.text((8, 8), f"{f / FPS:.1f} s {lay} {quoi}", fill=(255, 220, 0, 255))
        vignettes.append(img)
    cols = 4 if k > 2 else 1
    par = 12 if k > 2 else 1   # 12 thumbnails per sheet: readable at a glance
    lots = [vignettes[i:i + par] for i in range(0, len(vignettes), par)]
    for n_lot, lot in enumerate(lots, 1):
        rows = (len(lot) + cols - 1) // cols
        planche = Image.new("RGB", (cols * W // k, rows * H // k), "white")
        for i, v in enumerate(lot):
            planche.paste(v.convert("RGB"), ((i % cols) * W // k, (i // cols) * H // k))
        out = a.apercu / ("planche-montage.jpg" if len(lots) == 1 else f"planche-montage-{n_lot:02d}.jpg")
        planche.save(out, quality=88)
    print(f"  preview: {len(lots)} sheet(s) in {a.apercu}")


if __name__ == "__main__":
    main()
