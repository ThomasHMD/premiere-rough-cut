"""Overlay rules shared by all plans (a video's `plan.py`): a plan lays its scenes on words,
then calls `tenue()` BEFORE laying the curtains, then `volets()`.

    sys.path.insert(0, "<skills>/overlays/scripts")
    import habillage
    for ligne in habillage.tenue(SEG, WINDOWS, BROLLS, END, tc):
        print("  " + ligne)
    habillage.volets(SEG, WINDOWS, BROLLS, END, scene, son)

Plan conventions:
- SEG: segments {type, id, component, alpha, timecode, durationSec, cues, sfx, _start};
  `cues` and `sfx[].at` in seconds since the start of the scene;
- WINDOWS: demo windows [(id, start, end)], in sequence time;
- BROLLS: [(id, file, start, duration)];
- tc(t): seconds -> "MM:SS.ss".

Born from the editor's feedback on a first preview: animations not on screen long enough, gone
in the time of one word; it should feel dynamic and interesting, not nervous and stressful.
"""

# Minimums
MIN_PLEIN = {"chapter-card": 3.0, "question-card": 2.8, "chapitre": 3.0, "titre": 2.8, "mx-chapitre": 3.0, "mx-extinction": 3.0}   # full-screen cards
MIN_SUR = 2.6          # an overlay holds at least 2.6 s…
TENUE_DERNIER = 1.6    # … and its last element 1.6 s
FIN_GESTE = {"mx-extinction": 0.65}   # last cue = a gesture, not a text to read: the scene ends with it (otherwise 1 s of black screen)
TAMPON_MIN = 1.8       # a stamp that cannot hold 1.8 s is dropped
AVANCE_MAX = 1.0       # a card that runs into something may enter up to 1 s earlier
RETARD_MAX = 0.8       # the following card or demo may wait up to 0.8 s
ECART_SUR = 0.15       # an overlay stops 0.15 s before the next one
ECART_PLEIN = 0.2      # a full-screen scene stops 0.2 s before an overlay
RETOUR_MIN = 1.2       # a camera return shorter than 1.2 s: no curtain, the block continues

fin = lambda s: s["_start"] + s["durationSec"]
sur = lambda s: s["type"] != "scene" or (s["alpha"] and s["component"] != "volet")
plein = lambda s: s["type"] == "scene" and not s["alpha"]
cote = lambda s: (s.get("data") or {}).get("side")
meme_cote = lambda a, b: cote(a) is None or cote(b) is None or cote(a) == cote(b)
dernier = lambda s: max([c for c in s.get("cues") or [] if c < s["durationSec"]] or [0.0])


