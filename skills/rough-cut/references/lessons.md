# Rough-cut lessons (learned on real edits)

All of this was measured by comparing the skill's rough cuts to the edits a human editor finished, on a few
dozen "desk, talking-head" clips of 10 to 30 minutes. The scripts' default settings come from it: do not
change them without measuring again (see "Measuring" at the end).

## Decision semantics (hard rule)

- `disable` (>= 0.85 mechanical, >= 0.92 semantic): passage **removed from the timeline**, not grayed out.
- `flag` (0.6 to 0.85): clip **kept active**, red marker.
- `ignore` (< 0.6): nothing.

A version that delivered the cuts as deactivated clips (to delete by hand) was judged unusable: it moves the
work instead of removing it. An active flag is reassuring: when the skill doubts, the content stays and the
marker catches the eye. Cut what you are sure of; leave active only what you doubt.

## What the mechanical stage can and cannot do

Measured ceiling of the mechanical stage alone: **about 20% of the editor's cuts, for 5% false positives**.
The false positive is the critical metric (content the editor kept and the skill cut).

1. **Silences: the rule depends on the clip type.** Desk, talking-head (the speaker reads notes between two sentences): silences >= 1.5 s are cut ("nothing is said, there is just computer noise"). Field clips (outing, review on location): the silence is often a shot, flag only. When unsure about the type, ask.
2. **Short repetitions (2 or 3 words) are normal speech** ("there is", "it's", "no no"): kept. Automatic cut only from 6 very similar words.
3. **Always snap cuts to word boundaries**, otherwise "photographer" becomes "photogra".
4. **Take slate** ("1, 2, 1, 2, rolling") within the first 15 seconds: cut outright.
5. Similar-phrase detection (Jaccard >= 0.55 over 4 to 6 segments) is the only mechanical filter worth having beyond fillers and the slate.

## The real rough cut is semantic

With an LLM at the semantic stage: **57% of the editor's cuts, 8.6% false positives** (against 20% without).
Most of the work: rephrasings (the dominant pattern), false starts ("No...", "Wait..."), notes to the editor
spoken aloud, whole digressions.

- An LLM **overshoots its boundaries** (it says 22-71 s when the right cut is 37-60): higher threshold for semantic cuts (0.92) and snapping to words.
- Filter out cuts beyond the clip (`end <= duration + 0.5`): an LLM can invent times past the end.
- The semantic stage is done by Claude in context, reading the transcript and the script. If the stage ever goes through an external "thinking" model behind a service, disable its thinking budget or the answer comes back truncated.

## Why v2 (take selection, not defect detection)

- **whisper deduplicates repeated takes** (anti-repetition decoder): a sentence said twice 3 s apart appears once. A rough cut on whisper alone CANNOT see retakes: that is the root cause of the 57% ceiling. Same for verbatim stumbles and false starts.
- **Premiere's transcript** keeps every take, word for word, and its word starts stay right after a silence (whisper's drift after a long one). Premiere = primary source, whisper = second opinion, the script = referee of a deliberate repetition.
- Selection rules: repeated text, keep the LAST take; stumble, keep the longest consecutive piece; under-cut rather than over-cut (delivering 16 min out of 20 beats 11: re-cutting is easy, re-spacing is hell).
- Result on a 20 min clip: 0 false positives, the editor then removed only about 60 s more, in 20 min instead of 40 min of manual rough cutting (a factor 2 gain). After the silence calibration below, only 25 s more on the next clip.
- The aim is to push automation as far as it goes, toward a rough cut that needs no manual pass: no improvement is set aside because the volume is low.

## Silence calibration (`silence_cuts.py`)

On a finished edit, what the editor still removed on top: paddings that were too fat around cuts, pauses just
under the threshold, word tails, orphan connectors, and a little editorial. Settings kept: `min_gap` 1.0 s,
pads 0.25 / 0.20 s, minimum cut 0.45 s, word ends realigned to the sound level (Premiere word ends overshoot
by 0.3 to 0.6 s), enumeration guard (a pause under 1.5 s between TWO blocks under 2.5 s = comic or deliberate
rhythm, kept; the guard needs two short blocks, `--enum-any` restores the looser rule).

