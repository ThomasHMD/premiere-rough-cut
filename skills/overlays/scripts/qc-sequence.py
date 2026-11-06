#!/usr/bin/env python3
"""Acceptance tests for an overlaid sequence, before showing it to the editor. Born from the
feedback on the first preview of a video. Each test exits with code 1 if it fails.

    python3 qc-sequence.py derive <clip> <preview.mp4>       voice of the preview vs the clip, per segment: |offset| <= 20 ms
    python3 qc-sequence.py flash  <preview.mp4> <base.mp4>   face visible <= 6 frames between two blocks: 0
    python3 qc-sequence.py tenue  <premiere-sequence.xml>    real on-screen time of each element: none under the threshold
    python3 qc-sequence.py camera <props.json>...            demo camera: 0 zoom back-and-forth, 0 gesture late by > 0.5 s
    python3 qc-sequence.py mots   <preview.mp4> <transcript.json>   whisper on the preview vs the plan's words: no drift
    python3 qc-sequence.py planches <preview.mp4> <xml> <folder> [animation-script.json transcript.json]
                                                            contact sheets to look at (no automatic verdict)
    python3 qc-sequence.py bords  <renders .mp4/.mov>...     accent element cut by the frame edge: 0
    python3 qc-sequence.py zooms  <preview.mp4> <base.mp4> <xml>   zooms and framings on the speaker's camera synced to the voice: ±1 frame
    python3 qc-sequence.py coupes <xml> <clip>_timeline.json   block or zoom edge 1-6 frames on the wrong side of the speaker's cuts: 0
    python3 qc-sequence.py scenes <preview.mp4> <animation-script.json> <folder>
                                                            contact sheets INSIDE the scenes, one thumbnail per moment

- derive: "the further along, the more it drifts". Correlation of the voice over 2.5 s in the middle
  of each segment of <clip>_timeline.json.
- flash: "between two animations, my face sometimes shows for one frame". <base.mp4> =
  talking-head alone (preview-sequence.py --garder-base). A frame where more than 60% of the pixels
  equal the base shows the face; a run of 6 frames or fewer between two covered
  frames is a flash. Causes met: a demo shorter than its window (hence
  `--minDuration`), a badly composed preview (see preview-sequence.py).
- tenue: "animations that last the length of a word". Placed duration minus what the
  tracks above cover (wipes included). Thresholds: full-screen and demos 2.5 s,
  overlays 2.0 s. And no camera return shorter than 1.2 s between two blocks (hard
  cut, face barely seen: found by eye on a video, invisible to the flash test).
- camera: "it zooms, zooms out, changes area, zooms in again, where it could glide". Reads the
  props.json of the render (folder .rec-<id>/render/): movements, pauses, zoom back-and-forths
  less than 3 s apart; and, in recording.json, the anchored gestures that started late (the
  render then speeds up the footage to catch up: jittery).
- mots: "when I say free, it is "ended" that shows up". INDEPENDENT check of the
  transcript the plan takes its moments from: whisper listens again to 8 excerpts of 12 s spread over
  the whole preview, and each recognized word is compared with the same word in the transcript.
  Whisper dates words ~170 ms too EARLY (constant bias, measured on a video against the acoustic
  start): the test judges the DRIFT, not the absolute offset. Fails if an excerpt departs by
  more than 150 ms from the median of the excerpts (offset appearing mid-video) or if
  that median leaves [-300, +100] ms (global offset).
- zooms: "a zoom on me while I am not talking", "out of sync with the voice, it is a disaster". Each clip of the
  source placed above its V1 (punch-in, book framing) is searched for
  in the base (the speaker's talking-head, no zoom) shifted from -1 s to +1 s: at fixed scale,
  each frame of the preview is shrunk by 1/k and run through matchTemplate; at animated scale, the motion
  signature (difference between successive frames). Best offset outside ±1 frame = failure. The
  XML must first pass `garde_premiere.py` (CALAGE): this test proves that the PREVIEW shows what
  Premiere will show (a preview that numbers its frames wrongly reproduces or invents an offset).
- coupes: "after a cut, one frame slipped through", "zoom badly timed". The speaker's cuts =
  edges of the clips of <clip>_timeline.json, on the sequence grid (29.97). An opaque block (b-rolls, demos,
  full-screen, merged when they touch) that enters 1 to 6 frames AFTER a cut shows the previous shot;
  one that leaves 1 to 6 frames BEFORE a cut shows the face for a flash. Same for each zoom on the
  speaker's camera (the zoom ends on its cut). Engine: `habillage.coupes()`.
- planches: the by-eye pass. One row per talking-head ↔ full-screen block junction (frames
  -10, -4, 0, +4, +10 around the cut); with the script and the transcript, one thumbnail
  per slammed word (stamp, slam) 0.3 s after it lands, captioned with the word said at that moment.
"""
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import numpy as np