def tenue(SEG, WINDOWS, BROLLS, END, tc, lecture=None, montre=()):
    """Applies the minimum screen times to SEG and WINDOWS (modified in place).
    Sounds locked to words never move: only the ends change, plus the entrance of cards
    (their sounds follow them) and the start of demos (their gestures anchored on words do
    not move: screencast-record waits for them). Returns the change log; a line that starts
    with "!!" is a minimum that could not be met.
    Last, an overlay that runs into the next full-screen block (card, b-roll) is stopped at
    its start. `lecture`: {id: wanted duration}, written by controle-texte.py (<base>_lecture.json) so
    that a sentence has time to be read; counted as one more need. `montre`: [(start, end)]
    where the speaker shows an object to the camera (montre.py, validated on the contact sheet): nothing is lengthened there."""
    lecture = lecture or {}
    SEG.sort(key=lambda s: s["_start"])
    log = []

    def dessous():
        return [(a, b) for _, a, b in WINDOWS] + [(a, a + d) for _, _, a, d in BROLLS]

    def pousse_demo(t, d, pourquoi):
        for i, (sid, a, b) in enumerate(WINDOWS):
            if abs(a - t) < 0.06:
                WINDOWS[i] = (sid, round(a + d, 2), b)
                log.append(f"demo {sid} starts {d:.2f} s later ({pourquoi})")
                return True
        return False

    def couverture():
        """Ranges where the picture is covered (full-screen scenes, demos, b-rolls), glued together."""
        pl = sorted([(x["_start"], fin(x)) for x in SEG if plein(x) and x["component"] != "volet"] + dessous())
        out = []
        for a, b in pl:
            if out and a <= out[-1][1] + 0.02:   # 0.02 and not 0.05: a block ending 0.05 s before the next (end at "word - 0.15",
                # start at "word - 0.1") let the face show for 1 frame, which volets() reported without the hold closing it
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a, b])
        return out

    # 1. Overlays: MIN_SUR, last element TENUE_DERNIER; stop on the cut of the next full-screen
    #    block (the curtain, above, covers it) or before the next overlay.
    #    If room is missing, the following card or demo waits.
    for s in list(SEG):
        if not sur(s):
            continue
        t0 = s["_start"]
        cv = couverture()
        dedans = next((b for a, b in cv if a - 0.05 <= t0 < b), None)
        coupe = dedans if dedans is not None else min([a for a, _ in cv if a > t0 + 0.05] + [END])
        # the next overlay only bounds this one if it takes the same side of the picture (a
        # stamp on the right and a card on the left cross without bothering each other)
        suiv = min([x["_start"] - ECART_SUR for x in SEG if sur(x) and x is not s and x["_start"] > t0 + 0.05
                    and meme_cote(s, x)] + [a for a, _ in montre if a > t0 + 0.05] + [END])
        besoin = max(MIN_SUR, dernier(s) + TENUE_DERNIER, lecture.get(s.get("id"), 0.0))
        limite = min(coupe, suiv) - t0
        carton = next((x for x in SEG if plein(x) and x.get("component") in MIN_PLEIN
                       and abs(x["_start"] - (t0 + limite)) < 0.06), None)
        if limite < besoin and carton is not None and coupe <= suiv:
            d = round(min(RETARD_MAX, besoin - limite), 2)
            carton["_start"] += d
            carton["timecode"] = tc(carton["_start"])
            carton["durationSec"] = round(carton["durationSec"] - d, 2)
            log.append(f"{carton['id']} enters {d:.2f} s later (lets {s.get('id')} finish)")
            limite += d
        elif limite < besoin and dedans is None and coupe <= suiv:
            d = round(min(RETARD_MAX, besoin - limite), 2)
            if pousse_demo(coupe, d, f"lets {s.get('id')} finish"):
                limite += d
        if s.get("component") == "stamp" and min(besoin, limite) < TAMPON_MIN:
            SEG.remove(s)
            log.append(f"stamp {s['id']} removed: only {limite:.1f} s before the next element")
            continue
        if s["durationSec"] < besoin and limite > s["durationSec"]:
            nd = round(min(besoin, limite), 2)
            log.append(f"{s.get('id', s['type'])} : {s['durationSec']:.2f} → {nd:.2f} s")
            s["durationSec"] = nd
        # a stamp (a single word) is acceptable from TAMPON_MIN; the rest must meet its need
        mini = TAMPON_MIN if s.get("component") == "stamp" else besoin - 0.05
        if s["durationSec"] < mini:
            log.append(f"!! {s.get('id', s['type'])} stays at {s['durationSec']:.2f} s (wanted {besoin:.2f})")

    # 2. Full-screen: cards MIN_PLEIN, last element TENUE_DERNIER; extended without
    #    covering the next scene or overlay (demos, underneath, see 3).
    for s in SEG:
        if not plein(s) or s["component"] == "volet":
            continue
        t0 = s["_start"]
        besoin = max(MIN_PLEIN.get(s["component"], 0.0), dernier(s) + FIN_GESTE.get(s["component"], TENUE_DERNIER) if s.get("cues") else 0.0,
                     lecture.get(s["id"], 0.0))
        if s["durationSec"] >= besoin:
            continue
        # a b-roll or a demo bound it too: lengthened on top, the scene hid them (a scene over a b-roll
        # was refused by garde_premiere "HIDDEN ... only 21% visible")
        bornes = [x["_start"] for x in SEG if (plein(x) or sur(x)) and x is not s and x["_start"] > t0 + 0.05] + \
                 [a for a, _ in montre if a > t0 + 0.05] + [a for a, _ in dessous() if a > t0 + 0.05]
        limite = min(bornes + [END]) - t0 - (ECART_PLEIN if bornes and min(bornes) in [x["_start"] for x in SEG if sur(x)] else 0.0)
        nd = min(besoin, max(s["durationSec"], limite))
        avant = s["durationSec"]
        if nd < besoin and s["component"] in MIN_PLEIN:
            prec = max([fin(x) for x in SEG if (plein(x) or sur(x)) and x is not s and fin(x) <= t0 + 0.05] + [0.0])
            recul = min(AVANCE_MAX, besoin - nd, max(0.0, t0 - prec - 0.1))
            s["_start"] = round(t0 - recul, 3)
            s["timecode"] = tc(s["_start"])
            nd += recul
        s["durationSec"] = round(nd, 2)
        if s["durationSec"] > avant:
            log.append(f"{s['id']}: {avant:.2f} -> {s['durationSec']:.2f} s")
        if s["durationSec"] < besoin - 0.05:
            log.append(f"!! {s['id']} stays at {s['durationSec']:.2f} s (wanted {besoin:.2f})")

    # 3. No flash back to the face: between two full-screen blocks, a camera return
    #    shorter than RETOUR_MIN would be a hard cut (no curtain) and would show the
    #    face for half a second only (0.30 to 0.74 s). The earlier block holds
    #    until the next one (a demo keeps its last frame), unless an overlay
    #    starts in the gap: then it is intended, we only report it.
    cv = couverture()
    for (a1, b1), (a2, b2) in zip(cv, cv[1:]):
        trou = a2 - b1
        if not 0.02 < trou < RETOUR_MIN:
            continue
        if any(b1 - 0.02 <= x["_start"] < a2 for x in SEG if sur(x)):
            log.append(f"!! camera return of {trou:.2f} s at {tc(b1)} (an overlay starts in it)")
            continue
        fait = False
        for i, (sid, a, b) in enumerate(WINDOWS):
            if abs(b - b1) < 0.02:
                WINDOWS[i] = (sid, a, round(a2, 2))
                log.append(f"demo {sid} holds until the next block (+{trou:.2f} s, no more flash return)")
                fait = True
        for x in SEG:
            if plein(x) and x["component"] != "volet" and abs(fin(x) - b1) < 0.02:
                x["durationSec"] = round(a2 - x["_start"], 2)
                log.append(f"{x['id']} holds until the next block (+{trou:.2f} s, no more flash return)")
                fait = True
        if not fait:
            log.append(f"!! camera return of {trou:.2f} s at {tc(b1)} (b-roll: lengthen by hand)")

    # 4. A card never covers the start of a demo: a demo opens on a gesture and its
    #    noise (focus, typing), which would be heard without being seen. It starts at the
    #    end of the card (its window moves: record it again).
    for s in SEG:
        if plein(s) and s["component"] != "volet":
            for sid, a, b in list(WINDOWS):
                if s["_start"] + 0.05 < a < fin(s) - 0.02:
                    pousse_demo(a, round(fin(s) - a, 2), f"after {s['id']}")

    # 5. An overlay stops at the cut of the next full-screen block (the curtain passes
    #    over it). Laid on a track above the cards, it would stay visible OVER
    #    the card: the hold (1.) only lengthens, an end written too far used to pass
    #    (two GIFs covered 0.3 s of a chapter card).
    cv = couverture()
    for s in SEG:
        if not sur(s):
            continue
        nxt = next((a for a, _ in cv if a > s["_start"] + 0.05), None)
        if nxt is not None and fin(s) > nxt + 0.01:
            log.append(f"{s.get('id')} stopped at the cut of {tc(nxt)}: {s['durationSec']:.2f} -> {nxt - s['_start']:.2f} s")
            s["durationSec"] = round(nxt - s["_start"], 2)
    return log


