#!/usr/bin/env python3
"""On-screen text check, on the real layout of the scenes (in Remotion's browser).

    python3 controle-texte.py <rush>_animation-script.json [--only <id>] [--pas 10] [--brut]

Renders every scene of the script end to end in the "ControleTexte" composition (motion-design,
src/illustration/controle.tsx), one frame out of `--pas` (10 by default, 1/3 s), very small, and reads
the report each frame writes to the console. Blocking (exit code 1) on (tags kept as the composition writes them):
  DEBORDE    text goes outside the frame (e.g. a date running off the edge of a retro-screen card);
  MORD       text straddles the edge of a drawn shape (e.g. a caption on the slanted side of a trapezoid);
  CHEVAUCHE  two texts on top of each other;
  COUPE      text clipped by a mask (a screen, a card, the frame) for COUPE_MIN s or until the end
             of the scene;
  VIDE       a full-screen scene with no content at all (no text, no image besides the background) for more
             than 1 s (e.g. an empty neon background while a name is being said);
  LECTURE    a sentence (3 words or more) on screen for less time than it takes to read it, counted from its first
             letter (people read while it types): LECTURE_BASE + words / LECTURE_MOTS s, at least LECTURE_MIN, of which
             LECTURE_FIN fully typed (e.g. chapter card titles fully visible for only 0.3 to 1.1 s: "text not on
             screen long enough, there is no time to read it"). The duration each faulty scene would need goes
             in <base>_lecture.json, which the plan passes to habillage.tenue() (which stretches into free
             room): rerun the plan, then this check.
A defect is reported once per scene, with its first instant (seconds since the start of the scene).
Born from the editor's feedback: "text eaten by the drawing, you must not have checked".
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ATELIER = SKILL.parent / "motion-design"
VIDE_MIN = 1.0      # a full-screen scene may be empty for 1 s at most…
VIDE_ENTREE = 0.6   # … not counting its first frames (the background settling in)
LECTURE_MOTS = 3.0  # words read per second (subtitles: 3)…
LECTURE_BASE = 0.5  # … plus the time to rest the eyes on it
LECTURE_MIN = 1.5
LECTURE_FIN = 1.0   # the whole sentence stays at least 1 s after its last letter
LECTURE_MARGE = 0.15  # added to the wanted duration written in <base>_lecture.json
COUPE_MIN = 1.0     # text clipped for less time is an animated entrance (a chapter number rising behind its mask)


def scenes_de(script, only=None):
    return [{"id": s["id"], "component": s["component"], "data": s.get("data") or {}, "cues": s.get("cues") or [],
             "durationSec": s["durationSec"], "alpha": bool(s.get("alpha"))}
            for s in script["segments"] if s.get("type") == "scene" and s.get("component") != "volet"
            and (not only or only in s["id"])]


def empreinte(script) -> str:
    """What the check saw: the scenes of the script and the components' code (same files as the cache key
    of render-segments.py). `render-segments.py` refuses a script marked `controle_texte` whose signature
    (`<base>_controle-texte.json`, written here when everything passes) no longer matches: nothing is rendered unchecked."""
    h = hashlib.sha1(json.dumps(scenes_de(script), ensure_ascii=False, sort_keys=True).encode())
    src = ATELIER / "src"
    for f in sorted([src / "index.ts", src / "Root.tsx", *(src / "illustration").rglob("*")]):
        if f.is_file() and f.suffix in (".ts", ".tsx", ".css", ".json"):
            h.update(str(f.relative_to(src)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


def signature(script_path: Path) -> Path:
    return script_path.with_name(script_path.name.replace("_animation-script.json", "") + "_controle-texte.json")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    script = json.loads(Path(args[0]).read_text())
    only = args[args.index("--only") + 1] if "--only" in args else None
    pas = int(args[args.index("--pas") + 1]) if "--pas" in args else 10  # fr-ok: flag name
    fps = script.get("fps", 30)
    W, H = script.get("width", 1920), script.get("height", 1080)
    scenes = scenes_de(script, only)
    if not scenes:
        print("no scene")
        sys.exit(2)
    tmp = Path(tempfile.mkdtemp(prefix="controle-texte-"))
    props = tmp / "props.json"
    props.write_text(json.dumps({"fps": fps, "width": W, "height": H, "scenes": scenes}, ensure_ascii=False))
    cmd = ["npx", "remotion", "render", "src/index.ts", "ControleTexte", str(tmp / "controle.mp4"), f"--props={props}",
           f"--every-nth-frame={pas}", "--scale=0.25", "--log=verbose", "--concurrency=4"]
    r = subprocess.run(cmd, cwd=ATELIER, capture_output=True, text=True)
    sortie = r.stdout + r.stderr
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    releves = []
    for ligne in sortie.splitlines():
        m = re.search(r"CONTROLE (\{.*\})", ligne)
        if m:
            try:
                releves.append(json.loads(m.group(1)))
            except json.JSONDecodeError:
                pass
    if r.returncode != 0 or not releves:
        print(f"!! check render failed (code {r.returncode}, {len(releves)} readings)\n{sortie[-2500:]}")
        sys.exit(2)
    if "--brut" in args:   # readings as they are, to understand a defect that was not seen
        for x in releves:
            print(json.dumps(x, ensure_ascii=False))
    vus, fautes = set(), []
    par_scene = {}
    for x in sorted(releves, key=lambda x: (x["debut"], x["t"])):
        par_scene.setdefault((x["id"], x["debut"]), []).append(x)
        for f in x["fautes"]:
            cle = (x["id"], re.sub(r" \([^()]*\)$", "", re.sub(r"« (.{12}).*?»", r"« \1", f)))  # fr-ok: guillemets written by controle.tsx
            if cle not in vus:
                vus.add(cle)
                fautes.append(f"{x['id']} at {x['t']:.1f} s: {f}")
    durees = {s["id"]: s["durationSec"] for s in scenes}
    lecture = {}   # id: duration the scene would need for each sentence to be readable
    for (sid, debut), xs in par_scene.items():
        # reading time: each sentence, from its first whole frame to its last (a typed sentence is only whole
        # once typing is done)
        vu = {}
        for x in xs:
            for t in x.get("lus", []):
                vu.setdefault(t, [x["t"], x["t"]])[1] = x["t"]
        for t, (a, b) in vu.items():
            mots = len([m for m in t.split() if re.search(r"[A-Za-z\u00c0-\u00ff]", m)])
            if mots < 3 or any(u != t and u.startswith(t.rstrip()) for u in vu):   # start of a sentence still being typed
                continue
            besoin = max(LECTURE_MIN, LECTURE_BASE + mots / LECTURE_MOTS)
            fin_ = min(b + pas / fps, durees.get(sid, b + pas / fps))
            premiere = min([a] + [v[0] for u, v in vu.items() if len(u.strip()) >= 3 and t.startswith(u.rstrip())])
            manque = max(besoin - (fin_ - premiere), LECTURE_FIN - (fin_ - a))
            if manque > 0.05 and (sid, "LECTURE", t) not in vus:
                vus.add((sid, "LECTURE", t))
                # + LECTURE_MARGE: the reading only has one frame out of `pas`; without a margin, the wanted duration fell 0.1 s
                # short on the next round and the plan -> check loop ran forever
                lecture[sid] = max(lecture.get(sid, 0.0), round(durees.get(sid, 0.0) + manque + LECTURE_MARGE, 2))
                fautes.append(f"{sid} at {a:.1f} s: LECTURE « {t[:50]} » {fin_ - premiere:.1f} s on screen "  # fr-ok
                              f"(whole {fin_ - a:.1f} s) for {besoin:.1f} s of reading ({mots} words)")
        depuis = {}
        for k, x in enumerate(xs):
            # typed text changes on every frame: the key keeps only its first 12 characters
            cles = {re.sub(r"« (.{12}).*?»", r"« \1… »", re.sub(r" \(\d+ % visible\)$", "", c)) for c in x.get("coupes", [])}  # fr-ok
            for c in cles:
                depuis.setdefault(c, x["t"])
                # clipped for COUPE_MIN s, or until the end of the scene (the text ends up cut)
                if (x["t"] - depuis[c] >= COUPE_MIN - 1e-6 or k == len(xs) - 1) and (sid, c) not in vus:
                    vus.add((sid, c))
                    fautes.append(f"{sid} at {depuis[c]:.1f} s: {c} (clipped {COUPE_MIN:.0f} s or more, or until the end)")
            for c in list(depuis):
                if c not in cles:
                    del depuis[c]
        if xs[0]["alpha"]:
            continue
        trou = None
        for x in xs:
            if x["contenu"] < 0:
                continue
            rel = x["t"]   # time since the start of the scene (Series)
            if x["contenu"] == 0 and rel >= VIDE_ENTREE:
                trou = rel if trou is None else trou
                if rel - trou >= VIDE_MIN:
                    fautes.append(f"{sid} at {trou:.1f} s: VIDE (no content on screen for more than {VIDE_MIN:.0f} s)")
                    break
            elif x["contenu"] > 0:
                trou = None
    if not only:   # wanted durations, kept from one pass to the next (a lengthened scene that passes keeps its duration)
        fl = Path(args[0]).with_name(Path(args[0]).name.replace("_animation-script.json", "") + "_lecture.json")
        avant = json.loads(fl.read_text()) if fl.exists() else {}
        tout = {k: max(avant.get(k, 0.0), lecture.get(k, 0.0)) for k in set(avant) | set(lecture) if k in durees}
        texte = json.dumps(dict(sorted(tout.items())), ensure_ascii=False, indent=1)
        if not fl.exists() or fl.read_text() != texte:
            fl.write_text(texte)
    print(f"Text check: {len(scenes)} scenes, {len(releves)} frames read")
    for f in fautes:
        print("  !! " + f)
    if fautes:
        sys.exit(1)
    print("  OK: no overflow, overlap, bitten text or empty screen")
    if not only and pas <= 10:   # full check: signature read by render-segments.py
        sig = signature(Path(args[0]))
        sig.write_text(json.dumps({"empreinte": empreinte(script), "pas": pas}, indent=1))
        print(f"  signature: {sig.name}")


if __name__ == "__main__":
    main()
