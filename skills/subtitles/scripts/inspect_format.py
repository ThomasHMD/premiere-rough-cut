#!/usr/bin/env python3
"""Inspects a Premiere subtitle JSON: format (keys/types), speaker, language,
and the current text segment by segment (= the typos to fix).

Usage: python3 inspect_format.py <premiere.json>
"""
import json, sys

def main():
    if len(sys.argv) != 2:
        print("Usage: inspect_format.py <premiere.json>", file=sys.stderr); sys.exit(1)
    d = json.load(open(sys.argv[1]))

    seg_keys, word_keys = set(), set()
    confs, eos_true, types = set(), 0, set()
    for s in d.get("segments", []):
        seg_keys |= set(s)
        for w in s.get("words", []):
            word_keys |= set(w)
            confs.add(w.get("confidence")); types.add(w.get("type"))
            if w.get("eos"): eos_true += 1

    print("=== FORMAT ===")
    print("top keys     :", sorted(d.keys()))
    print("segment keys :", sorted(seg_keys))
    print("word keys    :", sorted(word_keys))
    print("language     :", d.get("language"))
    sp = (d.get("speakers") or [{}])
    print("speakers     :", [(x.get("id"), x.get("name")) for x in sp])
    nseg = len(d.get("segments", []))
    nw = sum(len(s.get("words", [])) for s in d.get("segments", []))
    print(f"segments     : {nseg} | words: {nw} | eos=true: {eos_true} | types: {types}")
    # timings in seconds?
    if nseg:
        last = d["segments"][-1]["words"][-1]
        end = last.get("start", 0) + last.get("duration", 0)
        print(f"end of last word: {end:.2f} (in seconds if consistent with the video duration)")

    print("\n=== CURRENT TEXT (typos to fix) ===")
    for i, s in enumerate(d.get("segments", [])):
        txt = " ".join(w.get("text", "") for w in s.get("words", []))
        st = s.get("start", 0)
        print(f"[{i:02d}] {st:6.2f}  {txt}")

if __name__ == "__main__":
    main()
