#!/usr/bin/env python3
"""Transcript in SEQUENCE time, read from the .prproj the editor has validated.

Rule zero of the skill: never lay overlays on the cuts of the rough cut, always on the
sequence as it stands in the Premiere project after its pass. This script reads the rush
clips placed in the sequence (start/end in the sequence, in/out points in the rush),
derives the rush -> sequence map from them, and carries over the words of the rush's
transcript (words_premiere.json from the rough cut, already aligned on the audio).

    python3 timeline-from-prproj.py <rush> [<rush 2> …] [--prproj X.prproj] [--sequence NAME]
        [--words words_premiere.json] [--list] [--out-dir FOLDER] [--sans-calage]

Several rushes in one sequence: pass them
all; the outputs carry the name of the FIRST, each timeline clip names its `media` and
each word its `media`. `preview-sequence.py` and `qc-sequence.py derive` read them.

Words are re-aligned on their ACOUSTIC start, measured in the rush, if the median gap
exceeds 40 ms (see calage_acoustique; typically around -27 ms: nothing to fix).

Outputs, next to the rush:
    <rush>_transcription.json   {words: [{word, start, end, rush}], sequence, duration}
    <rush>_timeline.json        [{seq_in, seq_out, src_in, src_out}]

Exit codes: 0 ok; 2 ambiguous or missing sequence (the list is shown);
3 the project contains no clip of the rush.
"""
import argparse
import gzip
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TICKS = 254016000000  # Premiere ticks per second


