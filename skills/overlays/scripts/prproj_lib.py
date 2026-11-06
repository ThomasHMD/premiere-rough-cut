#!/usr/bin/env python3
"""Reading/writing a Premiere project (.prproj): tracks, clips, positions.

A .prproj is a gzipped XML. Objects reference each other by ObjectID / ObjectUID,
hence the index: a track does not CONTAIN its clips, it REFERENCES them.

Used to re-time clips that are already edited without going through an FCP7 import, which would
lose the formatting work (doubled tracks, blurred background, labels).
"""

import gzip
from pathlib import Path
import xml.etree.ElementTree as ET

TICKS = 254016000000          # Premiere ticks per second


def load(prproj: Path):
    with gzip.open(prproj, "rb") as f:
        root = ET.fromstring(f.read())
    by_id, by_uid = {}, {}
    for el in root.iter():
        i = el.get("ObjectID")
        if i:
            by_id[i] = el
        u = el.get("ObjectUID")
        if u:
            by_uid[u] = el
    return root, by_id, by_uid


class ProjetInvalide(Exception):
    pass


def check_track_order(root):
    """Premiere invariant: in each track, the TrackItems list is SORTED by Start and
    numbered 0..n-1. Premiere uses it as an interval index: an out-of-order clip
    vanishes from the display as soon as you zoom (a delivered file the editor could not work
    with). Returns the list of faulty tracks."""
    by_id, by_uid = {}, {}
    for el in root.iter():
        if el.get("ObjectID"):
            by_id[el.get("ObjectID")] = el
        if el.get("ObjectUID"):
            by_uid[el.get("ObjectUID")] = el
    bad = []
    for ti in root.iter("TrackItems"):
        refs = ti.findall("TrackItem")
        if len(refs) < 2 or ti.get("Version") != "1":
            continue
        starts = []
        for r in refs:
            it = deref(r, by_id, by_uid)
            if it is None or not it.tag.endswith("ClipTrackItem"):
                starts = None
                break
            b = _bounds_ro(it)
            starts.append(b)
        if not starts:
            continue
        if any(y < x for x, y in zip(starts, starts[1:])) or \
           [r.get("Index") for r in refs] != [str(i) for i in range(len(refs))]:
            bad.append((starts[0], len(refs)))
    return bad


def _bounds_ro(item):
    holder = item
    for tag in ("ClipTrackItem", "TrackItem"):
        nxt = holder.find(tag)
        if nxt is not None:
            holder = nxt
    s = holder.find("Start")
    return int(s.text) if s is not None and s.text else 0


def sort_tracks(root):
    """Re-sorts and renumbers all the clip TrackItems lists by Start."""
    by_id, by_uid = {}, {}
    for el in root.iter():
        if el.get("ObjectID"):
            by_id[el.get("ObjectID")] = el
        if el.get("ObjectUID"):
            by_uid[el.get("ObjectUID")] = el
    for ti in root.iter("TrackItems"):
        refs = ti.findall("TrackItem")
        if len(refs) < 2 or ti.get("Version") != "1":
            continue
        items = [deref(r, by_id, by_uid) for r in refs]
        if any(it is None or not it.tag.endswith("ClipTrackItem") for it in items):
            continue
        order = sorted(zip(refs, items), key=lambda x: _bounds_ro(x[1]))
        for r in refs:
            ti.remove(r)
        for i, (r, _) in enumerate(order):
            r.set("Index", str(i)); ti.append(r)


