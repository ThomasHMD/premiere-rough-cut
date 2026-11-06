#!/usr/bin/env python3
"""Vocabulary of the default sound palette: which sound for which gesture.

A video's plan never picks a file or a volume: it names a GESTURE (`son.liste`, `son.chapitre`,
`son.tampon`...) and gets back the list `(file, time, dB)` to pass in a scene's `sfx` key. The
synth recipes are in make-sfx.py, the art direction in reference/sound-palette.md.

    import sys; sys.path.insert(0, "<skill>/scripts"); import son
    scene(..., sfx=son.liste([t1, t2, t3]) + son.tampon(t4))

Default timbres: a shot that sets no palette takes the sounds of the public/sfx/ subfolder named
by public/sfx/defaut.json (real recordings, falling back to the original palette for a missing
sound); `son.palette(...)` removes them. See the "Default timbres" block further down.

Files already come out at the right level (reference voice: make-sfx.py, VOIX_REF). Each
function's `d` is an offset in dB from that level; `son.DECALAGE` shifts a whole video at once
(final voice louder or quieter than the reference).

Several palettes are possible, same gestures, same levels, same scale: a palette = a subfolder
of public/sfx/ with the same file names (public/sfx/ itself = the default palette).
`son.palette("<subfolder>")` takes the sounds that follow from that subfolder; a sound it lacks
comes from the default palette (fallback). `son.palette("defaut")` goes back to public/sfx/.
The chapter card then takes the arpeggio (arpege.wav) instead of the page turn. A palette made of
real recordings (sound library, home takes) goes there with scripts/palette-import.py.

Lists: `LISTES = "objets"` by default in this kit (one card set down per element, alternating
variants, no musical pitch); "notes": the scale climbs and the last element resolves. Chained
notes on a list are the sound most often rejected on listening. Affects `liste`, `vues` and
`cascade`.

Sound report: `releve(...)` writes the numbered, timestamped list of a video's sounds (what is on
screen, what is said, the file, the level), so the user can answer "remove: 3, 17 to 19".
Written by overlays/scripts/render-segments.py on every edit.
"""
import json
from pathlib import Path

SFX = Path(__file__).resolve().parent.parent / "public" / "sfx"
PALETTE = "defaut"   # the palette the sounds come from (subfolder of public/sfx/, "defaut" = public/sfx/)
DOSSIER = ""         # its folder under public/sfx/ ("" for the default palette)
GAMME = ["C4", "D4", "E4", "G4", "A4", "C5", "D5", "E5", "G5", "A5", "C6", "D6", "E6"]
LISTES = "objets"    # "objets": one card set down per element; "notes": the scale climbs over a list (see the header)
DECALAGE = 0.0
# Sync: every sound lands 2 frames (67 ms) AFTER the visual moment it is given. A sound that is
# early is noticed from 45 ms, a late one only from 125 ms (ITU BT.1359); placed exactly on the
# first visible frame, sounds seem "slightly early" on listening.
CALAGE = 2 / 30

# Lists climb the scale and end on a stable degree (G or C).
_LISTES = {
    1: ["E5"],
    2: ["E5", "G5"],
    3: ["C5", "E5", "G5"],
    4: ["C5", "D5", "E5", "G5"],
    5: ["C5", "D5", "E5", "G5", "C6"],
    6: ["C5", "D5", "E5", "G5", "A5", "C6"],
}


def dossiers():
    """{palette: folder of its sounds under public/sfx/}: "defaut" (public/sfx/) and every subfolder that holds .wav files."""
    d = {"defaut": ""}
    d.update({p.name: p.name for p in sorted(SFX.iterdir()) if p.is_dir() and any(p.glob("*.wav"))} if SFX.is_dir() else {})
    return d


def palette(nom):
    """Sets the palette of the sounds that follow ("defaut" or a subfolder of public/sfx/). An
    unknown name is an error (never the default palette silently)."""
    global PALETTE, DOSSIER
    d = dossiers()
    if nom not in d:
        raise ValueError(f"unknown sound palette \"{nom}\" (available: {', '.join(d)})")
    PALETTE, DOSSIER = nom, d[nom]


def _s(fichier, at, d=0.0):
    f = fichier
    if DOSSIER and (SFX / DOSSIER / fichier).exists():   # the palette's sound; if missing from its folder, the default palette's (fallback)
        f = f"{DOSSIER}/{fichier}"
    elif TIMBRES and PALETTE is None and (SFX / TIMBRES / fichier).exists():   # no palette set: the default timbre; if missing from its folder, the paper one (fallback)
        f = f"{TIMBRES}/{fichier}"
    return (f, None if at is None else at + CALAGE, round(d + DECALAGE, 1))


