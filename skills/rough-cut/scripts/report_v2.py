#!/usr/bin/env python3
"""Rough-cut report v2 (take selection): what goes, what is left to decide, with the
EDIT times (the ones the editor sees in the sequence) and the clip times.
Several clips = one single sequence end to end (merge_xml.py), cumulated times.

    python3 report_v2.py --title "My video" --out report.md \\
        [--notes notes.md] work_folder_clip1 [work_folder_clip2 ...]

notes.md (optional) is appended as is at the end: "kept on purpose", points to watch
that are specific to the video.
"""
import argparse
import json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--title", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--notes")
ap.add_argument("work", nargs="+")
a = ap.parse_args()


def mmss(t):
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


rows, flags, head = [], [], []
offset = tot_rush = tot_cut_takes = 0.0
n_takes = n_clips = 0
for wd in a.work:
    W = Path(wd)
    meta = json.loads((W / "meta.json").read_text())
    DUR = meta["duration_seconds"]
    rush = Path(meta["rush_path"]).stem
    final = json.loads((W / "cuts_final.json").read_text())["cuts"]
    sem = json.loads((W / "cuts_semantic.json").read_text())["cuts"]
    dis = sorted((c for c in final if c["decision"] == "disable"), key=lambda c: c["start"])
    keep, t = [], 0.0
    for c in dis:
        if c["start"] - t > 0.07:
            keep.append((t, c["start"]))
        t = max(t, c["end"])
    if DUR - t > 0.07:
        keep.append((t, DUR))

    def montage(ts):
        acc = 0.0
        for s, e in keep:
            if ts < s:
                return offset + acc
            if ts <= e:
                return offset + acc + ts - s
            acc += e - s
        return offset + acc

    for c in sem:
        if c["decision"] == "disable":
            n_takes += 1
            tot_cut_takes += c["end"] - c["start"]
            suite = c.get("garde_ensuite", "")
            rows.append(f"| {mmss(montage(c['start']))} | {rush} {mmss(c['start'])} | {c['end'] - c['start']:.1f} s | "
                        f"{c['type']} | {c['reason']}" + (f" → resumes at: \"{' '.join(suite.split()[:6])}...\"" if suite else "") + " |")
        else:
            flags.append(f"| {mmss(montage(c['start']))} | {rush} {mmss(c['start'])} | {c['reason']} |")
    kept = sum(e - s for s, e in keep)
    head.append(f"- {rush}: {DUR / 60:.1f} min of footage, {kept / 60:.1f} min kept, {len(keep)} clips "
                f"(from {mmss(offset)} to {mmss(offset + kept)} in the sequence).")
    offset += kept
    tot_rush += DUR
    n_clips += len(keep)

md = [f"# Rough cut v1: {a.title}", "",
      f"- Footage: {tot_rush / 60:.1f} min. Edit: **{offset / 60:.1f} min**, {n_clips} clips, one single sequence.",
      *head,
      f"- {n_takes} failed or repeated takes removed ({tot_cut_takes:.0f} s), the rest is silences of reading notes.",
      f"- {len(flags)} red marker(s): passages kept, for you to decide.", ""]
if flags:
    md += ["## To decide (red markers in the sequence)", "",
           "| In the edit | In the clip | Passage and why the doubt |", "|---|---|---|", *flags, ""]
md += ["## Takes removed (the last one is always kept)", "",
       "| In the edit | In the clip | Duration | Type | What goes, and where it resumes |", "|---|---|---|---|---|", *rows, ""]
if a.notes:
    md += [Path(a.notes).read_text().strip(), ""]
Path(a.out).write_text("\n".join(md))
print(f"{a.out}: {n_takes} takes, {len(flags)} doubts, edit {offset / 60:.1f} min")
