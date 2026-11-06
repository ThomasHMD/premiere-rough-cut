#!/usr/bin/env python3
"""Mini music synthesis engine in numpy/scipy, with no samples and no AI.

Instruments: FM electric piano (Rhodes-style), pad (filtered detuned saws), bass, kick, rim,
hi-hat, vinyl crackle. Effects: convolution reverb (synthetic impulse response), tape wow,
soft saturation. Everything is deterministic (fixed seed): same score = same file.

Typical usage (see music/*.py):
    from synth import Track, note_hz
    tr = Track(seconds=20)
    tr.add(tr.rhodes(note_hz("E4"), 1.2, vel=0.7), t=0.0, pan=-0.2, bus="keys")
    tr.render("out.wav")
"""
from __future__ import annotations

import re
import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
_rng = np.random.default_rng(1234)

NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_hz(name: str) -> float:
    """'A4' -> 440.0; accepts # and b (e.g. 'F#3', 'Bb2')."""
    m = re.fullmatch(r"([A-G])([#b]?)(-?\d)", name)
    if not m:
        raise ValueError(name)
    n = NOTE[m.group(1)] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    midi = 12 * (int(m.group(3)) + 1) + n
    return 440.0 * 2 ** ((midi - 69) / 12)


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def _filt(x, kind, f, order=2):
    sos = butter(order, f, btype=kind, fs=SR, output="sos")
    return sosfilt(sos, x, axis=0)


def _adsr(n, a=0.005, r=0.08, hold=None):
    env = np.ones(n)
    na = max(1, int(a * SR))
    env[:na] = np.linspace(0, 1, na)
    nr = max(1, int(r * SR))
    if hold is not None:
        nh = min(n, int(hold * SR))
        tail = n - nh
        if tail > 0:
            env[nh:] *= np.linspace(1, 0, tail) ** 2
    else:
        env[-nr:] *= np.linspace(1, 0, nr)
    return env


# ---------------------------------------------------------------- instruments

def rhodes(f, dur, vel=0.7, release=0.25):
    """2-operator FM electric piano + "tine" (reed partial), decay depends on pitch."""
    t = _t(dur + release)
    tau = np.clip(2.2 * (220 / f) ** 0.5, 0.6, 3.0)
    amp = np.exp(-t / tau)
    index = (1.3 + 2.2 * vel) * np.exp(-t / 0.4) + 0.45
    mod = np.sin(2 * np.pi * f * t)
    body = np.sin(2 * np.pi * f * t + index * mod)
    tine = 0.2 * vel * np.sin(2 * np.pi * f * 14.0 * t) * np.exp(-t / 0.03)
    bark = 0.06 * vel * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.2)
    y = (body + tine + bark) * amp * vel
    env = _adsr(len(t), a=0.003, hold=dur)
    return y * env


def pad(freqs, dur, vel=0.4, attack=0.9, release=1.2, cutoff=1400, voices=5, detune=0.12):
    """Pad: saws detuned (in cents) per note, low-pass filtered, slow attack. Stereo."""
    t = _t(dur + release)
    out = np.zeros((len(t), 2))
    for f in freqs:
        for v in range(voices):
            cents = (v - (voices - 1) / 2) * detune * 100 / max(1, voices - 1) * 2
            fv = f * 2 ** (cents / 1200)
            ph = _rng.random()
            saw = 2 * ((fv * t + ph) % 1.0) - 1
            pan = (v / max(1, voices - 1)) * 2 - 1
            out[:, 0] += saw * (0.5 - 0.35 * pan)
            out[:, 1] += saw * (0.5 + 0.35 * pan)
    out = _filt(out, "low", cutoff, 4)
    env = _adsr(len(t), a=attack, hold=dur)
    return out * env[:, None] * vel / (len(freqs) * voices) * 3


def bass(f, dur, vel=0.8):
    t = _t(dur + 0.08)
    y = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t) + 0.08 * np.sin(6 * np.pi * f * t)
    y *= np.exp(-t / 1.2)
    y = np.tanh(1.4 * y)
    return _filt(y * _adsr(len(t), a=0.006, hold=dur) * vel, "low", 900)


def kick(vel=0.9):
    t = _t(0.45)
    f = 46 + 90 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) * np.exp(-t / 0.16)
    click = _filt(_rng.standard_normal(len(t)), "high", 2500) * np.exp(-t / 0.003) * 0.15
    return np.tanh(1.5 * (y + click)) * vel


def rim(vel=0.5):
    t = _t(0.18)
    body = np.sin(2 * np.pi * 330 * t) * np.exp(-t / 0.02)
    noise = _filt(_rng.standard_normal(len(t)), "band", [1200, 5000]) * np.exp(-t / 0.045)
    return (0.6 * body + 0.8 * noise) * vel


def hat(vel=0.3, open_=False):
    t = _t(0.35 if open_ else 0.08)
    n = _filt(_rng.standard_normal(len(t)), "high", 7000)
    return n * np.exp(-t / (0.12 if open_ else 0.018)) * vel


