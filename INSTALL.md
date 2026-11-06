# Install

Once per machine. `bash install.sh` does everything below and stops on what is missing; this document is
for understanding it, or installing by hand.

## 1. What you need

| Piece | Why | Tested version |
|---|---|---|
| macOS on Apple Silicon | accelerated whisper.cpp (Metal), fast Remotion renders | recent macOS, M chips |
| **Premiere Pro** | transcript (Text panel > Transcribe), XML import, final edit | recent version with built-in transcription |
| **Claude Code** | reads the skills and drives everything | latest version |
| Homebrew | installs the rest | |
| **Node.js** >= 20 | Remotion (React animation) | 20 to 26 |
| **Python 3** >= 3.10 | rough cut, subtitles, sounds, music, site demos | 3.11 to 3.14 |
| **ffmpeg** with `prores_ks` | audio extraction, ProRes 4444 renders (transparency) for Premiere | 7 and up |
| **whisper.cpp** + `large-v3-turbo` model | local transcription, second opinion | 1.7 and up |
| Playwright's Chromium | records site demos | installed by Playwright |

Python packages: `numpy`, `scipy`, `soundfile`, `Pillow`, `playwright`, `fonttools`, `opencv-python`. For
`subtitles` also: `ctc-forced-aligner`, `torch`, `torchaudio`, `unidecode`.

License: the kit is MIT. Remotion is free for an individual or a company of 3 employees or fewer; beyond
that, a company license (remotion.pro). Full text: `skills/motion-design/node_modules/remotion/LICENSE.md`
after `npm ci`.
Node packages: pinned in `skills/motion-design/package.json` (Remotion 4.0.529 and its modules), installed by `npm ci`.

## 2. Install as a Claude Code plugin

```
/plugin marketplace add ThomasHMD/premiere-rough-cut
/plugin install premiere-rough-cut@premiere-rough-cut
```

Then the one-time setup line:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/install.sh" --data "${CLAUDE_PLUGIN_DATA}"
```

In plugin mode `install.sh` copies no skill. The workshop's `node_modules` lives in the data folder given
by `--data`, and `skills/motion-design/node_modules` is a link to it. After a plugin update the link is
gone: run the same setup line again and it is restored in a second.

## 3. Install by hand

```bash
# system tools
brew install node python ffmpeg whisper-cpp

# Python
python3 -m pip install numpy scipy soundfile pillow playwright fonttools opencv-python
python3 -m pip install ctc-forced-aligner torch torchaudio unidecode   # for subtitles
python3 -m playwright install chromium

# whisper model (~1.6 GB)
mkdir -p ~/Models/whisper
curl -L -o ~/Models/whisper/ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin

# skills: the four folders side by side
mkdir -p ~/.claude/skills
cp -R skills/rough-cut skills/subtitles skills/overlays skills/motion-design ~/.claude/skills/

# Remotion workshop
cd ~/.claude/skills/motion-design && npm ci
```

Or let the script do it: from the kit root, `bash install.sh` (skills copied into `~/.claude/skills`),
`bash install.sh --dest <folder>` (skills copied elsewhere, for example `<project>/.claude/skills`).

`install.sh` options:

| Option | Effect |
|---|---|
| `--data <dir>` | plugin mode: the workshop's `node_modules` goes in this folder, linked from `skills/motion-design/node_modules`; no skill is copied |
| `--dest <dir>` | manual mode: where to copy the skills (default `~/.claude/skills`) |
| `--check` | only checks, installs nothing |

It checks, and installs after asking: Homebrew, node >= 20, python3, ffmpeg with `prores_ks`, whisper-cli
(whisper-cpp), the model `~/Models/whisper/ggml-large-v3-turbo.bin`, the Python packages, Playwright's
Chromium, then runs `npm ci` in the workshop and a test render.

On a Homebrew-managed Python, `pip install` may refuse ("externally-managed-environment"): use a virtual
environment (`python3 -m venv ~/.venvs/montage && source ~/.venvs/montage/bin/activate`) or add
`--break-system-packages` knowingly.

Python downloaded from python.org (not Homebrew): scripts that download (images, GIFs, pages) fail with
`CERTIFICATE_VERIFY_FAILED` until its certificates are installed. Run once
`/Applications/Python\ 3.X/Install\ Certificates.command` (X = its version); `install.sh` detects this and offers it.

For a project skills folder instead of the global one, use `--dest <project>/.claude/skills`. For
`examples/plan-example.py`, then export `KIT_SKILLS=<project>/.claude/skills`.

## 4. Optional keys

Copy `skills/overlays/.env.example` to `.env` in the skill folder (or at the project root) and fill in what you use:

- `SERPAPI_API_KEY`: image search (illustration photos). Limited free tier: save your searches.
- `GIPHY_API_KEY`: GIF search (`gifs.py`). Free at developers.giphy.com.

Without a key, everything else works. Never commit the `.env`.

## 5. Check

```bash
bash install.sh --check
whisper-cli --help >/dev/null && echo "whisper OK"
ls ~/Models/whisper/ggml-large-v3-turbo.bin
ffmpeg -hide_banner -encoders | grep prores_ks
python3 -c "import numpy, scipy, soundfile, PIL, playwright; print('python OK')"
cd ~/.claude/skills/motion-design
npx tsc --noEmit && echo "types OK"
npx remotion still src/index.ts LowerThirdTrack /tmp/kit-test.png --frame=90 && open /tmp/kit-test.png
python3 scripts/make-sfx.py            # regenerates public/sfx/ (palette sounds)
python3 music/example_pad.py 12 /tmp/pad.wav && afplay /tmp/pad.wav
```

End-to-end site demo (about 2 min):

```bash
cd ~/.claude/skills/overlays
python3 scripts/screencast-record.py examples/screencast-exemple.json --out /tmp/demo-rec
python3 scripts/screencast-render.py /tmp/demo-rec --out /tmp/demo.mp4 && open /tmp/demo.mp4
```

## 6. Synced folder (Dropbox, iCloud, Drive...)

If the skills or the videos live in a synced folder:

- the workshop's `node_modules` (about 1 GB, tens of thousands of files): exclude it from sync;
- `export MONTAGE_DEPOT=<unsynced folder, same disk>`: render work files;
- demo recordings go in `~/.cache/kit-montage/` (or `MONTAGE_CACHE`): about 1 GB per minute of demo.

## 7. Update the kit

Plugin: `/plugin update premiere-rough-cut`, then rerun the setup line (the `node_modules` link). By hand:
a new version arrives as a zip; replace the four skill folders, keeping aside what was customized
(`motion-design/src/illustration/theme.ts`, fonts in `public/fonts/`, settings in `scripts/make-sfx.py`,
`.env`), then `npm ci` and `python3 scripts/make-sfx.py`. `CHANGELOG.md` says what changed.
