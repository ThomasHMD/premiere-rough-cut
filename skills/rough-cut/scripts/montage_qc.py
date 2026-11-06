#!/usr/bin/env python3
"""QC of the resulting edit: the edit's audio is built (clip minus the cuts), transcribed
again with whisper and read clip by clip, with the cut points visible.

This is the method that revealed everything on a real video: an 18 s clip for a 6 s
sentence = a forgotten silence; a sentence said twice on both sides of a cut = a
surviving take; a word truncated at the edge of a clip = a boundary inside speech.
To do on every rough cut before handing back.

    python3 montage_qc.py <work_folder> [--no-whisper] [--lang fr]

Writes montage_qc.wav, montage_qc.json (whisper) and montage_qc.log (the read-through).
Exit code 2 when a clip holds more than --max-blanc seconds without speech, or lasts
less than a second (a fragment left between two cuts).

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

pw = json.loads((W / "words_premiere.json").read_text()) if (W / "words_premiere.json").exists() else []
lines, bad = [], 0
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
    lines.append(f"[{i:03d}] {s:7.1f}-{e:7.1f} ({e - s:5.1f} s){flag}\n   P  {ptxt}\n   W  {txt}")
log = "\n".join(lines)
(W / "montage_qc.log").write_text(log + "\n")
print(log)
print(f"\n{len(keep)} clips, edit {bounds[-1] / 60:.2f} min, {bad} alert(s): blank of more than {a.max_blanc} s or fragment of less than 1 s")
sys.exit(2 if bad else 0)
