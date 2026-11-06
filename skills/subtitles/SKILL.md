---
name: subtitles
description: |
  Fix a Premiere Pro caption/transcript JSON export (an auto transcription full of typos, especially on proper nouns) by transcribing the video again locally with whisper.cpp, then rebuilding a JSON in Premiere's exact format (re-importable as is) with names corrected from a reference script, punctuation and capitals restored, titles of works in quotes, and word timings realigned on the audio by forced alignment. Also fixes the transcript stored inside a Premiere project (.prproj) for voice-over sequences. French and English built in, other languages by adding one JSON file.
  Trigger when the user asks to "fix the captions", "fix the subtitles", "correct the transcript", "redo the subtitle JSON", "the captions are out of sync", "captions have typos", or hands over a Premiere caption/transcript .json.
  Do NOT trigger for: cutting retakes, ums and silences (skill `rough-cut`), pulling the captions of a YouTube video, translating, or making .srt/.vtt files (the format here is Premiere's native JSON).
version: 2.0.0
---

# subtitles: fix Premiere Pro captions

One-time setup: see `INSTALL.md` at the kit root. With the plugin, the setup line is
`bash "${CLAUDE_PLUGIN_ROOT}/install.sh" --data "${CLAUDE_PLUGIN_DATA}"`; with a manual install (the four `skills/`
folders copied side by side into `~/.claude/skills/`), run `bash install.sh` from the kit root.
Scripts live in this skill's `scripts/` folder. This skill points to the other one as `../rough-cut/...`.

## What the skill does

Premiere generates an automatic transcript (a `.json` export) that is often full of typos, above all on
**proper nouns** (a photographer's name turned into two unrelated words). whisper.cpp transcribes much better.
This skill transcribes the video again locally, then rebuilds a `.json` in **Premiere's exact format**
(re-importable as is): names corrected with the help of a reference script, punctuation and capitals put back,
titles of works in quotes. Finally it **realigns the timings on the audio by forced alignment** (whisper's
timestamps drift).

- **YES**: local transcription, name correction, punctuation and case, quotes around titles, **timing realignment on the audio (forced alignment)**, a format identical to Premiere's, ready to re-import.
- **NO**: cutting or rough-cutting the video (that is `rough-cut`), translating, resyncing a caption file that is already right, `.srt`/`.vtt` subtitles (the format here is Premiere's native JSON).

## Expected inputs

1. **The exported video** from Premiere (`.mp4`/`.mov`): it carries the audio to transcribe.
2. **The captions `.json`** exported from Premiere: it gives the target format (keys, `speaker` UUID, language) to clone.
3. **The reference script of the video**, in any readable form (plain text, Markdown, a Google Doc, a Notion page, a pasted text): the **authority for the spelling of proper nouns** (people, works, places, brands). If there is none, ask for it, or correct only the obvious typos and keep whisper's spelling for any uncertain name.

## Language

Typography (spacing around punctuation), accented letters, punctuation sets, quote mark and spelling normalizations live in `languages/<code>.json` (`fr` and `en` are built in), never in the code. The language is chosen by `--lang <code>`, else the language of the Premiere JSON, else the one recorded in the whisper transcript, else `en`. How the files work and how to add a language: [`../rough-cut/references/languages.md`](../rough-cut/references/languages.md) (same mechanism; this skill has its own `languages/` folder).

## Requirements (once per machine)

`whisper-cli` + `ffmpeg` + the model `~/Models/whisper/ggml-large-v3-turbo.bin`. See [`../rough-cut/references/whisper-setup.md`](../rough-cut/references/whisper-setup.md) (shared setup). Check: `which whisper-cli ffmpeg && ls ~/Models/whisper/`.

**Forced alignment** (realigning timings on the audio, step 6b):
```
pip3 install --break-system-packages ctc-forced-aligner torch torchaudio unidecode
```
An ONNX model of about 1.2 GB is downloaded on first run (cache `~/ctc_forced_aligner/`). Check: `python3 -c "import ctc_forced_aligner"`.

---

## Workflow

> The `scripts/...` commands below assume you are **in the skill folder**. The working directory can be reset between two shell calls: either `cd` into the skill folder once, or prefix every script with its absolute path. Work files (audio, transcript, corrections) go in a scratch folder outside any synced folder.

### 1. Sniff the video and the input format

**FIRST: snapshot the original.** Premiere can REWRITE the input `.json` on a re-export, and it is the only sync truth for checking the timings in step 7:

```bash
cp "<Reel.json>" /tmp/subs_original_premiere.json
```

```bash
ffprobe -v error -show_entries format=duration:stream=codec_type,r_frame_rate \
  -of default=noprint_wrappers=1 "<video>"
```
Note the **duration** (the last word must fall inside it) and the **fps**. Then inspect the input Premiere JSON to confirm the format:

```bash
python3 scripts/inspect_format.py "<Reel.json>"
```
It prints the keys (top/segment/word), the `speaker` UUID, the language, the number of segments, and the **current text segment by segment** (= the list of typos to fix). The expected format is documented in [references/premiere-format.md](references/premiere-format.md): read it if the inspection shows unusual keys.

### 2. Transcribe locally (whisper.cpp)

```bash
python3 scripts/extract_audio.py "<video>" /tmp/subs_audio.wav
python3 scripts/transcribe.py /tmp/subs_audio.wav /tmp/subs_transcript.json --model large-v3-turbo --language <code>
```
About 8 s for 3 min on Apple Silicon. The transcript has segments with `text` (punctuated, cased) and timestamped `words`.

### 2b. If whisper did NOT punctuate (continuous delivery): re-punctuate

On fast monologues whisper sometimes returns a **stream with no punctuation and no capitals** (segments break in the middle of a sentence, no `.`/`,`). Clear symptom: `build_subs.py` reports **`eos: 0`**. Without punctuation the captions are unreadable. Quick check: `python3 scripts/words_of.py /tmp/subs_transcript.json 0 1 2 --plain`.

If so, **re-punctuate yourself** (it is an LLM job, not whisper's): rewrite the `text` of each segment with punctuation and sentence capitals, **keeping whisper's words verbatim**: add ONLY punctuation and case; lexical fixes (names, acronyms) stay in `corrections.json`. **Punctuation ALWAYS attached to the word** (`so?`, not `so ?`): a sign preceded by a space becomes an isolated token that the alignment **silently drops** (114 `?`/`!` were once lost at once). `build_subs.py` puts back the language's spacing (for French, a no-break space) by itself. Put the result in a JSON `{index: "punctuated text"}`, then:

```bash
python3 scripts/repunctuate.py --transcript /tmp/subs_transcript.json --punct /tmp/punct.json --output /tmp/subs_transcript_punct.json
```

The script **refuses** if you added, removed or changed a word (it shows the diff): that is what keeps the word-to-timing alignment intact. Take care of the flow across segments: a segment that **continues** a sentence starts lowercase, one that **opens** a sentence takes a capital. Use this punctuated transcript for the rest (`--transcript` in step 6).

Also delete any **end-of-clip hallucination**: on the final silence whisper often invents a line such as a subtitle credit or "Thanks for watching" (the typical lines of each language are listed under `whisper_hallucinations` in `languages/<code>.json`). Delete it with a `seq_rule` N to 0. Another hallucination: **consecutive segments with identical text** whose words have a **near-zero duration** (`start==end`), repetitions invented over a silence ("here we go" x3). Detection: segments i and i+1 with the same text and words of duration 0. Fix: delete them from the transcript before the build (`del segs[i:j]`).

### 3. Read the whisper transcript and the reference script

Print the transcript segment by segment (`text`) and compare it with the input Premiere text (step 1). whisper already fixes a lot, but keeps typos on names. Read the reference script to get the **canonical spelling** of proper nouns and of the titles of works it cites.

### 4. Build `corrections.json` (the intelligent core)

This is where quality is decided. Build a corrections file by comparing what whisper heard with the names of the script. Inspect the **word-by-word split** of the affected segments to write exact rules:

```bash
python3 scripts/words_of.py /tmp/subs_transcript.json 2 9 38   # indexed tokens of the segments to examine
```
The output indexes every word (`9:Smyth  10:Jones`): that is what lets you write exact rules without guessing the tokenization (how many tokens a name takes, hyphens kept, etc.).

Format of `corrections.json` (all keys optional):

```json
{
  "quote_char": "\"",
  "normalize_cotes": true,
  "seq_rules": [
    [["jon","smyth"], ["John","Smith"]],
    [["train","park"],    ["Trent","Parke"]],
    [["arthus","bertrand"], ["Arthus-Bertrand"]]
  ],
  "word_rules": {"macdum": "Magnum", "scholler": "Schoeller"},
  "titles": [
    {"match": ["the","decisive","moment"], "canonical": ["The","Decisive","Moment"]},
    {"match": ["errance"], "canonical": ["Errance"], "sep_comma": true}
  ]
}
```

- **`seq_rules`**: multi-word names, or 1 to N / N to 1. Matching is done on the words **in lowercase, stripped of punctuation**. Use it for any name spanning 2 or more whisper words, or when the number of words changes. **Case: the target words are used VERBATIM**: write the final case you want, position in the sentence included (`["Today","we",...]` if the word opens the sentence, not `["today",...]`). **Same length** source/target: punctuation (internal commas) and timings are kept by index; **different lengths**: timings are redistributed and only the punctuation of the first/last word survives (the internal commas of replaced words are lost: reread those segments in step 7). **Deletion**: an empty target `[["uh"], []]` removes the word (reserve it for real isolated noises that whisper doubled; for a badly transcribed word, correct it rather than delete it, or you lose part of a sentence).
- **`word_rules`**: a one-word name, case forced (lowercase key to exact value).
- **`titles`**: cited works (books, series, titled photographs) get automatic quotes (opening on the first word, closing on the last) plus a `canonical` for the title's correct case. `sep_comma: true` adds a comma after the title (useful when several titles follow each other). Put **works** in quotes, not people's names or brands.
- **`normalize_cotes`**: applies the spelling normalizations of the language file (`normalize_words`), for variants whisper writes inconsistently. Off unless you set it.
- **`french_typography`**: the switch for the language's typographic spacing (the name is historical; it applies to whatever language is in use). Default taken from the language file: for French, a no-break space (U+00A0) before the double punctuation signs and the closing quote mark, and after the opening quote mark; for English, none. Set `false` only if you want attached punctuation. When you re-punctuate in step 2b, the punctuation MUST be attached (`Flop:`); `build_subs.py` puts the spacing back by itself.

### 5. Settle uncertainties WITH the user (never invent)

whisper sometimes produces an ambiguous or unintelligible **non-name** word. **Do not guess silently.** List these points with their timecode and ask the user what is really said, offering a hypothesis if the context or the script suggests one. Distinguish:

- **Correct outright**: proper nouns confirmed by the script; **obvious and certain** typos.
- **Ask first**: ambiguous non-name words, or any correction that changes the **meaning** (for instance whisper "who feels" against the script "without": a reversal of meaning, flag it even if the script settles it).

Do not rewrite spoken style (slang, filler phrases, repetitions): captions must follow the audio.

**What to write in the file while waiting for the answer** (you need not block generation): produce a first version that applies all the safe corrections plus your best hypothesis for the common ambiguous words (and flag them), but **keep whisper's raw spelling for an uncertain NAME that is absent from the script**: never invent a proper noun. Deliver that version with the list of points to validate (timecodes), then **regenerate** after the answer by updating `corrections.json`. That is the normal flow: generate, present with the questions, refine.

### 6. Generate the corrected file

```bash
python3 scripts/build_subs.py \
  --transcript /tmp/subs_transcript.json \
  --original "<Reel.json>" \
  --corrections /tmp/corrections.json \
  --output "<folder>/<name>_corrige.json" [--lang <code>]
```

The script clones the original's format (speaker UUID, language, sorted keys, minified UTF-8), puts punctuation and case back, applies the corrections, adds the quotes, recomputes `eos`, and prints a **validation report**.

**Write `<name>_corrige.json` NEXT TO the original, never overwrite the original export** (it is the user's source). The `_corrige` suffix is a file name the scripts rely on: keep it.

### 6a. Check the 2 recurring traps of `build_subs.py` (every time)

Two bugs seen across many videos, to check after EVERY build:

1. **Decimal numbers doubled.** whisper splits `6.6` into 2 tokens (`6` + `.6`; likewise `1,33`, or `4 AM` into `4` + `AM`); the punctuation re-injection doubles them in the output (`1.4 .4`, `6.6. .6`), and `seq_rules` match badly (the normalization does not strip an internal `./,`). **Detection**: grep the final output for the patterns `\d[.,]?\s+[.,]\d`. **Fix**: surgery on the transcript BEFORE the build: merge the 2 tokens into one (`{'text':'1.4','start':a.start,'end':b.end,...}`; whisper word schema = `text/start/end/confidence`, NOT `duration`), then rebuild.
2. **Isolated end-of-sentence punctuation dropped.** A `?`/`!`/`:` present in the whisper segment's `text` but with no word token of its own disappears (`How did we do it ?` loses its `?`). **Detection**: compare `count('?')` (and `!`, `:`) between the whisper text and the output. **Fix**: post-edit the output JSON: re-append ` ?` (with the language's spacing) to the previous token.

If trap 1 is detected, fix the transcript and rebuild (step 6). If trap 2, patch the output directly.

### 6b. Realign the timings on the audio: forced alignment (ALWAYS)

**whisper's word timings DRIFT** (measured up to **7 s early**, non-linear) with fast, multi-take monologues: whisper **squashes the silences between takes**, so the voice arrives AFTER the caption. Typical complaint: "when the 'Ah' shows up I already hear the next sentence". **DTW (`-dtw`) changes nothing** (same offsets), and a time-warp on sparse anchors **distorts** the zones that were already right. The whisper text is good, only its **timings** are wrong, so replace them with **forced alignment** (wav2vec2 CTC) of the final text on the acoustics.

```bash
python3 scripts/align_forced.py \
  --subs "<folder>/<name>_corrige.json" \
  --audio /tmp/subs_audio.wav \
  --output "<folder>/<name>_aligned.json"
```

The script rereads the word list of the corrected JSON, aligns every word on the audio (**strict 1:1 mapping**: it fails cleanly rather than produce something false), and **replaces `start`/`duration`** while keeping text, schema, speaker and language identical. Measured result: median delta **+0.08 s** against Premiere's own timings (against 7 s early before), take intros aligned on the onset, 0 overlaps. `<name>_aligned.json` is the **deliverable** (not `_corrige.json`).

Bonus: forced alignment makes any manual compression of words "stretched" by whisper over silences unnecessary (take intros like a repeated greeting): their timings are recomputed anyway.

### 7. Reread and validate

Always **reread the final text segment by segment** (not only the report):

```bash
python3 scripts/words_of.py "<...>_aligned.json" --all
```
Check: names right, punctuation that helps follow the sentences, capitals at sentence starts, titles in quotes **balanced** (even count), last word <= video duration, schema identical to the original (the report says so).

**Also check the TIMING before delivering** (the text can be perfect and the sync wrong): the snapshot `/tmp/subs_original_premiere.json` (step 1) is the sync truth. Take 5 or 6 caption starts from Premiere spread over the video (above all the **restarts after a long silence**, such as take intros), find the same words in `_aligned.json` and compare the `start` values: |delta| must stay <= about 0.5 s. If a zone drifts by several seconds, the forced alignment has a problem: do not deliver.

Show the user a recap of the corrections plus the uncertain points settled, and remind them to re-import **`<name>_aligned.json`** into Premiere.

## Route B: fix the sequence transcript embedded in the .prproj

For voice-over sequences: the user transcribed the sequence in Premiere, and there is no JSON export and no exported video. Premiere stays the base (it holds every timecode and keeps repetitions, doubled words and regional turns of phrase); whisper is used only to settle the wrong words.

1. `scripts/prproj_transcript_json.py PROJECT.prproj --liste`, then
   `... PROJECT.prproj origin.json [--sequence "name"]`: the SEQUENCE transcript (sequence timecodes) in Premiere's export format. Work on a copy of the `.prproj`, never on the user's own.
2. `scripts/second_avis_whisper.py PROJECT.prproj origin.json --voix "Track" --out FOLDER --prompt "A photographer comments on a shoot in <city>."`: whisper segment by segment (about 3 s per segment). `--voix` is a pattern of the voice files' names. **Never run whisper on the whole voice file**: it hallucinated a credit line in a loop over 20 min of audio.
3. Read ALL of `compare.txt`, rewrite every segment in `corrections.json` (the full text of the segment). Arbitration rules learned:
   - a word added by whisper in mid-sentence: credible if Premiere has a PAUSE (an item with empty text >= 0.3 s) at that spot, since Premiere hides there the words it does not recognize (swear words, unusual words); without a pause it is an invention (a whole phrase in 0.2 s);
   - words added at the edge of an excerpt belong to the neighboring segment: ignore them. whisper drops repetitions and small grammatical words; do not follow it;
   - remaining doubt: `--sondes` (window +-1.5 s, 3 decodings); homophones: settle by meaning; the image of the clip at the same timecode if needed;
   - keep a glossary of the speaker's recurring references (names, titles, the speaker's own name, slang) in the prompt: Premiere and whisper both mangle them;
   - spelling yes (hyphenated imperatives, typography), spoken style no.
4. `scripts/appliquer_corrections.py origin.json corrections.json fixed.json --voix PROJECT.prproj Track`: timecodes kept (an added word is placed in the neighboring pause). The delivered file contains NO pause (empty-text item): Premiere rereads them as words, hence "..." captions and sentences starting at the beginning of the blank left between two reels (up to 75 s too early). Pauses are removed, segment bounds = first and last real word, words trimmed at the edge of their voice clip (`--voix`; exit code 1 if a word falls outside every clip). Afterwards check: the list of Premiere words removed or merged (no accident), increasing timecodes, 0 empty items, 0 words and 0 segments outside a voice clip.
   Why: in the `.prproj` a real pause has type 3 (field f6); an empty item imported from JSON becomes a WORD with no text. On re-import Premiere creates the typed pauses itself in the gaps between words.
5. Deliver `transcription-corrigee.json` in the project's doc folder plus a copy with the `.prtranscript` extension (in case the import dialog filters the extension), with 3 to 5 doubtful points and their sequence timecode. Import: Text panel > Transcript > ... > Import, with the sequence active.
6. **Check the re-import in the project, not on trust**: `scripts/verifier_import.py PROJECT.prproj --autour <s>` on the latest file of `Adobe Premiere Pro Auto-Save/` (Premiere writes one about every 6 min, only if the project changed). Premiere shows nothing when an import did not take: one re-import once left the project with the previous version byte for byte (hundreds of untyped empty items), hence captions still sitting in the blanks. Put defective versions in a subfolder so only one file is left to choose. What remains is Premiere's doing, not the data: the caption before a blank is often held about 2 s, so the last one of a reel can overrun by 0.2 to 1.6 s into the blank.

---

## Why these choices (to pass on, not to apply blindly)

- **Punctuation and case live INSIDE `word.text`** (Premiere's native format: "go.", "Coffee"). `transcribe.py` strips them (bare lowercase words). Without re-injection from the whisper source text, captions have no commas or capitals and are hard to read. `build_subs.py` realigns every timestamped word on the segment's punctuated text.
- **Timings = forced alignment, NOT raw whisper** (step 6b). whisper gives the right TEXT but its word timestamps drift (up to 7 s early, non-linear) because it squashes silences between takes: the caption goes before the voice. So the final text is re-fitted on the acoustics with wav2vec2 CTC (`align_forced.py`). NEVER deliver on raw whisper timings for this kind of content (fast monologue, multiple takes). If a word still lags in a karaoke-style display, that is the residual of the forced alignment (sub-second): say so.
- **Ask rather than invent**: a wrong name in a public caption is worse than a question. The script is the authority for names; for the rest, the doubt is settled with the user.

## Scripts

| Script | Role |
|---|---|
| `scripts/extract_audio.py <video> <out.wav>` | 16 kHz mono audio (whisper-ready) |
| `scripts/transcribe.py <wav> <out.json> --model large-v3-turbo --language <code>` | whisper.cpp transcription to timestamped words |
| `scripts/repunctuate.py --transcript --punct --output` | Re-injects punctuation (step 2b) when whisper returned a stream with no `.,`; validates the words |
| `scripts/inspect_format.py <premiere.json>` | Format + speaker + current text (typos) |
| `scripts/words_of.py <json> [ids... \| --all]` | Word-by-word split of a whisper transcript or a Premiere JSON |
| `scripts/build_subs.py --transcript --original --corrections --output [--lang]` | Rebuilds the corrected Premiere JSON + report |
| `scripts/align_forced.py --subs --audio --output` | **(6b) Realigns the timings on the audio** by wav2vec2 forced alignment: fixes whisper's drift. Produces the `_aligned.json` deliverable |
| `scripts/prproj_transcript_json.py PROJECT.prproj [OUT.json] [--liste] [--sequence]` | (route B) Transcript embedded in the .prproj to a Premiere export JSON |
| `scripts/second_avis_whisper.py PROJECT.prproj origin.json --voix --out [--prompt] [--sondes]` | (route B) whisper segment by segment + `compare.txt`; targeted probes |
| `scripts/verifier_import.py PROJECT.prproj [--autour s]` | (route B) What Premiere really kept: typed pauses / untyped empties, gaps between captions |
| `scripts/appliquer_corrections.py origin.json corrections.json out.json --voix P.prproj Track` | (route B) Corrected text per segment to re-importable JSON, timecodes kept, no pauses, words inside the voice clips |
