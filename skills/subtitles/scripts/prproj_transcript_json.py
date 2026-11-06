#!/usr/bin/env python3
"""Premiere transcript embedded in a .prproj -> JSON in the Premiere export format
(re-importable: Text panel > Transcript > ... > Import).

A .prproj holds one transcript per transcribed clip AND one per sequence (the sequence's
synthetic transcript, with sequence timecodes). The sequence one is what gets corrected and
re-imported. FlatBuffers payload, schema as observed:
  Document : f0 segments, f2 speakers (f0 name, f1 -> table whose 16 bytes at +4 = UUID)
  Segment  : f0 start, f1 duration, f2 speaker, f3 words, f4 language
  Word     : f0 start, f1 duration, f2 text, f3 confidence, f5 present = end of sentence;
             empty text = pause (Premiere sometimes hides a word it did not recognize there)

  prproj_transcript_json.py PROJECT.prproj --liste
  prproj_transcript_json.py PROJECT.prproj OUTPUT.json [--sequence "name"]
"""
import argparse, base64, gzip, json, re, sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rough-cut" / "scripts"))
from extract_prproj_transcript import FB, TICKS_PER_SECOND as T


def documents(xml):
    """[(owner name, is it a sequence transcript?, bytes)] for each transcript."""
    seqs = set(re.findall(r'<Sequence ObjectUID="[^"]+".*?<Name>(.*?)</Name>', xml, re.S))
    out = []
    for m in re.finditer(r'<ExternallyProvidedTranscriptDocument ObjectID="(\d+)"(.*?)</ExternallyProvidedTranscriptDocument>', xml, re.S):
        td = re.search(r'<TranscriptData Encoding="base64"[^>/]*>(.*?)</TranscriptData>', m.group(2), re.S)
        if not td:
            continue
        b = base64.b64decode(re.sub(r"\s", "", td.group(1)))
        tc = re.search(r'<TranscriptClip ObjectID="(\d+)"(?:(?!</TranscriptClip>).)*TranscriptTextSegments ObjectRef="%s"' % m.group(1), xml, re.S)
        nom = "?"
        if tc:
            mc = re.search(r'<MasterClip ObjectUID="[^"]+"(?:(?!</MasterClip>).)*ObjectRef="%s"(?:(?!</MasterClip>).)*</MasterClip>' % tc.group(1), xml, re.S)
            if mc and re.search(r"<Name>(.*?)</Name>", mc.group(0)):
                nom = re.search(r"<Name>(.*?)</Name>", mc.group(0)).group(1)
        out.append((nom, nom in seqs, b))
    return out


def convert(b):
    fb = FB(b); r0 = fb.u32(0)
    doc = fb.deref(r0 + fb.fields(r0)[0]); df = fb.fields(doc)
    sp = fb.vector(doc + df[2])[0]; spf = fb.fields(sp)
    so = fb.deref(sp + spf[1])
    spid, spname = str(uuid.UUID(bytes=bytes(b[so + 4:so + 20]))), fb.string(sp + spf[0])
    segs = []
    for s in fb.vector(doc + df[0]):
        sf = fb.fields(s)
        words = []
        for w in fb.vector(s + sf[3]):
            wf = fb.fields(w) + [0] * 8
            words.append({"confidence": round(fb.f32(w + wf[3]), 6) if wf[3] else 1,
                          "duration": fb.i64(w + wf[1]) / T if wf[1] else 0, "eos": bool(wf[5]),
                          "start": fb.i64(w + wf[0]) / T if wf[0] else 0, "tags": [],
                          "text": fb.string(w + wf[2]) if wf[2] else "", "type": "word"})
        segs.append({"duration": fb.i64(s + sf[1]) / T, "language": fb.string(s + sf[4]), "speaker": spid,
                     "start": fb.i64(s + sf[0]) / T, "words": words})
    return {"language": segs[0]["language"], "segments": segs, "speakers": [{"id": spid, "name": spname}]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prproj"); ap.add_argument("sortie", nargs="?")
    ap.add_argument("--sequence"); ap.add_argument("--liste", action="store_true")
    a = ap.parse_args()
    docs = documents(gzip.open(a.prproj, "rb").read().decode("utf-8", "replace"))
    if a.liste or not a.sortie:
        for nom, synth, b in sorted(docs, key=lambda d: -len(d[2])):
            try:
                d = convert(b)
            except (IndexError, ValueError):
                continue  # empty transcript
            n = sum(1 for s in d["segments"] for w in s["words"] if w["text"].strip())
            if n:
                print(f"{'SEQUENCE' if synth else 'clip    '}  {n:6d} words  {nom}")
        return
    cand = [d for d in docs if d[1] and (not a.sequence or d[0] == a.sequence)]
    if not cand:
        sys.exit("no matching sequence transcript; see --liste")
    d = convert(max(cand, key=lambda x: len(x[2]))[2])
    json.dump(d, open(a.sortie, "w"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    W = [w for s in d["segments"] for w in s["words"] if w["text"].strip()]
    print(f"{len(d['segments'])} segments, {len(W)} words, {W[0]['start']:.2f}s -> {W[-1]['start'] + W[-1]['duration']:.2f}s")


if __name__ == "__main__":
    main()