def fps_de(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip()
    return float(Fraction(r))


def derive(rush, apercu):
    from scipy.signal import correlate
    rush = Path(rush)
    tl = json.loads((rush.parent / f"{rush.stem}_timeline.json").read_text())

    def dec(f, ss, t):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, ss):.3f}", "-i", str(f), "-vn", "-ac", "1",
                            "-ar", "8000", "-t", f"{t:.3f}", "-f", "f32le", "-"], capture_output=True).stdout
        return np.frombuffer(r, np.float32).astype(float)

    pire = 0.0
    for c in tl:
        if c["seq_out"] - c["seq_in"] < 4:
            continue
        t = (c["seq_in"] + c["seq_out"]) / 2
        src = rush.with_name(c["media"]) if c.get("media") else rush   # sequence with several clips
        r0 = c["src_in"] + t - c["seq_in"] - 1.25
        if r0 < 0:                         # (same guard on the clip side)
            continue
        ref = dec(src, r0, 2.5)
        g0 = max(0.0, t - 3.25)          # a segment at the very start: the window does not begin before 0
        got = dec(apercu, g0, 6.5)
        if len(got) < len(ref) or ref.std() == 0:
            continue
        ref = (ref - ref.mean()) / ref.std()
        x = correlate(got, ref, mode="valid", method="fft")
        e = np.sqrt(np.convolve(got ** 2, np.ones(len(ref)), "valid")) + 1e-9
        ncc = x / e / np.sqrt(len(ref))
        k = int(np.argmax(ncc))
        lag = (k / 8000 - (t - 1.25 - g0)) * 1000
        if ncc[k] > 0.5:
            pire = max(pire, abs(lag))
        print(f"segment {c['seq_in']:7.1f}-{c['seq_out']:7.1f} s: voice {lag:+5.0f} ms (corr {ncc[k]:.2f})")
    print(f"max offset: {pire:.0f} ms")
    return pire <= 20


def flash(apercu, base):
    W, H = 240, 136

    def frames(f):
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(f), "-vf", f"scale={W}:{H},format=gray", "-f",
                              "rawvideo", "-"], stdout=subprocess.PIPE)
        while True:
            b = p.stdout.read(W * H)
            if len(b) < W * H:
                return
            yield np.frombuffer(b, np.uint8).astype(np.int16)

    fps = fps_de(apercu)
    face = np.array([float((np.abs(a - b) < 12).mean()) for a, b in zip(frames(apercu), frames(base))])
    vis = face > 0.6
    runs, i = [], 0
    while i < len(vis):
        if vis[i]:
            j = i
            while j < len(vis) and vis[j]:
                j += 1
            av, ap = face[max(0, i - 3):i], face[j:j + 3]
            if len(av) and len(ap) and av.max() < 0.4 and ap.max() < 0.4 and j - i <= 6:
                runs.append((i, j))
            i = j
        else:
            i += 1
    # the reverse: a block that holds only 1 to 3 frames in the middle of the talking-head
    cache, eclairs, i = face < 0.1, [], 0
    while i < len(cache):
        if cache[i]:
            j = i
            while j < len(cache) and cache[j]:
                j += 1
            av, ap = face[max(0, i - 6):max(0, i - 3)], face[j + 3:j + 6]
            if j - i <= 3 and len(av) and len(ap) and av.min() > 0.6 and ap.min() > 0.6:
                eclairs.append((i, j))
            i = j
        else:
            i += 1
    for i, j in runs:
        print(f"face {j - i} frame(s) at {i / fps:8.3f} s (frames {i}-{j - 1})")
    for i, j in eclairs:
        print(f"flash of {j - i} frame(s) on the talking-head at {i / fps:8.3f} s (frames {i}-{j - 1})")
    print(f"{len(runs)} face flash(es), {len(eclairs)} flash(es) over {len(face)} frames")
    return not runs and not eclairs


