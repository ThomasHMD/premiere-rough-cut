#!/usr/bin/env python3
"""Detects the silences to cut between the words of the Premiere transcript,
checked against the audio energy (RMS), and writes them as "disable" cuts.

Rule (desk talking-head shoot): long silences are the speaker reading notes, they
ARE CUT. The old "never auto-cut a silence" rule only holds for clips where the
silence is b-roll on screen (photo outing, field review): skip the silence cuts then.

Quality guards:
- speech = words of the PREMIERE transcript only (whisper timestamps drift after a
  long silence and create fake speech that protects the silence);
- RMS check: if the zone to cut holds more than max_loud_s of windows above
  loud_ratio x the median speech RMS, the cut is downgraded to a flag
  (laugh, handling noise, speech missed by the transcript);
- speech end realigned on the RMS: Premiere word ends often overflow by
  0.3-0.6 s into the silence, so the cut starts at the real energy drop
  + pad_out (word starts are reliable);
- enumeration guard: a pause < enum_gap between TWO short speech blocks
  (< enum_block) is intended rhythm (a list, a comic repetition), left alone.
  Tightened (one short block used to be enough): on a bench of three videos
  against the editor's finished edits, 7 more pauses cut like the editor did (7.4 s),
  1 too many (0.8 s); the old setting is still there with --enum-any;
- minimal raw gap min_gap; minimal cut min_cut (no micro jump cuts).

Defaults calibrated by simulation against the editor's FINAL edit: catches 31 s of
silences out of the 60 s removed by hand, 0 s of speech cut by mistake, ~3 s of
silence disagreement (edges +/-0.2 s). The old setting (1.5/0.5/0.4/1.0) left a
"slack" edit.

Usage:
    python3 silence_cuts.py <words_premiere.json> <audio.wav> <cuts_silence.json>
        [--min-gap 1.0] [--pad-out 0.25] [--pad-in 0.20] [--min-cut 0.45]
        [--duration SECONDS] [--lang fr]

The reason texts come from ../languages/<code>.json: --lang, else the "language" of the
transcript.json next to words_premiere.json, else en.
"""
import argparse
import json
import sys
import wave
from pathlib import Path

import lang

try:
    import numpy as np
except ImportError:
    print("ERROR: numpy required (pip install numpy)", file=sys.stderr)
    sys.exit(1)

HOP_S = 0.02          # RMS window
LOUD_RATIO = 0.265    # "loud" threshold relative to the median speech RMS
MAX_LOUD_S = 0.6      # beyond that, the zone is suspect -> flag instead of cut
QUIET_RATIO = 0.16    # under this ratio of the speech RMS = silence (word-end realignment)
ENUM_GAP = 1.5        # pause < 1.5s between two short blocks = enumeration rhythm
ENUM_BLOCK = 2.5      # "short" speech block (s) for the enumeration guard
HEAD_S = 0.35         # the speech level is measured on the head of the words (the ends overflow)
OVERFLOW_S = 1.0      # a word longer than this has swallowed the silence that follows it
OVERFLOW_QUIET_S = 0.30  # continuous calm that marks the real end of an overflowing word


def speech_blocks(words, merge_gap=0.25):
    blocks = []
    for w in words:
        if blocks and w["start"] - blocks[-1][1] < merge_gap:
            blocks[-1][1] = max(blocks[-1][1], w["end"])
        else:
            blocks.append([w["start"], w["end"]])
    return blocks


def trim_overflow(words, rms, quiet):
    """Brings back to its real end a word whose Premiere duration swallowed the next silence.

    Seen on a real video: the .prproj transcript had 31 words longer than 1.5 s
    (up to 12 s, against 0 to 2 on two other videos). The silence no longer existed
    between the words, so it was no longer cut: 1 min 30 of gaps stayed in the edit.
    We start again from the word start (reliable) and stop at the first continuous calm.
    """
    need = int(OVERFLOW_QUIET_S / HOP_S)
    fixed = 0
    for w in words:
        if w["end"] - w["start"] <= OVERFLOW_S:
            continue
        i = int((w["start"] + 0.10) / HOP_S)
        imax = min(int(w["end"] / HOP_S), len(rms) - 1)
        run = 0
        while i < imax:
            run = run + 1 if rms[i] <= quiet else 0
            if run >= need:
                w["end"] = (i - run + 1) * HOP_S
                fixed += 1
                break
            i += 1
    return fixed


