"""Applies text corrections (per segment) to a Premiere transcript (export JSON) while
keeping its timecodes. The text of a segment is rewritten in full; the word-by-word alignment
(difflib) does the rest:
  unchanged word (apart from case/punctuation) -> original timecode;
  replaced/merged words ("Is it" -> "Isn't it") -> duration redistributed over their range;
  added word -> placed in the neighboring Premiere pause if there is one (Premiere often hides
  the word it did not recognize there), otherwise shares the time of the previous word.
Typography: the language's no-break spaces (French rule: a space before double signs, after opening quotes), from
../languages/<code>.json. eos recomputed.

  appliquer_corrections.py ORIGINAL.json corrections.json OUTPUT.json [--voix PROJECT.prproj PATTERN] [--lang fr]
  --voix: clips each word to the bounds of the voice clip that carries it (PATTERN = text found in
  the names of the voice files, e.g. "Track") and checks that no word falls in a gap between two
  clips (exit 1 otherwise).
  --lang: language code (default: language of ORIGINAL.json, else en).
  corrections.json: {"<segment index>": "full corrected text of the segment", ...}
"""
import json,re,sys,difflib,copy
import lang
NB=' '
PUNCT_AFTER=set()   # tokens made only of these (plus . , …) are glued to the previous word
NBSP_BEFORE=''      # characters that take a no-break space before them
NBSP_AFTER=''       # characters that take a no-break space after them
EOS_CLOSERS=''      # characters allowed after . ! ? … for the word to still end a sentence
def configure(data):
    global PUNCT_AFTER,NBSP_BEFORE,NBSP_AFTER,EOS_CLOSERS
    ty=data['typography']
    PUNCT_AFTER=set(ty['detached_punct']); NBSP_BEFORE=ty['nbsp_before']; NBSP_AFTER=ty['nbsp_after']
    EOS_CLOSERS=data['eos_closers']
def tokenize(text):
    raw=text.split()
    out=[]
    for t in raw:
        if out and (all(c in PUNCT_AFTER or c in '.,…' for c in t)):
            out[-1]=out[-1]+(NB if t[0] in NBSP_BEFORE else '')+t
        elif out and len(out[-1])==1 and out[-1] in NBSP_AFTER:
            out[-1]=out[-1]+NB+t
        else: out.append(t)
    return out
def typo(t):
    # language typography: no-break space before NBSP_BEFORE characters, after NBSP_AFTER ones
    if NBSP_BEFORE and re.search('['+re.escape(NBSP_BEFORE)+']',t):
        t=re.sub(r'\s*(['+re.escape(NBSP_BEFORE)+'])',lambda m:NB+m.group(1),t)
    for c in NBSP_AFTER:
        t=t.replace(c+' ',c+NB)
    t=re.sub(r'^'+NB,'',t)
    return t
def norm(t):
    t=t.lower().replace('’',"'")
    t=re.sub(r"[^\w'\-]",'',t)
    return t
