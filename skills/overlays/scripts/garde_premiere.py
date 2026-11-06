#!/usr/bin/env python3
"""Premiere guard: refuses an XML (or an imported sequence) that Premiere would display
wrongly. Called by `render-segments.py` BEFORE writing the delivered XML: an XML that fails is
never delivered. Can also be used on its own:

    python3 garde_premiere.py <sequence.xml>                       # before import
    python3 garde_premiere.py <sequence.xml> --projet <.prproj> [--sequence NAME]   # after import

Exit code 1 on the slightest defect. Each rule comes from a delivered file that came out wrong:

- ORDER. In each track, clips are listed in chronological order and do not overlap.
  Premiere keeps the file order and uses it as an index: an out-of-order clip becomes a
  GHOST (it shows in the picture but not on the timeline, it cannot be seen or cut, and it
  vanishes or jumps when you zoom). Typical case: white mattes appended after the b-rolls
  on V2, wrongly diagnosed as a 29.97 bug.
- FILES. Each <file> is defined in full exactly once, at its first appearance, and tells
  the truth about the media (ffprobe: frame rate, frame count, dimensions). A lying <file>
  gives a black clip on playback.
- DURATION. A clip does not ask for more than its media holds (more than one frame beyond =
  black or a frozen frame at the end of the clip).
- FRAME RATE. A clip of 29.97 media whose <in> is counted at a flat 30 (clip rate ntsc FALSE)
  is refused as soon as the gap exceeds 1.5 frames (in point beyond about 50 s), with or
  without an edit map.
- SYNC POINT. A clip of the rush (zoom on its camera) shows the picture of its own edit at
  the same instant (<rush>_timeline.json): Premiere reads <in> in the media's real rate.
- SOUNDS. Each sound effect falls during a visible element that matches it: a sound with no
  picture (element deleted, hidden, or ghost) is an error, not a detail. The live sound of a
  filmed shot (same file as a video clip of the sequence: the voice of the camera in a
  Tella-style edit) is not a sound effect: it keeps going under a full-screen card.
- HIDDEN. An element covered by more than half by an opaque element on a higher track is not
  seen: its screen time and its sound effect are wrong.
- CLOUD SYNC. No "conflicted copy" next to a media file: a sync service (some
  name their conflict copies this way) can restore an old version of a file and rename the
  good one "conflicted copy". Premiere would read the old one.
- PROJECT (after import): the clip lists of the imported sequence are sorted
  (`prproj_lib.check_track_order`), and every clip of the XML is in its place.
"""
from __future__ import annotations

import argparse
import functools
import json
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

TICKS = 254_016_000_000
OPAQUE_EXT = {".mp4", ".m4v", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
STILL_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def _rate(el) -> float:
    tb = int(el.findtext("rate/timebase") or 30)
    return tb * 1000 / 1001 if (el.findtext("rate/ntsc") or "").upper() == "TRUE" else float(tb)


@functools.lru_cache(maxsize=None)
def _probe(path: str) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,r_frame_rate,nb_frames,width,height,sample_rate,channels",
                          "-show_entries", "format=duration", "-of", "json", path],
                         capture_output=True, text=True)
    if out.returncode:
        return {}
    d = json.loads(out.stdout)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    return {"dur": float(d.get("format", {}).get("duration") or 0), "v": v, "a": a}


def _path(file_el) -> Path | None:
    u = file_el.findtext("pathurl")
    if not u:
        return None
    return Path(urllib.parse.unquote(u.replace("file://localhost", "", 1).replace("file://", "", 1)))


def _items(track):
    """Clips of a track in file order (clipitem and generatoritem)."""
    return [c for c in track if c.tag in ("clipitem", "generatoritem")]


def _clips(seq, kind):
    out = []
    for ti, tr in enumerate(seq.findall(f"media/{kind}/track"), 1):
        out.append([(c, int(c.findtext("start")), int(c.findtext("end"))) for c in _items(tr)])
    return out


