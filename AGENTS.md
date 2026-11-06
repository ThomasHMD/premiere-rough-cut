# Video editing kit for Claude

> **This file is for the AI (Claude Code) that will install and use this kit.** The human who gave it to
> you shoots talking-head videos and wants you to do the rough cut, the subtitle fix, then the overlays
> (animations, sounds, site demos, GIFs, photos), delivered into Premiere Pro. Read this file in full,
> then `INSTALL.md`, then `WORKFLOW.md`, before proposing anything.

## What the kit does

Four Claude Code skills that work together:

| Skill | Role | Input | Output |
|---|---|---|---|
| `rough-cut` | removes retakes, false starts, stumbles and long silences | the clip + the Premiere project (transcript done) + the script if possible | an already-edited Premiere XML (`<clip>_Derush_v1.xml`) + a report |
| `subtitles` | fixes Premiere's caption JSON: a local whisper pass, the script for proper nouns, forced alignment for timings | the caption JSON exported from Premiere + the video + the script if possible | a corrected JSON, re-importable as is |
| `overlays` | PLACES and EDITS the graphics, word-synced on the voice | the sequence approved by the user in the `.prproj` | a Premiere XML with scenes, lower thirds, photos, GIFs, site demos and sound effects on their own tracks; or a Tella-style edit of an OBS cam + screen shoot |
| `motion-design` | the WORKSHOP: renders everything that moves or makes a sound | called by `overlays`, or alone for a fully animated video | Remotion renders (alpha MOV, MP4), synthesized sounds, music, mix |

Everything runs locally: animation in code (Remotion, React), sounds and music synthesized in Python,
local transcription (whisper.cpp). No AI-generated image or video, no subscription. Only two optional
keys (image search, GIF search).

**Remotion license, to check with the user**: Remotion is free for an individual, a nonprofit or a company
of 3 employees or fewer; beyond that, a company license is required (remotion.pro). Its terms also forbid
reselling Remotion itself or a derivative. The other pieces are free (whisper.cpp MIT, OFL fonts,
Playwright Apache 2.0). The kit itself is MIT licensed.

## The principle that makes it work

Two transcriptions, cross-checked:

- **Premiere** (Text panel > Transcribe): keeps EVERYTHING that was said, retakes and stumbles included, with accurate word starts. This is the **timing**.
- **whisper.cpp**: cleaner text, but it merges repeated sentences (its decoder takes a retake for a hallucination). This is the **second opinion on the words**.

Premiere gives the right moment, whisper and the script give the right words. With both, you know what
was said, where and when: you can cut (rough cut), fix the captions, then add graphics to the exact word.

## Install the skills

Two ways. Pick one with the user.

1. **As a Claude Code plugin** (recommended):
   ```
   /plugin marketplace add ThomasHMD/premiere-rough-cut
   /plugin install premiere-rough-cut@premiere-rough-cut
   ```
   then run the setup line once: `bash "${CLAUDE_PLUGIN_ROOT}/install.sh" --data "${CLAUDE_PLUGIN_DATA}"`
   (Claude Code replaces both variables with real paths). The skills are then invoked as
   `/premiere-rough-cut:rough-cut`, `/premiere-rough-cut:subtitles`, `/premiere-rough-cut:overlays` and
   `/premiere-rough-cut:motion-design`.
2. **By hand**: copy the four folders of `skills/` **side by side** into the user's skills folder:
   `~/.claude/skills/` (all sessions) or `<their project>/.claude/skills/` (one project). They must stay
   neighbors: `overlays` finds the workshop at `../motion-design`. Then run `bash install.sh` from the kit root.

`install.sh` checks the machine, installs what is missing (it asks first), downloads the whisper model,
runs `npm ci` in the workshop and renders a test still. Details and the manual route: `INSTALL.md`.

Check: the last step of `install.sh` must render an image (a lower third on a transparent background).

## Before the first video: personalize

The kit ships **neutral**: blue accent `#2F5BEA`, Inter and Source Serif 4 fonts, a "muted workshop"
sound palette. It is a starting point, not an identity. With the user:

