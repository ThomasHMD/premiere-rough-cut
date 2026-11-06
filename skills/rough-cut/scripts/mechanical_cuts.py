#!/usr/bin/env python3
"""Mechanical detection of cuts from the whisper transcript + the raw audio.

Three passes:
1. Isolated fillers: "um", "uh", etc. (the language file's lists).
2. Acoustic silences with FFmpeg silencedetect (-30dB, > 0.6s).
   Essential because whisper misses the silences inside a segment.
3. Immediate textual repetitions: N-grams (N=2..6) repeated less than 2s apart.

False-start markers ("wait", "let me start again") are only detected,
to point windows out to the LLM (stage 5), never cut here.

Usage:
    python3 mechanical_cuts.py transcript.json cuts_mechanical.json [audio.wav] [--lang fr]

If audio.wav is given, FFmpeg silencedetect is used (recommended).
Otherwise fallback on the gaps between whisper words (less reliable).

Word lists, patterns and reason texts come from ../languages/<code>.json: --lang, else the
"language" of the transcript, else en.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import lang

# Language data (languages/<code>.json), loaded in main()
LANG = {}
# Characters removed by normalize_word; main() adds the language's word_chars
NON_WORD = r"[^\w'-]"

SILENCE_VERY_LONG_S = 30.0   # > 30s: automatic cut (probably empty, no B-roll that long)
SILENCE_FLAG_S = 0.6         # 0.6..30s: flag only (the editor decides by looking)
SILENCE_BUFFER_S = 0.18      # breath kept on each side of the silence
SILENCE_DB_THRESHOLD = -30   # acoustic threshold (FFmpeg silencedetect)
REPETITION_WINDOW_S = 2.0    # window within which a repetition counts
REPETITION_MIN_NGRAM = 2
REPETITION_MAX_NGRAM = 6


def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    fallback = Path("/opt/homebrew/bin/ffmpeg")
    if fallback.exists():
        return str(fallback)
    return None


def detect_silences_ffmpeg(audio_path, threshold_db=SILENCE_DB_THRESHOLD,
                            min_duration_s=SILENCE_FLAG_S):
    """Runs ffmpeg silencedetect on audio.wav and parses its output."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    cmd = [
        ffmpeg, "-hide_banner", "-i", str(audio_path),
        "-af", f"silencedetect=n={threshold_db}dB:d={min_duration_s}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr  # silencedetect prints on stderr

    silences = []
    current_start = None
    for line in output.splitlines():
        if "silence_start:" in line:
            try:
                current_start = float(line.split("silence_start:")[1].strip().split()[0])
            except Exception:
                current_start = None
        elif "silence_end:" in line and current_start is not None:
            try:
                end = float(line.split("silence_end:")[1].split("|")[0].strip())
                duration = end - current_start
                silences.append({
                    "start": current_start,
                    "end": end,
                    "duration": duration,
                })
                current_start = None
            except Exception:
                current_start = None
    return silences


def load_marqueurs(data):
    """The three word lists of the language data: fillers, sentence-start fillers, false starts."""
    return (set(data["fillers"]), set(data["sentence_start_fillers"]),
            list(data["false_start_triggers"]))


def normalize_word(w):
    """Lowercase + strip the punctuation around."""
    return re.sub(NON_WORD, "", w.lower())


def flatten_words(transcript):
    """Flat list of all the words with their timecodes and their segment."""
    flat = []
    for seg in transcript["segments"]:
        for word in seg["words"]:
            flat.append({
                "text": word["text"],
                "norm": normalize_word(word["text"]),
                "start": word["start"],
                "end": word["end"],
                "confidence": word.get("confidence", 0.9),
                "segment_id": seg["id"],
            })
    return flat


def context_around(words, idx, span_chars=80):
    """Returns the words before/after, for context."""
    before = ""
    i = idx - 1
    while i >= 0 and len(before) < span_chars:
        before = words[i]["text"] + " " + before
        i -= 1
    after = ""
    i = idx + 1
    while i < len(words) and len(after) < span_chars:
        after = after + " " + words[i]["text"]
        i += 1
    return before.strip(), after.strip()


