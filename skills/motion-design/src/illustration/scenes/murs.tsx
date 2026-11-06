import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile } from "remotion";
import { Brackets, C, Eyebrow, F, Paper, Rise, clamp, easeOut, easeStd, fr, nb, ramp, rnd, shadow, useFadeOut, useSpringAt, useT } from "./kit";
import { SceneProps, StampMark } from "./opaque";

// Scenes of a video about the walls between your photos and your book.
// The motif: brick walls placed on the path between the hard drive and the book, and a
// red dot (the project, or a name such as PROJECT, the "red thread") that bumps into them or crosses them.
// As generic as possible: all the content comes from `data`, all the moments from `cues`
// (seconds from the start of the scene, aligned to the words by the plan). Data contract at the
// top of each component. No price, no logo.

const cue = (cues: number[], i: number | undefined, fallback: number) =>
  typeof i === "number" && typeof cues?.[i] === "number" ? cues[i] : fallback;
const sideX = (side: string | undefined, w: number) => (side === "right" ? 1920 - 90 - w : 90);
const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

/* ================================================================== */
/* Brick wall (SVG)                                                     */
/* rise: 0 → 1 (the wall comes out of the ground); burst: 0 → 1 (the bricks */
/* fly, the dot has passed); half: 0 → 1 (the upper half falls);      */
/* shake: horizontal offset in px                                     */
type WallProps = {
  x: number;
  base: number;
  w: number;
  h: number;
  rise?: number;
  burst?: number;
  half?: number;
  shake?: number;
  color: string;
  seed: number;
};
const ROWS = 6;
const Wall: React.FC<WallProps> = ({ x, base, w, h, rise = 1, burst = 0, half = 0, shake = 0, color, seed }) => {
  const rh = h / ROWS;
  const gap = Math.max(3, w * 0.035);
  const bricks: React.ReactNode[] = [];
  for (let r = 0; r < ROWS; r++) {
    const cells = r % 2 === 1 ? [[0, 0.25], [0.25, 0.75], [0.75, 1]] : [[0, 0.5], [0.5, 1]];
    cells.forEach(([a, b], i) => {
      const id = r * 3 + i + seed * 17;
      const dir = (a + b) / 2 - 0.5;
      // burst: each brick flies outward, rises a little then falls back
      const k = burst;
      const dx = k * (dir * 260 + (rnd(id + 1) - 0.5) * 90);
      const dy = k * (-90 * rnd(id + 2) + 420 * k * k);
      const rot = k * (rnd(id + 3) - 0.5) * 110;
      const op = 1 - clamp01((k - 0.55) / 0.45);
      // upper half that falls behind the wall (half of the work is done)
      const top = r >= ROWS / 2;
      const hk = top ? half : 0;
      const fy = hk * (60 + 30 * rnd(id + 5));
      const fop = 1 - hk;
      const bx = x - w / 2 + a * w + gap / 2;
      const by = base - (r + 1) * rh + gap / 2;
      bricks.push(
        <rect
          key={`${r}-${i}`}
          x={bx}
          y={by}
          width={(b - a) * w - gap}
          height={rh - gap}
          rx={3}
          fill={color}
          opacity={op * fop}
          transform={`translate(${dx + shake} ${dy + fy}) rotate(${rot} ${bx + ((b - a) * w) / 2} ${by + rh / 2})`}
        />,
      );
    });
  }
  // coming out of the ground: translation downward, cut at the path line
  const clipId = `mur-${seed}`;
  return (
    <g>
      <clipPath id={clipId}>
        <rect x={x - w * 3} y={-2000} width={w * 6} height={burst > 0 ? 6000 : base + 2000} />
      </clipPath>
      <g clipPath={`url(#${clipId})`}>
        <g transform={`translate(0 ${(1 - rise) * (h + 10)})`}>{bricks}</g>
      </g>
    </g>
  );
};

/* Line pictograms: hard drive and open book */
const Disque: React.FC<{ x: number; y: number; s?: number; color?: string; pulse?: number }> = ({ x, y, s = 1, color = C.contrast, pulse = 0 }) => (
  <g transform={`translate(${x} ${y}) scale(${s * (1 + 0.12 * pulse)})`}>
    <rect x={-62} y={-42} width={124} height={84} rx={14} fill="#FFFFFF" stroke={color} strokeWidth={5} />
    <line x1={-40} y1={18} x2={20} y2={18} stroke={color} strokeWidth={5} strokeLinecap="round" />
    <circle cx={40} cy={18} r={7} fill={C.accent} />
    <line x1={-40} y1={-14} x2={40} y2={-14} stroke={color} strokeWidth={3} strokeLinecap="round" opacity={0.35} />
  </g>
);
const Livre: React.FC<{ x: number; y: number; s?: number; fill?: number }> = ({ x, y, s = 1, fill = 0 }) => {
  const col = fill > 0.5 ? C.accent : C.contrast;
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <path d="M0 -36 C -26 -50 -52 -50 -76 -40 L -76 40 C -52 30 -26 30 0 44 Z" fill={fill > 0 ? `rgba(47,91,234,${0.18 * fill})` : "#FFFFFF"} stroke={col} strokeWidth={5} strokeLinejoin="round" />
      <path d="M0 -36 C 26 -50 52 -50 76 -40 L 76 40 C 52 30 26 30 0 44 Z" fill={fill > 0 ? `rgba(47,91,234,${0.18 * fill})` : "#FFFFFF"} stroke={col} strokeWidth={5} strokeLinejoin="round" />
      <line x1={0} y1={-36} x2={0} y2={44} stroke={col} strokeWidth={5} />
    </g>
  );
};

