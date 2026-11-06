#!/usr/bin/env python3
"""Converts a Premiere Pro transcript export (JSON) into timestamped words.

Why this file is MANDATORY (v2): whisper silently dedupes repeated takes (its
anti-loop decoder takes a sentence repeated verbatim for a hallucination and
compresses it: checked on a real clip, a sentence said twice was transcribed once,
not fixable by configuration, "-mc 0" only recovers part of it). The Premiere
transcript keeps every take, and its timestamps do not drift after long silences,
unlike whisper's. It is therefore the PRIMARY source for retakes and boundaries.

Export on the Premiere side: Text panel > Transcript > ... > Export > JSON.
Expected structure: {"segments": [{"words": [{"text", "start", "duration",
"eos", "type"}, ...]}]}

Usage:
    python3 parse_premiere_transcript.py <export_premiere.json> <words_premiere.json>
"""
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        print("Usage: parse_premiere_transcript.py <export.json> <words_out.json>",
              file=sys.stderr)
        sys.exit(1)

    data = json.loads(Path(sys.argv[1]).read_text())
    words = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            if w.get("type") != "word":
                continue
            # Premiere exports the PAUSES as items of type "word" with empty text
            # (51 on a test video, up to 1.6 s). Keeping them creates fake words that
            # fill the gaps and hide silences to cut. Checked against
            # extract_prproj_transcript.py: once the empty items are dropped on both
            # sides, the 4426 words match to 0.000000000 s.
            if not w["text"].strip():
                continue
            words.append({
                "text": w["text"],
                "start": w["start"],
                "end": w["start"] + w["duration"],
                "eos": bool(w.get("eos", False)),
            })

    if not words:
        print("ERROR: no word found, wrong export format?", file=sys.stderr)
        sys.exit(1)

    Path(sys.argv[2]).write_text(json.dumps(words, ensure_ascii=False))
    print(f"{len(words)} words, from {words[0]['start']:.2f}s to {words[-1]['end']:.2f}s")


if __name__ == "__main__":
    main()
