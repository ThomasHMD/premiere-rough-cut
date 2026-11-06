#!/usr/bin/env python3
"""Deterministic post-edit QC: detects the takes that survived in the rough cut.

Principle: the transcript of the RESULTING edit is rebuilt (words kept once the
disable cuts are applied), then searched for word n-grams repeated less than
window_s apart. A close repetition is either a surviving retake (a rough-cut miss)
or intended rhetoric (anaphora, enumeration): to check against the script.

Second pass: SENTENCE-START RESTARTS. The 2 words that follow a pause (>= 0.3 s)
or a cut already appeared less than 8 s of edit earlier ("by computing the gap
in the colors, | by computing the gap between the colors", "On this camera, | On
this camera, there is..."). Takes repeated with a variant escape the 5-grams; on a
real video this check found 5 that the editor had cut, for 9 intended repetitions.

Exit code 2 when at least one hit is not covered by --allow. This is the mechanical
acceptance test of the deliverable.

Usage:
    python3 qc_repeat_scan.py <words_premiere.json> <cuts_final.json>
        [--ngram 5] [--window 30] [--allow file.txt]
        [--reprise-mots 2] [--reprise-pause 0.3] [--reprise-fenetre 8]

--allow: one normalized pattern per line (lowercase, accents removed); any hit whose
n-gram contains a pattern is ignored.
--reprise-mots / --reprise-pause / --reprise-fenetre: number of words, minimal pause (s)
and largest gap (s of edit) of the sentence-start restart pass.
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path


def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^\w']", "", t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words_json")
    ap.add_argument("cuts_json")
    ap.add_argument("--ngram", type=int, default=5)
    ap.add_argument("--window", type=float, default=30.0)
    ap.add_argument("--allow", default=None)
    ap.add_argument("--reprise-mots", type=int, default=2)
    ap.add_argument("--reprise-pause", type=float, default=0.3)
    ap.add_argument("--reprise-fenetre", type=float, default=8.0, help="largest gap, in seconds of edit")
    args = ap.parse_args()

    words = json.loads(Path(args.words_json).read_text())
    cuts = [c for c in json.loads(Path(args.cuts_json).read_text())["cuts"]
            if c["decision"] == "disable"]
    allow = []
    if args.allow:
        allow = [l.strip() for l in Path(args.allow).read_text().splitlines() if l.strip()]

    def kept(w):
        mid = (w["start"] + w["end"]) / 2
        return not any(c["start"] <= mid <= c["end"] for c in cuts)

    kw = [(norm(w["text"]), w["start"]) for w in words if kept(w) and norm(w["text"])]
    kws = [w for w in words if kept(w) and norm(w["text"])]

    seen = defaultdict(list)
    n = args.ngram
    for i in range(len(kw) - n + 1):
        seen[" ".join(t for t, _ in kw[i:i + n])].append(kw[i][1])

    hits = []
    for gram, starts in seen.items():
        if any(a in gram for a in allow):
            continue
        for a, b in zip(starts, starts[1:]):
            if b - a < args.window:
                hits.append((a, b, gram))

    # dedupe the overlapping n-grams (shifted variants of the same hit)
    hits.sort()
    merged = []
    for a, b, g in hits:
        if merged and a - merged[-1][0] < args.ngram + 2 and abs(b - merged[-1][1]) < args.ngram + 2:
            continue
        merged.append((a, b, g))

    # Sentence-start restarts: 2 words after a pause or a cut, already said just before.
    def montage(a, b):
        """Kept duration between a and b (clip time): the gap as heard in the edit."""
        d = b - a
        for c in cuts:
            d -= max(0.0, min(b, c["end"]) - max(a, c["start"]))
        return d

    reprises = []
    for j in range(1, len(kws) - args.reprise_mots + 1):
        p, w = kws[j - 1], kws[j]
        coupe = any(p["start"] < c["start"] and c["end"] <= w["start"] + 0.05 for c in cuts)
        if not coupe and w["start"] - p["end"] < args.reprise_pause:
            continue
        g = [norm(x["text"]) for x in kws[j:j + args.reprise_mots]]
        for i in range(max(0, j - 40), j - args.reprise_mots + 1):
            if [norm(x["text"]) for x in kws[i:i + args.reprise_mots]] != g:
                continue
            if montage(kws[i]["start"], w["start"]) > args.reprise_fenetre:
                continue
            txt = " ".join(g)
            if not any(a in txt for a in allow):
                reprises.append((kws[i]["start"], w["start"], " ".join(x["text"] for x in kws[i:j]),
                                 " ".join(x["text"] for x in kws[j:j + 6])))
            break

    if merged:
        print(f"{len(merged)} close repetition(s) in the edit: surviving "
              f"retake OR intended rhetoric, check against the script:")
        for a, b, g in merged:
            print(f"  {a:7.1f}s ↔ {b:7.1f}s: \"{g}\"")
    if reprises:
        print(f"{len(reprises)} sentence-start restart(s): repeated take (keep the LAST one) OR "
              f"intended repetition, listen to it (hear.py):")
        for a, b, avant, apres in reprises:
            print(f"  {a:7.1f}s ↔ {b:7.1f}s: \"{avant[-90:]}\" | \"{apres}\"")
    if merged or reprises:
        sys.exit(2)
    print("QC OK: no close repetition in the edit.")


if __name__ == "__main__":
    main()