RETRO = {"titre-retro", "chiffres-retro", "fiche-retro", "tirage", "ecran"}
BLOC_COURT = 4.5       # a shorter block (card, profile card) enters and leaves without a curtain: two curtains for 3 s of screen is half the block
ALLER_RETOUR = 3.0     # two full-screen blocks less than 3 s apart: no curtain between them (busy back and forth)


COUPE_IMAGES = 6   # a block edge 6 frames or less on the wrong side of a cut snaps onto it


def coupes(SEG, BROLLS, TL, tc, fps=29.97, montre=()):
    """Snaps to the cuts the edges of blocks that hide the speaker's face (opaque scenes, b-rolls). Call after
    `tenue()`, before `volets()`. A block that enters 1 to 6 frames AFTER a cut showed those frames of the next shot
    before covering them; a block that leaves 1 to 6 frames BEFORE a cut let the end of the previous shot show: a stray
    frame after a cut looks odd. The entrance moves back onto the cut (cues and sounds follow: they stay on their
    words), the exit lengthens up to it; never if another block already covers the gap. TL: the map of the speaker's edit
    (`_timeline.json`). Returns the log of moved edges."""
    cuts = sorted({round(c["seq_in"] * fps) for c in TL} | {round(c["seq_out"] * fps) for c in TL})
    blocs = lambda: [(x["_start"], fin(x)) for x in SEG if plein(x) and x["component"] != "volet"] + \
                    [(a, a + d) for _, _, a, d in BROLLS]
    def couvert(a, b, soi):   # gap already covered by another block, or a moment when the speaker shows an object (we do not enter it)
        return any(x <= a + 0.5 / fps and y >= b - 0.5 / fps for x, y in blocs() if (x, y) != soi) or \
            any(m0 < b and m1 > a for m0, m1 in montre)
    journal = []
    def caler(nom, a, b):
        fa, fb = round(a * fps), round(b * fps)
        na, nb = a, b
        c = next((c for c in cuts if 0 < fa - c <= COUPE_IMAGES), None)
        if c is not None and not couvert(c / fps, a, (a, b)):
            na = round(c / fps, 3)
            journal.append(f"{tc(a)} {nom}: entrance snapped to the cut ({fa - c} frame(s) earlier)")
        c = next((c for c in cuts if 0 < c - fb <= COUPE_IMAGES), None)
        if c is not None and not couvert(b, c / fps, (a, b)):
            nb = round(c / fps, 3)
            journal.append(f"{tc(b)} {nom}: exit snapped to the cut ({c - fb} frame(s) later)")
        return na, nb
    for s in SEG:
        if not plein(s) or s["component"] == "volet":
            continue
        a, b = s["_start"], fin(s)
        na, nb = caler(s["id"], a, b)
        if (na, nb) == (a, b):
            continue
        d = a - na
        s["_start"] = na
        s["timecode"] = tc(na)
        s["durationSec"] = round(nb - na, 3)
        s["cues"] = [round(c + d, 3) for c in s.get("cues") or []]
        for f in s.get("sfx") or []:
            f["at"] = round(f["at"] + d, 3)
    for i, (bid, f, a, d) in enumerate(BROLLS):
        na, nb = caler(f"b-roll {bid}", a, a + d)
        BROLLS[i] = (bid, f, na, round(nb - na, 3))
    return journal