def pistes_video(seq):
    """Video tracks of the XML, WITHOUT the speaker-camera zoom track (enlarged pieces of the clip, placed just above
    the V1): these are cuts of the speaker's shot, not elements to read, and the QCs number the tracks from
    V2 = b-rolls and demos, V3 = full-screen, V4 = overlays."""
    out = []
    for tr in seq.find("media/video").findall("track"):
        its = tr.findall("clipitem")
        noms = {it.findtext("name") for it in its}
        # one or several clips (one zoom in clip B, the others in clip A), never an ANIM render
        zooms = its and all(
            any(p.findtext("parameterid") == "scale" for p in it.iter("parameter")) for it in its) \
            and all(not n.startswith("ANIM") and n.upper().endswith((".MOV", ".MP4")) for n in noms)
        if not zooms or not out:   # the first track (the speaker's V1) is always kept
            out.append(tr)
    return out


def tenue(xml):
    seuil = {2: 2.5, 3: 2.5, 4: 2.0}   # V2 demos and b-rolls, V3 full-screen, V4 overlays
    seq = ET.parse(xml).getroot().find(".//sequence")
    fps = float(seq.findtext("rate/timebase")) * (1000 / 1001 if seq.findtext("rate/ntsc") == "TRUE" else 1)
    tracks = []
    for tr in pistes_video(seq):
        tracks.append([(int(it.findtext("start")), int(it.findtext("end")), it.findtext("name") or "?",
                        it.findtext("alphatype") == "straight")
                       for it in tr.findall("clipitem")
                       if int(it.findtext("start")) >= 0 and it.findtext("enabled") != "FALSE"])

    def vu(a, b, couvre):
        cur, v = a, 0
        for s, e in sorted((max(a, s), min(b, e)) for s, e in couvre if e > a and s < b):
            v += max(0, s - cur)
            cur = max(cur, e)
        return v + max(0, b - cur)

    court = []
    for k, clips in enumerate(tracks, start=1):
        if k not in seuil:
            continue
        # a transparent overlay (stamp, retro screen placed on a stack of cards) does not hide what is under it
        dessus = [(s, e) for cl in tracks[k:] for s, e, _, alpha in cl if not alpha]
        for s, e, n, _ in clips:
            if "volet" in n:   # intended 0.5 s transition, on the overlays track
                continue
            v = vu(s, e, dessus) / fps
            if v < seuil[k]:
                court.append((s / fps, k, n, (e - s) / fps, v))
    for t, k, n, d, v in sorted(court):
        print(f"{int(t // 60):02d}:{t % 60:05.2f}  V{k}  {n[:40]:40s} placed {d:5.2f} s, seen {v:5.2f} s")
    print(f"{len(court)} element(s) under the threshold")
    # flash camera returns: less than 1.2 s of face between two full-screen blocks (V2 and V3)
    pl = sorted((s, e) for cl in tracks[1:3] for s, e, _, _ in cl)
    cover = []
    for s, e in pl:
        if cover and s <= cover[-1][1] + 1:
            cover[-1][1] = max(cover[-1][1], e)
        else:
            cover.append([s, e])
    eclairs = [(b, a2) for (_, b), (a2, _) in zip(cover, cover[1:]) if (a2 - b) / fps < 1.2]
    for b, a2 in eclairs:
        t = b / fps
        print(f"{int(t // 60):02d}:{t % 60:05.2f}  camera return of {(a2 - b) / fps:.2f} s between two blocks")
    print(f"{len(eclairs)} camera return(s) shorter than 1.2 s")
    return not court and not eclairs


