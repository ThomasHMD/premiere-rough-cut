---
name: rough-cut
description: |
  Automatic rough cut of talking-head footage (monologues, spoken videos) for Premiere Pro. Produces a Final Cut Pro 7 XML (XMEML) whose timeline already has the retakes, false starts, stumbles, filler words and long silences removed. The original clip is never touched. Local transcription (Premiere's own transcript read from the .prproj, plus whisper.cpp as a second opinion), take selection done by Claude in context, three-level decisions (cut / flag / ignore), red markers on doubtful spots. French and English built in, other languages by adding one JSON file.
  Trigger when the user asks to "rough cut", "cut the retakes", "remove ums", "remove the filler words", "clean up this clip", "cut the silences", "prepare a first edit", "first pass of the edit", or hands over a talking-head video (.mp4, .mov, .mkv) to prepare for Premiere.
  Do NOT trigger for: fixing captions (skill `subtitles`), placing graphics or lower thirds (skill `overlays`), building an animation (skill `motion-design`).
version: 2.0.0
requires_secrets: false
---

# rough-cut: automatic rough cut for Premiere Pro

One-time setup: see `INSTALL.md` at the kit root. With the plugin, the setup line is
`bash "${CLAUDE_PLUGIN_ROOT}/install.sh" --data "${CLAUDE_PLUGIN_DATA}"`; with a manual install (the four `skills/`
folders copied side by side into `~/.claude/skills/`), run `bash install.sh` from the kit root.
Scripts live in this skill's `scripts/` folder.

## Scope

- **YES**: a Final Cut Pro 7 XML (XMEML, `.xml`) whose timeline already has the retakes, false starts, stumbles, filler words and long silences removed; a markdown report; red markers on what is left to decide.
- **NO**: modifying the clip, transcoding, exporting the video, color grading, mixing, choosing between two takes beyond obvious rephrasings (that is the editor's call).

## Core rule: the original clip is NEVER modified

The skill only writes next to the clip:
- `<clip>_Derush_v1.xml`: the edit to import (FCP7 / XMEML);
- `<clip>_Derush_v1.report.md`, `<clip>_Derush_v1.log.txt`;
- `<clip>_Derush_v1_work/`: the work folder, kept (transcripts, intermediate cuts).

The XML points to the clip by absolute path (`file://localhost/...`): Premiere only references it. A new pass creates `v2`, `v3`... without overwriting anything.

## What the user does (3 steps)

1. In Premiere: import the clip, run the transcription (Text panel > Transcribe), **save the project**. The transcript is then INSIDE the `.prproj`: never ask the user to export it.
2. Give Claude the path of the clip, and the reference script of the video if there is one (plain text, Markdown, a Google Doc, a Notion page, anything readable). The script only serves to tell whether a repetition is deliberate. Without a script, the pass still works; deliberate repetitions then become flags instead of cuts.
3. Import the `.xml` (`File > Import`). A `Derush_vN` sequence appears, **already edited**: the cuts are absent from the timeline (clips end to end, nothing to close up), and doubts stay as active clips with a red marker.

Ask nothing else: language, clip type and options are inferred (see below), and a question is only worth asking when the clip type is truly ambiguous.

## Language

Everything language-specific (filler words, false-start phrases, slate patterns, orphan connectors, openers to cut, whisper hallucinations, the reason texts of the markers) lives in `languages/<code>.json`, never in the code. French (`fr`) and English (`en`) are built in. The language is chosen by `--lang <code>`, else the language recorded in the transcript, else `en`. Details and how to add a language: [`references/languages.md`](references/languages.md).

## Pipeline v2: take selection (the normal route)

Detecting defects alone (v1, below) tops out around 57% recall because
**whisper silently deduplicates repeated takes**: its anti-loop decoder treats a sentence repeated word for word as a hallucination and transcribes it once. This cannot be fixed by configuration. Premiere's transcript keeps every take, word for word, and its word starts do not drift after long silences (whisper's do). Hence:

| Step | Tool | Role |
|---|---|---|
| 1 | `extract_prproj_transcript.py project.prproj words_premiere.json [--rush CLIP.MOV]` | **`.prproj` to `words_premiere.json`** (PRIMARY source). Exit code 2 if the project has no transcript: ask the user to run it and save the project. Fallback: `parse_premiere_transcript.py` on a manual JSON export |
| 2 | `extract_audio.py` + `transcribe.py` | whisper = SECOND OPINION (cross-check the text, never the boundaries) |
| 2b | `calibrate_premiere_times.py` | **realigns Premiere's transcript to the audio**. Run it on EVERY rough cut, right after the audio extraction (it leaves everything alone when the transcript is on time). Measures the offset by cross-correlation, window by window; a 1.8 s drift at the end of a 21 min clip has been seen. Symptom if forgotten: `silence_cuts.py` reports dozens of "suspicious noise" |
| 3 | **Claude in context** | semantic analysis: spot retakes, false starts and stumbles by comparing Premiere's transcript with the script and with whisper. Rules below |
| 4 | `silence_cuts.py` | silences >= 1.0 s between Premiere words, word ends realigned to the sound level, enumeration guard (short pauses between two short blocks = deliberate rhythm), noisy zone: flag or cut (see below). Defaults calibrated against finished edits: do not change them without re-measuring (see `references/lessons.md`, "Measuring") |
| 5 | `apply_takes.py <work>` | the takes decided in step 3 are written to `takes.json` (word indices; hand-set boundaries or cuts in seconds are optional). The script puts boundaries in energy valleys, merges with the silences, melts the mute fragments left between two cuts, flags an isolated sound of under 0.25 s at a clip edge, then **gives every join its air**, writing `cuts_final.json`. **Air at the join**: 0.27 s after the last speech of the previous clip plus 0.28 s before the first speech of the next one, 0.55 s in all, a shortfall on one side being taken from the other (a retake almost never has a breath before it). Earlier, take cuts left only 0.22 s and the rough cut was rejected at the very first join ("you cut a sentence that is not finished"). It is measured on a speech mask (15% of the p95, islands under 0.07 s discarded, gaps under 0.09 s filled in), otherwise a tongue click or a consonant closure makes it look like there is no room. A `retake` or `faux_depart` with no 0.25 s of silence available is not cut; a `begaiement` or `correction` is removed mid-sentence and needs no air. A hand-set boundary is law. `protect` (keep a silence) only if the user asks |
| 6 | `build_premiere_xml.py` | XMEML. Option `meta["audio_file"]`: point the audio to a full-length processed WAV (see Known limits). Several clips: one XML per clip, then `merge_xml.py output.xml "name" a.xml b.xml` = a single sequence, end to end |
| 6b | the edit, transcribed again | end-to-end check: concatenate the kept intervals of `audio.wav`, run whisper on it, and READ the text with the cut points. Catches what the other checks miss: silences left in the edit (an 8 s clip for 3 words), clipped words, a surviving failed take |
| 7 | `qc_repeat_scan.py` | deterministic check: exit code 2 if a repeated 5-gram within 30 s survives in the edit, or if two words that follow a pause or a cut were already said less than 8 s of edit earlier (a take repeated with a variant). Every hit is checked against the script and by ear (`hear.py`): surviving retake (keep the LAST one) OR deliberate rhetoric (anaphora, enumerations) |
| 7b | `montage_qc.py <work>` | the edit's audio is transcribed and read clip by clip, Premiere words (P) against whisper (W): exit code 2 on a blank > 1.6 s, a fragment < 1 s, or a **dry join** (less than `--min-air`, 0.30 s by default, of blank between the last speech of a clip and the first of the next, stutters and corrections excepted); it also reports, without blocking, a short word of more than 0.45 s at the start of a clip (a doubled word that Premiere writes once and whisper deduplicates: "The... the book"). A doubtful edge is checked with `hear.py audio.wav 12.3-14.0 ...` (whisper on isolated slices) |
| 8 | `report_v2.py` | report: duration of the EDIT and of the clip, takes, doubts; `--notes` for "kept on purpose" and passages touching the script's sensitive points |

### Step 3, the decision rules

Hard rules:
- repeated text: keep the **LAST** take (even when it is less clean than an earlier one);
- stumble: keep the **longest consecutive piece**;
- doubt: `flag`, never `disable`. Under-cutting always beats over-cutting: adding a cut is easy, recovering a missing passage is hell.
- cut boundaries snap to Premiere words, with about 0.15 s of air before the first kept word.

Rules learned from real edits:
- **Any island of under 2 s squeezed between two take cuts gets listened to** (`hear.py`). It is almost always a false start. Never judge it from Premiere's text: a breath can carry words in Premiere, and a whisper hallucination of the "Thanks for watching" kind means there are no words at all.
- **A silence with noise that is not a sentence of the script** (an aside, a "here we go", handling the camera) is cut, not flagged.
- **A filler opener at the start of a sentence** (the "openers" list of the language file, for example "So," or "Well,") is cut.
- **Verbatim stutter** inside a sentence ("It's it's") is disabled. But a name repeated on both sides of a full stop ("less documented than Nikon. Nikon has plenty of docs") is not a stutter: Premiere may have written it as a double. `hear.py` the slice before any single-word cut.
- **Orphan connector** (an isolated "And / So / But") right before a cut silence is included in the cut. The same goes for **any lone false-start word** squeezed between a cut and a pause followed by another attack.
- **A nonsense word in Premiere's transcript with no whisper equivalent** inside a redundant aside is a stumble: at least flag it.
- **Filler phrase carrying no information** that repeats the next sentence: flag only (it is editorial).
- **A "retake" can be the end of the previous sentence**, badly dated by Premiere (a word 5 s long). The whisper text of the edit shows it.
- **Premiere sometimes splits one sentence in two**: a two-word "false start" can be the start of the next sentence.
- **Premiere misses small mumbled words**: cutting a repeated sentence can leave an orphan lead-in. `hear.py` the slice first; set the boundary by hand (6th element of an entry in `takes.json`).
- **A single doubled word** ("the the"): the boundary can eat the word before it, because Premiere dates both in the same breath. Listen to the join (`ffmpeg atrim` of the two kept pieces, then `hear.py`).
- **A seam between two clips**: the end of clip 1 and the start of clip 2 are listened to together. A sentence begun at the end of clip 1 and repeated at the start of clip 2 is cut from its first word.
- **Instructions spoken to the camera for the editor** ("this is for you, put some graphics here") are cut as instructions, and listed in the report, because they say where to illustrate.
- **After cutting a take, listen to the attack of the kept take** (a first word can get eaten when Premiere has two of them).

### The Premiere transcript is inside the .prproj

The `.prproj` is gzipped XML containing a block
`<ExternallyProvidedTranscriptDocument><TranscriptData Encoding="base64">`, whose payload is a FlatBuffers buffer. `extract_prproj_transcript.py` decodes it:

    Segment -> f0 i64 start_ticks, f3 vector<Word>, f4 string language
    Word    -> f0 i64 start_ticks, f1 i64 duration_ticks, f2 string text, f3 f32 confidence
    Premiere ticks = 254016000000 per second

Items with **empty text** are the PAUSES marked by Premiere (their duration covers the whole silence). The script drops them; otherwise every gap between words is 0 and `silence_cuts.py` finds nothing (symptom: "gaps > 1s: 0" and words 39 s long).

**Several clips in one project**: the `.prproj` holds one transcript PER clip. `--rush NAME.MOV` picks the one that fits the clip's duration (without it, the longest, with a warning). It compares the start of the last word, with a drift margin of 0.3% of the duration. Check that the word count differs from one clip to the other. One work folder per clip, then `merge_xml.py`.

**Two traps** in this transcript:
1. **It can drift** relative to the file: step 2b. Cuts are in FILE time (that is what the XML reads), so the words get corrected, never the other way round.
2. **Word durations can swallow the silence that follows**: the silence no longer exists between words and is no longer cut. `silence_cuts.py` brings those words back to their real end (`trim_overflow`). Never trust a Premiere word end; only the starts are reliable.

More traps (words dated inside a silence, mute fragments, tiny islands): `references/lessons.md`.

Take-cut boundaries: on the nearest **energy valley** of the word start, with the air budget of step 5 around the join. Describe cuts by **word indices**, not seconds: they survive a realignment.

### Read voice-over, no Premiere transcript

For a voice-over recorded as a WAV (no `.prproj`) and read from a script, transcribe **chunk by chunk**, which sidesteps whisper's deduplication.

| Step | Tool | Role |
|---|---|---|
| 1 | `transcribe_chunks.py <audio16k.wav> <work>/words_premiere.json --chunks <work>/chunks.json` | splits the audio at every pause (0.35 s or more of non-speech, measured on energy) and transcribes each chunk ALONE (`whisper-server`, `-mc 0`, `-dtw` + `-nfa` for real word times): a take and its retake fall into two chunks and both get transcribed. Chunk edges are set on the energy. Output in the format of `words_premiere.json` (plus `chunk`) |
| 2 | `align_script.py <work> <script.md>` | position in the script of every spoken word (local window around the current reading, catch-up by similarity for misheard words and for the word that opens a take). `dossier.txt`: one chunk per line, "retake" in the margin, passages of the script never read |
| 3 | `propose_takes.py <work>` | proposed `takes.json`: a script word said several times is kept only at its last take (whole chunk or end of chunk), short off-script chunks cut (hallucinations such as "Thanks for watching", breaths). Then **a read-through in context** of the whole file, decisions in `decisions.json` (`couper`, `couper_depuis`, `garder`, by chunk number), re-read at every rerun |
| 4 | `silence_cuts.py`, `apply_takes.py`, `qc_repeat_scan.py`, `montage_qc.py` | unchanged |
| 5 | `ecarts_script.py <work> <script.md>` | what the edit does differently from the script (skipped sentences, rewordings of 3 words or more): the list for the user to settle |
| 6 | `build_premiere_xml.py` | a `meta.json` without `width` gives an audio-only sequence (empty video track) pointing at the raw 48 kHz WAV |

Pitfalls (the proposal alone is not enough, always read it):
- a **reworded** retake no longer matches the script: the aligner then keeps the take that conforms and marks the right one as off-script. Keep the last complete take, even if it is further from the script;
- a chunk cut whole because its end is repeated can take away a start that is not (`couper_depuis`);
- a retake of one or two words is not seen (anti-coincidence threshold): a stray "Um" left in front of a sentence, two takes of the same name both kept. `ecarts_script.py` brings them out (words doubled in the sentence).

### A whole part in one XML, redone sentences put back in place

One XML per part, a minute of blank between modules. The faulty sentences are redone in **a single file** (a pause before each sentence, retakes allowed), transcribed by chunks like a clip (`transcribe_chunks.py`, `silence_cuts.py`, and a `meta.json`).

| Step | Tool | Role |
|---|---|---|
| 1 | `plan.json` (see `assemble_xml.py`) | modules in order, the clips of each module (no blank between two clips of a module), and for each retake: the clip chunks it replaces (`remplace`, end to end, already-cut chunks included) and the chunks kept from the source (last complete take) |
| 2 | `assemble_xml.py <plan.json> <output.xml>` | one sequence: clip on A1, retakes on A2, a marker per module and per retake. Air of the retakes taken from the pauses (never a digital blank). Level of each retake brought to that of the neighboring clip ("Audio Levels" filter). Joins of the original rough cut redone from the energy (`aerer`): a clip edge inside speech moves to the dip, air reopened up to 0.55 s when under 0.30 s. An **island** (a bit of a word of the removed take left at a clip edge) is reported as "TO LISTEN" with a proposed edge, never cut automatically; after `hear.py`, the fix goes into the plan: `"bornes": [{"rush", "de", "a", "pourquoi"}]`. `--sans-aerer`, `--brut` | <!-- fr-ok -->
| 3 | `qc_assemblage.py <xml> <plan.json> <folder> --avant` | on the delivered XML: sound redone clip by clip, air and edges at every join, level of the retakes, retranscription of each module against its script (new deviations compared with the original rough cuts, script positions said twice). Exit code 2 on an alert |
| 4 | `rendre_voix.py <xml> <output folder>` | **after the user's approval**: one WAV per module, the very sound of the sequence (A1 and A2 clips with their level), 2.8 s of silence at the head (first word around 3 s), 48 kHz mono 24-bit; nothing is rewritten if identical |

`raccords.py`: the air-at-the-join measure (speech mask, continuous blank), shared by `montage_qc.py` and `qc_assemblage.py`. Premiere reads the "Audio Levels" filter of the XML (0 dB = 0.17783 in the `.prproj`, which stores volume with 15 dB of headroom). More traps: a silence cut that starts on a word end dated too early by whisper eats the end of the sentence; doubled script positions can be mere turns of phrase said twice: read the text before reporting them.

The v1 pipeline (below) remains the fallback when there is **no** Premiere transcript (warn that word-for-word retakes will probably be missed).

## Machine requirements

Checked at startup; if something is missing, point to `INSTALL.md` (`references/whisper-setup.md` for whisper alone).

```bash
brew install whisper-cpp ffmpeg
mkdir -p ~/Models/whisper
curl -L -o ~/Models/whisper/ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
```

Python 3 with numpy (nothing else). No API key, no account, nothing leaves the machine after the model download.

## Pipeline v1 (fallback, 8 stages)

Run by `scripts/derush.py`. Each stage writes into `<clip>_Derush_vN_work/`, next to the clip, never deleted (resume and inspection stay possible).

| # | Script | Role |
|---|---|---|
| 1 | `derush.py` (entry point) | ffprobe metadata, version number |
| 2 | `extract_audio.py` | ffmpeg to `audio.wav` 16 kHz mono |
| 3 | `transcribe.py` | whisper.cpp to `transcript.json` |
| 4 | `mechanical_cuts.py` | word lists and patterns of the language file to `cuts_mechanical.json` |
| 5 | semantic analysis (Claude) | to `cuts_semantic.json` (see below) |
| 6 | `merge_cuts.py` | merge, snap to words, scores to `cuts_final.json` |
| 7 | `build_premiere_xml.py` | to `.xml` (XMEML / FCP7) |
| 8 | `build_report.py` | to `.report.md` |

### Stage 5: semantic analysis

The script writes `prompt_semantic.txt` and stops. That is the normal route: **Claude, running the skill, then does the following.**

1. read `prompt_semantic.txt` in full;
2. analyze the transcript following the rules in the prompt;
3. write the JSON into `cuts_semantic.json` (path given in the prompt);
4. resume: `derush.py <clip> --resume-from=6 --work-dir=<work>`.

If `cuts_semantic.json` already exists, the stage is skipped.

## Three-level decisions (the skill's philosophy)

Every proposed cut has a confidence between 0 and 1.

- **`disable`**: the passage is **removed from the timeline**, not deactivated. `build_spine_clips()` builds the sequence by subtraction: only the kept intervals remain, end to end, and the sequence duration is the sum of the kept intervals. The equivalent of a "ripple delete" already applied. Thresholds: **>= 0.85** for a mechanical cut, **>= 0.92** for a semantic cut (an LLM often overshoots its boundaries).
- **`flag` (0.6 to 0.85)**: no cut. The passage stays as an **active clip**, with a red sequence marker ("DOUBT <type> (conf X): reason") at the right place. The user decides.
- **`ignore` (< 0.6)**: nothing, to avoid drowning the timeline.

> Never invert these semantics. Delivering deactivated, grayed-out clips to delete by hand moves the work onto the user instead of removing it: the promise is a directly usable sequence.

## Cut types

- **`filler`**: filler words ("um", "uh"...) and sentence-start fillers, from the language file (editable: `languages/<code>.json`, see `references/languages.md`).
- **`silence`**: depends on the **clip type**. **Desk, talking-head** shoot (the speaker reads notes between sentences): silences >= 1.5 s ARE CUT (`silence_cuts.py`, sound-level check). **Field** clips (outing, walk, demonstration): the silence is often a shot to keep, flag only. When unsure about the type: ask.
- **`repetition`**: N consecutive words (2 to 6) repeated within 2 s. Short repetitions (2 or 3 words: "there is", "no no") are normal speech and kept; automatic cut only from 6 very similar words.
- **`false_start`**: "wait, let me start again", "no sorry, I'll redo that" (phrases from the language file).
- **`semantic_restart`**: a sentence rephrased 2 or 3 times with no explicit marker (semantic analysis only).
- **Slate** ("1, 2, 1, 2, rolling") within the first 15 seconds: cut outright.

## Invocation

```bash
python3 scripts/derush.py /absolute/path/clip.mp4 [--lang en]          # full v1
python3 scripts/derush.py /absolute/path/clip.mp4 --resume-from=6
python3 scripts/derush.py /absolute/path/clip.mp4 --debug
```

In v2, chain the scripts of the table in order, inside `<clip>_Derush_vN_work/`.

## Before handing back

- the XML exists and is larger than 1 KB;
- `qc_repeat_scan.py` and `montage_qc.py` pass (or every hit is explained);
- show the report summary: cuts removed, doubts, edit duration against clip duration;
- remind the user to import into Premiere and check the red markers. Passages touching the script's sensitive points (legal wording, figures that differ from the script) go in the report, not in the cuts.

## Reference files

- `references/lessons.md`: what was learned on real edits (calibrations, XMEML traps, how to measure). Read before a first rough cut.
- `references/languages.md`: how `--lang` and `languages/<code>.json` work, how to add a language.
- `references/verbal-markers-fr.md`: readable summary of the French filler and false-start markers.
- `references/xmeml-schema.md`: XMEML (FCP7) structure, tags used, why not FCPXML.
- `references/whisper-setup.md`: whisper.cpp and model installation.

## Known limits

- Single speaker, talking-head. Not tested on two-person dialogue.
- whisper model `large-v3-turbo` recommended; with a smaller model, confidence drops: raise the flag thresholds.
- **Premiere does not import modern FCPXML** (Final Cut Pro X): only the old XMEML (FCP7, `.xml`) passes. Do not retry FCPXML.
- A cut moves picture and sound together (no J-cut or L-cut): this is a rough cut, not a fine edit.
- **XMEML import carries NO effects**: audio effects added to the track (Enhance Speech, EQ...) are lost, and Enhance Speech re-analyzes every cut clip separately (worse dynamics than over the whole track). Workaround: export the processed audio ONCE at full length as a WAV (same t=0 as the clip); `meta["audio_file"]` makes the XML's audio clips point to that WAV, effects preserved and dynamics computed before cutting. Offer it each time. Otherwise: reapply the effect to the new sequence's track, or paste the cut clips into the user's own sequence (track effects survive there).
- The import creates a duplicate of the media item in the project (linked by path): normal, delete it after the import.