def calage_acoustique(rush, words):
    """Median gap between the true acoustic start of the words and the transcript's,
    measured on words preceded by at least 150 ms of silence (clean onset); returned in
    seconds if significant (>= 40 ms, at least 15 words), otherwise 0.
    A late transcript costs twice: the animation lands late, and the sound effect
    (+2 frames of offset) even more so, beyond the perceptible threshold (125 ms, ITU
    BT.1359). Measured once: -27 ms over 164 words, Premiere is accurate; whisper,
    for its part, dates words ~170 ms too EARLY (its own bias, not the transcript's)."""
    import subprocess
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(rush), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    au = np.frombuffer(raw, np.float32)
    ecarts = []
    for prev, w in zip(words, words[1:]):
        gap = w["start"] - prev["end"]
        if gap < 0.15:
            continue
        i0 = int((w["start"] - 0.2) * 16000)
        seg = au[max(0, i0):i0 + int(0.6 * 16000)]
        if i0 < 0 or len(seg) < 9000:
            continue
        db = 10 * np.log10((seg[:len(seg) // 80 * 80].reshape(-1, 80) ** 2).mean(1) + 1e-10)   # 5 ms
        # search AFTER the end of the previous word (otherwise, on a short pause, we pick up its
        # tail and think the word is ~120 ms early: a false alarm)
        k0 = int(max(0.0, 0.2 - gap + 0.03) / 0.005)
        lo = db[k0:40]
        if len(lo) < 6:
            continue
        floor = np.percentile(lo, 30)
        if db.max() - floor < 18:
            continue
        ecarts.append(-0.2 + (k0 + int(np.argmax(db[k0:] > floor + 10))) * 0.005)
    if len(ecarts) < 15:
        print(f"  acoustic alignment: only {len(ecarts)} measurable words, transcript left as is")
        return 0.0
    med = float(np.median(ecarts))
    if abs(med) < 0.04:
        print(f"  acoustic alignment: {med * 1000:+.0f} ms over {len(ecarts)} words, nothing to fix")
        return 0.0
    med = max(-0.3, min(0.3, med))
    print(f"  acoustic alignment: words shifted by {med * 1000:+.0f} ms (median over {len(ecarts)} clean onsets, "
          f"quartiles {np.percentile(ecarts, 25) * 1000:+.0f} / {np.percentile(ecarts, 75) * 1000:+.0f} ms)")
    return round(med, 3)


def load(prproj):
    with gzip.open(prproj, "rb") as f:
        root = ET.fromstring(f.read())
    by_id, by_uid = {}, {}
    for el in root.iter():
        if el.get("ObjectID"):
            by_id[el.get("ObjectID")] = el
        if el.get("ObjectUID"):
            by_uid[el.get("ObjectUID")] = el
    return root, by_id, by_uid


def deref(el, by_id, by_uid):
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


def video_tracks(seq, by_id, by_uid):
    """[[clip, ...], ...]: the video tracks of the sequence, from V1 upward."""
    out = []
    tg = seq.find("TrackGroups")
    if tg is None:
        return out
    for tgi in tg.findall("TrackGroup"):
        grp = deref(tgi.find("Second"), by_id, by_uid)
        if grp is None:
            grp = deref(tgi, by_id, by_uid)
        if grp is None or not grp.tag.startswith("Video"):
            continue
        inner = grp.find("TrackGroup")
        tl = (inner if inner is not None else grp).find("Tracks")
        if tl is None:
            continue
        for tr in tl:
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
            out.append(items)
    return out


def clip_info(item, by_id, by_uid):
    """(sequence start, sequence end, rush in, rush out, media name) in seconds."""
    holder = item
    for tag in ("ClipTrackItem", "TrackItem"):
        nxt = holder.find(tag)
        if nxt is not None:
            holder = nxt
    s, e = holder.find("Start"), holder.find("End")
    if e is None:
        return None
    sc = deref(item.find(".//SubClip"), by_id, by_uid)
    vc = deref(sc.find("Clip"), by_id, by_uid) if sc is not None else None
    c = vc.find("Clip") if vc is not None else None
    if c is None:
        return None
    ip, op = c.find("InPoint"), c.find("OutPoint")
    src = deref(c.find("Source"), by_id, by_uid)
    med = deref(src.find(".//Media"), by_id, by_uid) if src is not None else None
    name = None
    if med is not None:
        for tag in ("FilePath", "Title"):
            t = med.find(tag)
            if t is not None and t.text:
                name = Path(t.text.replace("\\", "/")).name
                break
    return (int(s.text or 0) / TICKS if s is not None else 0.0, int(e.text) / TICKS,
            int(ip.text or 0) / TICKS if ip is not None else 0.0,
            int(op.text) / TICKS if op is not None and op.text else None, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rush", nargs="+")
    ap.add_argument("--prproj")
    ap.add_argument("--sequence")
    ap.add_argument("--words")
    ap.add_argument("--list", action="store_true", help="List the sequences and exit")
    ap.add_argument("--out-dir", help="Output folder (default: next to the rush)")
    ap.add_argument("--sans-calage", action="store_true",
                    help="do not re-align the words on the acoustic start measured in the rush")
    a = ap.parse_args()

    rushes = [Path(r).resolve() for r in a.rush]
    rush = rushes[0]
    if len(rushes) > 1 and a.words:
        sys.exit("ERROR: --words only applies to a single rush")
    prproj = Path(a.prproj) if a.prproj else next(iter(sorted(
        rush.parent.glob("*.prproj"), key=lambda p: p.stat().st_mtime, reverse=True)), None)
    if prproj is None:
        print("ERROR: no .prproj next to the rush", file=sys.stderr)
        sys.exit(2)
    root, by_id, by_uid = load(prproj)

    def candidats(r):
        cands = []
        for seq in root.iter("Sequence"):
            n = seq.find(".//Name")
            name = n.text if n is not None else "?"
            best = None
            for items in video_tracks(seq, by_id, by_uid):       # the lowest track that carries the rush
                clips = [ci for ci in (clip_info(it, by_id, by_uid) for it in items) if ci and ci[4] == r.name]
                if clips:
                    best = sorted(clips)
                    break
            if best:
                cands.append((name, best))
        if not cands:
            print(f"ERROR: no sequence of {prproj.name} contains {r.name}", file=sys.stderr)
            sys.exit(3)
        print(f"{prproj.name}: sequences containing {r.name}")
        for name, clips in cands:
            print(f"  {name!r:40} {len(clips):3d} clips, ends at {clips[-1][1]:.1f} s")
        return cands

    par_rush = [(r, candidats(r)) for r in rushes]
    if a.list:
        return
    if a.sequence:
        name = a.sequence
    else:
        communes = set.intersection(*({c[0] for c in cands} for _, cands in par_rush))
        if len(communes) != 1:
            print("ERROR: several possible sequences, specify --sequence", file=sys.stderr)
            sys.exit(2)
        name = communes.pop()

    tl, out, sources, calages, n_src = [], [], [], [], 0
    for r, cands in par_rush:
        pick = [c for c in cands if c[0] == name]
        if not pick:
            print(f"ERROR: sequence {name!r} not found for {r.name}", file=sys.stderr)
            sys.exit(2)
        tl_r = []
        for s, e, i, o, _ in pick[0][1]:
            if o is None:
                o = i + (e - s)
            if abs((o - i) - (e - s)) > 0.05:
                print(f"  ⚠️  clip at {s:.2f} s: sequence duration {e - s:.2f} s != source duration {o - i:.2f} s "
                      "(speed changed?), words carried over proportionally")
            tl_r.append({"seq_in": round(s, 4), "seq_out": round(e, 4), "src_in": round(i, 4), "src_out": round(o, 4),
                         "media": r.name})
        tl += tl_r
        o_r, wpath, calage, n = mots_du_rush(r, tl_r, a)
        out += o_r
        sources.append(wpath.name)
        calages.append(round(calage * 1000))
        n_src += n
    tl.sort(key=lambda c: c["seq_in"])
    for c1, c2 in zip(tl, tl[1:]):
        if c2["seq_in"] < c1["seq_out"] - 1e-3:
            sys.exit(f"ERROR: two rush clips overlap at {c2['seq_in']:.2f} s ({c1['media']} / {c2['media']})")
    out.sort(key=lambda w: w["start"])
    dur = tl[-1]["seq_out"]
    out_dir = Path(a.out_dir) if a.out_dir else rush.parent
    (out_dir / f"{rush.stem}_transcription.json").write_text(json.dumps(
        {"sequence": name, "duration": round(dur, 3), "source": ", ".join(sources),
         "calage_ms": calages[0] if len(calages) == 1 else calages,
         "rushes": [r.name for r in rushes], "words": out}, ensure_ascii=False))
    (out_dir / f"{rush.stem}_timeline.json").write_text(json.dumps(tl, indent=0))
    kept = sum(c["seq_out"] - c["seq_in"] for c in tl)
    print(f"Sequence {name!r}: {len(tl)} clips, {dur / 60:.2f} min ({kept / 60:.2f} min of rush), "
          f"{len(out)} words of {n_src} carried over")
    print(f"  -> {rush.stem}_transcription.json, {rush.stem}_timeline.json")


def mots_du_rush(rush, tl, a):
    """Words of the rush carried over into sequence time (with its acoustic alignment)."""
    wpath = Path(a.words) if a.words else next(iter(sorted(
        rush.parent.glob(f"{rush.stem}_Derush_v*_work/words_premiere.json"), reverse=True)), None)
    if wpath is None or not wpath.exists():
        print(f"ERROR: words_premiere.json not found for {rush.name} (pass --words)", file=sys.stderr)
        sys.exit(2)
    src_words = json.loads(wpath.read_text())
    calage = 0.0 if a.sans_calage else calage_acoustique(rush, src_words)
    if calage:
        src_words = [{**w, "start": w["start"] + calage, "end": w["end"] + calage} for w in src_words]
    out = []
    for w in src_words:
        # A word goes to the clip that contains its middle (duration capped: word ends
        # overrun). Failing that, to the clip where it STARTS, if at least 80 ms remain: the editor
        # cuts right at the end of sentences and Premiere dates the last words too long;
        # the middle rule alone dropped the last word of several sentences,
        # and the demos aligned on them broke.
        mid = (w["start"] + min(w["end"], w["start"] + 0.6)) / 2
        c = next((c for c in tl if c["src_in"] <= mid < c["src_out"]), None) or \
            next((c for c in tl if c["src_in"] <= w["start"] < c["src_out"] - 0.08), None)
        if c is None:
            continue
        k = (c["seq_out"] - c["seq_in"]) / max(1e-6, c["src_out"] - c["src_in"])
        st = c["seq_in"] + (max(w["start"], c["src_in"]) - c["src_in"]) * k
        en = c["seq_in"] + (min(w["end"], c["src_out"]) - c["src_in"]) * k
        out.append({"word": w.get("text", w.get("word", "")), "start": round(st, 3),
                    "end": round(max(en, st + 0.01), 3), "rush": round(w["start"], 3), "media": rush.name})
    return out, wpath, calage, len(src_words)


if __name__ == "__main__":
    main()
