#!/usr/bin/env bash
# premiere-rough-cut: check and install everything the four skills need. Safe to rerun: it only does what is missing,
# and asks before installing anything.
#
#   Plugin install (Claude Code fills in both paths when it reads the skill):
#     bash "${CLAUDE_PLUGIN_ROOT}/install.sh" --data "${CLAUDE_PLUGIN_DATA}"
#   Manual install (copies the skills into ~/.claude/skills, or --dest <dir>):
#     bash install.sh [--dest <dir>]
#   Check only, install nothing:
#     bash install.sh --check [--data <dir> | --dest <dir>]
set -u
KIT="$(cd "$(dirname "$0")" && pwd)"
DATA="" DEST="" CHECK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --data) DATA="${2:-}"; shift 2 ;;
    --dest) DEST="${2:-}"; shift 2 ;;
    --check) CHECK=1; shift ;;
    -h|--help) sed -n 2,11p "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)"; exit 2 ;;
  esac
done
case "$DATA" in *'${'*) echo "--data was not filled in: run this line from the skill, or pass a real folder."; exit 2 ;; esac
MODEL="$HOME/Models/whisper/ggml-large-v3-turbo.bin"
SKILLS="rough-cut subtitles overlays motion-design"
MISSING=0

ok()  { printf '  \033[32mOK\033[0m %s\n' "$1"; }
ko()  { printf '  \033[31m!!\033[0m %s\n' "$1"; MISSING=1; }
ask() { [ "$CHECK" = 1 ] && return 1; read -r -p "  $1 [y/N] " r; [[ "$r" =~ ^[yY] ]]; }

echo "1. System tools"
if [ "$(uname -s)" != "Darwin" ]; then ko "macOS only for now (Premiere Pro, Homebrew, Apple Silicon tested)"; fi
if ! command -v brew >/dev/null; then
  ko "Homebrew is missing: install it first (https://brew.sh), then rerun."
  exit 1
fi
for pkg in node python ffmpeg whisper-cpp; do
  case $pkg in node) cmd=node ;; python) cmd=python3 ;; ffmpeg) cmd=ffmpeg ;; whisper-cpp) cmd=whisper-cli ;; esac
  if command -v "$cmd" >/dev/null; then ok "$cmd"
  elif ask "$cmd is missing. brew install $pkg?"; then brew install "$pkg" && ok "$cmd" || ko "$cmd"
  else ko "$cmd (brew install $pkg)"; fi
done
if command -v node >/dev/null; then
  v=$(node -p 'process.versions.node.split(".")[0]')
  [ "$v" -ge 20 ] && ok "Node $v (20 or later)" || ko "Node $v: version 20 or later is needed (brew upgrade node)"
fi
if command -v ffmpeg >/dev/null; then
  ffmpeg -hide_banner -encoders 2>/dev/null | grep -q prores_ks && ok "ffmpeg writes ProRes (prores_ks)" \
    || ko "ffmpeg without prores_ks: reinstall ffmpeg from Homebrew"
fi

echo "2. Python packages"
PKGS="numpy scipy soundfile pillow playwright fonttools opencv-python"
if python3 -c "import numpy, scipy, soundfile, PIL, playwright, fontTools, cv2" 2>/dev/null; then ok "$PKGS"
elif ask "Missing Python packages. python3 -m pip install $PKGS?"; then
  python3 -m pip install $PKGS || ko "pip refused (Python managed by Homebrew?): see INSTALL.md, section 2"
else ko "Python packages: $PKGS (INSTALL.md, section 2)"; fi
SUBS="ctc-forced-aligner torch torchaudio unidecode"
if python3 -c "import ctc_forced_aligner, torch, torchaudio, unidecode" 2>/dev/null; then ok "subtitles: $SUBS"
elif ask "Forced alignment for the subtitles skill (about 2 GB with torch). python3 -m pip install $SUBS?"; then
  python3 -m pip install $SUBS || ko "subtitles packages (INSTALL.md, section 2)"
else ko "subtitles packages, only needed by the subtitles skill: $SUBS"; fi
if python3 -c "import urllib.request; urllib.request.urlopen('https://pypi.org', timeout=10)" 2>/dev/null; then ok "HTTPS downloads from Python"
elif python3 -c "import urllib.request; urllib.request.urlopen('https://pypi.org', timeout=10)" 2>&1 | grep -q CERTIFICATE_VERIFY_FAILED; then
  # Python from python.org does not use the Mac's certificates until its certificate script has run
  cert=$(ls -d /Applications/Python\ 3*/Install\ Certificates.command 2>/dev/null | tail -1)
  if [ -n "$cert" ] && ask "Python does not verify HTTPS certificates (Python from python.org). Run \"$cert\"?"; then
    bash "$cert" >/dev/null 2>&1 && ok "Python certificates installed" || ko "certificates (run \"$cert\" by hand)"
  else ko "Python HTTPS certificates: run \"Install Certificates.command\" from the Python folder in Applications"; fi