/* ================================================================== */
/* Walls: the recurring motif                                          */
/* data: { phase: "accroche"|"traverse"|"mur"|"rappel"|"revelation",   */
/*   titres?: [5 short titles], actif?: 1..5, eyebrow?, titre?,        */
/*   question?, etiquette? (the name carried by the dot, e.g. PROJECT),  */
/*   allume?: n°, note? (label under the lit wall),                     */
/*   modules?: [{eyebrow, titre}] ×5, titreFormation?, surtitre?,       */
/*   outils?: [{m: 1..5, text}], k?: {…} (reveal, see below) }          */
/* cues:                                                               */
/*   accroche  [walls (cascade), dot start, stop, return to the disk]   */
/*   traverse  [start, arrival] (+ optionally one moment per wall, k.murs; */
/*             k.leve: index of the cue where the walls rise, when the  */
/*             crossing is the first appearance of the motif)           */
/*   mur       [lock of the active wall]                                */
/*   rappel    [lit wall, half (optional)]                              */
/*   revelation: indices in data.k = { sondage?, titre, flip, outils: [5], fin? } */
const XS = [440, 710, 980, 1250, 1520];
export const Murs: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const phase: string = data?.phase ?? "accroche";
  if (phase === "revelation") return <Revelation data={data} cues={cues} />;
  const actif: number = data?.actif ?? 0;
  const bas = phase === "mur" || phase === "rappel";
  const base = bas ? 850 : 690;
  const wW = bas ? 112 : 132;
  const wH = bas ? 196 : 236;
  const drawK = ramp(t, 0.0, 0.6, easeStd);

  // --- red dot (the project) ---
  const X0 = 242;
  let dotX = X0;
  let dotOp = 0;
  let dotS = 1;
  let shake = 0;
  const bursts = [0, 0, 0, 0, 0];
  const rise = [1, 1, 1, 1, 1];
  let livreFill = 0;
  let disquePulse = 0;
  let etiquette = 0;
  if (phase === "accroche") {
    const c0 = cue(cues, 0, 0.3);
    for (let i = 0; i < 5; i++) rise[i] = Math.min(1, sp(c0 + i * 0.11, { damping: 13, stiffness: 150 }));
    const dep = cue(cues, 1, c0 + 1.2);
    const but = Math.max(dep + 0.35, cue(cues, 2, dep + 1.0));
    const ret = cue(cues, 3, but + 1.6);
    const front = XS[0] - wW / 2 - 26;
    if (t >= dep) {
      dotOp = ramp(t, dep, dep + 0.15);
      const k = interpolate(t, [dep, but], [0, 1], { ...clamp, easing: (x) => x * x });
      dotX = lerp(X0, front, k);
      if (t >= but) {
        const d = t - but;
        dotX = front - 34 * Math.sin(Math.min(d, 0.35) / 0.35 * Math.PI) * Math.exp(-d * 2);
        dotS = 1 - 0.25 * Math.exp(-d * 9) * Math.abs(Math.cos(d * 30));
        shake = Math.sin(d * 70) * 9 * Math.exp(-d * 8);
      }
      if (t >= ret) {
        const k2 = ramp(t, ret, ret + 0.6, easeStd);
        dotX = lerp(front, X0 - 40, k2);
        dotS = 1 - 0.7 * k2;
        dotOp = 1 - ramp(t, ret + 0.45, ret + 0.65);
        disquePulse = Math.sin(clamp01((t - ret - 0.5) / 0.35) * Math.PI);
      }
    }
  } else if (phase === "traverse") {
    if (typeof data?.k?.leve === "number") {
      const c0 = cue(cues, data.k.leve, 0.2);
      for (let i = 0; i < 5; i++) rise[i] = Math.min(1, sp(c0 + i * 0.11, { damping: 13, stiffness: 150 }));
    }
    const dep = cue(cues, 0, 0.4);
    const arr = Math.max(dep + 1.5, cue(cues, 1, dep + 3));
    const murs: number[] = (data?.k?.murs ?? []).map((i: number) => cue(cues, i, -1));
    const span = 1730 - X0;
    // crossing moments: given, otherwise spread according to position
    const pass = XS.map((x, i) => (murs[i] > 0 ? murs[i] : dep + ((x - X0) / span) * (arr - dep)));
    // the dot advances at constant speed between two crossings (slight slowdown before each wall)
    const pts = [X0, ...XS, 1730];
    const ts = [dep, ...pass, arr];
    dotOp = ramp(t, dep - 0.1, dep + 0.1);
    for (let i = 0; i < pts.length - 1; i++) {
      if (t >= ts[i] && t <= ts[i + 1]) {
        const k = interpolate(t, [ts[i], ts[i + 1]], [0, 1], { ...clamp, easing: easeStd });
        dotX = lerp(pts[i], pts[i + 1], k);
      }
    }
    if (t > arr) dotX = 1730;
    for (let i = 0; i < 5; i++) bursts[i] = ramp(t, pass[i] - 0.04, pass[i] + 0.9, (x) => x);
    livreFill = ramp(t, arr - 0.05, arr + 0.25);
    if (t > arr) dotOp = 1 - ramp(t, arr, arr + 0.25);
    etiquette = ramp(t, dep, dep + 0.3) * (1 - ramp(t, arr - 0.3, arr));
  } else if (bas) {
    // wall card: the dot waits in front of the active wall
    dotOp = ramp(t, 0.15, 0.4);
    dotX = actif > 0 ? XS[actif - 1] - wW / 2 - 30 : X0;
  }

  const lock = cue(cues, 0, 0.35);
  const allume: number | undefined = data?.allume;
  const halfK = phase === "rappel" && typeof cues?.[1] === "number" ? ramp(t, cues[1], cues[1] + 0.6, easeStd) : 0;
  const titres: string[] = data?.titres ?? [];

  const couleurMur = (i: number) => {
    const n = i + 1;
    if (bas) {
      if (n === actif) return C.accent;
      if (allume === n && t >= cue(cues, 0, 0.3)) return C.accent;
      if (n < actif) return "rgba(26,26,26,0.22)";
      return "rgba(26,26,26,0.78)";
    }
    return C.contrast;
  };

  return (
    <Paper drift={1.5}>
      {/* title (wall cards) */}
      {!bas && (data?.titre || data?.eyebrow) && (
        <div style={{ position: "absolute", left: 120, top: 150, right: 120, textAlign: "center" }}>
          {data?.eyebrow && (
            <Rise at={0.05}>
              <Eyebrow size={32}>{nb(data.eyebrow)}</Eyebrow>
            </Rise>
          )}
          {data?.titre && (
            <Rise at={cue(cues, data?.k?.titre, 0.12)} dur={0.55}>
              <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 400, fontSize: data?.size ?? 110, lineHeight: 1.05, color: C.contrast, marginTop: 12 }}>{nb(data.titre)}</div>
            </Rise>
          )}
        </div>
      )}
      {bas && (
        <div style={{ position: "absolute", left: 120, top: 96, right: 120 }}>
          <Rise at={0.05}>
            <Eyebrow size={32}>{nb(data?.eyebrow ?? (actif ? `Wall ${actif} of 5` : ""))}</Eyebrow>
          </Rise>
          <div style={{ height: 18 }} />
          {data?.titre && (
            <Rise at={0.12} dur={0.55}>
              <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 400, fontSize: data?.size ?? 104, lineHeight: 1.05, letterSpacing: "-0.015em", color: C.contrast, textWrap: "balance" }}>
                {nb(`“${data.titre}”`)}
              </div>
            </Rise>
          )}
          {data?.question && (
            <div style={{ marginTop: 26, opacity: ramp(t, 0.5, 0.85), transform: `translateY(${(1 - ramp(t, 0.5, 0.85, easeOut)) * 16}px)` }}>
              <div style={{ fontFamily: F.sans, fontWeight: 400, fontSize: 42, color: C.inkSoft }}>{nb(data.question)}</div>
            </div>
          )}
        </div>
      )}
      <AbsoluteFill>
        <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
          {/* chemin */}
          <clipPath id="chemin">
            <rect x={0} y={0} width={230 + drawK * 1500} height={1080} />
          </clipPath>
          <line x1={230} y1={base} x2={1730} y2={base} stroke={C.inkSoft} strokeWidth={4} strokeLinecap="round" clipPath="url(#chemin)" opacity={0.55} />
          <Disque x={170} y={base - 52} pulse={disquePulse} />
          <Livre x={1790} y={base - 52} fill={livreFill} s={1 + 0.3 * Math.sin(Math.PI * clamp01(livreFill * 1.0)) * (phase === "traverse" ? 1 : 0)} />
          {XS.map((x, i) => (
            <g key={i}>
              <Wall
                x={x}
                base={base}
                w={wW}
                h={wH}
                rise={rise[i]}
                burst={bursts[i]}
                half={bas && i + 1 === actif ? halfK : 0}
                shake={i === 0 ? shake : 0}
                color={couleurMur(i)}
                seed={i + 1}
              />
              <text
                x={x}
                y={base - wH - 26}
                textAnchor="middle"
                fontFamily="Source Serif"
                fontStyle="italic"
                fontWeight={300}
                fontSize={bas ? 58 : 66}
                fill={bas && i + 1 === actif ? C.accent : C.contrast}
                opacity={rise[i] * (1 - bursts[i] * 0.6) * (bas && i + 1 < actif ? 0.35 : 1)}
              >
                {i + 1}
              </text>
              {titres[i] && !bas && (
                <text x={x} y={base + 52} textAnchor="middle" fontFamily="Inter" fontWeight={700} fontSize={24} fill={C.inkSoft} opacity={rise[i]}>
                  {titres[i]}
                </text>
              )}
            </g>
          ))}
          {/* the dot */}
          <g transform={`translate(${dotX} ${base - 30}) scale(${dotS})`} opacity={dotOp}>
            <circle r={22} fill={C.accent} stroke="#FFFFFF" strokeWidth={6} />
          </g>
        </svg>
        {/* label carried by the dot (PROJECT, the red thread) */}
        {data?.etiquette && etiquette > 0 && dotOp > 0.01 && (
          <div
            style={{
              position: "absolute",
              left: dotX,
              top: base - 118,
              transform: `translateX(-50%) scale(${0.8 + 0.2 * etiquette})`,
              opacity: etiquette * dotOp,
              padding: "8px 20px",
              borderRadius: 40,
              background: C.contrast,
              color: C.paperWarm,
              fontFamily: F.sans,
              fontWeight: 700,
              fontSize: 30,
              letterSpacing: "0.08em",
              whiteSpace: "nowrap",
            }}
          >
            {data.etiquette}
          </div>
        )}
        {/* the book reached: its name */}
        {phase === "traverse" && data?.livre && livreFill > 0 && (
          <div style={{ position: "absolute", right: 60, top: base - 190, textAlign: "right", opacity: livreFill, transform: `translateY(${(1 - livreFill) * 20}px)` }}>
            <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 64, color: C.accent }}>{data.livre}</div>
          </div>
        )}
        {/* labels under the path */}
        {phase === "accroche" && typeof cues?.[3] === "number" && (
          <div style={{ position: "absolute", left: 60, top: base + 34, width: 220, textAlign: "center", opacity: ramp(t, cues[3] + 0.3, cues[3] + 0.6), fontFamily: F.sans, fontWeight: 700, fontSize: 26, color: C.inkSoft }}>
            {data?.disque ?? "The hard drive"}
          </div>
        )}
        {phase === "rappel" && allume && data?.note && (
          <div
            style={{
              position: "absolute",
              left: XS[allume - 1],
              top: base + 30,
              transform: `translateX(-50%) scale(${sp(lock, { damping: 12, stiffness: 200 })})`,
              padding: "10px 24px",
              borderRadius: 40,
              background: C.accent,
              color: "#FFFFFF",
              fontFamily: F.sans,
              fontWeight: 700,
              fontSize: 30,
              whiteSpace: "nowrap",
            }}
          >
            {nb(data.note)}
          </div>
        )}
      </AbsoluteFill>
      {bas && actif > 0 && (
        <Brackets x={XS[actif - 1] - wW / 2 - 18} y={base - wH - 92} w={wW + 36} h={wH + 110} at={lock} arm={34} stroke={5} />
      )}
    </Paper>
  );
};