def detect_fillers(words, fillers, fillers_debut):
    """Detects isolated fillers and proposes cuts."""
    cuts = []
    for i, w in enumerate(words):
        norm = w["norm"]
        is_filler = norm in fillers
        is_filler_debut = norm in fillers_debut
        if not is_filler and not is_filler_debut:
            continue

        # Sentence-start filler: cut only at a real sentence start or after a silence
        if is_filler_debut and not is_filler:
            prev_gap = w["start"] - words[i - 1]["end"] if i > 0 else 999
            if prev_gap < 0.4:
                continue  # "well" in the middle of a sentence: kept

        before, after = context_around(words, i)
        cuts.append({
            "id": f"c_filler_{i:04d}",
            "start": round(max(0, w["start"] - 0.05), 3),
            "end": round(w["end"] + 0.05, 3),
            "type": "filler",
            "confidence": 0.95 if is_filler else 0.85,
            "reason": LANG["reasons"]["filler"].format(text=w["text"]),
            "matched_text": w["text"],
            "context_before": before,
            "context_after": after,
            "source": "mechanical",
        })
    return cuts


def detect_silences(words, total_duration, audio_path=None):
    """Detects silences with FFmpeg silencedetect, snapped to word boundaries.

    CRITICAL: never cut inside a whisper word. The cut must line up with the
    end of the last word before the silence and the start of the first word
    after it (with a small 50ms margin).
    """
    if audio_path:
        ff_silences = detect_silences_ffmpeg(audio_path)
        if ff_silences is None:
            print("WARN: ffmpeg not found, falling back on whisper gaps", file=sys.stderr)
            ff_silences = None
    else:
        ff_silences = None

    if ff_silences is None:
        return _detect_silences_whisper_gaps(words, total_duration)

    # Each ffmpeg silence is snapped to the whisper word boundaries.
    cuts = []
    for i, sil in enumerate(ff_silences):
        sil_start = sil["start"]
        sil_end = sil["end"]
        duration = sil["duration"]

        # Last word ending BEFORE the silence
        before_word = None
        for w in reversed(words):
            if w["end"] <= sil_start + 0.05:  # 50ms tolerance
                before_word = w
                break

        # First word starting AFTER the silence
        after_word = None
        for w in words:
            if w["start"] >= sil_end - 0.05:
                after_word = w
                break

        # Cut boundaries: just after the previous word, just before the next one
        if before_word:
            cut_start = round(before_word["end"] + SILENCE_BUFFER_S, 3)
        else:
            cut_start = round(sil_start + SILENCE_BUFFER_S, 3)

        if after_word:
            cut_end = round(after_word["start"] - SILENCE_BUFFER_S, 3)
        else:
            cut_end = round(sil_end - SILENCE_BUFFER_S, 3)

        # Range too short or inverted: skip
        if cut_end - cut_start < 0.15:
            continue

        # Safety: if the cut goes into a whisper word, shrink it
        for w in words:
            # word overlapping the start of the cut: move cut_start after it
            if w["start"] < cut_start < w["end"]:
                cut_start = round(w["end"] + 0.02, 3)
            # word overlapping the end of the cut: move cut_end before it
            if w["start"] < cut_end < w["end"]:
                cut_end = round(w["start"] - 0.02, 3)

        if cut_end - cut_start < 0.15:
            continue

        # Silences: flag only by default. The editor decides by looking,
        # because it can be B-roll, a dramatic pause, or a real gap to remove.
        # Only very long silences (>30s) are cut automatically.
        if duration >= SILENCE_VERY_LONG_S:
            confidence = 0.92
        else:
            confidence = 0.75

        cuts.append({
            "id": f"c_silence_{i:04d}",
            "start": cut_start,
            "end": cut_end,
            "type": "silence",
            "confidence": confidence,
            "reason": LANG["reasons"]["silence_acoustic"].format(duration=duration),
            "matched_text": "",
            "context_before": before_word["text"] if before_word else "",
            "context_after": after_word["text"] if after_word else "",
            "source": "mechanical",
        })

    return cuts


