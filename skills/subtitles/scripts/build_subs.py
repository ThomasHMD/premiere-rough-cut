#!/usr/bin/env python3
"""Rebuilds a subtitle file in Premiere Pro format from a whisper.cpp transcript, putting
punctuation and case back, applying proper-noun corrections and title quotes, and
recomputing eos.

The output format clones EXACTLY that of the original Premiere file (keys sorted
alphabetically, minified UTF-8, timings in seconds, same speaker UUID + language).

Usage:
    python3 build_subs.py \
        --transcript transcript.json \
        --original Reel.json \
        --corrections corrections.json \
        --output Reel_fixed.json \
        [--lang fr]

The language (--lang, else the original's language, else the transcript's, else en) selects
../languages/<code>.json: typography, accented letters, punctuation sets.

corrections.json (all keys optional):
{
  "quote_char": "\"",                 # quote mark for titles (straight by default, from the language file)
  "normalize_cotes": false,           # applies the language file's "normalize_words" (spelling variants)
  "french_typography": true,          # language typography (no-break spaces); default from the language file
  "seq_rules": [                      # multi-word names, N->M, forced case
    [["charbat","goula"], ["Sharbat","Gula"]]
  ],
  "word_rules": {"macdum": "Magnum"}, # one-word names, forced case
  "titles": [                         # works between quotes
    {"match": ["the","decisive","moment"], "canonical": ["The","Decisive","Moment"]},
    {"match": ["errance"], "canonical": ["Errance"], "sep_comma": true}
  ]
}

Match keys (seq_rules / word_rules / titles.match) are compared in LOWERCASE without
punctuation (the source word "Goula," matches "goula").
"""
import argparse, json, re, sys

import lang

LANG = None          # language data, set by use_language()
LEAD = TRAIL = ""    # leading / trailing punctuation sets of the language
_NON_WORD = None     # compiled regex of the characters ignored when comparing words


def use_language(data):
    global LANG, LEAD, TRAIL, _NON_WORD
    LANG, LEAD, TRAIL = data, data["lead_punct"], data["trail_punct"]
    _NON_WORD = re.compile(lang.non_word_pattern(data))


def clean(w):
    return _NON_WORD.sub("", w.lower())

def split_punct(tok):
    m = re.match(r"^([" + re.escape(LEAD) + r"]*)(.*?)([" + re.escape(TRAIL) + r"]*)$", tok)
    return m.group(1), m.group(2), m.group(3)

def make_normalize_cotes():
    """Spelling normalizations of the language file ("normalize_words": [{pattern, base}])."""
    def fix(base):
        def f(m):
            w = m.group(0)
            b = base + ("s" if w.lower().endswith("s") else "")
            return b[0].upper() + b[1:] if w[0].isupper() else b
        return f
    rules = [(re.compile(r["pattern"]), fix(r["base"])) for r in LANG.get("normalize_words", [])]
    def apply(core):
        for rx, f in rules:
            core = rx.sub(f, core)
        return core
    return apply

def align(raw_words, text):
    """Reattaches to each timed word its source form (case + leading/trailing punctuation)."""
    tokens = text.split()
    wordy = [t for t in tokens if clean(t)]
    if len(wordy) == len(raw_words):
        pairs = list(zip(raw_words, wordy))
    else:                                    # greedy fallback if the two are misaligned
        pairs = []; ti = 0
        for w in raw_words:
            wc = clean(w["text"]); chosen = w["text"]
            while ti < len(tokens):
                tok = tokens[ti]; ti += 1
                tc = clean(tok)
                if tc and (wc == tc or wc in tc or tc in wc):
                    chosen = tok; break
            pairs.append((w, chosen))
    items = []
    for w, tok in pairs:
        lead, core, trail = split_punct(tok)
        if not core:
            core = w["text"]
        items.append(dict(core=core, lead=lead, trail=trail, openq=False, closeq=False,
                          start=float(w["start"]), end=float(w["end"]),
                          conf=float(w.get("confidence", 0.9))))
    return items

def apply_seq(items, seq_rules):
    i = 0; out = []
    while i < len(items):
        hit = False
        for src, dst in seq_rules:
            n = len(src)
            if i + n <= len(items) and all(clean(items[i+k]["core"]) == src[k] for k in range(n)):
                blk = items[i:i+n]; m = len(dst)
                bs, be = blk[0]["start"], blk[-1]["end"]; conf = min(b["conf"] for b in blk)
                span = (be - bs) / m if m else 0
                for j, core in enumerate(dst):
                    if n == m:
                        # same length: lead/trail/timing kept per index
                        # (otherwise inner commas disappear: bug seen once)
                        out.append(dict(core=core,
                            lead=blk[j]["lead"], trail=blk[j]["trail"],
                            openq=False, closeq=False,
                            start=blk[j]["start"], end=blk[j]["end"], conf=conf))
                    else:
                        out.append(dict(core=core,
                            lead=blk[0]["lead"] if j == 0 else "",
                            trail=blk[-1]["trail"] if j == m - 1 else "",
                            openq=False, closeq=False,
                            start=round(bs + j*span, 3), end=round(bs + (j+1)*span, 3), conf=conf))
                i += n; hit = True; break
        if not hit:
            out.append(items[i]); i += 1
    return out

