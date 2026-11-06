# whisper.cpp setup for rough-cut

Once per machine. Everything stays local, nothing goes to the cloud. (`install.sh` at the kit root does this
for you; this page is for understanding it or doing it by hand.)

## Installing the binaries

```bash
# whisper.cpp via Homebrew (Metal-accelerated on Apple Silicon)
brew install whisper-cpp

# FFmpeg + ffprobe (needed for audio extraction and metadata)
brew install ffmpeg
```

Check:
```bash
which whisper-cli || which whisper-cpp || which main
which ffmpeg ffprobe
```

The whisper binary is called `whisper-cli` (recent versions), `whisper-cpp` or `main` (older builds). The
scripts detect all three.

## Downloading the model

Recommended model: `large-v3-turbo` (about 1.5 GB, best quality/speed trade-off).
On Apple Silicon (M4 Max): about 15-25x real time, so 5 min of footage is about 15-20 s of transcription.

```bash
mkdir -p ~/Models/whisper
curl -L -o ~/Models/whisper/ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
```

Lighter alternatives (handy for a quick test):
- `small` (about 466 MB, 5-10x faster, acceptable quality)
- `medium` (about 1.5 GB, more accurate than small but slower than large-v3-turbo)

```bash
# small (quick test)
curl -L -o ~/Models/whisper/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin

# medium
curl -L -o ~/Models/whisper/ggml-medium.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin
```

Note: models without the `.en` suffix are multilingual, which is what the skill needs for French and for
language auto-detection. Do not download an English-only model unless you only ever work in English.

## Choosing the model at runtime

By default the skill uses `large-v3-turbo`. To try another one:

```bash
python3 .../scripts/derush.py /path/clip.mp4 --model=small
```

## Choosing the language

whisper is told the spoken language (`-l <code>`). The skill passes the language chosen by `--lang` (see
`languages.md`); a language with no `languages/<code>.json` still transcribes, it just uses the English lists.

## Manual test (without the skill)

```bash
# Extract audio
ffmpeg -y -i clip.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le /tmp/test.wav

# Transcribe (replace en with your language code)
whisper-cli -m ~/Models/whisper/ggml-large-v3-turbo.bin \
  -l en -f /tmp/test.wav -of /tmp/test \
  --output-json --output-json-full

# Output: /tmp/test.json
head -20 /tmp/test.json
```

If it works by hand, the skill should work.

## Privacy

- The `whisper-cli` binary is strictly local: no outbound network after installation.
- The model is downloaded once from Hugging Face, then used offline.
- Your footage never leaves your machine.
- To check: `lsof -i -P` while the skill runs should list nothing for `whisper-cli`.

## Troubleshooting

**"whisper.cpp not found"**: `brew install whisper-cpp`, then restart the shell.

**"model not found"**: check `ls ~/Models/whisper/` and the expected path (`ggml-<name>.bin`).

**Transcript in the wrong language**: whisper auto-detects the language but can be wrong on short passages. Pass
the language explicitly with `--lang`.

**Very low confidence everywhere**: degraded audio or a model that is too small. Try `large-v3-turbo` instead of
`small`.

**Metal "GGML_ASSERT" error**: conflict with the OS; restart the machine or try `--no-gpu`.
