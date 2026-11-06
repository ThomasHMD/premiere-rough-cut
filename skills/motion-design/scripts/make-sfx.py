#!/usr/bin/env python3
"""Synth recipes for the default sound palette (reference/sound-palette.md).

Everything is synthesized (no samples, no rights to clear), deterministic, and goes through the
same chain: three materials (keyboard, camera, paper), one key (C major, pentatonic scale),
one room (the same short reverb on every sound).

Every file comes out ALREADY AT THE RIGHT LEVEL relative to the reference voice (measured on
finished videos): dropped by hand into Premiere at 0 dB, it sits where it belongs.

    python3 scripts/make-sfx.py                    # writes public/sfx/*.wav + palette.json
    python3 scripts/make-sfx.py --voix rush.mov    # measures the voice level of a file
    python3 scripts/make-sfx.py --planche out.mp4  # listening sheet: each sound, its name on screen

The vocabulary (which sound for which gesture) is in scripts/son.py.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, lfilter, sosfilt

SR = 48000
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "sfx"

# Reference voice level: 9th decile of the K level (100 ms windows) on the voice of finished
# videos (see --voix). Sounds are written at VOIX_REF + ROLES[role].
VOIX_REF = -22.0
ROLES = {"accent": -4.0, "info": -9.0, "texture": -14.0}

# Palette scale: C major pentatonic. None of these notes clash with another
# (change it here for another color: the whole palette follows).
GAMME = ["C4", "D4", "E4", "G4", "A4", "C5", "D5", "E5", "G5", "A5", "C6", "D6", "E6"]
_DEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def hz(nom):
    return 440.0 * 2 ** ((12 * (int(nom[-1]) + 1) + _DEMI[nom[0]] - 69) / 12)


def t(d):
    return np.arange(int(d * SR)) / SR


def filt(x, kind, f, order=2):
    return sosfilt(butter(order, f, btype=kind, fs=SR, output="sos"), x)


def bruit(n, graine):
    return np.random.default_rng(graine).standard_normal(n)


def place(out, x, at, g=1.0):
    i = int(at * SR)
    j = min(len(out), i + len(x))
    if j > i:
        out[i:j] += x[: j - i] * g
    return out


# ------------------------------------------------------------------ syncing to the animation

# Standard animation curve (Remotion's Easing.bezier, Material 3): the same as the scenes use,
# so sound and picture never drift apart. Change it together with them.
EASING = (0.2, 0.0, 0.0, 1.0)


def courbe(d, c=None):
    """Position (0 to 1) and speed (max = 1) of a movement lasting `d` seconds, animated with
    Easing.bezier(c) (default: the standard scene curve, the one used by the camera and the
    arrows). A sound that follows a movement takes its envelope, and its clicks fall at equal
    steps of TRAVEL. Standard curve: peak speed at 11.8% of the duration (106 ms out of
    0.9 s), halfway through the travel at 20%."""
    c = c or EASING
    u = np.linspace(0, 1, 20001)
    b = lambda u, a, e: 3 * (1 - u) ** 2 * u * a + 3 * (1 - u) * u ** 2 * e + u ** 3
    x, y = b(u, c[0], c[2]), b(u, c[1], c[3])
    pos = np.interp(t(d) / d, x, y)
    vit = np.gradient(pos)
    return pos, vit / vit.max()


def rose(n, graine):
    """Pink noise (-3 dB per octave): less hissy than white."""
    f = np.fft.rfft(bruit(n, graine))
    k = np.arange(len(f), dtype=float)
    k[0] = 1.0
    x = np.fft.irfft(f / np.sqrt(k), n)
    return x / x.std()


# ------------------------------------------------------------------ the room

def _ir(seconds=0.5, predelay=0.008, damp=3500, graine=7):
    n = int(seconds * SR)
    x = np.arange(n) / SR
    ir = bruit(n, graine) * np.exp(-6.9 * x / seconds)
    ir = filt(ir, "low", damp, 1)
    ir = np.concatenate([np.zeros(int(predelay * SR)), ir])
    return ir / np.sqrt((ir ** 2).sum())


_IR = _ir()


def piece(x, wet=0.12, lp=9000, hp=60):
    """The common chain: every sound plays in the same small, muffled room."""
    x = np.concatenate([x, np.zeros(int(0.45 * SR))])
    y = x + wet * fftconvolve(x, _IR)[: len(x)]
    y = filt(filt(y, "low", lp, 2), "high", hp, 2)
    fade = int(0.02 * SR)
    y[-fade:] *= np.linspace(1, 0, fade)
    return y


# ------------------------------------------------------------------ the keyboard

def rhodes(f, dur, vel=0.45, release=0.45):
    """Muffled electric piano: the same timbre as the outro (motion-design/scripts/synth.py)."""
    x = t(dur + release)
    tau = np.clip(2.2 * (220 / f) ** 0.5, 0.6, 3.0)
    # modulation index: a brief tine attack, then a round sound (the fundamental dominates
    # after 60 ms; the outro keeps a longer index because its notes last)
    index = (0.6 + 1.6 * vel) * np.exp(-x / 0.12) + 0.3
    body = np.sin(2 * np.pi * f * x + index * np.sin(2 * np.pi * f * x))
    tine = 0.2 * vel * np.sin(2 * np.pi * min(f * 14.0, 9000) * x) * np.exp(-x / 0.03)
    bark = 0.06 * vel * np.sin(2 * np.pi * 2 * f * x) * np.exp(-x / 0.2)
    env = np.ones(len(x))
    na = int(0.003 * SR)
    env[:na] = np.linspace(0, 1, na)
    nh = int(dur * SR)
    env[nh:] *= np.linspace(1, 0, len(x) - nh) ** 2
    return (body + tine + bark) * np.exp(-x / tau) * vel * env


def feutre(graine=3):
    """The little "tock" of the hammer on the tine: it is what makes the pop."""
    x = t(0.02)
    return filt(bruit(len(x), graine), "low", 1800, 2) * np.exp(-x / 0.003) * 0.5


def note(nom, vel=0.42, dur=0.10, release=0.45):
    y = rhodes(hz(nom), dur, vel, release)
    return place(y, feutre(), 0, vel * 0.5)


def gratte(noms, ecart=0.025, vel=0.42, dur=0.12, release=0.6):
    out = np.zeros(int((ecart * len(noms) + dur + release + 0.05) * SR))
    for k, n in enumerate(noms):
        place(out, note(n, vel * (1 - 0.06 * k), dur, release), k * ecart)
    return out


def accord():       # approval: a C major chord settling
    return gratte(["C5", "E5", "G5"], 0.022)


def question():     # stacked fifths, no third: it hangs in the air
    return gratte(["D4", "A4", "E5"], 0.04, vel=0.4, dur=0.2, release=1.0)


def notif():        # message, mail: G then C, a rising fourth
    out = np.zeros(int(0.95 * SR))
    place(out, note("G5", 0.55, 0.12, 0.4), 0)
    place(out, note("C6", 0.5, 0.14, 0.6), 0.11)
    return out


def sourd():        # the problem: a low, muffled note that drops a semitone
    x = t(0.3)
    f = hz("E3") * 2 ** (-np.clip(x / 0.12, 0, 1) / 12)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = (np.sin(ph + 1.2 * np.sin(ph)) + 0.3 * np.sin(2 * ph)) * np.exp(-x / 0.09)
    return place(filt(y, "low", 900, 2), feutre(5), 0, 0.6)


def basse():        # the C pedal under chapter cards
    return filt(rhodes(hz("C3"), 0.3, 0.45, 0.7), "low", 1400, 2)


def signature():    # the sound logo: a shutter release, then a C major 9 opening up
    out = np.zeros(int(2.4 * SR))
    place(out, obturateur(), 0, 0.5)
    place(out, rhodes(hz("C3"), 0.6, 0.5, 1.2), 0.07, 0.7)
    for k, n in enumerate(["E4", "G4", "B4", "D5"]):
        place(out, note(n, 0.45 - 0.03 * k, 0.5, 1.3), 0.07 + 0.035 * k)
    return out


# ------------------------------------------------------------------ the camera body

def clic(d=0.012, centre=3500, largeur=2500, decay=0.0025, gain=1.0, graine=1):
    x = t(d)
    lo, hi = max(100, centre - largeur / 2), min(SR / 2 - 100, centre + largeur / 2)
    return filt(bruit(len(x), graine), "band", [lo, hi]) * np.exp(-x / decay) * gain


def obturateur():
    """Focal-plane shutter + mirror: opening click, low body, closing click 58 ms later."""
    out = np.zeros(int(0.25 * SR))
    x = t(0.12)
    place(out, clic(0.02, 3000, 3000, 0.003, 1.0, 11), 0)
    place(out, np.sin(2 * np.pi * np.cumsum(90 + 60 * np.exp(-x / 0.01)) / SR) * np.exp(-x / 0.03) * 0.6, 0)
    place(out, filt(bruit(len(x), 12), "band", [500, 1800]) * np.exp(-x / 0.018) * 0.35, 0)
    place(out, clic(0.02, 4200, 3500, 0.0025, 0.8, 13), 0.058)
    return np.tanh(out * 1.3)


def af():
    """Focus locked: a double tick on a high G (in the scale)."""
    out = np.zeros(int(0.12 * SR))
    x = t(0.05)
    tic = np.sin(2 * np.pi * hz("G7") * x) * np.exp(-x / 0.006)
    place(out, tic, 0)
    place(out, tic, 0.045, 0.7)
    return out


def crans(n=14, d=0.9, graine=20):
    """Aperture ring: detents that slow down as they arrive (counters, timelines)."""
    out = np.zeros(int((d + 0.06) * SR))
    for k, u in enumerate(np.linspace(0, 1, n) ** 1.7):
        place(out, clic(0.01, 5200 + 400 * ((k % 2) - 0.5), 3000, 0.0012, 1 - 0.35 * u, graine + k), u * d)
    return out


def armement():
    """Cocking lever: the detents speed up, then the stop. Just before a shutter release."""
    out = np.zeros(int(0.5 * SR))
    for k, u in enumerate(np.linspace(0, 1, 9) ** 0.6):
        place(out, clic(0.012, 2600 + 120 * k, 2200, 0.002, 0.5 + 0.4 * u, 40 + k), u * 0.33)
    x = t(0.09)
    place(out, np.sin(2 * np.pi * np.cumsum(130 + 80 * np.exp(-x / 0.008)) / SR) * np.exp(-x / 0.02) * 0.9, 0.36)
    place(out, clic(0.02, 2200, 2400, 0.004, 0.9, 60), 0.36)
    return out


def souffle_zoom(sens=1, d=0.9, graine=300, crans=12):
    """The camera zooming: a light puff of air (a soft whoosh works better than a bare click)
    plus the ring detents. Everything follows the REAL picture curve: amplitude at speed^0.8,
    brightness at speed^1.5 (an object cutting through the air hisses louder and higher when
    it goes fast), detents at equal steps of travel, so tight at the start and spread out at
    the end, like the camera. Moving in brightens, moving out darkens; the file is never
    reversed (the peak stays at the start). No resonant filter: a crossfade between a dark
    and a bright version of the same pink noise. Replaces an earlier "ring" version whose
    peak landed 270 ms too late."""
    pos, v = courbe(d)
    x = rose(len(v), graine)
    sombre = filt(filt(x, "low", 900, 2), "high", 180, 2)
    clair = filt(x, "band", [1200, 5000], 1)
    br = v ** 1.5 * ((0.8 + 0.2 * pos) if sens > 0 else 0.7 * (1 - 0.4 * pos))
    out = (0.9 * sombre * (1 - br) + clair * br) * v ** 0.8
    out[:96] *= np.linspace(0, 1, 96)
    crete = np.abs(out).max()
    for k in range(1, crans + 1):
        i = min(len(v) - 1, int(np.searchsorted(pos, 0.95 * k / crans)))
        fc = 3200 + 300 * sens * k / crans
        place(out, clic(0.008, fc, 2000, 0.001, 0.5 * crete * (0.3 + 0.7 * v[i]), graine + 10 + k), i / SR)
    return out


def souris():
    out = np.zeros(int(0.14 * SR))
    x = t(0.03)
    corps = np.sin(2 * np.pi * 420 * x) * np.exp(-x / 0.006) * 0.4
    place(out, clic(0.015, 1900, 1800, 0.003, 1.0, 70) + corps[: int(0.015 * SR)], 0)
    place(out, clic(0.012, 2500, 2000, 0.0025, 0.55, 71), 0.07)
    return out


def touche(v=0):
    """A single key (site demos type at their own pace)."""
    x = t(0.03)
    corps = np.sin(2 * np.pi * (220 + 25 * v) * x) * np.exp(-x / 0.008) * 0.5
    return clic(0.03, 1600 + 250 * v, 1800, 0.005, 1.0, 90 + v) + corps


def frappe(n=23, d=0.8, graine=80):
    """Keyboard: dull keys, uneven like real typing."""
    rng = np.random.default_rng(graine)
    out = np.zeros(int((d + 0.08) * SR))
    x = t(0.03)
    for k in range(n):
        at = max(0, k * d / n + rng.uniform(-0.008, 0.008))
        corps = np.sin(2 * np.pi * rng.uniform(210, 270) * x) * np.exp(-x / 0.008) * 0.5
        touche = clic(0.03, 1700 + rng.uniform(-400, 400), 1800, 0.005, 1.0, graine + k) + corps
        place(out, touche, at, rng.uniform(0.6, 1.0))
    return out


# ------------------------------------------------------------------ paper

def tampon(v=0):
    """Ink stamp on paper: the hit lands on a low C, the paper slaps."""
    x = t(0.36)
    low = np.sin(2 * np.pi * np.cumsum(hz("C2") + 110 * np.exp(-x / 0.018)) / SR) * np.exp(-x / 0.07)
    claque = filt(bruit(len(x), 100 + v), "band", [250, 2300 + 350 * v]) * np.exp(-x / (0.016 + 0.003 * v)) * 1.5
    encre = filt(bruit(len(x), 110 + v), "band", [2500, 6000]) * np.exp(-x / 0.006) * 0.5
    table = np.sin(2 * np.pi * hz("G3") * x) * np.exp(-x / 0.03) * 0.3
    return np.tanh((low + claque + encre + table) * 1.4)


def pose(v=0):
    """A label, a card being set down: paper only. An earlier version used a sine falling from
    260 to 140 Hz under the noise (the recipe of an electronic tom, on a C sharp that clashes
    with the D of the pad): an awful "pock". Now: a dull paper body (pink noise 250-900 Hz,
    14 ms) and the slap of the sheet (1.2-6 kHz, 8 ms), no pitch, attack softened by 1.5 ms."""
    x = t(0.12)
    n = rose(len(x), 120 + v)
    corps = filt(filt(n, "low", 900, 2), "high", 250, 2) * np.exp(-x / 0.014) * 0.9
    feuille = filt(n, "band", [1200, 6000 - 500 * v], 1) * np.exp(-x / (0.008 + 0.002 * v)) * 0.8
    out = corps + feuille
    out[:72] *= np.linspace(0, 1, 72)
    return out


def glisse(sens=1, d=0.5):
    """A sheet sliding across the table (wipes, cards coming in). Not a synth whoosh: wide
    band, friction grain, peak at the moment of the cut."""
    x = t(d)
    n = bruit(len(x), 130)
    u = x / x[-1]
    out = np.zeros(len(x))
    K = 6
    for k in range(K):
        pos = (k + 0.5) / K if sens > 0 else 1 - (k + 0.5) / K
        env = np.clip(1 - np.abs(u - pos) * K * 0.6, 0, 1)
        fc = 600 * (4200 / 600) ** (k / (K - 1))
        bande = filt(n, "band", [fc * 0.55, min(fc * 2.1, SR / 2 - 100)], 1)
        out += bande / np.sqrt((bande ** 2).mean()) * env
    grain = 0.72 + 0.28 * filt(bruit(len(x), 131), "low", 70, 2) / 0.05
    sommet = np.exp(-((u - 0.40) / 0.24) ** 2)      # with the room, the peak lands on the cut (0.23 s)
    return out * np.clip(grain, 0.3, 1.6) * sommet


def swish_trait(d=0.6, pointe=10 / 30, graine=500):
    """The arrow being drawn (18 frames, standard curve): a brief swish that follows the speed
    of the stroke (peak at 71 ms), a bit of air at the peak, then a dry, soft tick on the frame
    where the arrowhead appears (frame 10, the first where the stroke passes 90%). Replaces an
    earlier pencil sound that peaked 220 ms too late."""
    pos, v = courbe(d)
    x = rose(len(v), graine)
    corps = filt(filt(x, "high", 700, 2), "low", 5500, 2)
    air = filt(x, "band", [2500, 7000], 1)
    out = (0.7 * corps + air * v ** 1.2) * v ** 0.9
    out[:96] *= np.linspace(0, 1, 96)
    place(out, clic(0.012, 4200, 2500, 0.0025, 0.45 * np.abs(out).max(), graine + 1), pointe)
    return out


def pop(nom="G5", graine=700):
    """An image appearing (supporting shot, contact-sheet view): a very light pop, after two
    rejected attempts (the "pock" of pose(), awful; then a printing puff too close to the
    arrow swish). The opposite of the pock: high (a note of the scale, never below C5), brief
    (peak at 1 ms, gone in 30 ms), a pitch that RISES 18% toward the note in 4 ms (a bubble
    bursting; the pock fell, like a tom), no low body, a touch of air to articulate it."""
    x = t(0.06)
    f = hz(nom) * (1 - 0.18 * np.exp(-x / 0.004))
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = (np.sin(ph) + 0.12 * np.sin(2 * ph)) * np.exp(-x / 0.009)
    y += filt(bruit(len(x), graine), "band", [2500, 7000], 1) * np.exp(-x / 0.0012) * 0.25
    y[:48] *= 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, 48))
    return y


def page():
    """A page turning: between two full-screen scenes in a row."""
    x = t(0.24)
    n = filt(bruit(len(x), 140), "band", [1400, 7000], 1)
    env = np.exp(-x / 0.028) + 0.6 * np.exp(-((x - 0.1) / 0.03) ** 2)
    rabat = np.sin(2 * np.pi * 210 * x) * np.exp(-((x - 0.11) / 0.02) ** 2) * 0.25
    return n * env + rabat


# ------------------------------------------------------------------ levels

_K1 = ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585])
_K2 = ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])


def niveaux(x, fen=0.1, pas=0.01):
    """K level (weighting from recommendation BS.1770) over 100 ms windows."""
    k = lfilter(*_K2, lfilter(*_K1, x))
    n, h = int(fen * SR), int(pas * SR)
    if len(k) < n:
        k = np.concatenate([k, np.zeros(n - len(k))])
    c = np.concatenate([[0.0], np.cumsum(k ** 2)])
    ms = (c[n::h] - c[:-n:h]) / n
    return 10 * np.log10(np.maximum(ms, 1e-12)) - 0.691


def force(x):
    return float(niveaux(x).max())


def niveau_voix(fichier, debut=0.0, duree=240.0):
    """9th decile of the 100 ms windows where someone is speaking (above -45)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(debut), "-t", str(duree), "-i", str(fichier),
                          "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
    lv = niveaux(np.frombuffer(raw, dtype=np.float32).astype(np.float64))
    lv = lv[lv > -45]
    return float(np.percentile(lv, 90)), float(np.percentile(lv, 50))


