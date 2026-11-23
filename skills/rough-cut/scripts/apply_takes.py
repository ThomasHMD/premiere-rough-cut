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


# Air left on both sides of a take cut. Measured on a real video: take cuts left only
# 0.10 + 0.12 = 0.22 s, against 0.55 s for the silence cuts the editor had approved. Result
# by ear: the kept sentence has no time to settle before the next one, "you cut a sentence
# that is not finished" (the editor's reaction to the first join). We now match the silences.
AIR_A = 0.27        # after the last kept speech (end of clip A)
AIR_B = 0.28        # before the attack of the first kept speech (start of clip B)
AIR_TOTAL = 0.55    # target at the join; a shortfall on one side is taken from the other
AIR_MIN = 0.25      # below this, the cut lands in the middle of speech: we do not make it


# Speech mask: more tolerant than QUIET (which requires absolute silence and drops to zero
# as soon as there is a mouse or keyboard under the voice). Gaps shorter than TROU_MAX are
# filled in: a consonant closure (the /ʒ/ of French "je" after "longtemps") is a 60 ms dip
# in the middle of a run of words, not a breath. Without this filling, the cut lands in
# that dip and the kept sentence stops dead.
TH_PAROLE = P95 * 0.15
TROU_MAX = 0.09
BLIP_MAX = 0.07     # une syllabe dure plus longtemps ; en dessous c'est un claquement

_parole = rms > TH_PAROLE
# First the islands too short to be a syllable (tongue click, mouse, key click): without
# this, a 30 ms spike splits a 2.3 s silence in two and the air budget measured around it
# drops to 0.17 s.
_i = 0
while _i < len(_parole):
    if _parole[_i]:
        _j = _i
        while _j < len(_parole) and _parole[_j]:
            _j += 1
        if (_j - _i) * HOP < BLIP_MAX:
            _parole[_i:_j] = False
        _i = _j
    else:
        _i += 1
_i = 0
while _i < len(_parole):
    if not _parole[_i]:
        _j = _i
        while _j < len(_parole) and not _parole[_j]:
            _j += 1
        if _i > 0 and _j < len(_parole) and (_j - _i) * HOP < TROU_MAX:
            _parole[_i:_j] = True
        _i = _j
    else:
        _i += 1


def zone_sans_parole(t):
    """(start, end) of the SPEECHLESS gap around time t, or (t, t) if t falls in the middle
    of speech. Used to measure the air really available around a cut."""
    i = min(len(_parole) - 1, max(0, int(t / HOP)))
    if _parole[i]:
        # Premiere sometimes dates the word 30 ms too early or too late: look right next to it.
        for d in range(1, int(0.12 / HOP) + 1):
            if i - d >= 0 and not _parole[i - d]:
                i -= d
                break
            if i + d < len(_parole) and not _parole[i + d]:
                i += d
                break
        else:
            return t, t
    lo = i
    while lo > 0 and not _parole[lo - 1]:
        lo -= 1
    hi = i
    while hi < len(_parole) - 1 and not _parole[hi + 1]:
        hi += 1
    return lo * HOP, (hi + 1) * HOP


def paroles(a, b):
    """Ranges of SPEECH in [a, b], from the mask (clicks already discarded)."""
    i0, i1 = max(0, int(a / HOP)), min(len(_parole), int(b / HOP) + 1)
    out, i = [], i0
    while i < i1:
        if _parole[i]:
            j = i
            while j < i1 and _parole[j]:
                j += 1
            out.append((i * HOP, j * HOP))
            i = j
        else:
            i += 1
    return out


def air_bornes(t_coupe, t_garde):
    """Bounds of a take cut, with the air shared between the two sides.

    t_coupe = start of the first REMOVED word, t_garde = start of the first KEPT word after.
    Returns (start, end, air_a, air_b, budget): the budget is the silence actually
    available on both sides, which caps everything. When one side has nothing to give
    (cut placed in a run-on with no breath), the rest is taken from the other; if the
    total stays under AIR_MIN, the caller drops the cut."""
    lo_a, hi_a = zone_sans_parole(t_coupe)   # gap between the kept speech and the removed word
    lo_b, hi_b = zone_sans_parole(t_garde)   # gap between the removed speech and the kept word
    bud_a, bud_b = hi_a - lo_a, hi_b - lo_b
    air_a, air_b = min(AIR_A, bud_a), min(AIR_B, bud_b)
    manque = AIR_TOTAL - (air_a + air_b)
    if manque > 0:                        # take it from the side that still has room
        pris = min(manque, bud_b - air_b)
        air_b += pris
        manque -= pris
    if manque > 0:
        air_a += min(manque, bud_a - air_a)
    return lo_a + air_a, hi_b - air_b, air_a, air_b, bud_a + bud_b


def cut_end(t):
    """Cut end before the first kept word (used outside take cuts)."""
    lo, hi = quiet_zone(t)
    return max(lo, hi - AIR_B)


def cut_start(t):
    """Cut start at the first cut word (used outside take cuts)."""
    lo, hi = quiet_zone(t)
    return min(hi, lo + AIR_A)