def camera(*props):
    ok = True
    for f in props:
        p = json.loads(Path(f).read_text())
        fps, cam = p["fps"], np.array(p["cam"])
        ls = np.log(cam[:, 0])
        dz = np.abs(np.diff(ls)) * fps
        dp = np.hypot(np.diff(cam[:, 1]), np.diff(cam[:, 2])) * fps / 1920
        moving = (dz > 0.08) | (dp > 0.04)
        segs, i = [], 0
        while i < len(moving):
            if moving[i]:
                j = i
                while j < len(moving) and moving[j]:
                    j += 1
                segs.append((i, j))
                i = j
            else:
                i += 1
        pauses = [(b[0] - a[1]) / fps for a, b in zip(segs, segs[1:])]
        sens = np.sign(np.diff(ls))
        sens[dz < 0.08] = 0
        ev = [(i, int(v)) for i, v in enumerate(sens) if v != 0 and (i == 0 or sens[i - 1] != v)]
        ar = sum(1 for a, b in zip(ev, ev[1:]) if a[1] != b[1] and (b[0] - a[0]) / fps < 3)
        dur = len(cam) / fps
        nom = Path(f).parent.parent.name if Path(f).parent.name == "render" else f
        print(f"{nom}: {dur:5.1f} s, {len(segs)} movements ({len(segs) / dur * 60:.0f}/min), "
              f"pauses < 1 s: {sum(1 for h in pauses if h < 1)}, zoom back-and-forths: {ar}")
        # gesture anchored on a word but started late: the render speeds up the footage to catch up
        rec = Path(f).parent.parent / "recording.json"
        late = [x for x in (json.loads(rec.read_text()).get("late") or []) if x[1] > 0.5] if rec.exists() else []
        if late:
            print(f"   gestures late by more than 0.5 s (step, s): {late}: shorten the scenario lead-in")
        ok &= ar == 0 and not late
    return ok


