#!/usr/bin/env python3
"""Renders the segments of an animation-script.json through Remotion and produces a Premiere XML.

Pipeline:
1. Reads <clip>_animation-script.json (next to the clip)
2. For each segment:
   - motion (premium)        -> BrandedVideo composition    -> opaque mp4
   - lower-third             -> LowerThirdTrack composition -> ProRes alpha mov
   - section-title           -> LowerThirdTrack composition -> ProRes alpha mov
   - scene                   -> Scene composition: animated overlays synced to the voice
                                (`component`, `data`, `cues` in seconds from the start
                                of the scene). `alpha: false` -> opaque mp4 (V5),
                                `alpha: true` -> ProRes 4444 mov (V6). `sfx` = list
                                [{file, at, gainDb}] mixed into one WAV per scene.
                                Render is cached: only the modified scenes are
                                rendered (--force to redo everything, --only to target).
3. Checks the timecodes against <clip>_transcription.json if present
4. Generates "<number> Illustration V1.xml" (FCP7 xmeml v5, sequence of the same name; renders in "... - rendus/",
   sounds in "... - sons.md") with:
   - V2: b-rolls (<clip>_broll-script.json): skipped if they overlap a photo
   - V3: illustration photos (<clip>_photos-script.json, take priority over the b-rolls)
   - V5: premium tracks (opaque)
   - V6: lower-third + section-title tracks (alpha)

Usage:
    python3 render-segments.py /path/clip.mp4
    python3 render-segments.py /path/clip.mp4 --premiums-only
    python3 render-segments.py /path/clip.mp4 --lower-thirds-only
    python3 render-segments.py /path/clip.mp4 --skip-verify
    python3 render-segments.py /path/clip.mp4 --en-place sous-titres   # one scene redone at the same path
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import json
import re
import subprocess
import sys
import unicodedata
import urllib.parse
import uuid
from datetime import date
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
# The Remotion project, the scenes, the fonts and the sounds live in the motion-design workshop:
# this skill only places and edits.
ATELIER = SKILL_ROOT.parent / "motion-design"
REMOTION_ENTRY = str(ATELIER / "src" / "index.ts")
SFX_DIR = ATELIER / "public" / "sfx"


def _empreinte_code() -> str:
    """Fingerprint of the Remotion sources of the overlays: a tweak to a component (a removed
    logo, say) invalidates the cache. Before, the key only followed the props, and a
    file rendered with the old code stayed in place without warning."""
    h = hashlib.sha1()
    src = ATELIER / "src"
    for f in sorted([src / "index.ts", src / "Root.tsx", *(src / "illustration").rglob("*")]):
        if f.is_file() and f.suffix in (".ts", ".tsx", ".css", ".json"):
            h.update(str(f.relative_to(src)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:12]


CODE = _empreinte_code()
DEFAULT_FPS = 30
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080

# Default SFX mapping (track A3 of the XML, plays in parallel with the overlay)
# Override: `sfxDefaults` in the JSON, or `sfx: {file: ..., gainDb: ...}` per segment
# Default sound identity (../motion-design/reference/sound-palette.md).
# The old sounds (Ding, whoosh-high/low, ding.wav) stay in public/sfx/: you go
# back to them through `sfxDefaults` in the JSON.
DEFAULT_SFX_MAPPING = {
    "lower-third": "pose-1.wav",
    "section-title": "page.wav",
    "motion": "accord.wav",
}

# SFX placed at the start of each photo whose name matches (book covers,
# magazines): rule extracted from a finished edit.
PHOTO_SFX_NAME = "page.wav"


def timbre(name: str) -> Path:
    """The file of a sound named without a folder: the one in the default timbres (`public/sfx/defaut.json`, key `timbres`:
    real recordings) if they have it, otherwise the one in `public/sfx/`. Same rule as `son.py`."""
    try:
        t = json.loads((SFX_DIR / "defaut.json").read_text()).get("timbres") or ""
    except (OSError, ValueError):
        t = ""
    if t and "/" not in name and (SFX_DIR / t / name).exists():
        return SFX_DIR / t / name
    return SFX_DIR / name
PHOTO_SFX_PATTERN = re.compile(r"cover|book|magazine|couverture|livre", re.I)  # fr-ok: French file names too

# 1 Premiere second = 254,016,000,000 ticks (pproTicksIn/Out of the FCP7 XML)
TICKS_PER_SEC = 254_016_000_000


def nom_livraison(base_dir: Path, base: str, version: str) -> str:
    """Readable name of a delivery, the one the editor looks for in the Finder and in Premiere: "<number> Illustration V1"
    (number read from the name of the video folder, otherwise the clip name). It replaced technical names
    such as premiere-sequence-<clip>.xml, animations-<clip>/, sons-<clip>.md and the sequence <clip>_ILLU_AUTO."""
    m = re.match(r"Vid[ée]o (\d+)", base_dir.name)  # fr-ok
    return f"{m.group(1) if m else base} Illustration {version.upper()}"


def slugify(s: str, max_len: int = 40) -> str:
    """ASCII-safe, lowercase, hyphens, at most max_len. Keeps no accent."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:max_len].rstrip("-") or "x"


