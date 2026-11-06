# Default sound palette

The sound effects of the animations come from a palette written once, in code, and reused on every video:
same material, same key, same levels. It is a **default** palette: its direction (a muted workshop, mechanical
and paper) can be kept or replaced, the method stays.

Three files carry the system:

| What | Where | Role |
|---|---|---|
| Direction | this document | why, and what is forbidden |
| Synth recipes | `scripts/make-sfx.py` | builds the sounds (`public/sfx/*.wav`, `palette.json`) |
| Vocabulary | `scripts/son.py` | which sound for which gesture; a video's plan only calls it |

Everything is synthesized: no samples, no rights, same code = same files. That is also its limit: a synthesized
sound that has a pitch sounds like one ("cheap, thin", feedback from a kit user). Unpitched sounds (paper,
mechanics) work better. For real recordings, see "A palette of real recordings" below: the plans do not change.

## The idea

The sound tells the same thing as the picture. Nothing that sounds like a "mobile app" or a "movie trailer".

**Three materials, and only three.**

- **The keyboard** (a muted electric piano): it carries INFORMATION. An element appears, a list unrolls, a question is asked, a message arrives. It is the only material with a note pitch.
- **The camera body** (mechanics: shutter, focus tick, ring clicks, lever, keys): it carries the GESTURE of aiming. Framing, locking, counting, firing, clicking.
- **The paper** (stamp, a label set down, a sheet that slides, a page turned): it carries the MATTER of the screen. Everything that is set down, stamped, comes in or goes out.

**One key.** C major pentatonic (C D E G A): no note rubs against another, and a piece of music in D dorian (the same set of notes, `music/example_pad.py`) runs underneath without dissonance. Nothing is out of the scale, except the "problem" note, which falls a semitone on purpose.

**One room.** Every sound goes through the same short reverb (0.5 s, damped at 3.5 kHz), the same low-pass at 9 kHz (no harsh highs) and the same high-pass: you hear a single room.

**The voice in front.** Each file is written at its final level, measured against a reference voice (`VOIX_REF` in `make-sfx.py`: -22, the 9th decile of the K-weighted level over 100 ms windows, measured on voices from finished videos). Three roles:

| Role | Level | Sounds |
|---|---|---|
| accent | voice - 4 dB | stamp, shutter, signature |
| info | voice - 9 dB | notes, chord, question, message, focus tick, label |
| texture | voice - 14 dB | ring clicks, typing, click, sheet, page, zoom whoosh, line, pop, set-down |

Placed at 0 dB in Premiere, a palette sound is therefore in its place. If a video's voice is louder or quieter than the reference, move the sound-effect tracks by the same amount, all together (they sit on their own tracks: A3, A4). `python3 scripts/make-sfx.py --voix <file>` gives the measurement; to adopt YOUR voice as the reference, put that measurement in `VOIX_REF` and rerun `make-sfx.py`.

## The grammar

1. **One sound = one visible movement.** No sound without something moving, no important movement without a sound. The sound lands on the word, like the picture.
2. **Lists do not sing** (default setting, `son.LISTES = "objets"`): one placed card per item, two variants alternating. A note that climbs with each item (`son.LISTES = "notes"`: C, E, G, the last one resolves) is the sound most often rejected on listening, by a kit user ("the notes concept is useless") as well as by learners of video courses (endless "ding-ding" is unbearable).
3. **Question, answer.** A question card plays stacked fifths, with no third: it hangs in the air. The chapter card that follows sets down the C bass: it resolves.
4. **Chapters climb.** The "N of total" card plays a note that rises one degree with each chapter; the last one lands on the high C.
5. **Arm, then fire.** A reveal: the lever 0.4 s before, the shutter on the beat. A counter: the ring clicks slowing down, then the shutter when the number lands.
6. **The stamp is rare and strong.** The only paper accent. Three variants rotate, never the same one twice in a row.
7. **The signature** (release + a chord that opens): once to three times per video, no more (the promise at the start, the end card).
8. **Transitions are paper.** A wipe = a sheet that slides, peak on the cut. Two full-screen scenes in a row = a page turned.
9. **Site demos stay discreet.** Click, keys, page change, tick on the highlighted element, all at the "texture" level: the voice already tells the story.
10. **Silence is a sound.** Talking-head footage has no sound effects. No more than about fifteen sounds per 30 s slice, gags aside.
11. **One success sound, at the end.** No `son.valide` ("it is validated") on a title or a number that appears mid-video: the very idea of a validation sound sounds "cheap". Its only place: the call to action of the very last frame.
12. **Nothing on the announcement of a problem.** Tested against a dull thud and a soft hum, silence won: `son.souci` exists, use it rarely.

