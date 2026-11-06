#!/usr/bin/env python3
"""Builds a sound-effect palette from real recordings (sound library, home takes), without touching
the shots: public/sfx/<palette>/ gets the SAME file names as the default palette, at the level of their role.
`son.palette("<palette>")` plays it; a sound it lacks comes from the default palette (son.py fallback).

    python3 palette-import.py --modele mapping.json    # template: every sound of the default palette, its role, empty source
    python3 palette-import.py mapping.json [--plafond -9]

Mapping (changing a sound = changing one line and rerunning):

    {"palette": "objets",
     "racine": "/path/to/raw/sounds",             (optional; default: the folder of the mapping file)
     "sons": {"pose-1.wav":   ["cards/card-down-1.wav", "info"],
              "tampon-1.wav": ["paper/wood-stamp-2.flac", "accent", -2],     (3rd value optional: nuance in dB)
              "page.wav":     ""}}                                             (empty: the default sound stays)

Each source (any format ffmpeg reads) is converted to mono 48 kHz, stripped of leading silence (the gesture sounds
on the frame: son.py syncs the attack, not the blank before it) and trailing silence, then set to the level of its
role (make-sfx.py: VOIX_REF + ROLES, K level over 100 ms, like the synth recipes). A real brief sound effect (stamp,
shutter) has a much higher peak than a synthesized sound at the same level: its peak is capped at --plafond dBFS (-9
by default, measured on a kit user's setup), even if that leaves it below its target; the script says so. mix.py
also limits the true peak of the final mix.

Roles: accent (signature, stamp, shutter), info (a card set down, a note), texture (slide, page, detents, clicks).
Several takes of the same gesture: pose-1.wav, pose-2.wav, pose-3.wav... (tampon-N too): son.py cycles through all of them.
A file is only rewritten if it changes; a sound removed from the mapping is removed from the palette.
"""
import argparse
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ICI = Path(__file__).resolve().parent
SFX = ICI.parent / "public" / "sfx"
SR = 48000
TOURNANTES = ("pose", "tampon")   # families whose takes son.py cycles through (pose-1, pose-2, pose-3...)


def lutherie():
    spec = importlib.util.spec_from_file_location("lutherie", ICI / "make-sfx.py")
    lut = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lut)
    return lut


def lire(source):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True)
    if raw.returncode or not raw.stdout:
        raise SystemExit(f"!! unreadable: {source}\n{raw.stderr.decode()[-300:]}")
    return np.frombuffer(raw.stdout, dtype=np.float32).astype(np.float64)


def taille(x):
    """Strips leading silence (2 ms kept before the attack, threshold -40 dB below the peak) and trailing silence
    (-50 dB, 10 ms kept), then applies a 15 ms fade-out."""
    pic = float(np.abs(x).max()) or 1.0
    fort = np.flatnonzero(np.abs(x) > pic * 10 ** (-40 / 20))
    queue = np.flatnonzero(np.abs(x) > pic * 10 ** (-50 / 20))
    a = max(0, fort[0] - int(0.002 * SR)) if len(fort) else 0
    b = min(len(x), queue[-1] + int(0.010 * SR)) if len(queue) else len(x)
    y = x[a:b].copy()
    f = min(len(y), int(0.015 * SR))
    y[len(y) - f:] *= np.linspace(1, 0, f)
    return y


