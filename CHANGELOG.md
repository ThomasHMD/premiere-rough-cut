# Changelog

## 2.0.0

- **The kit is now in English**: docs, scripts, messages, reports and on-screen default strings. Neutral and MIT licensed.
- **Claude Code plugin**: `/plugin marketplace add ThomasHMD/premiere-rough-cut`, then `/plugin install premiere-rough-cut@premiere-rough-cut`, then one setup line (`bash "${CLAUDE_PLUGIN_ROOT}/install.sh" --data "${CLAUDE_PLUGIN_DATA}"`). The manual install still works. `install.sh` takes `--data`, `--dest` and `--check`.
- **Skills renamed.** If you had 1.x, replace the old folders:

  | 1.x | 2.0.0 |
  |---|---|
  | `premiere-derush` | `rough-cut` |
  | `illustration-video` | `overlays` |
  | `motion-design` | `motion-design` (unchanged) |
  | (none) | `subtitles` (new) |

- **New skill `subtitles`** (the former premiere-sous-titres): fixes Premiere's caption JSON with a local whisper pass, the script for proper nouns, and forced alignment for timings; the result re-imports as is.
- **Language files**: `rough-cut` and `subtitles` read `languages/<code>.json` (fillers, false-start phrases, whisper hallucinations, typography). Choose with `--lang`, else the transcript's language, else `en`. French was tested on real videos; English is written from the same rules and still needs confirmation on a real English clip. Contributions for other languages are welcome.
- **New overlay checks**: `controle-texte.py` (on-screen text), `montre.py` (look at the result), `zone_libre.py` (free zones of the frame).
- **New scenes**: `matrix`, `murs`, `offre`.
- `install.sh` rewritten: also checks fonttools, opencv-python and the `subtitles` packages (ctc-forced-aligner, torch, torchaudio, unidecode), and finishes with a test render.

## 1.2.0

Sounds, from a user's feedback on three voice-over reels and from viewers' complaints about video courses.

- **New: sound list.** Every `render-segments.py` run writes `sons-<video>.md` (and `.json`) next to the XML: each sound numbered, its time, the scene and its text, the words spoken at that moment, the file, the role, the level. The user answers by number ("remove 3, 17 to 19").
- **New: palette of real recordings** (`motion-design/scripts/palette-import.py`): a mapping file says which recording plays for which expected file name, with its role; the script builds `public/sfx/<palette>/` (mono 48 kHz, head silence trimmed, role level, peak capped at -9 dBFS). A missing sound falls back to the default palette. `--modele` writes an empty mapping.
- **Lists without a scale by default**: `son.liste`, `son.vues` and `son.cascade` place one card per item (alternating variants); the rising scale stays available (`son.LISTES = "notes"`).
- `mix.py`: true-peak limiter (4x oversampled, -1.5 dBTP), only when the peak exceeds it; a mix above -1 dBTP is refused (code 1). No more temporary file next to the output.
- `palette-sonore.md`: three defaults (no approval sound mid-video, no sound on a problem announcement, lists without a scale), how to have the ear approve sounds, what works with real recordings, rights.
- `AGENTS.md`: Claude picks sounds without hearing them, and what shortens the user's answer.
- `install.sh`: detects a python.org Python without certificates and offers to run its `Install Certificates.command`.

## 1.1.0

- **New: Tella-style edit** of an OBS shoot with cam and screen recorded apart (`montage-tella.py`): four layouts animated with Basic Motion keyframes, screen synced to the cam by voice, rough-cut cuts, overlays on top in the same sequence, check sheet.
- **New: animated background** `FondAnime`: seamless 4K loop in three variants (`papier`, `nuit`, `brume`), card shadows and rounded corners rendered apart; grain made by `scripts/make-grain.py`.
- GIFs: one staple of the overlays (one every 2 to 4 min, on mood or self-mockery), plus an option.
- 4K sequences: scenes render at scale 2 (sharp text); a b-roll of another size is scaled to the sequence.
- `habillage.py`: an overlay stops at the cut of the next full-screen block.
- `garde_premiere.py`: a filmed shot's live sound is no longer taken for a sound effect under a card.
- Scenes: better typography, balanced two-line titles, collapsible caption (`labelWidth`), custom address in the URL bar (`url`), giant numbers sized by length, stamp ring no longer overflows.
- Theme: Inter as fallback for Source Serif.
- Fixed: hard-coded accent colors in highlights of proof and demo scenes now follow the kit's accent.
- Render: concurrency as a percentage of cores (`"85%"`).
- `mix.py`: without `--music`, direct voice mix (much faster). `silence_cuts.py`: cut bounded to the audio when the video outlasts the sound. `hear.py`: help shown without arguments.
- `son.py`: several palettes possible (one subfolder of `public/sfx/` each, `son.palette("<name>")`).

## 1.0.0

First distributed version.

- **premiere-derush**: rough cut by take selection (Premiere transcript read from the `.prproj`, realigned on the audio, cross-checked with whisper.cpp and the script), silence cuts calibrated on finished edits, already-edited Premiere XML (FCP7), end-to-end checks.
- **illustration-video**: timeline read from the `.prproj` after human correction, plan in sentence anchors, animated scenes, lower thirds, quotes, photos, b-rolls, GIFs, mail cards and screenshots, driven site demos, Premiere XML on separate tracks, QC chain, project-write guard.
- **motion-design**: Remotion 4.0.529 workshop (scene catalog, lower thirds, demos), centralized neutral theme (`theme.ts`), free fonts (Inter, Source Serif 4), synthesized sound palette, example synth and score, EBU R128 mix.
- Examples: `plan-example.py` (overlay plan), `screencast-exemple.json` (demo on a Wikipedia page).
