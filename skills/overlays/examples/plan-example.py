#!/usr/bin/env python3
"""A video's overlay plan, written in SENTENCE ANCHORS (never in seconds).

Copy it into the video's work folder (`<rush>_Illustration_work/plan.py`), then
rewrite it scene by scene for THIS video. When the edit moves: rerun
`timeline-from-prproj.py`, then this plan, then `render-segments.py`: everything re-aligns by itself.

    python3 plan.py "/path/rush.mov"

Reads   <rush>_transcription.json (words in SEQUENCE time, written by timeline-from-prproj.py
        or transcribe.py)
Writes  <rush>_animation-script.json (read by render-segments.py) and fenetres-demos.json (read
        by screencast-batch.py, if there are site demos).

Rules (SKILL.md, "Animated scenes"): a missing anchor stops everything (exit code 2), never a
placement at 0; a sound is laid by a GESTURE of `son.py`, never by a file name; call
`habillage.tenue()` then `habillage.volets()` and never copy their rules here.
"""
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

SKILLS = Path(os.environ.get("KIT_SKILLS", Path.home() / ".claude" / "skills")).expanduser()
sys.path.insert(0, str(SKILLS / "overlays" / "scripts"))
sys.path.insert(0, str(SKILLS / "motion-design" / "scripts"))
import habillage  # noqa: E402
import son  # noqa: E402

RUSH = Path(sys.argv[1]).resolve()
WORDS = json.loads(RUSH.with_name(RUSH.stem + "_transcription.json").read_text())["words"]
END = WORDS[-1]["end"]
SEG, WINDOWS, BROLLS, MANQUANTES = [], [], [], []


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


TOKENS = [norm(w["word"]) for w in WORDS]


def T(phrase, after=0.0, occurrence=1, offset=0.0, fin=False):
    """Instant (sequence seconds) where `phrase` starts (or ends, with fin=True), searched
    after `after`. A missing anchor is noted, and the plan stops at the end."""
    cible = norm(phrase).split()
    vus = 0
    for i in range(len(TOKENS) - len(cible) + 1):
        if WORDS[i]["start"] < after:
            continue
        if TOKENS[i:i + len(cible)] == cible:
            vus += 1
            if vus == occurrence:
                w = WORDS[i + len(cible) - 1] if fin else WORDS[i]
                return round((w["end"] if fin else w["start"]) + offset, 2)
    MANQUANTES.append(f"\"{phrase}\" after {after:.1f} s (occurrence {occurrence})")
    return None


def tc(t):
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


def scene(sid, component, start, end, data=None, alpha=False, cues=(), sfx=(), track=None):
    """A scene from start to end (sequence seconds). cues and sfx in ABSOLUTE time: they are
    brought back to the start of the scene here. sfx = lists returned by son.py."""
    if start is None or end is None:
        return None
    s = {"type": "scene", "id": sid, "component": component, "alpha": alpha,
         "timecode": tc(start), "durationSec": round(end - start, 2), "_start": start,
         "data": data or {}, "cues": [round(c - start, 2) for c in cues if c is not None],
         "sfx": [{"file": f, "at": round(a - start, 2), "gainDb": g} for f, a, g in sfx if a is not None]}
    if track:
        s["track"] = track
    SEG.append(s)
    return s


# ======================================================================
# THIS video's scenes (example: replace entirely)
# ======================================================================

# 1. Chapter card, laid on the sentence that announces it.
t = T("first part")
scene("part-1", "chapter-card", t, t + 3.2 if t else None,
      {"n": 1, "total": 3, "name": "The topic", "eyebrow": "Let's start", "icon": "spark"},
      sfx=son.chapitre(t, 1, 3) if t else [])

# 2. Three words that slam in at the side (overlay), each on ITS word.
a, b, c = T("simple"), T("fast"), T("free")
if None not in (a, b, c):
    scene("three-words", "slam", a - 0.1, c + 2.0,
          {"lines": [{"text": "Simple"}, {"text": "Fast"}, {"text": "Free", "accent": True}], "side": "right"},
          alpha=True, cues=[a, b, c], sfx=son.claque(a, 0) + son.claque(b, 1) + son.claque(c, 2, fort=True))

# 3. A big number, full-screen.
t = T("two hundred")
scene("figure", "stat", t, t + 3.5 if t else None,
      {"value": 200, "label": "videos edited", "eyebrow": "In one year"},
      cues=[t], sfx=son.compteur(t, 0.9) if t else [])

# 4. A GIF (gifs.py prendre … --public <video> prints the data to paste here).
# t = T("it works")
# scene("gif-works", "gif", t, t + 3.0, {"src": "scenes/my-video/gifs/it-works.mp4",
#       "srcW": 480, "srcH": 480, "loopSec": 2.0, "side": "left"}, alpha=True, cues=[t], sfx=son.pose(t))

# 5. A site demo (scenario in <folder>/Screencast/scenarios/demo-site.json):
# WINDOWS.append(("demo-site", T("let me show you"), T("that is it for the site", fin=True)))

# ======================================================================

if MANQUANTES:
    print("Anchors not found (fix the phrase, or anchor on the previous word + offset):")
    for m in MANQUANTES:
        print(f"  - {m}")
    sys.exit(2)

for ligne in habillage.tenue(SEG, WINDOWS, BROLLS, END, tc):
    print(("  " if not ligne.startswith("!!") else "") + ligne)
habillage.volets(SEG, WINDOWS, BROLLS, END, scene, son)

for s in SEG:
    s["timecode"] = tc(s["_start"])
segments = [{k: v for k, v in s.items() if k != "_start"} for s in sorted(SEG, key=lambda s: s["_start"])]
for s in segments:
    s["sfx"] = sorted(s["sfx"], key=lambda x: x["at"])
    son.controle([(x["file"], x["at"], x["gainDb"]) for x in s["sfx"]], s["id"])
RUSH.with_name(RUSH.stem + "_animation-script.json").write_text(
    json.dumps({"version": 1, "segments": segments}, ensure_ascii=False, indent=1))
(RUSH.parent / "fenetres-demos.json").write_text(
    json.dumps([{"id": i, "start": a, "end": b} for i, a, b in WINDOWS], ensure_ascii=False, indent=1))
print(f"{len(segments)} segments written to {RUSH.stem}_animation-script.json")