def mots(apercu, transcription, n=8, fen=30, decalages=(0.0, 0.4, 0.8)):
    # The median of a window varied by ±150 ms from one whisper pass to the next (same
    # window at 43.2 s: -278 then -76 ms; shifted by 0.4 s: -223 ms), while `derive`
    # measured the voice to 1 ms on each segment. Hence windows of 30 s (12 before: ±400 ms
    # in passages heavy with sound effects) and, for each one, three passes shifted by
    # 0.4 s whose offsets are pooled: whisper noise no longer passes for drift.
    import re
    import tempfile
    import unicodedata
    norm = lambda w: re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode().lower())
    tr = json.loads(Path(transcription).read_text())
    ref = [(norm(w["word"]), w["start"]) for w in tr["words"]]
    langue = tr.get("language") or "auto"   # short windows: detection is unreliable, reuse the rush language
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(apercu)], capture_output=True, text=True).stdout)
    if dur < 90:   # 14 s excerpts spread over the video: on a short clip they overlap
        print(f"preview of {dur:.0f} s: too short for this check (90 s at least), not measured")
        return True
    modele = Path.home() / "Models/whisper/ggml-large-v3-turbo.bin"
    tmp = Path(tempfile.mkdtemp(prefix="qc-mots-"))
    ok, meds = True, []
    for k in range(n):
        base = (dur - fen - 2 - max(decalages)) * (k + 0.5) / n
        ecarts = []
        for j, d in enumerate(decalages):
            t0 = base + d
            wav = tmp / f"x{k}-{j}.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-i", str(apercu), "-t", str(fen), "-vn",
                            "-ac", "1", "-ar", "16000", str(wav)], check=True)
            subprocess.run(["whisper-cli", "-m", str(modele), "-f", str(wav), "-l", langue, "-ml", "1", "-sow", "-oj",
                            "-of", str(tmp / f"x{k}-{j}"), "-np"], check=True, capture_output=True)
            segs = json.loads((tmp / f"x{k}-{j}.json").read_text(errors="ignore"))["transcription"]
            for sg in segs:
                w = norm(sg["text"])
                if len(w) < 4:          # short words: too many neighboring homophones
                    continue
                t = t0 + sg["offsets"]["from"] / 1000
                cands = [r for x, r in ref if x == w and abs(r - t) < 4]
                if cands:
                    ecarts.append(t - min(cands, key=lambda r: abs(r - t)))
            for f in tmp.iterdir():
                f.unlink()
        if len(ecarts) < 5 * len(decalages):
            print(f"excerpt {base:6.1f} s: only {len(ecarts)} word(s) recognized")
            ok = False
            continue
        med = float(np.median(ecarts)) * 1000
        meds.append(med)
        print(f"excerpt {base:6.1f} s: {len(ecarts):3d} words ({len(decalages)} passes), median offset {med:+5.0f} ms")
    tmp.rmdir()
    if meds:
        g = float(np.median(meds))
        pire = max(abs(m - g) for m in meds)
        print(f"median of the excerpts {g:+.0f} ms (whisper bias), largest gap from that median {pire:.0f} ms")
        ok &= -300 <= g <= 100 and pire <= 150
    return ok


def planches(apercu, xml, dossier, script=None, transcription=None):
    from PIL import Image, ImageDraw, ImageFont
    fps = fps_de(apercu)
    out = Path(dossier)
    out.mkdir(parents=True, exist_ok=True)
    # folder synced by the cloud sync: overwrite the sheets in place and delete only
    # the extra ones (a file deleted then recreated makes the sync create conflict copies)
    anciennes = set(out.glob("planche-*.jpg"))
    seq = ET.parse(xml).getroot().find(".//sequence")
    tr = pistes_video(seq)
    pl = sorted((int(it.findtext("start")), int(it.findtext("end"))) for t in tr[1:3] for it in t.findall("clipitem")
                if int(it.findtext("start")) >= 0 and it.findtext("enabled") != "FALSE")
    cover = []
    for a, b in pl:
        if cover and a <= cover[-1][1] + 1:
            cover[-1][1] = max(cover[-1][1], b)
        else:
            cover.append([a, b])
    tc = lambda n: f"{int(n / fps // 60):02d}:{n / fps % 60:05.2f}"
    rows = []
    for a, b in cover:
        # the wipe lasts 15 frames centered on the cut: -10 and +10 show the before and the after
        rows.append((f"block in {tc(a)}  (frames -10, -4, 0, +4, +10)", [a - 10, a - 4, a, a + 4, a + 10]))
        rows.append((f"block out {tc(b)}  (frames -10, -4, 0, +4, +10)", [b - 10, b - 4, b, b + 4, b + 10]))
    claques = []
    if script and transcription:
        words = json.loads(Path(transcription).read_text())["words"]
        for sg in json.loads(Path(script).read_text())["segments"]:
            if sg.get("component") not in ("stamp", "slam", "stamp-rain"):
                continue
            m, sec = sg["timecode"].split(":")
            t0 = int(m) * 60 + float(sec)
            for c in sg.get("cues") or []:
                t = t0 + c + 0.3
                # the word being said at the cue instant: the last one started (within 50 ms)
                dit = next((w["word"] for w in reversed(words) if w["start"] <= t0 + c + 0.05), "?")
                claques.append((f"{sg.get('id')} {tc(round(t * fps))} \"{dit}\"", round(t * fps)))
    for i in range(0, len(claques), 5):
        rows.append(("slammed words", [n for _, n in claques[i:i + 5]], [l for l, _ in claques[i:i + 5]]))
    need = set(n for r in rows for n in r[1] if n >= 0)
    # sequential read of the preview: exact frame indices, like the flash test
    dims = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", str(apercu)], capture_output=True, text=True).stdout.strip().split(",")
    Wv = 320
    Hv = round(Wv * int(dims[1]) / int(dims[0]) / 2) * 2
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(apercu), "-vf", f"scale={Wv}:{Hv}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    imgs, n = {}, 0
    while need - set(imgs):
        buf = p.stdout.read(Wv * Hv * 3)
        if len(buf) < Wv * Hv * 3:
            break
        if n in need:
            imgs[n] = Image.frombytes("RGB", (Wv, Hv), buf)
        n += 1
    p.kill()
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
    W, H = Wv, Hv
    par = 10
    feuilles = []
    for k in range(0, len(rows), par):
        bloc = rows[k:k + par]
        sheet = Image.new("RGB", (5 * (W + 6) + 6, len(bloc) * (H + 30) + 6), (120, 120, 120))
        d = ImageDraw.Draw(sheet)
        for r, row in enumerate(bloc):
            y = 6 + r * (H + 30)
            d.text((8, y), row[0] if len(row) == 2 else "", fill=(20, 20, 20), font=font)
            for c, n in enumerate(row[1]):
                if n in imgs:
                    d.rectangle([5 + c * (W + 6), y + 21, 6 + c * (W + 6) + W, y + 22 + H], outline=(255, 255, 255))
                    sheet.paste(imgs[n], (6 + c * (W + 6), y + 22))
                if len(row) == 3:
                    d.text((8 + c * (W + 6), y + 2), row[2][c][:44], fill=(20, 20, 20), font=font)
        f = out / f"planche-{k // par + 1:02d}.jpg"
        sheet.save(f, quality=85)
        feuilles.append(f)
    for f in anciennes - set(feuilles):     # no stale sheet from a previous pass
        f.unlink()
    print(f"{len(cover)} blocks, {len(claques)} slammed words -> {len(feuilles)} sheets in {out}")
    return True


