#!/usr/bin/env python3
"""Downloads a video's illustration images from a JSON manifest.

The manifest is built by Claude from the video's script (Notion):
entities in order of appearance, URLs resolved via serp_images.py.
This script does the deterministic part: download, validation, naming convention.

Naming convention:
    NN-category-photographer-name-subject.ext
    e.g. 01-pioneers-louis-daguerre-portrait.jpg
         01-pioneers-louis-daguerre-boulevard-du-temple.jpg
    (without a category: NN-photographer-name-subject.ext)

Manifest format (illustrations-manifest.json, placed in the video folder).
The keys are French, they are the contract (categorie = category, nom = name, sujet = subject):
{
  "version": 1,
  "dest": "Illustrations",              // relative to the manifest, or absolute path
  "items": [
    {
      "n": 1,                            // order of appearance in the script
      "categorie": "pioneers",           // optional: chapter or theme, or ""
      "nom": "Louis Daguerre",
      "sujet": "portrait",               // portrait | slug of the work/series
      "url": "https://...",              // direct URL of the image (resolved by Claude)
      "fallback_urls": ["https://..."],  // optional, tried if url fails
      "note": ""                         // free (source, credit...)
    }
  ]
}

Usage:
    python3 source-illustrations.py /path/illustrations-manifest.json
    python3 source-illustrations.py manifest.json --min-width 1000
    python3 source-illustrations.py manifest.json --force   # downloads again even if present
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

MAGIC = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG": ".png",
    b"GIF8": ".gif",
    b"RIFF": ".webp",  # RIFF....WEBP, checked below
}


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()


def sniff_ext(data: bytes) -> str | None:
    for magic, ext in MAGIC.items():
        if data.startswith(magic):
            if ext == ".webp" and data[8:12] != b"WEBP":
                continue
            return ext
    return None


def probe_width(path: Path) -> int:
    """Width in px via sips (native macOS). 0 on failure."""
    try:
        out = subprocess.run(["sips", "-g", "pixelWidth", str(path)],
                             capture_output=True, text=True, check=True).stdout
        m = re.search(r"pixelWidth:\s*(\d+)", out)
        return int(m.group(1)) if m else 0
    except subprocess.CalledProcessError:
        return 0


def download(url: str, timeout: int = 45) -> bytes | None:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", url.split("/", 3)[0] + "//" + url.split("/", 3)[2] + "/")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        print(f"      ✗ {e}")
        return None


def item_filename(item: dict) -> str:
    parts = [f"{int(item['n']):02d}"]
    if item.get("categorie"):
        parts.append(slugify(item["categorie"]))
    parts.append(slugify(item["nom"]))
    parts.append(slugify(item["sujet"]))
    return "-".join(p for p in parts if p)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", help="Path to illustrations-manifest.json")
    parser.add_argument("--min-width", type=int, default=1000,
                        help="Minimum width in px (warning below, no rejection)")
    parser.add_argument("--force", action="store_true", help="Download again even if the file exists")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)
    manifest = json.loads(manifest_path.read_text())

    dest_raw = manifest.get("dest", "Illustrations")
    dest = Path(dest_raw) if Path(dest_raw).is_absolute() else manifest_path.parent / dest_raw
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Destination: {dest}")

    ok, small, failed, skipped, missing_url = [], [], [], [], []

    for item in manifest.get("items", []):
        base = item_filename(item)
        label = f"{item['n']:>2}. {item['nom']}: {item['sujet']}"

        existing = list(dest.glob(base + ".*"))
        if existing and not args.force:
            print(f"  = {label}: already present ({existing[0].name})")
            skipped.append(base)
            continue

        urls = [u for u in [item.get("url")] + list(item.get("fallback_urls", [])) if u]
        if not urls:
            print(f"  ? {label}: no URL in the manifest: to be sourced")
            missing_url.append(label)
            continue

        print(f"  ↓ {label}")
        saved = None
        for url in urls:
            data = download(url)
            if not data:
                continue
            ext = sniff_ext(data)
            if not ext:
                print(f"      ✗ not an image (content {data[:12]!r})")
                continue
            out = dest / (base + ext)
            out.write_bytes(data)
            saved = out
            break

        if not saved:
            print("      ✗ all the URLs failed")
            failed.append(label)
            continue

        width = probe_width(saved)
        if width and width < args.min_width:
            print(f"      ⚠ {saved.name}: {width}px wide (< {args.min_width}): re-source in HD if possible")
            small.append(f"{saved.name} ({width}px)")
        else:
            print(f"      ✓ {saved.name} ({width}px)")
        ok.append(saved.name)

    print(f"\n=== SUMMARY: {len(ok)} downloaded, {len(skipped)} already present, "
          f"{len(failed)} failures, {len(missing_url)} without URL ===")
    if small:
        print(f"Low resolution ({len(small)}):")
        for s in small:
            print(f"  ⚠ {s}")
    if failed:
        print(f"Failures ({len(failed)}):")
        for f in failed:
            print(f"  ✗ {f}")
    if missing_url:
        print(f"Without URL ({len(missing_url)}):")
        for m in missing_url:
            print(f"  ? {m}")
    sys.exit(1 if failed or missing_url else 0)


if __name__ == "__main__":
    main()