/* ------------------------------------------------------------------ */
/* Reveal: the walls turn into modules                                 */
/* data.k = { sondage?: i (label "data.sondage" that lands),             */
/*   titre: i (kicker + course title), flip: i (the 5 walls             */
/*   turn over in cascade), outils: [i×5] (a tool label                */
/*   under its module, in the order of data.outils), fin?: i }         */
const CX = [280, 620, 960, 1300, 1640];
const Revelation: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const k = data?.k ?? {};
  const modules: { eyebrow: string; titre: string }[] = data?.modules ?? [];
  const outils: { m: number; text: string }[] = data?.outils ?? [];
  const cT = cue(cues, k.titre, 0.4);
  const cF = cue(cues, k.flip, cT + 0.6);
  const cardW = 316;
  const cardH = 390;
  const top = 360;
  const base = top + cardH;
  return (
    <Paper drift={1.5}>
      <div style={{ position: "absolute", left: 0, right: 0, top: 96, textAlign: "center" }}>
        {data?.surtitre && (
          <div style={{ opacity: ramp(t, cT, cT + 0.3) }}>
            <Eyebrow size={32}>{nb(data.surtitre)}</Eyebrow>
          </div>
        )}
        <div style={{ height: 14 }} />
        <Rise at={cT + 0.08} dur={0.55}>
          <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 400, fontSize: 100, lineHeight: 1.05, color: C.contrast }}>{nb(data?.titreFormation ?? "")}</div>
        </Rise>
      </div>
      {data?.sondage && typeof k.sondage === "number" && (
        <div style={{ position: "absolute", left: 120, top: 120, opacity: 1 - ramp(t, cT - 0.3, cT) }}>
          <StampMark at={cue(cues, k.sondage, 0.3)} text={data.sondage} size={60} rotate={-6} />
        </div>
      )}
      {CX.map((x, i) => {
        const f = interpolate(t, [cF + i * 0.22, cF + i * 0.22 + 0.7], [0, 180], { ...clamp, easing: easeStd });
        const front = f < 90;
        const m = modules[i] ?? { eyebrow: `Module ${i + 1}`, titre: "" };
        const oi = outils.findIndex((o) => o.m === i + 1);
        const ca = oi >= 0 ? cue(cues, k.outils?.[oi], -1) : -1;
        const cs = ca >= 0 ? sp(ca, { damping: 12, stiffness: 200 }) : 0;
        return (
          <React.Fragment key={i}>
            <div style={{ position: "absolute", left: x - cardW / 2, top, width: cardW, height: cardH, perspective: 1400 }}>
              <div style={{ position: "relative", width: "100%", height: "100%", transformStyle: "preserve-3d", transform: `rotateY(${f}deg)` }}>
                {front ? (
                  <svg width={cardW} height={cardH} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
                    <Wall x={cardW / 2} base={cardH} w={170} h={300} color={C.contrast} seed={i + 21} />
                    <text x={cardW / 2} y={cardH - 322} textAnchor="middle" fontFamily="Source Serif" fontStyle="italic" fontWeight={300} fontSize={62} fill={C.contrast}>
                      {i + 1}
                    </text>
                  </svg>
                ) : (
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      transform: "rotateY(180deg)",
                      background: "#FFFFFF",
                      borderRadius: 16,
                      boxShadow: shadow,
                      borderTop: `10px solid ${C.accent}`,
                      padding: "28px 22px",
                      display: "flex",
                      flexDirection: "column",
                    }}
                  >
                    <Eyebrow size={24}>{nb(m.eyebrow)}</Eyebrow>
                    <div style={{ height: 16 }} />
                    <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 400, fontSize: 37, lineHeight: 1.12, color: C.contrast, textWrap: "balance" }}>{nb(m.titre)}</div>
                    <div style={{ flex: 1 }} />
                    <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 300, fontSize: 90, lineHeight: 0.9, color: C.accent, alignSelf: "flex-end" }}>{i + 1}</div>
                  </div>
                )}
              </div>
            </div>
            {oi >= 0 && ca >= 0 && (
              <div
                style={{
                  position: "absolute",
                  left: x,
                  top: base + 40,
                  transform: `translateX(-50%) translateY(${(1 - cs) * 30}px) scale(${0.85 + 0.15 * cs})`,
                  opacity: Math.min(1, cs * 1.6),
                  padding: "12px 26px",
                  borderRadius: 40,
                  background: C.contrast,
                  color: C.paperWarm,
                  fontFamily: F.sans,
                  fontWeight: 700,
                  fontSize: 30,
                  whiteSpace: "nowrap",
                }}
              >
                {nb(outils[oi].text)}
              </div>
            )}
          </React.Fragment>
        );
      })}
      {typeof k.fin === "number" && data?.fin && (
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 110, textAlign: "center" }}>
          <Rise at={cue(cues, k.fin, 99)}>
            <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 54, color: C.inkSoft }}>{nb(data.fin)}</div>
          </Rise>
        </div>
      )}
    </Paper>
  );
};