def apply_seg(seg,new_text):
    items=seg['words']
    wi=[k for k,w in enumerate(items) if w['text'].strip()]
    old=[items[k] for k in wi]
    new=[typo(t) for t in tokenize(new_text)]
    a=[norm(w['text']) for w in old]; b=[norm(t) for t in new]
    sm=difflib.SequenceMatcher(None,a,b,autojunk=False)
    ops=sm.get_opcodes()
    # pure insertions: if Premiere marked a pause right at that spot, the inserted words
    # take the place of the pause (Premiere often hides a word it did not recognize there);
    # otherwise they share the time of the neighboring word
    pauses=[w for w in items if not w['text'].strip()]
    used_pauses=[]
    fixed=[]
    k=0; ops=list(ops)
    while k<len(ops):
        tag,i1,i2,j1,j2=ops[k]
        if tag!='insert': fixed.append(ops[k]); k+=1; continue
        t0=old[i1-1]['start']+old[i1-1]['duration'] if i1>0 else seg['start']
        t1=old[i1]['start'] if i1<len(old) else t0+1
        gap=[p for p in pauses if p['start']>=t0-1e-6 and p['start']+p['duration']<=t1+1e-6 and p['duration']>=0.15*(j2-j1)]
        if gap:
            fixed.append(('insert_pause',i1,i2,j1,j2,gap[0])); used_pauses.append(gap[0]); k+=1; continue
        # merge with the previous block (or the next one at the start)
        if fixed and fixed[-1][0] in ('equal','replace') and fixed[-1][2]>fixed[-1][1]:
            t,a1,a2,b1,b2=fixed.pop()[:5]
            if t=='equal' and a2-a1>1: fixed.append(('equal',a1,a2-1,b1,b2-1)); a1,b1=a2-1,b2-1
            fixed.append(('replace',a1,a2,b1,j2)); k+=1; continue
        t,a1,a2,b1,b2=ops[k+1]
        if t=='equal' and a2-a1>1:
            fixed.append(('replace',i1,a1+1,j1,b1+1)); ops[k+1]=('equal',a1+1,a2,b1+1,b2)
        else:
            fixed.append(('replace',i1,a2,j1,b2)); k+=1
        k+=1
    out=[]; dropped_ranges=[]
    for blk in fixed:
        tag,i1,i2,j1,j2=blk[:5]
        if tag=='insert_pause':
            p=blk[5]; s0,s1=p['start'],p['start']+p['duration']
            L=[len(t) for t in new[j1:j2]]; tot=sum(L); c=s0
            for y,l in zip(range(j1,j2),L):
                dd=(s1-s0)*l/tot
                out.append({"confidence":0.5,"duration":dd,"eos":False,"start":c,"tags":[],"text":new[y],"type":"word"}); c+=dd
            continue
        if tag=='equal':
            for x,y in zip(range(i1,i2),range(j1,j2)):
                w=copy.deepcopy(old[x]); w['text']=new[y]; out.append(w)
        elif tag=='delete':
            dropped_ranges.append((old[i1]['start'],old[i2-1]['start']+old[i2-1]['duration']))
        else:
            if i2==i1: raise SystemExit(f"insertion without time in segment: {new[j1:j2]}")
            s0=old[i1]['start']; s1=old[i2-1]['start']+old[i2-1]['duration']
            L=[len(t) for t in new[j1:j2]]; tot=sum(L); c=s0
            conf=min(w['confidence'] for w in old[i1:i2])
            for y,l in zip(range(j1,j2),L):
                d=(s1-s0)*l/tot
                out.append({"confidence":conf,"duration":d,"eos":False,"start":c,"tags":[],"text":new[y],"type":"word"}); c+=d
            if i2-i1>1: dropped_ranges.append((s0,s1))
    for w in out:
        w['eos']=bool(re.search(r'[.!?…]['+re.escape(EOS_CLOSERS)+r']*$',w['text']))
    keep=[p for p in pauses if p not in used_pauses and not any(r0-1e-6<=p['start'] and p['start']+p['duration']<=r1+1e-6 for r0,r1 in dropped_ranges)]
    seg['words']=sorted(out+keep,key=lambda w:w['start'])
    return ops
if __name__=='__main__':
    lang_arg=None
    if '--lang' in sys.argv:
        i=sys.argv.index('--lang'); lang_arg=sys.argv[i+1]; del sys.argv[i:i+2]
    d=json.load(open(sys.argv[1])); corr=json.load(open(sys.argv[2]))
    configure(lang.load(lang.resolve(lang_arg,d.get('language'))))
    for k,txt in corr.items():
        apply_seg(d['segments'][int(k)],txt)
    # ⚠️ No pauses in the delivered file: Premiere re-reads an item with empty text as a WORD
    # (subtitles "…", a sentence that starts at the beginning of a long gap between two reels).
    # They only serve to house the added words, above. Segment bounds = real words.
    clips=None
    if '--voix' in sys.argv:
        from second_avis_whisper import clips_voix
        i=sys.argv.index('--voix'); clips=clips_voix(sys.argv[i+1],sys.argv[i+2])
    hors=[]
    for s in d['segments']:
        s['words']=[w for w in s['words'] if w['text'].strip()]
        for w in s['words'] if clips else []:
            # Premiere sometimes overshoots by 0.1-0.2 s on the edge of a clip
            a,b=w['start'],w['start']+w['duration']
            c0,c1=min(((c[0],c[1]) for c in clips),key=lambda c:0 if c[0]<=a<c[1] else min(abs(a-c[0]),abs(b-c[1])))
            na,nb=max(a,c0),min(b,c1)
            if nb<=na: hors.append((round(a,2),w['text'])); continue
            if (na,nb)!=(a,b):
                print('clipped to the clip edge:',w['text'],round(a,2),round(b,2),'->',round(na,2),round(nb,2))
                w['start'],w['duration']=na,nb-na
        s['start']=s['words'][0]['start']
        s['duration']=s['words'][-1]['start']+s['words'][-1]['duration']-s['start']
    if hors: sys.exit(f"words outside every voice clip: {hors}")
    json.dump(d,open(sys.argv[3],'w'),ensure_ascii=False,sort_keys=True,separators=(",",":"))
    print(len(corr),'segments corrected')