def fmt_tc(seconds: float) -> str:
    """02:14: minutes:seconds."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}m{s:02d}s"


def tc_to_seconds(tc: str) -> float:
    """02:14 or 1:23:45 -> seconds."""
    parts = tc.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return float(tc)


def verify_timecodes(script: dict, transcript_path: Path) -> None:
    """Prints a check/warning/question mark per segment depending on whether the timecode lands on a word of the transcript."""
    if not transcript_path.exists():
        print(f"  (no transcript: {transcript_path.name}: check skipped)")
        return
    transcript = json.loads(transcript_path.read_text())
    words = transcript.get("words", [])
    if not words:
        return

    def word_at(seconds: float, tol: float = 1.0):
        for w in words:
            if abs(w["start"] - seconds) <= tol:
                return w
        return None

    for i, seg in enumerate(script.get("segments", []), start=1):
        tc = seg.get("timecode")
        if not tc or tc == "??":
            print(f"  ❓ #{i:02d}: no timecode")
            continue
        s = tc_to_seconds(tc)
        w = word_at(s)
        if w:
            print(f"  ✅ #{i:02d} {tc} → \"{w['word']}\" @ {w['start']:.2f}s")
        else:
            print(f"  ⚠️  #{i:02d} {tc} ({s:.1f}s) → no word within ±1s")


# NTSC flag of the SEQUENCE (29.97 / 59.94 / 23.976). Set in main() from
# the clip. Without it, a 29.97 sequence was written as ntsc=FALSE and every
# placement computed at integer fps: 0.1% drift, ~1 s of offset after
# 16 min.
SEQ_NTSC = False
# 4K sequence (Tella-style edit): the scenes are drawn at 1920×1080; they are
# rendered at 1920×1080 with --scale=2 (Chrome rasterizes at 4K: sharp text), never at
# 3840×2160 directly (everything would be half size, the wipes would cross twice too fast).
RENDER_SCALE = 1


def frames_son(path: Path, fps: int) -> int:
    """Duration of a sound in sequence frames, rounded down: a clip never asks for
    more than its file (round(duration × 30) overshot at 29.97)."""
    return max(1, math.floor(probe_audio_duration(path) * fps * (1000.0 / 1001.0 if SEQ_NTSC else 1.0)))


def seq_frames(seconds: float, fps: int) -> int:
    """Seconds of timeline -> frame number, taking NTSC into account."""
    return round(seconds * fps * (1000.0 / 1001.0 if SEQ_NTSC else 1.0))


def frames_couverts(start_frame: int, end_frame: int, fps: int) -> tuple[int, int]:
    """(animation frames, held end frames) so that a render at `fps` covers ALL of its clip
    [start, end[ in the sequence. At 29.97, n sequence frames last n × 1.001 / 30 s: a
    render of round(duration × 30) frames ended up to 2 frames before its clip, and Premiere
    showed the track below (often the face) on those frames. An ffmpeg preview
    that repeated the last frame hid the defect. The held end frames
    (TenirFin on the Remotion side) cover Premiere's rounding, nearest or
    down, plus one of margin; the guard checks the coverage in the XML."""
    n = max(1, end_frame - start_frame)
    ratio = 1001 / 1000 if SEQ_NTSC else 1.0
    main = max(1, round(n * ratio))
    need = math.ceil((n - 1) * ratio + 0.5) + 1
    return main, max(0, need - main) + 1


def calc_frames(seg_dur_sec: float, fps: int) -> tuple[int, int]:
    """Frame range for a segment rendered on its own: 0 → ceil(dur*fps) - 1."""
    n = max(1, round(seg_dur_sec * fps))
    return 0, n - 1


def write_segment_props(seg: dict, fps: int, width: int, height: int, tmp_path: Path,
                        tail: int = 0) -> None:
    """Creates a mini animation-script with a SINGLE segment (for an isolated render)."""
    mini = {
        "version": 1,
        "fps": fps,
        "width": width,
        "height": height,
        "segments": [seg],
        "tailFrames": tail,
    }
    tmp_path.write_text(json.dumps(mini, ensure_ascii=False))


def fichier_de_travail(dossier: Path, nom: str) -> Path:
    """Path of a work file (props, render in progress). If the video folder is
    synced (Dropbox, iCloud, Drive...), a file that grows then disappears can make the
    sync fail: the MONTAGE_DEPOT environment variable then points to a NON-synced
    folder on the same disk (the final rename stays atomic). Without it: a
    hidden file in the video folder."""
    depot = os.environ.get("MONTAGE_DEPOT")
    if depot and Path(depot).is_dir():
        d = Path(depot) / f"{date.today():%Y-%m-%d}-rendus"
        d.mkdir(exist_ok=True)
        return d / f"{uuid.uuid4().hex[:8]}-{nom}"
    return dossier / f".{nom}"


def texte_scene(data: dict) -> str:
    """A few words of what a scene shows (title, lines, figure), for the sound report."""
    bouts = []
    for k in ("eyebrow", "name", "title", "text", "term", "quote", "label", "value"):
        v = data.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip():
            bouts.append(str(v).strip())
    bouts += [str(x.get("text")) for x in data.get("lines") or [] if isinstance(x, dict) and x.get("text")]
    t = " · ".join(bouts)
    return f' "{t[:70]}{"…" if len(t) > 70 else ""}"' if t else ""


def ecrire_releve(releve: list[tuple], rush: Path, chemin: Path) -> None:
    """'<number> Illustration V1 - sons.md' and .json next to the XML: each sound numbered, its moment, what you see, what is said (motion-design,
    son.releve). You answer by numbers ("remove: 3, 17 to 19"); a corrected plan rewrites them at the next edit."""
    sys.path.insert(0, str(ATELIER / "scripts"))
    import son  # noqa: E402
    tr = rush.with_name(rush.stem + "_transcription.json")
    mots = json.loads(tr.read_text()).get("words", []) if tr.exists() else []
    son.releve(releve, mots, chemin, rush.stem)
    print(f"Sound report: {chemin.name}.md ({len(releve)} sounds, to comment by number)")


def run_remotion(composition: str, frames: tuple[int, int], output: Path, props_file: Path,
                 alpha: bool = False, remplacer: bool = True) -> Path:
    """Renders into a work file then puts it in place of `output`; with remplacer=False,
    renders the work file without putting anything in place (--en-place checks its format first)."""
    tmp = fichier_de_travail(output.parent, f"rendu-{output.name}")
    cmd = [
        "npx", "remotion", "render", REMOTION_ENTRY, composition,
        f"--frames={frames[0]}-{frames[1]}",
        f"--output={tmp}",
        f"--props={props_file}",
        "--muted",
        "--log=warn",
        # The workshop renders in jpeg on 8 cores by default: here png (quality) and 4 cores.
        "--image-format=png",
        "--concurrency=4",
    ]
    if RENDER_SCALE != 1:
        cmd.append(f"--scale={RENDER_SCALE}")
    if alpha:
        cmd += [
            "--codec=prores", "--prores-profile=4444",
            "--pixel-format=yuva444p10le",
        ]
    else:
        cmd += ["--codec=h264", "--crf=18"]

    print(f"    → {output.name}")
    result = subprocess.run(cmd, cwd=ATELIER, capture_output=True, text=True)
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        print(f"  ERROR remotion render:\n{result.stderr[-2000:]}", file=sys.stderr)
        sys.exit(1)
    if not remplacer:
        return tmp
    # Atomic replacement: Premiere (open on these files) never sees a half-written file,
    # and keeps the same name (it reloads the media without reimport).
    os.replace(tmp, output)
    return output


def run_scene(props_file: Path, n_frames: int, output: Path, alpha: bool) -> None:
    """Renders a scene (Scene composition). Opaque: h264. Transparent: ProRes 4444."""
    run_remotion("Scene", (0, n_frames - 1), output, props_file, alpha=alpha)


def props_scene(seg: dict, n_frames: int, tail: int, fps: int, width: int, height: int) -> dict:
    """Props of a scene rendered alone (Scene composition): the same for the normal render and --en-place."""
    return {"component": seg["component"], "data": seg.get("data") or {},
            "cues": seg.get("cues") or [], "durationSec": n_frames / fps,
            "tailFrames": tail, "fps": fps, "width": width // RENDER_SCALE, "height": height // RENDER_SCALE}


FORMAT_CLES = ("codec_name", "profile", "codec_tag_string", "pix_fmt", "width", "height", "r_frame_rate", "nb_frames")


def format_media(path: Path) -> dict:
    """What must stay identical for Premiere to reread a replaced media without reimport or offset:
    codec, profile, alpha (pix_fmt), dimensions, frame rate, frame count, duration."""
    d = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=" + ",".join(FORMAT_CLES), "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout)
    st = d["streams"][0]
    return {**{k: str(st.get(k, "")) for k in FORMAT_CLES}, "duration": f"{float(d['format']['duration']):.3f}"}


def ecarts_format(avant: dict, apres: dict) -> list[str]:
    return [f"{k}: {avant[k]} → {apres.get(k)}" for k in avant if avant[k] != apres.get(k)]


def corbeille(path: Path) -> Path:
    """Moves a file to the Mac trash by a plain rename (instant, even on 1 GB):
    ~/.Trash on the startup disk, <volume>/.Trashes/<uid> on another disk."""
    if path.stat().st_dev == Path.home().stat().st_dev:
        poubelle = Path.home() / ".Trash"
    else:
        vol = path.resolve()
        while vol.parent != vol and vol.parent.stat().st_dev == path.stat().st_dev:
            vol = vol.parent
        poubelle = vol / ".Trashes" / str(os.getuid())
        poubelle.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest = poubelle / path.name
    if dest.exists():
        dest = poubelle / f"{path.stem} {uuid.uuid4().hex[:6]}{path.suffix}"
    os.rename(path, dest)
    return dest


def refaire_en_place(seg: dict, props: dict, n_frames: int, out_file: Path, alpha: bool) -> None:
    """--en-place: renders ONE scene and replaces its file at the same path, touching nothing else
    (no other render, no XML, no sound report). Refuses if the new render does not have exactly the
    format of the old one (Premiere rereads it without reimport only if identical). The old one goes to the
    trash. Born from a subtitle font change: font changed, nothing else."""
    if not out_file.exists():
        print(f"ERROR --en-place: {out_file.name} does not exist yet (first render: without --en-place)", file=sys.stderr)
        sys.exit(1)
    avant = format_media(out_file)
    print(f"  before: {avant}")
    props_file = fichier_de_travail(out_file.parent, f"props-{out_file.stem}.json")
    props_file.write_text(json.dumps(props, ensure_ascii=False, sort_keys=True))
    print(f"  rendering {seg.get('id')} ({n_frames} frames)")
    tmp = run_remotion("Scene", (0, n_frames - 1), out_file, props_file, alpha=alpha, remplacer=False)
    props_file.unlink(missing_ok=True)
    ecarts = ecarts_format(avant, format_media(tmp))
    if ecarts:
        tmp.unlink(missing_ok=True)
        print("ERROR --en-place: the new render does not have the format of the old one, nothing replaced:", file=sys.stderr)
        for e in ecarts:
            print(f"  ✗ {e}", file=sys.stderr)
        sys.exit(1)
    jete = corbeille(out_file)
    os.replace(tmp, out_file)
    apres = format_media(out_file)
    if ecarts_format(avant, apres):
        print(f"ERROR --en-place: format changed after placing: {ecarts_format(avant, apres)}", file=sys.stderr)
        sys.exit(1)
    print(f"  after: identical ({avant['codec_name']} {avant['profile']}, {avant['pix_fmt']}, "
          f"{avant['width']}×{avant['height']}, {avant['r_frame_rate']}, {avant['nb_frames']} frames, {avant['duration']} s)")
    print(f"  ✅ {out_file.name} replaced in place; the old one is in the trash ({jete})")


def mix_scene_sfx(sfx: list[dict], out_wav: Path) -> bool:
    """Mixes the sound effects of a scene into a single 48 kHz stereo WAV (one clip on the
    sound track instead of ten: readable in Premiere, and muted with one click).
    Each entry: {file, at (s from the start of the scene), gainDb}."""
    items = []
    for x in sfx:
        f = SFX_DIR / x["file"]
        if not f.exists():
            print(f"  ⚠️  sound effect not found: {x['file']}", file=sys.stderr)
            continue
        items.append((f, max(0.0, float(x.get("at", 0))), float(x.get("gainDb", 0))))
    if not items:
        return False
    cmd = ["ffmpeg", "-v", "error", "-y"]
    chains, labels = [], []
    for i, (f, at, gain) in enumerate(items):
        cmd += ["-i", str(f)]
        ms = round(at * 1000)
        # mono -> stereo without loss (ffmpeg's mixer takes off 3 dB): the files of the
        # palette are written at the exact level they must sound under the voice
        st = ("pan=stereo|c0=c0|c1=c0" if probe_audio_meta(f)["channels"] == 1
              else "aformat=channel_layouts=stereo")
        chains.append(f"[{i}:a]aresample=48000,{st},volume={gain}dB,adelay={ms}|{ms}[a{i}]")
        labels.append(f"[a{i}]")
    chains.append(f"{''.join(labels)}amix=inputs={len(items)}:normalize=0:dropout_transition=0,"
                  "alimiter=limit=0.89:level=disabled[out]")
    cmd += ["-filter_complex", ";".join(chains), "-map", "[out]", "-c:a", "pcm_s24le", str(out_wav)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ERROR sound effects mix:\n{r.stderr[-800:]}", file=sys.stderr)
        sys.exit(1)
    return True


def layer_split(clips: list[dict]) -> list[list[dict]]:
    """Distributes clips into non-overlapping layers (one track per layer)."""
    layers: list[list[dict]] = []
    for c in sorted(clips, key=lambda x: x["start_frame"]):
        end = c.get("end_frame", c["start_frame"] + c.get("duration_frames", 0))
        for layer in layers:
            last = layer[-1]
            last_end = last.get("end_frame", last["start_frame"] + last.get("duration_frames", 0))
            if c["start_frame"] >= last_end:
                layer.append(c)
                break
        else:
            layers.append([c])
    return layers


def file_url(path: Path) -> str:
    """Encodes a path for FCP7 XML: file://localhost/path%20with%20spaces."""
    enc = urllib.parse.quote(str(path.resolve()).encode("utf-8"), safe="/")
    return f"file://localhost{enc}"


def probe_audio_duration(audio_path: Path) -> float:
    """Duration in seconds of an audio file via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def probe_video_duration(video_path: Path) -> float:
    """Duration in seconds of a video file via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def probe_image_size(image_path: Path) -> tuple[int, int]:
    """(width, height) of an image via sips (native macOS). (0, 0) on failure."""
    try:
        out = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(image_path)],
            capture_output=True, text=True, check=True,
        ).stdout
        w = re.search(r"pixelWidth:\s*(\d+)", out)
        h = re.search(r"pixelHeight:\s*(\d+)", out)
        return (int(w.group(1)) if w else 0, int(h.group(1)) if h else 0)
    except subprocess.CalledProcessError:
        return (0, 0)


def resolve_sfx_for_segment(seg: dict, sfx_overrides: dict) -> Path | None:
    """Determines the SFX file to play for this segment, or None if no sound.

    Precedence: seg.sfx.file > seg.sfx (str) > sfxDefaults[seg.type] > DEFAULT_SFX_MAPPING[seg.type]
    """
    sfx_raw = seg.get("sfx")
    if isinstance(sfx_raw, dict) and sfx_raw.get("file"):
        name = sfx_raw["file"]
    elif isinstance(sfx_raw, str):
        name = sfx_raw
    else:
        name = sfx_overrides.get(seg["type"]) or DEFAULT_SFX_MAPPING.get(seg["type"])
    if not name:
        return None
    candidate = timbre(name)
    return candidate if candidate.exists() else None


