#!/usr/bin/env python3
"""QC of the resulting edit: the edit's audio is built (clip minus the cuts), transcribed
again with whisper and read clip by clip, with the cut points visible.

This is the method that revealed everything on a real video: an 18 s clip for a 6 s
sentence = a forgotten silence; a sentence said twice on both sides of a cut = a
surviving take; a word truncated at the edge of a clip = a boundary inside speech.
To do on every rough cut before handing back.

    python3 montage_qc.py <work_folder> [--no-whisper] [--lang fr]

Writes montage_qc.wav, montage_qc.json (whisper) and montage_qc.log (the read-through).
Exit code 2 when a clip holds more than --max-blanc seconds without speech, lasts less
than a second (a fragment left between two cuts), or starts after less than --min-air
seconds of blank at the join (a dry join). Also flags, without blocking, a short Premiere
word of more than 0.45 s at the start of a clip: probably a doubled word ("The... the").

whisper runs in the language given by --lang, else the "language" of the work folder's
transcript.json, else it detects the language by itself.
"""
import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

import lang

ap = argparse.ArgumentParser()
ap.add_argument("work")
ap.add_argument("--no-whisper", action="store_true", help="reuse montage_qc.json")
ap.add_argument("--max-blanc", type=float, default=1.6, help="longest blank allowed in a clip (s)")
ap.add_argument("--min-air", type=float, default=0.30,
                help="minimum blank at the join between two clips")
lang.add_argument(ap)
a = ap.parse_args()
W = Path(a.work)
LANG_CODE = a.lang or lang.from_work_dir(W)
DUR = json.loads((W / "meta.json").read_text())["duration_seconds"]
cuts = sorted((c for c in json.loads((W / "cuts_final.json").read_text())["cuts"] if c["decision"] == "disable"),
              key=lambda c: c["start"])
keep, t = [], 0.0
for c in cuts:
    if c["start"] - t > 0.07:
        keep.append((t, c["start"]))
    t = max(t, c["end"])
if DUR - t > 0.07:
    keep.append((t, DUR))

wv = wave.open(str(W / "audio.wav"))
sr = wv.getframerate()
sig = np.frombuffer(wv.readframes(wv.getnframes()), dtype=np.int16)
parts = [sig[int(s * sr): int(e * sr)] for s, e in keep]
out = W / "montage_qc.wav"
with wave.open(str(out), "wb") as o:
    o.setnchannels(1)
    o.setsampwidth(2)
    o.setframerate(sr)
    o.writeframes(np.concatenate(parts).tobytes())
bounds = np.cumsum([0.0] + [len(p) / sr for p in parts])   # start of each clip in the edit

js = W / "montage_qc.json"
if not a.no_whisper or not js.exists():
    subprocess.run([sys.executable, str(Path(__file__).with_name("transcribe.py")), str(out), str(js)]
                   + (["--language", LANG_CODE] if LANG_CODE else []), check=True, capture_output=True)
data = json.loads(js.read_text())
words = data["words"] if isinstance(data, dict) and "words" in data else \
    [w for s in data.get("segments", []) for w in s.get("words", [])]

