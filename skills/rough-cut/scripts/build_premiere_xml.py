#!/usr/bin/env python3
"""Generates a Final Cut Pro 7 XML (XMEML) that Premiere Pro imports natively.

Premiere Pro does NOT read the modern FCPXML format (Final Cut Pro X 1.8+).
It only accepts the old Final Cut Pro 7 XMEML format, with the .xml extension.

The spine is made of parallel tracks (video + audio) holding only the kept clipitems,
end to end (the disabled cuts are removed). Markers at sequence level, with absolute
timecodes in frames.

Usage:
    python3 build_premiere_xml.py cuts_final.json meta.json output.xml
"""
import json
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom


def fps_to_xmeml(fps_num, fps_den):
    """Returns (timebase, ntsc) for XMEML.

    XMEML uses an integer timebase + an ntsc flag. Standard mapping:
    - 25/1     → timebase=25, ntsc=FALSE
    - 30/1     → timebase=30, ntsc=FALSE
    - 24/1     → timebase=24, ntsc=FALSE
    - 30000/1001 (29.97) → timebase=30, ntsc=TRUE
    - 24000/1001 (23.976) → timebase=24, ntsc=TRUE
    - 60/1     → timebase=60, ntsc=FALSE
    - 60000/1001 (59.94) → timebase=60, ntsc=TRUE
    - 50/1     → timebase=50, ntsc=FALSE
    """
    fps = fps_num / fps_den
    if fps_den == 1001:
        timebase = round(fps_num / 1000)
        ntsc = "TRUE"
    else:
        timebase = round(fps)
        ntsc = "FALSE"
    return timebase, ntsc


def seconds_to_frames(seconds, timebase, ntsc):
    """Converts seconds to XMEML frames."""
    if ntsc == "TRUE":
        # NTSC: 1 frame = 1001/(timebase*1000) seconds
        frames = round(seconds * timebase * 1000 / 1001)
    else:
        frames = round(seconds * timebase)
    return frames


def file_url(path):
    abs_path = Path(path).resolve()
    return "file://localhost" + urllib.parse.quote(str(abs_path))


def add_rate(parent, timebase, ntsc):
    rate = ET.SubElement(parent, "rate")
    ET.SubElement(rate, "timebase").text = str(timebase)
    ET.SubElement(rate, "ntsc").text = ntsc


def make_file_element(file_id, rush_path, total_frames, timebase, ntsc, width, height,
                      audio_channels, audio_rate, full=True):
    """Creates a <file>. With full=False, returns just <file id="..."/>."""
    file_el = ET.Element("file", {"id": file_id})
    if not full:
        return file_el
    ET.SubElement(file_el, "name").text = Path(rush_path).name
    ET.SubElement(file_el, "pathurl").text = file_url(rush_path)
    add_rate(file_el, timebase, ntsc)
    ET.SubElement(file_el, "duration").text = str(total_frames)

    media = ET.SubElement(file_el, "media")
    video = ET.SubElement(media, "video")
    video_sc = ET.SubElement(video, "samplecharacteristics")
    add_rate(video_sc, timebase, ntsc)
    ET.SubElement(video_sc, "width").text = str(width)
    ET.SubElement(video_sc, "height").text = str(height)
    ET.SubElement(video_sc, "anamorphic").text = "FALSE"
    ET.SubElement(video_sc, "pixelaspectratio").text = "square"
    ET.SubElement(video_sc, "fielddominance").text = "none"

    audio = ET.SubElement(media, "audio")
    ET.SubElement(audio, "channelcount").text = str(audio_channels)
    audio_sc = ET.SubElement(audio, "samplecharacteristics")
    ET.SubElement(audio_sc, "depth").text = "16"
    ET.SubElement(audio_sc, "samplerate").text = str(audio_rate)

    return file_el


