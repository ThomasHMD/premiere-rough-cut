#!/usr/bin/env python3
"""Mixes music + sound effects + optional voice-over into a single WAV, at the target loudness.

- the music dips automatically under the voice (soft side-chain, -8 dB by default);
- integrated loudness brought to --lufs (EBU R128 measurement by ffmpeg), TRUE peak limited to -1.5 dBTP (oversampled
  limiter, only if it is exceeded; above -1 dBTP after the limiter, the mix is refused, exit code 1);
- --sfx-voix-ref: the sound effects are files of the default sound palette, written at their level under a
  reference voice (make-sfx.py, VOIX_REF); they are re-fitted to the real voice (9th decile of the K level, 100 ms),
  --sfx-gain-db becomes a nuance around that fit (0 by default in this mode).

    python3 mix.py --music m.wav --sfx s.wav [--voice v.wav --voice-at 1.2] --lufs -18 --out mix.wav

Without --music (training videos: no music under the voice), the length is that of the voice
(or --duree) and the voice keeps its relative level; only the final loudness is adjusted.
"""
import argparse
import importlib.util
import os
import re
import subprocess

import numpy as np
import soundfile as sf

SR = 48000
PLAFOND_TP = -1.5   # maximum true peak of the mix (dBTP)


def load(path, n=None):
    x, sr = sf.read(path, always_2d=True)
    if sr != SR:
        raise SystemExit(f"{path}: {sr} Hz, expected {SR} (convert with ffmpeg -ar 48000)")
    if x.shape[1] == 1:
        x = np.repeat(x, 2, 1)
    if n is not None:
        x = np.pad(x, ((0, max(0, n - len(x))), (0, 0)))[:n]
    return x


def envelope(x, attack=0.03, release=0.35):
    e = np.abs(x).max(1)
    ka, kr = np.exp(-1 / (attack * SR)), np.exp(-1 / (release * SR))
    out = np.empty_like(e)
    acc = 0.0
    for i, v in enumerate(e):
        k = ka if v > acc else kr
        acc = k * acc + (1 - k) * v
        out[i] = acc
    return out


def lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1])


