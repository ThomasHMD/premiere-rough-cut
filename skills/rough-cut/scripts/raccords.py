"""Air at the join: the continuous blank around a cut point, measured in the sound of the edit.

On a real video the editor rejected a rough cut at the first join, "you cut a sentence that
is not finished": take cuts left only 0.22 s between the last speech of a clip and the first
of the next, against 0.55 s on the silence cuts he approves.
Speech mask at 15% of the RMS p95 (10 ms windows), islands shorter than 0.07 s discarded (a
tongue click splits a 2 s silence in two), gaps shorter than 0.09 s filled in (a consonant
closure is not a breath).
Used by montage_qc.py (one clip) and qc_assemblage.py (an assembled part).
"""
import numpy as np

HOP = 0.01


def rms(sig, sr):
    hop = int(sr * HOP)
    n = len(sig) // hop
    x = np.asarray(sig[: n * hop], dtype=np.float32).reshape(n, hop)
    return np.sqrt((x ** 2).mean(axis=1))


def masque(r):
    """Speech (True) / blank (False) per 10 ms window, from the RMS."""
    par = r > float(np.percentile(r, 95)) * 0.15
    for seuil, val in ((0.07, False), (0.09, True)):
        i = 0
        while i < len(par):
            if par[i] is not np.bool_(val):
                i += 1
                continue
            j = i
            while j < len(par) and par[j] == np.bool_(val):
                j += 1
            if (j - i) * HOP < seuil and (val is False or i > 0) and (val is False or j < len(par)):
                par[i:j] = not val
            i = j
    return par


def air(par, t):
    """Blanc continu autour de l'instant t (s) du montage (0 si t tombe en pleine parole)."""
    i = min(len(par) - 1, max(0, int(t / HOP)))
    trouve = None
    for d in range(0, 31):                      # the join can fall within ±0.3 s
        for k in (i - d, i + d):
            if 0 < k < len(par) - 1 and not par[k]:
                trouve = k
                break
        if trouve is not None:
            break
    if trouve is None:
        return 0.0
    lo = hi = trouve
    while lo > 0 and not par[lo - 1]:
        lo -= 1
    while hi < len(par) - 1 and not par[hi + 1]:
        hi += 1
    return (hi + 1 - lo) * HOP
