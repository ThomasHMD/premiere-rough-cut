#!/usr/bin/env python3
"""GIFs and memes for `gif` scenes: search GIPHY, pick from a contact sheet, take as MP4.

    python3 gifs.py chercher "it's a bug" [--num 8] [--planche sheet.jpg] [--langue en]
    python3 gifs.py prendre <id> --nom t2-gif-bug [--dest Illustrations/gifs] [--public <video>]

- `chercher` lists the results (id, title, size, duration) and builds a numbered contact sheet
  (one frame taken at 40% of each GIF): look at it BEFORE choosing, a GIPHY title does not say
  what is on screen.
- `prendre` downloads the original MP4 version (never the .gif: heavy, 256 colors) into
  `--dest`, adds a line to `gifs.json` (id, title, source page) and prints the `data` of the
  `gif` scene (src, srcW, srcH, loopSec). `--public <video>` also drops a copy in
  `motion-design/public/scenes/<video>/gifs/`, where the scene reads it (`staticFile`).

Key: GIPHY_API_KEY, in the skill's .env, the project's (four folders above scripts/) or the
environment. Free key: developers.giphy.com ("Create an API key").
Rights: a GIF often reuses a protected work (film, series). Quoting it briefly in a video is
the video author's call; on a video that is sold, better to refrain.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ATELIER = SKILL.parent / "motion-design"
API = "https://api.giphy.com/v1/gifs"


def charger_env():
    for p in (SKILL / ".env", SKILL.parents[2] / ".env"):
        if p.is_file():
            for ligne in p.read_text().splitlines():
                ligne = ligne.strip()
                if ligne and not ligne.startswith("#") and "=" in ligne:
                    k, v = ligne.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    cle = os.environ.get("GIPHY_API_KEY", "")
    if not cle:
        sys.exit("GIPHY_API_KEY missing: add it to the .env (free key at developers.giphy.com).")
    return cle


def appel(chemin, **params):
    params["api_key"] = charger_env()
    url = f"{API}/{chemin}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "gifs.py"}), timeout=30) as r:
        return json.loads(r.read())


def telecharger(url, dest: Path):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "gifs.py"}), timeout=60) as r:
        dest.write_bytes(r.read())


def duree(mp4: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:50] or "gif"


def cmd_chercher(a):
    res = appel("search", q=a.requete, limit=a.num, rating=a.rating, lang=a.langue)["data"]
    if not res:
        sys.exit("No results: rephrase (in English, GIPHY often answers better).")
    vignettes = []
    with tempfile.TemporaryDirectory() as td:
        for i, g in enumerate(res, 1):
            o = g["images"]["original"]
            apercu = g["images"].get("fixed_width", {}).get("mp4") or o.get("mp4")
            print(f"{i:2d}. {g['id']}  {o.get('width')}x{o.get('height')}  {g.get('title') or '(untitled)'}")
            if a.planche and apercu:
                mp4 = Path(td) / f"{i}.mp4"
                png = Path(td) / f"{i}.png"
                try:
                    telecharger(apercu, mp4)
                    d = duree(mp4)
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{d * 0.4:.2f}", "-i", str(mp4),
                                    "-frames:v", "1", str(png)], check=True, timeout=60)
                    vignettes.append((i, png))
                except Exception as e:  # a failed thumbnail does not block the contact sheet
                    print(f"    (thumbnail {i} failed: {e})")
        if a.planche and vignettes:
            planche(vignettes, Path(a.planche))
            print(f"Contact sheet: {a.planche}")


def planche(vignettes, sortie: Path):
    from PIL import Image, ImageDraw, ImageOps
    cote, cols = 300, 4
    rangs = (len(vignettes) + cols - 1) // cols
    img = Image.new("RGB", (cols * cote, rangs * cote), "white")
    d = ImageDraw.Draw(img)
    for k, (i, png) in enumerate(vignettes):
        v = ImageOps.contain(Image.open(png).convert("RGB"), (cote - 10, cote - 10))
        x, y = (k % cols) * cote + 5, (k // cols) * cote + 5
        img.paste(v, (x, y))
        d.rectangle([x, y, x + 46, y + 34], fill="black")
        d.text((x + 10, y + 8), str(i), fill="white")
    sortie.parent.mkdir(parents=True, exist_ok=True)
    img.save(sortie, quality=88)


def cmd_prendre(a):
    g = appel(a.id)["data"]
    o = g["images"]["original"]
    if not o.get("mp4"):
        sys.exit(f"{a.id}: no MP4 version at GIPHY.")
    dest = Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)
    nom = slug(a.nom or g.get("title") or a.id)
    mp4 = dest / f"{nom}.mp4"
    telecharger(o["mp4"], mp4)
    w, h, d = int(o.get("width") or 480), int(o.get("height") or 480), duree(mp4)
    index = dest / "gifs.json"
    lignes = json.loads(index.read_text()) if index.exists() else []
    lignes = [x for x in lignes if x.get("fichier") != mp4.name]
    lignes.append({"fichier": mp4.name, "id": g["id"], "titre": g.get("title", ""), "source": g.get("url", ""),
                   "largeur": w, "hauteur": h, "duree": round(d, 2)})
    index.write_text(json.dumps(lignes, ensure_ascii=False, indent=1))
    src = f"gifs/{mp4.name}"
    if a.public:
        cible = ATELIER / "public" / "scenes" / a.public / "gifs"
        cible.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mp4, cible / mp4.name)
        src = f"scenes/{a.public}/gifs/{mp4.name}"
    print(f"✓ {mp4} ({w}x{h}, {d:.1f} s)")
    print(json.dumps({"src": src, "srcW": w, "srcH": h, "loopSec": round(d, 2)}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("chercher")
    c.add_argument("requete")
    c.add_argument("--num", type=int, default=8)
    c.add_argument("--planche")
    c.add_argument("--langue", default="en", help="language of the search (GIPHY lang code)")
    c.add_argument("--rating", default="pg-13")
    p = sp.add_parser("prendre")
    p.add_argument("id")
    p.add_argument("--nom")
    p.add_argument("--dest", default="Illustrations/gifs")
    p.add_argument("--public", help="name of the video folder in motion-design/public/scenes/")
    a = ap.parse_args()
    (cmd_chercher if a.cmd == "chercher" else cmd_prendre)(a)


if __name__ == "__main__":
    main()
