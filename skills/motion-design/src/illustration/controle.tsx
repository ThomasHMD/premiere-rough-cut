// "ControleTexte" composition: all the scenes of a plan end to end, and for every rendered frame a readout of the text
// on screen, in the browser, on the real layout (font loaded). Launched by
// overlays/scripts/controle-texte.py, which reads the "CONTROLE {…}" lines of the console.
// Born from editing feedback: text running off a retro terminal screen, a title eaten by
// the edge of a funnel, empty retro screens lasting several seconds. Three readouts:
//   DEBORDE: text goes past the frame;
//   MORD: text straddling the edge of a drawn shape (partly inside, partly outside);
//   CHEVAUCHE: two texts on top of each other;
//   COUPE: text clipped by a mask (overflow hidden) for 1 s or more (an entrance rising behind a mask is allowed);
// plus `contenu` (visible texts and images, decor excluded) for the "empty screen" check.
// Decor (retro terminal banner, VCR PLAY label): marked data-decor, it does not count as content.
import React, { useLayoutEffect, useRef } from "react";
import { AbsoluteFill, Series, continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";
import { Scene } from "./scenes/Scene";

export type ControleScene = { id: string; component: string; data: Record<string, any>; cues: number[]; durationSec: number; alpha?: boolean };
export type ControleProps = { fps: number; width: number; height: number; scenes: ControleScene[] };
export const controleDefaults: ControleProps = { fps: 30, width: 1920, height: 1080, scenes: [] };
export const controleFrames = (p: ControleProps) => p.scenes.reduce((a, s) => a + Math.max(1, Math.round(s.durationSec * p.fps)), 0);

type Boite = { x: number; y: number; w: number; h: number };
const inter = (a: Boite, b: Boite) => Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));

