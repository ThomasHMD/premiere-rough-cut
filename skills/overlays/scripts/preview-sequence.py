#!/usr/bin/env python3
"""EXACT low-resolution preview of the illustrated sequence: what Premiere will play after
importing the XML onto the editor's sequence.

    python3 preview-sequence.py <rush> <start s> <end s> [output.mp4] [--xml X] [--garder-base]

1. The talking-head shot, glued back together according to <rush>_timeline.json IN ONE PIECE: each
   output frame n gets the rush frame at src_in + (n/fps - seq_in), and the sound is copied
   to the sample. WARNING: never glue separately encoded pieces back together (concat): each
   join adds about 25 ms to the voice, 3 s late after 10 min (a word on screen would appear
   well before it is said).
2. On top, the video tracks of the delivered XML, in their order, each active clip from start
   (included) to end (excluded); the sound effects of the audio tracks at their start. Two settings
   without which the preview invents face "flashes" between two elements:
   - each clip is advanced by half a frame (the overlay filter takes the last frame
     that arrived: otherwise the first frame of the clip arrives after that of the sequence);
   - eof_action=pass: a file shorter than its clip shows the track below, as in
     Premiere. The old setting (repeat) repeated the last frame and HID this defect:
     scenes rendered in round(duration x 30) frames ended 1 to 2 frames before their clip at
     29.97, the preview was clean and Premiere was not. Since then, every render covers its whole
     clip (frames_couverts).
Several rushes in the sequence: each clip of the timeline names its `media`
(timeline-from-prproj.py <rush1> <rush2>), read from the file next to the first rush.
With --garder-base, the talking-head shot alone stays next to it (<output>.base.mp4): it is the
reference of `qc-sequence.py flash`.
"""
import json
import re
import subprocess
import sys
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf

args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = sys.argv[1:]
RUSH = Path(args[0]).resolve()
A, B = float(args[1]), float(args[2])
OUT = Path(args[3]) if len(args) > 3 else RUSH.parent / f"apercu-{int(A)}-{int(B)}.mp4"
KEEP = "--garder-base" in opts
if "--xml" in opts:
    XML = Path(opts[opts.index("--xml") + 1])
else:
    cands = [p for p in RUSH.parent.glob("premiere-sequence-*.xml")
             if re.sub(r"[^a-z0-9]", "", RUSH.stem.lower()) in re.sub(r"[^a-z0-9]", "", p.stem.lower())]
    if len(cands) != 1:
        sys.exit(f"XML not found or ambiguous ({[c.name for c in cands]}): specify --xml")
    XML = cands[0]

pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=width,height,r_frame_rate", "-of", "json", str(RUSH)],
                               capture_output=True, text=True).stdout)["streams"][0]
RATE = pr["r_frame_rate"]
FPS = float(Fraction(RATE))
rw, rh = pr["width"], pr["height"]
W = 960 if rw >= rh else 540
H = round(W * rh / rw / 2) * 2
SR = 48000
tmp = Path(tempfile.mkdtemp(prefix="apercu-"))

clips = json.loads((RUSH.parent / f"{RUSH.stem}_timeline.json").read_text())
B = min(B, clips[-1]["seq_out"])
n0, n1 = round(A * FPS), round(B * FPS)


media = lambda c: RUSH.with_name(c["media"]) if c.get("media") else RUSH


def source_t(t):
    for c in clips:
        if c["seq_in"] - 1e-6 <= t < c["seq_out"] - 1e-6:
            return media(c), c["src_in"] + (t - c["seq_in"])
    return None


# 1a. picture: one rush frame per sequence frame, read in order (one reader per rush)
want = []
for n in range(n0, n1):
    s = source_t(n / FPS)
    want.append(None if s is None else (s[0], round(s[1] * FPS)))