def detect_similar_phrases(transcript_segments):
    """Detects very similar consecutive sentences (rephrasings).

    Observed pattern: the speaker says a sentence, fumbles it, says a close
    variant. Keeps the 2nd one (often more complete).

    Match when 2 consecutive sentences share >=60% of their content (Jaccard
    on the significant words of more than 3 characters).
    """
    cuts = []
    openers = tuple(LANG["correction_openers"])
    sigs = []  # list of (segment, set_of_significant_words)
    for seg in transcript_segments:
        words = [w["text"].lower() for w in seg.get("words", [])]
        sig = set(w for w in words if len(w) >= 4 and not w.startswith("'"))
        sigs.append((seg, sig))

    for i in range(len(sigs) - 1):
        seg_a, sig_a = sigs[i]
        for j in range(i + 1, min(i + 6, len(sigs))):
            seg_b, sig_b = sigs[j]
            if not sig_a or not sig_b:
                continue
            # Jaccard
            inter = len(sig_a & sig_b)
            union = len(sig_a | sig_b)
            if union == 0:
                continue
            jaccard = inter / union

            # Time distance between the 2 sentences
            gap = seg_b["start"] - seg_a["end"]
            if gap > 12:
                break

            # Threshold: sentences with enough shared significant words
            min_sig = min(len(sig_a), len(sig_b))
            if min_sig < 3:
                continue

            # Bonus when seg_b or one of the segments in between starts with a
            # correction opener ("no"): the "X. No, Y." pattern, where Y rephrases X
            text_b = (seg_b.get("text") or "").lstrip().lower()
            non_correction = text_b.startswith(openers) or any(
                (sigs[k][0].get("text") or "").lstrip().lower().startswith(openers)
                for k in range(i + 1, j)
            )

            threshold = 0.45 if non_correction else 0.55
            min_inter = 3 if non_correction else 4

            if jaccard >= threshold and inter >= min_inter:
                # Rephrasing. Cut the 1st version (from the start of seg_a
                # to the start of seg_b).
                cut_start = seg_a["start"]
                cut_end = seg_b["start"] - 0.1
                if cut_end - cut_start < 0.5:
                    continue
                # Confidence proportional to the similarity
                conf = 0.78 if jaccard < 0.75 else 0.85
                cuts.append({
                    "id": f"c_reform_{i:04d}",
                    "start": round(cut_start, 3),
                    "end": round(cut_end, 3),
                    "type": "semantic_restart",
                    "confidence": conf,
                    "reason": LANG["reasons"]["rephrasing"].format(jaccard=jaccard),
                    "matched_text": seg_a.get("text", "")[:60],
                    "context_before": "",
                    "context_after": seg_b.get("text", "")[:60],
                    "source": "mechanical",
                })
                break  # no other match searched for seg_a
    return cuts


def detect_slate(words):
    """Detects a take slate at the start of the clip and proposes a cut.

    Typical patterns: "1, 2, 1, 2, we're rolling", "1, 2, 3", "test test" (the
    slate_patterns of the language file). Only applies to the first 15 seconds.
    """
    if not words:
        return []

    # Text of the first 15 seconds
    head_words = [w for w in words if w["start"] < 15]
    if not head_words:
        return []
    head_text = " ".join(w["norm"] for w in head_words).lower()

    SLATE_PATTERNS = LANG["slate_patterns"]

    slate_end_word_idx = -1
    for pattern in SLATE_PATTERNS:
        m = re.search(pattern, head_text)
        if m:
            # Character position to word
            chars_seen = 0
            for wi, w in enumerate(head_words):
                # +1 for the space between words
                end_char = chars_seen + len(w["norm"])
                if end_char >= m.end():
                    slate_end_word_idx = max(slate_end_word_idx, wi)
                    break
                chars_seen = end_char + 1

    if slate_end_word_idx < 0:
        return []

    # Cut from 0 to the start of the word after the slate
    if slate_end_word_idx + 1 < len(head_words):
        cut_end = round(head_words[slate_end_word_idx + 1]["start"] - 0.1, 3)
    else:
        cut_end = round(head_words[slate_end_word_idx]["end"] + 0.3, 3)

    if cut_end <= 0.2:
        return []

    return [{
        "id": "c_slate",
        "start": 0.0,
        "end": cut_end,
        "type": "filler",
        "confidence": 0.95,
        "reason": LANG["reasons"]["slate"],
        "matched_text": " ".join(w["text"] for w in head_words[:slate_end_word_idx + 1]),
        "context_before": "",
        "context_after": head_words[slate_end_word_idx + 1]["text"] if slate_end_word_idx + 1 < len(head_words) else "",
        "source": "mechanical",
    }]