def libre_montre(SEG, BROLLS, montre, zooms=(), tc=str):
    """Nothing covers a moment when the speaker shows an object to the camera (montre.py): no scene, no overlay, no b-roll,
    no zoom (which would crop the object). Case seen in review: a screen video hid the camera the speaker was holding
    up close to the lens. Returns the faults."""
    el = [(x["_start"], fin(x), x["id"]) for x in SEG if x["component"] != "volet"] + \
         [(a, a + d, f"b-roll {i}") for i, _, a, d in BROLLS] + [(z["start"], z["start"] + z["out"] - z["in"], "zoom") for z in zooms]
    return [f"{tc(a)} {n} covers the moment the speaker shows an object ({tc(m0)} to {tc(m1)})"
            for a, b, n in el for m0, m1 in montre if a < m1 - 0.05 and b > m0 + 0.05]


def retro(s):
    """Scene in a retro look (neon, Minitel): never the design system's curtain over it (mixing looks is ugly:
    keep the base look's transition on base scenes). `mx-*` scenes (green terminal) and any element with the "matrix"
    theme count as retro too."""
    return (s.get("component") in RETRO or str(s.get("component", "")).startswith("mx-")
            or (s.get("data") or {}).get("theme") in ("neon", "minitel", "matrix"))


def volets(SEG, WINDOWS, BROLLS, END, scene, son, fps=29.97):
    """A curtain masks the passage between the talking-head shot and a full-screen block (scenes, demos and b-rolls that
    follow each other form a single block); the cut falls on its middle frame. No curtain (hard cut):
    - on a b-roll: a direct switch is less busy;
    - on a scene in a retro look (see `retro`): do not mix looks;
    - on a block shorter than BLOC_COURT s, nor between two blocks less than ALLER_RETOUR s apart: too many
      curtains feel a bit much (the b-roll and look rules alone cut the count by about half, this one trims more).
    A full-screen scene that follows another without a camera return turns the page (except cards, which have
    their own entrance). Returns the blocks."""
    spans = sorted([(x["_start"], fin(x), "retro" if retro(x) else "ds") for x in SEG if plein(x)]
                   + [(a, b, "demo") for _, a, b in WINDOWS] + [(a, a + d, "broll") for _, _, a, d in BROLLS])
    blocks = []   # [start, end, kind of first element, kind of last]
    # inside a block, a gap between two full-screen elements shows the face (1 frame, e.g. a page
    # ending 0.05 s before the next capture): report it here, before the render; the "flash" check
    # only sees it after the preview
    for a, b, k in spans:
        if blocks and 0.5 / fps < a - blocks[-1][1] <= RETOUR_MIN:
            print(f"  !! gap of {a - blocks[-1][1]:.2f} s at {a:.2f} s in a full-screen block: face visible")
        if blocks and a - blocks[-1][1] <= RETOUR_MIN:
            if b >= blocks[-1][1]:
                blocks[-1][1], blocks[-1][3] = b, k
        else:
            blocks.append([a, b, k, k])
    half = 7 / fps
    for i, (a, b, k0, k1) in enumerate(blocks):
        if b - a < BLOC_COURT:
            continue
        proche_avant = i > 0 and a - blocks[i - 1][1] < ALLER_RETOUR
        proche_apres = i + 1 < len(blocks) and blocks[i + 1][0] - b < ALLER_RETOUR
        if a > 1.0 and k0 in ("ds", "demo") and not proche_avant:
            scene("volet-in", "volet", a - half, a - half + 0.5, {"dir": 1}, alpha=True, sfx=son.volet_in(a - half))
        if b < END - 1.0 and k1 in ("ds", "demo") and not proche_apres:
            scene("volet-out", "volet", b - half, b - half + 0.5, {"dir": -1}, alpha=True, sfx=son.volet_out(b - half))
    SEG.sort(key=lambda s: s["_start"])
    opaque = [s for s in SEG if plein(s)]
    for s in opaque:
        if s["component"] in MIN_PLEIN:
            continue
        if not any(abs(s["_start"] - a) < 0.05 for a, *_ in blocks):
            # the page sound of the scene's palette (read from its own sounds): a bare "page.wav" sounded paper in
            # the middle of a terminal scene; the default timbres keep the paper page, as in son.py
            dossiers = {f["file"].split("/")[0] for f in s["sfx"] if "/" in f["file"]} - {getattr(son, "TIMBRES", "")}
            d = next((x for x in sorted(dossiers) if (son.SFX / x / "page.wav").exists()), None)
            s["sfx"].insert(0, {"file": f"{d}/page.wav" if d else "page.wav", "at": 0.0, "gainDb": 0.0})
    for a, b in zip(opaque, opaque[1:]):
        if fin(a) > b["_start"] + 0.02:
            print(f"  !! overlap {a['id']} / {b['id']}")
    return [(a, b) for a, b, *_ in blocks]