base_v = OUT.with_suffix(".base.mp4") if KEEP else tmp / "base.mp4"
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                        "-r", RATE, "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                        "-pix_fmt", "yuv420p", str(base_v)], stdin=subprocess.PIPE)
lecteurs = {}   # rush -> [process, current frame, last frame read]
noir = bytes(W * H * 3)
for w in want:
    if w is None:
        enc.stdin.write(noir)
        continue
    f, k = w
    if f not in lecteurs:
        lecteurs[f] = [subprocess.Popen(["ffmpeg", "-v", "error", "-hwaccel", "videotoolbox", "-i", str(f), "-vf",
                                         f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                        stdout=subprocess.PIPE), -1, None]
    lec = lecteurs[f]
    assert k >= lec[1], f"the edit goes backwards in {f.name}: sequential reading impossible"
    while lec[1] < k:
        lec[2] = lec[0].stdout.read(W * H * 3)
        lec[1] += 1
    enc.stdin.write(lec[2])
enc.stdin.close()
enc.wait()
for lec in lecteurs.values():
    lec[0].kill()

# 1b. sound: copied to the sample
sons_rush = {}
base_a = np.zeros((round((n1 - n0) / FPS * SR), 2), np.int16)
for c in clips:
    a, b = max(c["seq_in"], n0 / FPS), min(c["seq_out"], n1 / FPS)
    if b <= a:
        continue
    f = media(c)
    if f not in sons_rush:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-vn", "-ac", "2", "-ar", str(SR), "-f", "s16le",
                              "-"], capture_output=True).stdout
        sons_rush[f] = np.frombuffer(raw, np.int16).reshape(-1, 2)
    rush_a = sons_rush[f]
    i, j = round((a - n0 / FPS) * SR), round((b - n0 / FPS) * SR)
    s = round((c["src_in"] + a - c["seq_in"]) * SR)
    j = min(j, len(base_a))
    seg = rush_a[s:s + (j - i)]
    base_a[i:i + len(seg)] = seg
wav = tmp / "base.wav"
sf.write(wav, base_a, SR, subtype="PCM_16")

# 2. the XML tracks, in order (the first at the bottom, the last on top)
seq = ET.parse(XML).getroot().find(".//sequence")
path = lambda it: Path(urllib.parse.unquote(it.find("file/pathurl").text.replace("file://localhost", "")))
files = {it.find("file").get("id"): path(it) for it in seq.iter("clipitem") if it.find("file/pathurl") is not None}


cadences = {}
for it in seq.iter("clipitem"):
    f = it.find("file")
    if f is not None and f.find("pathurl") is not None:
        tb = float(f.findtext("rate/timebase") or it.findtext("rate/timebase"))
        cadences[f.get("id")] = tb * (1000 / 1001 if (f.findtext("rate/ntsc") or "").upper() == "TRUE" else 1)


def entree(it):
    """Source instant read by Premiere: <in> counted in the media's REAL rate (that of its <file>), not in
    the clip's <rate>. Read from the clip's <rate> (as before), the preview showed zooms in sync while
    Premiere played them 0.1% too late, out of step with the voice."""
    f = it.find("file")
    return int(it.findtext("in")) / cadences.get(f.get("id"), float(it.findtext("rate/timebase")))


def fichier(it):
    f = it.find("file")
    return path(it) if f.find("pathurl") is not None else files[f.get("id")]


def mouvement(it):
    """Basic Motion of a RUSH clip (zooms on its camera, framings on books): keys [(s since the start of the
    clip, scale, source x at center, source y at center)]; None elsewhere (b-rolls and renders laid full-frame).
    Keys written in several reference frames (render-segments): we keep those that fall inside the clip."""
    if fichier(it).name not in {c.get("media") or RUSH.name for c in clips}:   # any rush of the sequence
        return None
    dur = int(it.findtext("end")) - int(it.findtext("start"))
    def lire(par, centre):
        val = (lambda e: (float(e.findtext("horiz")), float(e.findtext("vert")))) if centre else (lambda e: float(e.text))
        cles = [(int(k.findtext("when")), val(k.find("value"))) for k in par.findall("keyframe")]
        cles = [(w, x) for w, x in cles if 0 <= w < dur]
        return cles or [(0, val(par.find("value")))]
    S, Cn = [(0, 100.0)], [(0, (0.0, 0.0))]
    for par in it.iter("parameter"):
        if par.findtext("parameterid") == "scale":
            S = lire(par, False)
        if par.findtext("parameterid") == "center":
            Cn = lire(par, True)
    if len(S) == 1 and len(Cn) == 1 and abs(S[0][1] - 100) < 0.1 and Cn[0][1] == (0.0, 0.0):
        return None
    if len(S) != len(Cn):   # fixed scale, animated center (or the reverse): repeat the fixed value
        S = S * len(Cn) if len(S) == 1 else S
        Cn = Cn * len(S) if len(Cn) == 1 else Cn
    out = []
    for (w, k), (_, (h, v)) in zip(S, Cn):
        k /= 100
        out.append((w / FPS, k, rw / 2 - h * rw / k, rh / 2 - v * rh / k))   # source point at the center of the frame
    return out


