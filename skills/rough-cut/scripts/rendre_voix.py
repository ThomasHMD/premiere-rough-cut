#!/usr/bin/env python3
"""After the editor validates a part: one WAV per module, rendered from the delivered XML.

The sound is what the editor listened to in Premiere: the XML clips (clip on A1, retakes on A2
with their level), read from the files they point to (the processed raw voice files, already run
through the voice processing chain), laid end to end as the sequence plays them.
No extra processing: the voice comes out as it was validated.

    python3 rendre_voix.py <part.xml> <output folder> [--amorce 2.8]

Writes `<folder>/<module title>.wav` (for example "1.1 - Introduction.wav", the name the
voice batch step expects), 48 kHz, mono, 24 bits. Digital silence at the start so that the voice
starts at --amorce s (the first clip keeps 0.20 s of air before its first word: first word
around 3.0 s); 5 ms fade at both ends of the file only.
An identical file is not rewritten; writing goes through a staging folder (same disk,
outside any synced folder) and then a rename. Exit code 1 if a module clips (peak at 0 dBFS; the
chain limiter holds the clips at -0.1 dBFS, a retake raised by a few dB could exceed it).
"""
import argparse
import hashlib
import io
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.dont_write_bytecode = True
ICI = Path(__file__).parent
sys.path.insert(0, str(ICI))
from qc_assemblage import SR, lire_xml, rendre  # noqa: E402

# Optional staging folder on the same disk, outside any synced folder (env var; unset = write next to the file)
DEPOT = Path(os.environ.get("ROUGH_CUT_STAGING_DIR", "/nonexistent"))
FONDU = 0.005
CRETE_MAX = 0.0      # dBFS: the voice chain already limits at -0.1 dBFS; above 0, the sound clips


def octets(y):
    b = io.BytesIO()
    sf.write(b, y, SR, subtype="PCM_24", format="WAV")
    return b.getvalue()


def ecrire(chemin, data):
    """Writes only if the content changes; True if written."""
    if chemin.exists() and hashlib.sha1(chemin.read_bytes()).digest() == hashlib.sha1(data).digest():
        return False
    tmp_dir = DEPOT if DEPOT.is_dir() and os.stat(DEPOT).st_dev == os.stat(chemin.parent).st_dev else chemin.parent
    tmp = tmp_dir / f".~{chemin.name}"
    tmp.write_bytes(data)
    os.replace(tmp, chemin)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("xml")
    ap.add_argument("sortie")
    ap.add_argument("--amorce", type=float, default=2.8, help="seconds of silence before the first clip")
    a = ap.parse_args()
    fps, clips, modules, _ = lire_xml(a.xml)
    if not modules:
        sys.exit("no \"Module start\" marker in the XML")
    out = Path(a.sortie)
    out.mkdir(parents=True, exist_ok=True)
    fins = [f for f, _ in modules[1:]] + [max(c["end"] for c in clips) + 1]
    code = 0
    for (f0, titre), fsuiv in zip(modules, fins):
        mc = [c for c in clips if f0 <= c["start"] < fsuiv]
        f1 = max(c["end"] for c in mc)
        y = rendre(mc, fps, f0, f1)
        n = int(FONDU * SR)
        y[:n] *= np.linspace(0, 1, n, dtype=np.float32)
        y[-n:] *= np.linspace(1, 0, n, dtype=np.float32)
        y = np.concatenate([np.zeros(int(round(a.amorce * SR)), dtype=np.float32), y])
        crete = 20 * np.log10(max(float(np.abs(y).max()), 1e-9))
        sature = crete >= CRETE_MAX
        code = max(code, int(sature))
        fait = ecrire(out / f"{titre}.wav", octets(y))
        print(f"{'⚠ ' if sature else ''}{titre}.wav : {len(y) / SR / 60:.2f} min, {len(mc)} clips, peak {crete:.1f} dBFS"
              f"{'' if fait else ' (identical, not rewritten)'}")
    sys.exit(code)


if __name__ == "__main__":
    main()