# Default timbres. A shot that sets no palette (`palette()` never called) takes the timbres of the
# public/sfx/ subfolder named by the `timbres` key of public/sfx/defaut.json: real recordings
# (palette-import.py), at the same level as the sounds they replace; a sound that folder lacks stays
# the original palette's (fallback). Without defaut.json: the original palette, as before. Setting a
# palette (`palette(...)`) removes these timbres: PALETTE is then no longer None and gestures take
# the file names of the palette set. The chapter card keeps the page turn; the arpeggio stays with
# the palette that asks for it.
def _timbres_defaut():
    """The public/sfx/ subfolder of the default timbres (`timbres` key of public/sfx/defaut.json); "" without a file or folder (a name with no folder is reported)."""
    try:
        nom = str(json.loads((SFX / "defaut.json").read_text()).get("timbres", "")).strip()
    except (OSError, ValueError, AttributeError):
        return ""
    if nom and not any((SFX / nom).glob("*.wav")):
        print(f"  !! sound: default timbres \"{nom}\" (defaut.json) not found in {SFX}, using the original palette")
        return ""
    return nom


TIMBRES = _timbres_defaut()
if TIMBRES:
    PALETTE = None   # "no palette set": `palette()` sets one, and removes the default timbres


def _propre(sfx):
    return [x for x in sfx if x[1] is not None]


def _variantes(prefixe, defaut):
    """Number of variants <prefix>-1.wav, -2.wav... playable in the current palette (its own, or by
    fallback the default's): a palette imported with more takes cycles through all of them."""
    n = 0
    while (DOSSIER and (SFX / DOSSIER / f"{prefixe}-{n + 1}.wav").exists()) or (SFX / f"{prefixe}-{n + 1}.wav").exists():
        n += 1
    return n or defaut


# ---------------------------------------------------------------- keyboard

def note(at, nom="E5", d=0.0):
    """A single element appears."""
    return _propre([_s(f"note-{nom}.wav", at, d)])


def liste(instants, d=0.0, resout=True):
    """Elements arriving one by one: each rises a step, the last resolves (LISTES "notes");
    one card set down per element, alternating variants (LISTES "objets").
    A time of None (optional anchor missing) is ignored."""
    ts = [x for x in instants if x is not None]
    n = len(ts)
    if n == 0:
        return []
    if LISTES == "objets":
        return [x for k, t in enumerate(ts) for x in pose(t, k, d)]
    noms = _LISTES[n] if n in _LISTES else GAMME[:n] if n <= len(GAMME) else [GAMME[k % len(GAMME)] for k in range(n)]
    if not resout and n in (5,):
        noms = ["C5", "D5", "E5", "G5", "A5"]
    return [_s(f"note-{nom}.wav", t, d) for nom, t in zip(noms, ts)]


def cascade(at, n, pas=0.075, d=-4.0):
    """Many elements at once (tile grid): a quick run up the scale (LISTES "objets": the sheet
    slides, the last tile is set down)."""
    if LISTES == "objets":
        return [_s("glisse-in.wav", at, d), _s("pose-1.wav", at + max(0, n - 1) * pas, d)]
    debut = max(0, len(GAMME) - n - 2)
    return [_s(f"note-{GAMME[min(debut + k, len(GAMME) - 1)]}.wav", at + k * pas, d) for k in range(n)]


def valide(at, d=0.0):
    """Checkmark, answer, last word of a demo: C major."""
    return _propre([_s("accord.wav", at, d)])


def question(at, verrou=0.55, d=0.0):
    """Question card: the chord hangs in the air, the focus points lock."""
    return [_s("question.wav", at, d), _s("af.wav", at + verrou, d)]


def notif(at, d=0.0):
    return _propre([_s("notif.wav", at, d)])


def souci(at, d=0.0):
    """A problem, a snag: the note that drops."""
    return _propre([_s("sourd.wav", at, d)])


