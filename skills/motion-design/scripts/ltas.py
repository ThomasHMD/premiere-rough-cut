#!/usr/bin/env python3
"""Average spectrum per octave of an audio file (dB relative to the 250-500 Hz band).
A tonal-balance check without listening: a "normal" music mix falls about 3 to 6 dB per octave
above 250 Hz; a dip or bump of more than ~6 dB against that slope points to a flaw."""
import sys
import numpy as np, soundfile as sf
from scipy.signal import welch

x, sr = sf.read(sys.argv[1])
x = x.mean(1) if x.ndim == 2 else x
f, p = welch(x, sr, nperseg=8192)
edges = [31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
ref = None
rows = []
for lo, hi in zip(edges[:-1], edges[1:]):
    m = (f >= lo) & (f < hi)
    db = 10 * np.log10(p[m].sum() + 1e-20)
    rows.append((lo, hi, db))
    if lo == 250:
        ref = db
for lo, hi, db in rows:
    print(f"{lo:>5}-{hi:<5} Hz  {db - ref:+6.1f} dB  {'#' * max(0, int((db - ref + 40) / 2))}")
