#!/usr/bin/env python3
"""Faithful email captures, ready to animate: a JSON of emails -> one PNG per email + the
coordinates of key phrases (to zoom, highlight, strike through in a scene).

Made for videos that tell the story of an exchange (dispute, customer service, application:
proof on screen). The text of the emails is copied VERBATIM from the source (the mailbox): this
script rewrites nothing, it only lays out.

    python3 mail-cards.py mails.json [--out <folder>] [--only m05,m09] [--planche]

JSON format (paths relative to the JSON). The keys are French, they are the contract:

    {"moi": "the author",
     "flou": ["Camille", "address@example.com"],     # blurred everywhere, unrecoverable
     "mails": [{
        "id": "m03", "slug": "reply-1", "temps": 2,
        "de": {"nom": "Camille (Example Support)", "adresse": "support@example.zendesk.com"},
        "a": "moi",                                   # or a list of addresses
        "cc": ["press@example.com"],                  # optional
        "date": "2026-09-09T23:31:47+02:00",          # Paris time displayed as is
        "objet": "Submission from Get Help",
        "texte": "Hello,\\n\\n…",                      # *bold* allowed
        "html": "src/m01.html",                       # instead of texte: the original HTML email
        "zendesk": {"langue": "fr", "ticket": "Support ticket #26644856: …",
                    "auteur": "Camille", "horodatage": "9 Sept. 2026, 2:31 PM UTC-7"},
        "cles": {"disabled": "The account has been disabled",
                 "seam": {"texte": "Hello,", "n": 2}}   # n-th occurrence
     }]}

Outputs, for each email: `<id>-<slug>.png` (card alone, transparent background, 2x) and
`<id>-<slug>.boxes.json`: {key: {texte, x, y, w, h, lignes: [[x,y,w,h]…]}} in pixels of the PNG.
A phrase that cannot be found fails the email (exit code 1): the key must be verbatim.
"""
import argparse
import html as H
import json
import re
import sys
from datetime import datetime
from pathlib import Path

JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]  # fr-ok: French date display (data)
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]  # fr-ok: French date display (data)
LARGEUR = 1100
ECHELLE = 2

ZD = {
    # French Zendesk boilerplate, reproduced as the real email shows it (data)
    "fr": ("##- Veuillez saisir votre réponse au-dessus de cette ligne -##",  # fr-ok
           "Vous pouvez ajouter une réponse en répondant à cet e-mail. Assurez-vous d'utiliser la même "  # fr-ok
           "adresse e-mail que celle utilisée pour nous contacter la première fois.",  # fr-ok
           "Mise à jour par : "),  # fr-ok
    "en": ("##- Please type your reply above this line -##",
           "You can add a response by replying to this email. Please be sure to reply with the same "
           "email address that you used to originally contact us.",
           ""),
}

CSS = """
*{box-sizing:border-box}
html,body{margin:0;background:transparent}
body{padding:40px;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text',sans-serif;color:#1d1d1f}
.carte{width:%(w)dpx;background:#fff;border-radius:18px;box-shadow:0 2px 6px rgba(0,0,0,.08),0 18px 48px rgba(0,0,0,.14);overflow:hidden}
.tete{padding:30px 38px 22px;border-bottom:1px solid #e6e6e8}
.objet{font-size:25px;font-weight:650;line-height:1.3;margin:0 0 20px;letter-spacing:-.01em}
.ligne{display:flex;align-items:flex-start;gap:16px}
.avatar{flex:0 0 48px;height:48px;border-radius:50%%;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:600;font-size:21px}
.qui{flex:1;min-width:0;font-size:16px;line-height:1.45}
.nom{font-weight:650}
.adr{color:#6e6e73}
.dest{color:#6e6e73;font-size:15px}
.date{color:#6e6e73;font-size:15px;white-space:nowrap;padding-top:2px}
.corps{padding:28px 38px 36px;font-size:17px;line-height:1.58;white-space:pre-wrap;word-wrap:break-word}
.corps.html{white-space:normal;padding:18px 0 10px}
.zd-garde{color:#9a9a9e;font-size:13px;margin-bottom:14px}
.zd-ticket{color:#0068a5;font-weight:600;margin-bottom:6px}
.zd-aide{color:#6e6e73;font-size:14px;line-height:1.5;margin-bottom:22px}
.zd-sep{border-top:1px solid #e6e6e8;margin:0 0 20px}
.zd-auteur{font-weight:650;margin-bottom:10px}
.flou{filter:blur(7px);color:#1d1d1f;user-select:none}
"""

COULEURS = ["#0061fe", "#6e56cf", "#1a7f5a", "#b4552d", "#8a6d00", "#c2185b"]


def date_fr(iso):
    d = datetime.fromisoformat(iso)
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}, {d.hour:02d}:{d.minute:02d}"


def gras(s):
    return re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", s)