def bords(*fichiers):
    """Accent-colored element (stamp, pill, highlight, frame) cut by the frame edge:
    4 frames per second of each render at 960x540, 3 px band on the four edges,
    held for two frames in a row (the entrance of a stamp, 0.14 s magnified 2.6 times, is not a defect).
    The color is read from the workshop theme (`accent` in theme.ts). Wipes (intended accent
    edge) are excluded. On one video, 4 files were found, all invisible on the junction
    contact sheets."""
    W, H, B = 960, 540, 3
    theme = Path(__file__).resolve().parents[2] / "motion-design/src/illustration/theme.ts"
    m = re.search(r'accent:\s*"#([0-9A-Fa-f]{6})"', theme.read_text()) if theme.exists() else None
    acc = np.array([int((m.group(1) if m else "2F5BEA")[k:k + 2], 16) for k in (0, 2, 4)], np.int16)
    edge = np.zeros((H, W), bool)
    edge[:B] = edge[-B:] = True
    edge[:, :B] = edge[:, -B:] = True
    bad = 0
    for f in fichiers:
        if "volet" in Path(f).name:
            continue
        p = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-vf", f"fps=4,scale={W}:{H}", "-f", "rawvideo",
                            "-pix_fmt", "rgba", "-"], capture_output=True)
        a = np.frombuffer(p.stdout, np.uint8)
        n = a.size // (W * H * 4)
        if n == 0:
            print(f"?? {f}: no frame read")
            bad += 1
            continue
        a = a[: n * W * H * 4].reshape(n, H, W, 4)
        proche = (np.abs(a[..., :3].astype(np.int16) - acc).max(axis=-1) < 60) & (a[..., 3] > 128)
        hits = (proche & edge).sum(axis=(1, 2))
        tenu = np.minimum(hits[:-1], hits[1:]) if n > 1 else hits
        i = int(tenu.argmax())
        if tenu[i] > 6:
            bad += 1
            print(f"!! {Path(f).name:<40} {int(tenu[i])} px of accent at the edge at {i / 4:.1f} s")
    print(f"{bad} file(s) with an accent element cut at the edge")
    return bad == 0