def make_audio_file_element(file_id, wav_path, total_frames, timebase, ntsc,
                            audio_channels, audio_rate, full=True):
    """Audio-only <file> (processed full-length WAV, aligned on the start of the clip).

    Lets the audio clips of the timeline point to an already processed mix
    (Enhance Speech, EQ...) exported by the user: the dynamics are computed on the
    WHOLE track before cutting, and the effects do not get lost at import.
    """
    file_el = ET.Element("file", {"id": file_id})
    if not full:
        return file_el
    ET.SubElement(file_el, "name").text = Path(wav_path).name
    ET.SubElement(file_el, "pathurl").text = file_url(wav_path)
    add_rate(file_el, timebase, ntsc)
    ET.SubElement(file_el, "duration").text = str(total_frames)
    media = ET.SubElement(file_el, "media")
    audio = ET.SubElement(media, "audio")
    ET.SubElement(audio, "channelcount").text = str(audio_channels)
    audio_sc = ET.SubElement(audio, "samplecharacteristics")
    ET.SubElement(audio_sc, "depth").text = "16"
    ET.SubElement(audio_sc, "samplerate").text = str(audio_rate)
    return file_el


def make_clipitem(clipitem_id, name, file_el, in_f, out_f, start_f, end_f,
                  enabled, timebase, ntsc, media_type, audio_track_index=None,
                  note=None):
    """Creates a <clipitem>.

    media_type is "video" or "audio".
    in_f / out_f: timecodes in the source (in frames).
    start_f / end_f: position in the sequence (in frames).
    """
    clip = ET.Element("clipitem", {"id": clipitem_id})
    ET.SubElement(clip, "name").text = name
    ET.SubElement(clip, "enabled").text = "TRUE" if enabled else "FALSE"
    ET.SubElement(clip, "duration").text = str(out_f - in_f)
    add_rate(clip, timebase, ntsc)
    ET.SubElement(clip, "in").text = str(in_f)
    ET.SubElement(clip, "out").text = str(out_f)
    ET.SubElement(clip, "start").text = str(start_f)
    ET.SubElement(clip, "end").text = str(end_f)
    clip.append(file_el)

    if media_type == "audio":
        sourcetrack = ET.SubElement(clip, "sourcetrack")
        ET.SubElement(sourcetrack, "mediatype").text = "audio"
        ET.SubElement(sourcetrack, "trackindex").text = str(audio_track_index or 1)

    if note:
        # In XMEML, notes go in a separate comment, or through <comments>
        comments = ET.SubElement(clip, "comments")
        master = ET.SubElement(comments, "mastercomment1")
        master.text = note

    return clip


def build_spine_clips(cuts, total_duration):
    """Final spine: only the KEEP passages (the disabled ones are really removed).

    Flags stay inside the kept clips and get a red marker at sequence level.
    """
    disable_cuts = sorted(
        [c for c in cuts if c["decision"] == "disable"],
        key=lambda c: c["start"],
    )
    flag_cuts = sorted(
        [c for c in cuts if c["decision"] == "flag"],
        key=lambda c: c["start"],
    )

    # The list of "intervals to keep" is built by subtracting the disabled cuts
    spine = []
    position = 0.0
    for cut in disable_cuts:
        cut_start = max(cut["start"], position)
        cut_end = max(cut["end"], cut_start)
        if cut_start > position:
            spine.append({
                "start": position, "end": cut_start,
                "markers": [],
            })
        position = cut_end

    # end leftover shorter than 2 frames: no clip is created (Premiere rejects a
    # clipitem whose in == out after rounding to frames)
    if total_duration - position > 0.07:
        spine.append({
            "start": position, "end": total_duration,
            "markers": [],
        })

    # Attach the flag markers to the matching kept clips
    for fc in flag_cuts:
        for clip in spine:
            if clip["start"] <= fc["start"] < clip["end"]:
                clip["markers"].append({
                    "start": fc["start"],
                    "end": min(fc["end"], clip["end"]),
                    "value": f"DOUBT {fc['type']} (conf {fc['confidence']:.2f}): {fc['reason']}",
                })
                break

    return spine