sem = []
refus = []
for a, b, typ, conf, why, *opt in takes.get("cuts", []):
    air_a = air_b = None
    if b + 1 >= len(words):
        start = 0.0 if a is None else cut_start(words[a]["start"])
        end = DUR
    elif a is None:
        start = 0.0
        end = cut_end(words[b + 1]["start"])
    else:
        start, end, air_a, air_b, budget = air_bornes(words[a]["start"], words[b + 1]["start"])
        # Not enough silence on either side: the cut would land in the middle of speech and
        # the kept sentence would stop dead. We do not make it.
        # Only for cuts that end a take (retake, false start): a stutter or a correction is
        # removed IN THE MIDDLE of a sentence, the delivery carries on over it and there is
        # no air to leave.
        if not opt and typ in ("retake", "faux_depart") and budget < AIR_MIN:
            refus.append((words[a]["start"], budget, why))
            continue
    # optional 6th element {"start": s, "end": s}: boundary set by hand (in seconds)
    # when the edit QC shows a sound left at the edge (word badly cut by Premiere)
    manuel = bool(opt)
    if opt:
        start, end = opt[0].get("start", start), opt[0].get("end", end)
    # Cutting word 0 used to leave the blank before it (0.5 s, "fragment" at QC); and a word
    # said in one breath with the next ("Well, but") gave an empty cut, with no error: the
    # word stayed in the edit.
    if a == 0:
        start = 0.0
    if end - start < 0.05:
        print(f"⚠ empty cut {start:.2f}-{end:.2f} ({why[:60]}): word stuck to the next one, "
              f"set the bounds by hand (6th element, after hear.py)")
    sem.append({"start": round(start, 2), "end": round(end, 2), "decision": "disable",
                "confidence": conf, "type": typ, "reason": why,
                "words": [a if a is not None else 0, b],
                "coupe": " ".join(x["text"] for x in words[(a or 0): b + 1])[:160],
                "manuel": manuel,
                "air_a": None if air_a is None else round(air_a, 2),
                "air_b": None if air_b is None else round(air_b, 2),
                "garde_ensuite": " ".join(x["text"] for x in words[b + 1: b + 7])})
for t, budget, why in refus:
    print(f"⚠ cut dropped at {t:.2f}s: only {budget:.2f}s of silence available "
          f"(< {AIR_MIN}), it would cut in the middle of speech. {why[:70]}")
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
        m["manuel"] = m.get("manuel") or c.get("manuel", False)
        if c["type"] != "silence" and m["type"] == "silence":
            m["type"], m["reason"], m["confidence"] = c["type"], c["reason"], c["confidence"]
        elif c["type"] != "silence" and c["reason"] not in m["reason"]:
            m["reason"] += " + " + c["reason"]
    else:
        merged.append({k: c[k] for k in ("start", "end", "decision", "confidence", "type", "reason")})
        # "manuel" used to be lost here, so the air pass rewrote the hand-set boundaries
        # despite "it is law" below.
        merged[-1]["manuel"] = c.get("manuel", False)
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


sons_clip = {}
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
    sons_clip[i] = r

# Air at the join, single pass. Before, two mechanisms contradicted each other: take cuts
# were placed 0.10 / 0.12 s from the speech, then this re-trim brought any blank back to
# 0.20 / 0.25 s. In total 0.22 s at the join of a take cut, against 0.55 s on the silence
# cuts the editor had approved. By ear the kept sentence had no time to settle: "you cut a
# sentence that is not finished". Now a single budget, measured between the LAST SPEECH of
# the previous clip and the FIRST of the next one, taken from the side that has it.
for i, c in enumerate(merged):
    if c["end"] >= DUR - 0.05 or c["start"] <= 0.05:   # ends of the clip: handled above
        continue
    if c.get("manuel"):                   # hand-set bound: it is law
        continue
    av = paroles(merged[i - 1]["end"] if i > 0 else 0.0, c["start"])
    ap = paroles(c["end"], merged[i + 1]["start"] if i + 1 < len(merged) else DUR)
    if not av or not ap:
        continue
    fin_a, debut_b = av[-1][1], ap[0][0]
    # what SPEAKS in the removed material, bounds excluded (paroles() also returns the range
    # that starts at debut_b: keeping it wiped out all the air on side B)
    dedans = [r for r in paroles(fin_a, debut_b)
              if r[1] > fin_a + 1e-6 and r[0] < debut_b - 1e-6]
    if dedans:
        max_a, max_b = dedans[0][0] - fin_a, debut_b - dedans[-1][1]
    else:                                 # silence cut: the whole interval is blank
        max_a = max_b = debut_b - fin_a
    air_a, air_b = min(AIR_A, max_a), min(AIR_B, max_b)
    manque = AIR_TOTAL - (air_a + air_b)
    if manque > 0:
        pris = min(manque, max_b - air_b)
        air_b += pris
        manque -= pris
    if manque > 0:
        air_a += min(manque, max_a - air_a)
    start, end = round(fin_a + air_a, 2), round(debut_b - air_b, 2)
    if end - start > 0.05:
        if abs(start - c["start"]) > 0.02 or abs(end - c["end"]) > 0.02:
            print(f"air du raccord {c['start']:.2f}->{c['end']:.2f} : "
                  f"{start:.2f}->{end:.2f} ({air_a:.2f} + {air_b:.2f} = {air_a + air_b:.2f} s)")
        c["start"], c["end"] = start, end

for m in merged:
    m["end"] = min(m["end"], DUR)

sil_flags = [c for c in sil_keep if c["decision"] == "flag"]
final = sorted(merged + flags + sil_flags, key=lambda c: c["start"])
(W / "cuts_final.json").write_text(json.dumps({"cuts": final}, ensure_ascii=False, indent=1))

cut = sum(m["end"] - m["start"] for m in merged)
print(f"{len(sem)} take cuts, {len(sil_keep)} silences -> {len(merged)} merged cuts, "
      f"{cut:.1f} s removed, edit {(DUR - cut) / 60:.2f} min out of {DUR / 60:.2f}")
print(f"{len(flags)} editorial doubts, {len(sil_flags)} noisy silences in doubt")
