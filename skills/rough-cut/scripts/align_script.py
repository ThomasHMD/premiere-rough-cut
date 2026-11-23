#!/usr/bin/env python3
"""Aligns the spoken words (words_premiere.json, or the one from transcribe_chunks.py) on the
script that was read, to prepare take selection for a read voice-over.

Each spoken word gets the position of the script word it pronounces (or nothing: aside,
rewording, word whisper misheard). A script passage spoken twice therefore lands on the
same position: the earlier take is a retake, the LAST one is kept.

    python3 align_script.py <work_dir> <script.md> [--out dossier.txt]

Writes in the work folder:
- align.json: for each word, its position in the script (null if none);
- dossier.txt: one chunk per line (time, script positions, share of script words,
  text), with "<< REPRISE" in the margin when a later chunk repeats the same words,
  and at the end the list of script passages never spoken and of deviations from the text.
This is the file to read to write takes.json; nothing is decided here.

The script: everything before the "---" line, without headings (#), the clapper-board lines and bold.
"""
import argparse
import difflib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


NOMBRES = dict(zip("0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 30 40 50 60 100 1000".split(),  # fr-ok
                   "zero un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze "  # fr-ok
                   "seize dixsept dixhuit dixneuf vingt trente quarante cinquante soixante cent mille".split()))  # fr-ok


