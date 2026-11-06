#!/usr/bin/env python3
"""Example of a score in code: a soft pad under a voice-over, no drums.

Template to copy for a project (`music/<project>.py`): change the chord grid, the tempo, the
instruments. Everything is synthesized (scripts/synth.py: FM electric piano, pad, bass, vinyl
crackle, reverb): no samples, no rights to clear, same score = same file.

    python3 music/example_pad.py <duration_s> <output.wav>
    python3 scripts/mix.py --music output.wav --voice voice.wav --lufs -16 --out mix.wav

Slow D Dorian grid, one chord every 2 bars at 70 BPM: Dm9 | Bbmaj7 | Fmaj9 | C6/9.
These notes do not clash with the sound-effect palette (C major pentatonic, make-sfx.py).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from synth import Track, note_hz as N, vinyl  # noqa: E402

BPM = 70
BEAT = 60 / BPM
CHORDS = [
    ("D2", ["F3", "A3", "C4", "E4"]),
    ("Bb1", ["D3", "F3", "A3", "C4"]),
    ("F2", ["A3", "C4", "E4", "G4"]),
    ("C2", ["E3", "A3", "D4", "G4"]),
]
MOTIF = ["A4", "C5", "E5", "D5"]  # one note per chord, on beat 3, every other chord


def main(total, out):
    tr = Track(total)
    span = 8 * BEAT  # two bars per chord
    t, i = 0.0, 0
    while t < total:
        bass, voicing = CHORDS[i % len(CHORDS)]
        tr.add(tr.pad([N(n) for n in voicing], span + 1.5, vel=0.30, attack=1.6, release=2.0, cutoff=1500), t, bus="pad", gain=0.9)
        tr.add(tr.bass(N(bass), span * 0.9, vel=0.35), t, bus="bass", gain=0.5)
        for k, n in enumerate(voicing[1:]):  # soft chord on beat 1
            tr.add(tr.rhodes(N(n), BEAT * 3, vel=0.28), t + k * 0.02, bus="keys", pan=-0.15 + 0.1 * k, gain=0.55)
        if i % 2 == 0:  # motif note on beat 3
            tr.add(tr.rhodes(N(MOTIF[i % len(MOTIF)]), BEAT * 2.5, vel=0.32), t + 2 * BEAT, bus="keys", pan=0.2, gain=0.5)
        t += span
        i += 1
    tr.add(vinyl(total, crackle=0.25, hiss=0.002), 0, bus="vinyl", gain=0.35)
    tr.render(out, sends={"pad": 0.35, "keys": 0.4}, fade_out=(max(0.0, total - 3.0), total - 0.2))
    print(f"{out}: {total:.1f} s")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(float(sys.argv[1]), sys.argv[2])
