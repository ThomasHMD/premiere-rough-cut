#!/usr/bin/env python3
"""Checks, in a .prproj (or the latest auto-save), what Premiere REALLY kept after a
transcript re-import and a caption generation (route B).

Premiere shows no error if the import did not take: only reading the project proves it.
  - sequence transcript: words, typed pauses (f6 = 3, what Premiere creates itself) and
    UNTYPED empty items (re-read as words: the captions step over them -> text in the gaps);
  - caption tracks: number, gaps > 1 s between two captions, captions > 5 s.
Reference: a project with a native Premiere transcript (typed pauses) shows many gaps > 1 s;
a project where no gap exceeds 0.5 s has its captions glued end to end.

  verifier_import.py PROJECT.prproj [--autour SECONDS]
"""
import argparse, base64, gzip, re, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rough-cut" / "scripts"))
from extract_prproj_transcript import FB, TICKS_PER_SECOND as T
from prproj_transcript_json import documents


def mots_sequence(xml):
    b = max((d for d in documents(xml) if d[1]), key=lambda d: len(d[2]))[2]
    fb = FB(b); r0 = fb.u32(0); doc = fb.deref(r0 + fb.fields(r0)[0]); df = fb.fields(doc)
    out = []
    for s in fb.vector(doc + df[0]):
        for w in fb.vector(s + fb.fields(s)[3]):
            wf = fb.fields(w) + [0] * 8
            out.append((fb.i64(w + wf[0]) / T if wf[0] else 0, fb.i64(w + wf[1]) / T if wf[1] else 0,
                        fb.string(w + wf[2]) if wf[2] else "", b[w + wf[6]] if wf[6] else None))
    return out


def texte(b):
    best = None
    for o in range(len(b) - 4):
        n = struct.unpack_from("<I", b, o)[0]
        if 0 < n < 400 and o + 4 + n < len(b) and b[o + 4 + n] == 0:
            try:
                s = b[o + 4:o + 4 + n].decode("utf-8")
            except UnicodeDecodeError:
                continue
            if s.replace(" ", " ").isprintable() and s != "Monaco":
                best = s
    return best


def sous_titres(xml):
    objs = {m.group(2): m.group(0) for m in re.finditer(r'<(\w+) ObjectID="(\d+)"[^>]*>.*?</\1>', xml, re.S)}
    # deduplicated binary data: an identical block only carries the BinaryHash
    bh = dict(re.findall(r'BinaryHash="([^"]+)">([^<]+)<', xml))
    pistes = []
    for m in re.finditer(r'<CaptionDataClipTrack ObjectUID="([^"]+)".*?</CaptionDataClipTrack>', xml, re.S):
        caps = []
        for r in re.findall(r'<TrackItem Index="\d+" ObjectRef="(\d+)"', m.group(0)):
            it = objs.get(r, "")
            if "CaptionDataClipTrackItem" not in it[:40]:
                continue
            a = int(re.search(r"<Start>(-?\d+)</Start>", it).group(1)) / T
            e = int(re.search(r"<End>(\d+)</End>", it).group(1)) / T
            blk = objs[re.search(r'BlockVectorItem Index="0" ObjectRef="(\d+)"', it).group(1)]
            h = re.search(r'BinaryHash="([^"]+)"', blk).group(1)
            caps.append((a, e, texte(base64.b64decode(re.sub(r"\s", "", bh[h])))))
        if caps:
            pistes.append(sorted(caps))
    return pistes


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("prproj"); ap.add_argument("--autour", type=float)
    a = ap.parse_args()
    xml = gzip.open(a.prproj, "rb").read().decode("utf-8", "replace")
    W = mots_sequence(xml)
    nt = sum(1 for w in W if not w[2].strip() and w[3] is None)
    print(f"sequence transcript: {sum(1 for w in W if w[2].strip())} words, "
          f"{sum(1 for w in W if w[3] == 3)} typed pauses, {nt} UNTYPED empty items"
          + ("  <- old import with pauses: captions in the gaps" if nt else ""))
    tc = lambda s: f"{int(s // 60)}:{s % 60:05.2f}"
    for c in sous_titres(xml):
        g = [c[i + 1][0] - c[i][1] for i in range(len(c) - 1)]
        print(f"caption track: {len(c)} captions, gaps > 1 s: {sum(x > 1 for x in g)}, "
              f"captions > 5 s: {sum(e - s > 5 for s, e, _ in c)}")
        for s, e, t in c:
            if a.autour is not None and abs(s - a.autour) < 20:
                print(f"   {tc(s)} -> {tc(e)}  {t}")


if __name__ == "__main__":
    main()
