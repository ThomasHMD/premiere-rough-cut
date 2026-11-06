#!/usr/bin/env python3
"""Applies the take selection (made by Claude in context) and merges it with the
silences: takes.json + cuts_silence.json -> cuts_semantic.json + cuts_final.json.

Takes are described by Premiere WORD INDICES (realigned words_premiere.json): a cut
runs from the start of the first cut word to the start of the first kept word, with
its boundaries set in the nearest energy valley (RMS).

    python3 apply_takes.py <work_folder> [--lang fr]

takes.json (in the work folder):
    {"cuts":    [[first_word, last_word, "retake", 0.96, "reason"], ...],      # null = start of the clip
     (optional 6th element {"start": s, "end": s}: boundary set by hand)
     "time_cuts": [[start_s, end_s, "noise", 0.95, "reason"], ...],           # cuts in seconds
     "flags":   [[first_word, last_word, "aside", 0.70, "reason"], ...],      # kept, red marker
     "protect": [[start_s, end_s, "reason"], ...]}                            # intended silences

The reasons written by the script itself come from ../languages/<code>.json: --lang, else
the "language" of the work folder's transcript.json, else en.
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np

import lang

code, argv = lang.pop_argv(sys.argv[1:])
W = Path(argv[0])
REASONS = lang.load(lang.resolve(code, lang.from_work_dir(W)))["reasons"]
words = json.loads((W / "words_premiere.json").read_text())
takes = json.loads((W / "takes.json").read_text())
DUR = json.loads((W / "meta.json").read_text())["duration_seconds"]
HOP = 0.01

wv = wave.open(str(W / "audio.wav"))
sr = wv.getframerate()
sig = np.frombuffer(wv.readframes(wv.getnframes()), dtype=np.int16).astype(np.float32)
hop = int(sr * HOP)
n = len(sig) // hop
rms = np.sqrt((sig[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
rms = np.convolve(rms, np.ones(3) / 3, mode="same")
P95 = float(np.percentile(rms, 95))
QUIET = P95 * 0.06


def quiet_zone(t):
    """Nearest energy valley to the word start t: (start, end) of the quiet zone around
    the minimum searched in [t-0.25, t+0.10], or (m, m) when there is only continuous
    speech there (m = the quietest instant)."""
    a, b = max(0, int((t - 0.25) / HOP)), min(len(rms), int((t + 0.10) / HOP))
    m = a + int(np.argmin(rms[a:b]))
    if rms[m] > QUIET:
        return m * HOP, m * HOP
    lo = m
    while lo > 0 and rms[lo - 1] <= QUIET and (m - lo) * HOP < 1.0:
        lo -= 1
    hi = m
    while hi < len(rms) - 1 and rms[hi + 1] <= QUIET and (hi - m) * HOP < 1.0:
        hi += 1
    return lo * HOP, (hi + 1) * HOP


def cut_end(t):
    """Cut end before the first kept word: 0.12 s of air before the real attack."""
    lo, hi = quiet_zone(t)
    return max(lo, hi - 0.12)


def cut_start(t):
    """Cut start at the first cut word: 0.10 s after the real end of the kept word
    before it (the silence before, if long, is handled by silence_cuts)."""
    lo, hi = quiet_zone(t)
    return min(hi, lo + 0.10)


sem = []
for a, b, typ, conf, why, *opt in takes.get("cuts", []):
    start = 0.0 if a is None else cut_start(words[a]["start"])
    end = cut_end(words[b + 1]["start"]) if b + 1 < len(words) else DUR
    # optional 6th element {"start": s, "end": s}: boundary set by hand (in seconds)
    # when the edit QC shows a sound left at the edge (word badly cut by Premiere)
    if opt:
        start, end = opt[0].get("start", start), opt[0].get("end", end)
    sem.append({"start": round(start, 2), "end": round(end, 2), "decision": "disable",
                "confidence": conf, "type": typ, "reason": why,
                "words": [a if a is not None else 0, b],
                "coupe": " ".join(x["text"] for x in words[(a or 0): b + 1])[:160],
                "garde_ensuite": " ".join(x["text"] for x in words[b + 1: b + 7])})
flags = []
for a, b, typ, conf, why in takes.get("flags", []):
    flags.append({"start": round(words[a]["start"], 2),
                  "end": round(min(words[b]["end"], words[b]["start"] + 0.6), 2),
                  "decision": "flag", "confidence": conf, "type": typ, "reason": why})
# Cuts given in seconds (noise, a false start Premiere did not transcribe: seen at QC).
for t0, t1, typ, conf, why in takes.get("time_cuts", []):
    sem.append({"start": float(t0), "end": float(t1), "decision": "disable",
                "confidence": conf, "type": typ, "reason": why})

sil = json.loads((W / "cuts_silence.json").read_text())["cuts"]
# A removed take that starts right after a cut silence: its start moves back to the
# end of the silence, otherwise a half-second fragment (the attack of the cut word)
# stays between the two cuts.
for c in sem:
    prev = [x["end"] for x in sil if x["decision"] == "disable" and c["start"] - 0.8 <= x["end"] <= c["start"] + 0.3]
    if prev:
        c["start"] = round(min(c["start"], min(prev)), 2)
(W / "cuts_semantic.json").write_text(json.dumps({"cuts": sem + flags}, ensure_ascii=False, indent=1))
protect = takes.get("protect", [])
sil_keep = []
for c in sil:
    hit = [p for p in protect if c["start"] < p[1] and c["end"] > p[0]]
    if hit:
        print(f"protected silence {c['start']}-{c['end']}: {hit[0][2]}")
        continue
    sil_keep.append(c)

# End of the clip: 1 s of air after the last sound, the rest goes (no micro-clip).
last_start = words[-1]["start"]
sil_keep = [c for c in sil_keep if c["start"] < last_start]
loud = np.nonzero(rms[int(last_start / HOP):] > QUIET)[0]
last_sound = last_start + (int(loud[-1]) + 1) * HOP if len(loud) else words[-1]["end"]
if DUR - (last_sound + 1.0) > 0.3:
    sil_keep.append({"start": round(last_sound + 1.0, 2), "end": DUR, "decision": "disable",
                     "type": "silence", "confidence": 0.9, "reason": REASONS["clip_end"]})
# Start of the clip: same thing before the first word (0.4 s of air).
first = words[0]["start"]
if first > 1.0 and not any(c["start"] <= 0.05 for c in sem + sil_keep):
    sil_keep.append({"start": 0.0, "end": round(cut_end(first) - 0.25, 2), "decision": "disable",
                     "type": "silence", "confidence": 0.9, "reason": REASONS["clip_start"]})

dis = sorted([c for c in sem + sil_keep if c["decision"] == "disable"], key=lambda c: c["start"])
merged = []
for c in dis:
    if merged and c["start"] - merged[-1]["end"] < 0.3:
        m = merged[-1]
        m["end"] = max(m["end"], c["end"])
        if c["type"] != "silence" and m["type"] == "silence":
            m["type"], m["reason"], m["confidence"] = c["type"], c["reason"], c["confidence"]
        elif c["type"] != "silence" and c["reason"] not in m["reason"]:
            m["reason"] += " + " + c["reason"]
    else:
        merged.append({k: c[k] for k in ("start", "end", "decision", "confidence", "type", "reason")})
# Mute fragments: a leftover of less than a second between two cuts, with nothing louder
# than a breath, goes with them. Cause: a word that Premiere dated in the middle of a
# silence (actually said before), which silence_cuts therefore protected.
# A longer leftover where nothing goes above the silence threshold goes too: on a real
# video, four 1.01 s gaps between two cut silences (words dated inside the gap) stayed
# in the edit, and the editor removed them.
i = 0
while i + 1 < len(merged):
    g0, g1 = merged[i]["end"], merged[i + 1]["start"]
    seg = rms[int(g0 / HOP): int(g1 / HOP) + 1]
    if len(seg) == 0 or (g1 - g0 < 1.0 and seg.max() < 4 * QUIET) or seg.max() < QUIET:
        print(f"mute fragment {g0:.2f}-{g1:.2f} merged into the neighboring cuts")
        merged[i]["end"] = merged[i + 1]["end"]
        if merged[i]["type"] == "silence" and merged[i + 1]["type"] != "silence":
            merged[i]["type"], merged[i]["reason"] = merged[i + 1]["type"], merged[i + 1]["reason"]
        del merged[i + 1]
    else:
        i += 1
# Edges of the kept clips. A take cut is set on Premiere words; when one of them is dated
# inside a silence, the clip keeps that silence at its edge (1.6 s before a sentence), or an
# isolated 0.1 s fragment (a one-letter word before the next one). The editor removes both by
# hand: they are removed here. Sound = above QUIET; 0.25 s of air is left after the last
# speech, 0.20 s before the first, as in silence_cuts.py.
def sons(a, b):
    """Sound ranges in [a, b] (gaps under 0.15 s merged): [(start, end)]."""
    on = rms[int(a / HOP): int(b / HOP)] > QUIET
    out, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            s0, s1 = a + i * HOP, a + j * HOP
            if out and s0 - out[-1][1] < 0.15:
                out[-1] = (out[-1][0], s1)
            else:
                out.append((s0, s1))
            i = j
        else:
            i += 1
    return out


for i in range(len(merged) + 1):
    k0 = merged[i - 1]["end"] if i > 0 else 0.0
    k1 = merged[i]["start"] if i < len(merged) else DUR
    r = sons(k0, k1)
    if not r:
        continue
    # A sound of less than 0.25 s isolated at the edge: noise (peak < 0.2 x p95) -> removed;
    # otherwise it may be an intended word (a one-word sentence after a silence) -> doubt.
    for bord in ("head", "tail"):
        ok = i > 0 if bord == "head" else i < len(merged)
        e, v = (r[0], r[1]) if bord == "head" and len(r) > 1 else (r[-1], r[-2]) if len(r) > 1 else (None, None)
        if not ok or e is None or e[1] - e[0] >= 0.25 or (v[0] - e[1] if bord == "head" else e[0] - v[1]) < 0.5:
            continue
        crete = float(rms[int(e[0] / HOP): int(e[1] / HOP) + 1].max())
        if crete < 0.2 * P95:
            print(f"fragment at the {bord} of a clip {e[0]:.2f} ({e[1] - e[0]:.2f} s) removed")
            r = r[1:] if bord == "head" else r[:-1]
        else:
            print(f"isolated word at the {bord} of a clip {e[0]:.2f}: doubt")
            flags.append({"start": round(e[0], 2), "end": round(e[1] + 0.3, 2), "decision": "flag", "confidence": 0.6,
                          "type": "eclat", "reason": REASONS["isolated_sound_" + bord].format(duration=e[1] - e[0])})
    if i > 0 and r[0][0] - 0.20 > k0 + 0.35:
        print(f"gap at the head of a clip {k0:.2f}-{r[0][0] - 0.20:.2f} removed")
        merged[i - 1]["end"] = round(r[0][0] - 0.20, 2)
    fin_du_rush = i < len(merged) and merged[i]["end"] >= DUR - 0.05  # the air after the last word is kept
    if i < len(merged) and not fin_du_rush and r[-1][1] + 0.25 < k1 - 0.35:
        print(f"gap at the tail of a clip {r[-1][1] + 0.25:.2f}-{k1:.2f} removed")
        merged[i]["start"] = round(r[-1][1] + 0.25, 2)

for m in merged:
    m["end"] = min(m["end"], DUR)

sil_flags = [c for c in sil_keep if c["decision"] == "flag"]
final = sorted(merged + flags + sil_flags, key=lambda c: c["start"])
(W / "cuts_final.json").write_text(json.dumps({"cuts": final}, ensure_ascii=False, indent=1))

cut = sum(m["end"] - m["start"] for m in merged)
print(f"{len(sem)} take cuts, {len(sil_keep)} silences -> {len(merged)} merged cuts, "
      f"{cut:.1f} s removed, edit {(DUR - cut) / 60:.2f} min out of {DUR / 60:.2f}")
print(f"{len(flags)} editorial doubts, {len(sil_flags)} noisy silences in doubt")
