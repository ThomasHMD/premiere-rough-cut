#!/usr/bin/env python3
"""Transcribes a WAV audio with whisper.cpp and normalizes it to our format.

Looks for the whisper-cli binary (recent versions) or whisper-cpp or main (older builds).
Normalized output: transcript.json with timed words and confidence.

Usage:
    python3 transcribe.py audio.wav transcript.json --model large-v3-turbo --meta meta.json [--lang fr]

--lang (alias --language) is the spoken language; without it whisper detects it by itself, and
the detected language is recorded in transcript.json ("en" if detection gives nothing).
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import lang

DEFAULT_MODEL_DIR = Path.home() / "Models" / "whisper"
WHISPER_BINARIES = ["whisper-cli", "whisper-cpp", "main"]
BREAK_PUNCT = ".!?,:;"   # set from the language file in main()


def check_binary(name):
    found = shutil.which(name)
    if found:
        return found
    fallback = Path("/opt/homebrew/bin") / name
    if fallback.exists():
        return str(fallback)
    return None


def find_whisper_binary():
    for name in WHISPER_BINARIES:
        path = check_binary(name)
        if path:
            return path
    return None


def find_model(model_name):
    """Looks for the ggml-<name>.bin model in ~/Models/whisper/."""
    candidates = [
        DEFAULT_MODEL_DIR / f"ggml-{model_name}.bin",
        DEFAULT_MODEL_DIR / f"{model_name}.bin",
        Path(model_name).expanduser(),  # if the user passes a direct path
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def normalize_whisper_output(raw, audio_path, language):
    """Converts the whisper.cpp JSON output to our transcript.json format.

    whisper.cpp v1.7+ produces:
    {
      "transcription": [
        {"timestamps": {"from": "00:00:00,840", "to": "00:00:02,310"},
         "offsets": {"from": 840, "to": 2310},
         "text": " Hello everyone"}
      ]
    }

    In some versions, --output-words also adds a "tokens" array with
    per-token timing. We stay defensive: if there are no words, we generate
    placeholder words by spreading the segment's timecodes linearly.
    """
    segments = []
    raw_segments = raw.get("transcription", []) or raw.get("segments", [])

    for i, seg in enumerate(raw_segments):
        # Timestamps (in ms or seconds depending on the version)
        offsets = seg.get("offsets") or {}
        if offsets:
            start = offsets["from"] / 1000.0
            end = offsets["to"] / 1000.0
        else:
            start = float(seg.get("start", 0))
            end = float(seg.get("end", start))
        text = seg.get("text", "").strip()
        if not text:
            continue

        # Words with timecodes: whisper.cpp returns BPE tokens that can
        # be sub-parts of words ("phot" + "ograp" + "her"). We merge them.
        words = []
        if "tokens" in seg and isinstance(seg["tokens"], list):
            current = None
            for tok in seg["tokens"]:
                tok_text_raw = tok.get("text", "")
                if not tok_text_raw or tok_text_raw.strip().startswith("["):
                    continue
                tok_offsets = tok.get("offsets") or {}
                if tok_offsets:
                    w_start = tok_offsets["from"] / 1000.0
                    w_end = tok_offsets["to"] / 1000.0
                else:
                    w_start = float(tok.get("start", start))
                    w_end = float(tok.get("end", end))
                p = tok.get("p")
                conf = float(p) if p is not None and 0 <= p <= 1 else 0.9

                # A new word starts if:
                # - the token starts with a space (BPE convention)
                # - or it is strong punctuation (the language file's token_break_punct)
                # - or it is the very first token
                stripped = tok_text_raw.lstrip()
                starts_new_word = (
                    tok_text_raw.startswith(" ")
                    or current is None
                    or stripped[:1] in BREAK_PUNCT
                )
                if starts_new_word:
                    if current:
                        words.append(current)
                    current = {
                        "text": stripped,
                        "start": round(w_start, 3),
                        "end": round(w_end, 3),
                        "confidence": round(conf, 3),
                    }
                else:
                    # Continuation of the current word: glue the token on the end
                    current["text"] += stripped
                    current["end"] = round(w_end, 3)
                    current["confidence"] = round(min(current["confidence"], conf), 3)

            if current:
                words.append(current)

            # Filter out the "words" that are just punctuation
            words = [w for w in words if any(c.isalnum() for c in w["text"])]

        # Fallback: no timed words, split linearly
        if not words:
            tokens = text.split()
            if tokens:
                step = (end - start) / len(tokens)
                for j, t in enumerate(tokens):
                    words.append({
                        "text": t,
                        "start": round(start + j * step, 3),
                        "end": round(start + (j + 1) * step, 3),
                        "confidence": 0.85,
                    })

        segments.append({
            "id": f"s_{i:04d}",
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
            "words": words,
        })

    return {
        "rush_path": str(audio_path),
        "language": language,
        "segments": segments,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", help="Path to the WAV audio")
    parser.add_argument("output", help="Path of the transcript.json to write")
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--language", "--lang", dest="language", default=None,
                        help="spoken language code (fr, en...); default: whisper detects it")
    parser.add_argument("--meta", help="Path of the meta.json to enrich with the model used")
    args = parser.parse_args()

    audio = Path(args.audio).resolve()
    out_json = Path(args.output).resolve()

    if not audio.exists():
        print(f"ERROR: audio not found: {audio}", file=sys.stderr)
        sys.exit(1)

    whisper = find_whisper_binary()
    if not whisper:
        print("ERROR: whisper.cpp not found. Install it: brew install whisper-cpp", file=sys.stderr)
        sys.exit(1)

    model = find_model(args.model)
    if not model:
        print(f"ERROR: model not found: {args.model}", file=sys.stderr)
        print(f"Expected download location: {DEFAULT_MODEL_DIR}/ggml-{args.model}.bin", file=sys.stderr)
        print("See references/whisper-setup.md", file=sys.stderr)
        sys.exit(1)

    # whisper.cpp appends .json to the given prefix. We use a name different from the
    # final output file so we can delete it after normalization
    # without overwriting our output.
    raw_prefix = out_json.parent / (out_json.stem + ".whisper_raw")
    raw_json = Path(str(raw_prefix) + ".json")

    cmd = [
        whisper,
        "-m", str(model),
        "-l", args.language or "auto",
        "-f", str(audio),
        "-of", str(raw_prefix),
        "--output-json",
        "--output-json-full",  # includes tokens if supported
        "--print-progress",
    ]
    print(f"[whisper] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR whisper: {result.stderr[:1000]}", file=sys.stderr)
        sys.exit(1)

    if not raw_json.exists():
        print(f"ERROR: whisper did not produce a JSON: {raw_json}", file=sys.stderr)
        print(result.stdout[-500:], file=sys.stderr)
        sys.exit(1)

    raw = json.loads(raw_json.read_text())
    language = args.language or (raw.get("result") or {}).get("language") or lang.FALLBACK
    global BREAK_PUNCT
    BREAK_PUNCT = lang.load(lang.resolve(language))["token_break_punct"]
    transcript = normalize_whisper_output(raw, audio, language)
    transcript["model"] = args.model

    # Merge duration/fps from meta if available
    if args.meta and Path(args.meta).exists():
        meta = json.loads(Path(args.meta).read_text())
        transcript["duration_seconds"] = meta.get("duration_seconds")
        transcript["fps"] = meta.get("fps")
        transcript["rush_path"] = meta.get("rush_path", str(audio))

    out_json.write_text(json.dumps(transcript, indent=2, ensure_ascii=False))
    n_segments = len(transcript["segments"])
    n_words = sum(len(s["words"]) for s in transcript["segments"])
    print(f"Transcript written: {out_json} ({n_segments} segments, {n_words} words)")

    # Clean up the raw whisper output
    raw_json.unlink()


if __name__ == "__main__":
    main()
