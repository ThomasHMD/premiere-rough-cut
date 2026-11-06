# French verbal markers (readable summary)

The source of truth is `languages/fr.json` (see [`languages.md`](languages.md)): that is the file the scripts read,
and the one to edit. This page lists the French markers in a human-readable form, with a short note on how each
group is used. It is a data file: the French expressions stay in French on purpose.

## Isolated fillers (`filler`)

Cut automatically (confidence 0.95) when surrounded by silence or punctuation.

- euh
- euhh
- heu
- hum
- hmm
- mh
- bah

## Sentence-start fillers (`filler_debut`)

Cut only at the start of a sentence or after a silence (> 0.4 s). Otherwise keep them: they are words of
natural speech.

- ben
- enfin

## False starts (`false_start`)

They open a window for Claude to analyze (semantic stage). No automatic cut.

- attends
- attendez
- non non
- non pardon
- pardon
- je reprends
- je recommence
- je refais
- stop
- coupez
- coupe

## Other French data

The same file also holds the French slate patterns, orphan connectors (Et / Alors / Donc / Mais), openers to cut
(« Voilà, »), whisper hallucinations (« Sous-titrage Société Radio-Canada ») and the reason texts of the red markers. Their keys are
described in the `_doc` entry of the JSON file.

## Enriching a list

- Add a word to a list in `languages/fr.json`; the scripts pick it up on the next run.
- Prefer spoken forms (whisper sometimes drops accents).
- Test on a clip before keeping an enriched list.
- For variants (a long-vowel "euh"), whisper may write « euhhh » or « heu »: add the common variants.