def modele(chemin):
    meta = json.loads((SFX / "palette.json").read_text())["sons"]
    c = {"_lisez": "Fill in \"sons\": [path of the recording, role] (role optional: the default's, see \"_defaut\"); "
                   "leave \"\" to keep the default sound. Add pose-3.wav, tampon-4.wav... for more takes. "
                   "Then: palette-import.py <this file>.",
         "palette": "objets", "racine": "",
         "sons": {nom: "" for nom in sorted(meta)},
         "_defaut": {nom: f"{m.get('role', 'info')} · {m.get('usage', '')}" for nom, m in sorted(meta.items())}}
    Path(chemin).write_text(json.dumps(c, ensure_ascii=False, indent=1))
    print(f"template written: {chemin} ({len(c['sons'])} sounds; fill in \"sons\" with [source, role])")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("correspondance", nargs="?")
    ap.add_argument("--modele", help="write a mapping template to this path")
    ap.add_argument("--plafond", type=float, default=-9.0, help="maximum peak of a sound, in dBFS (default -9)")
    a = ap.parse_args()
    if a.modele:
        return modele(a.modele)
    if not a.correspondance:
        ap.error("give a mapping file, or --modele <path>")

    cor_path = Path(a.correspondance).resolve()
    cor = json.loads(cor_path.read_text())
    nom_palette = (cor.get("palette") or "").strip()
    if not nom_palette or nom_palette in ("defaut", "papier") or "/" in nom_palette:
        raise SystemExit("\"palette\": a plain subfolder name (e.g. \"objets\"), never the default palette")
    racine = Path(cor.get("racine") or cor_path.parent).expanduser()
    dossier = SFX / nom_palette
    ancien = json.loads((dossier / "palette.json").read_text()) if (dossier / "palette.json").exists() else None
    if ancien is not None and not ancien.get("importee"):
        raise SystemExit(f"{dossier} is a synthesized palette (not made by this tool): pick another name")
    defaut = json.loads((SFX / "palette.json").read_text())["sons"]
    lut = lutherie()
    dossier.mkdir(parents=True, exist_ok=True)

    meta, plafond = {}, 10 ** (a.plafond / 20)
    for nom, v in sorted(cor.get("sons", {}).items()):
        if not v:
            continue
        source, role, nuance = (v + [None, 0.0])[:3] if isinstance(v, list) else (v, None, 0.0)
        role = role or defaut.get(nom, {}).get("role", "info")
        if role not in lut.ROLES:
            raise SystemExit(f"{nom}: unknown role \"{role}\" ({', '.join(lut.ROLES)})")
        src = Path(source).expanduser()
        src = src if src.is_absolute() else racine / src
        if not src.exists():
            raise SystemExit(f"{nom}: source not found: {src}")
        y = taille(lire(src))
        cible = lut.VOIX_REF + lut.ROLES[role] + float(nuance or 0.0)
        y *= 10 ** ((cible - lut.force(y)) / 20)
        crete, sous = float(np.abs(y).max()), 0.0
        if crete > plafond:
            sous = 20 * np.log10(crete / plafond)
            y *= plafond / crete
        buf = io.BytesIO()
        sf.write(buf, y, SR, subtype="PCM_24", format="WAV")
        sortie = dossier / nom
        if not sortie.exists() or sortie.read_bytes() != buf.getvalue():
            sortie.write_bytes(buf.getvalue())
        meta[nom] = {"role": role, "source": str(src), "usage": defaut.get(nom, {}).get("usage", ""),
                     "niveau": round(lut.force(y), 1), "crete": round(20 * np.log10(np.abs(y).max()), 1),
                     "duree": round(len(y) / SR, 2), **({"sous_cible_db": round(sous, 1)} if sous else {})}
        famille = nom.rsplit("-", 1)[0] if nom.rsplit("-", 1)[-1][:-4].isdigit() else None
        hors = ("" if nom in defaut else "  (extra take: son.py cycles through it)" if famille in TOURNANTES
                else "  (name not in the default palette: no son.py gesture plays it)")
        print(f"{nom:18s} {role:8s} level {meta[nom]['niveau']:6.1f}  peak {meta[nom]['crete']:6.1f}  {meta[nom]['duree']:.2f} s"
              + (f"  capped, {sous:.1f} dB below its target" if sous else "") + hors)

    for nom in sorted(set((ancien or {}).get("sons", {})) - set(meta)):
        (dossier / nom).unlink(missing_ok=True)
        print(f"{nom:18s} removed (not in the mapping: the default sound takes over)")
    contenu = json.dumps({"identite": nom_palette, "importee": True, "correspondance": str(cor_path),
                          "voixRef": lut.VOIX_REF, "roles": lut.ROLES, "plafondDbfs": a.plafond, "sons": meta},
                         ensure_ascii=False, indent=1)
    pj = dossier / "palette.json"
    if not pj.exists() or pj.read_text() != contenu:
        pj.write_text(contenu)
    print(f"\n{len(meta)} sounds in {dossier}; the other {len(set(defaut) - set(meta))} come from the default palette. "
          f"In a shot: son.palette(\"{nom_palette}\").")


if __name__ == "__main__":
    sys.exit(main())
