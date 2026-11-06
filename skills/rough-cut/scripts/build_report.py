#!/usr/bin/env python3
"""Generates a readable markdown report of the proposed cuts.

Usage:
    python3 build_report.py cuts_final.json meta.json output.report.md
"""
import json
import sys
from collections import Counter
from pathlib import Path


def fmt_ts(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:06.3f}"
    return f"{m:02d}:{s:06.3f}"


def fmt_duration(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}min {s:04.1f}s"


def main():
    if len(sys.argv) != 4:
        print("Usage: build_report.py <cuts_final.json> <meta.json> <output.report.md>",
              file=sys.stderr)
        sys.exit(1)

    data = json.loads(Path(sys.argv[1]).read_text())
    meta = json.loads(Path(sys.argv[2]).read_text())
    out = Path(sys.argv[3])

    cuts = data["cuts"]
    stats = data["stats"]
    rush_name = Path(meta["rush_path"]).name

    by_type = Counter(c["type"] for c in cuts if c["decision"] == "disable")
    flag_by_type = Counter(c["type"] for c in cuts if c["decision"] == "flag")

    lines = []
    lines.append(f"# Rough-cut report: {rush_name}")
    lines.append("")
    lines.append(f"**Version**: Derush_v{meta.get('version', 1)}")
    lines.append(f"**Whisper model**: {meta.get('model', 'large-v3-turbo')}")
    lines.append(f"**Clip duration**: {fmt_duration(meta['duration_seconds'])}")
    lines.append(f"**Frame rate**: {meta['fps']:.3f} fps")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Disabled cuts** (automatic): {stats['cuts_disabled']}")
    lines.append(f"- **Red markers** (to review): {stats['cuts_flagged']}")
    lines.append(f"- **Time saved**: {fmt_duration(stats['time_removed_seconds'])} "
                 f"({stats['ratio'] * 100:.1f}% of the clip)")
    lines.append(f"- **Resulting duration**: "
                 f"{fmt_duration(stats['duration_seconds'] - stats['time_removed_seconds'])}")
    lines.append("")

    lines.append("## Disabled cuts by type")
    lines.append("")
    if by_type:
        for typ, n in by_type.most_common():
            lines.append(f"- **{typ}**: {n}")
    else:
        lines.append("(no disabled cut)")
    lines.append("")

    if flag_by_type:
        lines.append("## Red markers by type (to review in Premiere)")
        lines.append("")
        for typ, n in flag_by_type.most_common():
            lines.append(f"- **{typ}**: {n}")
        lines.append("")

    # Detail of the flag markers (useful for the review)
    flagged = [c for c in cuts if c["decision"] == "flag"]
    if flagged:
        lines.append("## Red markers in detail")
        lines.append("")
        lines.append("| Timecode | Type | Confidence | Reason |")
        lines.append("|---|---|---|---|")
        for c in sorted(flagged, key=lambda c: c["start"]):
            lines.append(f"| {fmt_ts(c['start'])} | {c['type']} | "
                         f"{c['confidence']:.2f} | {c['reason']} |")
        lines.append("")

    # Top 10 longest cuts (useful to spot the bad good ideas)
    disabled = [c for c in cuts if c["decision"] == "disable"]
    if disabled:
        lines.append("## Top 10 longest disabled cuts")
        lines.append("")
        lines.append("| Timecode | Duration | Type | Confidence | Reason |")
        lines.append("|---|---|---|---|---|")
        top = sorted(disabled, key=lambda c: -(c["end"] - c["start"]))[:10]
        for c in top:
            d = c["end"] - c["start"]
            lines.append(f"| {fmt_ts(c['start'])} | {fmt_duration(d)} | {c['type']} | "
                         f"{c['confidence']:.2f} | {c['reason'][:80]} |")
        lines.append("")

    lines.append("## How to use this rough cut in Premiere")
    lines.append("")
    lines.append("1. `File > Import` the `.xml` next to this report")
    lines.append("2. A new `Derush_v{version}` sequence appears in the project"
                 .replace("{version}", str(meta.get("version", 1))))
    lines.append("3. The cut passages have been **removed from the edit**: the clips are "
                 "already end to end, nothing to close up. To find a cut passage again, "
                 "see its source timecode in this report")
    lines.append("4. The **red markers** point out the doubtful zones, left in the "
                 "edit. Click one to see the reason + confidence score")
    lines.append("5. The original clip has not been modified. This sequence only references it")
    lines.append("")

    out.write_text("\n".join(lines))
    print(f"Report written: {out}")


if __name__ == "__main__":
    main()