def lineaire(cles, var):
    """Piecewise-linear ffmpeg expression of `var` over [(t, value)]."""
    e = f"{cles[-1][1]:.4f}"
    for (t0, a), (t1, b) in reversed(list(zip(cles, cles[1:]))):
        e = f"if(lt({var},{t1:.4f}),{a:.4f}+({b - a:.4f})*max(0,({var}-{t0:.4f}))/{max(1e-3, t1 - t0):.4f},{e})"
    return e


layers, sons = [], []
for tr in seq.find("media/video").findall("track"):
    for it in tr.findall("clipitem"):
        s, e = int(it.findtext("start")), int(it.findtext("end"))
        if e > n0 and s < n1 and s >= 0 and it.findtext("enabled") != "FALSE":
            layers.append((s, e, entree(it), fichier(it), mouvement(it)))
for tr in seq.find("media/audio").findall("track"):
    for it in tr.findall("clipitem"):
        s = int(it.findtext("start"))
        if n0 <= s < n1 and it.findtext("enabled") != "FALSE":
            sons.append((s, int(it.findtext("in")) / float(it.findtext("rate/timebase")), fichier(it)))
cmd =["ffmpeg", "-v", "error", "-y", "-i", str(base_v), "-i", str(wav)]
fc, last = [], "[0:v]"
for i, (s, e, cin, f, mv) in enumerate(layers, start=2):
    t0 = (s - n0) / FPS - 0.5 / FPS
    # zoom: no -itsoffset. With it, the precise cut of -ss lets through the frames since the previous
    # key frame, which zoompan renumbers: frame late by 0 to 1 s depending on the GOP (measured at 12 frames)
    cmd += ["-ss", f"{cin:.6f}"] + ([] if mv else ["-itsoffset", f"{t0:.6f}"]) + ["-i", str(f)]
    if mv:   # zoom: the window of the source seen by Premiere at each frame (scale and center by key frames)
        tv = f"(in/{FPS:.5f})"
        z = lineaire([(t, k) for t, k, _, _ in mv], tv)
        px = lineaire([(t, x) for t, _, x, _ in mv], tv)
        py = lineaire([(t, y) for t, _, _, y in mv], tv)
        fc.append(f"[{i}:v]zoompan=z='{z}':x='{px}-iw/zoom/2':y='{py}-ih/zoom/2':d=1:s={W}x{H}:fps={RATE},setpts=PTS-STARTPTS+{max(0.0, t0):.6f}/TB,format=yuva420p[o{i}]")   # zoompan restarts from 0
    else:
        fc.append(f"[{i}:v]scale={W}:{H},format=yuva420p[o{i}]")
    fc.append(f"{last}[o{i}]overlay=eof_action=pass:enable='between(n,{s - n0},{e - n0 - 1})'[v{i}]")
    last = f"[v{i}]"
amix = ["[1:a]"]
k = len(layers) + 2
for s, cin, f in sons:
    cmd += ["-ss", f"{cin:.4f}", "-i", str(f)]
    ms = (s - n0) / FPS * 1000
    fc.append(f"[{k}:a]aresample={SR},aformat=channel_layouts=stereo,adelay={ms:.1f}|{ms:.1f}[a{k}]")
    amix.append(f"[a{k}]")
    k += 1
fc.append(f"{''.join(amix)}amix=inputs={len(amix)}:normalize=0:dropout_transition=0[aout]")
cmd += ["-filter_complex", ";".join(fc), "-map", last, "-map", "[aout]", "-frames:v", str(n1 - n0), "-r", RATE,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(OUT)]
subprocess.run(cmd, check=True)
for p in tmp.iterdir():
    p.unlink()
tmp.rmdir()
print(f"{OUT.name}: {len(layers)} elements laid, {len(sons)} sound effects, frames {n0} to {n1}"
      + (f"; talking head alone: {base_v.name}" if KEEP else ""))