1. **Their visual identity**: colors, fonts (`motion-design/SKILL.md`, "Apply your brand"). One theme file: `motion-design/src/illustration/theme.ts`.
2. **Their sound palette**: keep the default palette or change its direction (`motion-design/reference/palette-sonore.md`). Have them listen to the contact sheet (`make-sfx.py --planche`) before approving.
3. **Their overlay level**: light (one premium scene per chapter, one lower third per minute) or dense (scenes over 60 to 70% of the frame). See "Editorial golden rule" in `overlays/SKILL.md`.
4. **Their reference voice**: `python3 motion-design/scripts/make-sfx.py --voix <one of their clips>` measures their level; copy the value into `VOIX_REF` so the sound effects land at the right volume.

These choices are theirs: propose, show, get approval. Write down what is decided in the kit's files (the
theme, the sound palette), not only in the conversation.

## Working rules

- **The clip is never modified.** Everything is written next to it (`<clip>_Derush_v1.xml`, work folders). A new pass is `v2`, never an overwrite.
- **Premiere only imports Final Cut Pro 7 XML (XMEML).** Never FCPXML.
- **The reference timeline for overlays is the one in the `.prproj`**, after the user has corrected the rough cut, never the one in the rough-cut XML (`timeline-from-prproj.py`).
- **The user approves the rough cut before the overlays.** Do not chain the two without their go-ahead.
- **Every check that exits with code 1 blocks delivery** (QC chain in `overlays/SKILL.md`). All zeros do not excuse you from looking at the contact sheets. For overlays with text, also run `controle-texte.py`, `montre.py` and `zone_libre.py`.
- **A delivered preview carries a number** (`apercu-v1.mp4`, `apercu-v2.mp4`): never overwrite what the user has already seen.
- **Synced folder** (Dropbox, iCloud, Drive): keep `node_modules`, render caches and demo recordings out of the sync (`MONTAGE_DEPOT`, `MONTAGE_CACHE`, see `.env.example`). Look for "conflicted copy" files each time you resume.
- **No cloned voice** in this kit: the voice is the user's.
- **You choose sounds without hearing them.** You place a sound effect from its description; only the user can say whether it lands badly. Give them the numbered list (`sons-<video>.md`, written at each edit), A/B/C excerpts or a folder where they can delete what they dislike: anything that shortens their answer is worth more than a better choice on your part (`motion-design/reference/palette-sonore.md`, "Have the ear approve").

## Languages

`rough-cut` and `subtitles` read their language data (filler words, false-start phrases, whisper
hallucinations, typography rules) from `languages/<code>.json` inside each skill. The language is `--lang <code>`,
else the one recorded in the transcript, else `en`. French was tested on real videos. English is written
from the same rules and still needs confirmation on a real English clip. Contributions for other languages
are welcome: copy `en.json`, translate it, open a pull request.

## File map

```
AGENTS.md           this file (for the AI)
INSTALL.md          the stack, command by command, and how to check it
WORKFLOW.md         from script to finished video, step by step (diagram)
CHANGELOG.md        what changed from one version to the next
VERSION             kit version number
install.sh          automatic install and check (--data, --dest, --check)
skills/
  rough-cut/      SKILL.md, scripts/ (Python), languages/, references/ (lessons, XML format, verbal markers)
  subtitles/      SKILL.md, scripts/ (Python), languages/
  overlays/       SKILL.md, scripts/ (Python), examples/ (plan, demo scenario), references/lecons.md, .env.example
  motion-design/  SKILL.md, Remotion project (src/, public/), scripts/ (sounds, music, mix), reference/palette-sonore.md
```

Each `SKILL.md` is the reference for its skill. The `references/lecons.md` files say WHY the scripts do
what they do (everything comes from real edits compared with a human editor's work): read them before
changing a script.

## Known limits

- Tested on Mac Apple Silicon (macOS), recent Premiere Pro, Node 20 and up, Python 3.11 and up. Windows and Linux: not tested (the scripts use nothing Mac-specific except `sips` for a few image conversions, replaceable with Pillow).
- Premiere's French transcript is the reference; other languages work for whisper, and the rough-cut rules (verbal markers) were written and tested for French first. English follows the same rules and awaits a real English clip.
- The semantic step of the rough cut (spotting retakes) is done by you, in the conversation. It is the most important one: take the time to compare the transcript with the script.
- Site demos drive a real browser: a site that changes structure breaks a scenario. Redo the recording of that demo alone, never the whole video.