def _detect_silences_whisper_gaps(words, total_duration):
    """Fallback: silences from the gaps between whisper words (less reliable)."""
    cuts = []
    if not words:
        return cuts

    if words[0]["start"] > SILENCE_HARD_CUT_S:
        cuts.append({
            "id": "c_silence_head",
            "start": 0.0,
            "end": round(words[0]["start"] - SILENCE_BUFFER_S, 3),
            "type": "silence",
            "confidence": 0.92,
            "reason": LANG["reasons"]["silence_head"].format(start=words[0]["start"]),
            "matched_text": "",
            "context_before": "",
            "context_after": words[0]["text"],
            "source": "mechanical",
        })

    for i in range(len(words) - 1):
        gap_start = words[i]["end"]
        gap_end = words[i + 1]["start"]
        gap = gap_end - gap_start
        if gap < SILENCE_FLAG_S:
            continue
        cut_start = round(gap_start + SILENCE_BUFFER_S, 3)
        cut_end = round(gap_end - SILENCE_BUFFER_S, 3)
        if cut_end <= cut_start:
            continue
        confidence = 0.92 if gap >= SILENCE_HARD_CUT_S else 0.7
        cuts.append({
            "id": f"c_silence_{i:04d}",
            "start": cut_start,
            "end": cut_end,
            "type": "silence",
            "confidence": confidence,
            "reason": LANG["reasons"]["silence_between_words"].format(gap=gap),
            "matched_text": "",
            "context_before": words[i]["text"],
            "context_after": words[i + 1]["text"],
            "source": "mechanical",
        })

    if total_duration and total_duration - words[-1]["end"] > SILENCE_HARD_CUT_S:
        cuts.append({
            "id": "c_silence_tail",
            "start": round(words[-1]["end"] + SILENCE_BUFFER_S, 3),
            "end": round(total_duration, 3),
            "type": "silence",
            "confidence": 0.95,
            "reason": LANG["reasons"]["silence_tail"].format(duration=total_duration - words[-1]["end"]),
            "matched_text": "",
            "context_before": words[-1]["text"],
            "context_after": "",
            "source": "mechanical",
        })

    return cuts


def detect_repetitions(words):
    """Detects immediate N-gram repetitions (less than 2s apart).

    Strategy: for each position i, check whether the N-gram (N=2..6) starting
    at i is repeated exactly somewhere between i+N and i+N+window.
    If so, the FIRST occurrence is cut (with every word between the two).

    Confidence depends on N and on the weight of the tokens:
    - N=2: max 0.75 (flag, no automatic cut)
    - N=3: max 0.80 (flag)
    - N=4: 0.88 (cut)
    - N=5+: 0.92 (cut)
    If every token is empty (words under 3 characters or stop words), it drops to 0.6.
    """
    # Short stop words of the language, which should not justify an automatic cut:
    # connectors and articles common in spoken speech.
    STOP_WORDS = set(LANG["stop_words"])

    def is_trivial_ngram(seq):
        """Trivial N-gram: every token is a stop word OR under 3 characters OR punctuation."""
        meaningful = 0
        for tok in seq:
            t = tok.strip()
            if not t:
                continue
            if len(t) < 3:
                continue
            if t in STOP_WORDS:
                continue
            meaningful += 1
        return meaningful == 0

    cuts = []
    n = len(words)
    flagged_indices = set()

    for i in range(n):
        if i in flagged_indices:
            continue
        for ngram in range(REPETITION_MAX_NGRAM, REPETITION_MIN_NGRAM - 1, -1):
            if i + ngram >= n:
                continue
            seq1 = [words[i + k]["norm"] for k in range(ngram)]
            seq1_end_time = words[i + ngram - 1]["end"]

            # Look for the same sequence within the window
            j = i + ngram
            found_match = -1
            while j < n - ngram + 1:
                if words[j]["start"] - seq1_end_time > REPETITION_WINDOW_S:
                    break
                seq2 = [words[j + k]["norm"] for k in range(ngram)]
                if seq1 == seq2:
                    found_match = j
                    break
                j += 1

            if found_match > 0:
                # Cut from the start of seq1 to the start of seq2 (excluded),
                # snapped to the exact boundaries of the whisper words.
                cut_start = words[i]["start"]
                # Cut end = just before the 1st word of the 2nd occurrence
                cut_end = words[found_match]["start"] - 0.02
                matched = " ".join(words[i + k]["text"] for k in range(ngram))
                before, after = context_around(words, i)

                # Confidence depends on N. Very conservative: even long
                # repetitions are sometimes rephrasings or rhetorical structures
                # that the editor keeps. Everything is a flag except the very
                # long ones (N>=6), which are almost always real retakes to remove.
                if ngram >= 6:
                    conf = 0.88
                elif ngram == 5:
                    conf = 0.82
                elif ngram == 4:
                    conf = 0.78
                elif ngram == 3:
                    conf = 0.72
                else:  # N=2
                    conf = 0.65

                # Trivial (stop words / short words): lower still
                if is_trivial_ngram(seq1):
                    conf = min(conf, 0.55)

                cuts.append({
                    "id": f"c_rep_{i:04d}",
                    "start": round(cut_start, 3),
                    "end": round(cut_end, 3),
                    "type": "repetition",
                    "confidence": round(conf, 2),
                    "reason": LANG["reasons"]["repetition"].format(text=matched, n=ngram),
                    "matched_text": matched,
                    "context_before": before,
                    "context_after": after,
                    "source": "mechanical",
                })
                for k in range(found_match - i):
                    flagged_indices.add(i + k)
                break  # smaller n-grams are not tested at the same position

    return cuts