/* ================================================================== */
/* Sort: a mass of views, successive selections, the final selection   */
/* laid out in a grid (with the real photos if `images`).              */
/* data: { eyebrow, total, environ?, totalLabel, extra?: {n, label},   */
/*   etapes: [{n, label, environ?}], final?: {cols, rows},              */
/*   images?: [src] (grille finale), tampons?: [{text, k, x?, y?, size?}], */
/*   zone?: {x, y, w, h} (grille finale), attente?: s before the layout } */
/* cues: [mass, one per step…] then those designated by the stamps    */
/* The LAST step lays out its selection in a grid if `final` is given. */
export const Tri: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const total: number = data?.total ?? 1000;
  const etapes: { n: number; label: string; environ?: boolean }[] = data?.etapes ?? [];
  const extra: { n: number; label: string } | undefined = data?.extra;
  const images: string[] = data?.images ?? [];
  const c0 = cue(cues, 0, 0.3);
  const ce = etapes.map((_, i) => cue(cues, i + 1, c0 + 1.6 + i * 1.6));
  // zone of the mass
  const AX = 120, AY = 300, AW = 1680;
  const AH = extra ? 560 : 680;
  const aspect = 1.5;
  let cols = Math.ceil(Math.sqrt((total * AW) / (AH * aspect)));
  let rows = Math.ceil(total / cols);
  let cw = AW / cols;
  let ch = cw / aspect;
  if (rows * ch > AH) {
    ch = AH / rows;
    cw = ch * aspect;
    cols = Math.floor(AW / cw);
    rows = Math.ceil(total / cols);
  }
  const fullRows = Math.floor(total / cols);
  const lastN = total - fullRows * cols;
  const gx = Math.max(1, cw * 0.18);
  const masseW = cols * cw;
  const mx = AX + (AW - masseW) / 2;
  const reveal = ramp(t, c0, c0 + 1.0, easeOut);
  // nested selections: prefixes of a fixed permutation of the cells
  const nMax = etapes.length ? etapes[0].n : 0;
  const perm: number[] = [];
  const used = new Set<number>();
  for (let s = 0; perm.length < nMax && s < nMax * 50; s++) {
    const idx = Math.floor(rnd(s * 7.13 + 3.1) * total);
    if (!used.has(idx)) {
      used.add(idx);
      perm.push(idx);
    }
  }
  const cell = (idx: number) => ({ x: mx + (idx % cols) * cw, y: AY + Math.floor(idx / cols) * ch });
  // current step
  let cur = -1;
  ce.forEach((c, i) => {
    if (t >= c) cur = i;
  });
  const last = etapes.length - 1;
  const final = data?.final;
  const gStart = ce[last] + (data?.attente ?? 0.9);
  const gk = final && cur === last ? ramp(t, gStart, gStart + 0.9, easeStd) : 0;
  // grille finale
  const fn = etapes[last]?.n ?? 0;
  const Z = data?.zone ?? { x: 560, y: 250, w: 1240, h: 760 };
  const FX = Z.x, FY = Z.y, FW = Z.w, FH = Z.h, fgap = 16;
  const fcols = final?.cols ?? Math.ceil(Math.sqrt(fn * 1.6));
  const frows = final?.rows ?? Math.ceil(fn / fcols);
  const fAsp = images.length ? 1 : aspect;
  let fcw = (FW - (fcols - 1) * fgap) / fcols;
  let fch = fcw / fAsp;
  if (frows * fch + (frows - 1) * fgap > FH) {
    fch = (FH - (frows - 1) * fgap) / frows;
    fcw = fch * fAsp;
  }
  const gridW = fcols * fcw + (fcols - 1) * fgap;
  const gridH = frows * fch + (frows - 1) * fgap;
  const gx0 = FX + (FW - gridW) / 2;
  const gy0 = FY + (FH - gridH) / 2;
  // compteur
  const shown = (() => {
    if (cur < 0) return { v: total * reveal, environ: !!data?.environ, label: data?.totalLabel ?? "" };
    const from = cur === 0 ? total : etapes[cur - 1].n;
    const k = ramp(t, ce[cur], ce[cur] + 0.8, easeOut);
    return { v: from + (etapes[cur].n - from) * k, environ: !!etapes[cur].environ, label: etapes[cur].label };
  })();
  const masseOp = cur < 0 ? 1 : gk > 0 ? lerp(0.35, 0.05, gk) : 0.35;
  const tampons: { text: string; k: number; x?: number; y?: number; size?: number }[] = data?.tampons ?? [];
  return (
    <Paper drift={1.2}>
      <div style={{ position: "absolute", left: 120, top: 70 }}>
        <Rise at={0.03}>
          <Eyebrow size={30}>{nb(data?.eyebrow ?? "")}</Eyebrow>
        </Rise>
        <div style={{ display: "flex", alignItems: "baseline", gap: 30, marginTop: 6, opacity: ramp(t, c0 - 0.1, c0 + 0.1) }}>
          <span style={{ fontFamily: F.display, fontWeight: 300, fontSize: 150, lineHeight: 1.0, letterSpacing: "-0.03em", color: cur >= 0 ? C.accent : C.contrast, fontVariantNumeric: "tabular-nums" }}>
            {(shown.environ ? "≈ " : "") + fr(shown.v)}
          </span>
          <span style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 44, color: C.contrast }}>{nb(shown.label)}</span>
        </div>
      </div>
      <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0 }}>
        <defs>
          <pattern id="tri-case" x={mx} y={AY} width={cw} height={ch} patternUnits="userSpaceOnUse">
            <rect x={gx / 2} y={gx / 2} width={cw - gx} height={ch - gx} rx={Math.min(3, cw * 0.1)} fill={C.contrast} />
          </pattern>
          <clipPath id="tri-revele">
            <rect x={mx} y={AY} width={masseW * reveal} height={AH + 200} />
          </clipPath>
        </defs>
        <g clipPath="url(#tri-revele)" opacity={masseOp}>
          <rect x={mx} y={AY} width={masseW} height={fullRows * ch} fill="url(#tri-case)" />
          {lastN > 0 && <rect x={mx} y={AY + fullRows * ch} width={lastN * cw} height={ch} fill="url(#tri-case)" />}
        </g>
        {extra && (
          <g opacity={masseOp * ramp(t, c0 + 0.5, c0 + 1.1)}>
            {Array.from({ length: extra.n }).map((_, i) => {
              const ew = Math.min(28, (AW - 300) / extra.n);
              return <rect key={i} x={AX + 300 + i * ew} y={AY + AH + 50} width={ew - 4} height={ew - 4} rx={2} fill={C.inkSoft} />;
            })}
          </g>
        )}
        {/* chosen cells: red, then laid out */}
        {cur >= 0 &&
          perm.slice(0, etapes[cur].n).map((idx, j) => {
            const p = cell(idx);
            const popK = ramp(t, ce[cur] + (j / Math.max(1, etapes[cur].n)) * 0.4, ce[cur] + (j / Math.max(1, etapes[cur].n)) * 0.4 + 0.2);
            const isFinal = gk > 0;
            const gxp = gx0 + (j % fcols) * (fcw + fgap);
            const gyp = gy0 + Math.floor(j / fcols) * (fch + fgap);
            const x = isFinal ? lerp(p.x, gxp, gk) : p.x;
            const y = isFinal ? lerp(p.y, gyp, gk) : p.y;
            const w = isFinal ? lerp(cw, fcw, gk) : cw;
            const h = isFinal ? lerp(ch, fch, gk) : ch;
            const grow = isFinal ? 1 : 1 + 1.2 * (1 - popK) * popK * 4 * 0.5;
            return (
              <rect
                key={idx}
                x={x + (w * (1 - grow)) / 2}
                y={y + (h * (1 - grow)) / 2}
                width={w * grow - (isFinal ? 0 : gx)}
                height={h * grow - (isFinal ? 0 : gx)}
                rx={isFinal ? 6 : 2}
                fill={images.length && gk > 0.6 ? "#FFFFFF" : C.accent}
                opacity={cur === 0 || isFinal ? Math.max(popK, isFinal ? 1 : 0) : 1}
                style={{ filter: isFinal ? "drop-shadow(0 6px 12px rgba(26,26,26,0.18))" : undefined }}
              />
            );
          })}
      </svg>
      {/* real photos in the final grid (white border, native ratio) */}
      {gk > 0.6 &&
        images.slice(0, fn).map((src, j) => {
          const gxp = gx0 + (j % fcols) * (fcw + fgap);
          const gyp = gy0 + Math.floor(j / fcols) * (fch + fgap);
          const op = ramp(t, gStart + 0.75 + j * 0.018, gStart + 1.05 + j * 0.018);
          return (
            <div key={j} style={{ position: "absolute", left: gxp + 5, top: gyp + 5, width: fcw - 10, height: fch - 10, opacity: op }}>
              <Img src={staticFile(src)} style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            </div>
          );
        })}
      {extra && (
        <div style={{ position: "absolute", left: AX, top: AY + AH + 40, width: 280, fontFamily: F.sans, fontWeight: 700, fontSize: 30, color: C.inkSoft, opacity: (cur < 0 ? 1 : 0.4) * ramp(t, c0 + 0.5, c0 + 1.1) }}>
          {nb(extra.label)}
        </div>
      )}
      {tampons.map((tp, i) => (
        <div key={i} style={{ position: "absolute", right: tp.x === undefined ? 120 : undefined, left: tp.x, top: tp.y ?? 96 }}>
          <StampMark at={cue(cues, tp.k, 99)} text={tp.text} size={tp.size ?? 74} rotate={-7} />
        </div>
      ))}
    </Paper>
  );
};