def page(m, base, moi, flou=()):
    de = m["de"]
    # the avatar initial must not give away a blurred name ("Camille (Example Support)" -> E)
    reste = de.get("nom") or de.get("adresse") or "?"
    for f in flou:
        reste = reste.replace(f, "")
    initiale = (re.findall(r"[A-Za-z\u00c0-\u00ff]", reste) or ["?"])[0].upper()
    couleur = COULEURS[sum(map(ord, de.get("adresse", ""))) % len(COULEURS)]
    a = m.get("a", "moi")
    dest = "à " + (moi if a == "moi" else ", ".join(a if isinstance(a, list) else [a]))  # fr-ok: card UI is French
    if m.get("cc"):
        dest += "<br>cc : " + ", ".join(H.escape(x) for x in m["cc"])
    tete = f"""<div class="tete"><div class="objet">{H.escape(m['objet'])}</div>
<div class="ligne"><div class="avatar" style="background:{couleur}">{H.escape(initiale)}</div>
<div class="qui"><span class="nom">{H.escape(de.get('nom', ''))}</span>
<span class="adr">&lt;{H.escape(de.get('adresse', ''))}&gt;</span><div class="dest">{dest}</div></div>
<div class="date">{date_fr(m['date'])}</div></div></div>"""
    if m.get("html"):
        corps = '<div class="corps html"><div id="hote"></div></div>'
        brut = (base / m["html"]).read_text(encoding="utf-8")
    else:
        zd = m.get("zendesk")
        interieur = ""
        if zd:
            garde, aide, prefixe = ZD[zd.get("langue", "en")]
            interieur += f'<div class="zd-garde">{H.escape(garde)}</div>'
            interieur += f'<div class="zd-ticket">{H.escape(zd["ticket"])}</div>'
            if zd.get("auteur"):
                interieur += f'<div class="zd-aide">{H.escape(aide)}</div><div class="zd-sep"></div>'
                interieur += f'<div class="zd-auteur">{H.escape(prefixe + zd["auteur"])}, {H.escape(zd["horodatage"])}</div>'
        interieur += gras(H.escape(m["texte"]).replace("\\*", "*"))
        corps = f'<div class="corps">{interieur}</div>'
        brut = None
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS % {'w': LARGEUR}}</style></head>
<body><div class="carte">{tete}{corps}</div></body></html>"""
    return doc, brut


JS_FLOU = """(noms) => {
  const racines = [document.querySelector('.carte')];
  const h = document.querySelector('#hote'); if (h && h.shadowRoot) racines.push(h.shadowRoot);
  const esc = s => s.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
  const re = new RegExp(noms.map(esc).join('|'), 'g');
  for (const r of racines) {
    const w = document.createTreeWalker(r, NodeFilter.SHOW_TEXT); const nodes = [];
    while (w.nextNode()) nodes.push(w.currentNode);
    for (const n of nodes) {
      if (!re.test(n.data)) continue; re.lastIndex = 0;
      const frag = document.createDocumentFragment(); let last = 0, x;
      while ((x = re.exec(n.data))) {
        frag.append(n.data.slice(last, x.index));
        const s = document.createElement('span'); s.className = 'flou';
        s.style.cssText = 'filter:blur(7px);user-select:none';
        s.textContent = x[0].replace(/[A-Za-z0-9]/g, (c, i) => 'Hxmkaelrnobt'[(i * 7 + x.index) % 12]);
        frag.append(s); last = re.lastIndex;
      }
      frag.append(n.data.slice(last)); n.replaceWith(frag);
    }
  }
}"""

JS_BOITES = """(cles) => {
  const carte = document.querySelector('.carte').getBoundingClientRect();
  const racines = [document.querySelector('.carte')];
  const h = document.querySelector('#hote'); if (h && h.shadowRoot) racines.push(h.shadowRoot);
  const nodes = [];
  for (const r of racines) { const w = document.createTreeWalker(r, NodeFilter.SHOW_TEXT);
    while (w.nextNode()) nodes.push(w.currentNode); }
  let plein = '', pos = [];
  for (const n of nodes) { pos.push([plein.length, n]); plein += n.data; }
  const norm = s => s.replace(/\\s+/g, ' ');
  const ouOrig = (texte, occ) => {
    // whitespace-tolerant search: compare after normalizing, then recover the original index
    const cible = norm(texte); let map = [], nt = '';
    for (let i = 0; i < plein.length; i++) { const c = /\\s/.test(plein[i]) ? ' ' : plein[i];
      if (c === ' ' && nt.endsWith(' ')) continue; nt += c; map.push(i); }
    let k = -1; for (let o = 0; o < occ; o++) { k = nt.indexOf(cible, k + 1); if (k < 0) return null; }
    return [map[k], map[k + cible.length - 1] + 1];
  };
  const noeud = i => { let lo = 0; for (let j = 0; j < pos.length; j++) { if (pos[j][0] <= i) lo = j; else break; }
    return [pos[lo][1], i - pos[lo][0]]; };
  const out = {};
  for (const [cle, spec] of Object.entries(cles)) {
    const texte = typeof spec === 'string' ? spec : spec.texte, occ = typeof spec === 'string' ? 1 : (spec.n || 1);
    const r = ouOrig(texte, occ); if (!r) { out[cle] = null; continue; }
    const [n0, o0] = noeud(r[0]); const [n1, o1] = noeud(r[1] - 1);
    const rg = document.createRange(); rg.setStart(n0, o0); rg.setEnd(n1, o1 + 1);
    const rects = [...rg.getClientRects()].filter(q => q.width > 1);
    const lignes = []; for (const q of rects) { const l = lignes.find(L => Math.abs(L.y - q.y) < 4);
      if (l) { const x2 = Math.max(l.x + l.w, q.x + q.width); l.x = Math.min(l.x, q.x); l.w = x2 - l.x; l.h = Math.max(l.h, q.height); }
      else lignes.push({x: q.x, y: q.y, w: q.width, h: q.height}); }
    const X = Math.min(...lignes.map(l => l.x)), Y = Math.min(...lignes.map(l => l.y));
    const X2 = Math.max(...lignes.map(l => l.x + l.w)), Y2 = Math.max(...lignes.map(l => l.y + l.h));
    out[cle] = {texte, x: X - carte.x, y: Y - carte.y, w: X2 - X, h: Y2 - Y,
                lignes: lignes.map(l => [l.x - carte.x, l.y - carte.y, l.w, l.h])};
  }
  return out;
}"""


def rendre(mails, base, out, moi, flou):
    from playwright.sync_api import sync_playwright
    erreurs = 0
    faits = []
    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(viewport={"width": LARGEUR + 80, "height": 900}, device_scale_factor=ECHELLE)
        # no tracking pixel or outgoing link: block everything that is not a static image
        ctx.route(re.compile(r".*"), lambda r: r.abort() if (
            r.request.resource_type not in ("document", "image", "font", "stylesheet")
            or re.search(r"links\.|/e/eo|track|click", r.request.url)) else r.continue_())
        pg = ctx.new_page()
        for m in mails:
            doc, brut = page(m, base, moi, flou)
            pg.set_content(doc, wait_until="load")
            if brut is not None:
                brut = re.sub(r"<img[^>]*(?:links\.[a-z0-9-]+\.com|/e/eo|/open\?|/track)[^>]*>", "", brut)
                brut = re.sub(r'href="[^"]*"', 'href="#"', brut)
                pg.evaluate("(h) => { const s = document.querySelector('#hote').attachShadow({mode:'open'}); s.innerHTML = h; }", brut)
                pg.wait_for_load_state("networkidle")
                pg.wait_for_timeout(400)
            if flou:
                pg.evaluate(JS_FLOU, flou)
            boites = pg.evaluate(JS_BOITES, m.get("cles", {}))
            manquantes = [k for k, v in boites.items() if v is None]
            nom = f"{m['id']}-{m['slug']}"
            pg.locator(".carte").screenshot(path=str(out / f"{nom}.png"), omit_background=True)
            for v in boites.values():
                if v:
                    for k in ("x", "y", "w", "h"):
                        v[k] = round(v[k] * ECHELLE)
                    v["lignes"] = [[round(c * ECHELLE) for c in l] for l in v["lignes"]]
            (out / f"{nom}.boxes.json").write_text(json.dumps(boites, ensure_ascii=False, indent=1), encoding="utf-8")
            etat = "ok" if not manquantes else "KEYS NOT FOUND: " + ", ".join(manquantes)
            print(f"  {nom}.png  {len(boites) - len(manquantes)} keys  {etat}")
            erreurs += bool(manquantes)
            faits.append(out / f"{nom}.png")
        nav.close()
    return erreurs, faits


def planche(fichiers, sortie):
    from PIL import Image
    ims = [Image.open(f) for f in fichiers]
    col = 4
    lw = 700
    th = [round(im.height * lw / im.width) for im in ims]
    lignes = [max(th[i:i + col]) for i in range(0, len(ims), col)]
    feuille = Image.new("RGB", (col * (lw + 30) + 30, sum(lignes) + 30 * (len(lignes) + 1)), (228, 226, 222))
    y = 30
    for r, h in enumerate(lignes):
        for c in range(col):
            i = r * col + c
            if i >= len(ims):
                break
            t = ims[i].convert("RGBA").resize((lw, th[i]))
            feuille.paste(t, (30 + c * (lw + 30), y), t)
        y += h + 30
    feuille.save(sortie, quality=85)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--out")
    ap.add_argument("--only")
    ap.add_argument("--planche", action="store_true")
    a = ap.parse_args()
    src = Path(a.json).resolve()
    data = json.loads(src.read_text(encoding="utf-8"))
    out = Path(a.out).resolve() if a.out else src.parent
    out.mkdir(parents=True, exist_ok=True)
    mails = data["mails"]
    if a.only:
        garder = set(a.only.split(","))
        mails = [m for m in mails if m["id"] in garder]
    erreurs, faits = rendre(mails, src.parent, out, data.get("moi", "moi"), data.get("flou", []))
    if a.planche and faits:
        planche(faits, out / "planche-mails.jpg")
        print(f"  contact sheet: {out / 'planche-mails.jpg'}")
    sys.exit(1 if erreurs else 0)


if __name__ == "__main__":
    main()