- Shrinking the pads further does not get closer to the human edit: what the editor removes on top is not at the edge of the silences. Small pauses of 0.3 to 0.9 s: the editor keeps most of them; do not lower `min_gap`.
- Pauses of 0.7 to 0.9 s that were cut by the editor and pauses of the same size that were kept both exist. Tested on one clip, `--min-gap 0.9` gained one correct cut and 0 wrong; 0.8 cut 2 pauses the editor keeps. One sample is not enough: default 1.0 unchanged.
- Pauses of 0.8 to 1.4 s of true calm that Premiere counts under 1 s: the editor cut some and kept as many of the same size. No rule: it is rhythm.
- A silence that the script marks as deliberate (a beat after the hook) was cut anyway by the editor. Only protect a silence on request; at best, a flag.

## Premiere transcript traps

- **Drift**: on one clip, words arrived later and later (0 s at the start, 1.8 s at the end, slope 0.14%). Fixed by `calibrate_premiere_times.py` (word to voice-activity cross-correlation, 40 s windows, median over 5). Without drift it touches nothing. A symptom of an uncorrected drift: dozens of "suspicious noise" silences, then a minute and a half of blanks left in the edit.
- **Overflowing words**: words whose duration contains the whole following silence (up to 12 s). Fixed in `silence_cuts.py` (`trim_overflow`, speech level on the head of the words, step back to the real attack of the next word).
- **Words dated inside a silence**: Premiere sometimes puts a word in the middle of a silence although it was said before; a mute 0.3 s fragment is left between two cuts. Handled by `apply_takes.py` (mute fragments melted), reported by `montage_qc.py`. The same happens when a removed take follows a cut silence (the attack of the cut word is left).
- **Blanks of 1.01 s between two cut silences** (Premiere words dated inside the blank): the mute-fragment rule once stopped at 1 s. `apply_takes.py` now removes every island where nothing exceeds the silence threshold, whatever its length.
- **Missed small words** ("There" before a sentence): the cut starts too late and leaves a stray sound. Seen on the W line of `montage_qc.py`; boundary fixed by hand after `hear.py`.
- **Isolated sound under 0.25 s at a clip edge**: removed if it is only noise (peak < 0.2 x p95), otherwise flagged. Energy cannot tell a stray "a" from a deliberate "NEVER." said after a silence (0.52 x p95 against 0.37).
- **Blank at a clip edge** left by a take cut placed on a badly dated word: `apply_takes.py` realigns every clip edge to the real sound (0.25 s of air after the last speech, 0.20 s before the first), except after the last word of the clip, where it keeps the air.
- **Stray punctuation or text in an island proves nothing**: Premiere wrote "the camera." and "on the X." for islands that, listened to alone, were a breath (whisper hallucinates a "Thanks for watching" line, a sign there are no words at all) and a false start. An island is judged by `hear.py`, never by Premiere's text.
- **Repeated words from one clip to the next in the W lines of `montage_qc`** ("Second | Second", "I will | will") are often a slicing artifact: check with `hear.py` on the clip before concluding a take survived.
- **Wrong transcript picked with several clips in a project**: a transcript that drifted by 2.1 s had its last words starting after the end of the file, and the script picked the other clip's transcript without an error. Fixed by comparing the start of the last word (not its end, which can swallow silence) with a drift margin of 0.3% of the duration. Check that the word counts differ from one clip to the other.

## Take-selection lessons (from comparing with the editors' finished sequences)

