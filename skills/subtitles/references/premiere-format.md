# Premiere Pro caption JSON format

Premiere exports its auto transcript (and re-imports it) as **minified UTF-8 JSON with alphabetically sorted keys**, timings **in seconds** (float). `build_subs.py` clones this format from the original file; this page is for understanding and diagnosing when the inspection shows differences.

## Structure

```json
{
  "language": "en-us",
  "segments": [
    {
      "duration": 3.05,
      "language": "en-us",
      "speaker": "00634364-2071-42be-aaf7-80d559731696",
      "start": 4.8,
      "words": [
        {
          "confidence": 1,
          "duration": 0.4266666666666667,
          "eos": false,
          "start": 4.8,
          "tags": [],
          "text": "First",
          "type": "word"
        }
      ]
    }
  ],
  "speakers": [
    {"id": "00634364-2071-42be-aaf7-80d559731696", "name": "Unknown"}
  ]
}
```

## Keys (alphabetical order, imposed by Premiere)

| Level | Keys |
|---|---|
| top | `language`, `segments`, `speakers` |
| segment | `duration`, `language`, `speaker`, `start`, `words` |
| word | `confidence`, `duration`, `eos`, `start`, `tags`, `text`, `type` |

## Meaning of the `word` fields

- **`start` / `duration`**: in **seconds** (float). `start + duration` of the last word is about the video duration (a few tenths of tolerance).
- **`text`**: the word **WITH its punctuation and case**. This is the crucial point: Premiere stores "go.", "Coffee" (capital), "name," directly in the word's text. There is no separate punctuation field. A readable caption (commas, full stops, sentence capitals) depends entirely on what goes here.
- **`eos`**: *end of sentence*: `true` on the last word of a sentence (followed by `.`/`!`/`?`). A grouping hint for Premiere.
- **`confidence`**: 0 to 1. Premiere puts real values there; so does whisper (token probability). Not critical for the import.
- **`tags`**: almost always `[]`.
- **`type`**: always `"word"`.
- **Pauses**: inside a `.prproj` a real pause is an item with empty text and type 3. A JSON import of an item with empty text creates a WORD with no text instead, so a JSON built by the scripts carries no pause: Premiere recreates typed pauses itself in the gaps between words.

## Fidelity points (for a surprise-free re-import)

1. **Reuse the same `speaker` UUID and `name`** as the original export (otherwise Premiere creates a phantom speaker).
2. **Sorted keys + minified**: `json.dump(..., ensure_ascii=False, sort_keys=True, separators=(",",":"))`.
3. **Accents as direct UTF-8** (no `\uXXXX`): `ensure_ascii=False`.
4. **Never overwrite the original export**: write `<name>_corrige.json` next to it.

## Difference from the whisper transcript

`transcribe.py` (whisper.cpp) outputs a different format: `segments[].text` (punctuated) + `segments[].words[]` with `start`/`end` (no `duration`) and **without** punctuation or sentence case on the words. `build_subs.py` bridges the two: it realigns every whisper word on the segment's punctuated `text` to recover punctuation and case, then emits the Premiere format above.
