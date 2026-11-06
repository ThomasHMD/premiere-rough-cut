#!/usr/bin/env python3
"""Lets you "listen" to short slices of an audio: whisper transcribes each slice on its own.
Used to place a cut boundary when the word timestamps (Premiere, or whisper on the whole
clip) are not reliable to within 0.3 s.

    python3 hear.py <audio.wav> 47.5-48.28 48.28-49.65 50.6-52.6 [--lang fr]

whisper runs in the language given by --lang, else the "language" of the transcript.json
next to the audio, else it detects the language by itself. A line made of a whisper hallucination (the
whisper_hallucinations of the language file) means there is no word in the slice.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import lang

code, argv = lang.pop_argv(sys.argv[1:])
if len(argv) < 2 or argv[0].startswith("-"):
    sys.exit(__doc__)
audio, spans = argv[0], argv[1:]
language = code or lang.from_work_dir(Path(audio).parent)
tmp = Path(tempfile.mkdtemp(prefix="hear-"))
for sp in spans:
    a, b = (float(x) for x in sp.split("-"))
    wav, js = tmp / "s.wav", tmp / "s.json"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-to", str(b), "-i", audio,
                    "-af", "apad=pad_dur=1.0", str(wav)], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("transcribe.py")), str(wav), str(js)]
                   + (["--language", language] if language else []), capture_output=True)
    txt = " ".join(s["text"] for s in json.loads(js.read_text())["segments"]) if js.exists() else "(nothing)"
    print(f"{a:8.2f}-{b:8.2f}: {txt}")
    js.unlink(missing_ok=True)
wav.unlink(missing_ok=True)
tmp.rmdir()
