#!/usr/bin/env python3
"""The moments when the speaker shows an object to the camera (camera body, book): nothing must cover it.

    python3 montre.py <rush> [<rush2>…]              # reads <rush>_timeline.json, writes <rush>_montre.json + contact sheet
    python3 montre.py <rush> … --planche <output.jpg>

Rule: an animation laid over the moment the speaker holds an object up to the lens hides exactly what
they are showing. Stick to what is shown instead of covering it. Same rule as "here = the speaker shows
the object" in reels and as the framings on books.

Method: one frame every 0.5 s of its edit (map <rush>_timeline.json, several rushes possible),
face detection (OpenCV, two cascades); an object held in front of the lens hides the face. A window = at least
FENETRE_MIN s without a face, gaps shorter than TROU_MAX s glued back together. The detection does not know WHAT hides
the face (the speaker may also be looking at notes or leaning over): the contact sheet, one thumbnail per window with
its instant, must be looked at before relying on it; the plan receives the windows kept (`habillage.controles(…, montre=…)`
refuses them under a scene or an overlay).
"""
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

PAS = 0.5          # one frame every 0.5 s
FENETRE_MIN = 1.0  # at least 1 s without a face
TROU_MAX = 0.6     # a face seen in a single frame in the middle does not split the window
W, H = 640, 360


def images(rush: Path, debut: float, duree: float):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{debut:.3f}", "-i", str(rush), "-t", f"{duree:.3f}",
                        "-vf", f"fps={1 / PAS},scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True, check=True).stdout
    return np.frombuffer(r, np.uint8).reshape(-1, H, W)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(2)
    rush = Path(args[0]).resolve()
    tl = json.loads(rush.with_name(f"{rush.stem}_timeline.json").read_text())
    cascades = [cv2.CascadeClassifier(cv2.data.haarcascades + n)
                for n in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml")]
    ech = []   # (sequence instant, face seen, frame)
    for c in tl:
        src = rush.with_name(c["media"]) if c.get("media") else rush
        imgs = images(src, c["src_in"], c["seq_out"] - c["seq_in"])
        for k, im in enumerate(imgs):
            t = c["seq_in"] + k * PAS
            if t >= c["seq_out"]:
                break
            eq = cv2.equalizeHist(im)
            vu = any(len(cc.detectMultiScale(eq, 1.1, 5, minSize=(70, 70))) for cc in cascades)
            ech.append((round(t, 2), bool(vu), im))
    fen, a = [], None
    for i, (t, vu, _) in enumerate(ech):
        if not vu and a is None:
            a = t
        if vu and a is not None:
            # an isolated face (one frame) in the middle of a window does not split it
            suite = [v for _, v, _ in ech[i:i + int(TROU_MAX / PAS) + 1]]
            if all(suite):
                fen.append([a, t])
                a = None
    if a is not None:
        fen.append([a, ech[-1][0] + PAS])
    fen = [f for f in fen if f[1] - f[0] >= FENETRE_MIN]
    out = rush.with_name(f"{rush.stem}_montre.json")
    texte = json.dumps({"pas": PAS, "fenetres": fen, "_note": "windows without a face, to validate on the contact sheet"},  # fr-ok: JSON keys
                       ensure_ascii=False, indent=1)
    if not out.exists() or out.read_text() != texte:
        out.write_text(texte)
    print(f"{len(ech)} frames, {len(fen)} window(s) without a face -> {out.name}")
    for f in fen:
        print(f"  {int(f[0] // 60):02d}:{f[0] % 60:05.2f} → {int(f[1] // 60):02d}:{f[1] % 60:05.2f}  ({f[1] - f[0]:.1f} s)")
    if "--planche" in sys.argv and fen:
        from PIL import Image, ImageDraw
        dest = Path(sys.argv[sys.argv.index("--planche") + 1])
        par_t = {t: im for t, _, im in ech}
        vign = []
        for a, b in fen:
            t = min(par_t, key=lambda x: abs(x - (a + b) / 2))
            v = Image.fromarray(par_t[t]).convert("RGB").resize((320, 180))
            ImageDraw.Draw(v).rectangle((0, 0, 150, 22), fill=(0, 0, 0))
            ImageDraw.Draw(v).text((4, 4), f"{int(a // 60):02d}:{a % 60:05.2f} {b - a:.1f}s", fill=(255, 255, 0))
            vign.append(v)
        col = 5
        pl = Image.new("RGB", (320 * col, 180 * ((len(vign) + col - 1) // col)))
        for i, v in enumerate(vign):
            pl.paste(v, (320 * (i % col), 180 * (i // col)))
        pl.save(dest, quality=85)
        print(f"contact sheet: {dest}")


if __name__ == "__main__":
    main()