def probe_video_meta(video_path: Path) -> dict:
    """Media truth via ffprobe: real timebase/ntsc, frame count, dimensions.

    This was THE bug of one video: the XML declared timebase=60 and duration=placed
    duration for 25/30 fps b-rolls: Premiere then creates a wrongly conformed master clip
    (thumbnail OK, black when the playhead passes). The <file> must tell the
    TRUTH about the media, exactly as a Premiere FCP7 export writes it.
    """
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate,nb_frames,width,height",
         "-show_entries", "format=duration",
         "-of", "json", str(video_path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    stream = data["streams"][0]
    num, den = (int(x) for x in stream["r_frame_rate"].split("/"))
    ntsc = (den == 1001)
    timebase = round(num / den) if ntsc else round(num / den)
    dur_s = float(data["format"]["duration"])
    nb = int(stream.get("nb_frames") or 0) or round(dur_s * num / den)
    return {
        "timebase": timebase, "ntsc": ntsc, "nb_frames": nb,
        "width": int(stream["width"]), "height": int(stream["height"]),
        "duration_s": dur_s,
    }


def probe_audio_meta(audio_path: Path) -> dict:
    """Audio truth: duration, sample rate, channels."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels",
         "-show_entries", "format=duration", "-of", "json", str(audio_path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    stream = data["streams"][0]
    return {
        "duration_s": float(data["format"]["duration"]),
        "samplerate": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
    }


def _white_matte_xml(idx: int, start: int, end: int, dur_s: float) -> str:
    """Full-frame white matte = native Premiere "Color" generatoritem (no PNG).

    Structure copied identically from a Premiere FCP7 export (round trip):
    rate 24 NTSC, in shifted by 1 h (86313 = 3600 s × 23.976), constant duration.
    Placed under each group of photos: the fit-contain photo is displayed on white.
    """
    in_pt = 86313
    out_pt = in_pt + max(1, round(dur_s * 24000 / 1001))
    return f"""
        <generatoritem id="matte_{idx}">
          <name>White matte (for photos)</name>
          <enabled>TRUE</enabled>
          <duration>1035764</duration>
          <start>{start}</start>
          <end>{end}</end>
          <in>{in_pt}</in>
          <out>{out_pt}</out>
          <rate>
            <timebase>24</timebase>
            <ntsc>TRUE</ntsc>
          </rate>
          <effect>
            <name>Color</name>
            <effectid>Color</effectid>
            <effectcategory>Matte</effectcategory>
            <effecttype>generator</effecttype>
            <mediatype>video</mediatype>
            <parameter authoringApp="PremierePro">
              <parameterid>fillcolor</parameterid>
              <name>Color</name>
              <value>
                <alpha>0</alpha>
                <red>255</red>
                <green>255</green>
                <blue>255</blue>
              </value>
            </parameter>
          </effect>
        </generatoritem>"""


def _fit_motion_filter(img_w: int, img_h: int, seq_w: int, seq_h: int) -> str:
    """Full Basic Motion (scale + rotation + center + anchor, Premiere export format)
    so that a still fills the frame as much as possible WITHOUT cropping (fit-contain)."""
    if not img_w or not img_h:
        return ""
    scale = min(seq_w / img_w, seq_h / img_h) * 100.0
    scale = max(1.0, min(round(scale, 4), 1000.0))
    return f"""
          <filter>
            <effect>
              <name>Basic Motion</name>
              <effectid>basic</effectid>
              <effectcategory>motion</effectcategory>
              <effecttype>motion</effecttype>
              <mediatype>video</mediatype>
              <pproBypass>false</pproBypass>
              <parameter authoringApp="PremierePro">
                <parameterid>scale</parameterid>
                <name>Scale</name>
                <valuemin>0</valuemin>
                <valuemax>1000</valuemax>
                <value>{scale}</value>
              </parameter>
              <parameter authoringApp="PremierePro">
                <parameterid>rotation</parameterid>
                <name>Rotation</name>
                <valuemin>-8640</valuemin>
                <valuemax>8640</valuemax>
                <value>0</value>
              </parameter>
              <parameter authoringApp="PremierePro">
                <parameterid>center</parameterid>
                <name>Center</name>
                <value>
                  <horiz>0</horiz>
                  <vert>0</vert>
                </value>
              </parameter>
              <parameter authoringApp="PremierePro">
                <parameterid>centerOffset</parameterid>
                <name>Anchor Point</name>
                <value>
                  <horiz>0</horiz>
                  <vert>0</vert>
                </value>
              </parameter>
            </effect>
          </filter>"""


def _cover_motion_filter(media_w: int, media_h: int, seq_w: int, seq_h: int) -> str:
    """Basic Motion (Scale) fit-COVER: fills the whole frame, cropping the overflow.
    For a horizontal 16:9 b-roll in a vertical 9:16 reel: otherwise it appears
    tiny, surrounded by black bars. Scale = max(W/w, H/h) × 100."""
    if not media_w or not media_h:
        return ""
    scale = max(seq_w / media_w, seq_h / media_h) * 100.0
    scale = max(1.0, min(round(scale, 4), 1000.0))
    if abs(scale - 100.0) < 0.5:
        return ""
    return f"""
          <filter>
            <effect>
              <name>Basic Motion</name>
              <effectid>basic</effectid>
              <effectcategory>motion</effectcategory>
              <effecttype>motion</effecttype>
              <mediatype>video</mediatype>
              <pproBypass>false</pproBypass>
              <parameter authoringApp="PremierePro">
                <parameterid>scale</parameterid>
                <name>Scale</name>
                <valuemin>0</valuemin>
                <valuemax>1000</valuemax>
                <value>{scale}</value>
              </parameter>
            </effect>
          </filter>"""


def _recadrage_filter(scale: float, cles: list[tuple[int, float]], src_w: int, decal: list[int],
                      src_h: int = 0, cy: float | None = None) -> str:
    """Basic Motion of a reframing (9:16 reel pulled from a 16:9 clip): fixed scale,
    horizontal center followed by keyframes. `cles`: (frame since the start of the clip, wanted center x in px
    of the SOURCE). center.horiz = offset in sequence px / width of the SOURCE (real Premiere export,
    see montage-tella.py); each key is written in the references `decal` (start of the clip, <in>, <start>),
    the reference of <when> being undocumented: only the right block falls inside the clip."""
    k = scale / 100.0
    h = lambda cx: round((src_w / 2 - cx) * k / src_w, 5)
    # cy: wanted vertical offset, in SEQUENCE px (negative = upward), divided by the height of the source
    v = round(cy / src_h, 5) if cy and src_h else 0
    val = f"<value><horiz>{h(cles[0][1])}</horiz><vert>{v}</vert></value>"
    kf = "" if len(cles) < 2 else "".join(
        f"<keyframe><when>{d + f}</when><value><horiz>{h(cx)}</horiz><vert>{v}</vert></value></keyframe>"
        for d in decal for f, cx in cles)
    return f"""
          <filter>
            <effect>
              <name>Basic Motion</name>
              <effectid>basic</effectid>
              <effectcategory>motion</effectcategory>
              <effecttype>motion</effecttype>
              <mediatype>video</mediatype>
              <pproBypass>false</pproBypass>
              <parameter authoringApp="PremierePro"><parameterid>scale</parameterid><name>Scale</name><valuemin>0</valuemin><valuemax>1000</valuemax><value>{round(scale, 4)}</value></parameter>
              <parameter authoringApp="PremierePro"><parameterid>center</parameterid><name>Center</name>{val}{kf}</parameter>
            </effect>
          </filter>"""


def _cadre_filter(cles: list[tuple[int, float, float, float]], src_w: int, src_h: int, decal: list[int]) -> str:
    """Animated Basic Motion of a zoom on the speaker's camera (long video: "when I show the books the cam
    has to move onto them"): scale AND center by keyframes. `cles`: (frame since the start of the clip, scale %,
    SOURCE x brought to the center, vertical offset in sequence px). Same `decal` references as
    `_recadrage_filter` (start of the clip, <in>, <start>): they must not overlap, otherwise the keys get mixed."""
    dur = max(f for f, *_ in cles) + 1
    blocs = sorted(decal)
    if any(b - a < dur for a, b in zip(blocs, blocs[1:])):
        raise SystemExit(f"!! animated zoom: keyframe references {decal} less than {dur} frames apart")
    h = lambda k, cx: round((src_w / 2 - cx) * k / 100 / src_w, 5)
    v = lambda cy: round(cy / src_h, 5) if src_h else 0
    kf_s = "".join(f"<keyframe><when>{d + f}</when><value>{round(k, 4)}</value></keyframe>" for d in decal for f, k, _, _ in cles)
    kf_c = "".join(f"<keyframe><when>{d + f}</when><value><horiz>{h(k, cx)}</horiz><vert>{v(cy)}</vert></value></keyframe>"
                   for d in decal for f, k, cx, cy in cles)
    f0, k0, cx0, cy0 = cles[0]
    return f"""
          <filter>
            <effect>
              <name>Basic Motion</name>
              <effectid>basic</effectid>
              <effectcategory>motion</effectcategory>
              <effecttype>motion</effecttype>
              <mediatype>video</mediatype>
              <pproBypass>false</pproBypass>
              <parameter authoringApp="PremierePro"><parameterid>scale</parameterid><name>Scale</name><valuemin>0</valuemin><valuemax>1000</valuemax><value>{round(k0, 4)}</value>{kf_s}</parameter>
              <parameter authoringApp="PremierePro"><parameterid>center</parameterid><name>Center</name><value><horiz>{h(k0, cx0)}</horiz><vert>{v(cy0)}</vert></value>{kf_c}</parameter>
            </effect>
          </filter>"""


def build_xml(rush: Path, rendered: list[dict], sfx_clips: list[dict],
              broll_clips: list[dict], photo_clips: list[dict],
              fps: int, width: int, height: int,
              total_frames: int, out_xml: Path, rush_frames: int = 0,
              rush_pieces: list[dict] | None = None, nom: str = "", voix: dict | None = None,
              zooms: list[dict] | None = None) -> None:
    """Generates an FCP7 xmeml XML importable in Premiere with V1 (clip) + V2
    (b-rolls + white mattes) + V3 (photo stills) + V5 (premiums) + V6 (alpha
    overlays) + A3 (SFX).

    All clipitem structures are copied from an FCP7 export made by
    Premiere itself (round trip, `roundtrip-final2.xml`). Golden rule:
    the <file> block tells the TRUTH about the media (real fps, real duration, real
    dimensions via ffprobe/sips): a lying <file> produces a wrongly conformed
    master clip: thumbnail OK but BLACK when the playhead passes.
    """
    def ticks(frames: int, timebase: int) -> int:
        return round(frames / timebase * TICKS_PER_SEC)

    # Registry of the <file>: a UNIQUE id per file (hash of the path: truncated
    # stems created collisions between different files), defined IN FULL
    # once then referenced `<file id="…"/>` at the next occurrences.
    # Redefining the same id N times (17× whoosh-high…) corrupts the audio master clip
    # → "the sound disappears on click" (editor feedback).
    import hashlib
    _file_ids: dict[str, str] = {}
    _files_emitted: set[str] = set()

    def file_id_for(media_path: Path) -> str:
        key = str(media_path.resolve())
        if key not in _file_ids:
            h = hashlib.md5(key.encode()).hexdigest()[:6]
            stem = re.sub(r"[^A-Za-z0-9_-]", "_", media_path.stem)[:32]
            _file_ids[key] = f"file_{stem}_{h}"
        return _file_ids[key]

    def emit_file(media_path: Path, inner: str) -> str:
        """Full <file> block at the 1st occurrence, empty reference afterwards."""
        fid = file_id_for(media_path)
        if fid in _files_emitted:
            return f'<file id="{fid}"/>'
        _files_emitted.add(fid)
        return f'<file id="{fid}">{inner}\n          </file>'

    def video_clip_xml(idx: int, item: dict, track_index: int) -> str:
        """Video clip (clip, b-roll, Remotion overlay): <file> = ffprobe truth."""
        media_path = item["path"]
        meta = probe_video_meta(media_path)
        start, end = item["start_frame"], item["end_frame"]
        n_frames = end - start
        in_pt = item.get("in_frame", 0)          # offset in the media, sequence base
        out_pt = in_pt + n_frames
        media_dur_seq = max(round(meta["duration_s"] * fps), out_pt)
        alphatype = "straight" if item["alpha"] else "none"
        ntsc = "TRUE" if meta["ntsc"] else "FALSE"
        tc_sep = ";" if meta["ntsc"] else ":"
        clip_id = f"clip_{track_index}_{idx}"
        # b-roll whose ratio differs from the sequence (16:9 in a 9:16 reel):
        # fit-cover to fill the frame without black bars.
        cover = ""
        if item.get("fit_cover"):
            cover = _cover_motion_filter(meta["width"], meta["height"], width, height)
        mo = item.get("motion")
        if mo:
            # free placement (reel): scale (default fit-cover), cx = wanted center in px of the source,
            # dy = vertical offset in sequence px ("screen" window above or below the center)
            sc = mo.get("scale") or max(width / meta["width"], height / meta["height"]) * 100.0
            cover = _recadrage_filter(sc, [(0, float(mo.get("cx", meta["width"] / 2)))], meta["width"], [0],
                                      meta["height"], mo.get("dy"))
        file_inner = f"""
            <name>{media_path.name}</name>
            <pathurl>{file_url(media_path)}</pathurl>
            <rate>
              <timebase>{meta['timebase']}</timebase>
              <ntsc>{ntsc}</ntsc>
            </rate>
            <duration>{meta['nb_frames']}</duration>
            <timecode>
              <rate>
                <timebase>{meta['timebase']}</timebase>
                <ntsc>{ntsc}</ntsc>
              </rate>
              <string>00{tc_sep}00{tc_sep}00{tc_sep}00</string>
              <frame>0</frame>
              <displayformat>{'DF' if meta['ntsc'] else 'NDF'}</displayformat>
            </timecode>
            <media>
              <video>
                <samplecharacteristics>
                  <rate>
                    <timebase>{meta['timebase']}</timebase>
                    <ntsc>{ntsc}</ntsc>
                  </rate>
                  <width>{meta['width']}</width>
                  <height>{meta['height']}</height>
                  <anamorphic>FALSE</anamorphic>
                  <pixelaspectratio>square</pixelaspectratio>
                  <fielddominance>none</fielddominance>
                </samplecharacteristics>
              </video>
            </media>"""
        return f"""
        <clipitem id="{clip_id}">
          <masterclipid>masterclip_{file_id_for(media_path)}</masterclipid>
          <name>{media_path.name}</name>
          <enabled>TRUE</enabled>
          <duration>{media_dur_seq}</duration>
          <rate>
            <timebase>{fps}</timebase>
            <ntsc>FALSE</ntsc>
          </rate>
          <start>{start}</start>
          <end>{end}</end>
          <in>{in_pt}</in>
          <out>{out_pt}</out>
          <pproTicksIn>{ticks(in_pt, fps)}</pproTicksIn>
          <pproTicksOut>{ticks(out_pt, fps)}</pproTicksOut>
          <alphatype>{alphatype}</alphatype>
          <pixelaspectratio>square</pixelaspectratio>
          <anamorphic>FALSE</anamorphic>
          {emit_file(media_path, file_inner)}{cover}
        </clipitem>"""

    def still_clip_xml(idx: int, item: dict, track_index: int) -> str:
        """Photo still (jpg/png): canonical structure of the Premiere export:
        clipitem rate 25 NDF, in=90000 (1 h), duration 1080000, <file> rate
        30 NTSC DF without duration, real dimensions. + Basic Motion fit-contain."""
        media_path = item["path"]
        start, end = item["start_frame"], item["end_frame"]
        dur_s = (end - start) / fps
        in_pt = 90000
        out_pt = in_pt + max(1, round(dur_s * 25))
        w = item.get("width") or width
        h = item.get("height") or height
        clip_id = f"clip_{track_index}_{idx}"
        filter_xml = _fit_motion_filter(w, h, width, height) if item.get("fit") else ""
        file_inner = f"""
            <name>{media_path.name}</name>
            <pathurl>{file_url(media_path)}</pathurl>
            <rate>
              <timebase>30</timebase>
              <ntsc>TRUE</ntsc>
            </rate>
            <timecode>
              <rate>
                <timebase>30</timebase>
                <ntsc>TRUE</ntsc>
              </rate>
              <string>00;00;00;00</string>
              <frame>0</frame>
              <displayformat>DF</displayformat>
            </timecode>
            <media>
              <video>
                <samplecharacteristics>
                  <rate>
                    <timebase>30</timebase>
                    <ntsc>TRUE</ntsc>
                  </rate>
                  <width>{w}</width>
                  <height>{h}</height>
                  <anamorphic>FALSE</anamorphic>
                  <pixelaspectratio>square</pixelaspectratio>
                  <fielddominance>none</fielddominance>
                </samplecharacteristics>
              </video>
            </media>"""
        return f"""
        <clipitem id="{clip_id}">
          <masterclipid>masterclip_{file_id_for(media_path)}</masterclipid>
          <name>{media_path.name}</name>
          <enabled>TRUE</enabled>
          <duration>1080000</duration>
          <rate>
            <timebase>25</timebase>
            <ntsc>FALSE</ntsc>
          </rate>
          <start>{start}</start>
          <end>{end}</end>
          <in>{in_pt}</in>
          <out>{out_pt}</out>
          <pproTicksIn>{ticks(in_pt, 25)}</pproTicksIn>
          <pproTicksOut>{ticks(out_pt, 25)}</pproTicksOut>
          <alphatype>none</alphatype>
          <pixelaspectratio>square</pixelaspectratio>
          <anamorphic>FALSE</anamorphic>
          {emit_file(media_path, file_inner)}{filter_xml}
        </clipitem>"""

    def rush_piece_xml(idx: int, pc: dict) -> str:
        """A piece of the clip on V1 (reel edited by script): <in>/<out> in the clip, reframing by keyframes.
        The <file> of the clip also declares its audio, so that A1 and A2 attach to it. A zoom of a sequence with several
        clips reads its own (`media_path`): a 16:10 one in a past video fell into clip B and read clip A (CALAGE)."""
        rush_ = pc.get("media_path") or rush
        meta = probe_video_meta(rush_)
        am = probe_audio_meta(rush_)
        start, end, in_pt = pc["start_frame"], pc["end_frame"], pc.get("in_frame_v", pc["in_frame"])
        out_pt = in_pt + end - start
        ntsc = "TRUE" if meta["ntsc"] else "FALSE"
        tc_sep = ";" if meta["ntsc"] else ":"
        file_inner = f"""
            <name>{rush_.name}</name>
            <pathurl>{file_url(rush_)}</pathurl>
            <rate><timebase>{meta['timebase']}</timebase><ntsc>{ntsc}</ntsc></rate>
            <duration>{meta['nb_frames']}</duration>
            <timecode><rate><timebase>{meta['timebase']}</timebase><ntsc>{ntsc}</ntsc></rate><string>00{tc_sep}00{tc_sep}00{tc_sep}00</string><frame>0</frame><displayformat>{'DF' if meta['ntsc'] else 'NDF'}</displayformat></timecode>
            <media>
              <video><samplecharacteristics><rate><timebase>{meta['timebase']}</timebase><ntsc>{ntsc}</ntsc></rate><width>{meta['width']}</width><height>{meta['height']}</height><anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance></samplecharacteristics></video>
              <audio><samplecharacteristics><depth>16</depth><samplerate>{am['samplerate']}</samplerate></samplecharacteristics><channelcount>{am['channels']}</channelcount></audio>
            </media>"""
        filt = _recadrage_filter(pc["scale"], pc["cles"], meta["width"], [0, in_pt, start], meta["height"], pc.get("cy"))
        if pc.get("cadre"):   # animated zoom (scale and center by keyframes): long video, books shown
            filt = _cadre_filter(pc["cadre"], meta["width"], meta["height"], [0, in_pt, start])
        # zooms of the long video: <in> counted at the REAL frame rate of the clip (29.97: 30 NTSC), like the rough-cut XML
        # (e.g. in 21764 for 726.26 s). Counted at exactly 30, the piece started 0.1% too late (0.74 s at 12 min
        # of clip) and showed at 7:44 a passage that had been cut. The reel keeps its own calculation.
        rt = (1001 / 1000) if pc.get("ntsc") else 1.0
        return f"""
        <clipitem id="rush_v_{idx}">
          <masterclipid>masterclip_{file_id_for(rush_)}</masterclipid>
          <name>{rush_.name}</name>
          <enabled>TRUE</enabled>
          <duration>{meta['nb_frames'] if pc.get("ntsc") else round(meta['duration_s'] * fps)}</duration>
          <rate><timebase>{fps}</timebase><ntsc>{"TRUE" if pc.get("ntsc") else "FALSE"}</ntsc></rate>
          <start>{start}</start>
          <end>{end}</end>
          <in>{in_pt}</in>
          <out>{out_pt}</out>
          <pproTicksIn>{round(ticks(in_pt, fps) * rt)}</pproTicksIn>
          <pproTicksOut>{round(ticks(out_pt, fps) * rt)}</pproTicksOut>
          <alphatype>none</alphatype>
          <pixelaspectratio>square</pixelaspectratio>
          <anamorphic>FALSE</anamorphic>
          {emit_file(rush_, file_inner)}{filt}
        </clipitem>"""

    def rush_audio_xml(idx: int, pc: dict, canal: int) -> str:
        start, end, in_pt = pc["start_frame"], pc["end_frame"], pc["in_frame"]
        if voix:   # the processed voice (stereo WAV starting at `debut` s of the clip): XMEML import keeps no audio effect
            vp, am = voix["path"], probe_audio_meta(voix["path"])
            in_pt -= round(voix["debut"] * fps)
            out_pt = in_pt + end - start
            inner = f"""
            <name>{vp.name}</name>
            <pathurl>{file_url(vp)}</pathurl>
            <rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate>
            <duration>{max(1, round(am['duration_s'] * 25))}</duration>
            <timecode><rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate><string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>
            <media><audio><samplecharacteristics><depth>24</depth><samplerate>{am['samplerate']}</samplerate></samplecharacteristics><channelcount>{am['channels']}</channelcount></audio></media>"""
            return f"""
        <clipitem id="rush_a{canal}_{idx}">
          <masterclipid>masterclip_a_{file_id_for(vp)}</masterclipid>
          <name>{vp.name}</name>
          <enabled>TRUE</enabled>
          <duration>{max(round(am['duration_s'] * fps), out_pt)}</duration>
          <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>
          <start>{start}</start>
          <end>{end}</end>
          <in>{in_pt}</in>
          <out>{out_pt}</out>
          <pproTicksIn>{ticks(in_pt, fps)}</pproTicksIn>
          <pproTicksOut>{ticks(out_pt, fps)}</pproTicksOut>
          {emit_file(vp, inner)}
          <sourcetrack><mediatype>audio</mediatype><trackindex>{canal}</trackindex></sourcetrack>
        </clipitem>"""
        meta = probe_video_meta(rush)
        out_pt = in_pt + end - start
        return f"""
        <clipitem id="rush_a{canal}_{idx}">
          <masterclipid>masterclip_{file_id_for(rush)}</masterclipid>
          <name>{rush.name}</name>
          <enabled>TRUE</enabled>
          <duration>{round(meta['duration_s'] * fps)}</duration>
          <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>
          <start>{start}</start>
          <end>{end}</end>
          <in>{in_pt}</in>
          <out>{out_pt}</out>
          <pproTicksIn>{ticks(in_pt, fps)}</pproTicksIn>
          <pproTicksOut>{ticks(out_pt, fps)}</pproTicksOut>
          <file id="{file_id_for(rush)}"/>
          <sourcetrack><mediatype>audio</mediatype><trackindex>{canal}</trackindex></sourcetrack>
        </clipitem>"""

    def clip_xml(idx: int, item: dict, track_index: int) -> str:
        is_still = item["path"].suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".tiff")
        return (still_clip_xml if is_still else video_clip_xml)(idx, item, track_index)

    def audio_clip_xml(idx: int, sfx: dict, track_index: int) -> str:
        media_path = sfx["path"]
        meta = probe_audio_meta(media_path)
        start = sfx["start_frame"]
        dur = sfx["duration_frames"]
        end = start + dur
        media_dur_seq = max(round(meta["duration_s"] * fps), dur)
        mono = ' premiereChannelType="mono"' if meta["channels"] == 1 else ""
        clip_id = f"audio_{track_index}_{idx}"
        file_inner = f"""
            <name>{media_path.name}</name>
            <pathurl>{file_url(media_path)}</pathurl>
            <rate>
              <timebase>25</timebase>
              <ntsc>FALSE</ntsc>
            </rate>
            <duration>{max(1, round(meta['duration_s'] * 25))}</duration>
            <timecode>
              <rate>
                <timebase>25</timebase>
                <ntsc>FALSE</ntsc>
              </rate>
              <string>00:00:00:00</string>
              <frame>0</frame>
              <displayformat>NDF</displayformat>
            </timecode>
            <media>
              <audio>
                <samplecharacteristics>
                  <depth>16</depth>
                  <samplerate>{meta['samplerate']}</samplerate>
                </samplecharacteristics>
                <channelcount>{meta['channels']}</channelcount>
              </audio>
            </media>"""
        return f"""
        <clipitem id="{clip_id}"{mono}>
          <masterclipid>masterclip_a_{file_id_for(media_path)}</masterclipid>
          <name>{media_path.name}</name>
          <enabled>TRUE</enabled>
          <duration>{media_dur_seq}</duration>
          <rate>
            <timebase>{fps}</timebase>
            <ntsc>FALSE</ntsc>
          </rate>
          <start>{start}</start>
          <end>{end}</end>
          <in>0</in>
          <out>{dur}</out>
          <pproTicksIn>0</pproTicksIn>
          <pproTicksOut>{ticks(dur, fps)}</pproTicksOut>
          {emit_file(media_path, file_inner)}
          <sourcetrack>
            <mediatype>audio</mediatype>
            <trackindex>1</trackindex>
          </sourcetrack>
        </clipitem>"""

    v5_clips = [c for c in rendered if c["track"] == "V5"]
    v6_clips = [c for c in rendered if c["track"] == "V6"]

    # White mattes: a white "Color" generatoritem under each GROUP of contiguous
    # photos (gap ≤ 1 s merged: rule of a finished edit), on the
    # b-roll track (free at those moments, colliding b-rolls are skipped).
    matte_spans: list[tuple[int, int]] = []
    seq_ratio = width / height
    for c in sorted(photo_clips, key=lambda x: x["start_frame"]):
        # Photo already at the sequence ratio => the white is baked into the image, no
        # matte to place. Essential at 29.97 where the "Color" generatoritem does not
        # display at all (checked on several videos).
        pw, ph = probe_image_size(c["path"])
        if ph and abs(pw / ph - seq_ratio) < 0.005:
            continue
        if matte_spans and c["start_frame"] - matte_spans[-1][1] <= fps:
            matte_spans[-1] = (matte_spans[-1][0], max(matte_spans[-1][1], c["end_frame"]))
        else:
            matte_spans.append((c["start_frame"], c["end_frame"]))

    # Compacted tracks: only the non-empty tracks, in the order
    # clip → b-rolls+white mattes → photos → premiums → lower-thirds.
    content_tracks = []   # list of XML strings of clipitems
    if rush_pieces:
        # a piece entirely hidden by a full-screen shot only brings its sound (HIDDEN guard): A1/A2 only
        content_tracks.append("".join(rush_piece_xml(i, pc) for i, pc in enumerate(rush_pieces) if pc.get("video", True)))
    elif not rush_frames:
        # --no-rush: V1 stays empty, it is for the editor's own edit. The b-rolls and
        # the demos thus keep their place (V2), the scenes theirs (V3 and above).
        content_tracks.append("")
    if rush_frames:
        rush_item = {"path": rush, "start_frame": 0, "end_frame": rush_frames, "alpha": False}
        content_tracks.append(video_clip_xml(0, rush_item, 1))
    if zooms:
        # zooms on the speaker's camera (long video): the clip at the zoom scale, synced frame for frame to its
        # V1 edit, video only (its voice stays that of its sequence), a track just above V1
        content_tracks.append("".join(rush_piece_xml(1000 + i, z) for i, z in enumerate(zooms)))
    # CHRONOLOGICAL ORDER in each track: Premiere keeps the file order and uses it
    # as an index; an out-of-order clip becomes a ghost (visible in the frame, absent from the
    # timeline, disappears when you zoom). The plan's demos used to come after the b-rolls,
    # the white mattes after both.
    if broll_clips or matte_spans:
        idx_track = len(content_tracks) + 1
        v2 = sorted([(c["start_frame"], 0, c) for c in broll_clips] +
                    [(a, 1, (a, b)) for a, b in matte_spans], key=lambda x: (x[0], x[1]))
        content_tracks.append("".join(
            clip_xml(i, x, idx_track) if k == 0 else _white_matte_xml(i, x[0], x[1], (x[1] - x[0]) / fps)
            for i, (_, k, x) in enumerate(v2)))
    if photo_clips:
        idx_track = len(content_tracks) + 1
        content_tracks.append("".join(clip_xml(i, c, idx_track) for i, c in
                                      enumerate(sorted(photo_clips, key=lambda x: x["start_frame"]))))
    v7_clips = [c for c in rendered if c["track"] == "V7"]   # transitions: a track of their own
    if not rush_frames and not rush_pieces and len(content_tracks) == 1:
        content_tracks.append("")   # no b-roll: keep the place of V2 anyway
    for layer in layer_split(v5_clips) + layer_split(v6_clips) + layer_split(v7_clips):
        idx_track = len(content_tracks) + 1
        content_tracks.append("".join(clip_xml(i, c, idx_track) for i, c in enumerate(layer)))

    video_tracks_xml = "".join(
        f"""
        <track>
          <enabled>TRUE</enabled>
          <locked>FALSE</locked>
          {t}
        </track>"""
        for t in content_tracks
    )
    # Sound effects: A3, then A4, A5... when two sounds overlap
    sfx_tracks_xml = "".join(
        f"""
        <track>
          <enabled>TRUE</enabled>
          <locked>FALSE</locked>
          {"".join(audio_clip_xml(i, c, 3 + li) for i, c in enumerate(layer))}
        </track>"""
        for li, layer in enumerate(layer_split(sfx_clips) or [[]])
    )

    fins = [c["end_frame"] for c in rendered + broll_clips + photo_clips + (rush_pieces or []) + (zooms or [])] + \
           [c["start_frame"] + c["duration_frames"] for c in sfx_clips] + [e for _, e in matte_spans]
    total_frames = max([total_frames, rush_frames] + fins)
    seq_ntsc = "TRUE" if SEQ_NTSC else "FALSE"
    seq_df = "DF" if SEQ_NTSC else "NDF"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="5">
  <sequence id="seq_{rush.stem}">
    <name>{nom or rush.stem + "_ILLU_AUTO"}</name>
    <duration>{total_frames}</duration>
    <rate>
      <timebase>{fps}</timebase>
      <ntsc>{seq_ntsc}</ntsc>
    </rate>
    <timecode>
      <rate>
        <timebase>{fps}</timebase>
        <ntsc>{seq_ntsc}</ntsc>
      </rate>
      <string>00:00:00:00</string>
      <frame>0</frame>
      <displayformat>{seq_df}</displayformat>
    </timecode>
    <media>
      <video>
        <format>
          <samplecharacteristics>
            <width>{width}</width>
            <height>{height}</height>
            <pixelaspectratio>square</pixelaspectratio>
            <rate>
              <timebase>{fps}</timebase>
              <ntsc>{seq_ntsc}</ntsc>
            </rate>
          </samplecharacteristics>
        </format>
        {video_tracks_xml}
      </video>
      <audio>
        <numOutputChannels>2</numOutputChannels>
        <format>
          <samplecharacteristics>
            <depth>16</depth>
            <samplerate>48000</samplerate>
          </samplecharacteristics>
        </format>
        <track>
          <enabled>TRUE</enabled>
          <locked>FALSE</locked>{"".join(rush_audio_xml(i, pc, 1) for i, pc in enumerate(rush_pieces or []))}
        </track>
        <track>
          <enabled>TRUE</enabled>
          <locked>FALSE</locked>{"".join(rush_audio_xml(i, pc, 2) for i, pc in enumerate(rush_pieces or []))}
        </track>
        {sfx_tracks_xml}
      </audio>
    </media>
  </sequence>
</xmeml>
"""
    # GUARD: the XML is only delivered if it passes all the checks (garde_premiere.py).
    # Otherwise it stays next to the output, named .REFUSE.xml, and the old XML is not touched.
    tmp = out_xml.with_name(f".{out_xml.stem}.verif.xml")
    tmp.write_text(xml)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from garde_premiere import valider_xml
    err = valider_xml(tmp)
    if err:
        refuse = out_xml.with_name(f"{out_xml.stem}.REFUSE.xml")
        os.replace(tmp, refuse)
        print(f"\n✗ XML REFUSED by the guard ({len(err)} defect(s)), nothing is delivered:", file=sys.stderr)
        for e in err:
            print("  ✗ " + e, file=sys.stderr)
        print(f"  (inspectable file: {refuse.name})", file=sys.stderr)
        sys.exit(1)
    os.replace(tmp, out_xml)
    out_xml.with_name(f"{out_xml.stem}.REFUSE.xml").unlink(missing_ok=True)
    print("  Premiere guard: OK (order, files, durations, sync, sounds, hiding)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("rush", help="Path to the video clip")
    parser.add_argument("--premiums-only", action="store_true")
    parser.add_argument("--lower-thirds-only", action="store_true")
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--skip-render", action="store_true",
                        help="Do not re-render the overlays, reuse those already on disk (XML regeneration only)")
    parser.add_argument("--no-sfx", action="store_true", help="Disables adding the SFX on A3")
    parser.add_argument("--no-brolls", action="store_true",
                        help="Ignore <clip>_broll-script.json even if it exists")
    parser.add_argument("--no-photos", action="store_true",
                        help="Ignore <clip>_photos-script.json even if it exists")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="Scenes: render everything again, even what is cached")
    parser.add_argument("--only", default="",
                        help="Scenes: render again those whose id contains this text "
                             "(after a component tweak), keep the others")
    parser.add_argument("--no-rush", action="store_true",
                        help="Does not emit the clip on V1. Use when illustrating an "
                             "ALREADY edited (rough-cut) sequence: the raw clip placed on V1 would have "
                             "a different duration than the sequence and would mislead.")
    parser.add_argument("--script", default="",
                        help="Animation script taken from somewhere other than next to the clip (reel pulled from a video): "
                             "<base>_animation-script.json, its b-rolls in <base>_broll-script.json; outputs "
                             "(\"<number> Illustration V1.xml\", its renders and its sounds) in its folder")
    parser.add_argument("--suffixe", default="",
                        help="Version of the delivery (\"v2\"): \"<number> Illustration V2.xml\", \"... - rendus/\", \"... - sons\"; the version already imported by the editor is never rewritten (its files are "
                             "referenced by their Premiere project)")
    parser.add_argument("--rendus-de", default="",
                        help="Version whose renders are reused (\"v2\") when only the XML changes: \"<number> Illustration V2 - rendus/\" "
                             "is used as is (cache), the XML and the sounds take --suffixe (re-synced zooms, 2 GB "
                             "of identical renders not redone)")
    parser.add_argument("--en-place", default="", metavar="ID",
                        help="Redo ONE scene (exact id, e.g. \"sous-titres\") and replace its file at the same path, "
                             "without re-rendering the rest or rewriting the XML: same format checked by ffprobe (otherwise nothing "
                             "is replaced), old file to the trash, Premiere rereads it without reimport")
    args = parser.parse_args()
    if args.en_place:
        args.no_brolls = args.no_photos = True   # nothing else is read or written

    rush = Path(args.rush).resolve()
    if not rush.exists():
        print(f"ERROR: clip not found: {rush}", file=sys.stderr)
        sys.exit(1)

    script_path = rush.with_name(rush.stem + "_animation-script.json")
    base_dir, base = rush.parent, rush.stem
    if args.script:
        script_path = Path(args.script).resolve()
        base_dir, base = script_path.parent, script_path.name.replace("_animation-script.json", "")
    photos_script_path = base_dir / (base + "_photos-script.json")
    broll_script_path = base_dir / (base + "_broll-script.json")

    if script_path.exists():
        script = json.loads(script_path.read_text())
        segments = script.get("segments", [])
        if not segments:
            print("ERROR: animation-script.json present but no segment.", file=sys.stderr)
            sys.exit(1)
        if script.get("controle_texte"):
            # check of the on-screen text (controle-texte.py) run on THIS script and THIS code, otherwise nothing is rendered
            import importlib.util
            spec = importlib.util.spec_from_file_location("controle_texte", Path(__file__).with_name("controle-texte.py"))
            ct = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ct)
            sig = ct.signature(script_path)
            vu = json.loads(sig.read_text()).get("empreinte") if sig.exists() else None
            if vu != ct.empreinte(script):
                print(f"ERROR: {'script or components changed since' if vu else 'no'} on-screen text check: "
                      f"run first  python3 scripts/controle-texte.py \"{script_path}\"", file=sys.stderr)
                sys.exit(1)
            print(f"On-screen text check: signed ({sig.name})")
    elif photos_script_path.exists() or broll_script_path.exists():
        # Photos/b-rolls only mode: no Remotion overlays, just the placement XML
        print("(no animation-script.json: photos/b-rolls XML only)")
        fallback = photos_script_path if photos_script_path.exists() else broll_script_path
        script = json.loads(fallback.read_text())
        segments = []
    else:
        print(f"ERROR: none of {script_path.name} / {photos_script_path.name} / "
              f"{broll_script_path.name} found next to the clip.", file=sys.stderr)
        sys.exit(1)

    # fps/dimensions: the JSON wins, otherwise the TRUTH OF THE CLIP via ffprobe (never a
    # hardcoded constant: a 9:16 1080×1920 reel must produce a 9:16 sequence,
    # and a 60 fps clip a 60 fps sequence).
    rush_meta = probe_video_meta(rush)
    fps = int(script.get("fps") or round(rush_meta["timebase"]))
    # The clip dictates the sequence NTSC: a 30000/1001 clip must produce a
    # 29.97 sequence (ntsc TRUE), not 30.000, otherwise every placement drifts.
    global SEQ_NTSC
    SEQ_NTSC = bool(script.get("ntsc", rush_meta["ntsc"]))
    width = int(script.get("width") or rush_meta["width"])
    height = int(script.get("height") or rush_meta["height"])
    global RENDER_SCALE
    if (width, height) == (3840, 2160):
        RENDER_SCALE = 2
    orientation = "vertical (reel 9:16)" if height > width else "horizontal (16:9)"
    print(f"fps={fps} width={width} height={height} [{orientation}] segments={len(segments)}")

    # Verify timecodes
    if not args.skip_verify:
        print("\nTimecode check:")
        verify_timecodes(script, rush.with_name(rush.stem + "_transcription.json"))

    # Output folder
    slug = slugify(base) + (f"-{slugify(args.suffixe)}" if args.suffixe else "")
    nom = nom_livraison(base_dir, base, args.suffixe or "V1")   # "<number> Illustration V1": XML, sequence, renders, sounds
    out_dir = base_dir / f"{nom_livraison(base_dir, base, args.rendus_de) if args.rendus_de else nom} - rendus"
    ancien = base_dir / f"animations-{slugify(base) + '-' + slugify(args.rendus_de) if args.rendus_de else slug}"
    if not out_dir.exists() and ancien.exists():   # delivery from before the rename: its renders keep their name
        out_dir = ancien
    out_dir.mkdir(exist_ok=True)
    print(f"\nOutput folder: {out_dir}")

    rendered: list[dict] = []
    sfx_clips: list[dict] = []
    broll_clips: list[dict] = []
    photo_clips: list[dict] = []
    sfx_overrides = script.get("sfxDefaults") or {}
    releve: list[tuple] = []   # (moment, file, dB, what is seen): sound report, written with the XML
    max_end_sec = 0.0
    p_n = lt_n = st_n = sc_n = 0
    cache_path = out_dir / ".scenes-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    # Load the photos if <clip>_photos-script.json exists (BEFORE the b-rolls:
    # photos take priority, colliding b-rolls will be skipped)
    if photos_script_path.exists() and not args.no_photos:
        photo_data = json.loads(photos_script_path.read_text())
        photos_dir_raw = photo_data.get("photos_dir")
        photos_dir = Path(photos_dir_raw) if photos_dir_raw else rush.parent / "Illustrations"
        default_photo_dur = float((photo_data.get("defaults") or {}).get("durationSec", 4.0))
        print(f"\nPhotos: reading {photos_script_path.name}")
        for photo in photo_data.get("photos", []):
            if not photo.get("file") or photo.get("enabled") is False:
                continue
            tc = photo.get("timecode")
            if not tc or tc == "??":
                print(f"  ⚠️  photo #{photo.get('id','?')} ({photo.get('file')}) without a valid timecode, skipped")
                continue
            photo_file = photos_dir / photo["file"]
            if not photo_file.exists():
                print(f"  ⚠️  photo not found: {photo['file']}", file=sys.stderr)
                continue
            start_sec = tc_to_seconds(tc)
            dur_sec = photo.get("durationSec") or default_photo_dur
            end_sec = start_sec + dur_sec
            if end_sec > max_end_sec:
                max_end_sec = end_sec
            img_w, img_h = probe_image_size(photo_file)
            if img_w and img_w < 800 and img_h < 1000:
                print(f"  ⚠️  LOW RES ({img_w}×{img_h}): {photo['file']}: the editor will probably "
                      "replace it, suggest re-sourcing", file=sys.stderr)
            photo_clips.append({
                "track": "V3",
                "path": photo_file,
                "start_frame": seq_frames(start_sec, fps),
                "end_frame": seq_frames(end_sec, fps),
                "alpha": False,
                "width": img_w,
                "height": img_h,
                "fit": True,   # Scale fit-contain filter in the XML
            })
            # Whoosh on the appearance of book/magazine covers
            # (rule extracted from a finished edit)
            if not args.no_sfx and PHOTO_SFX_PATTERN.search(photo["file"]):
                whoosh = timbre(PHOTO_SFX_NAME)
                if whoosh.exists():
                    sfx_clips.append({
                        "path": whoosh,
                        "start_frame": seq_frames(start_sec, fps),
                        "duration_frames": frames_son(whoosh, fps),
                    })
                    releve.append((start_sec, PHOTO_SFX_NAME, 0.0, f"photo {photo['file']}"))
            print(f"  ✅ #{photo.get('id','?')} @ {tc} dur={dur_sec:.1f}s → {photo['file']}")
        if not photo_clips:
            print("  (no valid photo to include)")

    # Load the b-rolls if <clip>_broll-script.json exists
    if broll_script_path.exists() and not args.no_brolls:
        broll_data = json.loads(broll_script_path.read_text())
        brolls_dir_raw = broll_data.get("brolls_dir")
        brolls_dir = Path(brolls_dir_raw) if brolls_dir_raw else rush.parent / "Brolls"
        print(f"\nB-rolls: reading {broll_script_path.name}")
        for broll in broll_data.get("brolls", []):
            if not broll.get("file"):
                continue
            tc = broll.get("timecode")
            if not tc or tc == "??":
                print(f"  ⚠️  b-roll #{broll.get('id','?')} without a valid timecode, skipped")
                continue
            # normpath: a screencast is entered as "../Screencast/x.mp4", and Brolls/ may not exist;
            # an absolute path (taken from a delivered video, elsewhere on the disk) is used as is
            broll_file = Path(os.path.normpath(brolls_dir / Path(broll["file"]).expanduser()))
            if not broll_file.exists():
                print(f"  ⚠️  b-roll #{broll.get('id','?')} not found: {broll['file']}", file=sys.stderr)
                continue
            start_sec = tc_to_seconds(tc)
            # Clip in and out: an excerpt taken IN THE MIDDLE of a file
            # (a delivered lesson) is placed as is, without re-encoding or cutting: `inSec` gives
            # the entry in the file (<in> and pproTicksIn of the clip), `outSec` the exit. Without them, the
            # b-roll starts at the beginning of the file, as before.
            in_sec = float(broll.get("inSec") or 0.0)
            dur_sec = broll.get("durationSec")
            if dur_sec is None and broll.get("outSec") is not None:
                dur_sec = float(broll["outSec"]) - in_sec
            if dur_sec is None:
                dur_sec = probe_video_duration(broll_file) - in_sec
            if broll.get("outSec") is not None and in_sec + dur_sec > float(broll["outSec"]) + 0.02:
                print(f"  ⚠️  b-roll #{broll.get('id','?')}: the duration exceeds the out point {broll['outSec']} s, brought back",
                      file=sys.stderr)
                dur_sec = float(broll["outSec"]) - in_sec
            end_sec = start_sec + dur_sec
            start_frame = seq_frames(start_sec, fps)
            end_frame = seq_frames(end_sec, fps)
            dispo = math.floor((probe_video_duration(broll_file) - in_sec) * fps * (1000.0 / 1001.0 if SEQ_NTSC else 1.0))
            end_frame = min(end_frame, start_frame + dispo)
            # Priority to photos: a b-roll that overlaps a photo is skipped
            clash = next((p for p in photo_clips
                          if start_frame < p["end_frame"] and end_frame > p["start_frame"]), None)
            if clash:
                print(f"  ⏭️  b-roll #{broll.get('id','?')} @ {tc} skipped "
                      f"(overlaps photo {clash['path'].name})")
                continue
            if end_sec > max_end_sec:
                max_end_sec = end_sec
            # fit-cover if the ratio OR the size of the b-roll differs from the sequence (vertical reel;
            # 1080p or 2048×1080 b-roll in a 4K sequence: otherwise a quarter of the frame)
            bmeta = probe_video_meta(broll_file)
            aspect_diff = (abs(bmeta["width"] / bmeta["height"] - width / height) > 0.05
                           or (bmeta["width"], bmeta["height"]) != (width, height))
            broll_clips.append({
                "track": "V2",
                "path": broll_file,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "alpha": False,
                "fit_cover": aspect_diff,
                "motion": broll.get("motion"),
                "_dispo": dispo,
                # <in> of the clip, in frames at the clip's rate (fps, non-NTSC): pproTicksIn = in_sec exactly
                **({"in_frame": round(in_sec * fps)} if in_sec else {}),
            })
            # a site demo arrives with its sounds (clicks, keys): <file>.sons.json
            sons_json = broll_file.with_suffix(".sons.json")
            if sons_json.exists() and not args.no_sfx and not args.dry_run:
                sons = [s for s in json.loads(sons_json.read_text()) if s["at"] < dur_sec - 0.05]
                wav = out_dir / f"ANIM-SC-{broll_file.stem}-son.wav"
                if sons and (args.force or not wav.exists() or wav.stat().st_mtime < sons_json.stat().st_mtime):
                    out_dir.mkdir(parents=True, exist_ok=True)
                    mix_scene_sfx(sons, wav)
                if sons and wav.exists():
                    sfx_clips.append({"path": wav, "start_frame": start_frame,
                                      "duration_frames": frames_son(wav, fps)})
            fc = " [fit-cover]" if aspect_diff else ""
            io = f" [in {in_sec:.2f} s]" if in_sec else ""
            print(f"  ✅ #{broll.get('id','?')} @ {tc} dur={dur_sec:.1f}s → {broll_file.name}{io}{fc}")
        if not broll_clips:
            print("  (no valid b-roll to include)")
        # Two b-rolls back to back in the plan (end of one = start of the other, to the hundredth) can
        # land 1 frame apart once each is rounded to the frame: the face shows for 1 frame between
        # the two. A gap of 1 or 2 frames is never
        # intended: the first holds until the second, if it has the frames.
        bv = sorted(broll_clips, key=lambda c: c["start_frame"])
        for a, b in zip(bv, bv[1:]):
            trou = b["start_frame"] - a["end_frame"]
            if 0 < trou <= 2 and a["start_frame"] + a["_dispo"] >= b["start_frame"]:
                print(f"  ↔︎ {a['path'].name} holds {trou} more frame(s), until {b['path'].name}")
                a["end_frame"] = b["start_frame"]

    # Scenes that share a file (same id: the wipes, dozens in a video): depending on rounding,
    # a clip is 15 or 16 frames, the cache key changed from one wipe to the next and the same
    # file was rendered 4 times per pass, the last render deciding its length. A single
    # render for all: the animation of the shortest, the last frame held up to the longest.
    partage: dict[str, tuple[int, int]] = {}
    for seg in segments:
        if seg.get("type") == "scene" and seg.get("id") and seg.get("timecode") not in (None, "??"):
            s0 = tc_to_seconds(seg["timecode"])
            m, t = frames_couverts(seq_frames(s0, fps), seq_frames(s0 + float(seg["durationSec"]), fps), fps)
            sid0 = slugify(seg["id"], 60)
            if sid0 in partage:
                m0, t0 = partage[sid0]
                partage[sid0] = (min(m0, m), max(m0 + t0, m + t) - min(m0, m))
            else:
                partage[sid0] = (m, t)

    if args.en_place:
        sid = slugify(args.en_place, 60)
        seg = next((s for s in segments if s.get("type") == "scene" and slugify(s.get("id") or "", 60) == sid), None)
        if seg is None:
            print(f"ERROR --en-place: no scene with id \"{args.en_place}\" in {script_path.name}", file=sys.stderr)
            sys.exit(1)
        alpha = bool(seg.get("alpha"))
        out_file = out_dir / f"ANIM-S-{sid}{'.mov' if alpha else '.mp4'}"
        n_frames, tail = partage[sid]
        props = props_scene(seg, n_frames, tail, fps, width, height)
        print(f"\n--en-place: {out_file.name}")
        refaire_en_place(seg, props, n_frames + tail, out_file, alpha)
        cache[out_file.name] = hashlib.sha1((json.dumps(props, ensure_ascii=False, sort_keys=True) + CODE).encode()).hexdigest()
        cache_path.write_text(json.dumps(cache, indent=1))
        return

    for i, seg in enumerate(segments, start=1):
        dur = float(seg["durationSec"])
        tc = seg.get("timecode")
        if not tc or tc == "??":
            print(f"ERROR: segment #{i} without a valid timecode ({tc!r}). "
                  "Each segment must point at the moment of the timeline where the overlay must appear.",
                  file=sys.stderr)
            sys.exit(1)
        start_sec = tc_to_seconds(tc)
        end_sec = start_sec + dur
        if end_sec > max_end_sec:
            max_end_sec = end_sec
        start_frame = seq_frames(start_sec, fps)
        end_frame = seq_frames(end_sec, fps)
        tc_str = fmt_tc(start_sec)
        seg_type = seg["type"]

        if seg_type == "motion" and not args.lower_thirds_only:
            p_n += 1
            comp_slug = slugify(seg.get("component", "premium"))
            out_file = out_dir / f"ANIM-P{p_n:02d}-{tc_str}-{comp_slug}.mp4"
            track = "V5"
            alpha = False
            composition = "BrandedVideo"
        elif seg_type == "lower-third" and not args.premiums_only:
            lt_n += 1
            term_slug = slugify(seg["data"].get("term") or seg["data"].get("name")
                                 or seg["data"].get("title") or seg["data"].get("place") or "lt")
            out_file = out_dir / f"ANIM-LT{lt_n:02d}-{tc_str}-{term_slug}.mov"
            track = "V6"
            alpha = True
            composition = "LowerThirdTrack"
        elif seg_type == "section-title" and not args.premiums_only:
            st_n += 1
            title_slug = slugify(seg["data"].get("title", "section"))
            out_file = out_dir / f"ANIM-ST{st_n:02d}-{tc_str}-{title_slug}.mov"
            track = "V6"
            alpha = True
            composition = "LowerThirdTrack"
        elif seg_type == "scene" and not args.lower_thirds_only and not args.premiums_only:
            # Animated overlays: one file per scene, named by its id (stable when
            # a scene is inserted), rendered only if its props changed.
            sc_n += 1
            alpha = bool(seg.get("alpha"))
            sid = slugify(seg.get("id") or f"{sc_n:02d}-{seg['component']}", 60)
            out_file = out_dir / f"ANIM-S-{sid}{'.mov' if alpha else '.mp4'}"
            n_frames, tail = partage.get(sid) or frames_couverts(start_frame, end_frame, fps)
            props = props_scene(seg, n_frames, tail, fps, width, height)
            blob = json.dumps(props, ensure_ascii=False, sort_keys=True)
            key = hashlib.sha1((blob + CODE).encode()).hexdigest()
            stale = (args.force or not out_file.exists() or cache.get(out_file.name) != key
                     or (args.only and args.only in sid))
            if args.dry_run:
                print(f"  [dry-run] scene {sid} @ {tc_str} dur={dur:.2f}s {'to render' if stale else 'cached'}")
            elif stale and not args.skip_render:
                print(f"  #{i:02d} scene {sid} dur={dur:.2f}s @ {tc_str}")
                props_file = fichier_de_travail(out_dir, f"props-{sid}.json")
                props_file.write_text(blob)
                run_scene(props_file, n_frames + tail, out_file, alpha)
                props_file.unlink(missing_ok=True)
                cache[out_file.name] = key
                cache_path.write_text(json.dumps(cache, indent=1))
            elif not out_file.exists():
                print(f"  ⚠️  {out_file.name} missing: remove --skip-render", file=sys.stderr)
                sys.exit(1)
            rendered.append({"track": seg.get("track") or ("V6" if alpha else "V5"), "path": out_file,
                             "start_frame": start_frame, "end_frame": end_frame, "alpha": alpha})
            sfx_list = seg.get("sfx") or []
            if not args.no_sfx:
                quoi = f"{sid} ({seg['component']}){texte_scene(seg.get('data') or {})}"
                releve.extend((start_sec + x["at"], x["file"], x.get("gainDb", 0.0), quoi) for x in sfx_list)
            if sfx_list and not args.no_sfx and not args.dry_run:
                wav = out_dir / f"ANIM-S-{sid}-son.wav"
                skey = hashlib.sha1(json.dumps(sfx_list, sort_keys=True).encode()).hexdigest()
                if args.force or not wav.exists() or cache.get(wav.name) != skey:
                    if mix_scene_sfx(sfx_list, wav):
                        cache[wav.name] = skey
                        cache_path.write_text(json.dumps(cache, indent=1))
                if wav.exists():
                    sfx_clips.append({"path": wav, "start_frame": start_frame,
                                      "duration_frames": frames_son(wav, fps)})
            continue
        else:
            continue

        # Mini-props for an isolated render
        props_file = fichier_de_travail(out_dir, f"props-{i:03d}.json")
        n_main, tail = frames_couverts(start_frame, end_frame, fps)
        write_segment_props({**seg, "durationSec": n_main / fps}, fps, width // RENDER_SCALE, height // RENDER_SCALE,
                            props_file, tail)
        frames = (0, n_main + tail - 1)

        if args.dry_run:
            print(f"  [dry-run] {seg_type:<14} → {out_file.name} frames=0-{frames[1]}")
        elif args.skip_render:
            if out_file.exists():
                print(f"  #{i:02d} {seg_type:<14} dur={dur:.1f}s @ {tc_str} → skip (exists: {out_file.name})")
            else:
                print(f"  ⚠️  #{i:02d} {out_file.name} missing: it has to be rendered, remove --skip-render", file=sys.stderr)
                sys.exit(1)
        else:
            # Same cache as the scenes: an unchanged overlay is not rendered twice
            lkey = hashlib.sha1(json.dumps([seg, fps, width, height, n_main, tail, CODE], ensure_ascii=False,
                                           sort_keys=True).encode()).hexdigest()
            if out_file.exists() and cache.get(out_file.name) == lkey and not args.force:
                print(f"  #{i:02d} {seg_type:<14} dur={dur:.1f}s @ {tc_str} (cached)")
            else:
                print(f"  #{i:02d} {seg_type:<14} dur={dur:.1f}s @ {tc_str}")
                run_remotion(composition, frames, out_file, props_file, alpha=alpha)
                cache[out_file.name] = lkey
                cache_path.write_text(json.dumps(cache, indent=1))
            props_file.unlink(missing_ok=True)

        rendered.append({
            "track": track,
            "path": out_file,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "alpha": alpha,
        })

        # SFX collection (track A3 of the XML, independent of the video render)
        if not args.no_sfx:
            sfx_path = resolve_sfx_for_segment(seg, sfx_overrides)
            if sfx_path:
                sfx_dur_frames = frames_son(sfx_path, fps)
                releve.append((start_sec, sfx_path.name, 0.0, f"{seg_type}{texte_scene(seg)}"))
                sfx_clips.append({
                    "path": sfx_path,
                    "start_frame": start_frame,
                    "duration_frames": sfx_dur_frames,
                })

    # XML
    if (rendered or broll_clips or photo_clips) and not args.dry_run:
        rush_frames = 0 if args.no_rush else seq_frames(probe_video_duration(rush), fps)
        total_frames = max(seq_frames(max_end_sec, fps), rush_frames)
        out_xml = base_dir / f"{nom}.xml"
        # Pieces of the clip placed by the script (reel): seconds → sequence frames, keys relative to the clip
        rush_pieces = []
        for pc in script.get("rush_clips", []):
            s0, s1 = seq_frames(pc["start"], fps), seq_frames(pc["start"] + pc["out"] - pc["in"], fps)
            # video: <in> at the media's frame rate (Premiere reads in / 29.97 on an NTSC clip: a reel started
            # +0.84 to +1.07 s behind its voice, when reread in Premiere); audio (WAV voice) keeps in / fps
            ntsc_rush = bool(rush_meta["ntsc"])
            rush_pieces.append({"start_frame": s0, "end_frame": s1, "in_frame": round(pc["in"] * fps), "ntsc": ntsc_rush,
                                "in_frame_v": round(pc["in"] * fps * (1000 / 1001 if ntsc_rush else 1.0)),
                                "scale": pc.get("scale", 100.0), "video": pc.get("video", True), "cy": pc.get("cy"),
                                "cles": [(max(0, min(s1 - s0 - 1, round((t - pc["in"]) * fps))), x) for t, x in pc["cles"]]})
        if rush_pieces:
            rush_frames = 0
            total_frames = max(total_frames, max(p["end_frame"] for p in rush_pieces))
        # Zooms placed by the plan (long video): one piece of the clip per zoom, fixed scale, center (cx, cy) that keeps
        # the head in place; one clip of the edit per piece (the plan cuts at the clip)
        zooms = []
        for z in script.get("zooms", []):
            s0, s1 = seq_frames(z["start"], fps), seq_frames(z["start"] + z["out"] - z["in"], fps)
            ntsc_rush = bool(rush_meta["ntsc"])
            zooms.append({"start_frame": s0, "end_frame": s1, "scale": z["scale"], "ntsc": ntsc_rush,
                          **({"media_path": rush.parent / z["media"]} if z.get("media") else {}),
                          "in_frame": round(z["in"] * fps * (1000 / 1001 if ntsc_rush else 1.0)),
                          "cy": z.get("cy"), "cles": [(0, z["cx"])],
                          # animated frame: [(seconds from the start of the piece, scale %, source cx, sequence cy)]
                          **({"cadre": [(max(0, min(s1 - s0 - 1, round(t * fps))), k, cx, cy) for t, k, cx, cy in z["cadre"]]}
                             if z.get("cadre") else {})})
        build_xml(rush, rendered, sfx_clips, broll_clips, photo_clips,
                  fps, width, height, total_frames, out_xml, rush_frames, rush_pieces, script.get("sequence") or nom,
                  ({"path": (script_path.parent / script["voix"]["fichier"]).resolve(), "debut": script["voix"]["debut"]}
                   if script.get("voix") else None), zooms)
        print(f"\nPremiere XML: {out_xml}")
        if zooms:
            print(f"     V2 = {len(zooms)} zooms on the speaker's camera (above their V1)")
        if releve:
            ecrire_releve(releve, rush, base_dir / f"{nom} - sons")
        print(f"  → File > Import in Premiere:")
        print(f"     V1 = clip ({rush_frames} frames)")
        if broll_clips or photo_clips:
            print(f"     V{3 if zooms else 2} = b-rolls ({len(broll_clips)}) + black backgrounds under photos")
        if photo_clips:
            print(f"     V3 = photos ({len(photo_clips)}, native stills + Scale fit-frame filter)")
        print(f"     following tracks = premiums / lower-thirds (compacted, no empty track)")
        print(f"     A3 and following = sound effects ({len(sfx_clips)} clips)")
    elif args.dry_run:
        print(f"\n[dry-run] {len(rendered)} segments to render (XML not generated)")


if __name__ == "__main__":
    main()
