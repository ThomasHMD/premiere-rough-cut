#!/usr/bin/env python3
"""Build one Premiere sequence for a whole part of a voice-over (several modules), with the re-recorded
sentences (retakes) put back in their place.

The editor's request: one XML per part, with 1 minute of blank between modules, otherwise handling
them by hand is a nightmare. Each module keeps its rough cut (cuts_final.json from its work folder,
never modified here); a retake replaces a run of chunks of the clip (chunks.json, indexes as in
dossier.txt) with chunks from another recording.

    python3 assemble_xml.py <plan.json> <output.xml> [--brut]

plan.json:
{
  "nom": "Course part 1",                      # sequence name
  "blanc": 60,                                 # s of blank between two modules (not between two clips of a module)
  "modules": [
    {"titre": "1.2 - Module title", "script": "<script .md, for qc_assemblage.py>",
     "rushs": [{"work": "<work folder of the clip>", "audio": "<processed WAV, same length, optional>"}],
     "reprises": [{"nom": "Take B", "rush": 0, "remplace": [38, 40],
                   "source": "<work folder of the retakes>", "audio": "<processed WAV, optional>",
                   "morceaux": [0, 1]}],
     "bornes": [{"rush": 0, "de": 158.21, "a": 157.96, "pourquoi": "leftover word of the abandoned take at the edge"}]}
  ]
}

- "audio": the sound the clips play (voice processed beforehand, same number of samples as
  the raw clip, so same instants); --brut: the raw clips (meta.json).
- A retake removes from the clip everything from the start of chunk remplace[0] to the end of
  remplace[1] (chunks already cut included) and puts the chosen chunks of the source in their place,
  in order; chunks that follow each other in the source keep their pause (minus the silences of the
  source's cuts_silence.json), a jump (abandoned take in the middle) leaves PAD_FIN + PAD_DEBUT of air
  taken from the silence of the source, never a digital blank.
- The air around a retake is the clip's: the cut falls in the pause (at most PAD_*, at most half the
  pause), the retake brings as much of its own pause.
- Retakes on track A2, clip on A1: visible at a glance. One marker per module (start) and per retake
  (name, text of the source).
- Joins of the original rough cut under AIR_MIN: opened up in the clip's silence (aerer); --sans-aerer
  to keep them as they are. Level of each retake brought to that of the neighboring clip (gains,
  "Audio Levels" filter of the clip, which Premiere reads as its volume).
Also writes <output>.segments.json (each clip, its source, its instants) for qc_assemblage.py.
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
from build_premiere_xml import add_rate, make_clipitem, make_file_element  # noqa: E402
import raccords  # noqa: E402

FPS = 30            # voice-over WAVs: meta.json fps 30/1 (timebase 30, ntsc FALSE)
PAD_DEBUT = 0.20    # s of air taken before a chunk (= pad-in of silence_cuts.py)
PAD_FIN = 0.25      # s of air taken after a chunk (= pad-out of silence_cuts.py)
MINI = 0.07         # s: below this, no clip (Premiere refuses in == out)
AIR_MIN = 0.30      # s: a tighter join needs opening up (montage_qc.py --min-air)
AIR_VISE = 0.55     # s: target air when opening up (apply_takes.AIR_TOTAL)
MARGE = 0.05        # s left between the air taken and the removed speech
ILOT_MAX = 0.30     # s: a bit of word left at the edge of a clip (beyond this, it is a kept word)
ILOT_BLANC = 0.10   # s: silence that separates the islet from the rest of the clip
RECUL = 0.16       # s: window to look for the dip when a clip edge falls inside speech
SANS_AIR = ("begaiement", "correction")   # removed mid-sentence: the flow carries on over them


def fr(t):
    return int(round(t * FPS))


def coupes(W, nom):
    f = Path(W) / nom
    if not f.exists():
        return []
    d = json.loads(f.read_text())
    return sorted((c["start"], c["end"]) for c in (d["cuts"] if isinstance(d, dict) else d) if c["decision"] == "disable")


def complement(dis, a, b):
    """[a, b] minus the intervals in dis."""
    out, t = [], a
    for s, e in dis:
        if e <= t or s >= b:
            continue
        if s - t > MINI:
            out.append((t, s))
        t = max(t, e)
    if b - t > MINI:
        out.append((t, b))
    return out


def bords(ch, i, j):
    """Start and end of the run of chunks i..j, with the air taken from the neighboring pauses."""
    s, e = ch[i][0], ch[j][1]
    av = s - ch[i - 1][1] if i > 0 else PAD_DEBUT * 2
    ap = ch[j + 1][0] - e if j + 1 < len(ch) else PAD_FIN * 2
    return s - min(PAD_DEBUT, av / 2), e + min(PAD_FIN, ap / 2)


def suites(idx):
    """[0, 1, 5, 6, 8] -> [(0, 1), (5, 6), (8, 8)]"""
    out = []
    for k in sorted(idx):
        if out and k == out[-1][1] + 1:
            out[-1][1] = k
        else:
            out.append([k, k])
    return [tuple(x) for x in out]


def plan_segments(plan, brut=False):
    """[{module, piste, source, debut, fin, nom, reprise?}] in order, and the module starts (s)."""
    segs = []
    for m in plan["modules"]:
        for k, r in enumerate(m["rushs"]):
            W = Path(r["work"])
            meta = json.loads((W / "meta.json").read_text())
            ch = json.loads((W / "chunks.json").read_text())
            src = meta["rush_path"] if brut or not r.get("audio") else r["audio"]
            dur = meta["duration_seconds"]
            garde = complement(coupes(W, "cuts_final.json"), 0.0, dur)
            # boundary set by hand (seen at QC, checked by ear): {"rush", "de", "a", "pourquoi"}
            for bn in m.get("bornes", []):
                if bn.get("rush", 0) != k:
                    continue
                touche = False
                for n, (s, e) in enumerate(garde):
                    if abs(e - bn["de"]) < 0.02:
                        garde[n], touche = (s, bn["a"]), True
                    elif abs(s - bn["de"]) < 0.02:
                        garde[n], touche = (bn["a"], e), True
                if not touche:
                    sys.exit(f"ERROR: boundary {bn['de']} not found in {W.name}")
            reps = sorted((p for p in m.get("reprises", []) if p.get("rush", 0) == k), key=lambda p: p["remplace"][0])
            fenetres = []
            for p in reps:
                a, b = bords(ch, *p["remplace"])
                if fenetres and a < fenetres[-1][1]:
                    sys.exit(f"ERROR: overlapping retakes in {W.name} ({p['nom']})")
                fenetres.append((a, b, p))
            t = 0.0
            for a, b, p in fenetres + [(dur, dur, None)]:
                for s, e in garde:
                    s2, e2 = max(s, t), min(e, a)
                    if e2 - s2 > MINI:
                        segs.append({"module": m["titre"], "piste": 1, "source": src, "debut": s2, "fin": e2,
                                     "brut": meta["rush_path"], "work": str(W)})
                if p is None:
                    break
                S = Path(p["source"])
                smeta = json.loads((S / "meta.json").read_text())
                sch = json.loads((S / "chunks.json").read_text())
                ssrc = smeta["rush_path"] if brut or not p.get("audio") else p["audio"]
                sdis = coupes(S, "cuts_silence.json")
                texte = " ".join(sch[x][2] for x in sorted(p["morceaux"]))
                premier = True
                for x, y in suites(p["morceaux"]):
                    u, v = bords(sch, x, y)
                    for s, e in complement(sdis, u, v):
                        segs.append({"module": m["titre"], "piste": 2, "source": ssrc, "debut": s, "fin": e,
                                     "brut": smeta["rush_path"], "work": str(S), "reprise": p["nom"],
                                     "texte": texte if premier else None,
                                     "remplace": p["remplace"], "fenetre": [round(a, 3), round(b, 3)]})
                        premier = False
                t = b
    return segs


_masques = {}


def masque_source(path):
    """(speech mask, rms) of the whole file, 10 ms windows (raccords.py)."""
    if path not in _masques:
        import soundfile as sf
        y, sr = sf.read(path, dtype="float32", always_2d=True)
        r = raccords.rms(y[:, 0], sr)
        _masques[path] = (raccords.masque(r), r, y[:, 0], sr)
    return _masques[path]


def _blanc(par, t, sens, borne):
    """Continuous blank from instant t going backward (sens -1) or forward (+1), without passing borne."""
    k, n = int(round(t / raccords.HOP)), 0
    while True:
        j = k - 1 - n if sens < 0 else k + n
        if j < 0 or j >= len(par) or par[j]:
            break
        if (sens < 0 and j * raccords.HOP < borne) or (sens > 0 and (j + 1) * raccords.HOP > borne):
            break
        n += 1
    return n * raccords.HOP


def _creux(y, sr, t0, t1):
    """Instant of the energy dip (5 ms windows) between t0 and t1: the boundary between two words."""
    import numpy as np
    h = int(sr * 0.005)
    i0, i1 = int(t0 * sr), int(t1 * sr)
    n = (i1 - i0) // h
    if n < 1:
        return t0
    x = y[i0: i0 + n * h].reshape(n, h)
    k = int(np.argmin((x ** 2).mean(axis=1)))
    return (i0 + k * h + h / 2) / sr


def _ilot(par, t, sens, maxi=ILOT_MAX, blanc=ILOT_BLANC):
    """An islet of speech of at most maxi s stuck to the edge t of the clip (inner side), separated from the
    rest of the clip by at least blanc s of silence, AND whose speech continues on the other side of the cut
    (within 0.05 s): it is a piece of a word from the removed take. Returns (new edge, islet duration) or None.
    sens -1: end of clip (the islet ends at t); +1: start of clip (it starts at t)."""
    H = raccords.HOP
    k = int(round(t / H))
    n = len(par)
    dehors = range(k, min(n, k + 10)) if sens < 0 else range(max(0, k - 10), k)
    if not any(par[j] for j in dehors):
        return None
    pas = -1 if sens < 0 else 1
    j = k - 1 if sens < 0 else k
    # tolerance of 10 windows at the edge: the dip of the cut itself, or the closure of the cut
    # word ("Par|ty": 0.10 s of silence between "Par" and "ty")
    for _ in range(10):
        if 0 <= j < n and not par[j]:
            j += pas
    debut = j
    while 0 <= j < n and par[j]:
        j += pas
    duree = abs(j - debut) * H
    if duree < 0.05 or duree > maxi:
        return None
    b = j
    while 0 <= j < n and not par[j]:
        j += pas
    sil = abs(j - b) * H
    if sil < blanc:
        return None
    if sens < 0:   # blank = windows j+1 .. b; the kept speech ends at (j+1)*H
        nouveau = (j + 1) * H + min(PAD_FIN, sil / 2)
    else:          # blank = windows b .. j-1; the kept speech resumes at j*H
        nouveau = j * H - min(PAD_DEBUT, sil / 2)
    return round(nouveau, 3), round(duree, 2)


def aerer(segs):
    """Joins of the original rough cut, based on the clip's energy.

    1. Edge inside speech: a clip that stops while the clip is still speaking (end of word eaten:
       "artis..." for "artists", "...made for th...", whisper's word ends fall early) ends at the energy
       dip of the next RECUL s; a clip that starts mid-speech starts at the dip of the preceding RECUL s.
    2. Air: under AIR_MIN, we reopen air taken from the clip's silence, up to AIR_VISE, first before the
       attack of the next clip, then after the end of the previous clip, never inside the removed speech
       (MARGE).
    A stumble or a correction (SANS_AIR) is removed mid-sentence: left alone.
    Returns the list of joins touched."""
    faits = []
    for L, R in zip(segs, segs[1:]):
        if L["module"] != R["module"] or L["piste"] != 1 or R["piste"] != 1 or L["source"] != R["source"] \
                or R["debut"] - L["fin"] < 0.02:
            continue
        typ = next((c.get("type", "") for c in json.loads((Path(L["work"]) / "cuts_final.json").read_text())["cuts"]
                    if c["decision"] == "disable" and abs(c["start"] - L["fin"]) < 0.03), "")
        if typ in SANS_AIR:
            continue
        par, _, y, sr = masque_source(L["source"])
        H = raccords.HOP
        bord = []
        # 0. islet at the edge: a piece of a word from the removed take can stay at the edge of the clip
        #    (a "Par..." left over, a cut set on a word start that whisper placed too late). Nothing is
        #    touched on its own: voice processing mutes some closures ("sta|ble"), an islet can be the end
        #    of a kept word. Reported, to be listened to (hear.py), then a boundary is set in the plan if
        #    it is a leftover.
        ecouter = []
        for cote, t, sens in (("end", L["fin"], -1), ("start", R["debut"], +1)):
            il = _ilot(par, t, sens)
            if il is not None:
                ecouter.append(f"islet of {il[1]:.2f} s at the {cote} of the clip at {t:.2f} (proposed edge {il[0]:.2f})")
        if par[min(len(par) - 1, int(L["fin"] / H) - 1)]:
            t = _creux(y, sr, L["fin"], min(L["fin"] + RECUL, R["debut"]))
            bord.append(f"end {L['fin']:.2f} -> {t:.2f}")
            L["fin"] = t
        if par[min(len(par) - 1, int(R["debut"] / H))]:
            t = _creux(y, sr, max(R["debut"] - RECUL, L["fin"]), R["debut"])
            bord.append(f"start {R['debut']:.2f} -> {t:.2f}")
            R["debut"] = t
        a_in = _blanc(par, L["fin"], -1, L["debut"])
        b_in = _blanc(par, R["debut"], +1, R["fin"])
        avant = a_in + b_in
        pris = pris2 = 0.0
        if avant < AIR_MIN:
            manque = AIR_VISE - avant
            dispo = max(0.0, _blanc(par, R["debut"], -1, L["fin"]) - MARGE)
            pris = min(manque, dispo)
            R["debut"] -= pris
            manque -= pris
            dispo = max(0.0, _blanc(par, L["fin"], +1, R["debut"]) - MARGE)
            pris2 = min(manque, dispo)
            L["fin"] += pris2
        if bord or pris or pris2 or ecouter:
            faits.append({"module": L["module"], "raw": round(R["debut"], 2), "type": typ, "bord": bord, "ecouter": ecouter,
                          "avant": round(avant, 2), "apres": round(avant + pris + pris2, 2)})
    return faits


def gains(segs, plafond=-1.0, seuil=0.5, fenetre=10.0):
    """Gain of each retake (other session, other voice of the moment) so that its speech matches that of
    the clip just before and just after (fenetre s on each side, dB RMS of the speech windows). Under
    seuil dB: nothing. A positive gain is capped so that the peak stays under plafond dBFS."""
    import numpy as np

    def niveau(spans):
        v = []
        for src, a, b in spans:
            par, _, y, sr = masque_source(src)
            hop = int(sr * raccords.HOP)
            v += [y[k * hop:(k + 1) * hop] for k in range(int(a / raccords.HOP), min(len(par), int(b / raccords.HOP))) if par[k]]
        if not v:
            return None, None
        x = np.concatenate(v)
        return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9), 20 * np.log10(np.abs(x).max() + 1e-9)

    out = []
    k = 0
    while k < len(segs):
        if not segs[k].get("reprise"):
            k += 1
            continue
        j = k
        while j + 1 < len(segs) and segs[j + 1].get("reprise") == segs[k]["reprise"] and segs[j + 1]["module"] == segs[k]["module"]:
            j += 1
        voisins = []
        for pas, debut in ((-1, k - 1), (1, j + 1)):
            tot, i = 0.0, debut
            while 0 <= i < len(segs) and tot < fenetre and not segs[i].get("reprise") and segs[i]["module"] == segs[k]["module"]:
                voisins.append((segs[i]["source"], segs[i]["debut"], segs[i]["fin"]))
                tot += segs[i]["fin"] - segs[i]["debut"]
                i += pas
        nr, crete = niveau([(s["source"], s["debut"], s["fin"]) for s in segs[k:j + 1]])
        nv, _ = niveau(voisins)
        g = 0.0 if nr is None or nv is None else float(nv - nr)
        if abs(g) < seuil:
            g = 0.0
        if g > 0 and crete is not None:
            g = float(min(g, plafond - crete))
        for s in segs[k:j + 1]:
            s["gain_db"] = round(g, 1)
        out.append((segs[k]["module"], segs[k]["reprise"], round(g, 1)))
        k = j + 1
    return out


def filtre_niveau(clip, gain_db):
    """Clip volume ("Audio Levels" of the Final Cut 7 XML, which Premiere imports as Volume > Level)."""
    f = ET.SubElement(clip, "filter")
    e = ET.SubElement(f, "effect")
    for k, v in (("name", "Audio Levels"), ("effectid", "audiolevels"), ("effectcategory", "audiolevels"),
                 ("effecttype", "audiolevels"), ("mediatype", "audio")):
        ET.SubElement(e, k).text = v
    p = ET.SubElement(e, "parameter", {"authoringApp": "PremierePro"})
    for k, v in (("parameterid", "level"), ("name", "Level"), ("valuemin", "0"), ("valuemax", "3.98109"),
                 ("value", f"{10 ** (gain_db / 20):.6f}")):
        ET.SubElement(p, k).text = v


def ecrire_xml(plan, segs, out):
    blanc = fr(plan.get("blanc", 60))
    xmeml = ET.Element("xmeml", {"version": "5"})
    seq = ET.SubElement(xmeml, "sequence", {"id": plan["nom"]})
    ET.SubElement(seq, "name").text = plan["nom"]
    dur_el = ET.SubElement(seq, "duration")
    add_rate(seq, FPS, "FALSE")
    ET.SubElement(seq, "in").text = "-1"
    ET.SubElement(seq, "out").text = "-1"
    tc = ET.SubElement(seq, "timecode")
    add_rate(tc, FPS, "FALSE")
    ET.SubElement(tc, "string").text = "00:00:00:00"
    ET.SubElement(tc, "frame").text = "0"
    ET.SubElement(tc, "displayformat").text = "NDF"
    media = ET.SubElement(seq, "media")
    vid = ET.SubElement(media, "video")
    vsc = ET.SubElement(ET.SubElement(vid, "format"), "samplecharacteristics")
    add_rate(vsc, FPS, "FALSE")
    for k, v in (("width", "1920"), ("height", "1080"), ("anamorphic", "FALSE"),
                 ("pixelaspectratio", "square"), ("fielddominance", "none")):
        ET.SubElement(vsc, k).text = v
    vt = ET.SubElement(vid, "track")
    ET.SubElement(vt, "enabled").text = "TRUE"
    ET.SubElement(vt, "locked").text = "FALSE"
    aud = ET.SubElement(media, "audio")
    asc = ET.SubElement(ET.SubElement(aud, "format"), "samplecharacteristics")
    ET.SubElement(asc, "depth").text = "16"
    ET.SubElement(asc, "samplerate").text = "48000"
    pistes = {1: ET.SubElement(aud, "track"), 2: ET.SubElement(aud, "track")}

    fichiers = {}       # path -> (id, meta); the full <file> on first use only
    pos, module, n_mod, marqueurs = 0, None, 0, []
    for i, sg in enumerate(segs):
        if sg["module"] != module:
            if module is not None:
                pos += blanc
            module = sg["module"]
            n_mod += 1
            marqueurs.append((pos, pos + 1, module, "Module start"))
        in_f, out_f = fr(sg["debut"]), fr(sg["fin"])
        if out_f - in_f < 1:
            continue
        src = sg["source"]
        if src not in fichiers:
            meta = json.loads((Path(sg["work"]) / "meta.json").read_text())
            fichiers[src] = (f"file-{len(fichiers) + 1}", meta, True)
        fid, meta, plein = fichiers[src]
        fichiers[src] = (fid, meta, False)
        fel = make_file_element(fid, src, fr(meta["duration_seconds"]), FPS, "FALSE", None, None,
                                meta["audio_channels"], meta["audio_rate"], full=plein)
        rep = sg.get("reprise")
        etiquette = sg["module"].split(" - ")[0]
        nom = f"{etiquette} retake {rep}" if rep else f"{etiquette} {i:04d}"
        clip = make_clipitem(f"clipitem-{i:04d}", nom, fel, in_f, out_f, pos, pos + out_f - in_f,
                             True, FPS, "FALSE", "audio", audio_track_index=1)
        if sg.get("gain_db"):
            filtre_niveau(clip, sg["gain_db"])
        pistes[sg["piste"]].append(clip)
        sg["seq_debut"], sg["seq_fin"], sg["in_f"], sg["out_f"] = pos, pos + out_f - in_f, in_f, out_f
        if rep and sg.get("texte"):
            marqueurs.append((pos, pos + out_f - in_f, f"Retake: {rep}", sg["texte"]))
        pos += out_f - in_f
    for t in pistes.values():
        ET.SubElement(t, "enabled").text = "TRUE"
        ET.SubElement(t, "locked").text = "FALSE"
    dur_el.text = str(pos)
    for a, b, nom, com in marqueurs:
        mk = ET.SubElement(seq, "marker")
        ET.SubElement(mk, "comment").text = com
        ET.SubElement(mk, "name").text = nom
        ET.SubElement(mk, "in").text = str(a)
        ET.SubElement(mk, "out").text = str(b)

    # self-check (same refusals as Premiere): zero duration, end-start != out-in, overlap
    err, occupe = [], []
    for t in pistes.values():
        prev = 0
        for c in t.findall("clipitem"):
            i_f, o_f, s_f, e_f = (int(c.find(x).text) for x in ("in", "out", "start", "end"))
            if o_f - i_f < 1 or (o_f - i_f) != (e_f - s_f) or s_f < prev:
                err.append(f"{c.find('name').text}: in={i_f} out={o_f} start={s_f} end={e_f}")
            prev = e_f
            occupe.append((s_f, e_f, c.find("name").text))
    occupe.sort()
    for (s1, e1, n1), (s2, e2, n2) in zip(occupe, occupe[1:]):
        if s2 < e1:
            err.append(f"overlap {n1} / {n2}")
    if err:
        print("ERROR: invalid sequence, XML not written:", *err[:10], sep="\n  ", file=sys.stderr)
        sys.exit(1)
    jolie = minidom.parseString(ET.tostring(xmeml, encoding="utf-8")).toprettyxml(indent="  ", encoding="UTF-8").decode()
    lignes = [l for l in jolie.splitlines() if l.strip()]
    lignes.insert(1, "<!DOCTYPE xmeml>")
    Path(out).write_text("\n".join(lignes))
    return pos, n_mod, len(marqueurs)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("plan")
    ap.add_argument("sortie")
    ap.add_argument("--brut", action="store_true", help="clips play the raw clips, not the processed voices")
    ap.add_argument("--sans-aerer", action="store_true", help="keep the joins of the original rough cut as they are")
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    segs = plan_segments(plan, a.brut)
    faits = [] if a.sans_aerer else aerer(segs)
    gs = gains(segs)
    pos, n_mod, n_mk = ecrire_xml(plan, segs, a.sortie)
    side = Path(a.plan).with_name(Path(a.sortie).stem + ".segments.json")
    side.write_text(json.dumps({"plan": a.plan, "xml": a.sortie, "fps": FPS, "blanc": plan.get("blanc", 60),
                                "aeres": faits, "gains": gs, "segments": segs}, ensure_ascii=False, indent=0))
    for f in faits:
        print(f"  join {f['module'][:4]} raw {f['raw']:.2f} ({f['type']}) air {f['avant']:.2f} -> {f['apres']:.2f} s"
              + (f"  edge inside speech: {', '.join(f['bord'])}" if f["bord"] else "")
              + (f"  WARNING, LISTEN: {', '.join(f['ecouter'])}" if f["ecouter"] else ""))
    for m, r, g in gs:
        print(f"  level: {m[:4]} retake {r} {g:+.1f} dB")
    n_rep = len({(s["module"], s["reprise"]) for s in segs if s.get("reprise")})
    print(f"{Path(a.sortie).name}: sequence '{plan['nom']}', {n_mod} modules, {len(segs)} clips "
          f"including {sum(1 for s in segs if s.get('reprise'))} from retakes ({n_rep} retakes), "
          f"{pos / FPS / 60:.2f} min with the blanks, {n_mk} markers; segments: {side}")


if __name__ == "__main__":
    main()
