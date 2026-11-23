#!/usr/bin/env python3
"""Sentence-by-sentence transcription, to rough-cut without a Premiere transcript.

whisper deduplicates repeated takes when it hears them in the same window (see
SKILL.md, v2 pipeline). Here the audio is cut at every pause (0.35 s or more of non-speech),
and each chunk is transcribed ALONE, without context (`-mc 0`): a take and its retake
land in two different chunks and are therefore both transcribed.

Output: the same format as words_premiere.json (list of {"text","start","end","eos","conf"},
file time), plus "chunk" (chunk number). The v2 scripts (silence_cuts,
apply_takes, qc_repeat_scan, montage_qc) read it as is. --chunks also writes the list
of chunks [start, end, text]: that is the one aligned on the script.

    python3 transcribe_chunks.py <audio_16k_mono.wav> <words.json> [--chunks chunks.json]
            [--model large-v3-turbo] [--port 8178]

The whisper server (whisper-server, whisper.cpp) is started once for the whole file,
then stopped; if it is already running on the port, it is reused and left as is.
Measured on an Apple Silicon Mac: 5 to 7 times real time without DTW.
"""
import argparse
import io
import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import wave
from pathlib import Path

import numpy as np

HOP = 0.01          # energy frame (s)
PAUSE = 0.35        # non-speech that separates two chunks (s)
ILOT = 0.10         # shorter speech island discarded (click)
MAX_CHUNK = 25.0    # beyond this, cut at the quietest valley
PAD = 0.20          # air around each chunk sent to whisper
MODELES = Path.home() / "Models" / "whisper"


def lire_wav(p):
    w = wave.open(str(p))
    if w.getnchannels() != 1 or w.getsampwidth() != 2:
        sys.exit("expected audio: mono 16-bit (extract_audio.py)")
    sr = w.getframerate()
    sig = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return sig, sr


def masque_parole(sig, sr):
    hop = int(sr * HOP)
    n = len(sig) // hop
    x = sig[: n * hop].astype(np.float32).reshape(n, hop)
    rms = np.sqrt((x ** 2).mean(axis=1))
    rms = np.convolve(rms, np.ones(3) / 3, mode="same")
    seuil = float(np.percentile(rms, 95)) * 0.10
    m = rms > seuil
    # short gaps filled, short islands discarded
    def runs(mask, val):
        out, i = [], 0
        while i < len(mask):
            if mask[i] == val:
                j = i
                while j < len(mask) and mask[j] == val:
                    j += 1
                out.append((i, j))
                i = j
            else:
                i += 1
        return out
    for a, b in runs(m, False):
        if a > 0 and b < len(m) and (b - a) * HOP < PAUSE:
            m[a:b] = True
    for a, b in runs(m, True):
        if (b - a) * HOP < ILOT:
            m[a:b] = False
    return m, rms, runs(m, True)


def morceaux(regions, rms):
    """Speech regions (frame indices) -> chunks (s), cut under MAX_CHUNK."""
    out = []
    for a, b in regions:
        pile = [(a, b)]
        while pile:
            x, y = pile.pop(0)
            if (y - x) * HOP <= MAX_CHUNK:
                out.append((x * HOP, y * HOP))
                continue
            lo, hi = x + int(5 / HOP), y - int(5 / HOP)
            c = lo + int(np.argmin(rms[lo:hi]))
            pile[:0] = [(x, c), (c, y)]
    return out


