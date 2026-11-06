#!/usr/bin/env python3
"""Prints the WORD-BY-WORD breakdown of a whisper transcript or a Premiere JSON.
Essential for step 4 (writing exact correction rules: knowing how many tokens a name takes,
whether hyphens are kept, etc.) and for step 7 (proofreading).

By default: for each segment, the rebuilt text THEN the list of INDEXED words
(this is what lets you write seq_rules/word_rules without guessing the tokenization).

Usage:
    python3 words_of.py <json> --all          # all segments
    python3 words_of.py <json> 2 9 38         # specific segments
    python3 words_of.py <json> 2 --plain      # text only, without the word index
"""
import json, sys

def main():
    if len(sys.argv) < 2:
        print("Usage: words_of.py <json> [ids... | --all] [--plain]", file=sys.stderr); sys.exit(1)
    d = json.load(open(sys.argv[1]))
    rest = sys.argv[2:]
    plain = "--plain" in rest
    rest = [a for a in rest if not a.startswith("--") or a == "--all"]
    segs = d.get("segments", [])
    if not rest or "--all" in rest:
        ids = range(len(segs))
    else:
        ids = [int(a) for a in rest if a.lstrip("-").isdigit()]

    for i in ids:
        if i < 0 or i >= len(segs):
            continue
        s = segs[i]
        words = [w.get("text", "") for w in s.get("words", [])]
        st = s.get("start", 0)
        print(f"[{i:02d}] {st:6.2f}  " + " ".join(words))
        if not plain:
            # indexed list: locates each token so rules can be written exactly
            indexed = "  ".join(f"{j}:{t}" for j, t in enumerate(words))
            print(f"        └ {indexed}")

if __name__ == "__main__":
    main()
