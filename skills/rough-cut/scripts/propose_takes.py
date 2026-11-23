#!/usr/bin/env python3
"""Propose takes.json for a read voice-over, from align.json (align_script.py).

Rule: a script word spoken several times is kept only at its LAST take.
- chunk whose script words are all repeated later: cut whole (retake;
  faux_depart under 4 words);
- chunk whose end only is repeated: cut from the first word of that end (a
  beginning that is said nowhere else stays: "I shoot a lot close to
  home | so naturally...");
- short chunk outside the script (fewer than 4 words, no script word): false start, cut;
  worth listening to when shorter than 2 s (hear.py), it is often a breath or a
  whisper "Subtitles by" hallucination;
- everything else (long chunk outside the script, retake in the middle of a chunk): flagged
  (doubt), never cut here. A rewording by the speaker does not match the script: the take
  that follows a matching take may be the right one, hence a flag rather than a cut.

    python3 propose_takes.py <work_dir>   -> takes.json + propositions.txt

Nothing is final: read propositions.txt (and dossier.txt) before apply_takes.py.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

W = Path(sys.argv[1])
words = json.loads((W / "words_premiere.json").read_text())
pos = json.loads((W / "align.json").read_text())

morc = defaultdict(list)
for i, w in enumerate(words):
    morc[w.get("chunk", 0)].append(i)
ordre = sorted(morc, key=lambda c: words[morc[c][0]]["start"])
rang = {c: k for k, c in enumerate(ordre)}
dernier = {}
for c in ordre:
    for i in morc[c]:
        if pos[i] is not None:
            dernier[pos[i]] = c


# known whisper hallucinations on a breath or a noise
import re
HALLU = re.compile(r"sous-titrage|radio-canada|amara|merci d'avoir regard|abonnez", re.I)  # fr-ok


def texte(a, b):
    return " ".join(words[i]["text"] for i in range(a, b + 1))


# Cut in the middle of a chunk (repeated end): no pause before the first cut word, so
# no air to leave; apply_takes would add some (0.27 s) and bite into the word. Bounds set
# here (6th element): start = energy valley closest to the DTW start of the cut word, end =
# 0.12 s before the start of the next chunk (measured on energy, hence reliable).
import wave
import numpy as np
_w = wave.open(str(W / "audio.wav"))
_sr = _w.getframerate()
_sig = np.frombuffer(_w.readframes(_w.getnframes()), dtype=np.int16).astype(np.float32)
_hop = int(_sr * 0.01)
_n = len(_sig) // _hop
_rms = np.sqrt((_sig[: _n * _hop].reshape(_n, _hop) ** 2).mean(axis=1))


def bornes_milieu(k, dernier_mot):
    t = words[k]["start"]
    a, b = max(0, int((t - 0.15) / 0.01)), min(_n, int((t + 0.08) / 0.01) + 1)
    debut = (a + int(np.argmin(_rms[a:b]))) * 0.01
    suiv = dernier_mot + 1
    fin = words[suiv]["start"] - 0.12 if suiv < len(words) else words[dernier_mot]["end"]
    return {"start": round(debut, 2), "end": round(max(fin, debut + 0.05), 2)}


cuts, flags, lignes = [], [], []
for c in ordre:
    ii = morc[c]
    ali = [i for i in ii if pos[i] is not None]
    redit = [i for i in ali if rang[dernier[pos[i]]] > rang[c]]
    dur = words[ii[-1]]["end"] - words[ii[0]]["start"]
    t = words[ii[0]]["start"]
    tag = f"{int(t // 60):02d}:{t % 60:05.2f} #{c}"
    if not ali:
        if len(ii) < 4 or HALLU.search(texte(ii[0], ii[-1])):
            cuts.append([ii[0], ii[-1], "faux_depart", 0.80,
                         f"off script, {len(ii)} word(s): \"{texte(ii[0], ii[-1])}\""
                         + (" (listen)" if dur < 2 else "")])
            lignes.append(f"CUT     {tag} off script: {texte(ii[0], ii[-1])}")
        else:
            flags.append([ii[0], ii[-1], "hors_script", 0.50, f"off script: \"{texte(ii[0], ii[-1])[:80]}\""])
            lignes.append(f"FLAG    {tag} off script ({len(ii)} words): {texte(ii[0], ii[-1])}")
        continue
    if not redit or (len(redit) < 3 and len(redit) < 0.3 * len(ali)):
        continue  # one or two words found later: coincidence, not a retake
    vers = sorted({dernier[pos[i]] for i in redit}, key=lambda x: rang[x])
    # beginning said nowhere else: 3 script words or more before the first repeated word
    k0 = ii.index(redit[0])
    tete = [i for i in ii[:k0] if pos[i] is not None]
    suite = [i for i in ii[k0:] if pos[i] is not None]
    redit_suite = [i for i in suite if i in redit]
    if len(tete) < 3 and len(redit) >= 0.6 * len(ali) and len(ali) >= 0.6 * len(ii):
        typ = "retake" if len(ii) >= 4 else "faux_depart"
        cuts.append([ii[0], ii[-1], typ, 0.92, f"repeated in #{','.join(map(str, vers))}: \"{texte(ii[0], ii[-1])[:70]}\""])
        lignes.append(f"CUT     {tag} whole, repeated in #{','.join(map(str, vers))}: {texte(ii[0], ii[-1])}")
    elif len(tete) >= 3 and len(redit_suite) >= max(2, 0.6 * len(suite)):
        cuts.append([ii[k0], ii[-1], "retake", 0.85,
                     f"end repeated in #{','.join(map(str, vers))}: \"{texte(ii[k0], ii[-1])[:70]}\"",
                     bornes_milieu(ii[k0], ii[-1])])
        lignes.append(f"CUT     {tag} end only (from \"{words[ii[k0]]['text']}\"), "
                      f"repeated in #{','.join(map(str, vers))}: {texte(ii[k0], ii[-1])}")
    else:
        flags.append([redit[0], redit[-1], "retake", 0.55,
                      f"words repeated in the middle of the chunk, in #{','.join(map(str, vers))}"])
        lignes.append(f"FLAG    {tag} {len(redit)} words repeated in the middle, in #{','.join(map(str, vers))}: "
                      f"{texte(ii[0], ii[-1])}")

# Review decisions (decisions.json, alongside): they override the proposals and
# survive a new transcription (chunks, cut on energy, keep their numbers).
#   {"couper": [[chunk, "type", "reason"], ...],
#    "couper_depuis": [[chunk, "first cut word", "reason"], ...],
#    "garder": [chunk, ...],          # neither cut nor flag on this chunk
#    "douter": [[chunk, "reason"], ...]}  # kept, with a marker to listen to
dec_f = W / "decisions.json"
if dec_f.exists():
    dec = json.loads(dec_f.read_text())
    garder = set(dec.get("garder", []))
    for c, *_ in dec.get("couper", []):
        garder.add(c)
    for c, *_ in dec.get("couper_depuis", []):
        garder.add(c)
    for c, *_ in dec.get("douter", []):
        garder.add(c)
    dans = lambda x, ens: any(words[i].get("chunk") in ens for i in range(x[0], x[1] + 1))
    cuts = [x for x in cuts if not dans(x, garder)]
    flags = [x for x in flags if not dans(x, garder)]
    for c, typ, why in dec.get("couper", []):
        ii = morc[c]
        cuts.append([ii[0], ii[-1], typ, 0.95, f"review: {why}"])
        lignes.append(f"CUT     #{c} (review) {why}: {texte(ii[0], ii[-1])}")
    for c, mot, why in dec.get("couper_depuis", []):
        ii = morc[c]
        k = next((i for i in ii if words[i]["text"].strip(",.…").lower() == mot.lower()), None)
        if k is None:
            sys.exit(f"decisions.json: \"{mot}\" not found in chunk #{c} ({texte(ii[0], ii[-1])})")
        cuts.append([k, ii[-1], "retake", 0.95, f"review: {why}", bornes_milieu(k, ii[-1])])
        lignes.append(f"CUT     #{c} (review) from \"{mot}\", {why}: {texte(k, ii[-1])}")
    for c, why in dec.get("douter", []):
        ii = morc[c]
        flags.append([ii[0], ii[-1], "a_ecouter", 0.50, f"review: {why}"])
        lignes.append(f"FLAG    #{c} (review) {why}: {texte(ii[0], ii[-1])}")
    cuts.sort(key=lambda x: x[0])
    flags.sort(key=lambda x: x[0])

old = {}
if (W / "takes.json").exists():
    old = json.loads((W / "takes.json").read_text())
    if old.get("_source") != "propose_takes":
        sys.exit("takes.json already exists and was not written by propose_takes.py: nothing is overwritten")
(W / "takes.json").write_text(json.dumps({"_source": "propose_takes", "cuts": cuts, "flags": flags,
                                          "time_cuts": [], "protect": []}, ensure_ascii=False, indent=1))
(W / "propositions.txt").write_text("\n".join(lignes) + "\n")
print(f"{len(cuts)} cuts, {len(flags)} flags proposed; see {W / 'propositions.txt'}")