def mesure(x):
    """(integrated loudness in LUFS, true peak in dBTP) of a 48 kHz stereo signal, measured by ffmpeg (EBU R128,
    oversampled peak), the signal going through a pipe."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                        "-af", "ebur128=peak=true", "-f", "null", "-"], input=x.astype(np.float32).tobytes(),
                       capture_output=True).stderr.decode()
    tp = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", r)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1]), (float(tp.group(1)) if tp and tp.group(1) != "-inf" else -99.0)


def decalage(avant, apres, n=SR):
    """Delay of `apres` relative to `avant` in samples (0 if aligned), measured by correlation over the loudest second, within ±10 ms."""
    m = min(len(avant), len(apres))
    if m < 2 * n:
        return 0
    i = int(np.argmax((avant[:m // 4800 * 4800] ** 2).reshape(-1, 4800).sum(axis=1))) * 4800
    i = min(max(i, 480), m - n - 480)
    a, b = avant[i:i + n], apres[i - 480:i + n + 480]
    c = np.correlate(b, a, "valid")
    return int(np.argmax(c)) - 480


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--music", help="optional: without music, voice + sound effects only")
    ap.add_argument("--duree", type=float, help="without --music: track length in seconds (default: end of the voice)")
    ap.add_argument("--sfx")
    ap.add_argument("--voice")
    ap.add_argument("--voice-at", type=float, default=0.0)
    ap.add_argument("--voice-gain-db", type=float, default=0.0)
    ap.add_argument("--sfx-gain-db", type=float, help="default: -9; 0 with --sfx-voix-ref")
    ap.add_argument("--sfx-voix-ref", type=float, help="reference voice level of the sound effects (-22: default palette)")
    ap.add_argument("--duck-db", type=float, default=8.0)
    ap.add_argument("--lufs", type=float, default=-18.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.music:
        music = load(a.music)
    else:
        if not a.voice:
            raise SystemExit("without --music, --voice is required")
        nv = int(a.voice_at * SR) + len(load(a.voice))
        music = np.zeros((int(a.duree * SR) if a.duree else nv, 2))
    n = len(music)
    mix = music.copy()
    if a.voice:
        v = load(a.voice)
        i = int(a.voice_at * SR)
        voice = np.zeros((n, 2))
        j = min(n, i + len(v))
        voice[i:j] = v[: j - i] * 10 ** (a.voice_gain_db / 20)
        if a.music:
            env = envelope(voice)
            env = env / (env.max() or 1)
            duck = 10 ** (-a.duck_db * np.clip(env * 4, 0, 1) / 20)
            # the voice must dominate: bring it ~ 9 dB above the music (RMS over its active zones)
            act = env > 0.05
            rv = np.sqrt((voice[act] ** 2).mean()) if act.any() else 1
            rm = np.sqrt((music[act] ** 2).mean()) if act.any() else 1
            voice *= (rm * 10 ** (9 / 20)) / (rv or 1)
            mix = music * duck[:, None] + voice
        else:
            # without music (training videos) the music is silence: no envelope or ducking to compute (the envelope was
            # a Python loop over every sample, 6 s for 16 min of voice); the result is the voice itself, byte for byte
            mix = music + voice
    if a.sfx:
        g = -9.0 if a.sfx_gain_db is None else a.sfx_gain_db
        if a.sfx_voix_ref is not None:
            if not a.voice:
                raise SystemExit("--sfx-voix-ref requires --voice")
            spec = importlib.util.spec_from_file_location("lutherie", os.path.join(os.path.dirname(__file__), "make-sfx.py"))
            lut = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(lut)
            lv = lut.niveaux(voice.mean(1))
            lv = lv[lv > lv.max() - 30]
            p90 = float(np.percentile(lv, 90))
            g = (a.sfx_gain_db or 0.0) + p90 - a.sfx_voix_ref
            print(f"voice: 9th decile {p90:.1f} (sound-effect reference {a.sfx_voix_ref:.0f}): sound effects {g:+.1f} dB")
        mix = mix + load(a.sfx, n) * 10 ** (g / 20)

    # the mix goes to ffmpeg through a pipe, with no temporary file (nothing appears then vanishes in a synced folder)
    integre, _ = mesure(mix)
    gain_db = a.lufs - integre
    _, tp = mesure(mix * 10 ** (gain_db / 20))
    limite = tp > PLAFOND_TP
    if not limite:
        sf.write(a.out, mix * 10 ** (gain_db / 20), SR, subtype="PCM_24")
    else:
        # TRUE-peak limiter: real sound effects (stamp, shutter) have much steeper attacks than synthesized
        # sounds; capping the samples is not enough, the peak re-forms between two samples on playback
        # (-0.1 dBTP measured on a kit user's setup). Oversampled 4x, attack 2 ms, release 60 ms,
        # 0.2 dB of margin for the return to 48 kHz. Applied only when the peak is exceeded: otherwise the mix comes out untouched.
        # The limiter removes loudness: raise the gain and redo while the gap exceeds 0.3 LU (4 passes at most).
        # `latency=true`: without it, alimiter delays the whole sound by its attack (2 ms, 96 samples);
        # the offset is checked afterwards, a mix shifted against the picture is refused.
        lim = 10 ** ((PLAFOND_TP - 0.2) / 20)
        for _ in range(4):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                            "-af", f"aresample=192000,alimiter=limit={lim:.4f}:level=false:attack=2:release=60:latency=true,aresample={SR}",
                            "-c:a", "pcm_s24le", a.out], input=(mix * 10 ** (gain_db / 20)).astype(np.float32).tobytes(), check=True)
            ecart = a.lufs - lufs(a.out)
            if abs(ecart) <= 0.3:
                break
            gain_db += ecart
        sortie, _ = sf.read(a.out)
        d = decalage(mix.mean(axis=1) if mix.ndim > 1 else mix, sortie.mean(axis=1) if sortie.ndim > 1 else sortie)
        if d or len(sortie) != len(mix):
            raise SystemExit(f"!! limiter: sound shifted by {d} samples or length changed ({len(mix)} -> {len(sortie)}): mix refused")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", a.out, "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    tp_fin = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", r)
    tp_fin = float(tp_fin.group(1)) if tp_fin else 0.0
    print(f"{a.out}  {float(re.findall(r'I:\s+(-?[\d.]+) LUFS', r)[-1]):.1f} LUFS  true peak {tp_fin:.1f} dBTP"
          + (f" (limiter: {tp:.1f} before)" if limite else ""))
    if tp_fin > PLAFOND_TP + 0.5:
        raise SystemExit(f"!! true peak {tp_fin:.1f} dBTP above {PLAFOND_TP + 0.5:.1f}: mix refused")


if __name__ == "__main__":
    main()
