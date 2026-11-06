#!/usr/bin/env python3
"""Builds the LLM prompt for stage 5 (semantic analysis).

The LLM (Claude, running the skill) receives:
- the transcript as text with readable timecodes
- the mechanical cuts already found (to confirm or refine)
- the flagged windows (false starts detected mechanically)
- the decision rules and the expected output format

Output: prompt_semantic.txt + path of the expected output cuts_semantic.json

Usage:
    python3 llm_prompt_builder.py transcript.json cuts_mechanical.json prompt.txt cuts_semantic.json [--lang fr]

The language name and the speech examples of the prompt come from ../languages/<code>.json:
--lang, else the "language" of the transcript, else en.
"""
import json
import sys
from pathlib import Path

import lang


def format_timestamp(seconds):
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:06.3f}"


def render_transcript(transcript):
    """Readable output: one segment per line, with its start timecode."""
    lines = []
    for seg in transcript["segments"]:
        ts = format_timestamp(seg["start"])
        lines.append(f"[{ts}] {seg['text']}")
    return "\n".join(lines)


def render_mechanical_cuts(cuts_data):
    cuts = cuts_data.get("cuts", [])
    windows = cuts_data.get("false_start_windows", [])

    lines = ["### Mechanical cuts already found (to confirm or refine)"]
    if cuts:
        for c in cuts:
            ts = format_timestamp(c["start"])
            lines.append(f"- [{ts} → {format_timestamp(c['end'])}] type={c['type']} "
                         f"conf={c['confidence']:.2f}: {c['reason']}")
    else:
        lines.append("(none)")

    lines.append("")
    lines.append("### Windows flagged with false-start markers (analyze these first)")
    if windows:
        for w in windows:
            ts = format_timestamp(w["start"])
            lines.append(f"- [{ts} → {format_timestamp(w['end'])}]: {w['reason']}")
    else:
        lines.append("(none)")
    return "\n".join(lines)


PROMPT_TEMPLATE = """# Stage 5: semantic analysis of the cuts for Premiere Pro

You are analyzing the transcript of a talking-head monologue in {language_name} to find the
semantic false starts, the rephrased repetitions and the restarted sentences.
The user wants to keep only the last version of a rephrased sentence.

## Context

- **Type**: talking-head monologue / vlog, spoken and natural tone
- **Language**: {language_name}
- **Expected precision**: 90%, **better to flag than to remove**
- **Confidence score**: 0..1
  - >= 0.92 → `disable` decision (the passage will be REMOVED from the edit, not just grayed out:
    irreversible on the timeline side, only give this score when you are certain)
  - 0.6 to 0.92 → `flag` decision (passage kept in the edit, red marker for review)
  - < 0.6 → ignored (do not include it in the output)

## What to detect

1. **Explicit false starts**: {explicit_false_starts}
   followed by a rephrasing. Cut from the start of the false start to the start of the rephrasing.
2. **Sentences restarted 2 or 3 times** (close variants with no explicit marker). Keep the last version. Cut all the previous versions.
3. **Non-trivial immediate textual repetitions** ({immediate_repetition}). If the mechanical cuts already cover it, do not duplicate.
4. **Sentences abandoned** halfway and followed by a restart.

## What NOT to cut

- Intended rhetorical repetitions ({rhetorical_repetition})
- Rephrasings that bring new content ({rephrasing_with_content})
- Natural hesitations that are part of the flow
- Intended dramatic pauses
- Light verbal tics that naturally pace the speech

## Cutting rules

- Always cut from the **start of the false start to the start of the rephrasing** (not before, not after)
- **Never spill over the rephrased sentence**: it is kept in full
- If you hesitate between two versions of a rephrased sentence, keep **the longest and calmest one**
- When in doubt, lower the score under 0.92 to get a `flag` rather than a `disable`

## Transcript

```
{transcript_text}
```

## Cuts already found mechanically

{mechanical_section}

## Output format

**You must write a valid JSON file at this path**: `{output_path}`

Exact schema:

```json
{{
  "cuts": [
    {{
      "id": "c_sem_0001",
      "start": 42.18,
      "end": 47.92,
      "type": "false_start",
      "confidence": 0.88,
      "reason": {example_reason},
      "matched_text": {example_matched_text},
      "context_before": {example_context_before},
      "context_after": {example_context_after},
      "source": "semantic"
    }}
  ]
}}
```

Allowed values for `type`:
- `false_start`: false start with an explicit marker
- `semantic_restart`: sentence rephrased with no marker
- `repetition`: non-trivial textual repetition (rare here, normally already handled mechanically)

If **no relevant semantic cut** is found, write `{{"cuts": []}}`.

## Procedure

1. Read this prompt in full
2. Read the transcript above in full
3. Find the suspect zones, starting with the flagged windows
4. For each proposed cut, justify it in 1 line in `reason`
5. Write the final JSON to `{output_path}`
6. Resume the orchestration: `python3 derush.py <rush> --resume-from=6 --work-dir=<work>` (`derush.py` printed the exact paths)
"""


def main():
    code, argv = lang.pop_argv(sys.argv[1:])
    if len(argv) != 4:
        print("Usage: llm_prompt_builder.py <transcript.json> <cuts_mechanical.json> "
              "<prompt.txt> <cuts_semantic_output_path> [--lang CODE]", file=sys.stderr)
        sys.exit(1)

    transcript = json.loads(Path(argv[0]).read_text())
    cuts_mech = json.loads(Path(argv[1]).read_text())
    out_prompt = Path(argv[2])
    out_semantic = Path(argv[3]).resolve()
    data = lang.load(lang.resolve(code, transcript.get("language")))
    ex = data["prompt_examples"]

    transcript_text = render_transcript(transcript)
    mechanical_section = render_mechanical_cuts(cuts_mech)

    prompt = PROMPT_TEMPLATE.format(
        transcript_text=transcript_text,
        mechanical_section=mechanical_section,
        output_path=str(out_semantic),
        language_name=data["language_name"],
        explicit_false_starts=", ".join(f'"{x}"' for x in ex["explicit_false_starts"]),
        immediate_repetition=f'"{ex["immediate_repetition"]}"',
        rhetorical_repetition=f'"{ex["rhetorical_repetition"]}"',
        rephrasing_with_content=f'"{ex["rephrasing_with_content"]}"',
        example_reason=json.dumps(ex["reason"], ensure_ascii=False),
        example_matched_text=json.dumps(ex["matched_text"], ensure_ascii=False),
        example_context_before=json.dumps(ex["context_before"], ensure_ascii=False),
        example_context_after=json.dumps(ex["context_after"], ensure_ascii=False),
    )
    out_prompt.write_text(prompt)
    print(f"LLM prompt written: {out_prompt} ({len(prompt)} chars)")
    print(f"Expected output: {out_semantic}")


if __name__ == "__main__":
    main()