# ------------------------------------------------------------------ the palette

def palette():
    """file name -> (raw signal, role, material, reverb, what it is for)."""
    p = {}
    for n in GAMME:
        p[f"note-{n}.wav"] = (note(n), "info", "keyboard", 0.14, "an element appears")
    p["accord.wav"] = (accord(), "info", "keyboard", 0.16, "approval, last element, checkmark")
    p["question.wav"] = (question(), "info", "keyboard", 0.2, "a question is asked")
    p["notif.wav"] = (notif(), "info", "keyboard", 0.16, "message, mail")
    p["sourd.wav"] = (sourd(), "info", "keyboard", 0.08, "a problem, a refusal")
    p["basse.wav"] = (basse(), "info", "keyboard", 0.12, "C pedal under a chapter card")
    p["signature.wav"] = (signature(), "accent", "keyboard", 0.2, "sound logo: opening, promise, ending")
    p["obturateur.wav"] = (obturateur(), "accent", "camera", 0.08, "capture, a number landing, hard cut")
    p["af.wav"] = (af(), "info", "camera", 0.06, "the focus points lock")
    p["crans-court.wav"] = (crans(8, 0.5), "texture", "camera", 0.05, "short counter")
    p["crans.wav"] = (crans(14, 0.9), "texture", "camera", 0.05, "counter, progress bar")
    p["crans-long.wav"] = (crans(22, 1.6), "texture", "camera", 0.05, "timeline, long countdown")
    p["armement.wav"] = (armement(), "texture", "camera", 0.06, "just before a reveal")
    p["clic.wav"] = (souris(), "texture", "camera", 0.04, "mouse click in a demo")
    p["frappe.wav"] = (frappe(), "texture", "camera", 0.04, "an address being typed")
    for v in range(3):
        p[f"touche-{v + 1}.wav"] = (touche(v), "texture", "camera", 0.04, "a keyboard key in a demo")
    for v in range(3):
        p[f"tampon-{v + 1}.wav"] = (tampon(v), "accent", "paper", 0.1, "stamp, a word that slams")
    for v in range(2):
        p[f"pose-{v + 1}.wav"] = (pose(v), "info", "paper", 0.08, "label, card, bubble being set down")
    p["glisse-in.wav"] = (glisse(1), "texture", "paper", 0.08, "entry wipe, card arriving")
    p["glisse-out.wav"] = (glisse(-1), "texture", "paper", 0.08, "exit wipe")
    p["page.wav"] = (page(), "texture", "paper", 0.08, "moving on to the next scene")
    p["trait.wav"] = (swish_trait(), "texture", "paper", 0.05, "an arrow, a stroke being drawn (0.6 s)")
    p["zoom-in.wav"] = (souffle_zoom(1), "texture", "camera", 0.05, "the camera moves in on a detail (0.9 s)")
    p["zoom-out.wav"] = (souffle_zoom(-1), "texture", "camera", 0.05, "the camera pulls back to the full image (0.9 s)")
    p["zoom-in-07.wav"] = (souffle_zoom(1, 0.7), "texture", "camera", 0.05, "zoom into a supporting shot (0.7 s)")
    for n in ("C5", "D5", "E5", "G5", "A5", "C6"):
        p[f"pop-{n}.wav"] = (pop(n), "texture", "paper", 0.05, "an image appears (supporting shot: G; contact sheet: the scale climbs)")
    return p


