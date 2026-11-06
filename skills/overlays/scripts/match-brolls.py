#!/usr/bin/env python3
"""Scans <rush_dir>/Brolls/ and produces a <rush>_broll-script.json template to fill in.

Expected naming convention: NN_description-in-english_K.mp4
  - NN  = order number (01, 02, ...)
  - description = EN keywords separated by dashes
  - K   = variant number (1, 2, ...)

The template groups the variants by number, lists every option for each b-roll, and leaves
the `file` / `timecode` / `note` fields empty for validation.

Claude (or the user) then fills in:
  - file        : chosen variant (e.g. "01_xxx_2.mp4")
  - timecode    : placement in the rush (e.g. "02:34")
  - durationSec : null = native duration of the clip
  - note        : free comment

Usage:
    python3 match-brolls.py /path/rush.mp4
    python3 match-brolls.py /path/rush.mp4 --force      # overwrites an existing template
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".avi"}


def parse_broll_filename(name: str) -> tuple[str, str, str] | None:
    """Returns (id, slug_keywords, variant), or None if the name does not follow the convention.

    Examples:
      01_famous-photographer_1.mp4 → ("01", "famous-photographer", "1")
      02_art-gallery-photography_2.mov → ("02", "art-gallery-photography", "2")
    """
    stem = Path(name).stem
    m = re.match(r"^(\d{1,3})_(.+?)_(\d+)$", stem)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def probe_video_duration(path: Path) -> float:
    """Duration in seconds via ffprobe (0.0 on failure)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("rush", help="Path to the rush video (the Brolls/ folder is looked for next to it)")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing broll-script")
    parser.add_argument("--brolls-dir", help="Override the b-rolls folder (default: <rush_dir>/Brolls)")
    args = parser.parse_args()

    rush = Path(args.rush).resolve()
    if not rush.exists():
        print(f"ERROR: rush not found: {rush}", file=sys.stderr)
        sys.exit(1)

    brolls_dir = Path(args.brolls_dir).resolve() if args.brolls_dir else rush.parent / "Brolls"
    if not brolls_dir.exists():
        print(f"ERROR: b-rolls folder not found: {brolls_dir}", file=sys.stderr)
        print("  Tip: put the b-rolls in a 'Brolls/' folder next to the rush, or use --brolls-dir.",
              file=sys.stderr)
        sys.exit(1)

    out_json = rush.with_name(rush.stem + "_broll-script.json")
    if out_json.exists() and not args.force:
        print(f"ERROR: {out_json.name} already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    # Scan + group by numeric prefix
    groups: dict[str, list[dict]] = defaultdict(list)
    skipped: list[str] = []
    for f in sorted(brolls_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() not in VIDEO_EXTS:
            continue
        parsed = parse_broll_filename(f.name)
        if not parsed:
            skipped.append(f.name)
            continue
        broll_id, keywords, variant = parsed
        groups[broll_id].append({
            "variant": variant,
            "file": f.name,
            "keywords": keywords.replace("-", " "),
            "duration_sec": round(probe_video_duration(f), 2),
        })

    if not groups:
        print(f"ERROR: no b-roll found in the NN_description_K.mp4 format in {brolls_dir}",
              file=sys.stderr)
        sys.exit(1)

    # Build the template to fill in
    brolls_template = []
    for broll_id in sorted(groups.keys(), key=int):
        variants = sorted(groups[broll_id], key=lambda v: int(v["variant"]))
        kw = variants[0]["keywords"]
        brolls_template.append({
            "id": broll_id,
            "keywords": kw,
            "variants": [
                {"variant": v["variant"], "file": v["file"], "duration_sec": v["duration_sec"]}
                for v in variants
            ],
            "file": "",
            "timecode": "??",
            "durationSec": None,
            "note": "",
        })

    output = {
        "version": 1,
        "fps": 60,
        "rush": rush.name,
        "brolls_dir": str(brolls_dir),
        "brolls": brolls_template,
    }
    out_json.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print(f"✅ Template written: {out_json}")
    print(f"   {len(brolls_template)} b-rolls grouped ({sum(len(g) for g in groups.values())} files in total).")
    if skipped:
        print(f"   ⚠️  {len(skipped)} files ignored (do not follow NN_description_K.mp4):")
        for s in skipped[:5]:
            print(f"      - {s}")
        if len(skipped) > 5:
            print(f"      ... and {len(skipped)-5} more")
    print()
    print("Next step: fill in `file`, `timecode`, `durationSec` (null = native duration), `note`")
    print("then run `render-segments.py` to generate the XML with the b-rolls on V2.")


if __name__ == "__main__":
    main()
