#!/usr/bin/env python3
"""Extracts the 16 kHz mono audio of the clip, as 16-bit PCM WAV.

This is the input whisper.cpp expects.

Usage:
    python3 extract_audio.py /path/clip.mp4 /path/output.wav
"""
import shutil
import subprocess
import sys
from pathlib import Path


def check_binary(name):
    found = shutil.which(name)
    if found:
        return found
    fallback = Path("/opt/homebrew/bin") / name
    if fallback.exists():
        return str(fallback)
    return None


def main():
    if len(sys.argv) != 3:
        print("Usage: extract_audio.py <clip> <output.wav>", file=sys.stderr)
        sys.exit(1)

    rush = Path(sys.argv[1]).resolve()
    out_wav = Path(sys.argv[2]).resolve()

    ffmpeg = check_binary("ffmpeg")
    if not ffmpeg:
        print("ERROR: ffmpeg not found. Install it: brew install ffmpeg", file=sys.stderr)
        sys.exit(1)

    cmd = [
        ffmpeg, "-y",
        "-i", str(rush),
        "-vn",                # no video
        "-ac", "1",           # mono
        "-ar", "16000",       # 16 kHz
        "-c:a", "pcm_s16le",  # PCM 16-bit little endian (whisper-friendly)
        str(out_wav),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg ERROR: {result.stderr[:500]}", file=sys.stderr)
        sys.exit(1)

    if not out_wav.exists() or out_wav.stat().st_size < 1000:
        print(f"ERROR: output WAV empty or missing: {out_wav}", file=sys.stderr)
        sys.exit(1)

    print(f"Audio extracted: {out_wav} ({out_wav.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