def chapitre(at, n, total, verrou=0.45, d=0.0):
    """"N of total" card: the sheet arrives, the bass sets down the C, the chapter note rises a
    step with each card and the last one lands on the high C."""
    suite = GAMME[: GAMME.index("C6") + 1][-total:] if total <= GAMME.index("C6") + 1 else GAMME
    nom = suite[min(n - 1, len(suite) - 1)]
    # a palette that has an arpeggio (arpege.wav) uses it instead of the page turn under the chapter card
    return [_s("arpege.wav" if DOSSIER and (SFX / DOSSIER / "arpege.wav").exists() else "page.wav", at, d), _s("basse.wav", at + 0.08, d - 2),
            _s(f"note-{nom}.wav", at + verrou, d + 1), _s("af.wav", at + verrou, d - 3)]


def signature(at, d=0.0):
    """Sound logo. One to three times per video: the promise, the ending."""
    return _propre([_s("signature.wav", at, d)])


# ---------------------------------------------------------------- camera body

def obturateur(at, d=0.0):
    return _propre([_s("obturateur.wav", at, d)])


def af(at, d=0.0):
    """Focus points: `at` = first frame where they switch to the accent color (focus acquired),
    never their appearance (AFBrackets: appearance + 16 frames)."""
    return _propre([_s("af.wav", at, d)])


def zoom(at, sens="in", d=0.0, duree=0.9):
    """The camera moves (standard curve): a light puff of air and the ring detents, placed on the
    START of the movement (the peak lands by itself at maximum speed, 0.11 s). "in" moves in on a
    detail, "out" pulls back to the full image, "pan" slides from one area to another of the same
    size (more discreet). `duree` 0.7: the zoom into a supporting shot."""
    f = "zoom-in-07.wav" if duree < 0.8 else "zoom-out.wav" if sens == "out" else "zoom-in.wav"
    return _propre([_s(f, at, d - (3 if sens == "pan" else 0))])


def appui(debut_fondu, d=0.0):
    """A supporting shot fading in (0.3 s): a very light pop on the G, where the image really
    becomes visible (2 frames after the start of the fade, 22% opacity)."""
    return _propre([_s("pop-G5.wav", debut_fondu + 2 / 30, d)])


def vues(debuts, d=-2.0):
    """The views of a contact sheet, one after another: one pop per view, the scale climbs and
    the last lands on the C (grammar section 2; LISTES "objets": one card set down per view).
    `debuts`: start of the reveal of each view."""
    if LISTES == "objets":
        return [x for k, t in enumerate(debuts) for x in pose(t + 2 / 30, k, d)]
    suite = ["C5", "D5", "E5", "G5", "A5", "C6"]
    n = len(debuts)
    noms = suite[-n:] if n <= len(suite) else [suite[round(k * 5 / (n - 1))] for k in range(n)]
    return [_s(f"pop-{nom}.wav", t + 2 / 30, d) for nom, t in zip(noms, debuts)]


def compteur(at, duree=0.9, d=0.0, chute=True):
    """A number ticking up: the ring detents, then the shutter when it lands."""
    f = "crans-court.wav" if duree < 0.7 else "crans.wav" if duree < 1.3 else "crans-long.wav"
    return [_s(f, at, d)] + ([_s("obturateur.wav", at + duree + 0.05, d - 3)] if chute else [])


def revele(at, d=0.0):
    """A reveal: cock the shutter (0.4 s before), release at `at`."""
    return [_s("armement.wav", max(0.0, at - 0.42), d), _s("obturateur.wav", at, d)]


def clic(at, d=0.0):
    return _propre([_s("clic.wav", at, d)])


def frappe(at, d=0.0):
    return _propre([_s("frappe.wav", at, d)])


# ---------------------------------------------------------------- paper

def tampon(at, k=0, d=0.0):
    """The stamp. `k` cycles through the palette's variants (three by default; never the same hit twice in a row)."""
    return _propre([_s(f"tampon-{k % _variantes('tampon', 3) + 1}.wav", at, d)])


def pose(at, k=0, d=0.0):
    """A label, a card, a bubble being set down. `k` cycles through the palette's variants (two by default)."""
    return _propre([_s(f"pose-{k % _variantes('pose', 2) + 1}.wav", at, d)])


def claque(at, k=0, fort=False, d=0.0):
    """A word that slams onto the screen: a label set down; the accented line takes the stamp."""
    return tampon(at, k, d - 3) if fort else pose(at, k, d + 2)


def carte(at, d=0.0):
    """A side card coming in: the sheet slides, then settles."""
    return [_s("glisse-in.wav", max(0.0, at - 0.2), d - 2), _s("pose-1.wav", at + 0.05, d - 2)]


