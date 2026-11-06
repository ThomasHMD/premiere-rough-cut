#!/usr/bin/env python3
"""Repairs the ghost clips of a Premiere project without touching anything else.

    python3 reparer-projet.py <project.prproj> [--essai]

A ghost clip = a clip listed out of chronological order in its track: Premiere plays it
but does not show it on the timeline (it can be neither seen nor cut, and it jumps when you
zoom). Cause: an imported XML whose tracks were not sorted.

The project MUST be closed in Premiere (otherwise it will rewrite its in-memory state on top).
Steps, all blocking:
1. sort each clip list by start (`prproj_lib.sort_tracks`), write next to the original;
2. proof that nothing else changed: the canonical form of both projects differs only
   by the order of the `<TrackItem>` (same elements, same values);
3. `prproj_lib.check_track_order` empty on the result;
4. the original goes to the trash (~/.Trash/), the repaired one takes its name.
`--essai` (dry run) stops after 3 and leaves the result in the temp folder.
"""
import gzip
import re
import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prproj_lib as P  # noqa: E402


def canon(path: Path) -> list[str]:
    raw = gzip.open(path).read().decode("utf-8")
    return ET.canonicalize(raw).splitlines()


def main():
    src = Path(sys.argv[1]).resolve()
    essai = "--essai" in sys.argv
    tmpd = Path(tempfile.mkdtemp(prefix="reparer-projet-"))
    dst = tmpd / src.name
    root, _, _ = P.load(src)
    avant = P.check_track_order(root)
    if not avant:
        print("No ghost clip: nothing to repair.")
        return
    print(f"{len(avant)} track(s) with out-of-order clips")
    P.sort_tracks(root)
    P.save(root, dst)          # refuses to write an unsorted track

    a, b = canon(src), canon(dst)
    ligne = lambda l: re.sub(r'Index="\d+" ', "", l.strip())
    diff_a = Counter(ligne(l) for l in a) - Counter(ligne(l) for l in b)
    diff_b = Counter(ligne(l) for l in b) - Counter(ligne(l) for l in a)
    if diff_a or diff_b or len(a) != len(b):
        print("✗ The repaired project differs beyond the clip order: nothing is replaced.")
        for l in list(diff_a)[:5] + list(diff_b)[:5]:
            print("   ", l[:150])
        sys.exit(1)
    r2, _, _ = P.load(dst)
    if P.check_track_order(r2):
        print("✗ Tracks still out of order after sorting: nothing is replaced.")
        sys.exit(1)
    print("✓ Only the clip order changed; no track is out of order anymore.")
    if essai:
        print(f"(dry run) result: {dst}")
        return
    corbeille = Path.home() / ".Trash" / f"{src.stem}-avant-reparation-{time.strftime('%Y%m%d-%H%M%S')}.prproj"
    shutil.move(str(src), str(corbeille))
    shutil.move(str(dst), str(src))
    print(f"✓ Project repaired in place; the original is in the trash ({corbeille.name}).")


if __name__ == "__main__":
    main()
