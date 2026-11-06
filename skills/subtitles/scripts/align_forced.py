#!/usr/bin/env python3
"""Re-times the words of a Premiere JSON on the AUDIO by forced alignment (wav2vec2 CTC).

WHY. whisper's word timestamps DRIFT (measured up to -7 s, non-linear) on fast monologues
with several takes: whisper squashes the silences between takes, so the voice arrives AFTER
the subtitle. DTW does not help; a warp on sparse anchors distorts the zones that were right.
The whisper text is good, only its TIMINGS are wrong.
Solution: force-align the final (corrected) text on the acoustics of the audio, so each word
is placed where it is actually spoken (median delta ~0 vs ground truth).

WHAT THE SCRIPT DOES. Takes the JSON already built by build_subs.py (text + list of correct
words) and REPLACES the start/duration of each word with its real acoustic position, keeping
the text, the schema, the speaker and the language identical. Strict 1:1 mapping:
1 JSON word = 1 aligned token (fails cleanly on a misalignment instead of producing wrong output).

PREREQUISITES (once per machine):
    pip3 install --break-system-packages ctc-forced-aligner torch torchaudio unidecode
    (the ~1.2 GB ONNX model downloads by itself on the first run, then is cached in ~/ctc_forced_aligner/)

Usage:
    python3 align_forced.py --subs <build.json> --audio <audio.wav|video.mp4> --output <final.json> [--lang fr]

The language (--lang, else the language of --subs, else en) selects ../languages/<code>.json,
which gives the ISO-639-3 code used for romanization (override with --language).
"""
import os, shutil, sys

# ctc_forced_aligner and speechbrain do not exist for Python 3.15: this script stays on 3.14.
if sys.version_info >= (3, 15) and shutil.which("python3.14"):
    os.execvp("python3.14", ["python3.14", *sys.argv])

import argparse
import json
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import lang

PLACEHOLDER = "um"   # replaced in main() by the language file's empty_token_placeholder


def clean_token(text):
    """1 JSON word -> 1 alignable token, WITHOUT inner space (otherwise the split breaks the 1:1).
    Removes punctuation + no-break space; keeps apostrophe and hyphen."""
    t = text.replace(" ", " ")
    t = "".join(c for c in t if not unicodedata.category(c).startswith("P") or c in "'-")
    t = t.replace(" ", "")
    return t or PLACEHOLDER  # never empty: keeps the index mapping intact


def ensure_wav(audio_path):
    """Returns a 16 kHz mono WAV. Extracts it with ffmpeg if the input is not one."""
    p = Path(audio_path).resolve()
    if p.suffix.lower() == ".wav":
        return str(p), None
    tmp = Path(tempfile.gettempdir()) / "align_forced_audio.wav"
    cmd = ["ffmpeg", "-y", "-i", str(p), "-vn", "-ac", "1", "-ar", "16000",
           "-c:a", "pcm_s16le", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR ffmpeg: {r.stderr[:400]}", file=sys.stderr)
        sys.exit(1)
    return str(tmp), tmp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subs", required=True, help="JSON built by build_subs.py")
    ap.add_argument("--audio", required=True, help="16 kHz mono WAV, or a video (audio extracted automatically)")
    ap.add_argument("--output", required=True, help="final JSON (NEVER overwrite the original Premiere file)")
    ap.add_argument("--language", help="ISO-639-3 code for romanization (default: from the language file)")
    lang.add_argument(ap)
    ap.add_argument("--batch", type=int, default=4)
    args = ap.parse_args()

    try:
        import ctc_forced_aligner as m
    except ModuleNotFoundError:
        print("ERROR: ctc-forced-aligner is missing. Install it with:\n"
              "  pip3 install --break-system-packages ctc-forced-aligner torch torchaudio unidecode",
              file=sys.stderr)
        sys.exit(1)

    doc = json.load(open(args.subs))
    data = lang.load(lang.resolve(args.lang, doc.get("language")))
    global PLACEHOLDER
    PLACEHOLDER = data["empty_token_placeholder"]
    if not args.language:
        args.language = data["iso3"]
    words = [w for s in doc["segments"] for w in s["words"]]
    if not words:
        print("ERROR: no words in --subs", file=sys.stderr)
        sys.exit(1)
    text = " ".join(clean_token(w["text"]) for w in words)

    wav, tmp = ensure_wav(args.audio)
    print(f"[align] {len(words)} words | audio={Path(wav).name} | loading ONNX model…")
    al = m.AlignmentSingleton()                     # downloads the model on the first run
    audio = m.load_audio(wav)
    vid = len(audio) / 16000.0
    print(f"[align] audio {vid:.1f}s | emissions (CPU, ~70s / 20 min)…")
    emissions, stride = m.generate_emissions(al.alignment_model, audio, batch_size=args.batch)
    tok_s, text_s = m.preprocess_text(text, romanize=True, language=args.language)
    segs, scores, blank = m.get_alignments(emissions, tok_s, al.alignment_tokenizer)
    spans = m.get_spans(tok_s, segs, blank)
    wts = m.postprocess_results(text_s, spans, stride, scores)
    real = [w for w in wts if w.get("text") not in ("<star>", "star", "*")]

    if len(real) != len(words):
        print(f"ERROR: {len(real)} aligned tokens != {len(words)} JSON words. "
              "1:1 mapping broken (romanization split/merged a word). "
              "Inspect, do not deliver.", file=sys.stderr)
        sys.exit(2)

    # Apply with guards: clamp to [0, duration], minimum duration, non-decreasing start
    prev = 0.0
    for w, a in zip(words, real):
        s = max(prev, min(float(a["start"]), vid))
        e = max(s + 0.05, min(float(a["end"]), vid))
        w["start"] = round(s, 6)
        w["duration"] = round(e - s, 6)
        prev = s
    for s in doc["segments"]:
        p = s["words"]
        s["start"] = p[0]["start"]
        s["duration"] = round(p[-1]["start"] + p[-1]["duration"] - p[0]["start"], 6)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    last = max(w["start"] + w["duration"] for w in words)
    overlaps = sum(1 for i in range(1, len(words)) if words[i]["start"] < words[i-1]["start"] - 1e-6)
    print(f"Written: {args.output}")
    print(f"Words: {len(words)} | last word end: {last:.2f}s / audio {vid:.2f}s | "
          f"overlaps: {overlaps}")
    if tmp and tmp.exists():
        tmp.unlink()


if __name__ == "__main__":
    main()