def load_rms(wav_path):
    wv = wave.open(str(wav_path))
    sr = wv.getframerate()
    sig = np.frombuffer(wv.readframes(wv.getnframes()), dtype=np.int16).astype(np.float32)
    hop = int(sr * HOP_S)
    n = len(sig) // hop
    rms = np.sqrt((sig[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    return rms, len(sig) / sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words_json")
    ap.add_argument("audio_wav")
    ap.add_argument("cuts_out")
    ap.add_argument("--min-gap", type=float, default=1.0)
    ap.add_argument("--pad-out", type=float, default=0.25)
    ap.add_argument("--pad-in", type=float, default=0.20)
    ap.add_argument("--min-cut", type=float, default=0.45)
    ap.add_argument("--enum-gap", type=float, default=ENUM_GAP, help="enumeration guard: longest protected pause (s)")
    ap.add_argument("--enum-any", action="store_true",
                    help="old enumeration guard: a single short block is enough to protect the pause")
    ap.add_argument("--duration", type=float, default=None,
                    help="clip duration (default: duration of the wav)")
    lang.add_argument(ap)
    args = ap.parse_args()
    reasons = lang.load(lang.resolve(args.lang, lang.from_work_dir(Path(args.words_json).parent)))["reasons"]

    words = json.loads(Path(args.words_json).read_text())
    rms, wav_dur = load_rms(args.audio_wav)
    duration = args.duration or wav_dur

    # Speech level: median RMS over the head of the words. Measured over whole
    # words, it collapses when the word ends overflow into the silence.
    mask = np.zeros(len(rms), dtype=bool)
    for w in words:
        mask[int(w["start"] / HOP_S): int(min(w["end"], w["start"] + HEAD_S) / HOP_S) + 1] = True
    ref = float(np.median(rms[mask]))
    n_fixed = trim_overflow(words, rms, QUIET_RATIO * ref)
    if n_fixed:
        print(f"{n_fixed} overflowing words brought back to their real end")
    blocks = speech_blocks(words)

    def real_speech_end(t, tmax):
        """Realigns the Premiere word end (which overflows) on the real RMS drop."""
        i, imax = int(t / HOP_S), int(tmax / HOP_S)
        if i < len(rms) and rms[i] > QUIET_RATIO * ref:
            while i < imax and rms[i] > QUIET_RATIO * ref:
                i += 1
        else:
            imin = int(max(t - 0.6, 0) / HOP_S)
            while i > imin and rms[i - 1] <= QUIET_RATIO * ref:
                i -= 1
        return i * HOP_S

    def real_speech_start(t, tmin):
        """Moves back to the real attack when the speech began before the stated word start
        (short word attached to the previous one, transcript realigned to within 0.1 s)."""
        # bounded by the audio: the video can last a few frames longer than the sound track
        i, imin = min(int(t / HOP_S), len(rms)), int(max(tmin, t - 0.6) / HOP_S)
        while i > imin and rms[i - 1] > QUIET_RATIO * ref:
            i -= 1
        return i * HOP_S

    cuts = []
    prev = 0.0
    prev_block_dur = 0.0
    for s, e in blocks + [[duration + 1.0, duration + 1.0]]:
        raw = s - prev
        next_block_dur = e - s
        # enumeration guard: short pause between two short blocks = intended rhythm
        courts = (prev_block_dur < ENUM_BLOCK, next_block_dur < ENUM_BLOCK)
        enum_rhythm = raw < args.enum_gap and (any(courts) if args.enum_any else all(courts))
        if raw >= args.min_gap and prev > 0 and not enum_rhythm:
            cs = real_speech_end(prev, s) + args.pad_out
            ce = min(real_speech_start(min(s, duration), cs) - args.pad_in, duration)
            if ce - cs >= args.min_cut:
                zone = rms[int(cs / HOP_S): int(ce / HOP_S)]
                loud_s = float((zone > LOUD_RATIO * ref).sum() * HOP_S)
                suspect = loud_s > MAX_LOUD_S
                cuts.append({
                    "start": round(cs, 2), "end": round(ce, 2),
                    "decision": "flag" if suspect else "disable",
                    "type": "silence", "confidence": 0.65 if suspect else 0.9,
                    "reason": (reasons["silence_noisy"].format(gap=raw, noise=loud_s) if suspect
                               else reasons["silence_notes"].format(gap=raw)),
                })
        prev = max(prev, e)
        prev_block_dur = e - s

    Path(args.cuts_out).write_text(json.dumps({"cuts": cuts}, ensure_ascii=False, indent=1))
    dis = [c for c in cuts if c["decision"] == "disable"]
    fl = [c for c in cuts if c["decision"] == "flag"]
    total = sum(c["end"] - c["start"] for c in dis)
    print(f"{len(dis)} silences cut ({total:.1f}s), {len(fl)} flags (suspect noise)")


if __name__ == "__main__":
    main()
