#!/usr/bin/env python3
"""Extracts the Premiere transcript straight from the .prproj file.

Why: the v2 pipeline needs the Premiere transcript (whisper dedupes repeated takes,
see parse_premiere_transcript.py). It used to be requested from the user through
"Text panel > Transcript > ... > Export > JSON". No need: Premiere already embeds
it in the project.

Where it lives: the .prproj is gzipped XML holding a block
<ExternallyProvidedTranscriptDocument><TranscriptData Encoding="base64">, whose
payload is a FlatBuffers buffer. Reverse-engineered schema:

    root        -> f0: table Document
    Document    -> f0: vector<Segment>, f5: string language, ...
    Segment     -> f0: i64 start_ticks
                   f3: vector<Word>
                   f4: string language ("fr-fr", "en-us"...)
    Word        -> f0: i64 start_ticks
                   f1: i64 duration_ticks
                   f2: string text
                   f3: f32 confidence

Ticks are Premiere ticks: 254016000000 per second.

Output: the same words_premiere.json as parse_premiere_transcript.py
(text / start / end / eos), ready for silence_cuts.py.

Usage:
    python3 extract_prproj_transcript.py <project.prproj> <words_premiere.json> [--rush <clip.mov>]

Several clips in the project = one transcript per clip.
`--rush` picks the right one from the file duration: the one whose last word STARTS the
latest without going past the end of the clip (not its end: a Premiere word duration can
swallow the silence that follows and overflow the file), with a margin for the drift.
Without `--rush`, the largest one is kept.
"""
import base64
import gzip
import json
import re
import struct
import sys
from pathlib import Path

TICKS_PER_SECOND = 254016000000


class FB:
    """Minimal FlatBuffers reader (little-endian, no generated schema)."""

    def __init__(self, buf):
        self.b = buf

    def u16(self, o):
        return struct.unpack_from("<H", self.b, o)[0]

    def i32(self, o):
        return struct.unpack_from("<i", self.b, o)[0]

    def u32(self, o):
        return struct.unpack_from("<I", self.b, o)[0]

    def i64(self, o):
        return struct.unpack_from("<q", self.b, o)[0]

    def f32(self, o):
        return struct.unpack_from("<f", self.b, o)[0]

    def fields(self, table):
        """Offsets of the table fields, indexed by field number (0 = absent)."""
        vtable = table - self.i32(table)
        vsize = self.u16(vtable)
        return [self.u16(vtable + 4 + i * 2) for i in range((vsize - 4) // 2)]

    def deref(self, pos):
        """Follows a uoffset (relative to its own position)."""
        return pos + self.u32(pos)

    def string(self, pos):
        o = self.deref(pos)
        n = self.u32(o)
        return self.b[o + 4:o + 4 + n].decode("utf-8", "replace")

    def vector(self, pos):
        """Returns the list of table positions of the vector."""
        o = self.deref(pos)
        n = self.u32(o)
        base = o + 4
        return [self.deref(base + i * 4) for i in range(n)]


def read_blob(prproj_path):
    xml = gzip.open(prproj_path, "rb").read().decode("utf-8", "replace")
    # [^>/]: a self-closing tag (empty transcript) used to swallow the next block
    blobs = re.findall(
        r'<TranscriptData Encoding="base64"[^>/]*>(.*?)</TranscriptData>', xml, re.S
    )
    if not blobs:
        print(
            "ERROR: no transcript in this .prproj.\n"
            "  Run the transcription in Premiere (Text panel > Transcribe),\n"
            "  save the project, then run again.",
            file=sys.stderr,
        )
        sys.exit(2)
    return [base64.b64decode(re.sub(r"\s", "", b)) for b in blobs]


def rush_duration(path):
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())


def main():
    args = sys.argv[1:]
    rush = None
    if "--rush" in args:
        i = args.index("--rush")
        rush = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        print("Usage: extract_prproj_transcript.py <project.prproj> <words_out.json> [--rush <clip>]",
              file=sys.stderr)
        sys.exit(1)

    decoded = [w for w in (decode(b) for b in read_blob(Path(args[0]))) if w]
    if not decoded:
        print("ERROR: transcript found but empty (unexpected FlatBuffers schema?)",
              file=sys.stderr)
        sys.exit(3)
    if rush:
        dur = rush_duration(rush)
        # margin: the transcript can drift by 0.14%; on a real video, its last words started
        # 1.6 to 2.1 s after the end of the file (realigned afterwards by calibrate_premiere_times.py)
        fits = [w for w in decoded if w[-1]["start"] <= dur + max(2.0, 0.003 * dur)]
        if not fits:
            print(f"ERROR: no transcript fits in the {dur:.0f} s of {Path(rush).name}",
                  file=sys.stderr)
            sys.exit(4)
        fits.sort(key=lambda w: w[-1]["start"])
        if len(fits) > 1 and fits[-1][-1]["start"] - fits[-2][-1]["start"] < 5.0:
            print("WARNING: two transcripts of similar durations, check the text",
                  file=sys.stderr)
        words = fits[-1]
    else:
        if len(decoded) > 1:
            print(f"WARNING: {len(decoded)} transcripts, the longest one is kept "
                  "(--rush to choose)", file=sys.stderr)
        words = max(decoded, key=len)
    Path(args[1]).write_text(json.dumps(words, ensure_ascii=False))
    print(f"{len(words)} words, from {words[0]['start']:.2f}s to {words[-1]['end']:.2f}s"
          + (f" ({len(decoded)} transcripts in the project)" if len(decoded) > 1 else ""))


def decode(blob):
    """One FlatBuffers block -> sorted list of words."""
    fb = FB(blob)

    root = fb.u32(0)  # FlatBuffers root: 12 or 16 depending on the alignment (16 seen in practice)
    document = fb.deref(root + fb.fields(root)[0])
    segments = fb.vector(document + fb.fields(document)[0])

    words = []
    for seg in segments:
        sf = fb.fields(seg)
        if len(sf) <= 3 or sf[3] == 0:
            continue
        for w in fb.vector(seg + sf[3]):
            wf = fb.fields(w)
            if len(wf) <= 2 or 0 in (wf[0], wf[1], wf[2]):
                continue
            start = fb.i64(w + wf[0]) / TICKS_PER_SECOND
            end = start + fb.i64(w + wf[1]) / TICKS_PER_SECOND
            text = fb.string(w + wf[2])
            # Items with empty text are the PAUSES marked by Premiere: their
            # duration covers the whole silence. They are dropped (the equivalent of
            # the type != "word" filter of the JSON export), otherwise every gap
            # between words is 0 and silence_cuts.py finds nothing left to cut.
            if not text.strip():
                continue
            conf = fb.f32(w + wf[3]) if len(wf) > 3 and wf[3] else 1.0
            words.append({"text": text, "start": start, "end": end,
                          "eos": bool(re.search(r"[.!?…]$", text)), "conf": conf})

    words.sort(key=lambda w: (w["start"], w["end"]))
    return words


if __name__ == "__main__":
    main()