- **Takes repeated with a variant** ("I disassembled it because it was in assembly, | I disassembled and decompiled it"; "by computing the gap in the colors, | by computing the color gap"): all missed by the 5-gram check. The editor keeps the last one every time. Hence the second check in `qc_repeat_scan.py`: two words that follow a pause or a cut, already said less than 8 s of edit earlier. On a heavy clip: 14 alerts, 5 of which the editor cut. Listen to each alert (`hear.py`).
- **Aborted take left between two cuts** ("I did.", then "I did a photo of the chart"; a sentence trailing off, then its restart; a lead-in that Premiere glued to the previous sentence). A clip under 2 s squeezed between two take cuts is always listened to: it is almost always a false start.
- **Filler openers**: "Well," before "tell me what you think", and an isolated "So," between two pauses: cut.
- **Seam between two clips**: a clip ended on a sentence that is repeated at the start of the next one. A cut that began after its first words left them, and the next clip's opening word (0.9 s) stayed. A seam is handled as ONE sentence: listen to the end of clip 1 and the start of clip 2 together.
- **Put back by the editor**: a word at the start of a kept take (Premiere had two, the cut ate the second) and 0.2 s of "like that". After a take cut, listen to the attack of the kept take.
- **Doubts**: the "silence with noise" cases that the editor cut were asides ("here we go", "but there are options"); an isolated sound at the head of a clip was cut, two at the tail were kept; editorial doubts (an aside, a redundant sentence) were kept as they were. So: a silence with noise that is not a script sentence (aside, handling the gear, "here we go") is cut, no longer flagged. Filler phrases that the editor keeps as is do not deserve even a flag; the ones that repeat the next sentence do.
- **A short, hesitating aside** can be what Premiere writes as a nonsense word (for example a made-up word in the middle of a redundant aside, where whisper hears "an enormous collection of books so uh"): cut by the editor (3 s). A Premiere word with no whisper equivalent in the middle of a restatement deserves at least a flag.
- **A lone false-start word** after a cut silence ("If", 0.7 s, then "often it pays off...") was cut: the orphan-connector rule applies to any lone word wedged between a cut and a pause followed by another attack, not only to And / So / But.
- **A single-word cut can eat the word before**: when the speaker stutters a doubled word ("of the the traveler"), Premiere dates the first copy and the previous word in the same breath and the nearest energy valley falls before the previous word. Same risk on "to stay in a in some" (boundary inside "stay"). For every one- or two-word stutter, listen to the join: `ffmpeg atrim` of the two kept pieces, then `hear.py` on the result. Otherwise a hand-set boundary (6th element of an entry in `takes.json`).
- **Premiere misses mumbled small words** ("So that is the first reason" transcribed "That is the first reason"): cutting the sentence leaves an orphan lead-in. `hear.py` on the slice, then a hand-set boundary.
- **Premiere splits one sentence in two** ("I put them online less" becomes "I." then "But no more online"): a two-word "false start" can be the start of the next sentence. The whisper text of the edit (the W lines of `montage_qc.stdout`) shows it.
- **A repeated name across a full stop is not a stutter** (see SKILL.md).
- **A "retake" can be the end of the previous sentence** (see SKILL.md).
- **Ending lines**: on a call-to-action said several times, keep the **last** version, as the rule says, even if it is less clean than an earlier one (keeping the first and flagging the second was a miss).
- **Instructions to the editor spoken to camera** are cut and listed in the report, because they say where to illustrate.
- **Passages that touch the script's guard rails** (legal wording, figures that differ from the script, a punchline that must stay word for word) go in the report, not in the cuts. Editorial stays with the speaker.

## XMEML traps (fixed in `build_premiere_xml.py`, do not reintroduce)

1. A leftover shorter than one frame at the end (a cut at 1102.10 s on a clip of 1102.101 s) creates a clip with in == out: "Start/end of the track item is not valid", track refused.
2. Rounding the sequence positions (accumulated floats) and the source boundaries separately to frames gives (end - start) != (out - in) on one clip out of three. Fix: accumulate sequence positions in WHOLE frames (start = running total; end = running total + (out - in)), and drop clips shorter than 0.07 s. The script validates itself before writing.
3. Premiere imports only XMEML (FCP7), never modern FCPXML.

## Checks to redo on every rough cut

- **Transcribe the resulting edit again** and read it with the cut points: an 18 s clip for a 6 s sentence = a forgotten silence. It is this check that revealed most of the traps above. (Step 6b, then `montage_qc.py`.)
- `qc_repeat_scan.py`: repeated 5-grams within 30 s in the edit (surviving retake or deliberate rhetoric) and the repeat-with-variant check.
- Always a visual pass in Premiere before approving: a word-by-word comparison does not tell everything about how an edit feels.
- Cuts and results are in FILE time; if a transcript is realigned, redo `apply_takes.py` from word indices, never from seconds.

## Measuring (to recalibrate)

1. Ask the editor for the XML re-exported from THEIR finished sequence (Premiere: File > Export > Final Cut Pro XML).
2. Extract from it the intervals of the clip they kept (a `vdef_intervals.json`-style list of start and end times).
3. Compare with `cuts_final.json`: speech cut wrongly (false positives, measured at sound level > 0.25 x p95 in each gap), silences left, total duration. Also list what the editor removed on top (text, measured speech), what they put back, what they did with the doubts, and which clips they moved.
4. Change a setting only if the measurement improves on SEVERAL clips.
5. When a gap repeats, it becomes a rule or an automatic check; a one-off stays a note.

