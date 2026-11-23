#!/usr/bin/env python3
"""Deviations between the script and what remains in the edit (read voice-over), sentence by sentence.

Run after apply_takes.py: only the kept words (outside the "disable" cuts of
cuts_final.json) are compared to the script. For each script sentence:
- "skipped" (SKIPPED): the sentence, or a passage of 3 words or more, is said in no kept take;
- "reworded" (REWORDED): 3 or more words changed, added or removed, or two content words
  of the script missing;
the rest (one or two words changed, a whisper error that resembles the
script word) is counted, not listed.

    python3 ecarts_script.py <work_dir> <script.md>   -> ecarts.txt (and ecarts.json)

whisper can mishear: check a deviation by ear (hear.py) before raising it.
"""
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from align_script import mots_script, norm, decoupe_mot  # noqa: E402

PETITS = set("le la les l de des du d un une et a à au aux en y ne n pas que qu qui ce c ça "  # fr-ok
             "se s on il elle ils vous nous je j me m te t tu est sont donc alors bon mais ou "  # fr-ok
             "là si plus très bien aussi oui eh".split())  # fr-ok


def main():
    W, script_md = Path(sys.argv[1]), Path(sys.argv[2])
    words = json.loads((W / "words_premiere.json").read_text())
    pos = json.loads((W / "align.json").read_text())
    cuts = json.loads((W / "cuts_final.json").read_text())["cuts"]
    dis = [(c["start"], c["end"]) for c in cuts if c["decision"] == "disable"]

    def garde(w):
        m = (w["start"] + min(w["end"], w["start"] + 0.3)) / 2
        return not any(a <= m < b for a, b in dis)

    script = mots_script(script_md.read_text())
    sn = [norm(t) for t in script]
    # script sentences: [start, end[ as positions
    phrases, d = [], 0
    for i, t in enumerate(script):
        if re.search(r"[.!?…:]$", t) or i == len(script) - 1:
            phrases.append((d, i + 1))
            d = i + 1

    # kept words, in time order, with their position (unaligned ones attached
    # to the position of the last aligned word before them)
    gardes, last = [], -1
    for i, w in enumerate(words):
        if not garde(w):
            continue
        p = pos[i]
        if p is not None:
            last = p
        gardes.append((p if p is not None else last + 0.5, w["text"], w["start"]))

    sortie, mineurs, js = [], 0, []
    for a, b in phrases:
        dit = [(p, t, s) for p, t, s in gardes if a - 0.5 <= p < b - 0.5 or (p == b - 0.5)]
        ref = sn[a:b]
        dn = [norm(x) for _, t, _ in dit for x in decoupe_mot(t)]
        if not dit:
            txt = " ".join(script[a:b])
            if len(ref) >= 3:
                sortie.append(f"SKIPPED     (script {a}) {txt}")
                js.append({"type": "saute", "pos": a, "script": txt})
            continue
        sm = difflib.SequenceMatcher(None, ref, dn, autojunk=False)
        change, grave = 0, False
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                continue
            r, h = ref[i1:i2], dn[j1:j2]
            if op == "replace" and len(r) == len(h) == 1 and \
                    difflib.SequenceMatcher(None, r[0], h[0]).ratio() >= 0.6:
                continue  # whisper error that resembles the script word
            change += max(len(r), len(h))
            if op == "delete" and len([x for x in r if x not in PETITS]) >= 2:
                grave = True  # a piece of the script sentence is missing
        if change >= 3 or grave:
            t0 = dit[0][2]
            sc = " ".join(script[a:b])
            ditxt = " ".join(t for _, t, _ in dit)
            sortie.append(f"REWORDED    {int(t0 // 60):02d}:{t0 % 60:05.2f}\n    script: {sc}\n    said  : {ditxt}")
            js.append({"type": "reformule", "t": round(t0, 2), "script": sc, "dit": ditxt})
        elif change:
            mineurs += 1
    entete = [f"{len(js)} deviations to settle, {mineurs} minor deviations not listed (a small word added or dropped)",
              "(raw file time; whisper may have misheard: check by ear)", ""]
    (W / "ecarts.txt").write_text("\n".join(entete + sortie) + "\n")
    (W / "ecarts.json").write_text(json.dumps(js, ensure_ascii=False, indent=1))
    print(entete[0])


if __name__ == "__main__":
    main()
