#!/usr/bin/env python3
"""Second opinion from whisper, segment by segment, on a Premiere sequence transcript.

whisper on a whole voice file can hallucinate in a loop (a subtitle credit line repeated over 20 min):
so the source audio of EACH Premiere segment is cut out (voice clips of the sequence
read from the .prproj, sequence timecode -> source file), whisper transcribes it alone, and
compare.txt lists the word-by-word differences. Premiere stays the base (it timecodes everything
and keeps the repetitions); whisper is only used to settle the wrong words. It often adds, at the
edge of an excerpt, words of the neighboring segment (0.4 s margin): ignore those differences.

  second_avis_whisper.py PROJECT.prproj transcription.json --voix "Track" --out FOLDER [--prompt "..."] [--lang fr]
  second_avis_whisper.py PROJECT.prproj transcription.json --voix "Track" --out FOLDER --sondes probes.txt
     probes.txt: one line "label|segment index|exact words of the segment" -> window +-1.5 s,
     3 decodings (default, beam 8, temperature 0.3) to settle a doubtful word.
--lang: spoken language (default: language of transcription.json, else en).
"""
import argparse, difflib, json, os, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "overlays" / "scripts"))
import prproj_lib as P

import lang

MODEL = str(Path.home() / "Models/whisper/ggml-large-v3-turbo.bin")


def clips_voix(prproj, motif):
    root, by_id, by_uid = P.load(Path(prproj))
    seqs = P.sequences(root, by_id, by_uid)
    idx = max(range(len(seqs)), key=lambda i: sum(len(t[3]) for t in P.tracks(seqs[i][1], by_id, by_uid)))
    out = []
    for kind, n, _, items in P.tracks(seqs[idx][1], by_id, by_uid):
        if kind != "A":
            continue
        for it in items:
            f = P.media_name(it, by_id, by_uid) or ""
            if motif not in Path(f).name:
                continue
            b = P.bounds(it, by_id, by_uid)
            c = P.deref(P.deref(it.find(".//SubClip"), by_id, by_uid).find("Clip"), by_id, by_uid).find("Clip")
            out.append((b[0], b[1], int(c.find("InPoint").text) / P.TICKS, f))
    # the .prproj sometimes gives only the file name: look for it next to the project
    noms = {Path(c[3]).name for c in out if not Path(c[3]).exists()}
    trouves = {f.name: str(f) for f in Path(prproj).resolve().parent.rglob("*") if f.name in noms} if noms else {}
    manquants = noms - set(trouves)
    if manquants:
        sys.exit(f"voice files not found under {Path(prproj).parent}: {sorted(manquants)}")
    return sorted((a, b, ip, f if Path(f).exists() else trouves[Path(f).name]) for a, b, ip, f in out)


def extrait(clips, a, b, pad, dest):
    c = min(clips, key=lambda c: 0 if c[0] - 0.2 <= a < c[1] + 0.2 else min(abs(a - c[0]), abs(a - c[1])))
    sa, sb = c[2] + a - c[0] - pad, c[2] + b - c[0] + pad
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{max(0, sa):.3f}", "-to", f"{sb:.3f}", "-i", c[3],
                    "-af", "dynaudnorm", "-ar", "16000", "-ac", "1", dest], check=True)


def whisper(wav, extra=(), prompt=None, code="en"):
    cmd = ["whisper-cli", "-m", MODEL, "-l", code, "-np", "-nt", "-f", wav, *extra] + (["--prompt", prompt] if prompt else [])
    return " ".join(subprocess.run(cmd, capture_output=True, text=True).stdout.split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prproj"); ap.add_argument("transcription")
    ap.add_argument("--voix", required=True, help='text found in the names of the voice files (e.g. "Track")')
    ap.add_argument("--out", required=True); ap.add_argument("--prompt"); ap.add_argument("--sondes")
    lang.add_argument(ap)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    clips = clips_voix(a.prproj, a.voix)
    doc = json.load(open(a.transcription))
    segs = doc["segments"]
    code = lang.load(lang.resolve(a.lang, doc.get("language")))["whisper_code"]
    mots = lambda s: [w for w in s["words"] if w["text"].strip()]

    if a.sondes:
        for ligne in open(a.sondes):
            if not ligne.strip():
                continue
            tag, k, phrase = ligne.rstrip("\n").split("|")
            ws = mots(segs[int(k)]); toks = [t.strip(".,?!…").lower() for t in phrase.split()]
            i = next(i for i in range(len(ws) - len(toks) + 1)
                     if all(ws[i + j]["text"].lower().strip(".,?!…  ").startswith(t) for j, t in enumerate(toks)))
            w0, w1 = ws[i], ws[i + len(toks) - 1]
            dest = str(out / f"sonde-{tag}.wav"); extrait(clips, w0["start"], w1["start"] + w1["duration"], 1.5, dest)
            print(f'{tag} [{k}] "{phrase}"')
            for extra in ([], ["-bs", "8", "-bo", "8"], ["-tp", "0.3", "-nf"]):
                print("    ", whisper(dest, extra, code=code))
        return

    norm = lambda t: re.sub(r"[^\w']", "", t.lower().replace("’", "'").replace("-", " "))
    split = lambda t: [w for w in re.split(r"[\s\-]+", t) if norm(w)]
    rapport = []
    for k, s in enumerate(segs):
        ws = mots(s)
        dest = str(out / f"s{k:03d}.wav"); extrait(clips, ws[0]["start"], ws[-1]["start"] + ws[-1]["duration"], 0.4, dest)
        wt = whisper(dest, prompt=a.prompt, code=code)
        pt = " ".join(w["text"] for w in ws)
        A, B = split(pt), split(wt)
        ecarts = [f"   …{' '.join(A[max(0, i1 - 3):i1])} [{' '.join(A[i1:i2])}] → [{' '.join(B[j1:j2])}]"
                  for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [norm(x) for x in A], [norm(x) for x in B], autojunk=False).get_opcodes()
                  if tag != "equal"]
        rapport.append(f"[{k}] P: {pt}\n    W: {wt}\n" + "\n".join(ecarts))
        print(k, end=" ", flush=True)
    (out / "compare.txt").write_text("\n\n".join(rapport))
    print(f"\n{out / 'compare.txt'}")


if __name__ == "__main__":
    main()
