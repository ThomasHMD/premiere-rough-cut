#!/usr/bin/env python3
"""Realigns the timestamps of the Premiere transcript on the real audio of the clip.

Why: the transcript embedded in the .prproj is not always in sync with the file. On a
real video, its words came later and later compared with the sound, from 0 s at the
start to 1.8 s after 21 min (a 0.14% drift, almost linear), while two other videos had
no offset at all. Without realignment, every cut boundary falls inside speech: the
symptom is silence_cuts.py downgrading almost every silence to "suspect noise".

Method: cross-correlation, window by window, between the mask of the Premiere words
(word starts) and the voice activity measured on the RMS. This gives the offset as a
function of time, smoothed with a median, then applied to each word by interpolation.
Nothing is assumed about the shape of the drift.

Writes only if the offset goes past --min-shift somewhere; the original version is
then kept in <words>.raw.json.

Usage:
    python3 calibrate_premiere_times.py <words_premiere.json> <audio.wav>
        [--min-shift 0.12] [--window 40] [--hop 20] [--dry-run]

Exit code: 0 (realigned or already in sync), 3 when the measurement is not reliable.
"""
import argparse
import json
import sys
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:
    print("ERROR: numpy required (pip install numpy)", file=sys.stderr)
    sys.exit(1)

H = 0.01            # RMS step
HEAD = 0.35         # a word counts for its first 0.35 seconds (the ends overflow)
MAX_LAG_S = 4.0     # largest offset searched, in both directions


def load_vad(wav_path):
    wv = wave.open(str(wav_path))
    sr = wv.getframerate()
    sig = np.frombuffer(wv.readframes(wv.getnframes()), dtype=np.int16).astype(np.float32)
    hop = int(sr * H)
    n = len(sig) // hop
    rms = np.sqrt((sig[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    thr = np.percentile(rms, 95) * 0.06
    return (rms > thr).astype(np.float32)


def measure(words, vad, window, hop):
    """Returns [(window center in Premiere time, audio - Premiere offset, agreement)]."""
    n = len(vad)
    maxlag = int(MAX_LAG_S / H)
    pm = np.zeros(n + maxlag + int(window / H), np.float32)
    for x in words:
        a = int(x["start"] / H)
        if a < len(pm):
            pm[a: int(min(x["end"], x["start"] + HEAD) / H) + 1] = 1
    res = []
    last = int(words[-1]["end"])
    for t0 in range(0, max(last - window, 1), hop):
        a, b = int(t0 / H), int((t0 + window) / H)
        seg = pm[a:b]
        if seg.sum() < 3.0 / H:      # less than 3 s of speech: silent window, skipped
            continue
        best = None
        for lag in range(-maxlag, maxlag + 1):
            a2 = a + lag
            if a2 < 0 or a2 + len(seg) > n:
                continue
            c = float((seg * vad[a2: a2 + len(seg)]).sum())
            if best is None or c > best[0]:
                best = (c, lag)
        if best:
            res.append((t0 + window / 2, best[1] * H, best[0] / float(seg.sum())))
    return res


def smooth(points):
    """Sliding median over 5 windows: removes isolated peaks. A repeated take sometimes
    makes the correlation lock 2 to 3 s off."""
    ys = [p[1] for p in points]
    out = []
    for i in range(len(ys)):
        out.append(float(np.median(ys[max(0, i - 2): i + 3])))
    return [p[0] for p in points], out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words_json")
    ap.add_argument("audio_wav")
    ap.add_argument("--min-shift", type=float, default=0.12)
    ap.add_argument("--window", type=int, default=40)
    ap.add_argument("--hop", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    wpath = Path(args.words_json)
    words = json.loads(wpath.read_text())
    vad = load_vad(args.audio_wav)

    points = measure(words, vad, args.window, args.hop)
    if len(points) < 3:
        print("ERROR: too few spoken windows to measure the offset", file=sys.stderr)
        sys.exit(3)
    accord = float(np.median([p[2] for p in points]))
    xs, ys = smooth(points)
    worst = max(ys, key=abs)
    k, c = np.polyfit(xs, ys, 1)
    print(f"Audio - Premiere offset: {ys[0]:+.2f} s at the start, {ys[-1]:+.2f} s at the end "
          f"(slope {k * 100:+.3f}%, median agreement {accord:.2f}, {len(points)} windows)")
    if accord < 0.55:
        print("ERROR: agreement too low between the transcript and the audio, "
              "unreliable measurement (wrong clip? wrong transcript?)", file=sys.stderr)
        sys.exit(3)
    # A real offset lasts: it takes at least 3 windows in a row beyond the threshold.
    run = longest = 0
    for y in ys:
        run = run + 1 if abs(y) >= args.min_shift else 0
        longest = max(longest, run)
    if longest < 3:
        print(f"Transcript in sync (largest offset {worst:+.2f} s): nothing to fix")
        return
    if args.dry_run:
        print(f"Realignment needed (largest offset {worst:+.2f} s), --dry-run: nothing written")
        return

    raw = wpath.with_suffix(".raw.json")
    if not raw.exists():
        raw.write_text(wpath.read_text())

    def shift(t):
        return float(np.interp(t, xs, ys))

    for x in words:
        d = shift(x["start"])
        x["start"] = round(x["start"] + d, 3)
        x["end"] = round(x["end"] + d, 3)
    words.sort(key=lambda x: (x["start"], x["end"]))
    wpath.write_text(json.dumps(words, ensure_ascii=False))

    after = measure(words, vad, args.window, args.hop)
    rest = max((abs(p[1]) for p in after), default=0.0)
    print(f"Realigned: {len(words)} words, largest residual offset {rest:.2f} s "
          f"(original kept in {raw.name})")


if __name__ == "__main__":
    main()