def scenes(apercu, script, dossier):
    """The by-eye pass INSIDE the scenes: one thumbnail 0.8 s after each moment of a scene
    (step placed, note, stamp, line), plus one at 40% and one at the end. The junction
    sheets only see entrances and exits: on one video, notes placed on the text in a
    tight shot, stamps cut at the edge and cut lines did not show up there."""
    import tempfile
    from PIL import Image, ImageDraw, ImageFont
    out = Path(dossier)
    out.mkdir(parents=True, exist_ok=True)
    sec = lambda tc: int(tc.split(":")[0]) * 60 + float(tc.split(":")[1])
    shots = []
    for sg in json.loads(Path(script).read_text())["segments"]:
        if sg.get("type") != "scene":
            continue
        t0, dur = sec(sg["timecode"]), sg["durationSec"]
        ts = {round(min(dur - 0.4, c + 0.8), 2) for c in sg.get("cues", []) if isinstance(c, (int, float)) and 0 <= c < dur}
        ts |= {round(dur * 0.4, 2), round(dur - 0.4, 2)}
        shots += [(sg["id"], t, t0 + t) for t in sorted(ts)]
    W, H, COLS, ROWS = 384, 216, 6, 6
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
    except Exception:
        font = ImageFont.load_default()
    tmp = Path(tempfile.mkdtemp(prefix="qc-scenes-")) / "_f.jpg"   # outside the synced folder
    pages = [shots[i:i + COLS * ROWS] for i in range(0, len(shots), COLS * ROWS)]
    for p, page in enumerate(pages, 1):
        sheet = Image.new("RGB", (COLS * (W + 6) + 6, ROWS * (H + 26) + 6), (110, 110, 110))
        d = ImageDraw.Draw(sheet)
        for i, (sid, t, ts) in enumerate(page):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{ts:.3f}", "-i", str(apercu), "-frames:v", "1",
                            "-vf", f"scale={W}:{H}", str(tmp)], check=True)
            x, y = 6 + (i % COLS) * (W + 6), 6 + (i // COLS) * (H + 26)
            d.text((x, y), f"{sid} +{t:.1f}s", fill=(255, 255, 255), font=font)
            sheet.paste(Image.open(tmp), (x, y + 20))
        sheet.save(out / f"scenes-{p:02d}.jpg", quality=86)
    tmp.unlink(missing_ok=True)
    tmp.parent.rmdir()
    print(f"{len(shots)} thumbnails, {len(pages)} sheets in {out}")
    return True


def zooms(apercu, base, xml):
    import cv2
    W, H, M = 320, 180, 30
    def images(f, t0, d):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.4f}", "-i", str(f), "-t", f"{d:.4f}", "-vf",
                            f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        return np.frombuffer(r, np.uint8).reshape(-1, H, W)
    def signature(a):
        return np.abs(np.diff(a.astype(float), axis=0)).mean(axis=(1, 2))
    seq = ET.parse(xml).getroot().find(".//sequence")
    fps = int(seq.findtext("rate/timebase"))
    gardees = pistes_video(seq)
    clips = [it for tr in seq.find("media/video").findall("track") if tr not in gardees for it in tr.findall("clipitem")]
    if not clips:
        print("no zoom on the camera in this XML")
        return True
    mauvais = 0
    for it in clips:
        s, e = int(it.findtext("start")) / fps, int(it.findtext("end")) / fps
        t0, d = s + 0.1, min(e - s - 0.2, 4.0)
        a, b = images(apercu, t0, d), images(base, t0 - M / fps, d + 2 * M / fps)
        n = len(a)
        par = it.find(".//parameter[parameterid='scale']")
        cles = [x for x in par.findall("keyframe") if 0 <= int(x.findtext("when")) < round((e - s) * fps)]
        if len(cles) <= 1:
            k = float(cles[0].findtext("value") if cles else par.findtext("value")) / 100
            tpl = [cv2.resize(x, (round(W / k), round(H / k)), interpolation=cv2.INTER_AREA) for x in a]
            sc = [(float(np.mean([cv2.matchTemplate(b[M + j + i], tpl[i], cv2.TM_CCOEFF_NORMED).max() for i in range(n)])), j)
                  for j in range(-M, M + 1) if M + j + n <= len(b)]
            seuil, mode = 0.6, f"image k={k:.2f}"   # motion blur, dim light: 0.75 to 0.9 at the right moment
        else:
            sa, sb = signature(a), signature(b)
            sc = [(float(np.corrcoef(sa, sb[M + j:M + j + n - 1])[0, 1]), j)
                  for j in range(-M, M + 1) if M + j + n - 1 <= len(sb)]
            seuil, mode = 0.5, "motion"
        score, j = max(sc)
        ok = abs(j) <= 1 and score > seuil
        mauvais += not ok
        print(f"  {int(s // 60)}:{s % 60:06.3f} → {int(e // 60)}:{e % 60:06.3f}  {mode:12}  offset {j:+d} frames "
              f"(score {score:.3f})  {'OK' if ok else 'OFFSET'}")
    print(f"{len(clips)} zooms, {mauvais} offset")
    return mauvais == 0