def apply_titles(items, titles, quote):
    i = 0
    while i < len(items):
        hit = False
        for t in titles:
            src = [clean(x) for x in t["match"]]; n = len(src)
            if i + n <= len(items) and all(clean(items[i+k]["core"]) == src[k] for k in range(n)):
                canon = t.get("canonical", t["match"])
                for k in range(n):
                    it = items[i+k]
                    it["core"] = canon[k]
                    it["openq"] = (k == 0)
                    it["closeq"] = (k == n - 1)
                    if t.get("sep_comma") and k == n - 1 and "," not in it["trail"]:
                        it["trail"] = it["trail"] + ","
                i += n; hit = True; break
        if not hit:
            i += 1
    return items

NBSP = " "  # no-break space (U+00A0)
def french_typography(txt):
    """Language typography from the language file: no-break space BEFORE the characters of
    "nbsp_before" and AFTER those of "nbsp_after" (French rule: a space before double signs, after opening quotes).
    Idempotent (\\S does not match a NBSP already placed). Leaves . , (single signs) alone."""
    ty = LANG["typography"]
    if ty["nbsp_before"]:
        txt = re.sub(r"(?<=\S)([" + re.escape(ty["nbsp_before"]) + r"])", NBSP + r"\1", txt)
    if ty["nbsp_after"]:
        txt = re.sub(r"([" + re.escape(ty["nbsp_after"]) + r"])(?=\S)", r"\1" + NBSP, txt)
    return txt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True, help="whisper transcript.json (from transcribe.py)")
    ap.add_argument("--original", required=True, help="original Premiere JSON (format + speaker)")
    ap.add_argument("--corrections", help="corrections.json (default: no corrections)")
    ap.add_argument("--output", required=True)
    lang.add_argument(ap)
    args = ap.parse_args()

    tr = json.load(open(args.transcript))
    orig = json.load(open(args.original))
    corr = json.load(open(args.corrections)) if args.corrections else {}

    use_language(lang.load(lang.resolve(args.lang, orig.get("language"), tr.get("language"))))

    quote = corr.get("quote_char", LANG["quote_char"])
    seq_rules = [(list(map(str.lower, s)), d) for s, d in corr.get("seq_rules", [])]
    word_rules = {clean(k): v for k, v in corr.get("word_rules", {}).items()}
    titles = corr.get("titles", [])
    norm = make_normalize_cotes() if corr.get("normalize_cotes") else (lambda c: c)
    fr_typo = corr.get("french_typography", LANG["typography"]["default_on"])   # default from the language file

    # Format cloned from the original
    speaker = (orig.get("speakers") or [{}])[0]
    speaker_id = speaker.get("id", "00000000-0000-0000-0000-000000000000")
    speaker_name = speaker.get("name", LANG["default_speaker_name"])
    language = orig.get("language", LANG["premiere_language"])

    out_segments = []
    for seg in tr["segments"]:
        if not seg.get("words"):
            continue
        items = align(seg["words"], seg["text"])
        items = apply_seq(items, seq_rules)
        for it in items:
            low = clean(it["core"])
            it["core"] = word_rules[low] if low in word_rules else norm(it["core"])
        items = apply_titles(items, titles, quote)

        pwords = []
        for it in items:
            txt = it["lead"] + (quote if it["openq"] else "") + it["core"] + (quote if it["closeq"] else "") + it["trail"]
            if fr_typo:
                txt = french_typography(txt)
            pwords.append({
                "confidence": round(it["conf"], 6),
                "duration": round(max(0.0, it["end"] - it["start"]), 6),
                "eos": bool(re.search(r"[.!?]", it["trail"])),
                "start": round(it["start"], 6),
                "tags": [],
                "text": txt,
                "type": "word",
            })
        if not pwords:        # segment entirely deleted (N->0 rules): skip it
            continue
        s0 = pwords[0]["start"]; s1 = pwords[-1]["start"] + pwords[-1]["duration"]
        out_segments.append({"duration": round(s1 - s0, 6), "language": language,
                             "speaker": speaker_id, "start": s0, "words": pwords})

    result = {"language": language, "segments": out_segments,
              "speakers": [{"id": speaker_id, "name": speaker_name}]}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    # --- Validation report ---
    nw = sum(len(s["words"]) for s in out_segments)
    neos = sum(1 for s in out_segments for w in s["words"] if w["eos"])
    allw = [w for s in out_segments for w in s["words"]]
    maxend = max(w["start"] + w["duration"] for w in allw) if allw else 0
    quotes = sum(s["words"][k]["text"].count(quote) for s in out_segments for k in range(len(s["words"])))
    # same schema as the original?
    def sch(d):
        sk = set(); wk = set()
        for s in d["segments"]:
            sk |= set(s)
            for w in s["words"]: wk |= set(w)
        return set(d), sk, wk
    same = sch(orig) == sch(result)
    print(f"Written: {args.output}")
    print(f"Segments: {len(out_segments)} | words: {nw} | eos: {neos} | quotes: {quotes} (even={quotes%2==0})")
    print(f"End of last word: {maxend:.2f}s")
    print(f"Schema identical to the original: {same}")
    if not same:
        print("  ⚠️ different keys: check the input format", file=sys.stderr)
    if neos == 0 and nw > 30:
        print("  ⚠️ eos=0: the transcript probably has NO punctuation (whisper returned "
              "a continuous stream). Re-punctuate first with repunctuate.py, otherwise the subtitles "
              "will be unreadable. See step 2bis of the SKILL.", file=sys.stderr)

if __name__ == "__main__":
    main()