else ko "no HTTPS downloads from Python (network?)"; fi
if python3 -c "import playwright" 2>/dev/null; then
  if ls "$HOME/Library/Caches/ms-playwright" 2>/dev/null | grep -q chromium; then ok "Playwright Chromium"
  elif ask "Playwright Chromium is missing (site demos). Install it?"; then python3 -m playwright install chromium && ok "Chromium" || ko "Chromium"
  else ko "Chromium (python3 -m playwright install chromium)"; fi
fi

echo "3. Whisper model"
if [ -s "$MODEL" ]; then ok "$MODEL"
elif ask "Model large-v3-turbo is missing (about 1.6 GB). Download it?"; then
  mkdir -p "$(dirname "$MODEL")"
  curl -L --fail -o "$MODEL" https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin \
    && ok "model downloaded" || ko "model download"
else ko "whisper model (INSTALL.md, section 3)"; fi

echo "4. Skills"
if [ -n "$DATA" ]; then
  ok "plugin install: the skills stay where Claude Code put them ($KIT/skills)"
  ROOT="$KIT/skills"
else
  DEST="${DEST:-$HOME/.claude/skills}"
  ROOT="$DEST"
  [ "$CHECK" = 1 ] || mkdir -p "$DEST"
  for s in $SKILLS; do
    if [ -d "$DEST/$s" ]; then
      if [ "$(cd "$DEST/$s" && pwd)" = "$KIT/skills/$s" ]; then ok "$s (already in place)"
      elif ask "$DEST/$s already exists. Replace it with the kit's version (the old one moves to $DEST/$s.old-$(date +%Y%m%d-%H%M))?"; then
        mv "$DEST/$s" "$DEST/$s.old-$(date +%Y%m%d-%H%M)" && cp -R "$KIT/skills/$s" "$DEST/" && ok "$s replaced"
      else ok "$s (kept as is)"; fi
    elif [ "$CHECK" = 1 ]; then ko "$s not copied into $DEST"
    else cp -R "$KIT/skills/$s" "$DEST/" && ok "$s copied"; fi
  done
  for old in premiere-derush illustration-video; do
    [ -d "$DEST/$old" ] && echo "  note: $DEST/$old is the 1.x name of a skill of this kit; remove it once you have switched."
  done
fi

echo "5. Remotion workshop"
MD="$ROOT/motion-design"
if [ -n "$DATA" ]; then
  # node_modules lives in the plugin data folder (kept across plugin updates), linked into the workshop
  NM="$DATA/motion-design"
  if [ ! -d "$NM/node_modules/remotion" ] || ! cmp -s "$MD/package-lock.json" "$NM/package-lock.json"; then
    if command -v npm >/dev/null && ask "Install the workshop packages into $NM (npm ci, about 1 GB)?"; then
      mkdir -p "$NM" && cp "$MD/package.json" "$MD/package-lock.json" "$NM/" && (cd "$NM" && npm ci) && ok "npm ci" || ko "npm ci"
    else ko "workshop packages (rerun this script without --check)"; fi
  fi
  if [ -d "$NM/node_modules/remotion" ] && [ ! -e "$MD/node_modules" ]; then
    if [ "$CHECK" = 1 ]; then ko "node_modules link missing in $MD (rerun without --check)"
    else ln -s "$NM/node_modules" "$MD/node_modules" && ok "node_modules linked"; fi
  fi
else
  if [ -d "$MD/node_modules/remotion" ]; then ok "node_modules"
  elif command -v npm >/dev/null && ask "Install the workshop packages (npm ci, about 1 GB)?"; then
    (cd "$MD" && npm ci) && ok "npm ci" || ko "npm ci"
  else ko "node_modules (cd \"$MD\" && npm ci)"; fi
fi
if [ -d "$MD/node_modules/remotion" ]; then
  ok "node_modules"
  if [ "$CHECK" = 0 ]; then
    (cd "$MD" && npx tsc --noEmit) >/dev/null 2>&1 && ok "types" || ko "types (cd \"$MD\" && npx tsc --noEmit)"
    TEST="${TMPDIR:-/tmp}/premiere-rough-cut-test.png"
    (cd "$MD" && npx remotion still src/index.ts LowerThirdTrack "$TEST" --frame=90 --log=error) >/dev/null 2>&1 \
      && ok "test render: $TEST" || ko "Remotion test render"
  fi
fi
if ls "$MD/public/sfx/"*.wav >/dev/null 2>&1; then ok "sound palette"
elif [ "$CHECK" = 0 ] && python3 "$MD/scripts/make-sfx.py" >/dev/null 2>&1; then ok "sound palette generated"
else ko "sounds (python3 \"$MD/scripts/make-sfx.py\")"; fi

echo
if [ "$MISSING" = 0 ]; then
  echo "All set. Optional keys (image and GIF search): $ROOT/overlays/.env.example"
else
  echo "Some items are marked !! above (details: INSTALL.md)."
fi
exit "$MISSING"
