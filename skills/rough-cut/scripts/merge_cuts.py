#!/usr/bin/env python3
"""Merges the mechanical and semantic cuts, scoring + final decision.

Rules:
- Decision: confidence >= 0.85 → 'disable', 0.6..0.85 → 'flag', < 0.6 → dropped.
- Semantic (LLM) cuts: boundaries snapped to the whisper word boundaries
  (an LLM often returns timecodes that are only roughly on the word). Cuts outside the clip are rejected.
- When two cuts overlap, the widest one is kept (with the highest confidence).

Usage:
    python3 merge_cuts.py <cuts_mech> <cuts_sem> <meta> <cuts_final> [transcript]
"""
import difflib
import json
import re
import sys
from pathlib import Path


def normalize_word(w):
    """Lowercase + strip punctuation, for the fuzzy match."""
    return re.sub(r"[^\w]", "", w.lower(), flags=re.UNICODE)


def fuzzy_locate_text(matched_text, words, hint_start, hint_end, search_radius=15.0):
    """Looks for matched_text in words around the hint, returns (idx_start, idx_end_exclusive).

    matched_text: excerpt of the speech according to the LLM.
    words: [{text, start, end}, ...]
    hint_start, hint_end: approximate timecodes given by the LLM.
    search_radius: tolerance in seconds, to limit the search.

    Returns None when the match is too weak (ratio < 0.6).
    """
    target = [normalize_word(w) for w in matched_text.split() if normalize_word(w)]
    if not target:
        return None

    candidate_idx = [
        i for i, w in enumerate(words)
        if (hint_start - search_radius) <= w["start"] <= (hint_end + search_radius)
    ]
    if not candidate_idx:
        return None

    candidate_norm = [normalize_word(words[i]["text"]) for i in candidate_idx]

    matcher = difflib.SequenceMatcher(a=target, b=candidate_norm, autojunk=False)
    blocks = [b for b in matcher.get_matching_blocks() if b.size > 0]
    if not blocks:
        return None

    matched_count = sum(b.size for b in blocks)
    ratio = matched_count / len(target)
    if ratio < 0.6:
        return None

    first_b = min(b.b for b in blocks)
    last_b = max(b.b + b.size for b in blocks)
    return candidate_idx[first_b], candidate_idx[last_b - 1] + 1


def overlaps(a, b):
    return not (a["end"] <= b["start"] or b["end"] <= a["start"])


def merge_overlapping(cuts):
    if not cuts:
        return []
    cuts = sorted(cuts, key=lambda c: c["start"])
    merged = [cuts[0]]
    for c in cuts[1:]:
        last = merged[-1]
        if overlaps(last, c):
            last["start"] = min(last["start"], c["start"])
            last["end"] = max(last["end"], c["end"])
            if c["confidence"] > last["confidence"]:
                last["confidence"] = c["confidence"]
                last["type"] = c["type"]
                last["reason"] = c["reason"]
                last["matched_text"] = c["matched_text"]
                last["source"] = c.get("source", "mechanical")
        else:
            merged.append(c)
    return merged


def assign_decision(cuts):
    """Final decision.

    Mechanical cuts: disable when conf >= 0.85.
    Semantic (LLM) cuts: disable only when conf >= 0.92 (an LLM often overshoots
    its boundaries). Fewer false positives, at the price of a few true positives.
    """
    out = []
    for c in cuts:
        conf = c["confidence"]
        is_sem = c.get("source") == "semantic"
        disable_threshold = 0.92 if is_sem else 0.85
        if conf >= disable_threshold:
            c["decision"] = "disable"
            out.append(c)
        elif conf >= 0.6:
            c["decision"] = "flag"
            out.append(c)
    return out


def extract_words(transcript):
    """Flat list of the words with start/end, from the whisper transcript."""
    words = []
    for seg in transcript.get("segments", []):
        for w in seg.get("words", []):
            if "start" in w and "end" in w:
                words.append({"start": float(w["start"]), "end": float(w["end"])})
    words.sort(key=lambda w: w["start"])
    return words


