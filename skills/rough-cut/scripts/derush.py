#!/usr/bin/env python3
"""Orchestrator of the automatic rough cut for Premiere Pro.

Full pipeline: audio extraction → whisper.cpp transcription → mechanical cuts
→ semantic analysis (stage 5) → merge + scoring → FCP7 XML (XMEML) + report.

Usage:
    python3 derush.py /path/clip.mp4
    python3 derush.py /path/clip.mp4 --lang en            # spoken language (default: detected by whisper)
    python3 derush.py /path/clip.mp4 --resume-from=6      # resume after the LLM stage 5
    python3 derush.py /path/clip.mp4 --debug              # keeps the work folder
    python3 derush.py /path/clip.mp4 --model=small        # other whisper model
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# Stage 5 (semantic analysis): by default, the AI running the skill does it, in context
# (prompt_semantic.txt). Optional: DERUSH_WEBHOOK = URL of a service of your own (n8n
# workflow, Make, cloud function...) that receives {transcript, cuts_mechanical, meta} as a
# POST and returns the JSON {"cuts": [...]} in the cuts_semantic.json format.
DERUSH_WEBHOOK = os.environ.get("DERUSH_WEBHOOK", "").strip()


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def check_binary(name):
    """Looks for a binary in the PATH or in /opt/homebrew/bin."""
    found = shutil.which(name)
    if found:
        return found
    fallback = Path("/opt/homebrew/bin") / name
    if fallback.exists():
        return str(fallback)
    return None


def ffprobe_metadata(rush_path):
    ffprobe = check_binary("ffprobe")
    if not ffprobe:
        die("ffprobe not found. Install FFmpeg: brew install ffmpeg")
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,width,height,codec_name",
        "-show_entries", "format=duration",
        "-show_entries", "stream=channels,sample_rate",
        "-of", "json",
        str(rush_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        die(f"ffprobe failed: {result.stderr}")
    data = json.loads(result.stdout)

    video = next((s for s in data.get("streams", []) if "width" in s), None)
    if not video:
        die("No video stream found in the clip")

    # Audio stream through a second query (simpler than parsing everything at once)
    cmd_audio = [
        ffprobe, "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=channels,sample_rate,codec_name",
        "-of", "json",
        str(rush_path),
    ]
    result_audio = subprocess.run(cmd_audio, capture_output=True, text=True)
    audio_data = json.loads(result_audio.stdout) if result_audio.returncode == 0 else {}
    audio = next((s for s in audio_data.get("streams", [])), None)
    if not audio:
        die("No audio stream found in the clip. The rough cut needs audio.")

    fps_num, fps_den = map(int, video["r_frame_rate"].split("/"))
    fps = fps_num / fps_den

    return {
        "rush_path": str(rush_path),
        "duration_seconds": float(data["format"]["duration"]),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": fps,
        "fps_num": fps_num,
        "fps_den": fps_den,
        "video_codec": video.get("codec_name", "unknown"),
        "audio_channels": int(audio.get("channels", 2)),
        "audio_rate": int(audio.get("sample_rate", 48000)),
        "audio_codec": audio.get("codec_name", "aac"),
    }


def next_version(rush_path):
    """Scans the `<clip>_Derush_vN.xml` files next to the clip to increment the version.

    The extension must stay in line with `out_xml` (XMEML/.xml): otherwise the version
    stays stuck at 1 and every run overwrites the previous edit.
    """
    parent = rush_path.parent
    stem = rush_path.stem
    n = 1
    while (parent / f"{stem}_Derush_v{n}.xml").exists():
        n += 1
    return n


def run_stage(label, cmd, work_dir):
    """Runs a subprocess and logs it."""
    print(f"[{label}] {' '.join(str(c) for c in cmd)}")
    log_file = work_dir / "log.txt"
    with log_file.open("a") as log:
        log.write(f"\n=== {label} ===\n")
        log.write(" ".join(str(c) for c in cmd) + "\n")
        result = subprocess.run(cmd, capture_output=True, text=True)
        log.write(result.stdout or "")
        log.write(result.stderr or "")
    if result.returncode != 0:
        die(f"Stage '{label}' failed (see {log_file}). stderr: {result.stderr[:500]}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Automatic rough cut for Premiere Pro.")
    parser.add_argument("rush", help="Absolute path of the video clip")
    parser.add_argument("--resume-from", type=int, default=1, help="Stage to resume from (1..8)")
    parser.add_argument("--debug", action="store_true", help="Keeps the work folder")
    parser.add_argument("--model", default="large-v3-turbo", help="Whisper model")
    parser.add_argument("--work-dir", help="Work folder (useful with --resume-from)")
    parser.add_argument("--lang", help="language code of the speech (fr, en...), passed to every stage; "
                                       "default: detected by whisper, then read from the transcript")
    args = parser.parse_args()
    lang_args = ["--lang", args.lang] if args.lang else []

    rush = Path(args.rush).expanduser().resolve()
    if not rush.exists():
        die(f"Clip not found: {rush}")
    if not rush.is_file():
        die(f"The path is not a file: {rush}")

    # Work folder: next to the clip, so that a manual resume stays possible.
    # The version number is chosen first (it is used in the folder name).
    if args.work_dir:
        work = Path(args.work_dir)
        if not work.exists():
            die(f"Work folder not found: {work}")
    else:
        version = next_version(rush)
        work = rush.parent / f"{rush.stem}_Derush_v{version}_work"
        if work.exists():
            # If an orphan work folder already exists for this version,
            # the next one is taken so as not to overwrite it.
            n = version
            while work.exists():
                n += 1
                work = rush.parent / f"{rush.stem}_Derush_v{n}_work"
        work.mkdir()
    print(f"Work folder: {work}")

    # Metadata + version
    meta_file = work / "meta.json"
    if args.resume_from <= 1:
        meta = ffprobe_metadata(rush)
        meta["version"] = next_version(rush)
        meta["work_dir"] = str(work)
        meta["model"] = args.model
        meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        print(f"Stage 1 OK: duration {meta['duration_seconds']:.1f}s, "
              f"{meta['fps']:.2f} fps, version v{meta['version']}")
    else:
        if not meta_file.exists():
            die(f"meta.json missing in {work}. Run again without --resume-from.")
        meta = json.loads(meta_file.read_text())

    audio_wav = work / "audio.wav"
    transcript = work / "transcript.json"
    cuts_mech = work / "cuts_mechanical.json"
    cuts_sem = work / "cuts_semantic.json"
    cuts_final = work / "cuts_final.json"
    prompt_file = work / "prompt_semantic.txt"

    rush_stem = rush.stem
    rush_dir = rush.parent
    # Final Cut Pro 7 XML (XMEML) format with the .xml extension:
    # the only format Premiere Pro reads natively (modern .fcpxml is refused).
    out_xml = rush_dir / f"{rush_stem}_Derush_v{meta['version']}.xml"
    out_report = rush_dir / f"{rush_stem}_Derush_v{meta['version']}.report.md"
    out_log = rush_dir / f"{rush_stem}_Derush_v{meta['version']}.log.txt"

    if args.resume_from <= 2:
        run_stage("2/extract_audio", [sys.executable, str(SCRIPTS / "extract_audio.py"),
                                       str(rush), str(audio_wav)], work)
    if args.resume_from <= 3:
        run_stage("3/transcribe", [sys.executable, str(SCRIPTS / "transcribe.py"),
                                    str(audio_wav), str(transcript),
                                    "--model", args.model,
                                    "--meta", str(meta_file)] + lang_args, work)
    if args.resume_from <= 4:
        run_stage("4/mechanical_cuts", [sys.executable, str(SCRIPTS / "mechanical_cuts.py"),
                                         str(transcript), str(cuts_mech),
                                         str(audio_wav)] + lang_args, work)
    if args.resume_from <= 5:
        # Stage 5: optional webhook (DERUSH_WEBHOOK); without it, or when it fails,
        # "LLM-as-stage" mode: the AI reads prompt_semantic.txt and writes cuts_semantic.json.
        if not cuts_sem.exists():
            try:
                if not DERUSH_WEBHOOK:
                    raise urllib.error.URLError("no DERUSH_WEBHOOK: analysis done in context")
                print(f"[5/semantic] POST {DERUSH_WEBHOOK}")
                payload = {
                    "transcript": json.loads(transcript.read_text()),
                    "cuts_mechanical": json.loads(cuts_mech.read_text()),
                    "meta": meta,
                }
                req = urllib.request.Request(
                    DERUSH_WEBHOOK,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=180) as resp:
                    data = json.loads(resp.read())
                    cuts_sem.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                    n = len(data.get("cuts", []))
                    print(f"  Received {n} semantic cuts from the webhook.")
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
                print(f"  [5/semantic] {e}: prompt for the AI in context.")
                run_stage("5a/llm_prompt", [sys.executable, str(SCRIPTS / "llm_prompt_builder.py"),
                                             str(transcript), str(cuts_mech),
                                             str(prompt_file), str(cuts_sem)] + lang_args, work)
                print()
                print("=" * 70)
                print("STAGE 5: LLM semantic analysis (manual)")
                print("=" * 70)
                print(f"1. Read: {prompt_file}")
                print(f"2. Write the JSON result into: {cuts_sem}")
                print(f"3. Resume: python3 {Path(__file__).resolve()} {rush} "
                      f"--resume-from=6 --work-dir={work}")
                print("=" * 70)
                sys.exit(0)

    if args.resume_from <= 6:
        run_stage("6/merge", [sys.executable, str(SCRIPTS / "merge_cuts.py"),
                               str(cuts_mech), str(cuts_sem), str(meta_file),
                               str(cuts_final), str(transcript)], work)
    if args.resume_from <= 7:
        run_stage("7/build_premiere_xml", [sys.executable, str(SCRIPTS / "build_premiere_xml.py"),
                                            str(cuts_final), str(meta_file), str(out_xml)], work)
    if args.resume_from <= 8:
        run_stage("8/build_report", [sys.executable, str(SCRIPTS / "build_report.py"),
                                      str(cuts_final), str(meta_file), str(out_report)], work)

    # Copy the work log next to the final output
    if (work / "log.txt").exists():
        out_log.write_text((work / "log.txt").read_text())

    # The work folder is NOT deleted: everything stays next to the clip,
    # for manual resume, inspection and checking.

    # Summary
    stats = json.loads(cuts_final.read_text())["stats"]
    print()
    print("=" * 70)
    print(f"Rough cut done: {out_xml.name}")
    print(f"  Disabled cuts: {stats['cuts_disabled']}")
    print(f"  Red markers:   {stats['cuts_flagged']}")
    print(f"  Time saved:    {stats['time_removed_seconds']:.1f}s "
          f"({stats['ratio'] * 100:.0f}% of the clip)")
    print("=" * 70)
    print(f"Import into Premiere: {out_xml}")
    print(f"  File > Import (Premiere reads the .xml extension natively)")


if __name__ == "__main__":
    main()