def norm(s):
    s = unicodedata.normalize("NFD", s.lower().replace("’", "'"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]", "", s)
    return NOMBRES.get(s, s)  # whisper writes "2 minutes", the script "deux minutes"  # fr-ok


def mots_script(md):
    lignes = []
    for l in md.splitlines():
        if l.strip() == "---":
            break
        if l.startswith("#") or l.lstrip().startswith("🎬") or not l.strip():
            continue
        lignes.append(re.sub(r"\*\*|__|^\s*[-*]\s+", "", l))
    brut = " ".join(lignes)
    brut = re.sub(r"[()«»\"“”]", " ", brut)  # fr-ok
    toks = []
    for t in re.split(r"\s+|(?<=[a-zA-Z])'(?=\w)|-(?=\w)", brut):
        if t and norm(t):
            toks.append(t)
    # "l'image" -> "l'" "image": whisper often writes "l'image" as one block
    return toks


def decoupe_mot(t):
    return [x for x in re.split(r"(?<=[a-zA-Z])'(?=\w)|-(?=\w)", t) if norm(x)]


def proche(x, y):
    return difflib.SequenceMatcher(None, x, y).ratio()


def aligne(dits, script, fen=150):
    """Script position for each spoken word, chunk by chunk (local alignment).

    Chunks are taken in time order and searched near where the reading had got to
    (fen words before and after): a retake goes back a few sentences, never to the
    other end of the script. Elsewhere, only on strong support (3 word pairs).
    Then the words left alone are caught by similarity (whisper writes misspelled proper
    nouns) between two aligned neighbors, or right after the previous chunk."""
    sn = [norm(t) for t in script]
    idx = defaultdict(list)
    for i in range(len(sn) - 1):
        idx[(sn[i], sn[i + 1])].append(i)
    pos = [None] * len(dits)
    par_morceau = defaultdict(list)
    for k, w in enumerate(dits):
        par_morceau[w["chunk"]].append(k)
    ordre = sorted(par_morceau, key=lambda c: dits[par_morceau[c][0]]["start"])
    cur = 0
    for c in ordre:
        ks = par_morceau[c]
        dn = [norm(dits[k]["text"]) for k in ks]
        votes, votes_loin = defaultdict(int), defaultdict(int)
        for j in range(len(dn) - 1):
            for p in idx.get((dn[j], dn[j + 1]), []):
                if abs(p - cur) <= fen:
                    votes[(p - j) // 8] += 1
                else:
                    votes_loin[(p - j) // 8] += 1
        if votes:
            best = max(votes, key=lambda v: (votes[v], -abs(v * 8 - cur)))
        elif votes_loin and max(votes_loin.values()) >= 3:
            best = max(votes_loin, key=votes_loin.get)
        else:
            continue
        a = max(0, best * 8 - 10)
        b = min(len(sn), best * 8 + len(dn) + 20)
        sm = difflib.SequenceMatcher(None, dn, sn[a:b], autojunk=False)
        for blk in sm.get_matching_blocks():
            for t in range(blk.size):
                pos[ks[blk.a + t]] = a + blk.b + t
        # lone words stuck between two aligned words: similarity
        for j, k in enumerate(ks):
            if pos[k] is not None:
                continue
            g = next((pos[ks[x]] for x in range(j - 1, -1, -1) if pos[ks[x]] is not None), None)
            d = next((pos[ks[x]] for x in range(j + 1, len(ks)) if pos[ks[x]] is not None), None)
            lo = (g + 1) if g is not None else max(0, (d or 0) - 3)
            hi = d if d is not None else min(len(sn), (g or 0) + 4)
            cand = [(proche(dn[j], sn[q]), q) for q in range(lo, hi) if q not in pos]
            if cand:
                r, q = max(cand)
                if r >= 0.6:
                    pos[k] = q
        al = [pos[k] for k in ks if pos[k] is not None]
        if al:
            cur = max(al)
    # chunks left with nothing: their words, right after the reading of the previous chunk,
    # or right before that of the next one (a short filler, then the real start of the right take)
    def essai(ks, q):
        out, r_tot = {}, 0.0
        for k in ks:
            dn = norm(dits[k]["text"])
            cand = [(proche(dn, sn[x]), x) for x in range(max(0, q), min(len(sn), q + 4))]
            if cand:
                r, x = max(cand)
                if r >= 0.75:
                    out[k] = x
                    r_tot += r
                    q = x + 1
        return out, r_tot
    cur = 0
    for n, c in enumerate(ordre):
        ks = par_morceau[c]
        al = [pos[k] for k in ks if pos[k] is not None]
        if not al:
            suiv = next((min(p for p in (pos[k] for k in par_morceau[d]) if p is not None)
                         for d in ordre[n + 1:n + 3]
                         if any(pos[k] is not None for k in par_morceau[d])), None)
            avant, ra = essai(ks, cur + 1)
            apres, rb = essai(ks, suiv - len(ks)) if suiv is not None else ({}, 0.0)
            if not all(x < suiv for x in apres.values()):
                apres, rb = {}, 0.0
            for k, x in (apres if rb > ra else avant).items():
                pos[k] = x
            al = [pos[k] for k in ks if pos[k] is not None]
        if al:
            cur = max(al)
    return pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("script")
    a = ap.parse_args()
    W = Path(a.work)
    brut = json.loads((W / "words_premiere.json").read_text())
    # spoken words split like the script (l'image -> l' image), keeping the original index
    dits = []
    for i, w in enumerate(brut):
        for t in decoupe_mot(w["text"]):
            dits.append({"text": t, "start": w["start"], "chunk": w.get("chunk", 0), "orig": i})
    script = mots_script(Path(a.script).read_text())
    pos = aligne(dits, script)

    # position per original word: the first aligned part
    pos_orig = [None] * len(brut)
    for d, p in zip(dits, pos):
        if p is not None and pos_orig[d["orig"]] is None:
            pos_orig[d["orig"]] = p
    (W / "align.json").write_text(json.dumps(pos_orig))

    # chunks
    morc = defaultdict(list)
    for i, w in enumerate(brut):
        morc[w.get("chunk", 0)].append(i)
    ordre = sorted(morc, key=lambda c: brut[morc[c][0]]["start"])
    dernier = {}  # script position -> last chunk that says it
    for c in ordre:
        for i in morc[c]:
            if pos_orig[i] is not None:
                dernier[pos_orig[i]] = c
    lignes = []
    for c in ordre:
        ii = morc[c]
        ps = [pos_orig[i] for i in ii if pos_orig[i] is not None]
        part = len(ps) / len(ii)
        redits = sorted({dernier[p] for p in ps if dernier[p] != c})
        n_redit = sum(1 for p in ps if dernier[p] != c)
        marge = ""
        if n_redit:
            marge = f"  << REPRISE {n_redit}/{len(ii)} words repeated in #{','.join(map(str, redits))}"
        rng = f"{min(ps):5d}-{max(ps):5d}" if ps else "    -      "
        t = brut[ii[0]]["start"]
        texte = " ".join(brut[i]["text"] for i in ii)
        lignes.append(f"#{c:<4d} {int(t // 60):02d}:{t % 60:05.2f}  [{rng}] {part:4.0%}  "
                      f"w{ii[0]}-{ii[-1]}  {texte}{marge}")

    dits_pos = set(p for p in pos_orig if p is not None)
    trous, i = [], 0
    while i < len(script):
        if i not in dits_pos:
            j = i
            while j < len(script) and j not in dits_pos:
                j += 1
            if j - i >= 3:
                trous.append(f"  [{i}-{j - 1}] {' '.join(script[i:j])}")
            i = j
        else:
            i += 1
    sortie = ["CHUNKS (file time, script positions, share of script words)"] + lignes
    sortie += ["", f"SCRIPT PASSAGES NEVER SPOKEN (3 words or more): {len(trous)}"] + trous
    (W / "dossier.txt").write_text("\n".join(sortie) + "\n")
    tot = len(brut)
    ali = sum(1 for p in pos_orig if p is not None)
    print(f"{tot} spoken words, {ali} aligned on the script ({ali / max(1, tot):.0%}), "
          f"{len(script)} script words, {len(trous)} gaps; file: {W / 'dossier.txt'}")


if __name__ == "__main__":
    main()