Rules 2, 11 and 12 rest on one user's feedback (three voice-over reels) and on learners' complaints about video courses. Treat them as defaults to test by ear, not as laws. Density is a separate question. A reel watched without effort tolerated about 25 sounds per minute once the three families above were removed. A video that teaches (a course) finds the same density irritating, since attention is already taken: aim for one sound per new screen, plus the structure.

**Timing.** Every sound lands 2 frames (67 ms) AFTER the visual instant (`son.CALAGE`): a sound that is early is noticed from 45 ms, a late one only from 125 ms (ITU BT.1359). Placed exactly on the first visible frame, sounds seem early. A sound that accompanies a movement (zoom, arrow) follows the REAL curve of the animation (`EASING` in `make-sfx.py`, the same as `easeStd` in the scenes): its clicks fall at equal steps of travel, the whoosh peaks with the speed.

## Forbidden

- Synth swells, trailer-style risers, movie impacts, notification "dings", phone interface sounds. Exception: a LIGHT puff of air under a zoom, timed on the movement's curve, never a riser.
- Continuous background music under a long talking-head video (music under an animation voice-over, yes).
- A pitched sound out of the scale, a file chosen "by ear at the moment" in a plan: if a gesture is missing, add it to `son.py` (and to the synth recipes if a new sound is needed).
- A volume set by hand in a plan: levels are in the files. `d=` is for nuance (-4 in a cascade), not for catching up.

Gags (a rubber duck `canard.wav`, a sound meme) are outside the palette on purpose: they break the pattern. Rare, at the "accent" level.

## The vocabulary (`scripts/son.py`)

| Gesture on screen | Call | What you hear |
|---|---|---|
| an element appears | `son.note(t)` | a note |
| elements arrive one by one | `son.liste([t1, t2, ...])` | one placed card per element (`LISTES = "notes"`: the scale climbing, resolved ending) |
| a grid fills at once | `son.cascade(t, n)` | the sheet slides, the last tile is set down ("notes": a fast run up to the high C) |
| check mark, answer, "it is settled" | `son.valide(t)` | C major (one per video, at the end: grammar 11) |
| question card | `son.question(t)` | suspended chord + focus tick |
| chapter card | `son.chapitre(t, n, total)` | page, C bass, the chapter's note, tick |
| message, mail | `son.notif(t)` | G then C |
| a problem | `son.souci(t)` | low note that falls (often better: nothing, grammar 12) |
| opening, end | `son.signature(t)` | release + chord |
| a number counts up | `son.compteur(t, duration)` | ring clicks, then shutter |
| a reveal | `son.revele(t)` | lever, shutter |
| focus frame, highlight | `son.af(t)` | double tick |
| capture, hard cut | `son.obturateur(t)` | shutter |
| stamp | `son.tampon(t, k)` | stamp (variant k) |
| a word that slams | `son.claque(t, k, fort=...)` | label set down; stamp if emphasized |
| side card comes in | `son.carte(t)` | sheet slides, then lands |
| bubble, label | `son.pose(t, k)` | set-down |
| something slides | `son.glisse(t)` | sheet |
| next scene | `son.page(t)` | page |
| wipes | `son.volet_in(t)`, `son.volet_out(t)` | sheet, one way then the other |
| an address is typed | `son.frappe(t)` | keyboard |
| click in a demo | `son.clic(t)` | mouse |
| the camera moves, zooms | `son.zoom(t, "in"\|"out"\|"pan", duree=)` | light whoosh + ring clicks timed on the curve |
| an arrow, a line is drawn | `son.trait(t, pointille=...)` | paper rub + tick on the tip |
| a support image fades in | `son.appui(fade_start)` | very light pop |
| views arrive one after another | `son.vues([t1, t2, ...])` | one placed card per view ("notes": a pop per view, the scale climbs) |

Each call returns a list of `(file, instant, dB)` to add into a scene's `sfx` key. `son.controle()` flags a scene that is too busy or a missing file. `son.DECALAGE` shifts a whole video at once (voice louder or quieter than the reference).

