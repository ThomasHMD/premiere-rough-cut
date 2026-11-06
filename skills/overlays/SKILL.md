---
name: overlays
description: |
  Add overlays to a talking-head clip (editorial YouTube video, tutorial, reel) with graphics synced to the word on the voice: lower thirds, full-screen quotes, chapter cards, animated scenes (numbers, lists, timelines, documents, emails, GIFs), illustration photos, b-rolls, automatically recorded website demos, sound effects. Also edits a screen-recording shoot (camera and screen files) in a Tella-style layout switcher. This skill PLACES and EDITS (transcript, timeline of the Premiere project, phrase-anchored plan, sourcing of photos, GIFs, screenshots and emails, screencasts, Premiere XML); everything that is MADE (the Remotion project, scenes, fonts, sounds) lives in the `motion-design` workshop that its scripts call.
  Output: video files (opaque MP4, ProRes 4444 MOV with transparency) and an FCP7 XML importable in Premiere Pro, each element on its own track at its own time.
  Trigger when the user says "add overlays", "lower thirds", "illustrate this video", "dress this clip", "add animations", "find the images for the video", "find a GIF for...", "record a site demo", "record a demo of this website", "Tella-style edit", "edit the camera and the screen together", or hands over a rough-cut talking-head clip to dress.
  Do NOT trigger for: the rough cut itself (skill `rough-cut`), captions (skill `subtitles`), an entire video built from motion design with no footage (skill `motion-design`), color grading, thumbnails.
version: 2.0.0
user-invocable: true
requires_secrets: true
---

# overlays: graphics synced to the voice, placed in Premiere

## Two skills, one workshop

| Here (`overlays`): place and edit | Workshop (`motion-design`): make |
|---|---|
| transcript, timeline of the `.prproj`, plan written as phrase anchors | the ONLY Remotion project: `motion-design/src/`, overlay compositions in `src/illustration/` (BrandedVideo, LowerThirdTrack, Screencast, Scene, FondAnime) |
| sourcing: photos, b-rolls, GIFs (`gifs.py`), web captures, email cards (`mail-cards.py`) | `public/`: fonts, `scenes/<video>/` (scene media), `sfx/` (sounds) |
| recording of site demos (`screencast-record.py`) | theme (`src/illustration/theme.ts`), sound palette (`reference/sound-palette.md`, `scripts/make-sfx.py`, `scripts/son.py`) |
| `render-segments.py`, `screencast-render.py`, `montage-tella.py`: start the render INSIDE the workshop, then place everything in the Premiere XML | music, mix |

The two folders must be **neighbors** (`<skills>/overlays` and `<skills>/motion-design`): the scripts find the
workshop through `../motion-design`. A new scene component is written in
`motion-design/src/illustration/scenes/`; a new sound goes in the workshop's synth recipes.
Installation (once per machine, plugin install): `bash "${CLAUDE_PLUGIN_ROOT}/install.sh" --data "${CLAUDE_PLUGIN_DATA}"`.
By hand, with the four skill folders copied side by side: `bash install.sh` from the kit root. After a plugin
update the workshop's `node_modules` link is gone: rerun the setup line. Details: `INSTALL.md` of the kit.

## Editorial golden rule (default setting, adapt it to the channel)

**The video is carried by the voice. Graphics do not retell what is said: they anchor what one would only
feel otherwise** (a proper name, a quote, a place, a title, a number), **or they SHOW what is being talked
about** (a document, a site, a diagram).

Two levels of dressing:
- **light**: 1 premium per chapter + 1 lower third every 45 to 60 s, outside the intro (0-30 s) and the conclusion;
- **dense** (demo, investigation or tutorial video): animated scenes over 60 to 70% of the picture, each scene
  synced to words, no scene without motion for more than 3 s. The talking head keeps its place.

Ask for the level wanted if it is not said. Do not animate by default: the intro (viewers decide whether to
stay), an intimate anecdote (animation kills the emotion), a question that builds suspense, the conclusion and
the call to action, a list of adjectives.

A deviation from the script that was said on camera (a number, a term, an approximation) is corrected ON SCREEN:
the rough cut flags it in its report, the plan puts the right value on the voice, without asking for a new take.

## Rule zero: the reference timeline is the Premiere project's, never the rough cut's

The order is ALWAYS: rough cut (`rough-cut`) -> **the editor reviews and changes the edit in Premiere** ->
overlays. Between the two, cuts move, clips are dropped, the duration changes: times computed on the rough cut
land 30 s to 1 min off and elements end after the end of the video.

**Hard stop after the rough cut**, even if the user said "rough cut then overlays, it's up to you": deliver the
rough-cut XML, then wait until the user says they validated it in Premiere. Before that, no plan, no times, no
placement. Only what depends on no time can move on (sourcing images and GIFs).

```bash
python3 scripts/timeline-from-prproj.py "/path/clip.MOV" --list              # which sequences carry the clip
python3 scripts/timeline-from-prproj.py "/path/clip.MOV" --sequence "Derush_v1"
# -> <clip>_transcription.json (words in SEQUENCE time) + <clip>_timeline.json (map clip -> sequence)
```

