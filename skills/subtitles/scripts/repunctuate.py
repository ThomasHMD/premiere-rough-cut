#!/usr/bin/env python3
"""Puts editorial punctuation back into a whisper transcript that has none
(continuous-speech case: whisper returns a stream without commas or periods, so the subtitles are unreadable).

Claude supplies, in a JSON, the punctuated text of each segment KEEPING the whisper words
verbatim (same words, same order: only +punctuation attached +sentence capitals).
The script VALIDATES that each text has exactly the same words (case/punctuation-insensitive)
as the whisper segment, otherwise it refuses and shows the diff (safety: keeps the
word<->timing alignment). build_subs.py then puts this punctuation back onto the timed words.

Usage:
    python3 repunctuate.py --transcript in.json --punct punct.json --output out.json [--lang fr]

punct.json: {"0": "Hello! It's been...", "1": "...", ...}  (segment index -> punctuated text)
Segments missing from the file are left as they are.
The language (--lang, else the transcript's, else en) selects the accented letters ignored
when comparing words, from ../languages/<code>.json.
"""
import argparse, json, re, sys

import lang

_NON_WORD = None

def clean(w):
    return _NON_WORD.sub("", w.lower())

def main():
    global _NON_WORD
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--punct", required=True, help="JSON {segment_index: punctuated text}")
    ap.add_argument("--output", required=True)
    lang.add_argument(ap)
    args = ap.parse_args()

    d = json.load(open(args.transcript))
    punct = json.load(open(args.punct))
    punct = {int(k): v for k, v in punct.items()}
    _NON_WORD = re.compile(lang.non_word_pattern(lang.load(lang.resolve(args.lang, d.get("language")))))

    errors = 0
    for i, seg in enumerate(d["segments"]):
        if i not in punct:
            continue
        whisper_words = [clean(w["text"]) for w in seg["words"]]
        my_words = [clean(t) for t in punct[i].split() if clean(t)]
        if whisper_words != my_words:
            errors += 1
            print(f"⚠️ SEG {i}: the words do not match (you added/removed/changed a word).", file=sys.stderr)
            for j in range(max(len(whisper_words), len(my_words))):
                a = whisper_words[j] if j < len(whisper_words) else "-"
                b = my_words[j] if j < len(my_words) else "-"
                if a != b:
                    print(f"   1st divergence at pos {j}: whisper='{a}'  you='{b}'", file=sys.stderr)
                    break
            continue
        seg["text"] = punct[i]

    if errors:
        print(f"\n{errors} segment(s) in error: NOTHING written. Keep ONLY punctuation/case, "
              f"no word added/removed (lexical fixes go in corrections.json).", file=sys.stderr)
        sys.exit(1)

    json.dump(d, open(args.output, "w"), ensure_ascii=False)
    print(f"OK: punctuated transcript: {args.output} ({len(punct)} segments punctuated)")

if __name__ == "__main__":
    main()