/* ================================================================== */
/* Route: the trip map, the advancing line, the photos by city        */
/* data: { eyebrow, titre, sous, etats: [{d}] (chemins SVG 1920×1080),  */
/*   villes: [{nom, x, y, cote?: "haut"|"bas"|"gauche"|"droite"}],       */
/*   photos?: [{src, w, h, x, y, ville?, k?, rot?}] }                    */
/*   (a photo pops up when the line reaches `ville` (rank in villes),   */
/*   or at the moment cues[k] if `k` is given)                          */
/* cues: [start, arrival, …moments of the photos with `k`]             */
export const Route: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const villes: { nom: string; x: number; y: number; cote?: string }[] = data?.villes ?? [];
  const etats: { d: string }[] = data?.etats ?? [];
  const photos: { src: string; w: number; h: number; x: number; y: number; ville?: number; k?: number; rot?: number }[] = data?.photos ?? [];
  const dep = cue(cues, 0, 0.5);
  const arr = Math.max(dep + 1, cue(cues, 1, dep + 5));
  // cumulative length of the line
  const seg: number[] = [0];
  for (let i = 1; i < villes.length; i++) seg.push(seg[i - 1] + Math.hypot(villes[i].x - villes[i - 1].x, villes[i].y - villes[i - 1].y));
  const L = seg[seg.length - 1] || 1;
  const p = interpolate(t, [dep, arr], [0, 1], { ...clamp, easing: easeStd }) * L;
  let px = villes[0]?.x ?? 0, py = villes[0]?.y ?? 0;
  for (let i = 1; i < villes.length; i++) {
    if (p <= seg[i]) {
      const k = (p - seg[i - 1]) / Math.max(1, seg[i] - seg[i - 1]);
      px = lerp(villes[i - 1].x, villes[i].x, k);
      py = lerp(villes[i - 1].y, villes[i].y, k);
      break;
    }
    px = villes[i].x;
    py = villes[i].y;
  }
  const d = villes.map((v, i) => `${i ? "L" : "M"}${v.x} ${v.y}`).join(" ");
  const mapIn = ramp(t, 0, 0.6, easeOut);
  return (
    <Paper drift={1.6}>
      <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0 }}>
        <g opacity={mapIn}>
          {etats.map((e, i) => (
            <path key={i} d={e.d} fill="#E7E2D7" stroke="#CFC7B8" strokeWidth={2} strokeLinejoin="round" />
          ))}
        </g>
        <path d={d} fill="none" stroke={C.accent} strokeWidth={7} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={L} strokeDashoffset={L - p} />
        {villes.map((v, i) => {
          const at = dep + (seg[i] / L) * (arr - dep);
          const s = sp(at, { damping: 11, stiffness: 220 });
          const cote = v.cote ?? "haut";
          const tx = cote === "gauche" ? v.x - 22 : cote === "droite" ? v.x + 22 : v.x;
          const ty = cote === "bas" ? v.y + 48 : cote === "haut" ? v.y - 26 : v.y + 10;
          const anchor = cote === "gauche" ? "end" : cote === "droite" ? "start" : "middle";
          return (
            <g key={i} opacity={t >= at ? 1 : 0}>
              <circle cx={v.x} cy={v.y} r={11 * s} fill="#FFFFFF" stroke={C.accent} strokeWidth={5} />
              <text x={tx} y={ty} textAnchor={anchor} fontFamily="Inter" fontWeight={700} fontSize={30} fill={C.contrast} opacity={Math.min(1, s * 1.5)} style={{ paintOrder: "stroke", stroke: C.paperWarm, strokeWidth: 8 }}>
                {v.nom}
              </text>
            </g>
          );
        })}
        {t >= dep && t <= arr + 0.3 && <circle cx={px} cy={py} r={14} fill={C.accent} stroke="#FFFFFF" strokeWidth={5} />}
      </svg>
      {photos.map((ph, i) => {
        const at = typeof ph.k === "number" ? cue(cues, ph.k, 99) : typeof ph.ville === "number" ? dep + ((seg[ph.ville] ?? 0) / L) * (arr - dep) + 0.08 : 99;
        const s = sp(at, { damping: 13, stiffness: 170 });
        if (t < at) return null;
        const box = data?.box ?? 270;
        const r = ph.w / ph.h;
        const w = r >= 1 ? box : box * r;
        const h = r >= 1 ? box / r : box;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: ph.x - w / 2 - 12,
              top: ph.y - h / 2 - 12,
              padding: 12,
              background: "#FFFFFF",
              boxShadow: shadow,
              transform: `translateY(${(1 - s) * 60}px) rotate(${ph.rot ?? (i % 2 ? 2.5 : -2.5)}deg) scale(${0.85 + 0.15 * s})`,
              opacity: Math.min(1, s * 1.8),
            }}
          >
            <Img src={staticFile(ph.src)} style={{ width: w, height: h, display: "block" }} />
          </div>
        );
      })}
      <div style={{ position: "absolute", left: 120, bottom: 110 }}>
        <Rise at={0.1}>
          <Eyebrow size={30}>{nb(data?.eyebrow ?? "")}</Eyebrow>
        </Rise>
        <Rise at={0.18} dur={0.55}>
          <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 400, fontSize: 80, lineHeight: 1.08, color: C.contrast, marginTop: 8 }}>{nb(data?.titre ?? "")}</div>
        </Rise>
        {data?.sous && (
          <Rise at={0.3}>
            <div style={{ fontFamily: F.sans, fontSize: 38, color: C.inkSoft, marginTop: 10 }}>{nb(data.sous)}</div>
          </Rise>
        )}
      </div>
    </Paper>
  );
};

/* ================================================================== */
/* One voice: two sources (digital, film) that                       */
/* join in the book's layout (flatplan).                              */
/* data: { gauche: {eyebrow, label, images: [{src, w, h}]},            */
/*   droite: {…}, fusion: [{src, w, h, cote: "g"|"d"}], titre }          */
/* cues: [gauche, droite, fusion, titre]                               */
export const UneVoix: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const cG = cue(cues, 0, 0.3), cD = cue(cues, 1, cG + 1.2), cFu = cue(cues, 2, cD + 1.5), cTi = cue(cues, 3, cFu + 1.2);
  const fk = ramp(t, cFu, cFu + 1.0, easeStd);
  const pile = (cote: "g" | "d", at: number) => {
    const src = cote === "g" ? data?.gauche : data?.droite;
    const imgs: { src: string; w: number; h: number }[] = src?.images ?? [];
    const cx = cote === "g" ? 500 : 1420;
    return (
      <div style={{ opacity: 1 - fk }}>
        <div style={{ position: "absolute", left: cx - 380, width: 760, top: 110, textAlign: "center", opacity: ramp(t, at, at + 0.3) }}>
          <Eyebrow size={28}>{nb(src?.eyebrow ?? "")}</Eyebrow>
          <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 76, color: C.contrast, marginTop: 6 }}>{nb(src?.label ?? "")}</div>
        </div>
        {imgs.map((im, j) => {
          // flipping through: every 1.1 s the top photo slides and goes back underneath
          const n = imgs.length;
          const t1 = at + 0.4 + n * 0.12;
          const per = 1.1;
          const kk = t > t1 ? Math.floor((t - t1) / per) : 0;
          const ph = t > t1 ? ((t - t1) % per) / per : 0;
          const i = (j + kk) % n;          // rank in the stack (n - 1 = top)
          const sortie = i === n - 1 && t > t1 ? ramp(ph, 0.72, 1, easeStd) : 0;
          const s = sp(at + 0.1 + j * 0.12, { damping: 13, stiffness: 170 });
          const box = 420;
          const r = im.w / im.h;
          const w = r >= 1 ? box : box * r;
          const h = r >= 1 ? box / r : box;
          const off = (i - (n - 1) / 2);
          return (
            <div
              key={j}
              style={{
                position: "absolute",
                left: cx - w / 2 - 12 + off * 46 + sortie * (cote === "g" ? -150 : 150),
                top: 600 - h / 2 - 12 + off * 14,
                padding: 12,
                background: "#FFFFFF",
                boxShadow: shadow,
                zIndex: i,
                transform: `translateY(${(1 - s) * 120}px) rotate(${off * 3.2 + sortie * (cote === "g" ? -8 : 8)}deg)`,
                opacity: Math.min(1, s * 1.8) * (1 - sortie),
              }}
            >
              <Img src={staticFile(im.src)} style={{ width: w, height: h, display: "block" }} />
            </div>
          );
        })}
      </div>
    );
  };
  // flatplan: one row, common height, native ratio
  const fusion: { src: string; w: number; h: number; cote: string }[] = data?.fusion ?? [];
  const H = 250, gap = 22;
  const widths = fusion.map((f) => (H * f.w) / f.h);
  const total = widths.reduce((a, b) => a + b, 0) + gap * Math.max(0, fusion.length - 1);
  const sc = Math.min(1, 1720 / Math.max(1, total));
  let acc = (1920 - total * sc) / 2;
  return (
    <Paper drift={1.4}>
      {pile("g", cG)}
      {t >= cD - 0.05 && pile("d", cD)}
      {fk > 0 &&
        fusion.map((f, i) => {
          const w = widths[i] * sc, h = H * sc;
          const x = acc;
          acc += w + gap * sc;
          const from = f.cote === "g" ? { x: 500, y: 600 } : { x: 1420, y: 600 };
          const kk = ramp(t, cFu + i * 0.05, cFu + 0.8 + i * 0.05, easeStd);
          const cx = lerp(from.x, x + w / 2, kk);
          const cy = lerp(from.y, 470, kk);
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: cx - w / 2 - 8,
                top: cy - h / 2 - 8,
                padding: 8,
                background: "#FFFFFF",
                boxShadow: "0 10px 26px rgba(26,26,26,0.16)",
                opacity: Math.min(1, kk * 3),
              }}
            >
              <Img src={staticFile(f.src)} style={{ width: w, height: h, display: "block" }} />
            </div>
          );
        })}
      <div style={{ position: "absolute", left: 0, right: 0, top: 700, textAlign: "center" }}>
        <Rise at={cTi} dur={0.55}>
          <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 400, fontSize: 120, color: C.contrast }}>{nb(data?.titre ?? "")}</div>
        </Rise>
      </div>
      {t >= cTi + 0.3 && (
        <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0 }}>
          <path d="M660 870 C 820 856, 1100 884, 1260 862" fill="none" stroke={C.accent} strokeWidth={8} strokeLinecap="round" strokeDasharray={620} strokeDashoffset={620 * (1 - ramp(t, cTi + 0.3, cTi + 0.75, easeStd))} />
        </svg>
      )}
    </Paper>
  );
};