def glisse(at, d=0.0):
    """Something slides within a scene (cards reshuffling, an envelope coming in)."""
    return _propre([_s("glisse-in.wav", at, d)])


def trait(at, pointille=False, d=0.0):
    """An arrow being drawn (18 frames): a swish that follows the stroke, a tick on the arrowhead.
    Placed on the frame where the arrow starts (round the time to the frame, like Remotion).
    Dotted ("what is not"), more discreet."""
    return _propre([_s("trait.wav", at, d - (3 if pointille else 0))])


def page(at, d=0.0):
    """Moving from one full-screen scene to the next, with no camera move back."""
    return _propre([_s("page.wav", at, d)])


def volet_in(at, d=0.0):
    return _propre([_s("glisse-in.wav", at, d)])


def volet_out(at, d=0.0):
    return _propre([_s("glisse-out.wav", at, d)])


# ---------------------------------------------------------------- sound report

def _roles():
    """{file as played ("pose-1.wav", "neon/pose-1.wav"): role} from each palette's palette.json."""
    r = {}
    for pj in [SFX / "palette.json", *sorted(SFX.glob("*/palette.json"))]:
        try:
            sons = json.loads(pj.read_text()).get("sons", {})
        except (OSError, ValueError):
            continue
        prefixe = "" if pj.parent == SFX else f"{pj.parent.name}/"
        r.update({prefixe + nom: m.get("role", "") for nom, m in sons.items()})
    for sous in sorted(p for p in SFX.iterdir() if p.is_dir() and not (p / "palette.json").exists()):   # a palette imported without palette.json plays the original palette's roles
        r.update({f"{sous.name}/{f.name}": r[f.name] for f in sorted(sous.glob("*.wav")) if f.name in r})
    return r


def _tc(t):
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def releve(entrees, mots=(), chemin=None, titre=""):
    """Numbered, timestamped list of a video's sounds, so the user can answer by number ("remove:
    3, 17 to 19") instead of "there are too many sound effects": Claude places the sounds without
    hearing them, only listening tells which ones land badly.
    `entrees`: (time, file, dB, what is on screen), time in seconds of the video as played (sync
    included); `mots`: [(word, start, end)] or [{"word", "start", "end"}]. With `chemin` (no
    extension), writes <chemin>.md (to read) and <chemin>.json (for a script), only if they
    change. Returns the lines."""
    ms = [(m["word"], m["start"], m["end"]) if isinstance(m, dict) else tuple(m[:3]) for m in mots]
    roles = _roles()
    lignes = []
    for n, (t, f, db, quoi) in enumerate(sorted((e for e in entrees if e[0] is not None), key=lambda e: e[0]), 1):
        dit = [w for w, a, b in ms if b >= t - 1.0 and a <= t + 1.0]
        lignes.append({"n": n, "t": round(t, 2), "tc": _tc(t), "image": quoi or "", "dit": " ".join(dit[:14]).strip(),
                       "son": f, "role": roles.get(f, ""), "db": db})
    if chemin:
        p = str(chemin)
        md = [f"# Sounds{': ' + titre if titre else ''} ({len(lignes)})", "",
              "Answer by number: \"remove: 3, 17 to 19\", \"12 lower\". Roles and levels: palette.json.", "",
              "| no. | time | on screen | what is said | sound | role | dB |", "|---|---|---|---|---|---|---|"]
        md += [f"| {x['n']} | {x['tc']} | {x['image'].replace('|', '/')} | {x['dit'].replace('|', '/')} | {x['son']} | {x['role']} | {x['db']:+g} |"
               for x in lignes]
        for ext, contenu in ((".md", "\n".join(md) + "\n"), (".json", json.dumps(lignes, ensure_ascii=False, indent=1))):
            f = Path(p + ext)
            if not f.exists() or f.read_text() != contenu:
                f.write_text(contenu)
    return lignes


# ---------------------------------------------------------------- safeguards

def controle(sfx, nom=""):
    """Warns when a scene is too chatty (more than 5 sounds per second outside a cascade) or when
    a file is missing. Returns the list unchanged."""
    ts = sorted(a for _, a, _ in sfx)
    for i, a in enumerate(ts):
        if sum(1 for b in ts[i:] if b < a + 1.0) > 11:
            print(f"  (sounds: {nom} very dense around {a:.1f} s)")
            break
    for f, _, _ in sfx:
        if not (SFX / f).exists():
            print(f"  !! missing sound: {f} (run scripts/make-sfx.py)")
    return sfx