## Air at the join: why a rough cut is refused at the first cut
The editor stopped watching at the first join: "there is a bad join right at the first cut", then "it is not the picture, it is the sound, you cut a sentence that is not finished".
- **Cause, in the engine**: two mechanisms of `apply_takes.py` contradicted each other. Take cuts were placed 0.10 s after the last kept speech and 0.12 s before the next attack, then the edge re-trim brought any remaining blank back to 0.20 / 0.25 s. Total at a take-cut join: **0.22 s**, against **0.55 s** on the approved silence cuts. On the video in question, **28 joins out of 54** were under 0.30 s. By ear the kept sentence has no time to settle and the next one runs into it, even when no word is truncated.
- **Fix**: a single air budget, measured between the LAST SPEECH of the previous clip and the FIRST of the next one. `AIR_A` 0.27 + `AIR_B` 0.28 = `AIR_TOTAL` 0.55 s, a shortfall on one side being taken from the other (a retake often has no breath before it: all the air comes from after). One pass, at the end, after the cuts are merged.
- **Three measuring traps**, all fixed in `apply_takes.py`: (1) **consonant closure**: the /ʒ/ of "je" after "longtemps" makes a 60 ms dip in the middle of a run of words; without filling gaps under `TROU_MAX` (0.09 s) the boundary lands in it; (2) **3 cs tongue click**: it splits a 2.3 s silence in two and drops the measured budget to 0.17 s, so a legitimate cut was dropped, hence `BLIP_MAX` (0.07 s): a speech island shorter than a syllable is discarded BEFORE filling; (3) **absolute silence threshold**: `QUIET` (6% of p95) falls to zero as soon as a mouse or keyboard sits under the voice; the speech mask at 15% of p95 holds.
- **By cut type**: a `retake` or `faux_depart` ends a take and needs air; without `AIR_MIN` (0.25 s) of silence available on both sides the cut is not made. A `begaiement` or `correction` is removed IN THE MIDDLE of a sentence, the delivery carries on over it: no air to leave, never dropped, and a zero blank there is normal.
- **A hand-set boundary** (6th element of `takes.json`) is law: the air pass no longer touches it.
- **Permanent check**: `montage_qc.py` now measures the blank at the join IN the resulting edit (`--min-air`, default 0.30 s) and exits 2 if a join other than a stutter falls under it. Median obtained: 0.55 s.
- **Wrong lead not to follow again**: "bad join" made me look at the picture. Measuring visual continuity on both sides of the cut was true but beside the point. **On a refused join, measure the air BEFORE looking at the picture.**
- **Empty cut and word 0**: a word said in one breath with the next ("Well, but I think") gave a cut at 0 s, with no error, and the word stayed in the edit; `apply_takes.py` now prints "empty cut": set the bounds by hand after `hear.py`. Cutting from word 0 now starts at the beginning of the clip (it used to leave the blank before it, a "fragment" at QC).
- **A doubled word at the attack of a kept take** ("The... the book begins", right after a take cut): Premiere writes it as a single "The" of 0.68 s, and whisper deduplicates it, so `raccords.py` did not hear it. New check in `montage_qc.py`: a short word (3 letters or fewer) of more than 0.45 s at the start of a clip, followed without a pause, is reported as "DOUBLED WORD?" to listen to. 1 alert on 51 clips, the right one. Same family as the doubled words of earlier videos: the first word of a kept take that repeats the last word of the clip before is to be removed.
- **Presentation said twice**: a name introduced, then the same name taken up after a pause with another sentence around it, is a retake said again, not an effect: keep the last one. A filler sentence that announces without saying anything, in the intro, goes (flag at least; in an intro, propose the cut). A repetition that tells (an anecdote taken up during a demo) is intended: leave it as a doubt, never a cut.
- **When the user only reviews the start** of the rough cut, the intro pass is the sample of what they want: the first 30 seconds deserve the most care (filler sentences, doubled words), the rest of the rough cut holds as is.
- **A collab insert shot without speech** (b-roll, voice-over later): the editor did not take a tight 12-shot sequence; they laid long shots continuously, sped up to 200%. For a b-roll made without speech, propose the long shots sped up first.