function releve(root: HTMLElement, W: number, H: number) {
  const R = root.getBoundingClientRect();
  const s = R.width / W;
  if (!(s > 0.01)) return { fautes: [] as string[], contenu: -1 };   // not laid out yet
  const box = (r: DOMRect): Boite => ({ x: (r.left - R.left) / s, y: (r.top - R.top) / s, w: r.width / s, h: r.height / s });
  const opa = (el: Element | null) => {
    let o = 1;
    for (let e = el; e && e !== root.parentElement; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === "none" || cs.visibility === "hidden") return 0;
      o *= parseFloat(cs.opacity || "1");
    }
    return o;
  };
  // the visible part of a box: clipped by each overflow-hidden ancestor (the big number of the chapter card
  // rises behind a mask: without this, a false DEBORDE); null if none of it is visible
  const visible = (el: Element, b: Boite): Boite | null => {
    let v = b;
    for (let e: Element | null = el; e && e !== root.parentElement; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.overflow === "visible" && cs.overflowX === "visible" && cs.overflowY === "visible") continue;
      const c = box(e.getBoundingClientRect());
      const x0 = Math.max(v.x, c.x), y0 = Math.max(v.y, c.y), x1 = Math.min(v.x + v.w, c.x + c.w), y1 = Math.min(v.y + v.h, c.y + c.h);
      if (x1 - x0 < 2 || y1 - y0 < 2) return null;
      v = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
    }
    return v;
  };
  const textes: { el: Element; b: Boite; decor: boolean; t: string; plein?: string }[] = [];
  const coupes: string[] = [];   // text clipped by a mask: a fault if it lasts (controle-texte.py), not during an animated entrance
  // in height, the font box goes past the line (line height 1.08 under an entrance mask) without cutting any
  // letter: only a height cut of more than 30% counts; in width, 3% is enough (a line too long)
  const note = (t: string, b0: Boite, b: Boite | null, decor: boolean) => {
    if (decor || !b) return;
    const fx = b.w / b0.w, fy = b.h / b0.h;
    if (fx < 0.97 || fy < 0.7) coupes.push(`COUPE « ${t} » (${Math.round(100 * fx * fy)} % visible)`);   // fr-ok
  };
  root.querySelectorAll("svg[data-texte]").forEach((el) => {
    if (opa(el) < 0.3) return;
    const b0 = box(el.getBoundingClientRect());
    const b = visible(el, b0);
    note(el.getAttribute("data-texte") ?? "", b0, b, !!el.closest("[data-decor]"));
    if (b && b.w >= 2) textes.push({ el, b, decor: !!el.closest("[data-decor]"), t: el.getAttribute("data-texte") ?? "" });
  });
  const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = tw.nextNode(); n; n = tw.nextNode()) {
    const txt = (n.textContent ?? "").trim();
    const el = n.parentElement;
    if (!txt || !el || el.closest("svg")) continue;
    if (opa(el) < 0.3) continue;
    const rg = document.createRange();
    rg.selectNodeContents(n);
    const b0 = box(rg.getBoundingClientRect());
    const b = Number.isFinite(b0.x) ? visible(n.parentElement as Element, b0) : null;
    if (Number.isFinite(b0.x)) note(txt.slice(0, 40), b0, b, !!el.closest("[data-decor]"));
    if (b && b.w >= 2) textes.push({ el, b, decor: !!el.closest("[data-decor]"), t: txt.slice(0, 40), plein: txt });
  }
  const fautes: string[] = [];
  for (const x of textes)
    if (x.b.x < -4 || x.b.y < -4 || x.b.x + x.b.w > W + 4 || x.b.y + x.b.h > H + 4) fautes.push(`DEBORDE « ${x.t} » (${Math.round(x.b.x)}, ${Math.round(x.b.y)}, ${Math.round(x.b.w)} × ${Math.round(x.b.h)})`);   // fr-ok
  // drawn shapes (svg), excluding the terminal font
  const formes: { el: SVGGeometryElement; b: Boite }[] = [];
  root.querySelectorAll("path, rect, polygon, circle, ellipse").forEach((el) => {
    if (el.closest("svg[data-texte]")) return;
    const cs = getComputedStyle(el);
    if (!cs.fill || cs.fill === "none" || /rgba\([^)]*,\s*0\)$/.test(cs.fill) || parseFloat(cs.fillOpacity || "1") < 0.05) return;
    if (opa(el) < 0.3) return;
    const b = box(el.getBoundingClientRect());
    const a = b.w * b.h;
    if (a > 3000 && a < 0.5 * W * H) formes.push({ el: el as SVGGeometryElement, b });
  });
  // a text on its own opaque plate (a "You are here" label) stays readable on top of a shape
  const plaque = (el: Element, b: Boite) => {
    for (let e: Element | null = el; e && e !== root; e = e.parentElement) {
      const c = box(e.getBoundingClientRect());
      if (c.w * c.h > 0.25 * W * H) return false;
      const m = getComputedStyle(e).backgroundColor.match(/rgba?\(([^)]+)\)/);
      const al = m ? (m[1].split(",")[3] === undefined ? 1 : parseFloat(m[1].split(",")[3])) : 0;
      if (al > 0.8 && c.x <= b.x + 1 && c.y <= b.y + 1 && c.x + c.w >= b.x + b.w - 1 && c.y + c.h >= b.y + b.h - 1) return true;
    }
    return false;
  };
  for (const x of textes) {
    if (x.decor || plaque(x.el, x.b)) continue;
    for (const f of formes) {
      if (!inter(x.b, f.b)) continue;
      const m = f.el.getScreenCTM()?.inverse();
      if (!m) continue;
      let dedans = 0, total = 0;
      for (let i = 0; i < 5; i++)
        for (let j = 0; j < 3; j++) {
          const px = x.b.x + x.b.w * (0.12 + 0.19 * i), py = x.b.y + x.b.h * (0.2 + 0.3 * j);
          const p = new DOMPoint(R.left + px * s, R.top + py * s).matrixTransform(m);
          total++;
          if (f.el.isPointInFill(p)) dedans++;
        }
      if (dedans > 0 && dedans < total) { fautes.push(`MORD « ${x.t} » (${dedans}/${total} dans une forme)`); break; }   // fr-ok
    }
  }
  const vis = textes.filter((x) => !x.decor);
  for (let i = 0; i < vis.length; i++)
    for (let j = i + 1; j < vis.length; j++) {
      const a = vis[i], b = vis[j];
      if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const o = inter(a.b, b.b);
      if (o > 0.25 * Math.min(a.b.w * a.b.h, b.b.w * b.b.h)) fautes.push(`CHEVAUCHE « ${a.t} » / « ${b.t} »`);   // fr-ok
    }
  let images = 0;
  root.querySelectorAll("img, video, canvas").forEach((el) => {
    const b = box(el.getBoundingClientRect());
    if (opa(el) >= 0.3 && b.w * b.h > 0.02 * W * H && inter(b, { x: 0, y: 0, w: W, h: H }) > 0.01 * W * H) images++;
  });
  // `lus`: texts fully visible, for the reading time (controle-texte.py, LECTURE: text not on screen
  // long enough, there is no time to read it)
  return { fautes: [...new Set(fautes)], coupes: [...new Set(coupes)], contenu: vis.length + images, lus: [...new Set(vis.map((x) => x.plein ?? x.t))] };
}

const Releve: React.FC<{ id: string; debut: number; alpha: boolean; children: React.ReactNode }> = ({ id, debut, alpha, children }) => {
  const ref = useRef<HTMLDivElement>(null);
  const f = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  useLayoutEffect(() => {
    const h = delayRender("text readout");
    // the layout may arrive a few animation frames later (tabs rendered in parallel): retry
    const essai = (n: number) => requestAnimationFrame(() => {
      const r = ref.current ? releve(ref.current, width, height) : null;
      if (r && r.contenu < 0 && n < 20) return essai(n + 1);
      if (r) console.log("CONTROLE " + JSON.stringify({ id, alpha, t: Math.round((f / fps) * 100) / 100, debut, ...r }));
      continueRender(h);
    });
    (document as any).fonts.ready.then(() => essai(0));
  }, [f]);
  return <AbsoluteFill ref={ref}>{children}</AbsoluteFill>;
};

export const ControleTexte: React.FC<ControleProps> = ({ fps, width, height, scenes }) => {
  let debut = 0;
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <Series>
        {scenes.map((s, i) => {
          const n = Math.max(1, Math.round(s.durationSec * fps));
          const d = debut;
          debut += n / fps;
          return (
            <Series.Sequence key={i} durationInFrames={n}>
              <Releve id={s.id} debut={Math.round(d * 100) / 100} alpha={!!s.alpha}>
                <Scene component={s.component} data={s.data} cues={s.cues} durationSec={s.durationSec} fps={fps} width={width} height={height} />
              </Releve>
            </Series.Sequence>
          );
        })}
      </Series>
    </AbsoluteFill>
  );
};