def valider_xml(xml_path: Path) -> list[str]:
    err: list[str] = []
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as e:
        return [f"XML unreadable: {e}"]
    seqs = root.findall(".//sequence")
    if len(seqs) != 1:
        return [f"{len(seqs)} sequences in the file (one expected)"]
    seq = seqs[0]
    fps = _rate(seq)
    one = 1 / fps

    # Files: full definition at first appearance, only once
    files, seen = {}, set()
    for f in root.iter("file"):
        fid = f.get("id")
        full = f.find("pathurl") is not None or f.find("mediaSource") is not None
        if fid not in seen:
            seen.add(fid)
            if not full:
                err.append(f"FILES: {fid} referenced before being defined")
        elif full:
            err.append(f"FILES: {fid} defined twice")
        if full:
            files[fid] = f

    # cloud sync: a conflict copy next to a media file = the media file may be the old one
    dossiers = {p.parent for p in (_path(f) for f in files.values()) if p} | {Path(xml_path).resolve().parent}
    for d in sorted(dossiers):
        for c in sorted(d.glob("*conflicted copy*")):
            err.append(f"CLOUD SYNC: conflict copy {c.name} in {d.name}/: the version in place may "
                       f"be the old one, compare dates first")

    # Truth about the media
    for fid, f in files.items():
        p = _path(f)
        if p is None:
            continue
        if not p.exists():
            err.append(f"FILES: {p.name} not found on disk")
            continue
        m = _probe(str(p))
        if p.suffix.lower() in STILL_EXT or not m:
            continue
        if m["v"] and f.find("media/video") is not None:
            num, den = (int(x) for x in m["v"]["r_frame_rate"].split("/"))
            real = num / den
            if abs(_rate(f) - real) > 0.01:
                err.append(f"FILES: {p.name} declared at {_rate(f):.3f} fps, actual {real:.3f}")
            nb = int(m["v"].get("nb_frames") or 0) or round(m["dur"] * real)
            dec = f.findtext("duration")
            if dec and abs(int(dec) - nb) > 1:
                err.append(f"FILES: {p.name} declared {dec} frames, actual {nb}")
            w, h = f.findtext("media/video/samplecharacteristics/width"), f.findtext("media/video/samplecharacteristics/height")
            if w and (int(w), int(h)) != (int(m["v"]["width"]), int(m["v"]["height"])):
                err.append(f"FILES: {p.name} declared {w}x{h}, actual {m['v']['width']}x{m['v']['height']}")

    def fichier(c):
        fe = c.find("file")
        return files.get(fe.get("id")) if fe is not None else None

    def nom(c):
        f = fichier(c)
        p = _path(f) if f is not None else None
        return p.name if p else (c.findtext("name") or "?")

    # Order, bounds, duration asked of the media
    for kind, label in (("video", "V"), ("audio", "A")):
        for k, items in enumerate(_clips(seq, kind), 1):
            prev = None
            for c, s, e in items:
                if e <= s:
                    err.append(f"BOUNDS: {label}{k} {nom(c)} end {e} <= start {s}")
                if prev and s < prev[1]:
                    quoi = "out of order vs" if s < prev[0] else "overlaps"
                    err.append(f"ORDER: {label}{k} {nom(c)} at {s / fps:.2f} s {quoi} {nom(prev[2])} "
                               f"({prev[0] / fps:.2f}-{prev[1] / fps:.2f} s): ghost clip in Premiere")
                prev = (s, e, c) if not prev or e >= prev[1] else prev
                f = fichier(c)
                p = _path(f) if f is not None else None
                if c.tag != "clipitem" or p is None or p.suffix.lower() in STILL_EXT or not p.exists():
                    continue
                m = _probe(str(p))
                ti = c.findtext("pproTicksIn")
                debut = int(ti) / TICKS if ti else int(c.findtext("in") or 0) / fps
                besoin = debut + (e - s) / fps
                if m and besoin > m["dur"] + 0.001:
                    err.append(f"DURATION: {label}{k} {nom(c)} at {s / fps:.2f} s needs {besoin:.2f} s, "
                               f"the media is {m['dur']:.2f}")

    # Hidden by an opaque element on a higher track
    vids = _clips(seq, "video")
    opaques = []
    for k, items in enumerate(vids, 1):
        for c, s, e in items:
            f = fichier(c)
            p = _path(f) if f is not None else None
            alpha = (c.findtext("alphatype") or "none") != "none"
            if c.tag == "generatoritem" or (p and p.suffix.lower() in OPAQUE_EXT and not alpha):
                opaques.append((k, s, e))

    def visible(k, s, e):
        cov = sorted((max(s, a), min(e, b)) for kk, a, b in opaques if kk > k and a < e and b > s)
        tot, cur = 0, s
        for a, b in cov:
            if b > cur:
                tot += b - max(a, cur)
                cur = b
        return 1 - tot / (e - s)

    for k, items in enumerate(vids, 1):
        for c, s, e in items:
            v = visible(k, s, e)
            if v < 0.5:
                err.append(f"HIDDEN: V{k} {nom(c)} at {s / fps:.2f} s is only {v:.0%} visible "
                           f"(covered by an opaque higher track)")

    # Each sound effect falls during a visible element that matches it
    tous = [(k, c, s, e, nom(c)) for k, items in enumerate(vids, 1) for c, s, e in items]
    filmes = {c.find("file").get("id") for _, c, _, _, _ in tous if c.find("file") is not None}
    for k, items in enumerate(_clips(seq, "audio"), 1):
        for c, s, e in items:
            if c.find("file") is not None and c.find("file").get("id") in filmes:
                continue   # live sound of a filmed shot, not a sound effect
            if (c.get("id") or "").startswith("rush_a"):
                continue   # its voice laid by render-segments (raw rush or processed WAV), not a sound effect
            n = nom(c)
            m = re.match(r"ANIM-(S|SC)-(.+)-son\.wav$", n)
            if m:
                cible = (lambda x: x.startswith(f"ANIM-S-{m.group(2)}.")) if m.group(1) == "S" else \
                        (lambda x: x == f"{m.group(2)}.mp4")
                cands = [t for t in tous if cible(t[4])]
            else:   # default sound of a type (lower third, photo): laid at the start of its element
                cands = [t for t in tous if abs(t[2] - s) <= 2]
            ok = [t for t in cands if t[2] - 2 <= s < t[3] and visible(t[0], t[2], t[3]) >= 0.5]
            if not ok:
                err.append(f"SOUNDS: A{k} {n} at {s / fps:.2f} s falls on no visible element "
                           f"that matches it")
    # SYNC POINT: a clip of the rush laid on its sequence (zooms of the long video) shows the picture of ITS edit at the
    # same instant. Premiere reads <in> in the media's REAL rate: counted at a flat 30 on a 29.97 rush, a zoom
    # started 0.74 s too late and showed a cut passage. Map: <rush>_timeline.json.
    for items in vids:
        for c, s0, e0 in items:
            f = fichier(c)
            p = _path(f) if f is not None else None
            if not p or c.tag != "clipitem":
                continue
            # FRAME RATE, no map: <in> counted at a flat 30 (clip rate FALSE) on 29.97 media shifts the picture by 0.1%
            # of the in point; beyond 1.5 frames (in point > about 50 s) it is visible (up to 0.84 s on a reel).
            if f.findtext("rate/ntsc") == "TRUE" and c.findtext("rate/ntsc") == "FALSE":
                n_in = int(c.findtext("in"))
                if n_in / _rate(f) - n_in / _rate(c) > 1.5 / _rate(f):
                    err.append(f"FRAME RATE: {p.name} at {s0 / fps:.2f} s: <in> {n_in} counted at {_rate(c):g} fps on {_rate(f):.3f} "
                               f"media: Premiere will read {(n_in / _rate(f) - n_in / _rate(c)) * 1000:+.0f} ms further")
            carte = p.with_name(p.stem + "_timeline.json")
            if not carte.exists():
                continue
            tl = [x for x in json.loads(carte.read_text()) if x.get("media", p.name) == p.name]
            # the map describes ITS edit, left on its V1 (empty in the XML): a sequence that carries the rush itself
            # on V1 (a reel we edited) has its own edit and is not read against it
            if any(fichier(x) is not None and _path(fichier(x)) == p for x, _, _ in (vids[0] if vids else [])):
                continue
            t = s0 / fps
            clip = next((x for x in tl if x["seq_in"] - one / 2 <= t < x["seq_out"]), None)
            if clip is None:
                err.append(f"SYNC POINT: {p.name} at {t:.2f} s outside its edit")
                continue
            lu = int(c.findtext("in")) / _rate(f)
            voulu = clip["src_in"] + t - clip["seq_in"]
            if abs(lu - voulu) > 1.5 / _rate(f):
                err.append(f"SYNC POINT: {p.name} at {t:.2f} s: Premiere will read the source at {lu:.2f} s, its edit shows {voulu:.2f} s "
                           f"({(lu - voulu) * 1000:+.0f} ms)")
            if lu + (e0 - s0) / fps > clip["src_out"] + one:
                err.append(f"SYNC POINT: {p.name} at {t:.2f} s runs past its edit clip (cuts at {clip['seq_out']:.2f} s)")

    last = max((e for items in vids + _clips(seq, "audio") for _, _, e in items), default=0)
    if int(seq.findtext("duration") or 0) < last:
        err.append(f"BOUNDS: sequence of {seq.findtext('duration')} frames, last clip at {last}")
    return err