/* ================================================================== */
/* Hanging: 1 to 4 framed images (white border, native ratio),        */
/* caption under each, which enter on their word.                     */
/* data: { eyebrow?, titre?, images: [{src, w, h, legende?, sous?}],   */
/*   mots?: [string], tampon?: {text, k, x?, y?}, sombre?: bool }        */
/* cues: one per image, then one per word, then what the stamp designates */
export const Accrochage: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const images: { src: string; w: number; h: number; legende?: string; sous?: string }[] = data?.images ?? [];
  const mots: string[] = data?.mots ?? [];
  const head = !!(data?.eyebrow || data?.titre);
  const top = head ? 280 : 130;
  const maxH = (mots.length ? 900 : 960) - top - (images.some((i) => i.legende) ? 110 : 0);
  const gap = 70;
  let hImg = maxH;
  const wsum = (h: number) => images.reduce((a, im) => a + (h * im.w) / im.h + 28, 0) + gap * Math.max(0, images.length - 1);
  if (wsum(hImg) > 1700) hImg = hImg * (1700 / wsum(hImg));
  const total = wsum(hImg);
  let x = (1920 - total) / 2;
  const blocH = hImg + 28 + (images.some((i) => i.legende || i.sous) ? 110 : 0);
  const bas = mots.length ? 900 : 1010;
  const y0 = Math.max(top, top + (bas - top - blocH) / 2);
  const kb = 1 + 0.03 * ramp(t, 0, 8, (v) => v);
  const sombre = !!data?.sombre;
  return (
    <Paper drift={0} dark={sombre}>
      {head && (
        <div style={{ position: "absolute", left: 120, top: 96, right: 120 }}>
          {data?.eyebrow && (
            <Rise at={0.03}>
              <Eyebrow size={30}>{nb(data.eyebrow)}</Eyebrow>
            </Rise>
          )}
          {data?.titre && (
            <Rise at={0.1} dur={0.55}>
              <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 76, lineHeight: 1.08, color: sombre ? C.paperWarm : C.contrast, marginTop: 8 }}>{nb(data.titre)}</div>
            </Rise>
          )}
        </div>
      )}
      <AbsoluteFill style={{ transform: `scale(${kb})`, transformOrigin: "50% 55%" }}>
        {images.map((im, i) => {
          const w = (hImg * im.w) / im.h;
          const left = x;
          x += w + 28 + gap;
          const at = cue(cues, i, 0.15 + i * 0.8);
          const s = sp(at, { damping: 14, stiffness: 150 });
          const rot = [-1.6, 1.3, -1.0, 1.8][i % 4];
          return (
            <div key={i} style={{ position: "absolute", left, top: y0, opacity: t >= at ? Math.min(1, s * 1.7) : 0 }}>
              <div style={{ padding: 14, background: "#FFFFFF", boxShadow: "0 22px 50px rgba(0,0,0,0.25)", transform: `translateY(${(1 - s) * 80}px) rotate(${rot}deg) scale(${0.92 + 0.08 * s})` }}>
                <Img src={staticFile(im.src)} style={{ width: w, height: hImg, display: "block" }} />
              </div>
              {(im.legende || im.sous) && (
                <div style={{ marginTop: 22, width: w + 28, textAlign: "center", opacity: ramp(t, at + 0.25, at + 0.5) }}>
                  {im.legende && <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 34, color: sombre ? C.paperWarm : C.contrast }}>{nb(im.legende)}</div>}
                  {im.sous && <div style={{ fontFamily: F.sans, fontStyle: "italic", fontSize: 28, color: sombre ? "rgba(242,242,242,0.7)" : C.inkSoft, marginTop: 4 }}>{nb(im.sous)}</div>}
                </div>
              )}
            </div>
          );
        })}
      </AbsoluteFill>
      {mots.length > 0 && (
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 70, display: "flex", justifyContent: "center", gap: 20 }}>
          {mots.map((m, j) => {
            const at = cue(cues, images.length + j, 99);
            const s = sp(at, { damping: 12, stiffness: 200 });
            return (
              <div key={j} style={{ padding: "12px 28px", borderRadius: 40, background: j === mots.length - 1 ? C.accent : C.contrast, color: "#FFFFFF", fontFamily: F.sans, fontWeight: 700, fontSize: 34, transform: `scale(${s})`, opacity: t >= at ? 1 : 0 }}>
                {nb(m)}
              </div>
            );
          })}
        </div>
      )}
      {data?.tampon && (
        <div style={{ position: "absolute", right: data.tampon.x === undefined ? 170 : undefined, left: data.tampon.x, top: data.tampon.y ?? Math.max(60, y0 - 40) }}>
          <StampMark at={cue(cues, data.tampon.k, 99)} text={data.tampon.text} size={data.tampon.size ?? 72} rotate={-6} />
        </div>
      )}
    </Paper>
  );
};

/* ================================================================== */
/* Funding: the gauge that passes the goal then exceeds it,            */
/* the print run, the publisher, the preface. No amount in euros.      */
/* data: { eyebrow, heures: 48, pourcent: 600, prefixe?, objectif?,     */
/*   exemplaires?: 380, exemplairesLabel?, lignes?: [{label, text}] }    */
/* cues: [gauge, overshoot, copies, line 1, line 2…]                  */
export const Financement: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const c0 = cue(cues, 0, 0.3), c1 = cue(cues, 1, c0 + 1.6), c2 = cue(cues, 2, c1 + 1.6);
  const pct: number = data?.pourcent ?? 600;
  const X0 = 160, LW = 1600, Y = 500;
  const mark = LW / (pct / 100);
  const k1 = ramp(t, c0, c0 + 0.9, easeOut);
  const k2 = ramp(t, c1, c1 + 1.5, easeOut);
  const fill = t < c1 ? mark * k1 : mark + (LW - mark) * k2;
  const heures = Math.round((data?.heures ?? 48) * k1);
  const v = t < c1 ? 100 * k1 : 100 + (pct - 100) * k2;
  const lignes: { label: string; text: string }[] = data?.lignes ?? [];
  return (
    <Paper drift={1.4}>
      <div style={{ position: "absolute", left: 160, top: 96 }}>
        <Rise at={0.03}>
          <Eyebrow size={30}>{nb(data?.eyebrow ?? "")}</Eyebrow>
        </Rise>
      </div>
      {/* figures above the gauge */}
      <div style={{ position: "absolute", left: X0, top: 250, opacity: ramp(t, c0, c0 + 0.2) }}>
        <div style={{ fontFamily: F.display, fontWeight: 300, fontSize: 150, lineHeight: 1, color: C.contrast, fontVariantNumeric: "tabular-nums" }}>{`${heures} h`}</div>
        <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 36, color: C.inkSoft, marginTop: 4 }}>{nb(data?.heuresLabel ?? "to be funded")}</div>
      </div>
      <div style={{ position: "absolute", right: 1920 - X0 - LW, top: 250, textAlign: "right", opacity: ramp(t, c1, c1 + 0.2) }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "flex-end", gap: 18 }}>
          {data?.prefixe && <span style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 64, color: C.inkSoft, opacity: ramp(t, c1 + 1.3, c1 + 1.6) }}>{data.prefixe}</span>}
          <span style={{ fontFamily: F.display, fontWeight: 300, fontSize: 150, lineHeight: 1, color: C.accent, fontVariantNumeric: "tabular-nums" }}>{`${fr(v)} %`}</span>
        </div>
        <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 36, color: C.inkSoft, marginTop: 4 }}>{nb(data?.pourcentLabel ?? "of the goal")}</div>
      </div>
      {/* the gauge */}
      <div style={{ position: "absolute", left: X0, top: Y, width: LW, height: 46, borderRadius: 30, background: "rgba(26,26,26,0.1)", overflow: "hidden", opacity: ramp(t, 0.1, 0.4) }}>
        <div style={{ width: fill, height: "100%", background: C.accent, borderRadius: 30 }} />
      </div>
      <div style={{ position: "absolute", left: X0 + mark - 3, top: Y - 24, width: 6, height: 94, background: C.contrast, opacity: ramp(t, 0.2, 0.5) }} />
      <div style={{ position: "absolute", left: X0 + mark, top: Y + 84, transform: "translateX(-50%)", fontFamily: F.sans, fontWeight: 700, fontSize: 28, color: C.contrast, opacity: ramp(t, 0.2, 0.5), whiteSpace: "nowrap" }}>
        {nb(data?.objectif ?? "Goal: 100%")}
      </div>
      {/* print run, publisher, preface */}
      <div style={{ position: "absolute", left: X0, right: 1920 - X0 - LW, top: 720, display: "flex", gap: 70, alignItems: "flex-start" }}>
        {data?.exemplaires && (
          <div style={{ opacity: t >= c2 ? 1 : 0, transform: `scale(${t >= c2 ? 0.85 + 0.15 * sp(c2, { damping: 11, stiffness: 200 }) : 0.85})`, transformOrigin: "0 50%" }}>
            <div style={{ fontFamily: F.display, fontWeight: 300, fontSize: 130, lineHeight: 1, color: C.contrast, fontVariantNumeric: "tabular-nums" }}>
              {fr(data.exemplaires * ramp(t, c2, c2 + 0.7, easeOut))}
            </div>
            <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 34, color: C.contrast, marginTop: 6 }}>{nb(data?.exemplairesLabel ?? "numbered copies")}</div>
          </div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 26, paddingTop: 14 }}>
          {lignes.map((l, i) => (
            <Rise key={i} at={cue(cues, 3 + i, c2 + 0.8 + i * 0.8)}>
              <div>
                <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 24, letterSpacing: "0.14em", textTransform: "uppercase", color: C.accent }}>{nb(l.label)}</div>
                <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 58, lineHeight: 1.1, color: C.contrast }}>{nb(l.text)}</div>
              </div>
            </Rise>
          ))}
        </div>
      </div>
    </Paper>
  );
};