def coupes(xml, timeline, marge=6):
    seq = ET.parse(xml).getroot().find(".//sequence")
    fps = float(seq.findtext("rate/timebase")) * (1000 / 1001 if seq.findtext("rate/ntsc") == "TRUE" else 1)
    cuts = sorted({round(t * fps) for c in json.load(open(timeline)) for t in (c["seq_in"], c["seq_out"])})
    gardees = pistes_video(seq)
    pistes = seq.find("media/video").findall("track")
    clip = lambda it: int(it.findtext("start")) >= 0 and it.findtext("enabled") != "FALSE"
    opaques = sorted((int(it.findtext("start")), int(it.findtext("end"))) for tr in gardees[1:]
                     for it in tr.findall("clipitem") if clip(it) and it.findtext("alphatype") != "straight")
    blocs = []
    for s, e in opaques:
        if blocs and s <= blocs[-1][1]:
            blocs[-1][1] = max(blocs[-1][1], e)
        else:
            blocs.append([s, e])
    zooms = [(int(it.findtext("start")), int(it.findtext("end"))) for tr in pistes if tr not in gardees
             for it in tr.findall("clipitem") if clip(it)]
    fautes = []
    for quoi, bords in (("bloc", blocs), ("zoom", zooms)):
        for a, b in bords:
            fautes += [(a / fps, f"{quoi} entered {a - c} frame(s) after its cut") for c in cuts if 0 < a - c <= marge]
            fautes += [(b / fps, f"{quoi} left {c - b} frame(s) before its cut") for c in cuts if 0 < c - b <= marge]
    for t, m in sorted(fautes):
        print(f"  {int(t // 60)}:{t % 60:05.2f}  {m}")
    print(f"{len(blocs)} blocks, {len(zooms)} zooms, {len(cuts)} cuts: {len(fautes)} edge(s) 1-{marge} frames on the wrong side")
    return not fautes


if __name__ == "__main__":
    test = {"derive": derive, "flash": flash, "tenue": tenue, "camera": camera, "mots": mots, "planches": planches,
            "bords": bords, "scenes": scenes, "zooms": zooms, "coupes": coupes}[sys.argv[1]]
    ok = test(*sys.argv[2:])
    print("OK" if ok else "FAIL")
    sys.exit(0 if ok else 1)
