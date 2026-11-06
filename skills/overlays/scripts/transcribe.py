#!/usr/bin/env python3
"""Transcribes a video rush with whisper.cpp and produces <rush>_transcription.json.

Output format (flat, compatible with render-segments.py):
{
  "rush_path": "...",
  "language": "en",
  "model": "large-v3-turbo",
  "duration_seconds": 600.0,
  "words": [
    {"word": "Hello", "start": 0.84, "end": 1.21, "confidence": 0.98},
    ...
  ]
}

Reuses the rough-cut logic (whisper-cli + model in ~/Models/whisper).

Usage:
    python3 transcribe.py /path/rush.mp4
    python3 transcribe.py /path/rush.mp4 --model large-v3 --language en
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_MODEL_DIR = Path.home() / "Models" / "whisper"
WHISPER_BINARIES = ["whisper-cli", "whisper-cpp", "main"]


def find_whisper_binary() -> str | None:
    for name in WHISPER_BINARIES:
        found = shutil.which(name)
        if found:
            return found
        fallback = Path("/opt/homebrew/bin") / name
        if fallback.exists():
            return str(fallback)
    return None


def find_model(model_name: str) -> Path | None:
    candidates = [
        DEFAULT_MODEL_DIR / f"ggml-{model_name}.bin",
        DEFAULT_MODEL_DIR / f"{model_name}.bin",
        Path(model_name).expanduser(),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def extract_audio(video: Path, out_wav: Path) -> float:
    """Extracts the audio as 16 kHz mono WAV and returns the duration in seconds."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-ac", "1", "-ar", "16000", "-vn",
        str(out_wav),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    # Duration via ffprobe
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, check=True,
    )
    return float(probe.stdout.strip())


def normalize_to_flat_words(raw: dict) -> list[dict]:
    """Converts the whisper.cpp output into a flat list {word, start, end, confidence}."""
    flat_words: list[dict] = []
    raw_segments = raw.get("transcription", []) or raw.get("segments", [])

    for seg in raw_segments:
        offsets = seg.get("offsets") or {}
        if offsets:
            seg_start = offsets["from"] / 1000.0
            seg_end = offsets["to"] / 1000.0
        else:
            seg_start = float(seg.get("start", 0))
            seg_end = float(seg.get("end", seg_start))
        text = seg.get("text", "").strip()
        if not text:
            continue

        # Words with timecodes via BPE tokens (whisper.cpp with --output-json-full)
        words: list[dict] = []
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
                    w_start = float(tok.get("start", seg_start))
                    w_end = float(tok.get("end", seg_end))
                p = tok.get("p")
                conf = float(p) if p is not None and 0 <= p <= 1 else 0.9

                stripped = tok_text_raw.lstrip()
                starts_new = (
                    tok_text_raw.startswith(" ")
                    or current is None
                    or stripped[:1] in ".!?,:;«»"  # fr-ok: includes French guillemets
                )
                if starts_new:
                    if current:
                        words.append(current)
                    current = {
                        "word": stripped,
                        "start": round(w_start, 3),
                        "end": round(w_end, 3),
                        "confidence": round(conf, 3),
                    }
                else:
                    current["word"] += stripped
                    current["end"] = round(w_end, 3)
                    current["confidence"] = round(min(current["confidence"], conf), 3)
            if current:
                words.append(current)
            words = [w for w in words if any(c.isalnum() for c in w["word"])]

        # Fallback: no tokens, spread the words linearly across the segment
        if not words:
            toks = text.split()
            if toks:
                step = (seg_end - seg_start) / len(toks)
                for j, t in enumerate(toks):
                    words.append({
                        "word": t,
                        "start": round(seg_start + j * step, 3),
                        "end": round(seg_start + (j + 1) * step, 3),
                        "confidence": 0.85,
                    })

        flat_words.extend(words)

    return flat_words


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Path to the rush video (mp4/mov/mkv)")
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--language", "--lang", dest="language", default=None,
                        help="spoken language code (fr, en...); default: whisper detects it")
    parser.add_argument("--output", help="Path of the output JSON (default: <rush>_transcription.json)")
    args = parser.parse_args()

    video = Path(args.video).resolve()
    if not video.exists():
        print(f"ERROR: video not found: {video}", file=sys.stderr)
        sys.exit(1)

    out_json = Path(args.output) if args.output else video.with_name(video.stem + "_transcription.json")

    whisper = find_whisper_binary()
    if not whisper:
        print("ERROR: whisper.cpp not found. brew install whisper-cpp", file=sys.stderr)
        sys.exit(1)

    model = find_model(args.model)
    if not model:
        print(f"ERROR: model not found: {args.model}", file=sys.stderr)
        print(f"Expected in: {DEFAULT_MODEL_DIR}/ggml-{args.model}.bin", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="overlays-") as tmp:
        tmp_dir = Path(tmp)
        wav = tmp_dir / "audio.wav"
        print(f"[1/3] Extracting 16 kHz mono WAV audio...")
        duration = extract_audio(video, wav)

        raw_prefix = tmp_dir / "whisper_raw"
        raw_json = Path(str(raw_prefix) + ".json")

        cmd = [
            whisper, "-m", str(model), "-l", args.language or "auto", "-f", str(wav),
            "-of", str(raw_prefix),
            "--output-json", "--output-json-full",
            "--print-progress",
        ]
        print(f"[2/3] whisper.cpp transcription ({args.model})...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"whisper ERROR: {result.stderr[:1000]}", file=sys.stderr)
            sys.exit(1)

        if not raw_json.exists():
            print(f"ERROR: whisper did not produce a JSON: {raw_json}", file=sys.stderr)
            print(result.stdout[-500:], file=sys.stderr)
            sys.exit(1)

        raw = json.loads(raw_json.read_text())

    print(f"[3/3] Normalizing to flat format...")
    words = normalize_to_flat_words(raw)

    transcript = {
        "rush_path": str(video),
        "language": args.language or (raw.get("result") or {}).get("language") or "en",
        "model": args.model,
        "duration_seconds": duration,
        "words": words,
    }
    out_json.write_text(json.dumps(transcript, indent=2, ensure_ascii=False))
    print(f"Transcript written: {out_json} ({len(words)} words, {duration:.1f}s)")


if __name__ == "__main__":
    main()