def vinyl(dur, crackle=0.5, hiss=0.004):
    n = int(dur * SR)
    y = _filt(_rng.standard_normal(n), "band", [300, 6000]) * hiss
    k = _rng.random(n) < (18 * crackle / SR)
    imp = np.zeros(n)
    imp[k] = _rng.choice([-1, 1], k.sum()) * _rng.uniform(0.05, 0.35, k.sum())
    y += _filt(imp, "band", [800, 7000], 1) * 0.35
    return y


# ------------------------------------------------------------------ effects

def reverb_ir(seconds=2.2, predelay=0.012, damp=4500, seed=7):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    decay = np.exp(-6.9 * t / seconds)  # RT60
    ir = rng.standard_normal((n, 2)) * decay[:, None]
    ir = _filt(ir, "low", damp, 1)
    ir[: int(0.05 * SR)] *= np.linspace(0.3, 1, int(0.05 * SR))[:, None]
    ir = np.vstack([np.zeros((int(predelay * SR), 2)), ir])
    return ir / np.sqrt((ir**2).sum(axis=0))


def reverb(x, wet=0.25, seconds=2.2, damp=4500):
    x2 = x if x.ndim == 2 else np.stack([x, x], 1)
    ir = reverb_ir(seconds, damp=damp)
    w = np.stack([fftconvolve(x2[:, c], ir[:, c])[: len(x2)] for c in range(2)], 1)
    return x2 * (1 - wet) + w * wet


def wow(x, depth=0.0012, rate=0.45, flutter=0.00012):
    """Tape wow: a light pitch vibrato from playback at a modulated speed."""
    n = len(x)
    t = np.arange(n) / SR
    offs = depth * np.sin(2 * np.pi * rate * t) + flutter * np.sin(2 * np.pi * 6.3 * t)
    idx = np.clip((t + offs) * SR, 0, n - 1)
    if x.ndim == 1:
        return np.interp(idx, np.arange(n), x)
    return np.stack([np.interp(idx, np.arange(n), x[:, c]) for c in range(x.shape[1])], 1)


def pan2(x, pan=0.0):
    x = x if x.ndim == 1 else x.mean(1)
    a = (pan + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], 1)


# ------------------------------------------------------------------ track

class Track:
    """Named stereo buses + time placement; render() mixes, processes and writes a 24-bit WAV."""

    def __init__(self, seconds: float):
        self.n = int(round(seconds * SR))
        self.bus: dict[str, np.ndarray] = {}

    # instrument shortcuts
    rhodes = staticmethod(rhodes)
    pad = staticmethod(pad)
    bass = staticmethod(bass)
    kick = staticmethod(kick)
    rim = staticmethod(rim)
    hat = staticmethod(hat)

    def add(self, sig, t: float, bus="main", pan=0.0, gain=1.0):
        b = self.bus.setdefault(bus, np.zeros((self.n, 2)))
        s = pan2(sig, pan) if sig.ndim == 1 else sig
        i = int(round(t * SR))
        if i >= self.n:
            return
        j = min(self.n, i + len(s))
        b[i:j] += s[: j - i] * gain

    def duck(self, bus: str, trigger_bus: str, amount=0.35, release=0.18):
        """Side-chain compressor style pumping: the bus dips on every hit of the trigger bus."""
        if bus not in self.bus or trigger_bus not in self.bus:
            return
        env = np.abs(self.bus[trigger_bus]).max(1)
        k = np.exp(-1 / (release * SR))
        sm = np.empty_like(env)
        acc = 0.0
        for i, v in enumerate(env):  # simple loop, ~1 s for 20 s of sound
            acc = max(v, acc * k)
            sm[i] = acc
        sm /= sm.max() or 1
        self.bus[bus] *= (1 - amount * sm)[:, None]

    def render(self, path: str, sends: dict[str, float] | None = None, master_lp=11000,
               fade_out: tuple[float, float] | None = None, wow_depth=0.0012, air=0.0):
        sends = sends or {}
        dry = sum(self.bus.values())
        send = sum(self.bus[b] * g for b, g in sends.items() if b in self.bus)
        mix = dry + (reverb(send, wet=1.0) if isinstance(send, np.ndarray) else 0)
        if wow_depth:
            mix = wow(mix, depth=wow_depth)
        if air:  # exciter: feeds back saturated highs (brightness without harshness)
            mix = mix + air * np.tanh(3 * _filt(mix, "high", 2500, 2)) / 3
        mix = _filt(mix, "low", master_lp, 2)
        mix = _filt(mix, "high", 28, 2)
        if fade_out:
            a, b = (int(v * SR) for v in fade_out)
            b = min(b, self.n)
            mix[a:b] *= np.linspace(1, 0, b - a)[:, None] ** 1.5
            mix[b:] = 0
        peak = np.abs(mix).max() or 1
        mix = np.tanh(1.2 * mix / peak) / np.tanh(1.2) * 0.89  # soft saturation, peak ~ -1 dBFS
        sf.write(path, mix, SR, subtype="PCM_24")
        return path