It reads the clips of the footage in the chosen sequence (ticks = 254016000000/s) and carries over the words of
`<clip>_Derush_vN_work/words_premiere.json` (the project's transcript, already realigned by the rough cut).
Several sequences carry the clip: it refuses to guess (code 2), ask which one. Several clips in one sequence:
pass them all, in order (`A.MOV B.MOV --sequence "..."`); each timeline entry and each word carries `media`, and
the outputs take the name of the first clip. A word cut flush stays if it STARTS in the clip (at least 80 ms
before the cut); a word truly cut breaks the anchor that aims at it: move the anchor to the previous word +
`offset`. Check that the last placed element stays before the real end of the sequence.

Never reuse a `cuts_final.json` or a map from the rough cut. Without a Premiere project (clip alone):
`python3 scripts/transcribe.py "/path/clip.mp4"` (local whisper.cpp, about 5 min for 15 min of footage on
Apple Silicon).

**When the user hands the edit back, run the comparison first**: the changes they made in Premiere are the most
reliable feedback. Compare their sequence with the rough-cut XML, turn each recurring gap into a fix, a check
or a rule, and only then write the overlay plan. When the user validates the final edit, do the same with the
delivered overlay XML: what they removed, moved (more than 2 frames), resized or added (their own footage pasted
on V1 does not count) becomes a fix, a check or a rule. Nothing removed or moved means the method of that
delivery is right: keep it.

## Pipeline

### 0. (Optional) b-rolls

A `Brolls/` folder next to the clip, files named `NN_description_K.mp4` (number, description, variant):

```bash
python3 scripts/match-brolls.py "/path/clip.mp4"     # -> <clip>_broll-script.json to complete
```

For each b-roll: the variant (`file`), the time (`timecode` MM:SS, checked in the transcript),
`durationSec` (`null` = native duration). Placed on **V2**. Run it BEFORE the site demos (`--force` overwrites
the file). Look at a contact sheet of the variants before choosing (3 frames per variant): a file name often
lies ("street-photography-portrait" was a drone shot of a city at night). Never put a b-roll on a sentence the
speaker does not literally show, and no overlay sound while a b-roll plays.

### 0 bis. (Optional) illustration photos

For a video that cites people, works, books, places:

1. **Manifest** from the script of the video: entities in order of appearance -> `illustrations-manifest.json`:
   ```json
   {"version": 1, "dest": "Illustrations", "items": [
     {"n": 1, "categorie": "reference", "nom": "First Last", "sujet": "portrait", "url": "https://...", "fallback_urls": [], "note": "source: ..."}]}
   ```
   The reference script can be in any format (text, Markdown, a document): it gives the right spelling and the
   things to show.
2. **URLs**: free sources first (Wikimedia Commons, official sites, open-access museums), then
   `python3 scripts/serp_images.py "Name Title" --num 5 --min-width 1200` (Google Images through SerpAPI, key
   `SERPAPI_API_KEY`). Check that the image is the right one (look at the thumbnail, not just the page title;
   auction lot pages are a trap). Check the rights if the video is sold.
3. **Download**: `python3 scripts/source-illustrations.py illustrations-manifest.json` ->
   `Illustrations/NN-category-name-subject.ext` (bytes checked, width measured; exit 1 if URLs are missing).
4. **Timing**: `python3 scripts/match-photos.py "/path/clip.mp4"` -> `<clip>_photos-script.json`, times prefilled by
   a fuzzy search of the name in the transcript (speech recognition mangles proper names). ALWAYS recheck each
   time by hand against the transcript (the fuzzy match can take a late mention instead of the first);
   `enabled: false` drops a photo. Photos go on **V3**, with priority over b-rolls (a b-roll that overlaps a photo
   is removed from the XML and logged).

Photo treatment: never crop (native ratio, a vertical stays vertical); a photo sits on a plain background with a
margin on all four sides (about 86% of the frame), not a full-frame contain that touches the top and bottom
edges. No `.webp` in the manifest (Premiere reads it as a zero-length media in XML: convert with
`sips -s format jpeg`). A photo under 800 px wide will look soft: `render-segments.py` prints a LOW RES warning,
list those before delivering. A book cover shown by a scene is the publisher's visual taken from the web (their
site, an HD mockup), never an image pulled from the speaker's own footage.

**When the speaker SHOWS an object, nothing covers it.** Scan the transcript for "here", "as you can see here",
"this one", "look" near the mention of a work: the speaker is holding the book or camera to the lens. No
full-screen photo on that window (an editor removed every such cover in a delivered edit); the cover goes
before or after the demonstration, or not at all.

### 0 ter. GIFs and memes (a basic, not an option)

One GIF every 2 to 4 min, on moments of mood or self-mockery ("this pushes very hard", "I am making it all up"),
never in the intro, never to illustrate a technical sentence literally. A `gif` scene (overlay, white frame,
looping) that arrives on the word, with its sound effect.

```bash
python3 scripts/gifs.py chercher "that's a bug" --planche gifs-sheet.jpg   # list + numbered contact sheet
python3 scripts/gifs.py prendre <id> --nom bug --public <video>            # source MP4 + the scene's data
```

Look at the contact sheet BEFORE choosing (a GIPHY title does not say what is shown; searching in English often
works better). `prendre` downloads the MP4 (never the .gif) into `Illustrations/gifs/`, keeps `gifs.json` (source
of every GIF), copies it to `motion-design/public/scenes/<video>/gifs/` and prints the `data` of the `gif` scene
(src, srcW, srcH, loopSec). Key `GIPHY_API_KEY` (free). A GIF often reuses a protected work: on a video that is
sold, abstain.

