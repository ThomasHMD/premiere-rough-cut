"""Language data shared by the subtitles scripts.

Everything that depends on the spoken language (typography rules, accented letters kept when
comparing words, punctuation sets, words to normalize, whisper hallucinations...) lives in
../languages/<code>.json, never in the code. This module only finds and reads those files.

Language choice, in this order:
  1. --lang <code> on the command line;
  2. the language recorded in the input files (Premiere JSON "language", whisper transcript "language");
  3. en.
A missing languages/<code>.json falls back to en.json with a one-line warning.

Usage in a script:
    import lang
    lang.add_argument(ap)                       # adds --lang
    data = lang.load(lang.resolve(args.lang, doc.get("language")))
"""
import json
import sys
from pathlib import Path

LANG_DIR = Path(__file__).resolve().parents[1] / "languages"
FALLBACK = "en"
ISO3 = {"fra": "fr", "fre": "fr", "eng": "en"}


def short_code(code):
    """'fr-fr', 'fr_FR', 'fra' -> 'fr'. None when the value is not a language code."""
    if not code or not isinstance(code, str):
        return None
    c = code.strip().lower().replace("_", "-").split("-")[0]
    c = ISO3.get(c, c)
    return c if c.isalpha() and 2 <= len(c) <= 3 else None


def resolve(*candidates):
    """First usable code among the candidates (explicit --lang first), else en."""
    for c in candidates:
        s = short_code(c)
        if s:
            return s
    return FALLBACK


def available():
    return sorted(p.stem for p in LANG_DIR.glob("*.json"))


def load(code=None):
    """Language data as a dict (keys starting with '_' are documentation and are dropped)."""
    code = short_code(code) or FALLBACK
    path = LANG_DIR / f"{code}.json"
    if not path.exists():
        print(f"[lang] no {path.name} in {LANG_DIR}, falling back to {FALLBACK}.json "
              f"(available: {', '.join(available())})", file=sys.stderr)
        code = FALLBACK
        path = LANG_DIR / f"{code}.json"
    if not path.exists():
        sys.exit(f"ERROR: language file missing: {path}")
    data = {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    data.setdefault("code", code)
    return data


def add_argument(ap):
    ap.add_argument("--lang", help="language code of the speech (fr, en...); default: the language "
                                   "found in the input files, else en")


def non_word_pattern(data):
    """Regex matching every character that is NOT part of a word when words are compared
    (digits, ascii letters, the language's accented letters, hyphen and apostrophe are kept)."""
    return r"[^0-9a-z" + data["word_chars"] + r"\-']"