def detect_false_start_windows(words, false_start_triggers):
    """Finds the zones that contain a false-start marker.

    Returns no cut, only a window pointed out to the LLM (stage 5).
    Format: type=false_start_window, score=0 (not a decision).
    """
    windows = []
    norm_text = " ".join(w["norm"] for w in words)

    for trigger in false_start_triggers:
        trigger_norm = trigger.lower()
        # Plain search in the normalized text
        idx = 0
        while idx < len(norm_text):
            pos = norm_text.find(trigger_norm, idx)
            if pos == -1:
                break
            # Character position back to word index
            chars_seen = 0
            word_idx = -1
            for wi, w in enumerate(words):
                if chars_seen + len(w["norm"]) >= pos:
                    word_idx = wi
                    break
                chars_seen += len(w["norm"]) + 1  # +1 for the space

            if word_idx >= 0:
                window_start = max(0, word_idx - 8)
                window_end = min(len(words), word_idx + 10)
                start_t = words[window_start]["start"]
                end_t = words[window_end - 1]["end"]
                windows.append({
                    "id": f"w_fs_{word_idx:04d}",
                    "start": round(start_t, 3),
                    "end": round(end_t, 3),
                    "type": "false_start_window",
                    "confidence": 0.0,  # not a decision, only a signal for the LLM
                    "reason": LANG["reasons"]["false_start_marker"].format(trigger=trigger),
                    "matched_text": trigger,
                    "trigger_word_index": word_idx,
                    "source": "mechanical",
                })
            idx = pos + len(trigger_norm)
    return windows


def main():
    global LANG, NON_WORD
    code, argv = lang.pop_argv(sys.argv[1:])
    if len(argv) < 2 or len(argv) > 3:
        print("Usage: mechanical_cuts.py <transcript.json> <cuts_mechanical.json> [audio.wav] [--lang CODE]",
              file=sys.stderr)
        sys.exit(1)

    transcript = json.loads(Path(argv[0]).read_text())
    out_file = Path(argv[1])
    audio_path = Path(argv[2]) if len(argv) == 3 else None
    if audio_path and not audio_path.exists():
        print(f"WARN: audio not found {audio_path}, falling back on whisper gaps", file=sys.stderr)
        audio_path = None

    LANG = lang.load(lang.resolve(code, transcript.get("language")))
    NON_WORD = r"[^\w" + LANG["word_chars"] + r"'-]"
    fillers, fillers_debut, false_starts = load_marqueurs(LANG)
    words = flatten_words(transcript)
    total_duration = transcript.get("duration_seconds")

    cuts = []
    cuts.extend(detect_slate(words))
    cuts.extend(detect_fillers(words, fillers, fillers_debut))
    cuts.extend(detect_silences(words, total_duration, audio_path=audio_path))
    cuts.extend(detect_repetitions(words))
    cuts.extend(detect_similar_phrases(transcript.get("segments", [])))
    windows = detect_false_start_windows(words, false_starts)

    # Sort by timecode
    cuts.sort(key=lambda c: c["start"])

    out_file.write_text(json.dumps({
        "cuts": cuts,
        "false_start_windows": windows,
    }, indent=2, ensure_ascii=False))

    print(f"Mechanical cuts: {len(cuts)} | false-start windows: {len(windows)}")


if __name__ == "__main__":
    main()