`son.pose` and `son.tampon` rotate through every take the palette holds (`pose-1.wav`, `pose-2.wav`, `pose-3.wav`...): never the same file twice in a row.

Outside scenes (defaults of `render-segments.py`): lower third = `pose-1.wav`, section title and cover = `page.wav`, full-screen quote = `accord.wav`. Site demos write their own sounds (`<demo>.sons.json`, by `screencast-render.py`).

## Have a human ear validate it

**Claude picks the sounds without hearing them.** It places a sound from its description; only the person who listens can say it lands badly. Anything that shortens their answer is worth more than a better choice by Claude:

- **The review list**: every pass of `render-segments.py` writes `sons-<video>.md` (and `.json`) next to the XML: each sound numbered, its instant, the scene and its text, the words spoken at that moment, the file, its role and its level (`son.releve`, which a motion-design plan can call too). The person answers by number ("remove: 3, 17 to 19"); look for what the removed sounds have in common and fix the FAMILY of gestures in the plan, not one sound at a time.
- **A/B/C excerpts**: for a doubtful family, do not debate. The plan takes one option (for example lists as cards, as bubbles or silent), only the mix is redone, and the track is put back on 10 to 15 s of the already rendered video (`ffmpeg -i video.mp4 -i mix-B.wav -map 0:v -map 1:a -c:v copy ...`): three variants in a minute, with no new picture render.
- **Sorting by deletion**: to choose timbres, one folder per family, two takes per sound; the person listens in the Finder and deletes what they do not like. A missing file is a refusal.
- **Two steps**: first the timbre, alone; then its place in the video. A sound kept when heard alone can be refused once placed on the picture.

## A palette of real recordings

A palette = a subfolder of `public/sfx/` with the same file names as the default palette; a sound it lacks comes from the default. `scripts/palette-import.py` builds it from any recordings (a sound library, home takes):

```bash
python3 scripts/palette-import.py --modele mapping.json   # every default sound, its role, empty source
# fill in "sons": {"pose-1.wav": ["cards/card-down-1.wav", "info"], "tampon-1.wav": ["paper/stamp.flac", "accent"], ...}
python3 scripts/palette-import.py mapping.json             # -> public/sfx/<palette>/
```

Each recording becomes mono 48 kHz, loses its leading and trailing silence (the attack lands on the frame) and takes its role's level. One more take (`pose-3.wav`, `tampon-4.wav`) joins the rotation. Changing a sound = changing a line and rerunning. In the plan: `son.palette("<palette>")`.

What worked for one user: **real objects**, recorded close, dry, with no pitch (cloth sliding, a page turned, a cork, a bubble, a stamp on paper, a card set down on a table, a mouse click, a scroll-wheel notch, a switch, a film camera shutter, a laptop keyboard, a mixing-desk fader). When a note is needed: a real recorded instrument (a muted piano, string pizzicato with celesta, guitar harmonics), rarely. Rejected almost every time: little bell, glockenspiel, kalimba, marimba, woodblock, confirmation "ding", chime, chords, pads, sparkles, risers, filter sweeps, reversed sounds.

**Rights**: a sound mixed into a video and a sound file redistributed are not under the same license. CC0 allows everything; many "royalty-free" libraries allow use in a video but forbid handing out the raw files. Read each library's license.

**Levels**: a short real sound effect (stamp, shutter) brought to its role's level has a much higher peak than a synthesized sound. `palette-import.py` caps each sound's peak at -9 dBFS (`--plafond`), even if that leaves it under its target, and `mix.py` limits the TRUE peak of the mix to -1.5 dBTP.

## Add or tweak a sound

1. The function in `make-sfx.py`, filed under its material; register it in `palette()` with its role. Pitched: a note of the scale. Noise: no resonant filter sweep.
2. `python3 scripts/make-sfx.py` (everything is regenerated, levels recomputed).
3. Measure before listening: pitch (spectrum peak), useful duration, level. A sound you cannot judge by ear is judged by its spectrum.
4. The gesture in `son.py`, the line in the table above.
5. `python3 scripts/make-sfx.py --planche sheet.mp4 [--voix clip.mov]`: a listening sheet (each sound, its name on screen, then typical phrases under the voice) to play to the person who decides. Their listening feedback comes first: note it here, with the date.

## Change direction

For another sound color: change `GAMME` (another scale without friction), the reverb (`_ir`), the material functions in `make-sfx.py`, then regenerate. The video plans do not change: they name gestures, not files.
