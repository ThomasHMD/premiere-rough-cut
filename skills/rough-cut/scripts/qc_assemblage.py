#!/usr/bin/env python3
"""Check of a part assembled by assemble_xml.py, on the delivered XML.

The sound of each module is rebuilt by reading the XML itself (files, in/out, start of
each clip), then:
1. joins: the air (raccords.py) at each join between two clips, below --min-air = alert;
   all the joins of a retake are listed, with the words on both sides;
2. level: the speech of each retake against that of the clip just before and just after (speech
   RMS dB), a gap above --max-db = alert (other recording session);
3. text: the module is re-transcribed chunk by chunk (transcribe_chunks.py), aligned on its script
   (align_script.py) and compared sentence by sentence (ecarts_script.py); with --avant, the
   deviations that did not exist in the original rough cuts are isolated ("NEW");
4. duplicates: a run of at least 3 script positions said twice in the edit (a
   retake laid without removing the old sentence, a leftover sentence end).

    python3 qc_assemblage.py <part.xml> <plan.json> <qc folder> [--avant] [--sans-whisper]

Writes in <qc folder>/<module>/: montage.wav (48 kHz), audio.wav (16 kHz), words_premiere.json,
chunks.json, align.json, ecarts.txt; and <qc folder>/qc.txt (the report). Exit code 2 on any alert.
The times given are those of the Premiere SEQUENCE (mm:ss from the start of the part).
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import soundfile as sf

sys.dont_write_bytecode = True
ICI = Path(__file__).parent
sys.path.insert(0, str(ICI))
import raccords  # noqa: E402

SR = 48000


def hms(t):
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def lire_xml(xml):
    seq = ET.parse(xml).getroot().find("sequence")
    fps = int(seq.find("rate/timebase").text)
    chemins = {}
    for f in seq.iter("file"):
        p = f.find("pathurl")
        if p is not None:
            chemins[f.get("id")] = urllib.parse.unquote(p.text.replace("file://localhost", ""))
    clips = []
    for k, t in enumerate(seq.find("media/audio").findall("track"), start=1):
        for c in t.findall("clipitem"):
            if c.find("enabled").text != "TRUE":
                continue
            lv = c.find("filter/effect/parameter[parameterid='level']/value")
            clips.append({"piste": k, "nom": c.find("name").text, "src": chemins[c.find("file").get("id")],
                          "niveau": float(lv.text) if lv is not None else 1.0,
                          **{x: int(c.find(x).text) for x in ("in", "out", "start", "end")}})
    clips.sort(key=lambda c: c["start"])
    modules = [(int(m.find("in").text), m.find("name").text) for m in seq.findall("marker")
               if (m.find("comment").text or "") == "Module start"]
    reps = {m.find("name").text.split("Retake: ", 1)[1]: int(m.find("in").text) for m in seq.findall("marker")
            if m.find("name").text.startswith("Retake: ")}
    return fps, clips, modules, reps


def rendre(clips, fps, f0, f1):
    """Sequence sound between frames f0 and f1 (sum of the tracks)."""
    spf = SR // fps
    y = np.zeros((f1 - f0) * spf, dtype=np.float32)
    for c in clips:
        if c["end"] <= f0 or c["start"] >= f1:
            continue
        x, _ = sf.read(c["src"], start=c["in"] * spf, stop=c["out"] * spf, dtype="float32", always_2d=True)
        x = x[:, 0] * c["niveau"]
        a = (c["start"] - f0) * spf
        y[a: a + len(x)] += x
    return y


def db_parole(y, par, a, b):
    """Speech RMS dB (windows marked as speech) between a and b seconds of the module."""
    i, j = max(0, int(a / raccords.HOP)), min(len(par), int(b / raccords.HOP))
    hop = int(SR * raccords.HOP)
    v = [y[k * hop:(k + 1) * hop] for k in range(i, j) if par[k]]
    if not v:
        return None
    x = np.concatenate(v)
    return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9)


def doublons(pos, words, t0):
    """Runs of >= 3 consecutive script positions said twice."""
    vu, out = {}, []
    seq = [(p, w) for p, w in zip(pos, words) if p is not None]
    for k, (p, w) in enumerate(seq):
        vu.setdefault(p, []).append(k)
    deux = sorted(p for p, ks in vu.items() if len(ks) > 1)
    run = []
    for p in deux + [None]:
        if run and (p is None or p != run[-1] + 1):
            if len(run) >= 3:
                ks = vu[run[0]]
                ws = [seq[k][1] for k in ks]
                out.append((run[0], run[-1], [t0 + w["start"] for w in ws],
                            " ".join(seq[k][1]["text"] for k in range(ks[0], ks[0] + len(run)))))
            run = []
        if p is not None:
            run.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("xml")
    ap.add_argument("plan")
    ap.add_argument("qc")
    ap.add_argument("--avant", action="store_true", help="compare with the deviations of the original rough cuts (ecarts.json of the clips)")
    ap.add_argument("--sans-whisper", action="store_true", help="reuse the transcriptions already done")
    ap.add_argument("--min-air", type=float, default=0.30)
    ap.add_argument("--max-db", type=float, default=1.5)
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    fps, clips, modules, reps = lire_xml(a.xml)
    Q = Path(a.qc)
    Q.mkdir(parents=True, exist_ok=True)
    titres = {m["titre"]: m for m in plan["modules"]}
    rapport, alertes = [], 0
    fins = [f for f, _ in modules[1:]] + [max(c["end"] for c in clips) + 1]
    for (f0, titre), fsuiv in zip(modules, fins):
        mc = [c for c in clips if f0 <= c["start"] < fsuiv]
        f1 = max(c["end"] for c in mc)
        D = Q / titre
        D.mkdir(exist_ok=True)
        y = rendre(mc, fps, f0, f1)
        sf.write(D / "montage.wav", y, SR, subtype="PCM_24")
        par = raccords.masque(raccords.rms(y, SR))
        t0 = f0 / fps
        rapport.append(f"\n## {titre} (sequence {hms(t0)} to {hms(f1 / fps)}, {(f1 - f0) / fps / 60:.2f} min, {len(mc)} clips)")

        # 1. joins
        secs, lignes_rep, bords = [], [], []
        for c1, c2 in zip(mc, mc[1:]):
            t = (c2["start"] - f0) / fps
            v = raccords.air(par, t)
            rep = c1["piste"] == 2 or c2["piste"] == 2
            if v < a.min_air:
                secs.append((t, v, c1["nom"], c2["nom"]))
            # edge inside speech (word end eaten, attack cut): speech touches the cut on one
            # side only; on both sides it is a dry join, already counted
            k = int(round(t / raccords.HOP))
            g, d = bool(par[max(0, k - 1)]), bool(par[min(len(par) - 1, k)])  # fr-ok (false positive: par, d, g)
            if g != d:
                bords.append((t, "end of clip" if g else "start of clip", c1["nom"], c2["nom"]))
            if rep:
                lignes_rep.append((t, v, c1["nom"], c2["nom"]))
        # 2. level of each retake against its neighbors
        groupes, cur = [], []
        for c in mc:
            if c["piste"] == 2:
                cur.append(c)
            elif cur:
                groupes.append(cur)
                cur = []
        if cur:
            groupes.append(cur)
        niveaux = []
        for g in groupes:
            s, e = (g[0]["start"] - f0) / fps, (g[-1]["end"] - f0) / fps
            dr = db_parole(y, par, s, e)
            dv = [x for x in (db_parole(y, par, max(0, s - 8), s), db_parole(y, par, e, e + 8)) if x is not None]
            if dr is not None and dv:
                niveaux.append((s, g[0]["nom"], dr - float(np.mean(dv))))

        # 3. text
        audio = D / "audio.wav"
        if not a.sans_whisper or not (D / "words_premiere.json").exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(D / "montage.wav"), "-ac", "1", "-ar", "16000",
                            "-c:a", "pcm_s16le", str(audio)], check=True)
            subprocess.run(["nice", sys.executable, str(ICI / "transcribe_chunks.py"), str(audio),
                            str(D / "words_premiere.json"), "--chunks", str(D / "chunks.json")],
                           check=True, capture_output=True)
        (D / "meta.json").write_text(json.dumps({"duration_seconds": len(y) / SR, "rush_path": str(D / "montage.wav"),
                                                 "fps": fps, "fps_num": fps, "fps_den": 1, "audio_channels": 1,
                                                 "audio_rate": SR, "width": None, "height": None}))
        (D / "cuts_final.json").write_text(json.dumps({"cuts": []}))
        script = titres[titre]["script"]
        subprocess.run([sys.executable, str(ICI / "align_script.py"), str(D), script], check=True, capture_output=True)
        subprocess.run([sys.executable, str(ICI / "ecarts_script.py"), str(D), script], check=True, capture_output=True)
        ec = json.loads((D / "ecarts.json").read_text())
        nouveaux = ec
        if a.avant:
            avant_r, avant_s, ns = set(), None, 0
            for r in titres[titre]["rushs"]:
                f = Path(r["work"]) / "ecarts.json"
                if f.exists():
                    e0 = json.loads(f.read_text())
                    avant_r |= {x["script"] for x in e0 if x["type"] == "reformule"}
                    s0 = {x["script"] for x in e0 if x["type"] == "saute"}
                    avant_s = s0 if avant_s is None else avant_s & s0
            nouveaux = [x for x in ec if x["script"] not in (avant_r if x["type"] == "reformule" else (avant_s or set()))]
        words = json.loads((D / "words_premiere.json").read_text())
        pos = json.loads((D / "align.json").read_text())
        dbl = doublons(pos, words, t0)

        rapport.append(f"Deviations from the script: {len(ec)} (whisper included)" + (f", of which {len(nouveaux)} absent from the original rough cuts" if a.avant else ""))
        for x in nouveaux:
            tt = hms(t0 + x["t"]) if "t" in x else "--:--"
            rapport.append(f"  NEW {x['type']:9s} {tt}\n    script: {x['script']}\n    said  : {x.get('dit', '')}")
        for p1, p2, ts, txt in dbl:
            alertes += 1
            rapport.append(f"  ⚠ DUPLICATE positions {p1}-{p2} said at {', '.join(hms(t) for t in ts)}: {txt}")
        for t, cote, n1, n2 in bords:
            alertes += 1
            av = " ".join(w["text"] for w in words if t - 2 <= w["end"] <= t + 0.05)[-50:]
            ap_ = " ".join(w["text"] for w in words if t - 0.05 <= w["start"] <= t + 2)[:50]
            rapport.append(f"  ⚠ EDGE INSIDE SPEECH {hms(t0 + t)}: {cote} ({n1} → {n2})   \"...{av} | {ap_}...\"")
        for t, v, n1, n2 in secs:
            alertes += 1
            rapport.append(f"  ⚠ DRY JOIN {hms(t0 + t)}: {v:.2f} s of air ({n1} → {n2})")
        for t, v, n1, n2 in lignes_rep:
            av = " ".join(w["text"] for w in words if t - 3 <= w["end"] <= t + 0.05)[-60:]
            ap_ = " ".join(w["text"] for w in words if t - 0.05 <= w["start"] <= t + 3)[:60]
            rapport.append(f"  retake join {hms(t0 + t)}: air {v:.2f} s   \"...{av} | {ap_}...\"")
        for s, nom, d in niveaux:
            flag = "  ⚠" if abs(d) > a.max_db else ""
            alertes += 1 if flag else 0
            rapport.append(f"  level {nom} ({hms(t0 + s)}): {d:+.1f} dB against the neighboring clip{flag}")
    txt = "\n".join(rapport)
    (Q / "qc.txt").write_text(txt + "\n")
    print(txt)
    print(f"\n{alertes} alert(s)")
    sys.exit(2 if alertes else 0)


if __name__ == "__main__":
    main()
