#!/usr/bin/env python3
"""Grain for the animated background (FondAnime): public/fond/grain.png, 3840x2160 grayscale.

Softened Gaussian noise (grain about 2 px), almost white: the composition lays it on in
"multiply" at 5% opacity, it only breaks up flat areas. Same seed = same image
(deterministic render, and loops already rendered stay valid).

    python3 scripts/make-grain.py            # writes public/fond/grain.png if missing
    python3 scripts/make-grain.py --force    # regenerates it
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

W, H = 3840, 2160
SORTIE = Path(__file__).resolve().parent.parent / "public" / "fond" / "grain.png"


def main():
    if SORTIE.exists() and "--force" not in sys.argv:
        print(f"{SORTIE} already exists (--force to regenerate it)")
        return
    rng = np.random.default_rng(1839)
    bruit = rng.standard_normal((H, W)).astype(np.float32)
    # soften by half a pixel: about 0.35 correlation between neighbors, like film grain
    img = Image.fromarray(np.clip(128 + 40 * bruit, 0, 255).astype(np.uint8), "L")
    a = np.asarray(img.filter(ImageFilter.GaussianBlur(0.6)), dtype=np.float32)
    a = (a - a.mean()) / (a.std() or 1)
    # almost white, tail toward dark (mean ~ 222, std ~ 27)
    v = np.clip(227 + 31 * a, 0, 255).astype(np.uint8)
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(v, "L").save(SORTIE, optimize=True)
    print(f"OK {SORTIE} (mean {v.mean():.0f}, std {v.std():.0f})")


if __name__ == "__main__":
    main()
