# Overlay lessons (learned on real edits)

What follows comes from videos that were really dressed and then finished by hand in Premiere, and from
comparing what the skill delivered with what the editor kept. The scripts already take it into account: this
document says WHY, so that a trap is not reintroduced when the code is touched.

## What was measured

- On a long video (54 photos placed): image selection right at 95%, placement right at about 100%. What the
  editor corrected: photo durations tightened (2 to 5 s instead of a fixed 4 s), 7 photos out of 54 removed,
  lower thirds re-synced (they were synced on the start of the sentence instead of the word said), two book
  covers added, whooshes kept only on covers while a "ding" stayed on lower thirds.
- On a reel edited INSIDE the imported sequence (the pipeline really is used): structure, mattes and lower
  thirds kept, 36 photos out of 50 at the exact positions. Removed: the book covers placed while the speaker
  SHOWS the book to the camera, and the low-resolution images. Stock-footage b-rolls: 2 out of 2 removed.
- On a long video delivered and reviewed marker by marker: the second delivery was imported "as is" (106 clips
  and 95 sounds, nothing removed or moved, only the speaker's own outro sound added). The method of that
  delivery is the reference: marker -> cause -> fix in the tool for the whole video -> new numbered delivery ->
  full chain replayed.

## Timing

1. **Read the frame rate of the clip with `ffprobe` BEFORE writing a plan.** A plan written at 30 fps on a 60 fps
   clip shifts everything by a factor of 2 in Premiere.
2. **Sync on the WORD said, not on the start of the sentence.** A lower third that appears before the name is
   spoken is noticed ("announcement before the sound"). The plan is synced on phrase anchors of the transcript
   (`habillage.py`); a proper name may start about 0.5 s before the word.
3. **Cross the script with the transcript.** The transcript gives times to the word, the script gives the right
   spelling: speech recognition mangles rare proper names (a "Sontag" becomes "Suzanne Sontag", a "Halpern"
   becomes "Alperne"). Look each script name up in the transcript by similarity, then REREAD: the approximate
   search sometimes takes a late mention (end of a chapter) instead of the first.
4. **Sync on what is SAID, not on what was written.** The shot video is often shorter than the script: a passage
   of the script may not exist in the clip.
5. **A name and its work less than 10 s apart = a single lower third** (the title of the work as a subline),
   never two stacked.
6. **A strong sentence said by the speaker on screen**: full-screen quote WITHOUT signature, their voice is enough.
7. **A density that works for editorial video**: one overlay every 45 to 75 s, outside the intro and the
   conclusion (13 overlays over 12 useful minutes read as one every 55 s).
8. **Whisper dates words early (about 170 ms), constantly**: judge drift, not the absolute gap. Measure a true word
   start by the energy rise after the end of the previous word.

## Editorial rules (editing feedback)

- Never a full-screen image while the speaker shows an object to the camera (book, camera, print): the image
  would hide the demonstration. Spot "here", "look", "as you have there" in the transcript.
- A supporting photo lasts 2 to 5 s, not a fixed duration; in a reel 2 to 3 s.
- An image under 800 px wide is flagged by `render-segments.py` (LOW RES): replace it before delivering rather
  than leaving it enlarged.
- Visually check EVERY image chosen on the strength of a title or a domain (thumbnail, then look): a "portrait"
  can be a work, a caption can describe another photo.
- Stock b-rolls get removed almost every time: place them only on request.
- A deviation from the script said on camera (a figure, a term) is corrected on screen, not by a retake.
- A "look derived from X" takes the direction of X, not its signature motif.
- Never iterate on a video already finished by hand: a remaining error is fixed on the next video, where the
  deliverable is really needed.
- Diagrams use the speaker's own words, reread in the transcript; a paraphrase put a profile on the wrong level
  of a funnel.
- A cover shown by a scene is the publisher's visual taken from the web, never an image extracted from the
  speaker's footage.

## Premiere and the XML (FCP7)

1. **The `<file>` block tells the truth of the media**: real rate, real frame count, real dimensions (ffprobe, or
   reading the image). A `<file>` that lies (the sequence's rate instead of the media's, the placed duration
   instead of the file's) gives a right thumbnail then BLACK when the playhead passes: Premiere conforms the
   media on the wrong values. True for videos AND stills.
2. **One `file id` = one file = one definition.** Full definition at the first occurrence, then a bare
   `<file id="..."/>`. An id redefined at each use, or truncated (two different files with the same id), makes
   sounds or images disappear on click. Ids come from a hash of the path.
3. **Still image**: long media duration (`max(36000, n x 10)` frames, also in `file/media/video/duration`), `in`
   shifted far from the bounds (3600), `out = in + n`, `alphatype none`, square pixels. With `in=0 / out=n /
   duration=n` the playhead hits the end of the media and the image flickers or vanishes. Canonical spec used
   by the tella script: clipitem `duration=1080000`, rate 25 NDF, `in=90000`; file rate 30 NTSC with timecode and
   real dimensions WITHOUT `<duration>`; plus Basic Motion with four parameters (contain scale, rotation,
   center, anchor).
4. **No `.webp`**: Premiere reads it as zero-length media. Convert to JPEG first. (Native import by hand works;
   the ban applies to the XML / manifest pipeline.)
5. **29.97 sequence**: n sequence frames last n x 1.001 / 30 s. A render that does not cover its whole clip leaves
   a black frame at the end: `render-segments.py` computes `tailFrames` (the last frame is held). A clip of a
   29.97 media is written with `in = round(t x fps x 1000/1001)` and `<ntsc>TRUE`: counting it as exactly 30
   shifts it by up to more than a frame, and a zoom ends up on a moment where the speaker is not talking.
   `garde_premiere.py` refuses such XML (CADENCE, CALAGE rules).
6. **Clips sorted per track.** Premiere reads the clips of a track in file order and uses it as an index: a clip
   out of order becomes a ghost (visible on the timeline, absent on playback, jumps when zooming). `build_xml`
   sorts, `garde_premiere.py` refuses to write otherwise.
7. **No empty track** in the delivered XML: tracks follow each other (clip, b-rolls and mattes, photos, premiums,
   lower thirds).
8. **The reference is Premiere itself.** For a new type of clip, export a hand-corrected sequence with "File >
   Export > Final Cut Pro XML" and copy its structure (round trip) rather than writing the XML from memory.
9. **Mattes**: a native color generator (`generatoritem` Color) in a 60 fps-type sequence. In a **29.97
   sequence generated mattes do not display, in any form** (generator, hand-made white still, still from the
   photo pipeline): the clip is sound in the project but nothing shows and it disappears from the timeline
   depending on zoom. In 29.97, bake the white into the images (centered padding at W = 1920 / (scale/100), H =
   1080 / (scale/100) for each photo; the contain scale on the clip stays valid; overwrite the files, same names,
   Premiere reloads them) and emit no matte track.
10. **Sequence already imported and worked on**: never ask for a reimport. Sort the tracks of the `.prproj`
    itself (`reparer-projet.py`, project closed) and prove that the canonical form (XML canonicalization) differs
    only by the order of the `TrackItem` elements.
11. **Photos placed by Premiere's own "Automate to Sequence"** (when the XML route is not enough): XML sequence
    markers are NOT counted as "unnumbered" markers (the option stays gray), so they must be set by hand
    (timecode field, type the time, Enter, M, with a 0.5 s pause between actions); photos copied with a
    chronological prefix `P01-...` and imported in a dedicated bin; lock the tracks to protect, patch the source
    track, playhead at 0 (only markers at or after the playhead count); tri = sort order, position = at unnumbered
    markers, method = overwrite. Never purge a bin by search plus select-all (search matches invisible fields
    such as paths).

## Proof scenes (emails, pages, screenshots)

- Never a line cut at the edges: each step of a `preuve` carries a `vue` (plan computes it: for an email the
  whole text column of the band of marked lines, measured on pixels; for a web page the element containing the
  phrase).
- A document does not stay in wide shot more than about 4 s: first step on the phrase that introduces it (no
  mark), then the marks; otherwise a note or stamp on the phrase said.
- Notes have their banner at the top left (71 px per note): the wide shot puts the document below it, the close
  shot frames each view under it, and a paper fade (close shot only, emails and web pages) wipes what rises
  under it. Before the banner, 12 proofs out of 15 had a note on text once zoomed, invisible on sheets (they
  only show joins): `qc-preuves.py` replays the camera.
- The framing counts everything drawn: the mark of the step (a frame overflows by 26 px, a highlight by 10) and
  the marks of earlier steps still on screen, with 60 px of margin (`Paper` grows about 1% during the scene). On
  an email the plan's `vue` widens to all VISIBLE text once the camera is set (three passes). On a web page, a
  neighboring column cut at the edge is accepted (widening it would bring the text down to 13 px).
- A mark of an earlier step half in the field (an underline of a title at the very top, a frame of a paragraph cut
  at the bottom): `viser()` moves the camera to bring it out of the field if the view of the step still holds,
  otherwise brings it in whole (margin 36 px = 24 + the drift of the paper). `qc-preuves` counts any visible
  mark, even cut; `--trace` lists the steps whose camera moved for that; `--avant-sortie` replays the old camera.
- A screenshot is placed like a photo (`photo()` of the plan) with a `zoomMax` to read its text, but the paper
  must fit in width (zoom up to about 1,860 px of paper): its caption is aligned left; a tall narrow capture can
  zoom more.
- `bords` also sees the red of a document (a video site's logo at the edge of a zoomed page): check the image
  before correcting, it is not always a mark.
- Everything anchored on the right is anchored BY THE RIGHT (`right`), never `left: 1300`; a timeline keeps 190
  px of margin on each side.
- Non-breaking spaces before " ? ! :" and inside quotes in ALL scene texts (`insecables()` of the plan); a lone
  quote mark at the start of a line has been seen twice.
- `stat`: `site: false` removes the address, `check: false` the ticks of the notes.
- Crop web pages around the phrases used (JPEG of 1,000 CSS px): a full page is 3840 x 21,800 px and 6 MB as PNG,
  the crop 0.2 to 0.9 MB; check on a sheet that no crop shows a forbidden thumbnail (a child, a cover).
- A screenshot the user pasted in an earlier conversation is in that conversation's history
  (`~/.claude/projects/*/*.jsonl`, base64 image): look there before asking again.
- Emails: where to take the text, if the mailbox is open in a browser: the page's global data gives the account
  key `ik`, then a `fetch` of the "original message" view for the message id; the MIME is in the raw-message
  `<pre>`; decode in JS (quoted-printable or base64, split on the REAL `boundary=` lines, not on any line
  starting with `--`) and return only the first message.

## Why the demo is built this way

- **Capture at double resolution** (2880 x 1620): otherwise zooms are blurry. The DevTools video stream is capped
  at CSS resolution (1440 px), hence the framed capture at scale 2, which only holds about 20 frames/s.
- **Hence the slow-motion x4**: gestures, scrolls, typing, waits and CSS animations are slowed, timestamps divided:
  about 60-80 usable frames/s. Identical frames (static page) are merged: a "hole" at the start or end of a scroll
  is not a stutter.
- **Scroll driven by the capture loop**: position set, then a capture framed on that position, no tremble.
- **Cursor drawn at render** (headless Chromium has none): smoothed, tilted with speed, enlarged, pressed on click
  with an accent wave.
- **Camera precomputed as critical springs**, smoothed in coordinates relative to the frameable zone: never
  background visible at full zoom, no jolt when a zoom starts.
- **`--rush` takes the exact rate and size of the clip** (29.97 included; 4K = Remotion render with `--scale=2`):
  a 1080p placed in a 4K sequence fills a quarter of the picture, a 30.00 in a 29.97 sequence drifts.
- Review feedback that shaped the camera: "it clicks everywhere a bit fast, it zooms, un-zooms, changes zone,
  zooms again, where it could just glide". A scenario never has an on/off click at each word of a filter list.

## Tella-style background

`FondAnime` composition: variants `papier` (light, soft blotches, a bundle of fine undulating lines two of which
in the accent, grain), `nuit`, `brume`; `--fond fixe` reverts to a fixed dark gradient. A seamless loop of
`--periode` s: everything is a function of theta = 2 pi frame / n, integer harmonics. Five 4K renders in
`<video folder>/Montage/`, redone only if the props, `FondAnime.tsx` or the grain change (`Montage/fonds.json`):
- `fond-<v>.mp4` (about 40 MB, h264 crf 16): V1 during motion and under the full-frame camera;
- `ombre-ecran-<v>.mp4`, `ombre-cote-<v>.mp4`: the same background + the drop shadow of the cards, V1 during
  still shots;
- `coins-ecran-<v>.mov`, `coins-cote-<v>.mov` (ProRes 4444, about 90 MB): the "shadow" render reduced to the
  corners outside the rounding, transparent elsewhere, V4 during still shots: they are what rounds the cards.
All loops are placed in phase (entry point = clip start modulo the period, clip cut at every turn): going from
`fond` to `ombre` makes no jump. A full-frame background with shadow and alpha weighed 1.2 GB per loop, hence the
split into opaque (V1) + corners (V4). The grain (`public/fond/grain.png`) is made at the first render by
`motion-design/scripts/make-grain.py`.

## Tella-style edit: what cannot be guessed

- **Basic Motion units**, calibrated on a real export: `center.horiz = (Px - W_seq/2) / source width`, `vert = (Py
  - H_seq/2) / source height` (negative upward), `scale` in %, `leftcrop...bottomcrop` in % of the source in the
  same effect.
- **Reference frame of the `<when>` elements not proven** (clip, media or sequence): each keyframe is written in
  the three disjoint ranges; only the right one falls inside the clip. Simplify as soon as a `.prproj` re-saved
  after import shows which one Premiere reads.
- **Still images** (background, frames) in the canonical format of `render-segments` (rate 25, in 90000): never
  keyframes on them.
- **Rounded corners and shadow**: over the cards during still shots only (loop `coins` on V4, or a "holed" PNG with
  `--fond fixe`); during a transition they are removed (the cards move).
- **Movement**: `cubic-bezier(0.42,0,0.58,1)` over 12 frames (15 if the full-frame camera is involved), spring
  (2.25 / 200 / 40) over 19 frames between ECRAN and ZOOM, transition started 8 frames before the phrase; one
  keyframe per frame during the transition.
- **Screen**: the macOS menu bar and title bar are removed (`ECRAN_SRC`); zoom zone = the area measured for the
  app (`LOUPE`), to adapt if the window changes.
- **Overlay placement by layout** (table `POS` in a plan): on the full-frame camera, on the side opposite the
  face (measure it on frames of the shoot: in one case the face sat at center right and only about 530 px were
  left on the right, everything placed there bit into the forehead); in ECRAN/ZOOM, numeric labels in the right
  column above the thumbnail (caption folded by `labelWidth`), stamps in the top band above the cards, never on
  the capture; in COTE, in the top band low enough for the "xn" counter; stamp size computed to fit its zone
  (width about size x (0.62 x letters + 1.12)); never straddling a card movement.
- Premiere 25.6.1 minimum (2025 bug: motion lost on XML import).

## Reel and long-video details

- Vertical: the lower third detects `height > width` and moves up (a margin of 48 px on each side, bottom raised
  above the caption zone, title smaller); photos stay contain on the white matte (a landscape photo becomes a
  band, that is intended); b-rolls are fit-COVER (scale = max(W/w, H/h) x 100, applied when the aspect ratios
  differ by more than 0.05).
- Photos of a reel: durations 2 to 3 s; lower third as long as its portrait photo; no stock b-roll; LOW RES
  under 800 px listed to the user before delivery.
- Embedded reel captions: plain static fonts only; the guard is in the component (an unknown key falls back to
  the default font).
- A long video's book-showing moments: framing zoom on the speaker's camera (130%, centre moved toward the book
  within the frame limits, back to 100% when lowered), nothing over it; the plan stops if a framing falls under
  an element or straddles one of the editor's cuts.
- Two b-rolls end to end, each rounded to the frame, left one frame of face between them: `render-segments` holds
  the first until the second when 1 or 2 frames separate them, and the plan rounds the END of a b-roll, not its
  duration. A b-roll or scene at the end of a block loses about 0.25 s under each wipe: to pass the `tenue` check
  place at least 3.05 s for a b-roll alone between two wipes.
- Scenes that share a file (same id: the wipes) are rendered once, animation of the shortest, last frame held to
  the longest; before, the cache key changed from one wipe to the next and the same file was rendered four times.
- `mots` check: windows of 30 s and three whisper passes shifted by 0.4 s each; on 12 s the median of a window
  varied by +-400 ms from one pass to the next while `derive` measured the voice to within 1 ms.
- A scene lengthened to be readable must not hide the footage that starts later: `tenue()` also bounds by the
  start of the b-rolls and the demos (rule MASKED of `garde_premiere.py`).

## Tools

- Always a `timeout=` on calls to ffmpeg: a valid PNG once made `ffmpeg -loop 1` loop at 100% CPU for 20 minutes.
  A faulty file rewritten as JPEG = fixed.
- Sound effects stay on separate audio tracks (A3, A4), never baked into the renders: the editor can move or mute
  them.
- Check an overlay on a real frame of the clip (ffmpeg composite), not on an empty background.
- The preview is a checking tool, not a deliverable.
- While a sync service is watching the video folder, write in it only the deliverables, each once; a file
  deleted while it is being uploaded makes the sync round fail. Scratch files go in a non-synced folder of the
  same disk (`MONTAGE_DEPOT`), a deliverable enters the folder by `mv`.