def valider_projet(prproj: Path, xml_path: Path, sequence: str | None = None) -> list[str]:
    """After import: does the sequence have ghost clips, and is every clip of the XML in
    its place? (The editor's additions are allowed: only order and absence count.)"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import prproj_lib as P
    root, by_id, by_uid = P.load(prproj)
    xr = ET.parse(xml_path).getroot()
    xseq = xr.find(".//sequence")
    name = sequence or xseq.findtext("name")
    seqs = [s for s in root.iter("Sequence") if s.findtext("Name") == name]
    if not seqs:
        return [f"PROJECT: sequence {name} missing from {prproj.name}"]
    err = []
    spec = __import__("importlib.util").util.spec_from_file_location(
        "tl", Path(__file__).resolve().parent / "timeline-from-prproj.py")
    tl = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(tl)
    fps = _rate(xseq)
    files = {f.get("id"): _path(f) for f in xr.iter("file") if f.find("pathurl") is not None}
    pistes = tl.video_tracks(seqs[0], by_id, by_uid)
    for k, items in enumerate(pistes, 1):
        st = []
        for it in items:
            h = it
            for tag in ("ClipTrackItem", "TrackItem"):
                n = h.find(tag)
                if n is not None:
                    h = n
            st.append(int(h.findtext("Start") or 0))
        inv = sum(1 for a, b in zip(st, st[1:]) if b < a)
        if inv:
            err.append(f"PROJECT: V{k} of {name} has {inv} out-of-order clip(s) = ghosts (invisible on the timeline)")
    for start, n in P.check_track_order(root):
        err.append(f"PROJECT: a list of {n} clips (start {start / TICKS:.2f} s) is not sorted/numbered "
                   f"in {prproj.name} (prproj_lib.check_track_order)")
    xv = _clips(xseq, "video")
    for k, items in enumerate(xv, 1):
        have = [tl.clip_info(i, by_id, by_uid) for i in (pistes[k - 1] if k <= len(pistes) else [])]
        for c, s, e in items:
            p = files.get(c.find("file").get("id")) if c.find("file") is not None else None
            n = p.name if p else c.findtext("name")
            if not any(h and h[4] == n and abs(h[0] - s / fps) < 1.5 / fps for h in have):
                err.append(f"PROJECT: V{k} {n} at {s / fps:.2f} s missing from the imported sequence")
    return err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml", type=Path)
    ap.add_argument("--projet", type=Path)
    ap.add_argument("--sequence")
    a = ap.parse_args()
    err = valider_xml(a.xml)
    if a.projet:
        err += valider_projet(a.projet, a.xml, a.sequence)
    for e in err:
        print("  ✗ " + e)
    print(f"{len(err)} defect(s)" if err else "OK: no defects")
    sys.exit(1 if err else 0)


if __name__ == "__main__":
    main()
