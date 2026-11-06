"""Language data shared by the rough-cut scripts.

Everything that depends on the spoken language (filler words, false-start phrases, slate
patterns, stop words, the reason texts written into the cuts, the examples of the LLM prompt...)
lives in ../languages/<code>.json, never in the code. This module only finds and reads those files.

Language choice, in this order:
  1. --lang <code> on the command line;
  2. the language recorded in the transcript (whisper's "language" in transcript.json);
  3. en.
A missing languages/<code>.json falls back to en.json with a one-line warning.

Usage in a script:
    import lang
    lang.add_argument(ap)                                    # argparse scripts: adds --lang
    code, argv = lang.pop_argv(sys.argv[1:])                 # scripts that read sys.argv by hand
    data = lang.load(lang.resolve(code, lang.from_transcript(path)))
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
                                   "recorded in the transcript, else en")


def pop_argv(argv):
    """Takes '--lang X' or '--lang=X' out of a list of arguments: (code or None, remaining list)."""
    rest, code, i = [], None, 0
    while i < len(argv):
        x = argv[i]
        if x == "--lang" and i + 1 < len(argv):
            code = argv[i + 1]
            i += 2
            continue
        if x.startswith("--lang="):
            code = x.split("=", 1)[1]
        else:
            rest.append(x)
        i += 1
    return code, rest


def from_transcript(path):
    """The "language" recorded in a whisper transcript.json, or None (file absent or unreadable)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc.get("language") if isinstance(doc, dict) else None


def from_work_dir(work_dir):
    """The language of the transcript.json of a work folder, or None."""
    return from_transcript(Path(work_dir) / "transcript.json")
