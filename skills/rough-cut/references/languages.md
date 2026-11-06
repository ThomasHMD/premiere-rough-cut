# Languages: `--lang` and `languages/<code>.json`

Everything that depends on the spoken language lives in a JSON file, never in the code. The scripts read it; to
change what counts as a filler or a false start, or to support a new language, you edit data, not Python.

## Where the files are

`skills/rough-cut/languages/<code>.json`, one file per language, named with the ISO 639-1 code (`fr`, `en`,
`es`...). Two ship with the kit: `fr.json` and `en.json`. They are the **source of truth**: this page does not
copy their lists, open the files to see the exact values. Each file has a `"_doc"` key that says in one line
what every list does, and the keys are in English, snake_case, one key per list.

The kinds of data they hold: filler words, sentence-start fillers, false-start phrases, take-slate patterns,
stop words, orphan connectors (the short words cut together with a silence), openers to cut at the start of a
sentence, whisper hallucination lines to drop, the examples given in the AI prompt, and the texts of the cut
reasons (shown in the red markers and the report, written in that language with its own typography). The
subtitles skill has its own `languages/<code>.json` for the typography and hallucination data it needs.

## How the language is chosen

In this order:

1. `--lang <code>` on the command line;
2. else the language recorded in the transcript (whisper's `language`, or the language Premiere stored in the transcript);
3. else `en`.

If `languages/<code>.json` does not exist for the chosen code, the scripts fall back to `en.json` and print a
one-line warning. Transcription still runs in the chosen language (whisper is told `-l <code>`); only the
word lists fall back.

Run any script with `--help` to see whether it takes `--lang`; the scripts that read word lists do.

## Adding a language

1. Copy `en.json` to `<code>.json`.
2. Translate each list for the target language. Keep the keys exactly as they are: they are the contract with the scripts.
   - fillers: the hesitation sounds people actually make in that language, including the spellings whisper tends to produce ("euhh" and "heu" for the French "euh", for instance);
   - false starts and slate: the phrases a speaker says when restarting or opening a take;
   - orphan connectors and openers: short words that begin a sentence and carry no content (the cuts that keep a clean edit);
   - whisper hallucinations: the lines whisper invents over silence in that language (subtitle credits, "thanks for watching" variants). Listen to a silent stretch of a real transcript to find them;
   - reasons: the texts of the cut reasons, shown in the red markers and the report; keep every `{name}` placeholder as it is.
3. Update `"_doc"` if you add or remove a list.
4. Test on a short clip of that language: `--lang <code>`, then read the report and run `montage_qc.py`.
   Start with fewer fillers rather than more: a missing filler leaves a word in, a false match cuts speech.
5. The same code in `skills/subtitles/languages/` lets the subtitles skill apply the right typography.

A language with no file still works, with English lists; the result is a rough cut that cuts silences and
retakes but misses that language's fillers.