/* ================================================================== */
/* Mosaic: all the lessons drop into their columns (modules).         */
/* 88 px thumbnails: titles deliberately unreadable (the "how" stays   */
/* in the course).                                                     */
/* data: { colonnes: [{eyebrow, titre, images: [src]}],                */
/*   compteurs?: [{v, label, pre?}], phrase?: string }                   */
/* cues: [drop, counter 1, counter 2…, sentence]                        */
export const Mosaique: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const colonnes: { eyebrow: string; titre: string; images: string[] }[] = data?.colonnes ?? [];
  const compteurs: { v: string; label: string; pre?: string }[] = data?.compteurs ?? [];
  const c0 = cue(cues, 0, 0.2);
  const TW = 88, TH = 49.5, G = 7, PER = 3;
  const colW = PER * TW + (PER - 1) * G;
  const gapC = (1680 - colonnes.length * colW) / Math.max(1, colonnes.length - 1);
  let g = 0;
  const cPh = cue(cues, 1 + compteurs.length, 99);
  // the thumbnails fade by half during the counters
  const firstC = compteurs.length ? cue(cues, 1, 99) : 99;
  const dim = Math.max(ramp(t, firstC, firstC + 0.4) * 0.65, 0);
  return (
    <Paper drift={1.2}>
      {colonnes.map((col, ci) => {
        const x0 = 120 + ci * (colW + gapC);
        return (
          <React.Fragment key={ci}>
            <div style={{ position: "absolute", left: x0, top: 110, width: colW, opacity: ramp(t, c0 + ci * 0.1, c0 + ci * 0.1 + 0.3) }}>
              <Eyebrow size={22}>{nb(col.eyebrow)}</Eyebrow>
              <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 34, lineHeight: 1.08, color: C.contrast, marginTop: 6, height: 76, textWrap: "balance" }}>{nb(col.titre)}</div>
            </div>
            {col.images.map((src, i) => {
              const gi = g++;
              const at = c0 + 0.25 + gi * 0.011;
              const s = sp(at, { damping: 15, stiffness: 140 });
              const x = x0 + (i % PER) * (TW + G);
              const y = 290 + Math.floor(i / PER) * (TH + G);
              return (
                <div
                  key={i}
                  style={{
                    position: "absolute",
                    left: x,
                    top: y,
                    width: TW,
                    height: TH,
                    boxShadow: "0 3px 8px rgba(26,26,26,0.14)",
                    transform: `translateY(${(1 - s) * -900}px) rotate(${(1 - s) * (rnd(gi + 4) - 0.5) * 40}deg)`,
                    opacity: t >= at ? 1 - dim : 0,
                  }}
                >
                  <Img src={staticFile(src)} style={{ width: TW, height: TH, display: "block" }} />
                </div>
              );
            })}
          </React.Fragment>
        );
      })}
      {compteurs.length > 0 && t >= firstC && (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 60 }}>
          {compteurs.map((c, i) => {
            const at = cue(cues, 1 + i, 99);
            const s = sp(at, { damping: 12, stiffness: 190 });
            if (t < at) return <div key={i} style={{ width: 520 }} />;
            return (
              <div key={i} style={{ width: 520, padding: "40px 30px", background: C.paperWarm, boxShadow: shadow, borderTop: `10px solid ${C.accent}`, textAlign: "center", transform: `scale(${0.8 + 0.2 * s})`, opacity: Math.min(1, s * 1.6) }}>
                {c.pre && <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 50, color: C.inkSoft, marginBottom: 4 }}>{nb(c.pre)}</div>}
                <div style={{ fontFamily: F.display, fontWeight: 300, fontSize: 150, lineHeight: 1, color: C.contrast }}>{nb(c.v)}</div>
                <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 42, color: C.contrast, marginTop: 10 }}>{nb(c.label)}</div>
              </div>
            );
          })}
        </AbsoluteFill>
      )}
      {data?.phrase && t >= cPh && (
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 120, textAlign: "center" }}>
          <Rise at={cPh} dur={0.5}>
            <span style={{ display: "inline-block", padding: "18px 44px", background: C.contrast, color: C.paperWarm, fontFamily: F.display, fontStyle: "italic", fontSize: 64 }}>{nb(data.phrase)}</span>
          </Rise>
        </div>
      )}
    </Paper>
  );
};

/* ================================================================== */
/* OVERLAYS (transparent background, left or right third)         */
/* ================================================================== */

/* Surveys: two stacks of answers (year 1, year 2) and a stamp,        */
/* or a quoted answer typed word by word.                              */
/* data (piles): { piles: [{annee, label}], tampon?, side?, x?, w?,    */
/*   tamponCx?, tamponY?, tamponSize?, tamponDepart?, anneau? }         */
/*   x, w: imposed zone (zone_libre.py); the drawing of the stacks (640 px */
/*   at scale 1) is shrunk to fit in it; tampon: \n = line break         */
/*   cues: [stack 1, stack 2, stamp]                                    */
/* data (reponse): { variante: "reponse", eyebrow, texte, side?, y?, x?, w? } */
/*   cues: [card, typing]                                               */
const FicheReponse: React.FC<{ seed: number }> = ({ seed }) => (
  <div style={{ width: 250, height: 150, background: "#FFFFFF", borderRadius: 10, boxShadow: "0 8px 22px rgba(0,0,0,0.28)", padding: "18px 20px", boxSizing: "border-box" }}>
    <div style={{ width: 120 + rnd(seed) * 70, height: 12, borderRadius: 6, background: "rgba(26,26,26,0.7)" }} />
    {[0, 1, 2].map((i) => (
      <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 14 }}>
        <div style={{ width: 18, height: 18, borderRadius: 4, border: `3px solid ${i === Math.floor(rnd(seed + 9) * 3) ? C.accent : "rgba(26,26,26,0.35)"}`, background: i === Math.floor(rnd(seed + 9) * 3) ? C.accent : "transparent" }} />
        <div style={{ width: 90 + rnd(seed + i) * 90, height: 9, borderRadius: 5, background: "rgba(26,26,26,0.22)" }} />
      </div>
    ))}
  </div>
);
export const Sondages: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const fade = useFadeOut(9);
  const left = data?.side !== "right";
  if (data?.variante === "reponse") {
    const at = cue(cues, 0, 0.1);
    const s = sp(at, { damping: 14, stiffness: 170 });
    const txt: string = nb(data?.texte ?? "");
    const k0 = cue(cues, 1, at + 0.4);
    const n = Math.floor(interpolate(t, [k0, k0 + txt.length * 0.045], [0, txt.length], clamp));
    const w = data?.w ?? data?.width ?? 560;
    return (
      <AbsoluteFill style={{ opacity: fade }}>
        <div
          style={{
            position: "absolute",
            left: data?.x ?? sideX(data?.side, w),
            top: data?.y ?? 220,
            width: w,
            background: C.paperWarm,
            borderLeft: `10px solid ${C.accent}`,
            padding: "28px 36px 34px",
            boxShadow: "0 14px 40px rgba(0,0,0,0.35)",
            transform: `translateX(${(1 - s) * (left ? -180 : 180)}px)`,
            opacity: Math.min(1, s * 1.6),
            boxSizing: "border-box",
          }}
        >
          <Eyebrow size={24}>{nb(data?.eyebrow ?? "Survey")}</Eyebrow>
          <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 58, lineHeight: 1.15, color: C.contrast, marginTop: 14, minHeight: 140 }}>
            {"“" + txt.slice(0, n)}
            {n < txt.length ? <span style={{ color: C.accent, opacity: Math.floor(t * 4) % 2 === 0 ? 1 : 0.2 }}>|</span> : <span>{"”"}</span>}
          </div>
        </div>
      </AbsoluteFill>
    );
  }
  const piles: { annee: string; label: string }[] = data?.piles ?? [];
  const tampAt = cue(cues, 2, 99);
  // imposed zone: the drawing (cards from -25 to 615 px, at scale 1) shrunk to w and positioned at x
  const zk = data?.w != null ? data.w / 640 : 1;
  const zx = data?.x != null ? data.x + 25 * zk : null;
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <div style={zx != null ? { position: "absolute", left: zx, top: 0, width: 640, height: 1080, transform: `scale(${zk})`, transformOrigin: "0 0" } : { position: "absolute", inset: 0 }}>
      {piles.map((p, pi) => {
        const at = cue(cues, pi, 0.1 + pi * 1.5);
        if (t < at - 0.05) return null;
        const y0 = 150 + pi * 400;
        const x0 = zx != null ? 0 : left ? 90 : 1920 - 70 - 560;
        return (
          <div key={pi} style={{ position: "absolute", left: x0, top: y0, width: 560, height: 330 }}>
            {Array.from({ length: 9 }).map((_, i) => {
              const s = sp(at + i * 0.07, { damping: 14, stiffness: 200 });
              return (
                <div key={i} style={{ position: "absolute", left: 10 + (rnd(pi * 31 + i) - 0.5) * 40, top: 60 + i * 9, transform: `translateY(${(1 - s) * -260}px) rotate(${(rnd(pi * 17 + i) - 0.5) * 12}deg)`, opacity: Math.min(1, s * 2) }}>
                  <FicheReponse seed={pi * 13 + i} />
                </div>
              );
            })}
            <div style={{ position: "absolute", left: 290, top: 40, opacity: ramp(t, at + 0.2, at + 0.5) }}>
              <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 300, fontSize: 110, lineHeight: 1, color: C.paperWarm, textShadow: "0 4px 18px rgba(0,0,0,0.45)" }}>{p.annee}</div>
              <div style={{ marginTop: 14, display: "inline-block", padding: "10px 22px", borderRadius: 40, background: C.contrast, color: C.paperWarm, fontFamily: F.sans, fontWeight: 700, fontSize: 30, maxWidth: 280 }}>{nb(p.label)}</div>
            </div>
          </div>
        );
      })}
      </div>
      {data?.tampon && (
        <div
          style={{
            position: "absolute",
            top: data?.tamponY ?? 470,
            ...(data?.tamponCx != null ? { left: data.tamponCx, transform: "translateX(-50%)" } : left ? { left: 150 } : { right: 90 }),
          }}
        >
          <StampMark at={tampAt} text={data.tampon} size={data?.tamponSize ?? 66} rotate={-7} depart={data?.tamponDepart} anneau={data?.anneau} />
        </div>
      )}
    </AbsoluteFill>
  );
};