def snap_to_words(cut, words, max_drift=0.6):
    """Snaps start to the start of the nearest word, end to the start of the next word.

    max_drift: largest tolerance in seconds for the snap to be valid.
    Returns None when the snap is impossible (cut outside the transcript or drift too large).
    """
    if not words:
        return cut

    s_target, e_target = cut["start"], cut["end"]

    # Snap start: the word whose start is the nearest
    best_start = min(words, key=lambda w: abs(w["start"] - s_target))
    if abs(best_start["start"] - s_target) > max_drift:
        return None  # cut out of range, rejected

    # Snap end: the word whose start comes right after e_target (= start of the word to keep)
    candidates_end = [w for w in words if w["start"] >= e_target - max_drift]
    if not candidates_end:
        return None
    best_end = min(candidates_end, key=lambda w: abs(w["start"] - e_target))
    if abs(best_end["start"] - e_target) > max_drift:
        # Fallback: take the end of the last word before e_target
        before = [w for w in words if w["end"] <= e_target + max_drift]
        if not before:
            return None
        snapped_end = max(before, key=lambda w: w["end"])["end"]
    else:
        snapped_end = best_end["start"]

    new_cut = dict(cut)
    new_cut["start"] = best_start["start"]
    new_cut["end"] = snapped_end
    if new_cut["end"] <= new_cut["start"]:
        return None
    return new_cut


def main():
    if len(sys.argv) not in (5, 6):
        print("Usage: merge_cuts.py <cuts_mech> <cuts_sem> <meta> <cuts_final> [transcript]",
              file=sys.stderr)
        sys.exit(1)

    mech = json.loads(Path(sys.argv[1]).read_text()).get("cuts", [])
    sem_path = Path(sys.argv[2])
    sem = json.loads(sem_path.read_text()).get("cuts", []) if sem_path.exists() else []
    meta = json.loads(Path(sys.argv[3]).read_text())
    out_path = Path(sys.argv[4])
    transcript_path = Path(sys.argv[5]) if len(sys.argv) == 6 else None

    duration = meta.get("duration_seconds", 0)

    for c in mech:
        c.setdefault("source", "mechanical")
    for c in sem:
        c.setdefault("source", "semantic")

    # Filter out the LLM cuts outside the clip + snap them to the whisper words.
    # Strategy: when matched_text is there, the fuzzy match comes first (it tightens
    # the LLM boundaries that overshoot). Otherwise, snap to the nearest words.
    if sem and transcript_path and transcript_path.exists():
        transcript = json.loads(transcript_path.read_text())
        # extract_words with a list of full objects (text included)
        word_objs = []
        for seg in transcript.get("segments", []):
            for w in seg.get("words", []):
                if "start" in w and "end" in w and w.get("text"):
                    word_objs.append({
                        "text": w["text"],
                        "start": float(w["start"]),
                        "end": float(w["end"]),
                    })
        word_objs.sort(key=lambda w: w["start"])

        snapped = []
        rejected = 0
        relocated = 0
        for c in sem:
            if c["start"] < 0 or c["end"] > duration + 0.5:
                rejected += 1
                continue

            new_cut = None
            mt = c.get("matched_text", "").strip()
            if mt and len(mt.split()) >= 4 and word_objs:
                loc = fuzzy_locate_text(mt, word_objs, c["start"], c["end"])
                if loc:
                    s_idx, e_idx = loc
                    new_cut = dict(c)
                    new_cut["start"] = word_objs[s_idx]["start"]
                    # end = start of the next word to keep, or end of the last matched one
                    if e_idx < len(word_objs):
                        new_cut["end"] = word_objs[e_idx]["start"]
                    else:
                        new_cut["end"] = word_objs[e_idx - 1]["end"]
                    if new_cut["end"] > new_cut["start"]:
                        relocated += 1
                    else:
                        new_cut = None

            if new_cut is None:
                new_cut = snap_to_words(c, word_objs)
            if new_cut is None:
                rejected += 1
                continue
            snapped.append(new_cut)
        if rejected or relocated:
            print(f"Semantic: {relocated} relocated through matched_text, {rejected} rejected")
        sem = snapped

    all_cuts = mech + sem
    merged = merge_overlapping(all_cuts)
    final = assign_decision(merged)

    time_removed = sum(c["end"] - c["start"] for c in final if c["decision"] == "disable")
    stats = {
        "cuts_disabled": sum(1 for c in final if c["decision"] == "disable"),
        "cuts_flagged": sum(1 for c in final if c["decision"] == "flag"),
        "cuts_total": len(final),
        "time_removed_seconds": round(time_removed, 2),
        "ratio": round(time_removed / duration, 4) if duration else 0,
        "duration_seconds": duration,
    }

    out_path.write_text(json.dumps({
        "cuts": final,
        "stats": stats,
    }, indent=2, ensure_ascii=False))

    print(f"Final cuts: {stats['cuts_total']} ({stats['cuts_disabled']} disable, "
          f"{stats['cuts_flagged']} flag) - {stats['time_removed_seconds']:.1f}s saved "
          f"({stats['ratio'] * 100:.0f}%)")


if __name__ == "__main__":
    main()