def ecrire():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {}
    for nom, (x, role, matiere, wet, usage) in palette().items():
        hp = 35 if nom.startswith("tampon") else 60
        y = piece(x, wet, hp=hp)
        cible = VOIX_REF + ROLES[role]
        y *= 10 ** ((cible - force(y)) / 20)
        crete = float(np.abs(y).max())
        if crete > 0.89:                     # a very short sound: cap it, it stays below its target
            y *= 0.89 / crete
        sf.write(OUT / nom, y, SR, subtype="PCM_24")
        meta[nom] = {"role": role, "matiere": matiere, "usage": usage, "niveau": round(force(y), 1),
                     "crete": round(20 * np.log10(np.abs(y).max()), 1), "duree": round(len(y) / SR, 2)}
        print(f"{nom:18s} {matiere:8s} {role:8s} level {meta[nom]['niveau']:6.1f}  peak {meta[nom]['crete']:6.1f} dB  {meta[nom]['duree']:.2f} s")
    (OUT / "palette.json").write_text(json.dumps(
        {"identite": "default palette", "voixRef": VOIX_REF, "roles": ROLES, "gamme": GAMME, "sons": meta},
        ensure_ascii=False, indent=1))
    print(f"\n{len(meta)} sounds + palette.json in {OUT}")


