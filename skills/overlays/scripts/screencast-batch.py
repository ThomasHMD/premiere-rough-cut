#!/usr/bin/env python3
"""(Re)records and edits the demos of a video, each in the window the plan leaves it,
and registers them on V2. Generalized from a video's own `demos.py`.

    python3 screencast-batch.py <rush> <demo-windows.json> [id…] [--rendu-seul]

- <demo-windows.json>: [{"id", "start", "end"}] in sequence time, written by the plan
  (AFTER `habillage.tenue()`, which may shift the start of a demo); the scenarios are
  in <rush folder>/Screencast/scenarios/<id>.json.
- The scenario's `rushStart` = start of its window (updated here). A window that moves
  forces a RE-RECORD: gestures anchored on words stay in place, the lead-in
  gets shorter; a gesture that starts more than 0.5 s late is reported (the render
  would speed up the picture to catch up): remove a free step from the start of the scenario.
- `--rendu-seul` (render only): redoes the edit from the existing recording (camera settings,
  duration), without reopening the site; only if the window has not moved.
- `--minDuration` = window + 0.1 s: a demo shorter than its window holds its last
  frame to the end. Without that, the face showed for 1 to 3 frames before the next scene.
- The recording (~1 GB of frames per minute) goes to ~/.cache/kit-montage/screencast/ (or
  $MONTAGE_CACHE), outside the video folder: frames never go through a sync service.
  Screencast/.rec-<id> is a link to it (--rendu-seul finds it again).
One demo at a time: a single heavy process.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SK = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("MONTAGE_CACHE", Path.home() / ".cache" / "kit-montage")) / "screencast"
args = [a for a in sys.argv[1:] if not a.startswith("--")]
RUSH, WINS = Path(args[0]).resolve(), Path(args[1]).resolve()
only = args[2:]
RENDU_SEUL = "--rendu-seul" in sys.argv
V = RUSH.parent
SC = V / "Screencast"
wins = {w["id"]: w for w in json.loads(WINS.read_text())}
bad, lents = [], []
for scen in sorted((SC / "scenarios").glob("*.json")):
    sid = scen.stem
    if only and not any(sid.startswith(o) for o in only):
        continue
    w = wins.get(sid)
    if not w:
        print(f"⚠️  {sid}: no window in the plan, skipped")
        continue
    d = json.loads(scen.read_text())
    bouge = abs(d.get("rushStart", -1) - w["start"]) > 1e-3
    if bouge:
        d["rushStart"] = w["start"]
        scen.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    rec = SC / f".rec-{sid}"
    # Before the first byte is written: without the link, ~1 GB of frames per minute would go into the sync.
    if not rec.exists():
        vrai = CACHE / f"{RUSH.stem}-{sid}"
        vrai.mkdir(parents=True, exist_ok=True)
        SC.mkdir(parents=True, exist_ok=True)
        rec.symlink_to(vrai)
    out = SC / f"{sid}.mp4"
    print(f"▶ {sid}: window {w['start']:.2f} -> {w['end']:.2f} ({w['end'] - w['start']:.1f} s)", flush=True)
    if RENDU_SEUL and bouge:
        sys.exit(f"{sid}: the window moved, --rendu-seul impossible (re-record)")
    if not RENDU_SEUL:
        subprocess.run(["nice", "-n", "10", "python3", str(SK / "screencast-record.py"), str(scen), "--out", str(rec),
                        "--transcript", str(V / f"{RUSH.stem}_transcription.json")], check=True)
    subprocess.run(["nice", "-n", "10", "python3", str(SK / "screencast-render.py"), str(rec), "--out", str(out),
                    "--rush", str(RUSH), "--minDuration", f"{w['end'] - w['start'] + 0.1:.3f}"], check=True)
    late = [x for x in (json.loads((rec / "recording.json").read_text()).get("late") or []) if x[1] > 0.5]
    if late:
        lents.append(f"{sid} {late}")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                               capture_output=True, text=True).stdout.strip())
    want = w["end"] - w["start"]
    bp = V / f"{RUSH.stem}_broll-script.json"
    bd = json.loads(bp.read_text())
    for b in bd["brolls"]:
        if b.get("id") == f"SC-{sid}":
            b["durationSec"] = round(min(dur, want), 3)
    bp.write_text(json.dumps(bd, indent=2, ensure_ascii=False))
    flag = "" if dur >= want - 0.4 else "  ⚠️ TOO SHORT"
    if flag:
        bad.append(sid)
    print(f"  {sid}.mp4: {dur:.2f} s for {want:.2f} s{flag}", flush=True)
if lents:
    print("Anchored gestures that started more than 0.5 s late (step, s): shorten the scenario lead-in")
    for x in lents:
        print("  " + x)
if bad:
    print("Demos shorter than their window:", ", ".join(bad))
if bad or lents:
    sys.exit(2)