def port_ouvert(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def requete(port, wav_bytes):
    b = uuid.uuid4().hex
    corps = io.BytesIO()
    for k, v in (("response_format", "verbose_json"), ("temperature", "0")):
        corps.write(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    corps.write(f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"m.wav\"\r\n"
                "Content-Type: audio/wav\r\n\r\n".encode())
    corps.write(wav_bytes)
    corps.write(f"\r\n--{b}--\r\n".encode())
    r = urllib.request.Request(f"http://127.0.0.1:{port}/inference", data=corps.getvalue(),
                               headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(r, timeout=120) as rep:
        return json.loads(rep.read())


def wav_morceau(sig, sr, t0, t1):
    a, b = max(0, int(t0 * sr)), min(len(sig), int(t1 * sr))
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes(sig[a:b].tobytes())
    w.close()
    return buf.getvalue(), a / sr


def mots_de(rep, t0, idx):
    """Timestamped words of the response; word pieces (no leading space) are glued back."""
    mots = []
    for seg in rep.get("segments", []):
        for w in seg.get("words", []):
            txt = w.get("word", "")
            if not txt.strip():
                continue
            if mots and not txt.startswith(" "):
                mots[-1]["text"] += txt.strip()
                mots[-1]["end"] = round(t0 + w["end"], 3)
                mots[-1]["conf"] = min(mots[-1]["conf"], float(w.get("probability", 1)))
                continue
            debut = t0 + (w["t_dtw"] / 100 if w.get("t_dtw", -1) >= 0 else w["start"])
            mots.append({"text": txt.strip(), "start": round(debut, 3),
                         "end": round(t0 + w["end"], 3), "conf": float(w.get("probability", 1)),
                         "chunk": idx, "dtw": w.get("t_dtw", -1) >= 0})
    mots = [m for m in mots if any(c.isalnum() for c in m["text"])]
    # DTW times: one start per word, increasing; the end = the start of the next word
    if mots and all(m.pop("dtw") for m in mots):
        for k in range(1, len(mots)):
            mots[k]["start"] = max(mots[k]["start"], mots[k - 1]["start"] + 0.02)
        for k in range(len(mots) - 1):
            mots[k]["end"] = round(mots[k + 1]["start"], 3)
    else:
        for m in mots:
            m.pop("dtw", None)
    for m in mots:
        m["eos"] = bool(re.search(r"[.!?…]$", m["text"]))
    return mots


def caler_bords(mm, d, f, tol=0.6):
    """whisper word times are approximate (no DTW); the chunk edges,
    on the other hand, are measured on energy: the first word starts at the start of speech, the
    last ends at its end (if the gap stays under tol)."""
    if mm:
        if abs(mm[0]["start"] - d) <= tol:
            mm[0]["start"] = round(d, 3)
        if abs(mm[-1]["end"] - f) <= tol:
            mm[-1]["end"] = round(f, 3)
        for m in mm:
            m["end"] = max(m["end"], m["start"] + 0.02)
    return mm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("words_out")
    ap.add_argument("--chunks")
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--port", type=int, default=8178)
    a = ap.parse_args()

    sig, sr = lire_wav(a.audio)
    dur = len(sig) / sr
    _, rms, regions = masque_parole(sig, sr)
    ch = morceaux(regions, rms)

    serveur = None
    if not port_ouvert(a.port):
        modele = MODELES / f"ggml-{a.model}.bin"
        # -dtw: true word times (without it, whisper.cpp packs the last words of a
        # chunk within a few hundredths of a second); it requires -nfa (no flash attention).
        serveur = subprocess.Popen(["nice", "whisper-server", "-m", str(modele), "-l", "fr",
                                    "-mc", "0", "--port", str(a.port),
                                    "-dtw", a.model.replace("-", "."), "-nfa"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(120):
            if port_ouvert(a.port):
                break
            time.sleep(0.5)
        else:
            serveur.terminate()
            sys.exit("whisper-server does not respond")
    t = time.time()
    mots, liste = [], []
    try:
        for i, (d, f) in enumerate(ch):
            g = (ch[i - 1][1] + d) / 2 if i else 0.0
            h = (f + ch[i + 1][0]) / 2 if i + 1 < len(ch) else dur
            t0, t1 = max(g, d - PAD), min(h, f + PAD)
            data, t0 = wav_morceau(sig, sr, t0, t1)
            rep = requete(a.port, data)
            mm = caler_bords(mots_de(rep, t0, i), d, f)
            mots += mm
            liste.append([round(d, 3), round(f, 3), " ".join(m["text"] for m in mm)])
            if i % 25 == 0:
                print(f"  {i + 1}/{len(ch)} chunks, {f:.0f}/{dur:.0f} s", file=sys.stderr, flush=True)
    finally:
        if serveur:
            serveur.terminate()
            serveur.wait(10)
    mots.sort(key=lambda m: m["start"])
    Path(a.words_out).write_text(json.dumps(mots, ensure_ascii=False))
    if a.chunks:
        Path(a.chunks).write_text(json.dumps(liste, ensure_ascii=False, indent=0))
    el = time.time() - t
    print(f"{len(ch)} chunks, {len(mots)} words, {dur:.0f} s of audio in {el:.0f} s "
          f"({dur / max(el, 0.1):.0f}x real time)")


if __name__ == "__main__":
    main()