def save(root, dest: Path):
    """Writes the project. REFUSES to write a file that Premiere would display wrongly: any
    unsorted track list is an error, never a warning. Scripts that move clips
    call sort_tracks() first."""
    bad = check_track_order(root)
    if bad:
        raise ProjetInvalide(f"{len(bad)} TrackItems list(s) not sorted/numbered: "
                             f"call prproj_lib.sort_tracks(root) before save()")
    with gzip.open(dest, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8" ?>\n')
        f.write(ET.tostring(root, encoding="utf-8"))


def deref(el, by_id, by_uid):
    """Follows an ObjectRef / ObjectURef to the element it points to."""
    if el is None:
        return None
    r = el.get("ObjectRef")
    if r and r in by_id:
        return by_id[r]
    r = el.get("ObjectURef")
    if r and r in by_uid:
        return by_uid[r]
    t = (el.text or "").strip()
    return by_id.get(t) or by_uid.get(t)


def sequences(root, by_id, by_uid):
    out = []
    for el in root.iter("Sequence"):
        n = el.find(".//Name")
        out.append((n.text if n is not None else "?", el))
    return out


def tracks(seq, by_id, by_uid):
    """[(type, index, [TrackItem...])] for a sequence, video then audio."""
    out = []
    tg = seq.find("TrackGroups")
    if tg is None:
        return out
    for tgi in tg.findall("TrackGroup"):
        grp = deref(tgi.find("Second"), by_id, by_uid) or deref(tgi, by_id, by_uid)
        if grp is None:
            continue
        kind = "V" if grp.tag.startswith("Video") else "A" if grp.tag.startswith("Audio") else "?"
        inner = grp.find("TrackGroup")
        tl = (inner if inner is not None else grp).find("Tracks")
        if tl is None:
            continue
        for i, tr in enumerate(tl):
            trk = deref(tr, by_id, by_uid)
            if trk is None:
                continue
            ci = trk.find(".//ClipItems/TrackItems")
            items = []
            if ci is not None:
                for ref in ci.findall("TrackItem"):
                    it = deref(ref, by_id, by_uid)
                    if it is not None:
                        items.append(it)
            out.append((kind, i + 1, trk, items))
    return out


def bounds(item, by_id, by_uid):
    """(start_s, end_s, Start element, End element) of a track clip."""
    holder = item
    for tag in ("ClipTrackItem", "TrackItem"):
        nxt = holder.find(tag)
        if nxt is not None:
            holder = nxt
    # Premiere omits tags that hold the default value: a clip that starts at 0 has
    # no <Start>. We create it so that we can write on it.
    s, e = holder.find("Start"), holder.find("End")
    if s is None:
        s = ET.SubElement(holder, "Start")
        s.text = "0"
    if e is None:
        return None
    return int(s.text or 0) / TICKS, int(e.text) / TICKS, s, e


def media_name(item, by_id, by_uid, depth=0):
    """Name of the source file behind a track clip."""
    # Direct path first: SubClip > (Video|Audio)Clip > Clip > Source > MediaSource > Media.
    # The depth-first walk below can, on an AUDIO clip, hit a shared object first
    # (Essential Sound settings) and return the media of another clip.
    sc = deref(item.find(".//SubClip"), by_id, by_uid)
    vc = deref(sc.find("Clip"), by_id, by_uid) if sc is not None else None
    c = vc.find("Clip") if vc is not None else None
    src = deref(c.find("Source"), by_id, by_uid) if c is not None else None
    med = deref(src.find(".//Media"), by_id, by_uid) if src is not None else None
    if med is not None:
        for tag in ("FilePath", "Title"):
            t = med.find(tag)
            if t is not None and t.text:
                return Path(t.text).name
    seen = set()
    stack = [item]
    while stack and len(seen) < 400:
        el = stack.pop()
        if id(el) in seen:
            continue
        seen.add(id(el))
        if el.tag in ("Media", "MasterClip", "VideoClip", "AudioClip", "Clip", "SubClip",
                      "ClipTrackItem", "TrackItem", "VideoClipTrackItem", "AudioClipTrackItem"):
            fp = el.find("FilePath") or el.find(".//FilePath")
            if fp is not None and fp.text:
                return Path(fp.text).name
            nm = el.find("Name")
            if nm is not None and nm.text and ("." in nm.text):
                return nm.text
        for ch in el:
            d = deref(ch, by_id, by_uid)
            if d is not None:
                stack.append(d)
            else:
                stack.append(ch)
    return None
