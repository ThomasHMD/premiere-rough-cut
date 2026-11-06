#!/usr/bin/env python3
"""Synthesized photo sound effects (no samples): shutter, ring detents, AF beep, whoosh.

    python3 sfx.py --out /tmp/sfx   # renders each sound effect as a WAV for listening
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

from synth import SR, _filt, _t

_rng = np.random.default_rng(99)


def _click(dur=0.012, center=3500, width=2500, decay=0.0025, gain=1.0):
    t = _t(dur)
    n = _rng.standard_normal(len(t))
    lo, hi = max(100, center - width / 2), min(SR / 2 - 100, center + width / 2)
    return _filt(n, "band", [lo, hi]) * np.exp(-t / decay) * gain


def shutter_clack(vel=1.0):
    """Focal-plane shutter + mirror: opening click, low thump, closing click 60 ms later."""
    out = np.zeros(int(0.25 * SR))
    a = _click(0.02, 3000, 3000, 0.003, 1.0)
    b = _click(0.02, 4200, 3500, 0.0025, 0.8)
    t = _t(0.12)
    thump = np.sin(2 * np.pi * (90 + 60 * np.exp(-t / 0.01)) * t) * np.exp(-t / 0.03) * 0.6
    body = _filt(_rng.standard_normal(len(t)), "band", [500, 1800]) * np.exp(-t / 0.018) * 0.35
    out[: len(a)] += a
    out[: len(t)] += thump + body
    i = int(0.058 * SR)
    out[i : i + len(b)] += b
    return np.tanh(out * 1.3) * vel


def ratchet(n=9, dur=1.0, vel=0.5, slow_down=1.8):
    """Aperture ring detents: regular clicks that slow down (a spring settling)."""
    out = np.zeros(int((dur + 0.05) * SR))
    u = np.linspace(0, 1, n) ** slow_down
    for k, x in enumerate(u):
        c = _click(0.01, 5200 + 400 * ((k % 2) - 0.5), 3000, 0.0012, vel * (1 - 0.4 * x))
        i = int(x * dur * SR)
        out[i : i + len(c)] += c
    return out


def af_tick(vel=0.25):
    """Discreet AF confirmation (not the shrill beep of camera bodies): a very short high double tick."""
    t = _t(0.05)
    tone = np.sin(2 * np.pi * 3100 * t) * np.exp(-t / 0.006)
    out = np.zeros(int(0.1 * SR))
    out[: len(t)] += tone
    j = int(0.045 * SR)
    out[j : j + len(t)] += tone * 0.7
    return out * vel


def whoosh(dur=0.6, vel=0.35, f0=400, f1=3000):
    """Filtered whoosh that sweeps (transitions)."""
    n = int(dur * SR)
    noise = _rng.standard_normal(n)
    out = np.zeros(n)
    hop = 512
    for i in range(0, n, hop):
        x = i / n
        fc = f0 * (f1 / f0) ** x
        seg = noise[max(0, i - 2048) : i + hop]
        y = _filt(seg, "band", [fc * 0.7, min(SR / 2 - 100, fc * 1.4)])[-hop:]
        out[i : i + len(y)] = y[: n - i]
    env = np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5
    return out * env * vel


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = Path(a.out)
    d.mkdir(parents=True, exist_ok=True)
    for name, sig in {
        "shutter": shutter_clack(),
        "ratchet": ratchet(),
        "af_tick": af_tick(),
        "whoosh": whoosh(),
    }.items():
        sf.write(d / f"{name}.wav", sig / (np.abs(sig).max() or 1) * 0.8, SR, subtype="PCM_24")
        print(d / f"{name}.wav")