/* Waffle: a survey percentage in 100 cells (N red).                   */
/* data: { eyebrow, value, label, side?, y?, x?, w? }; cues: [carte, remplissage] */
export const Gaufre: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const fade = useFadeOut(9);
  const at = cue(cues, 0, 0.05);
  const c1 = cue(cues, 1, at + 0.35);
  const s = sp(at, { damping: 13, stiffness: 180 });
  const v: number = data?.value ?? 37;
  const k = ramp(t, c1, c1 + 0.9, easeOut);
  const filled = Math.round(v * k);
  const left = data?.side !== "right";
  const w = data?.w ?? 460;
  const sq = 30, g = 6;
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <div
        style={{
          position: "absolute",
          left: data?.x ?? sideX(data?.side, w),
          top: data?.y ?? 150,
          width: w,
          boxSizing: "border-box",
          background: C.paperWarm,
          borderLeft: `10px solid ${C.accent}`,
          padding: "26px 34px 30px",
          boxShadow: "0 14px 40px rgba(0,0,0,0.35)",
          transform: `translateX(${(1 - s) * (left ? -200 : 200)}px) rotate(${left ? -1.2 : 1.2}deg)`,
          opacity: Math.min(1, s * 1.6),
        }}
      >
        <Eyebrow size={24}>{nb(data?.eyebrow ?? "Survey")}</Eyebrow>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginTop: 4 }}>
          <span style={{ fontFamily: F.display, fontWeight: 300, fontSize: 140, lineHeight: 1, letterSpacing: "-0.03em", color: C.contrast, fontVariantNumeric: "tabular-nums" }}>{filled}</span>
          <span style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 76, color: C.accent }}>%</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: `repeat(10, ${sq}px)`, gap: g, marginTop: 14 }}>
          {Array.from({ length: 100 }).map((_, i) => (
            <div key={i} style={{ width: sq, height: sq, borderRadius: 5, background: i < filled ? C.accent : "rgba(26,26,26,0.12)" }} />
          ))}
        </div>
        <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 34, lineHeight: 1.2, color: C.contrast, marginTop: 20, textWrap: "balance" }}>{nb(data?.label ?? "")}</div>
      </div>
    </AbsoluteFill>
  );
};

/* Belief: a received idea written on a card, struck out on the word.  */
/* data: { eyebrow, lignes: [string], verdict?, side?, y?, x?, w?,     */
/*   size?, verdictSize? }: one line per entry of lignes; verdict       */
/*   set on the side of the edge (right if side = right)                */
/* cues: [carte, barre, verdict]                                        */
export const Croyance: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const fade = useFadeOut(9);
  const at = cue(cues, 0, 0.05);
  const cb = data?.barre === false ? 99 : cue(cues, 1, 99);
  const cv = cue(cues, 2, 99);
  const s = sp(at, { damping: 14, stiffness: 170 });
  const lignes: string[] = data?.lignes ?? [];
  const left = data?.side !== "right";
  const w = data?.width ?? 540;
  const size = data?.size ?? 62;
  const vs = sp(cv, { damping: 11, stiffness: 210 });
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <div style={{ position: "absolute", left: data?.x ?? sideX(data?.side, w), top: data?.y ?? 200, width: w, display: "flex", flexDirection: "column", alignItems: left ? "flex-start" : "flex-end" }}>
        <div
          style={{
            alignSelf: "stretch",
            background: C.paperWarm,
            borderLeft: `10px solid ${C.accent}`,
            padding: "26px 36px 30px",
            boxShadow: "0 14px 40px rgba(0,0,0,0.35)",
            transform: `translateX(${(1 - s) * (left ? -180 : 180)}px) rotate(${left ? -1 : 1}deg)`,
            opacity: Math.min(1, s * 1.6),
          }}
        >
          <Eyebrow size={24}>{nb(data?.eyebrow ?? "")}</Eyebrow>
          <div style={{ marginTop: 10 }}>
            {lignes.map((l, i) => {
              const kb = ramp(t, cb + i * 0.22, cb + i * 0.22 + 0.32, easeStd);
              return (
                <div key={i} style={{ position: "relative", width: "fit-content", whiteSpace: "nowrap", fontFamily: F.display, fontStyle: "italic", fontSize: size, lineHeight: 1.12, color: kb > 0 ? C.inkSoft : C.contrast, marginRight: 14 }}>
                  {nb(l)}
                  <div style={{ position: "absolute", left: -6, top: "54%", height: Math.max(5, size * 0.09), width: `calc(${kb * 100}% + ${kb * 12}px)`, background: C.accent, borderRadius: 4, transform: "rotate(-1.5deg)" }} />
                </div>
              );
            })}
          </div>
        </div>
        {data?.verdict && t >= cv && (
          <div
            style={{
              marginTop: 18,
              padding: "14px 30px",
              borderRadius: 50,
              background: C.contrast,
              color: C.paperWarm,
              fontFamily: F.sans,
              fontWeight: 700,
              fontSize: data?.verdictSize ?? 40,
              whiteSpace: "nowrap",
              boxShadow: "0 10px 26px rgba(0,0,0,0.3)",
              transform: `scale(${vs})`,
              transformOrigin: left ? "0 50%" : "100% 50%",
            }}
          >
            {nb(data.verdict)}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

/* ================================================================== */
/* Quote: a sentence from the speaker, line by line on their voice.    */
/* data: { lignes: [string], accent?: index of the red line,           */
/*   eyebrow? }; cues: one per line                                    */
export const Citation: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const lignes: string[] = data?.lignes ?? [];
  const size = data?.size ?? (lignes.some((l) => l.length > 34) ? 76 : 92);
  const c0 = cue(cues, 0, 0.15);
  const barre = ramp(t, c0, c0 + 0.5, easeStd);
  return (
    <Paper drift={1.6}>
      <AbsoluteFill style={{ justifyContent: "center", padding: "0 220px" }}>
        <div style={{ position: "relative", paddingLeft: 60 }}>
          <div style={{ position: "absolute", left: 0, top: 8, bottom: 8, width: 10, background: C.accent, transform: `scaleY(${barre})`, transformOrigin: "50% 0" }} />
          {data?.eyebrow && (
            <div style={{ opacity: ramp(t, c0, c0 + 0.3), marginBottom: 22 }}>
              <Eyebrow size={30}>{nb(data.eyebrow)}</Eyebrow>
            </div>
          )}
          {lignes.map((l, i) => (
            <Rise key={i} at={cue(cues, i, c0 + i * 0.9)} dur={0.55}>
              <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 400, fontSize: size, lineHeight: 1.12, letterSpacing: "-0.01em", color: data?.accent === i ? C.accent : C.contrast, textWrap: "balance" }}>
                {nb(l)}
              </div>
            </Rise>
          ))}
        </div>
      </AbsoluteFill>
    </Paper>
  );
};