# --- plan checks, before any render ----------------------------------------------------------
AVANCE_MAX_SCENE = 0.8   # a scene starts 0.8 s at most before its first element


def avant_le_mot(SEG, tc, sauf=()):
    """A scene does not show long before what it illustrates: its first instant (`cues[0]`) falls
    in the first AVANCE_MAX_SCENE seconds. Showing a date as text long before saying it is slow and dull:
    the viewer already knows what is coming because it is written.
    Cards (MIN_PLEIN, brought forward on purpose by the hold) and curtains do not count. Returns the faults."""
    out = []
    for s in SEG:
        if s["component"] in MIN_PLEIN or s["component"] == "volet" or s.get("id") in sauf:
            continue
        c = [x for x in s.get("cues") or [] if x is not None]
        if c and min(c) > AVANCE_MAX_SCENE + 0.01:
            out.append(f"{tc(s['_start'])} {s['id']}: shown {min(c):.1f} s before its first word")
    return out


def cites(words, SEG, BROLLS, attendus, tc, fenetre=6.0, voix_seule=()):
    """Show the work being talked about: each name or work cited in `attendus` ({transcript phrase:
    reason if nothing to show, or None}) must have a scene (or a b-roll) that starts within `fenetre` s
    of the word, unless a reason is written ("the speaker holds it to the camera", "intro: voice only"). Typical fault:
    a photographer is cited, nothing on screen. `voix_seule`: ranges (start, end) where nothing is laid on purpose (intro,
    conclusion). Proper names in the transcript (capital letter outside a sentence start) missing from `attendus`
    are listed too: the plan must settle each one. Returns the faults."""
    import re as _re
    import unicodedata as _u
    norm = lambda x: _re.sub(r"[^a-z0-9]+", " ", _u.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()).split()
    toks = [(t, i) for i, w in enumerate(words) for t in norm(w["word"])]
    debuts = sorted([s["_start"] for s in SEG if s["component"] != "volet"] + [a for _, _, a, _ in BROLLS])
    out = []
    for phrase, raison in attendus.items():
        p = norm(phrase)
        trouve = [words[toks[k][1]]["start"] for k in range(len(toks) - len(p) + 1)
                  if all(toks[k + j][0] == p[j] for j in range(len(p)))]
        if not trouve:
            out.append(f"\"{phrase}\" not found in the transcript")
            continue
        for t in trouve:
            if any(a <= t <= b for a, b in voix_seule):
                continue
            if raison is None and not any(t - fenetre <= d <= t + fenetre for d in debuts):
                out.append(f"{tc(t)} \"{phrase}\" cited, nothing on screen (show the work, or write why not)")
    connus = {x for ph in attendus for x in norm(ph)}
    MOTS = {"je", "j", "et", "le", "la", "les", "un", "une", "des", "c", "ce", "ca", "donc", "alors", "mais", "vous", "on", "il",  # fr-ok: French stop words (data)
            "ils", "si", "voila", "bref", "question", "ici", "lui", "moi", "salut", "oui", "non", "pourquoi", "ensuite", "genre",
            "promis", "parce", "typiquement", "liste", "du", "de", "en", "au", "a", "dans", "tout", "sur", "ne", "n", "l", "d", "qu", "que"}  # fr-ok
    courants = {t for w in words if w["word"].strip()[:1].islower() for t in norm(w["word"])}   # written in lowercase elsewhere: common word
    for i, w in enumerate(words[1:], 1):
        txt = w["word"].strip()
        prev = words[i - 1]["word"].strip()
        if txt[:1].isupper() and prev[-1:] not in ".?!:" and not (set(norm(txt)) & (connus | MOTS | courants)):
            out.append(f"{tc(w['start'])} proper name? \"{txt}\": file it in the plan's cited list (shown, or a reason)")
    return out


