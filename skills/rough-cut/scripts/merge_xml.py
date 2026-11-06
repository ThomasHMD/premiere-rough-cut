#!/usr/bin/env python3
"""Joins several rough cuts (one XML per clip) into ONE Premiere sequence, end to end,
in the given order. For a video shot in several clips.

    python3 merge_xml.py <output.xml> "<sequence name>" a_Derush_v1.xml b_Derush_v1.xml

Each clip keeps its <file> (ids renamed), the clips of the next one are shifted by the
duration of the previous one, and so are the markers. Same self-check as build_premiere_xml.py.
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

out, name, inputs = Path(sys.argv[1]), sys.argv[2], [Path(p) for p in sys.argv[3:]]
base = ET.parse(inputs[0]).getroot()
seq = base.find("sequence")
seq.set("id", name)
seq.find("name").text = name
tracks = seq.find("media/video").findall("track") + seq.find("media/audio").findall("track")


def seq_end(s):
    return max(int(c.find("end").text) for c in s.iter("clipitem"))


offset = seq_end(seq)
for k, path in enumerate(inputs[1:], start=2):
    other = ET.parse(path).getroot().find("sequence")
    for f in other.iter("file"):
        f.set("id", f"r{k}-{f.get('id')}")
    for c in other.iter("clipitem"):
        c.set("id", f"r{k}-{c.get('id')}")
        c.find("name").text = f"r{k}_{c.find('name').text}"
        for tag in ("start", "end"):
            c.find(tag).text = str(int(c.find(tag).text) + offset)
    otracks = other.find("media/video").findall("track") + other.find("media/audio").findall("track")
    if len(otracks) != len(tracks):
        sys.exit(f"ERROR: {path.name} does not have the same number of tracks as {inputs[0].name}")
    for bt, ot in zip(tracks, otracks):
        anchor = list(bt).index(bt.find("enabled"))
        for j, c in enumerate(ot.findall("clipitem")):
            bt.insert(anchor + j, c)
    for m in other.findall("marker"):
        for tag in ("in", "out"):
            m.find(tag).text = str(int(m.find(tag).text) + offset)
        seq.append(m)
    offset = seq_end(seq)
seq.find("duration").text = str(offset)

errors = []
for t in tracks:
    prev = 0
    for c in t.findall("clipitem"):
        i_f, o_f, s_f, e_f = (int(c.find(x).text) for x in ("in", "out", "start", "end"))
        if o_f - i_f < 1 or (o_f - i_f) != (e_f - s_f) or s_f < prev:
            errors.append(f"{c.find('name').text}: in={i_f} out={o_f} start={s_f} end={e_f}")
        prev = e_f
ids = [c.get("id") for c in seq.iter("clipitem")]
if len(ids) != len(set(ids)):
    errors.append("duplicate clip ids")
if errors:
    print("ERROR: invalid sequence, XML not written:", *errors[:10], sep="\n  ", file=sys.stderr)
    sys.exit(1)
pretty = minidom.parseString(ET.tostring(base, encoding="utf-8")).toprettyxml(indent="  ", encoding="UTF-8").decode()
lines = [l for l in pretty.splitlines() if l.strip()]
lines.insert(1, "<!DOCTYPE xmeml>")
out.write_text("\n".join(lines))
fps = 30000 / 1001
print(f"{out.name}: sequence \"{name}\", {len(inputs)} clips, {len(ids) // len(tracks)} clips per track, "
      f"{offset / fps / 60:.2f} min, {len(seq.findall('marker'))} markers")