# ------------------------------------------------------------------ listening sheet

def planche(sortie, voix=None, voix_at=60.0):
    """A listening video: each sound of the palette, its name and use on screen, then the
    typical phrases (list, cascade, chapters, burst of stamps). With `voix`, everything is
    played under an excerpt of the voice, to judge the balance."""
    from PIL import Image, ImageDraw, ImageFont

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import son

    son.TIMBRES = ""   # the sheet auditions the synth recipes (public/sfx/), not the default sounds of the shots (son.py)
    meta = json.loads((OUT / "palette.json").read_text())["sons"]
    plans = []   # (title, subtitle, [(file, at, gainDb)], duration)
    for matiere in ("keyboard", "camera", "paper"):
        for nom, m in meta.items():
            if m["matiere"] != matiere or (nom.startswith("note-") and nom not in ("note-C5.wav",)):
                continue
            plans.append((nom.replace(".wav", ""), f"{matiere} · {m['usage']}", [(nom, 0.25, 0.0)], max(1.5, m["duree"] + 0.7)))
    lst = [0.3, 0.9, 1.5, 2.1]
    plans += [
        ("a list of 4", "the elements climb the scale, the last one resolves", son.liste(lst), 3.2),
        ("a list of 6", "", son.liste([0.3 + 0.5 * k for k in range(6)]), 4.2),
        ("cascade of 10 tiles", "", son.cascade(0.3, 10), 2.2),
        ("question, then answer", "the question hangs in the air, the chapter resolves it",
         son.question(0.3) + son.chapitre(2.4, 3, 10), 5.0),
        ("chapters 1 to 10", "each card rises one step, the last lands on the C",
         [s for k in range(10) for s in son.chapitre(0.3 + 1.1 * k, k + 1, 10)], 12.2),
        ("counter, then the number lands", "", son.compteur(0.3, 0.9), 2.4),
        ("cocking, release", "", son.revele(0.8), 2.2),
        ("three words that slam", "", son.claque(0.3, 0) + son.claque(1.0, 1, fort=True) + son.claque(1.7, 2), 3.0),
        ("burst of stamps", "", [s for k in range(5) for s in son.tampon(0.3 + 0.07 * k, k, d=-4)], 1.8),
        ("wipe, scene, page, wipe", "", son.volet_in(0.2) + son.page(1.6) + son.volet_out(3.0), 4.0),
        ("an address being typed", "", son.frappe(0.3), 1.8),
        ("signature", "opening, promise, end card", son.signature(0.3), 3.2),
    ]
    total = sum(p[3] for p in plans)
    mix = np.zeros(int(total * SR))
    W, H = 1280, 720
    tmp = Path(tempfile.mkdtemp(prefix="planche-"))
    ttf = next((f for f in ("/System/Library/Fonts/Supplemental/Georgia Italic.ttf", "/System/Library/Fonts/Helvetica.ttc")
                if Path(f).exists()), None)
    f1 = ImageFont.truetype(ttf, 84) if ttf else ImageFont.load_default()
    f2 = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30) if Path("/System/Library/Fonts/Helvetica.ttc").exists() else f1
    concat, at = [], 0.0
    for i, (titre, sous, sfx, dur) in enumerate(plans):
        for fichier, a, g in sfx:
            y, _ = sf.read(OUT / fichier)
            place(mix, y, at + a, 10 ** (g / 20))
        im = Image.new("RGB", (W, H), "#F2F2F2")
        d = ImageDraw.Draw(im)
        d.text((80, 70), f"PALETTE · {i + 1} / {len(plans)}", font=f2, fill="#2F5BEA")
        d.text((80, 260), titre, font=f1, fill="#141414")
        d.text((80, 400), sous, font=f2, fill="#555555")
        im.save(tmp / f"{i:02d}.png")
        concat.append(f"file '{tmp / f'{i:02d}.png'}'\nduration {dur:.3f}")
        at += dur
    concat.append(f"file '{tmp / f'{len(plans) - 1:02d}.png'}'")
    (tmp / "liste.txt").write_text("\n".join(concat))
    gain = 0.0
    if voix:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(voix_at), "-t", str(total), "-i", str(voix), "-vn",
                              "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
        v = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
        mix[: len(v)] += v[: len(mix)]
    else:
        gain = 12.0                          # no voice: boost everything for listening
    sf.write(tmp / "son.wav", np.clip(mix * 10 ** (gain / 20), -1, 1), SR, subtype="PCM_24")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "liste.txt"),
                    "-i", str(tmp / "son.wav"), "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "22",
                    "-c:a", "aac", "-b:a", "256k", "-shortest", str(sortie)], check=True)
    print(f"sheet: {sortie} ({total:.0f} s, {len(plans)} shots{', under the voice' if voix else ', +12 dB for listening'})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--voix", help="measure the voice level of this file (audio or video)")
    ap.add_argument("--at", type=float, default=60.0)
    ap.add_argument("--planche", help="write the listening sheet (mp4)")
    a = ap.parse_args()
    if a.voix and not a.planche:
        p90, p50 = niveau_voix(a.voix, a.at)
        print(f"voice: 9th decile {p90:.1f}, median {p50:.1f} (K level, 100 ms windows)")
    elif a.planche:
        planche(a.planche, a.voix, a.at)
    else:
        ecrire()