def sobriete(SEG, BROLLS, tc):
    """Three checks from the review grid, all blocking:
    - CURTAIN ON B-ROLL: a curtain that touches a b-roll (with a b-roll, a direct switch is less busy);
    - SOUND ON B-ROLL: a sound effect that sounds during a b-roll (no sound signature on a b-roll);
    - DS CURTAIN ON RETRO LOOK: a design-system curtain at the edge of a neon or Minitel scene (mixing looks is ugly).
    BROLLS: the real b-rolls (without the page-flipping ones). Returns the faults."""
    out = []
    vol = [s for s in SEG if s["component"] == "volet"]
    rb = [s for s in SEG if s["component"] != "volet" and retro(s) and plein(s)]
    for v in vol:
        a, b = v["_start"], v["_start"] + v["durationSec"]
        for _, f, x, d in BROLLS:
            if a < x + d + 0.05 and b > x - 0.05:
                out.append(f"{tc(a)} CURTAIN ON B-ROLL: {v['id']} touches {f}")
        for s in rb:
            if a < fin(s) + 0.05 and b > s["_start"] - 0.05:
                out.append(f"{tc(a)} DS CURTAIN ON RETRO LOOK: {v['id']} at the edge of {s['id']} ({s['component']})")
    for s in SEG:
        for x in s.get("sfx") or []:
            t = s["_start"] + x["at"]
            for _, f, a, d in BROLLS:
                if a + 0.02 < t < a + d - 0.02:
                    out.append(f"{tc(t)} SOUND ON B-ROLL: {x['file']} ({s['id']}) during {f}")
    return out