### 1. Frame rate and format of the clip (CRITICAL)

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate,width,height -of csv=p=0 "/path/clip.mp4"
```

`render-segments.py` reads rate and size of the clip when the JSON does not give them. A JSON at 30 on a clip at
60 shifts everything by a factor of 2. At 29.97, n sequence frames last n x 1.001 / 30 s, and each render must
cover its clip (`tailFrames` and the `TenirFin` component take care of it). A clip is written in the rate of its
MEDIA: Premiere reads `<in>` at 29.97 (the rate of the `<file>`), not in the clip's `<rate>`; the script writes
`in = round(t x fps x 1000/1001)` with `<ntsc>TRUE`.

**Vertical 9:16** (reel): same pipeline, same JSON. The lower third detects vertical and moves up above the
caption zone; photos stay whole (a band on the background); a 16:9 b-roll gets a scale that fills the width.
Reel rules (from comparing deliveries with the final edit): photos of 2 to 3 s (default 2.5), lower third as
long as its associated portrait photo and starting with it, no stock b-roll unless asked, no cover while the
speaker shows the object. Always render ONE lower third as a still and composite it on a gray frame to check the
vertical layout before the series.

### 2. Read before proposing

Read the WHOLE transcript. Spot: names of people (lower third "nom"), titles of works ("oeuvre"), places
("lieu"), terms or movements ("term"), strong quotes (premium `quote-full`), announcements of a part
(`section-title` or chapter card), striking numbers (`stat` scene), documents, exchanges and sites that are
talked about (proof scenes, demos). Every cited name, work or book is SHOWN somewhere (a hanging scene, a
photo, a card) or the reason it is not is written down. Read each diagram's content in the speaker's OWN words
(re-read in the transcript), never an interpretation: a wrong diagram (a profile placed on the wrong level of a
funnel) comes from paraphrasing.

### 3. Every premium is conceived in one sentence

"What I want to see: the sentence large, in italic, an accent rule on the left, the attribution small." If the
description is "text that appears", it is not a premium: lower third, or nothing.

### 4. Base catalog

| Type | Component / kind | Track | Data | Duration |
|---|---|---|---|---|
| `motion` (full-screen premium) | `quote-full` | V5 opaque | `text`, `author?`, `source?` | 10-14 s |
| `lower-third` | `lower-third-nom` | V6 alpha | `name`, `years?`, `tag?` | 6 s |
| `lower-third` | `lower-third-oeuvre` | V6 | `title`, `author`, `year?` | 6 s |
| `lower-third` | `lower-third-lieu` | V6 | `place`, `date` | 6 s |
| `lower-third` | `lower-third-term` | V6 | `term`, `subtitle?` | 6 s |
| `section-title` | | V6 | `eyebrow?`, `title` | 4 s |
| `scene` | see "Animated scenes" | V5 / V6 / V7 | `data`, `cues` | follows the voice |

A name and its work cited within 10 s: a single "nom" lower third with the work in `tag`. A quote by the
speaker themself: `quote-full` without `author` (their voice signs). The animations end with an automatic
fade-out over the last 18 frames.

### 5. Times to the word (CRITICAL)

Never an estimate: look the word up in `<clip>_transcription.json` and take its `start`. The element appears
**at the start of the word** (a lower third may precede it by 0.5 s at most; syncing on the start of the SENTENCE
reads as an announcement that comes early). `render-segments.py` refuses a segment without a valid time and
checks every time against the transcript (OK / WARN / UNKNOWN). Also check the frame rate in the JSON
(step 1).

### 6. Present the plan before writing

```
| # | Time  | Dur  | Type        | Component         | Why                            |
|---|-------|------|-------------|-------------------|--------------------------------|
| 1 | 01:24 | 6 s  | lower-third | lower-third-nom   | 1st mention of First Last      |
| 2 | 02:14 | 12 s | motion      | quote-full        | pivot quote of part 1          |
```

Wait for approval before writing the JSON and rendering.

### 7. Render and import

```bash
(cd ../motion-design && npm ci)                                   # once
python3 scripts/render-segments.py "/path/clip.mp4"               # everything: renders + XML
python3 scripts/render-segments.py "/path/clip.mp4" --lower-thirds-only
python3 scripts/render-segments.py "/path/clip.mp4" --skip-render   # XML only (files already rendered)
python3 scripts/render-segments.py "/path/clip.mp4" --no-sfx | --no-brolls | --no-photos | --dry-run
python3 scripts/render-segments.py "/path/clip.mp4" --suffixe v2    # next delivery: "... Illustration V2.xml"
```

Deliveries are named the way the editor looks for them: `<number> Illustration V1.xml` (a sequence of the same
name), `<number> Illustration V1 - rendus/` (the rendered files: `ANIM-P01-02m14s-quote-full.mp4`,
`ANIM-LT01-...mov`, `ANIM-S-<id>.mp4|mov`...) and `<number> Illustration V1 - sons.md` (+ `.json`). The number is
read from a folder named like `Video 12_title`, otherwise the clip's name is used. **A delivery that was
announced is considered imported: NEVER rename it afterwards** (the open project is not the `.prproj` on disk;
renaming gives offline media). A new name applies to the next delivery (`--suffixe v2`).

Import: `File > Import` the XML, open the sequence. Tracks, bottom to top: V1 the clip (or empty with
`--no-rush`, to paste your own sequence there), V2 b-rolls and demos, V3 photos, V5 premiums and opaque scenes,
V6 overlays, V7 wipes; A3 and above: sound effects, on separate tracks (muting or lowering a track is one
gesture). Everything can be disabled, moved, deleted by hand.

The XML is only written if it passes `garde_premiere.py` (otherwise it stays as `.REFUSE.xml`): sorted tracks,
truth of the files, durations, sounds, masking, copies in sync conflict. After import,
`python3 scripts/garde_premiere.py <xml> --projet <.prproj>` checks that no ghost clip was created.

**The sequence was already imported and worked on** (clip pasted, audio effects): never ask for a reimport. Ask
the user to save and CLOSE the project, then `python3 scripts/reparer-projet.py <project.prproj>` (sorts the
tracks of the `.prproj` with `prproj_lib.sort_tracks()`, proves that only the order of clips changed; `--essai`
stops before replacing), then `garde_premiere.py <xml> --projet <.prproj> --sequence <name>`. Regenerated media
keep their name: Premiere reloads them on opening.

A file that is redone keeps its name and replaces the old one in one move (written next to it, then renamed):
Premiere reloads it without reimport. To redo ONE scene in place (subtitles of a reel, a single card):
`render-segments.py <clip> --no-rush --skip-verify --script <script.json> --en-place <id>`. It compares codec,
profile, alpha, size, rate, frame count and duration before replacing the file; one difference and nothing is
replaced (exit 1).

## Sound (tracks A3 and above)

Every sound effect comes from a palette synthesized once (no samples, no rights), already at the right level
under the voice: **read `../motion-design/reference/sound-palette.md` before placing a sound.**
- Synth recipes: `python3 ../motion-design/scripts/make-sfx.py` (regenerates `motion-design/public/sfx/` +
  `palette.json`). `--voix clip.mov` measures the voice level; `--planche out.mp4 [--voix clip.mov]` makes a
  listening sheet.
- Vocabulary: `motion-design/scripts/son.py`. A plan names a GESTURE (`son.liste`, `son.chapitre`,
  `son.tampon`...), never a file or a volume.
- **Sound report**: every pass of `render-segments.py` writes `<number> Illustration V1 - sons.md` (and `.json`)
  next to the XML: each sound numbered, its time, the scene and its text, the words said at that moment, the file,
  the role, the level. Claude places sounds without hearing them: give this report to the user, who answers by
  numbers ("remove: 3, 17 to 19"); then fix the plan by family of gestures, not sound by sound (method:
  `sound-palette.md`, "validate by ear").
- Another palette (real recordings): `../motion-design/scripts/palette-import.py`, then `son.palette("<name>")` at
  the top of the plan.
- No background music on a long video.

Defaults outside scenes: lower third -> `pose-1.wav`; section title, book cover photo -> `page.wav`; full-screen
quote -> `accord.wav`; site demo -> clicks, keystrokes, pages written by `screencast-render.py`
(`<demo>.sons.json`). Global change: the `sfxDefaults` key of the JSON (`{"lower-third": "clic.wav",
"motion": null}`); per segment: `"sfx": {"file": "...", "gainDb": -3}` or `"sfx": null`. Sounds stay on separate
tracks, never fused in the .mov/.mp4.

## Animated scenes: the graphics that follow the voice

A scene = a component + its content (`data`) + its times (`cues`, in seconds from the start of the scene).
Everything that moves lands on a word.

```json
{ "type": "scene", "id": "part-1", "component": "chapter-card", "alpha": false,
  "timecode": "00:22.84", "durationSec": 3.2,
  "data": {"n": 1, "total": 3, "name": "The subject"}, "cues": [0.58],
  "sfx": [{ "file": "page.wav", "at": 0.0, "gainDb": 0 }] }