def main():
    if len(sys.argv) != 4:
        print("Usage: build_premiere_xml.py <cuts_final.json> <meta.json> <output.xml>",
              file=sys.stderr)
        sys.exit(1)

    cuts_data = json.loads(Path(sys.argv[1]).read_text())
    meta = json.loads(Path(sys.argv[2]).read_text())
    out_path = Path(sys.argv[3])

    cuts = cuts_data["cuts"]
    fps_num = meta["fps_num"]
    fps_den = meta["fps_den"]
    duration = meta["duration_seconds"]
    width = meta["width"]
    height = meta["height"]
    rush_path = meta["rush_path"]
    audio_channels = meta["audio_channels"]
    audio_rate = meta["audio_rate"]
    project_name = f"Derush_v{meta.get('version', 1)}"

    timebase, ntsc = fps_to_xmeml(fps_num, fps_den)
    total_frames = seconds_to_frames(duration, timebase, ntsc)

    spine_clips = build_spine_clips(cuts, duration)

    # Duration of the final sequence = sum of the kept clips (the disabled ones are removed)
    sequence_duration_s = sum(c["end"] - c["start"] for c in spine_clips)
    sequence_duration_f = seconds_to_frames(sequence_duration_s, timebase, ntsc)

    # Root
    xmeml = ET.Element("xmeml", {"version": "5"})
    sequence = ET.SubElement(xmeml, "sequence", {"id": project_name})
    ET.SubElement(sequence, "name").text = project_name
    ET.SubElement(sequence, "duration").text = str(sequence_duration_f)
    add_rate(sequence, timebase, ntsc)
    ET.SubElement(sequence, "in").text = "-1"
    ET.SubElement(sequence, "out").text = "-1"

    timecode = ET.SubElement(sequence, "timecode")
    add_rate(timecode, timebase, ntsc)
    ET.SubElement(timecode, "string").text = "00:00:00:00"
    ET.SubElement(timecode, "frame").text = "0"
    ET.SubElement(timecode, "displayformat").text = "NDF" if ntsc == "FALSE" else "DF"

    media = ET.SubElement(sequence, "media")

    # ====== VIDEO TRACK ======
    video_media = ET.SubElement(media, "video")
    v_format = ET.SubElement(video_media, "format")
    v_sc = ET.SubElement(v_format, "samplecharacteristics")
    add_rate(v_sc, timebase, ntsc)
    ET.SubElement(v_sc, "width").text = str(width)
    ET.SubElement(v_sc, "height").text = str(height)
    ET.SubElement(v_sc, "anamorphic").text = "FALSE"
    ET.SubElement(v_sc, "pixelaspectratio").text = "square"
    ET.SubElement(v_sc, "fielddominance").text = "none"

    v_track = ET.SubElement(video_media, "track")

    # The full <file> goes on the first clipitem and is then reused by reference
    file_id = "file-1"
    file_full = make_file_element(file_id, rush_path, total_frames, timebase, ntsc,
                                   width, height, audio_channels, audio_rate, full=True)

    # Sequence positions accumulated in whole FRAMES: guarantees end-start == out-in
    # and continuity with no hole (independent seconds->frames roundings created
    # one-frame differences between duration and end-start, which Premiere rejects).
    seq_frames = 0
    first_video_done = False
    for i, clip in enumerate(spine_clips):
        clip_duration = clip["end"] - clip["start"]
        if clip_duration < 0.07:  # < 2 frames: invalid clip for Premiere (in == out)
            continue

        in_f = seconds_to_frames(clip["start"], timebase, ntsc)
        out_f = seconds_to_frames(clip["end"], timebase, ntsc)
        start_f = seq_frames
        end_f = seq_frames + (out_f - in_f)
        name = f"keep_{i:03d}"

        # Full file on the 1st clip, reference afterwards
        if not first_video_done:
            file_el = file_full
            first_video_done = True
        else:
            file_el = make_file_element(file_id, rush_path, total_frames, timebase, ntsc,
                                         width, height, audio_channels, audio_rate, full=False)

        clipitem = make_clipitem(
            f"clipitem-v-{i:03d}", name, file_el,
            in_f, out_f, start_f, end_f,
            True, timebase, ntsc, "video",
        )
        v_track.append(clipitem)

        seq_frames = end_f

    # Track flags (video)
    ET.SubElement(v_track, "enabled").text = "TRUE"
    ET.SubElement(v_track, "locked").text = "FALSE"

    # ====== AUDIO TRACKS ======
    audio_media = ET.SubElement(media, "audio")
    audio_format = ET.SubElement(audio_media, "format")
    audio_sc = ET.SubElement(audio_format, "samplecharacteristics")
    ET.SubElement(audio_sc, "depth").text = "16"
    ET.SubElement(audio_sc, "samplerate").text = str(audio_rate)

    # Audio source: the clip, or a processed full-length WAV when meta["audio_file"] is set
    # (mix exported with the user's effects: see make_audio_file_element).
    audio_file = meta.get("audio_file")
    audio_file_id = "file-2" if audio_file else file_id
    first_audio_done = False

    # One track per audio channel (stereo = 2 tracks in standard Premiere XMEML)
    for ch in range(1, audio_channels + 1):
        a_track = ET.SubElement(audio_media, "track")
        seq_frames = 0
        for i, clip in enumerate(spine_clips):
            clip_duration = clip["end"] - clip["start"]
            if clip_duration < 0.07:  # < 2 frames: invalid clip for Premiere (in == out)
                continue
            in_f = seconds_to_frames(clip["start"], timebase, ntsc)
            out_f = seconds_to_frames(clip["end"], timebase, ntsc)
            start_f = seq_frames
            end_f = seq_frames + (out_f - in_f)
            name = f"keep_{i:03d}"

            if audio_file:
                file_el = make_audio_file_element(audio_file_id, audio_file, total_frames,
                                                  timebase, ntsc, audio_channels, audio_rate,
                                                  full=not first_audio_done)
                first_audio_done = True
            else:
                file_el = make_file_element(file_id, rush_path, total_frames, timebase, ntsc,
                                            width, height, audio_channels, audio_rate, full=False)
            clipitem = make_clipitem(
                f"clipitem-a{ch}-{i:03d}", name, file_el,
                in_f, out_f, start_f, end_f,
                True, timebase, ntsc, "audio",
                audio_track_index=ch,
            )
            a_track.append(clipitem)
            seq_frames = end_f

        ET.SubElement(a_track, "enabled").text = "TRUE"
        ET.SubElement(a_track, "locked").text = "FALSE"

    # ====== MARKERS at sequence level ======
    n_markers = 0
    for clip in spine_clips:
        for marker in clip["markers"]:
            # Position of the marker in the sequence (not in the source):
            # marker.start is in source time, but since the sequence is rebuilt
            # with cuts, its sequence offset differs. It is remapped through the
            # parent clip, by adding up the durations of the previous clips.
            seq_offset = 0.0
            for c in spine_clips:
                if c is clip:
                    seq_offset += marker["start"] - c["start"]
                    break
                seq_offset += c["end"] - c["start"]
            marker_start_f = seconds_to_frames(seq_offset, timebase, ntsc)
            marker_dur = max(marker["end"] - marker["start"], 1.0 / 30.0)
            marker_end_f = marker_start_f + seconds_to_frames(marker_dur, timebase, ntsc)

            m_el = ET.SubElement(sequence, "marker")
            ET.SubElement(m_el, "comment").text = marker["value"]
            ET.SubElement(m_el, "name").text = "Doubt"
            ET.SubElement(m_el, "in").text = str(marker_start_f)
            ET.SubElement(m_el, "out").text = str(marker_end_f)
            n_markers += 1

    # Pretty print + DOCTYPE
    # Self-check before writing: Premiere refuses a clipitem whose duration is zero
    # or whose (end - start) != (out - in): an "invalid track item start/end" error
    # at import, and an unusable track.
    errors = []
    for c in xmeml.iter("clipitem"):
        i_f = int(c.find("in").text)
        o_f = int(c.find("out").text)
        s_f = int(c.find("start").text)
        e_f = int(c.find("end").text)
        if o_f - i_f < 1 or e_f - s_f < 1 or (o_f - i_f) != (e_f - s_f):
            errors.append(f"{c.find('name').text}: in={i_f} out={o_f} start={s_f} end={e_f}")
    if errors:
        print("ERROR: invalid clipitems, XML not written:", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        sys.exit(1)

    rough = ET.tostring(xmeml, encoding="utf-8")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")
    lines = pretty.splitlines()
    if lines[0].startswith("<?xml"):
        lines.insert(1, "<!DOCTYPE xmeml>")
    out_path.write_text("\n".join(lines))

    print(f"Premiere XML written: {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    print(f"  Clips in the sequence: {len(spine_clips)}")
    print(f"  Sequence duration: {sequence_duration_s:.1f}s "
          f"(original clip: {duration:.1f}s)")
    print(f"  Markers (to review): {n_markers}")
    print(f"  Audio tracks: {audio_channels}")


if __name__ == "__main__":
    main()