def controles(SEG, BROLLS, words, CITES, tc, voix_seule=()):
    """All the plan's blocking checks (call after `volets()`): on the word, cited works shown, restraint."""
    return avant_le_mot(SEG, tc) + cites(words, SEG, BROLLS, CITES, tc, voix_seule=voix_seule) + sobriete(SEG, BROLLS, tc)


def _self_test():
    """Each check on a reference case that MUST fail, and on a sound case that must pass."""
    tc = lambda t: f"{t:.1f}"
    sc = lambda i, c, a, d, cues=(0.1,), sfx=(), data=None, alpha=False: {
        "type": "scene", "id": i, "component": c, "alpha": alpha, "durationSec": d, "cues": list(cues), "_start": a,
        "data": data or {}, "sfx": [{"file": f, "at": t, "gainDb": 0} for f, t in sfx]}
    w = lambda *m: [{"word": x, "start": t, "end": t + 0.3} for x, t in m]
    ok = True

    def attend(nom, fautes, doit):
        nonlocal ok
        bon = bool(fautes) == doit
        ok &= bon
        print(f"  {'OK ' if bon else '!! '}{nom}: {'fails' if fautes else 'passes'} ({'expected: fails' if doit else 'expected: passes'})")
    attend("text before the word (shown 3 s early)", avant_le_mot([sc("chiffres", "chiffres-retro", 10, 6, cues=(3.0,))], tc), True)
    attend("text on the word", avant_le_mot([sc("chiffres", "chiffres-retro", 10, 6, cues=(0.2,))], tc), False)
    mots = w(("Like", 1.0), ("Saul", 1.4), ("Leiter", 1.7), ("too", 2.0))
    attend("proper name cited with no visual", cites(mots, [], [], {"saul leiter": None}, tc), True)
    attend("proper name cited, shown", cites(mots, [sc("saul-leiter", "accrochage", 1.3, 5)], [], {"saul leiter": None}, tc), False)
    attend("proper name missing from the plan's list", cites(mots, [], [], {}, tc), True)
    br = [("05", "05_cafe.mp4", 20.0, 3.0)]
    attend("curtain on a b-roll", sobriete([sc("volet-in", "volet", 19.8, 0.5)], br, tc), True)
    attend("sound on a b-roll", sobriete([sc("gif", "gif", 18, 5, sfx=[("pose.wav", 3.0)], alpha=True)], br, tc), True)
    attend("b-roll on a hard cut, no sound", sobriete([sc("gif", "gif", 10, 5, sfx=[("pose.wav", 1.0)], alpha=True)], br, tc), False)
    attend("DS curtain at the edge of a Minitel scene", sobriete([sc("volet-in", "volet", 39.8, 0.5),
                                                               sc("chapitre-5", "titre-retro", 40, 4, data={"theme": "minitel"})], [], tc), True)
    attend("curtain at the edge of a DS scene", sobriete([sc("volet-in", "volet", 39.8, 0.5), sc("carte", "carte", 40, 4)], [], tc), False)
    # tenue() lengthens a scene so it can be read, never over the start of a b-roll (a scene once hid a b-roll,
    # garde_premiere HIDDEN)
    seg = [sc("locked", "mx-terminal", 20, 3)]
    tenue(seg, [], [("03", "03_pellicules.mp4", 25.0, 4.0)], 100, tc, lecture={"locked": 8})
    attend("scene lengthened for reading, stopped at the b-roll", [s for s in seg if s["_start"] + s["durationSec"] > 25.0 + 1e-6], False)
    return ok


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        print("habillage.py --self-test: each check on its reference case")
        sys.exit(0 if _self_test() else 1)
    print(__doc__)