```

- `alpha: false`: opaque full screen, h264, V5. `alpha: true`: overlay, ProRes 4444, V6. Two clips that overlap
  go on two tracks.
- `track: "V7"`: a separate track at the very top (wipes go there: hiding one track removes all transitions).
  With `--no-rush`, V1 stays empty for the editor's own sequence.
- `id` = file name (`ANIM-S-<id>`). The same `id` placed several times is rendered once (the animation of the
  shortest, last frame held up to the longest).
- Cache: only scenes whose props OR the code of `src/illustration/` changed are rendered (the code fingerprint
  is part of the key); `--only <part of id>`, `--force`.
- `sfx`: mixed into ONE WAV per scene (`...-son.wav`), placed on A3 (A4 on overlap), built with `son.py`.
- **No logo** in a scene, a premium or a lower third: it weighs down the picture for nothing. A scene footer
  carries at most the site address.

**Catalog** (`motion-design/src/illustration/scenes/`, registry `Scene.tsx`; the `data` contract is a comment
above each component):

| Full screen | Used for |
|---|---|
| `chapter-card` | "Part N / total": giant number, name, progress bar (`n`, `total`, `name`, `eyebrow`, `icon`, `label`) |
| `question-card` | full-screen question on a dark background, words falling one by one |
| `stat` | strong number with counter, notes (`site: false` removes the address, `check: false` the ticks) |
| `phone-demo` | phone screenshot in a mockup + numbered steps |
| `preuve` | an email, web page or photo that the camera explores, one step per sentence (highlight, strike, frame), notes, stamps |
| `chapitre`, `titre` | chapter card (giant number, question as overline, bar N / total); video title on a dark background |
| `dialogue` | an app's error message, typed word by word |
| `frise` | dates on a line, revealed in the order of the voice (not necessarily chronological), stamp |
| `duel`, `versus` | two verbatim quotes side by side, marked on words; two values face to face and a verdict |
| `demandes`, `textes` | grid of requests ticked, half-ticked or struck as the voice goes; "what the text imposes / what I got" line by line (`k`, `ke`: times of the line and of the answer) |
| `noeuds`, `chiffres`, `dossier` | node diagram with cut links; a few giant numbers (rule of 3-2-1); shared folder that fills up, then sharing, scan, flagged file, stamp |
| `recherche`, `terminal` | typed search and results; command and highlighted output |
| `murs`, `tri`, `route`, `accrochage`, `financement`, `mosaique`, `citation` | worked models of richer diagrams (obstacles on a road, nested selections, a map with a growing route, framed works with captions, a gauge, columns that fill) |
| `mx-*` | a complete alternative look ("green terminal"): bricks and rules in `motion-design/SKILL.md` |

| Overlay (alpha) | Used for |
|---|---|
| `stamp`, `stamp-rain` | stamp with counter; volleys of stamps (running gag) |
| `slam` | words that slam on paper labels (`lines: [{text, accent}]`, `side`) |
| `side-list`, `stat-tag` | side card with a list; number in a label |
| `bulle-dm` | messaging bubbles |
| `lien-description`, `url-bar` | "link in description" arrow; a site address |
| `gif` | GIF or meme as MP4 in a frame, on one side, looping |
| `sondages`, `gaufre`, `croyance` | stacks of answers or a typed answer; percentage in 100 cells; a received idea struck on the word, then the verdict |
| `volet` | 15-frame curtain that hides the cut between talking head and full screen |

**No overlay on the speaker's head: measured, placed, checked by code** (`scripts/zone_libre.py`). The classic
defect: "right third" by eye puts stamps on hair and beard and cards on the ear and glasses (a face often
spans 38 to 64% of the width, the hair reaches near the top, and the speaker moves). Once the rough cut is
validated:

```bash
python3 scripts/zone_libre.py mesurer <clip> <clip>_timeline.json <_Illustration_work folder>
```

4 frames per clip of THE SEQUENCE, face and silhouette detection (Apple Vision, `tete.swift` compiled in cache);
`tetes.json` = forbidden zone per clip (head + 3%). Look once at `tetes-controle.jpg`: a raised hand or a book in
front of the face skews the measure; a clip without a face takes the median box. In `plan.py`:
`Z.charger(tetes.json)`; overlays state their wishes (maximum size, height); after `habillage.tenue()`,
`Z.poser(component, data, start, end)` sizes and places them from the head to the edge (text measured in the real
fonts, long stamp or card on two or three lines, fall and ring of a stamp bounded); then `Z.controle(SEG)` stops
the plan if any box (rotation, animated entrance, ring, shadow, bounce included) cuts the forbidden zone.
Components covered and their placement parameters: `stamp` (cx, depart, anneau, line breaks), `slam` (right,
depart), `stat-tag` (right), `croyance` (x, w, size, verdictSize), `gaufre` (x, w), `gif` (x), `sondages` (x, w,
tamponCx), `lien-description` (right, bottom, size). A component that changes means its geometry in
`zone_libre.boite()` changes too. To verify on images: render the overlays at their entrance, take the pixels
with alpha > 0.15 (`Z.boite_alpha()`), compare with `Z.interdite()`. Overlay preview sheets put each overlay on
the frame of the clip **at the same instant**, not on a fixed frame.

**When the speaker shows an object** (camera, book held to the lens): `python3 scripts/montre.py <clip>
--planche sheet.jpg` finds windows without a face (one frame every 0.5 s of the edit, at least 1 s without a
face); look at the sheet (the detector also misses faces, and the speaker may simply be reading notes). Then
`SHOWN = [(start, end)]` in the plan, passed to `tenue(..., montre=...)` and `coupes(..., montre=...)` (nothing
extends there); a window end lands on ITS cut. `habillage.libre_montre()` stops the plan if a scene, overlay or
zoom falls on it. When the speaker shows books, the camera framing can also move toward the book: a `zooms`
entry with `cadre` keyframes (see below).

### The plan is written as phrase anchors, not seconds

Model: `examples/plan-example.py`, copy it to `<clip>_Illustration_work/plan.py` and rewrite it for the video.
`T("first part", after=...)` looks the phrase up in the transcript; the plan computes starts, durations, cues
and sounds, then writes `<clip>_animation-script.json`. When the editing moves: `timeline-from-prproj.py`, then
`plan.py`, then `render-segments.py`, and everything realigns. An anchor that is not found stops the plan
(code 2) with the list: never a placement at 0. Before writing, the plan calls `habillage.tenue()`, then
`habillage.coupes()`, then `habillage.volets()` (`scripts/habillage.py`): never copy these rules into a plan,
import them.

**No dead time.** A scene where nothing moves for more than 3 s is a failure: add a cue on the sentence said at
that moment, or shorten the scene. Reread the cue list of every long scene before rendering.

### What must never be delivered (each defect has its mechanism and its test)

"Dynamic and interesting, not nervous and stressful."

| Defect seen | Cause | Mechanism | Test |
|---|---|---|---|
| the face shows for one frame between two animations | demo shorter than its window; camera returns of 0.3 to 0.7 s between two blocks | `screencast-batch.py` passes `--minDuration` = window + 0.1 s; `habillage.tenue()` holds the previous block until the next | `qc-sequence.py flash` and `tenue` |
| "it clicks everywhere, zooms in, out, in again" | camera following every gesture; on/off clicks | camera planned in shots (`screencast-render.py`, "Calm camera"); scenario rules | `qc-sequence.py camera` |
| "it lasts the time of one word, it's gone" | duration = gap between two words | `habillage.tenue()` then `volets()` in EVERY plan | `qc-sequence.py tenue` |
| offset that grows toward the end of the preview | preview glued from separately encoded pieces (+3 ms per second) | `preview-sequence.py`: talking head in one piece, sound copied sample by sample | `qc-sequence.py derive` and `mots` |
| "nothing on the timeline but something shows", elements that jump on zoom | clips written OUT OF ORDER in an XML track: Premiere uses the file order as an index, the clip becomes a ghost | `build_xml` sorts every track; `garde_premiere.py` refuses to write | `garde_premiere.py` |
| sounds with no animation | sound of a ghost or of a deleted element | guard: every sound falls during a visible element | same |
| a frame of the track below at the end of a scene (29.97) | render rounded to round(duration x 30) frames | `TenirFin` + `tailFrames`: each render covers its clip + 2 frames | guard, DURATION rule |
| a frame of face after a cut | block edge 1 to 6 frames on the wrong side of the editor's cut | `habillage.coupes(SEG, BROLLS, TL, tc, fps=30000/1001, montre=...)` after `tenue()`, before `volets()`: such an edge snaps to its cut (29.97 grid, not 30) | `qc-sequence.py coupes <xml> <clip>_timeline.json`: 0 edge |
| text eaten by the drawing, text off the screen, empty background for 9 s | layout error in a component | `controle-texte.py` (below) | same |
| text on screen too briefly to read | sentence of 3 words or more visible less than 0.5 s + 1 s per 3 words | `controle-texte.py` writes `<base>_lecture.json`, the plan passes it to `tenue(..., lecture=...)` | `controle-texte.py`: 0 READING |
| an element shown long before it is said | `cues[0]` = the word, scene 0.1 to 0.2 s before it | `habillage.avant_le_mot()`: blocking beyond 0.8 s (chapter cards excepted) | `habillage.controles` |
| a cited name or work with nothing on screen | every cited name, work or book is shown, or the reason is written | `habillage.cites(words, SEG, BROLLS, CITES, tc, voix_seule=...)`: each entry of `CITES` has a scene within +-6 s or a reason; any capitalized word outside sentence start and never written lowercase is listed until the plan files it | same |
| too busy, "too present" | no wipe over a b-roll, a retro look or a short block (under 4.5 s), none between close blocks (under 3 s); no sound while a b-roll plays; a straight switch is lighter | `habillage.volets()`, `habillage.sobriete()` (blocking: WIPE OVER B-ROLL, SOUND OVER B-ROLL) | same |

**Blocking order.** `plan.py` calls `habillage.controles()` (at the word, cited, sobriety) and writes nothing if
it fails; it marks the script `controle_texte: true`; `controle-texte.py` signs the script when everything passes
(`<base>_controle-texte.json`: fingerprint of the scenes and of the component code) and `render-segments.py`
refuses a marked script whose signature is missing or no longer matches. Witnesses: `python3
scripts/habillage.py --self-test` (each check fails on its own case).

**Text check, on the real layout** (`python3 scripts/controle-texte.py <clip>_animation-script.json [--only <id>]
[--pas 10]`): renders all scenes end to end in the `ControleTexte` composition of the workshop (one frame in 10,
very small) and reads the layout report of each frame. Blocking (exit 1; the script's own labels may be DEBORDE, MORD, CHEVAUCHE, COUPE, VIDE, LECTURE or their translation): OVERFLOW (text leaves the frame), BITE
(text straddling a drawn shape), OVERLAP (two texts on each other), CUT (text clipped by a mask), EMPTY (a
full-screen scene with no content outside decoration for more than 1 s), READING (a sentence on screen less time
than needed to read it). Decoration is marked `data-decor`, a text in pixels `svg[data-texte]`. The loop for
READING: plan, check, plan, check; what stays blocked ("!! ... remains at") is settled by hand (earlier note,
shorter text, faster typing). The wanted duration keeps a 0.15 s margin (`LECTURE_MARGE`, otherwise the loop never
ends) and is kept from one turn to the next at the maximum: when a text changes or shortens, remove its key from
`_lecture.json` before rerunning.

**Hold on screen** (`habillage.py`, minimums at the top of the file):
- chapter card 3.0 s, question card 2.8 s; a card that bumps may enter up to 1.0 s earlier (its sounds follow);
- overlay 2.6 s, its LAST element held 1.6 s; stop on the cut of the next full-screen block (the wipe covers it)
  or 0.15 s before the next overlay ON THE SAME SIDE (`data.side`); a stamp (one word) passes from 1.8 s and is
  skipped below;
- if room is short, it is the card or demo that FOLLOWS that waits (0.8 s at most), never the element that would
  be cut;
- a card never covers the start of a demo (it opens on a gesture and its noise, heard without being seen): the
  demo starts when the card ends;
- no camera return shorter than 1.2 s between two blocks (it would be a hard cut, and show the face for half a
  second): the previous block holds until the next one (a demo keeps its last frame; `screencast-batch.py
  --rendu-seul` if only its end moved);
- an element enlarged to be readable never hides a b-roll or a demo that starts later: `tenue()` also bounds by
  their start;
- `tenue()` returns its log: a "!!" line is a minimum not met, to settle by hand (move an anchor, remove an
  element), never let it pass silently;
- `qc-sequence.py tenue` counts as covering only opaque clips: a transparent stamp over a flip-through does not
  hide it;
- sounds synced to words never move, and a stamp or slammed word lands at the START of ITS word (cue = start of
  the word, scene 0.1 s before, like `stamp()`).

**Zoom on the speaker's camera** (`zooms` key of the script, a few per 12 min, on jokes): punch-in capped at
112%, anchored on the center of the head, the editor's next cut does the zoom-out; never under an overlay or a
full-screen block; it starts at the end of the previous block or on a cut, and ends ON a cut when one falls
within 1.5 s; with under 1.2 s of room, no zoom. `render-segments.py` places them on V2, video only, above V1
(the editor's `.prproj` is never touched). The plan stops if a zoom falls under another element. Checks:
`qc-sequence.py zooms <preview> <base> <xml>` (each zoom looked up in the base at +-1 s, peak at 0 +-1 frame) and
`qc-sequence.py coupes` (zoom edges). To move toward a book being shown: a `zooms` entry with `cadre`
`[(t, scale, cx, cy), ...]`, times in CLIP time (they follow the editor's changes), position of the book measured
on a gridded contact sheet of the frames, 130% zoom, centre moved toward the book within the frame limits, back
to 100% when it is lowered; `render-segments.py` writes scale and centre as keyframes; nothing goes over it.

**Demo scenarios**: filters and chips -> the cursor glides from chip to chip (`move` anchored on the word), a
single click that shows the effect, never an on/off click at every word; map (Leaflet...) -> one zoom, never back
and forth; two quick focus steps -> `hover: false` on the second (otherwise the cursor travels first, about 0.6
s more, and the next gesture starts late); a demo window that moves (`tenue()` shifts it) -> record again; a
gesture anchored more than 0.5 s late -> remove or shorten a free step at the start.

### Full chain, in this order (each test exits 1: do not deliver)

```bash
python3 plan.py "<clip>"                                            # plan (tenue + coupes + volets), fenetres-demos.json
python3 scripts/screencast-batch.py "<clip>" fenetres-demos.json    # demos (those whose window moved)
python3 scripts/controle-texte.py "<clip>_animation-script.json"    # text: 0 overflow, 0 bite, 0 empty screen, 0 reading
python3 scripts/render-segments.py "<clip>" --no-rush --skip-verify # scenes (cache) + XML
python3 scripts/preview-sequence.py "<clip>" 0 <end> apercu-v1.mp4 --garder-base
python3 scripts/qc-sequence.py derive "<clip>" apercu-v1.mp4        # voice within 20 ms on every clip
python3 scripts/qc-sequence.py mots apercu-v1.mp4 "<clip>_transcription.json"   # whisper: no drift
python3 scripts/qc-sequence.py flash apercu-v1.mp4 apercu-v1.base.mp4   # 0 flash
python3 scripts/qc-sequence.py tenue "<folder>/<number> Illustration V1.xml"
python3 scripts/qc-sequence.py coupes "<folder>/<number> Illustration V1.xml" "<clip>_timeline.json"
python3 scripts/qc-sequence.py zooms apercu-v1.mp4 apercu-v1.base.mp4 "<xml>"
python3 scripts/qc-sequence.py camera "<folder>"/Screencast/.rec-*/render/props.json
python3 scripts/qc-preuves.py "<clip>_animation-script.json" ../motion-design/public
python3 scripts/qc-sequence.py bords "<folder>/<number> Illustration V1 - rendus"/*.mp4 "<folder>/<number> Illustration V1 - rendus"/*.mov
```

`preview-sequence.py` and `qc-sequence.py` read `soundfile` and `cv2`: use the Python that has them. Then the
pass by eye, before writing "it's ready":

```bash
python3 scripts/qc-sequence.py planches apercu-v1.mp4 "<xml>" .sheets-v1 "<clip>_animation-script.json" "<clip>_transcription.json"
python3 scripts/qc-sequence.py scenes apercu-v1.mp4 "<clip>_animation-script.json" .sheets-scenes-v1
```

One row per join (frames -10, -4, 0, +4, +10 around every block entry and exit), a thumbnail per slammed word
captioned with the word said at that instant, then the inside of the scenes (one thumbnail 0.8 s after every
cue of every scene): READ every sheet, the word displayed must be the word said. Sheets of joins alone miss
framing defects inside scenes. Title the sheets with PIL (some ffmpeg builds have no `drawtext`).

**The preview is a checking tool, not a deliverable.** Build it in a scratch folder for `derive`, `mots`, `flash`,
`planches` and `scenes`; do not drop it in the video folder and do not open it: the deliverable is the XML. On
request only, a delivered preview carries a version number (`apercu-v2.mp4`): never overwrite one the user has
seen.

Measurement traps: whisper dates words about 170 ms early, constant over the whole video (`mots` judges the
drift, not the absolute gap). To measure a true word start, look for the energy rise AFTER the end of the
previous word (otherwise, on a short pause, you catch its tail and think the transcript is late).
`timeline-from-prproj.py` measures this acoustic offset at every pass and only corrects beyond 40 ms.

**Deliver** = `render-segments.py` passes its guard (otherwise nothing is written), the chain above is green,
THEN an independent second pass: logo detector (there must be no logo), frame-by-frame coverage recomputed
apart, a contact sheet of every regenerated file. Even when certain, redo the pass.

**Delivering a V2 after the review.** Method:
1. Read the user's markers one by one (text and time); trace each to its cause and fix the cause in the tool for
   the whole video, never at the marked spot only.
2. `render-segments.py ... --suffixe v2`: `... Illustration V2.xml`, `... V2 - rendus/`, `... V2 - sons.md`; their
   project references the files of V1, rewriting them would change the sequence they are looking at. Check that
   every V1 file is still present and that V2 references none of them.
3. Have a sub-agent review the diagrams on contact sheets ("readable by a newcomer, faithful to the speaker's
   words") and apply ALL its remarks in one pass.
4. Replay the full chain after the slightest change to the plan until green (a reading fix once caused a b-roll
   to be hidden; the guard refused it).
5. One labeled contact sheet from the final preview: every marker and every moment where the speaker shows an
   object, at that instant.
6. A README in the video folder: one section per version (marker -> what changed, review, figures from the
   checks).
7. On validation, run the comparison with the final edit (see rule zero), then empty the scratch folders.

If the sync of the video folder is being watched or paused (Dropbox, iCloud, Drive...): write in it only the
deliverables, each once. Previews, sheets and trials go in a scratch folder; a deliverable goes through a
non-synced folder of the same disk and a `mv` (atomic rename). `MONTAGE_DEPOT` = a non-synced folder of the same
disk for the work files of the render; demo recordings already go in `~/.cache/kit-montage/` (or
`MONTAGE_CACHE`). Look for conflict copies at the start of every session: `garde_premiere.py` refuses an XML
whose media has a "conflicted copy" next to it.

## Proofs on screen: emails, web pages, screenshots

For a video that tells an exchange (dispute, customer service, application), the proofs are prepared BEFORE the
overlays, in `<video folder>/Illustrations/`: `mails/`, `web/`, `images/`, `gifs/`, `cartons/` (figures of the
cards), `terminal/`, plus an `ELEMENTS.md` that links each element to its anchor sentence, its status and what
the user must provide.

**Emails: `scripts/mail-cards.py mails.json [--planche]`.** One card per email (2x PNG, transparent background)
in the style of a mail client, text VERBATIM, and a `.boxes.json` with the rectangles of key phrases (to zoom,
highlight, strike). `flou` hides names and addresses everywhere (replaced by random letters then blurred:
irrecoverable; the avatar initial does not give the name away). A branded HTML email is rendered from its original
HTML (`"html": "src/..."`), tracking pixels and links removed; support tickets keep their header ("Please type
your reply above this line", ticket, author, time). A key phrase that is not found makes the email fail: that is
the guarantee of verbatim. Where to take the text: the user's mailbox (in Gmail open in a browser, "Show
original" gives the MIME; keep only the first message, not the whole quoted history, which can weigh 100 KB;
`DOMParser` may be blocked by Trusted Types on Gmail, extract with regular expressions).

**Web pages**: Playwright, 1920x1080 window at 2x, capture of top of page + full page + one crop per key phrase
with its coordinates (`<subject>.boxes.json`), cookies refused, never log in. A page that is gone or paywalled:
Wayback Machine. Crop around the phrases used (JPEG of 1,000 CSS px): a full page weighs 6 MB, the crop 0.2 to
0.9 MB; check on a sheet that no crop shows a forbidden thumbnail (a child, a cover).

Framing lessons (details in `references/lessons.md`, "Proof scenes"): every step carries a `vue` so no line is cut at the edges; a document does not stay in wide shot more than about 4 s; notes have a banner at the top left and the close shot frames under it; everything anchored on the right is anchored BY THE RIGHT; non-breaking spaces before " ? ! :" in all scene texts. `scripts/qc-preuves.py <animation-script> <motion-design>/public` replays the camera without a render (exit 1 if a view falls under the banner, a mark passes within 24 px of an edge, or a visible email line is cut).

## Site-demo mode: Tella-style screencast

The user talks about a site or web app and wants us to SEE it, without recording the demo themselves. A driven
browser plays a scenario synced to their voice, captures the screen at double resolution, then the render adds
background, browser window, zooms that follow the action, spotlight, animated cursor and captions. Example
scenario: `examples/screencast-example.json`.

```bash
python3 scripts/screencast-record.py scenario.json --out /tmp/demo-rec [--transcript clip_transcription.json]   # about 4 min per minute
python3 scripts/screencast-render.py /tmp/demo-rec --rush "/path/clip.mp4"    # in a video: rate of the clip, placed on V2
python3 scripts/screencast-render.py /tmp/demo-rec --out demo.mp4 [--fps 30]   # standalone demo
python3 scripts/screencast-batch.py <clip> fenetres-demos.json [id...]           # several demos of one video
```

**The skill places the demos, not the user.** A screencast is a b-roll like any other: `--rush` writes it into
`<clip>_broll-script.json` (`id: "SC-<scenario>"`, `kind: "screencast"`, `timecode` to the millisecond) and
`render-segments.py` places it on V2 at its `rushStart`. Never deliver "a file + the time to place it". The
recording makes about 1 GB of frames per minute: always `--out` in a scratch folder, never in a synced folder.

### Scenario format

```json
{
  "url": "https://example.com/",
  "viewport": [1440, 810], "dpr": 2, "slow": 4,
  "rushStart": 0,
  "hide": [".cookie-banner"],
  "render": { "fps": 60, "background": "dark" },
  "steps": [
    { "do": "wait", "sec": 1.4, "eyebrow": "The site", "caption": "The home page" },
    { "do": "focus", "target": "h1", "sec": 2.6, "spotlight": true },
    { "do": "scroll", "to": "#search", "sec": 1.2 },
    { "do": "type", "target": "#search input", "text": "Example", "word": "search" },
    { "do": "click", "target": "a:has-text('Result')", "at": 21.5 }
  ]
}
```

| `do` | Effect | Options |
|---|---|---|
| `wait` | wait | `sec` |
| `goto` / `back` | navigation | `url`, `sec` |
| `scroll` | smooth scroll | `to` (selector) + `block` `center`/`start`, or `by` (px), or `y`; `sec` |
| `move` / `hover` | moves the cursor | `target`, `pos: "left"`, `sec` |
| `click` | click (auto zoom) | `target`, `zoom: false` to not zoom (anchor link, menu) |
| `type` | click in the field then type | `target`, `text`, `delay` (s per key) |
| `clear` | empties a field | `target` |
| `focus` | zoom framed on an element (on its real content) | `sec`, `zoom`, `spotlight: true`, `pad`, `hold: true` + `unfocus`, `hover: false`, `wholeBox: true` |

On any step: `caption` (+ `eyebrow`, `captionSec`); **`at`** (seconds from `rushStart`) or **`word`** (+
`occurrence`, `offset`) to start exactly on a word of the transcript. If a gesture runs late (slow page), the
render realigns time (speed-up flagged beyond x2.5). `target` = Playwright selector (CSS, `:has-text()`,
`text=...`). `hide`: elements hidden on all pages (cookies, chat, newsletter pop-up). `geolocation`:
`[lat, lon]`, a SIMULATED position (never the user's) with the permission granted, for "near me" buttons.
`render`: `fps` (that of the clip, 29.97 included), `background` `dark`/`paper`/`accent`, `chrome` (browser
bar), `autoZoom` (1.7; 0 = none), `maxZoom` (2.0), `zoomLead`/`zoomHold` (the zoom starts 1.1 s before the click,
holds 1.8 s), `glide`, `minShot`, `deadZone`, `zoomSmooth`/`panSmooth`, `minDuration`, `cursorSize` (each key
also exists as an option of `screencast-render.py`).

**Calm camera** ("it clicks everywhere, zooms in, out, changes zone, zooms in again where it could just glide"):
the camera is planned in shots. Two close-ups less than `glide` (3.5 s) apart chain by gliding, zoom held (the
weaker of the two), without returning to the wide shot; a close-up (or chain) shorter than `minShot` (3 s) is
dropped, except with a spotlight (held 3 s); the camera does not move while the target stays inside the central
`deadZone` of the frame; slow springs (0.55 s zoom, 0.50 s reframe). `--props-only` prints the camera plan;
`qc-sequence.py camera` measures the result.

**With the voice**: transcribe, find the passage where the speaker talks about the site, `rushStart` = its start
(read in the timeline of the VALIDATED edit, never in the raw clip); one step per idea stated, anchored with
`word` on the word that carries it (captions become useless: the voice speaks); one scenario per tool or passage
(`01-home.json`, `02-search.json`...), each with its own `rushStart`: a failed demo is redone alone, and the
editor keeps independent clips in Premiere. The MP4 lasts from `rushStart` to the last gesture; rendered with
`--rush` it is placed on V2: full screen while the speaker explains, back on them at the end of the clip.

Why the recording works the way it does (double resolution, x4 slow-motion, scroll driven by the capture loop, cursor drawn at render): `references/lessons.md`, "Why the demo is built this way". Do not simplify it.

## Tella-style edit: camera + screen shoot

Input: a screen-recording shoot in separate files, the camera (`cam.mov`, 3840x2160), the screen (`ecran.mov`,
2560x1440), and a control mix (`montage.mov`, for checking only, never edited). Output: a Premiere XML where the
video alternates between four layouts animated by Basic Motion keyframes, fully editable in Premiere. Script:
`scripts/montage-tella.py`.

1. **Rough cut** of `cam.mov` with `rough-cut`. Editing instructions said during the take ("there, zoom on...")
   are separate cuts, noted in `<video folder>/MONTAGE.md`.
2. **Layout plan** `<video folder>/Montage/plan-dispositions.json`, written by the AI from the transcript and the
   screen activity (frames at 5 fps): a list of `{"mot": index in words_premiere, "disposition", "texte",
   "pourquoi"}`. Grammar: `CAM` when talking to people (intro, opinion, conclusion), `COTE` when showing an image
   and commenting on it, `ECRAN` when manipulating (camera thumbnail bottom right), `ZOOM` when pointing at a
   detail; 3 s minimum per shot, at most 4 changes per minute.
3. **Generator**:

```bash
python3 scripts/montage-tella.py --cam <cam.mov> --ecran <ecran.mov> --derush <cam_Derush_v1_work> \
  --plan <plan-dispositions.json> --out <..._Montage_v1.xml> --nom "Montage_v1" \
  [--decalage-ecran auto|0.0333] [--fond papier|nuit|brume|fixe] [--periode 20] \
  [--habillage <Illustration V1.xml>] [--apercu <folder> --instants 72 263 --reduction 2]
```

   It takes exactly the clips of the rough cut, aligns the screen on the camera by voice correlation (`auto`),
   writes background (V1), screen (V2), camera (V3), corners (V4), camera voice (A1-A2), one marker per layout plus
   the rough cut's doubts (named "Doubt": the FCP7 XML carries no color), then passes `garde_premiere` (HIDDEN
   errors ignored: it does not model Basic Motion). `--apercu` recomposes frames from the Premiere parameters
   written: look at the sheet before delivering. **Before the first take**: remeasure at the top of the script
   `FACE` (face in the camera), `CAM_CARTE` (4:5 crop of the thumbnail), `ECRAN_SRC` (screen without the menu bar)
   and `LOUPE` (area of the app where we zoom) on a frame of THE shoot.
4. **Animated background** (default): `FondAnime` composition of the workshop, variants `papier`, `nuit`, `brume`; `--fond fixe` = a fixed dark gradient. Five 4K loops rendered once into `<video folder>/Montage/` (`fond-*`, `ombre-*`, `coins-*`), redone only if the props, `FondAnime.tsx` or the grain change. Details of the loops: `references/lessons.md`, "Tella-style background".
5. **Overlays** (b-rolls, scenes, wipes, sounds): a Python plan `<clip>_Illustration_work/plan.py` that imports
   `montage-tella.py` to know the shots and their layout, and places each overlay according to the layout of the
   moment: over the full-frame camera, at the side opposite the face (measure the free zone on frames of this
   shoot; on a measured case the face was at center right and the right side left only about 530 px, everything
   placed there bit into the forehead); in ECRAN/ZOOM, numeric labels in the right column above the thumbnail
   (caption folded by `labelWidth`) and stamps in the top band, never on the capture; in COTE, in the top band,
   low enough for the "xn" counter; the size of a stamp is computed to fit its zone (width about size x (0.62 x
   letters + 1.12)); never straddling a card movement (`sur()` moves the entrance out of a transition and trims
   the end to the shot; after `habillage.tenue()`, what overflows is trimmed, or removed under `TAMPON_MIN`).
   Then:

```bash
python3 plan.py                                                  # <clip>_animation-script.json (3840x2160) + <clip>_broll-script.json
python3 scripts/render-segments.py <cam.mov> --no-rush --skip-verify   # nice, in the background: scenes rendered at scale 2
python3 scripts/montage-tella.py ... --out <..._Montage_v2.xml> --habillage <Illustration V1.xml> --apercu <folder>
```

   In a 4K sequence, `render-segments` renders a scene designed at 1920x1080 with `--scale=2` (props divided by 2,
   sharp text) and places a 1080p b-roll at Basic Motion 200% (`fit_cover` as soon as the size differs from the
   sequence). `--habillage` places its tracks above (V5 and up, A3 and up): one sequence to import. With
   `--apercu` and no `--instants`: one thumbnail per overlay element composed on the edit, 12 per sheet: look at
   them all. GIFs (`gifs.py`) are placed as elsewhere, on the full-frame camera, on the side opposite the face.
6. **After the editor's pass** (rule zero): their cuts are read in THEIR sequence, `montage-tella.py ... --sequence
   "<name>"` (and `clips_de_sequence()` in `plan.py`): the track that carries the camera, contiguous pieces glued
   then cut again at the rough-cut bounds (two rough-cut clips with no gap in the footage would otherwise stay
   welded, and the 100/112% alternation of the camera would slide from one clip onto all the rest; witness: their
   unchanged sequence gives exactly the rough cut). Then `timeline-from-prproj.py <cam> --sequence "<name>"` for
   the transcript, `plan.py`, render, merge into a NEW sequence (`_Montage_vN+1`). What they added by hand (noise
   reduction, adjustment layer) must be pasted back from their sequence: tell them at delivery.

What cannot be guessed (Basic Motion units, keyframe reference frame, still images, rounded corners, movement curves, screen crop, Premiere 25.6.1 minimum): `references/lessons.md`, "Tella-style edit: what cannot be guessed".

## Optional script formats

`<clip>_broll-script.json` (written by `match-brolls.py`, completed afterwards): `brolls[]` with `id`, `variants`,
`file` (empty = ignored), `timecode` (`"??"` = ignored), `durationSec` (`null` = native duration), `note`.
`inSec` / `outSec` (optional): entry and exit inside the file, to place a passage of a long video without
re-encoding it (the XML points to the delivered file with `<in>` and `pproTicksIn` at `inSec`; without
`durationSec` the duration is `outSec - inSec`); `file` may be an absolute or `~` path outside `Brolls/`, which
must stay there until export. `motion` (optional): `{scale?, cx?, dy?}` free placement in the frame (Basic
Motion): `scale` in % (default fit-cover), `cx` = wanted center in px of the SOURCE, `dy` = vertical offset in
px of the SEQUENCE.

`<clip>_photos-script.json` (written by `match-photos.py`): `defaults.durationSec`, `photos[]` with `file`,
`timecode`, `durationSec`, `enabled`, `note`.

A reel assembled by script straight from the clip: `render-segments.py <clip> --no-rush --skip-verify --script
<folder>/<base>_animation-script.json` (the script may live elsewhere than next to the clip; outputs go in its
folder). Extra script keys: `rush_clips` = `[{in, out, start, scale, cles: [[t_clip, cx], ...]}]`, the pieces of
the clip placed on V1 (clip time; `start` in reel time), reframed to 9:16 by `scale` (177.78 for a 16:9 clip) and
a horizontal centre tracked by keyframes, their sound on A1 and A2; `sequence` = the name of the sequence
imported.
Embedded captions use only plain static fonts: never a font with cut-outs, stencil or scanlines (a variable
font under a text stroke redraws its inner joins and turns stencil, unreadable on a phone); the guard is in the
component code, since cut-outs cannot be measured on the box of the text. Judge on a sheet reduced to 390 px wide.

**FCP7 XML golden rules** (the `<file>` block tells the truth of the media, one `file id` per file, long still-image media, sorted compacted tracks, baked backgrounds in 29.97): `references/lessons.md`, "Premiere and the XML". When in doubt about a new type of clip, have Premiere export a sequence that contains one (File > Export > Final Cut Pro XML) and copy its structure.

## Setting your own look

Colors, fonts, sizes: `../motion-design/src/illustration/theme.ts` (scenes read it), fonts in
`../motion-design/public/fonts/` (see `../motion-design/SKILL.md`, "Setting your own look"). After a change:
`remotion still` on the witness compositions, then `--force` at the next render. Checks for a new component or
plan: no foreign color token, text at least 44 px on 1080p (legible on YouTube), the accent used as a signal and
never as a fill, no em dash in on-screen texts, and always a still render composited on a frame of the clip
before the series:
`cd ../motion-design && npx remotion still src/index.ts Scene out.png --props=props.json --frame=N`.

A look "derived from X" takes the direction of X, not its signature motif (a retro neon look takes the night,
the neon and the grid, not the striped sun): look for a motif of the subject itself. A thematic look starts on the
word that opens the theme, not at the beginning of the chapter that leads to it.

## Machine requirements

See `INSTALL.md` of the kit: Node >= 20, Python 3 (numpy, scipy, soundfile, Pillow, OpenCV, Playwright), ffmpeg
with `prores_ks`, whisper.cpp + `ggml-large-v3-turbo.bin`, Premiere Pro (FCP7 XML import), and macOS for the
head measure (Apple Vision). Optional keys in `.env` (next to this skill, or at the project root): see
`.env.example`.

## Lessons

Read before a first video: [`references/lessons.md`](references/lessons.md).