# measured voice activity (RMS): the blank of a clip does not depend on the whisper timestamps
full = np.concatenate(parts).astype(np.float32)
hop = int(sr * 0.01)
n = len(full) // hop
rms = np.sqrt((full[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
quiet = float(np.percentile(rms, 95)) * 0.06

# Air at the join: rule and settings in raccords.py, shared with qc_assemblage.py. It is
# measured here in the resulting edit, not in the footage.
sys.path.insert(0, str(Path(__file__).parent))
import raccords  # noqa: E402

_par = raccords.masque(rms)


def air_raccord(t):
    """Blanc continu autour de l'instant t du montage (0 si t tombe en pleine parole)."""
    return raccords.air(_par, t)


types_coupe = {}
_cf = W / "cuts_final.json"
if _cf.exists():
    _d = json.loads(_cf.read_text())
    for _c in sorted([x for x in (_d["cuts"] if isinstance(_d, dict) else _d)
                      if x.get("decision") == "disable"], key=lambda x: x["start"]):
        types_coupe[round(_c["start"], 2)] = _c.get("type", "")

pw = json.loads((W / "words_premiere.json").read_text()) if (W / "words_premiere.json").exists() else []
lines, bad, doubles, serres = [], 0, 0, []
for i, (s, e) in enumerate(keep):
    a0, a1 = bounds[i], bounds[i + 1]
    txt = " ".join(w.get("word", w.get("text", "")).strip() for w in words
                   if a0 - 0.05 <= (w["start"] + w["end"]) / 2 < a1)
    seg = rms[int(a0 / 0.01): int(a1 / 0.01)] <= quiet
    run = best = 0
    for q in seg:                        # longest continuous blank of the clip
        run = run + 1 if q else 0
        best = max(best, run)
    blanc = best * 0.01
    flag = ""
    if blanc > a.max_blanc:
        flag = f"  ⚠ BLANK {blanc:.1f} s"
        bad += 1
    # P = Premiere words whose start falls inside the clip (what the cuts meant to keep),
    # W = what whisper hears in the edit. A difference at the edge of a clip = a boundary to review.
    ptxt = " ".join(x["text"] for x in pw if s - 0.02 <= x["start"] < e)
    if e - s < 1.0:                      # fragment: almost always a leftover between two cuts
        flag += "  ⚠ FRAGMENT"
        bad += 1
    # "The... the book begins" after a take cut, transcribed by Premiere as ONE "The" of
    # 0.68 s; whisper deduplicates the doubled word, so listening to the join did not show it.
    # A short word that is too long at the start of a clip = to listen to (hear.py). On a real
    # video: 1 alert out of 51 clips, and it was the stutter.
    att = [x for x in pw if s - 0.02 <= x["start"] < e][:2]
    if i and att:
        x = att[0]
        mot = x["text"].strip(".,;:!?…'’\"« »")  # fr-ok
        suite = att[1]["start"] - x["end"] if len(att) > 1 else 1.0
        if 0 < len(mot) <= 3 and not mot.isdigit() and x["end"] - x["start"] >= 0.45 and suite < 0.2:
            flag += f"  ⚠ DOUBLED WORD? \"{x['text']}\" {x['end'] - x['start']:.2f} s"
            doubles += 1
    # Air at the join into the clip. A stutter or a correction is removed in the middle of a
    # sentence: the delivery carries on over it, there is no air to leave, so we do not require it.
    if i:
        typ = types_coupe.get(round(keep[i - 1][1], 2), "")
        air = air_raccord(a0)
        if typ not in ("begaiement", "correction") and air < a.min_air:
            flag += f"  ⚠ RACCORD SEC {air:.2f} s"
            serres.append((air, a0, typ))
            bad += 1
    lines.append(f"[{i:03d}] {s:7.1f}-{e:7.1f} ({e - s:5.1f} s){flag}\n   P  {ptxt}\n   W  {txt}")
log = "\n".join(lines)
(W / "montage_qc.log").write_text(log + "\n")
print(log)
print(f"\n{len(keep)} clips, edit {bounds[-1] / 60:.2f} min, {bad} alert(s): blank of more than {a.max_blanc} s, "
      f"fragment of less than 1 s or join under {a.min_air} s of air")
if serres:
    print(f"{len(serres)} dry join(s): the kept sentence has no time to settle "
          f"(" + ", ".join(f"{t / 60:02.0f}:{t % 60:04.1f} {v:.2f}s {ty}" for v, t, ty in serres[:6]) + ")")
if doubles:
    print(f"{doubles} possible doubled word(s) at the start of a clip: listen with hear.py (does not block)")
sys.exit(2 if bad else 0)
