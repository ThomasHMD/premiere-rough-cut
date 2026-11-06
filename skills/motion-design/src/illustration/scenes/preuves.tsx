import React from "react";
import { AbsoluteFill, Img, Loop, OffthreadVideo, interpolate, staticFile, useVideoConfig } from "remotion";
import { Brackets, C, Check, Eyebrow, F, Paper, Rise, clamp, easeOut, easeStd, nb, ramp, shadow, useFadeOut, useSpringAt, useT } from "./kit";
import { SceneProps, StampMark } from "./opaque";

// "Proof" scenes: a story told by documents
// (mails, web pages, photos), figures, lists of requests, diagrams. Generic:
// all the content comes from `data`, all the moments from `cues` (seconds from the start of
// the scene, aligned to the speaker's words by the plan).

const cue = (cues: number[], i: number, fallback: number) =>
  typeof cues?.[i] === "number" ? cues[i] : fallback;

const sideX = (side: string | undefined, w: number) => (side === "left" ? 90 : 1920 - 90 - w);

type Rect = [number, number, number, number];

/* Dark label (note placed on a document, "1 h 22 later"). */
const Note: React.FC<{ at: number; text: string; accent?: boolean }> = ({ at, text, accent }) => {
  const sp = useSpringAt();
  const t = useT();
  if (t < at) return null;
  const s = sp(at, { damping: 12, stiffness: 200 });
  return (
    <div
      style={{
        alignSelf: "flex-start",
        padding: "14px 30px",
        borderRadius: 50,
        background: accent ? C.accent : C.contrast,
        color: "#fff",
        fontFamily: F.sans,
        fontWeight: 700,
        fontSize: 36,
        whiteSpace: "nowrap",
        boxShadow: "0 10px 26px rgba(0,0,0,0.28)",
        transform: `translateX(${(1 - s) * -60}px) scale(${0.9 + 0.1 * s})`,
        opacity: Math.min(1, s * 1.6),
      }}
    >
      {nb(text)}
    </div>
  );
};

/* Mark on lines of text of a document: highlighted (band + stroke), struck through, or frame. */
const Marque: React.FC<{ lignes: Rect[]; at: number; mode: string; scale: number }> = ({ lignes, at, mode, scale }) => {
  const t = useT();
  if (t < at) return null;
  const total = lignes.reduce((a, l) => a + l[2], 0) || 1;
  const dur = 0.5;
  let acc = 0;
  if (mode === "cadre") {
    const x0 = Math.min(...lignes.map((l) => l[0])), y0 = Math.min(...lignes.map((l) => l[1]));
    const x1 = Math.max(...lignes.map((l) => l[0] + l[2])), y1 = Math.max(...lignes.map((l) => l[1] + l[3]));
    const k = ramp(t, at, at + 0.35, easeOut);
    const pad = 14 + (1 - k) * 60;
    const arm = 34 / Math.max(scale, 0.4);
    const b = `${6 / Math.max(scale, 0.4)}px solid ${C.accent}`;
    const base: React.CSSProperties = { position: "absolute", width: arm, height: arm, opacity: k };
    return (
      <>
        <div style={{ ...base, left: x0 - pad, top: y0 - pad, borderLeft: b, borderTop: b }} />
        <div style={{ ...base, left: x1 + pad - arm, top: y0 - pad, borderRight: b, borderTop: b }} />
        <div style={{ ...base, left: x1 + pad - arm, top: y1 + pad - arm, borderRight: b, borderBottom: b }} />
        <div style={{ ...base, left: x0 - pad, top: y1 + pad - arm, borderLeft: b, borderBottom: b }} />
      </>
    );
  }
  return (
    <>
      {lignes.map(([x, y, w, h], i) => {
        const a0 = at + (acc / total) * dur;
        acc += w;
        const a1 = at + (acc / total) * dur;
        const k = ramp(t, a0, a1, easeStd);
        if (mode === "barre") {
          return (
            <div
              key={i}
              style={{ position: "absolute", left: x - 4, top: y + h * 0.48, width: (w + 8) * k, height: Math.max(4, h * 0.11), background: C.accent, borderRadius: 3 }}
            />
          );
        }
        return (
          <React.Fragment key={i}>
            <div style={{ position: "absolute", left: x - 6, top: y - h * 0.08, width: (w + 12) * k, height: h * 1.16, background: "rgba(47,91,234,0.16)", borderRadius: 4 }} />
            <div style={{ position: "absolute", left: x - 6, top: y + h * 1.02, width: (w + 12) * k, height: Math.max(4, h * 0.1), background: C.accent, borderRadius: 3 }} />
          </React.Fragment>
        );
      })}
    </>
  );
};

/* ================================================================== */
/* Proof: a document (mail, web page, photo) that the camera moves across */
/* data: { src, w, h, kind: mail|web|photo, url?, caption?,            */
/*          etapes: [{ lignes?: Rect[], box?: Rect, mode?, zoom? }],     */
/*          tampons?: [{ text, k, x?, y? }], notes?: [{ text, k, accent? }] } */
/* cues: one moment per step (the camera has arrived, the mark          */
/*        draws itself), then those that stamps and notes designate by `k`. */
/* Calm camera: a single movement per step, 0.9 s, started 0.6 s before */
/* the moment; never back to the wide shot between two steps.           */
export const Preuve: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const kind: string = data?.kind ?? "mail";
  const W: number = data?.w ?? 2200;
  const Himg: number = data?.h ?? 1400;
  const chrome = kind === "web" ? 110 : 0;
  const border = kind === "photo" ? Math.round(Math.max(W, Himg) * 0.035) : 0;
  const DW = W + 2 * border;
  const DH = Himg + chrome + 2 * border + (kind === "photo" && data?.caption ? Math.round(DW * 0.06) : 0);
  // view: the rectangle the camera frames (default: the marked lines); the shot puts in it the whole
  // text column around the lines, to never cut a line at the edges
  const etapes: { lignes?: Rect[]; box?: Rect; vue?: Rect; mode?: string; zoom?: number }[] = data?.etapes ?? [];
  const sMax: number = data?.zoomMax ?? (kind === "photo" ? 1.0 : 1.45);
  // wide shot: the whole width in 1600 px (1480 for a photo), the top of the document visible
  const s0 = Math.min((kind === "photo" ? 1480 : 1600) / DW, (kind === "photo" ? 940 : 4000) / DH);
  // the notes live in a banner at the top left (80, 70; 71 px per note, 16 gap):
  // the wide shot puts the document under this banner, the close shot frames its view under it, and
  // in the close shot a paper fade erases what rises beneath it (notes placed over
  // text in close shots)
  const nNotes = (data?.notes ?? []).length;
  const bande = nNotes ? 70 + nNotes * 71 + (nNotes - 1) * 16 + 20 : 0;
  const haut = nNotes ? bande : 70;
  const vue0 = (): [number, number, number] => {
    const cy = DH * s0 <= 960 - (haut - 70) ? DH / 2 - (haut - 70) / s0 / 2 : (540 - haut) / s0;
    return [s0, DW / 2, cy];
  };
  // a mark overflows its lines (frame: 14 px + the strokes; highlight: 6 px) and stays
  // drawn until the end of the scene: the framing counts it, that of the step and those before
  // that fall in the field (frames stuck to the right edge)
  const marques = (j: number): Rect[] => {
    const e = etapes[j];
    if (!e.mode) return [];
    const m = e.mode === "cadre" ? 26 : 10;
    return (e.lignes ?? (e.box ? [e.box] : [])).map((r) => [r[0] - m, r[1] - m, r[2] + 2 * m, r[3] + 2 * m] as Rect);
  };
  const viser = (e: (typeof etapes)[number], i: number): [number, number, number] => {
    const base = e.vue ? [e.vue] : e.lignes && e.lignes.length ? e.lignes : e.box ? [e.box] : null;
    if (!base) return vue0();
    const by0 = Math.min(...base.map((r) => r[1]));
    // with notes: the view is framed in the free height under the banner, centered below it
    const libre = bande ? Math.min(760, 1080 - bande - 110) : 760;
    const yc = bande ? (bande + 1080) / 2 : 540;
    const cadrer = (rs: Rect[]): [number, number, number] => {
      const x0 = Math.min(...rs.map((r) => r[0])), y0 = Math.min(...rs.map((r) => r[1]));
      const x1 = Math.max(...rs.map((r) => r[0] + r[2])), y1 = Math.max(...rs.map((r) => r[1] + r[3]));
      const bw = x1 - x0, bh = y1 - y0;
      // a view (whole text column) is framed in width with a 60 px margin: the paper
      // still grows by 1% during the scene
      let s = e.zoom ?? Math.min(e.vue ? 1800 / (bw + 60) : 1640 / (bw + 120), libre / (bh + 120), sMax);
      s = Math.max(s, s0);
      let cx = border + (x0 + x1) / 2, cy = border + chrome + (y0 + y1) / 2 - (yc - 540) / s;
      // never an empty background on the edges when the document is larger than the frame (the
      // notes banner may, however, show the paper above the document)
      const hw = 960 / s, hh = 540 / s;
      cx = DW * s <= 1920 ? DW / 2 : Math.min(Math.max(cx, hw - 40 / s), DW - hw + 40 / s);
      cy = DH * s <= 1080 - bande ? DH / 2 - (yc - 540) / s : Math.min(Math.max(cy, hh - (60 + bande) / s), DH - hh + 60 / s);
      return [s, cx, cy];
    };
    const rs: Rect[] = [...base, ...marques(i)];
    const c1 = cadrer(rs);
    const [s1, , cy1] = c1;
    const haut0 = cy1 - 540 / s1 - border - chrome, bas0 = cy1 + 540 / s1 - border - chrome;
    const prev = etapes.slice(0, i).flatMap((_, j) => marques(j));
    const avant = prev
      .filter((r) => r[1] >= haut0 && r[1] + r[3] <= bas0) // fully inside the field
      .map((r) => [r[0], by0, r[2], 0] as Rect); // width only: the vertical framing does not move
    const c = avant.length ? cadrer([...rs, ...avant]) : c1;
    // a previous mark half in the field stays cut by the edge for the whole step
    // (title underline at the very top, frame of the 2nd paragraph cut at the
    // bottom): we move it out of the field by shifting the camera if the step's view
    // still fits, otherwise we bring it in whole. Margin 36 px: 24 + the paper drift.
    const M = 36;
    const ecran = (k: [number, number, number], r: Rect) => [
      960 + (r[0] + border - k[1]) * k[0], 540 + (r[1] + border + chrome - k[2]) * k[0],
      960 + (r[0] + r[2] + border - k[1]) * k[0], 540 + (r[1] + r[3] + border + chrome - k[2]) * k[0],
    ];
    const coupees = (k: [number, number, number]) =>
      prev.filter((r) => {
        const [X0, Y0, X1, Y1] = ecran(k, r);
        return X1 > 0 && X0 < 1920 && Y1 > 0 && Y0 < 1080 && (X0 < M || X1 > 1920 - M || Y0 < M || Y1 > 1080 - M);
      });
    const tient = (k: [number, number, number]) =>
      base.every((r) => { const q = ecran(k, r); return q[1] >= (bande ? bande + 50 : 0) && q[3] <= 1050; }) &&
      marques(i).every((r) => { const q = ecran(k, r); return q[1] >= M && q[3] <= 1080 - M; });
    const cut = coupees(c);
    if (!cut.length) return c;
    const [s, cx, cy] = c;
    const hh = 540 / s;
    const dys = cut
      .flatMap((r) => { const q = ecran(c, r); return [-q[3] - 2, 1080 - q[1] + 2]; })
      .sort((a, b) => Math.abs(a) - Math.abs(b));
    for (const dy of dys) {
      const cy2 = cy - dy / s;
      if (DH * s <= 1080 - bande || cy2 < hh - (60 + bande) / s || cy2 > DH - hh + 60 / s) continue;
      const c2: [number, number, number] = [s, cx, cy2];
      if (tient(c2) && !coupees(c2).length) return c2;
    }
    let inc: Rect[] = [...rs, ...avant, ...cut];
    let c3 = cadrer(inc);
    for (let k = 0; k < 3; k++) {
      const plus = coupees(c3);
      if (!plus.length) break;
      inc = [...inc, ...plus];
      c3 = cadrer(inc);
    }
    return c3;
  };
  const plans = [vue0(), ...etapes.map(viser)];
  const MOVE = 0.9, LEAD = 0.6;
  let cam = plans[0];
  etapes.forEach((_, i) => {
    const at = cue(cues, i, 1 + i * 3) - LEAD;
    const k = ramp(t, at, at + MOVE, easeStd);
    if (k <= 0) return;
    const a = cam, b = plans[i + 1];
    cam = [Math.exp(Math.log(a[0]) + (Math.log(b[0]) - Math.log(a[0])) * k), a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
  });
  const [s, cx, cy] = cam;
  const enter = sp(0.0, { damping: 16, stiffness: 120 });
  const tampons: { text: string; k: number; x?: number; y?: number; size?: number }[] = data?.tampons ?? [];
  const notes: { text: string; k: number; accent?: boolean }[] = data?.notes ?? [];
  const url: string = data?.url ?? "";
  return (
    <Paper drift={0.6}>
      <AbsoluteFill style={{ overflow: "hidden" }}>
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            width: DW,
            height: DH,
            transformOrigin: "0 0",
            transform: `translate(${960 - cx * s}px, ${540 - cy * s + (1 - enter) * 80}px) scale(${s})`,
            opacity: Math.min(1, enter * 1.5),
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: kind === "mail" ? "transparent" : "#FFFFFF",
              borderRadius: kind === "web" ? 26 : kind === "photo" ? 6 : 0,
              boxShadow: kind === "mail" ? "none" : `0 ${30 / s}px ${80 / s}px rgba(26,26,26,0.22)`,
              overflow: "hidden",
            }}
          >
            {kind === "web" && (
              <div style={{ position: "absolute", left: 0, top: 0, width: DW, height: chrome, background: "#EAEAEA", display: "flex", alignItems: "center", gap: 18, padding: "0 34px", boxSizing: "border-box" }}>
                {["#E5E5E5", "#E5E5E5", "#E5E5E5"].map((c, i) => (
                  <div key={i} style={{ width: 26, height: 26, borderRadius: 26, background: c, border: "2px solid #D4D4D4" }} />
                ))}
                <div style={{ marginLeft: 24, flex: 1, height: 64, borderRadius: 40, background: "#FFFFFF", display: "flex", alignItems: "center", padding: "0 34px", fontFamily: F.sans, fontSize: 38, color: C.inkSoft }}>
                  {url}
                </div>
              </div>
            )}
            <Img src={staticFile(data?.src ?? "")} style={{ position: "absolute", left: border, top: border + chrome, width: W, height: Himg }} />
            {kind === "photo" && data?.caption && (
              <div style={{ position: "absolute", left: border, right: border, top: border * 1.4 + Himg, fontFamily: F.mono, fontSize: DW * 0.022, color: C.inkSoft }}>
                {data.caption}
              </div>
            )}
          </div>
          <div style={{ position: "absolute", left: border, top: border + chrome }}>
            {etapes.map((e, i) =>
              e.mode && (e.lignes || e.box) ? (
                <Marque key={i} lignes={e.lignes ?? [e.box as Rect]} at={cue(cues, i, 1 + i * 3)} mode={e.mode} scale={s} />
              ) : null,
            )}
          </div>
        </div>
      </AbsoluteFill>
      {kind !== "photo" && bande > 0 && (
        // only in close shot: in wide shot the document is already under the banner
        <AbsoluteFill
          style={{
            background: `linear-gradient(to bottom, ${C.paperWarm} 0px, ${C.paperWarm} ${bande - 20}px, ${C.paperWarm}00 ${bande + 50}px)`,
            opacity: ramp(s / s0, 1.04, 1.25),
          }}
        />
      )}
      <div style={{ position: "absolute", left: 80, top: 70, display: "flex", flexDirection: "column", gap: 16 }}>
        {notes.map((n, i) => (
          <Note key={i} at={n.k < 0 ? 0.15 : cue(cues, n.k, 1)} text={n.text} accent={n.accent} />
        ))}
      </div>
      {tampons.map((tp, i) => (
        <div key={i} style={{ position: "absolute", left: tp.x, right: tp.x === undefined ? 110 : undefined, top: tp.y ?? 120 }}>
          <StampMark at={cue(cues, tp.k, 2)} text={tp.text} size={tp.size ?? 84} rotate={-8} />
        </div>
      ))}
    </Paper>
  );
};

/* ================================================================== */
/* GIF or meme as an overlay, in a white frame, on one side.         */
/* data: { src, srcW, srcH, loopSec, side, w, y, rotate, caption, x? } */
export const Gif: React.FC<SceneProps> = ({ data, cues }) => {
  const sp = useSpringAt();
  const fade = useFadeOut(8);
  const { fps } = useVideoConfig();
  const at = cue(cues, 0, 0.05);
  const s = sp(at, { damping: 12, stiffness: 170 });
  const w: number = data?.w ?? 540;
  const h = Math.round((w * (data?.srcH ?? 480)) / (data?.srcW ?? 480));
  const pad = 14;
  const left = data?.side === "left";
  const mx = data?.theme === "matrix"; // green terminal art direction: black frame, phosphor green rule, straight
  const rot = mx ? 0 : data?.rotate ?? (left ? -2.5 : 2.5);
  const loop = Math.max(1, Math.round((data?.loopSec ?? 2) * fps));
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <div
        style={{
          position: "absolute",
          left: data?.x ?? sideX(data?.side, w + 2 * pad),
          top: data?.y ?? Math.max(60, 540 - (h + 2 * pad) / 2 - 40),
          padding: pad,
          paddingBottom: data?.caption ? 64 : pad,
          background: mx ? "#010805" : "#FFFFFF",
          boxShadow: mx ? "0 0 0 3px #19FF7F, 0 0 26px rgba(25,255,127,0.45)" : "0 22px 50px rgba(0,0,0,0.38)",
          transform: `translateY(${(1 - s) * 140}px) rotate(${rot}deg) scale(${0.85 + 0.15 * s})`,
          opacity: Math.min(1, s * 1.8),
        }}
      >
        <div style={{ width: w, height: h, overflow: "hidden", background: "#000" }}>
          <Loop durationInFrames={loop}>
            <OffthreadVideo src={staticFile(data?.src ?? "")} muted style={{ width: w, height: h, objectFit: "cover" }} />
          </Loop>
        </div>
        {data?.caption && (
          <div style={{ position: "absolute", left: pad, right: pad, bottom: 14, textAlign: "center", fontFamily: F.display, fontStyle: "italic", fontSize: 36, color: C.contrast }}>
            {data.caption}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

/* ================================================================== */
/* Generic chapter card: "Chapter 3 of 8", title, question            */
/* data: { n, total, titre, question, size }                           */
export const Chapitre: React.FC<SceneProps> = ({ data }) => {
  const t = useT();
  const sp = useSpringAt();
  const n: number = data?.n ?? 1;
  const total: number = data?.total ?? 8;
  const s = sp(0.02, { damping: 14, stiffness: 150 });
  return (
    <Paper drift={2}>
      <AbsoluteFill style={{ padding: "0 120px", flexDirection: "row", alignItems: "center" }}>
        <div style={{ width: 600, overflow: "hidden", height: 520 }}>
          <div
            style={{
              fontFamily: F.display,
              fontStyle: "italic",
              fontWeight: 300,
              fontSize: 500,
              lineHeight: 1,
              letterSpacing: "-0.04em",
              color: C.accent,
              transform: `translateY(${(1 - s) * 110}%)`,
            }}
          >
            {String(n).padStart(2, "0")}
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <Rise at={0.1}>
            <Eyebrow size={34}>{nb(data?.question ?? "")}</Eyebrow>
          </Rise>
          <div style={{ height: 22 }} />
          <Rise at={0.16} dur={0.55}>
            <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 400, fontSize: data?.size ?? 118, lineHeight: 1.06, letterSpacing: "-0.015em", color: C.contrast }}>
              {nb(data?.titre ?? "")}
            </div>
          </Rise>
        </div>
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 120, right: 120, bottom: 110, display: "flex", gap: 12, alignItems: "center" }}>
        {Array.from({ length: total }).map((_, i) => {
          const kk = ramp(t, 0.25 + i * 0.04, 0.5 + i * 0.04, easeStd);
          return (
            <div key={i} style={{ flex: 1, height: 10, borderRadius: 6, background: "rgba(26,26,26,0.14)", overflow: "hidden" }}>
              <div style={{ width: `${i < n ? kk * 100 : 0}%`, height: "100%", background: i === n - 1 ? C.accent : C.contrast }} />
            </div>
          );
        })}
        <div style={{ marginLeft: 20, fontFamily: F.sans, fontWeight: 700, fontSize: 28, letterSpacing: "0.08em", color: C.contrast, whiteSpace: "nowrap" }}>
          {`CHAPITRE ${n} / ${total}`}
        </div>
      </div>
    </Paper>
  );
};

/* ================================================================== */
/* Video title: words that rise, brackets that lock.                  */
/* data: { eyebrow, mots: [{ text, accent? }], size }; cues: [verrou] */
export const Titre: React.FC<SceneProps> = ({ data, cues }) => {
  const mots: { text: string; accent?: boolean }[] = data?.mots ?? [{ text: "Title" }];
  const lock = cue(cues, 0, 0.3 + mots.length * 0.15);
  return (
    <Paper dark drift={2.5}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        {data?.eyebrow && (
          <Rise at={0.02}>
            <Eyebrow size={32}>{data.eyebrow}</Eyebrow>
          </Rise>
        )}
        <div style={{ height: 30 }} />
        <div style={{ display: "flex", gap: 50, flexWrap: "wrap", justifyContent: "center", maxWidth: 1700 }}>
          {mots.map((m, i) => (
            <Rise key={i} at={0.1 + i * 0.15} dur={0.45}>
              <span style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 400, fontSize: data?.size ?? 210, lineHeight: 1.08, letterSpacing: "-0.02em", color: m.accent ? C.accent : C.paperWarm }}>
                {m.text}
              </span>
            </Rise>
          ))}
        </div>
      </AbsoluteFill>
      <Brackets x={150} y={280} w={1620} h={520} at={lock} arm={54} stroke={6} />
    </Paper>
  );
};

/* ================================================================== */
/* Error message: a neutral window, the text types itself line by line. */
/* data: { titre, lignes: [string], eyebrow }; cues: one per line      */
export const Dialogue: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const lignes: string[] = data?.lignes ?? [];
  const s = sp(0.02, { damping: 15, stiffness: 150 });
  return (
    <Paper drift={1.5}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        {data?.eyebrow && (
          <Rise at={0.05}>
            <Eyebrow size={30}>{data.eyebrow}</Eyebrow>
          </Rise>
        )}
        <div style={{ height: 36 }} />
        <div
          style={{
            width: 1340,
            background: "#FFFFFF",
            borderRadius: 26,
            boxShadow: shadow,
            overflow: "hidden",
            transform: `translateY(${(1 - s) * 90}px) scale(${0.94 + 0.06 * s})`,
            opacity: Math.min(1, s * 1.6),
          }}
        >
          <div style={{ height: 76, background: "#EAEAEA", display: "flex", alignItems: "center", padding: "0 34px", gap: 14 }}>
            {[0, 1, 2].map((i) => (
              <div key={i} style={{ width: 20, height: 20, borderRadius: 20, background: "#E5E5E5", border: "2px solid #D4D4D4" }} />
            ))}
            <div style={{ marginLeft: 20, fontFamily: F.sans, fontWeight: 700, fontSize: 30, color: C.inkSoft }}>{data?.titre ?? "Login"}</div>
          </div>
          <div style={{ padding: "60px 70px 70px", display: "flex", gap: 50, alignItems: "flex-start" }}>
            <div style={{ width: 120, height: 120, borderRadius: 120, background: C.accent, color: "#fff", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: F.sans, fontWeight: 700, fontSize: 84 }}>
              !
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
              {lignes.map((l, i) => {
                const at = cue(cues, i, 0.4 + i * 2);
                const n = Math.floor(interpolate(t, [at, at + l.length * 0.03], [0, l.length], clamp));
                return (
                  <div key={i} style={{ fontFamily: F.sans, fontWeight: i === 0 ? 700 : 400, fontSize: i === 0 ? 58 : 48, lineHeight: 1.2, color: C.contrast, minHeight: 60 }}>
                    {l.slice(0, n)}
                    {t >= at && n < l.length && <span style={{ color: C.accent }}>|</span>}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </AbsoluteFill>
    </Paper>
  );
};

/* ================================================================== */
/* Timeline: dated milestones on a line, each revealed on its word.   */
/* data: { eyebrow, titre, jalons: [{ annee, texte, k, img? }],        */
/*          tampon?: { text, k } } ; k = -1: visible from the start */
export const Frise: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const jalons: { annee: string; texte: string; k: number; img?: string }[] = data?.jalons ?? [];
  const n = jalons.length;
  // 190 px margin: the last date ("26/10/2007") used to end 10 px from the edge, as the paper grows
  const x0 = 190, x1 = 1730, ly = 600;
  const pas = n > 1 ? (x1 - x0) / (n - 1) : 0;
  const quand = (j: { k: number }) => (j.k < 0 ? 0.1 : cue(cues, j.k, 1 + j.k * 2));
  const vus = jalons.map((j, i) => ({ i, at: quand(j) })).filter((v) => t >= v.at);
  const dernier = vus.length ? vus.reduce((a, b) => (b.at > a.at ? b : a)).i : -1;
  const line = ramp(t, 0.0, 0.7, easeStd);
  return (
    <Paper drift={1.2}>
      <div style={{ position: "absolute", left: 150, top: 90 }}>
        <Rise at={0.05}>
          <Eyebrow size={30}>{data?.eyebrow ?? ""}</Eyebrow>
        </Rise>
        {data?.titre && (
          <Rise at={0.12}>
            <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 66, color: C.contrast, marginTop: 10 }}>{nb(data.titre)}</div>
          </Rise>
        )}
      </div>
      <div style={{ position: "absolute", left: x0 - 40, top: ly - 3, width: (x1 - x0 + 80) * line, height: 6, background: C.contrast, borderRadius: 3 }} />
      {jalons.map((j, i) => {
        const at = quand(j);
        if (t < at) return null;
        const a = sp(at, { damping: 13, stiffness: 190 });
        const x = x0 + i * pas;
        const on = i === dernier;
        const col = on ? C.accent : C.contrast;
        const w = Math.min(250, pas - 14);
        return (
          <React.Fragment key={i}>
            <div style={{ position: "absolute", left: x - 16, top: ly - 16, width: 32, height: 32, borderRadius: 32, background: col, transform: `scale(${a})` }} />
            {j.img && (
              <Img
                src={staticFile(j.img)}
                style={{ position: "absolute", left: x - 95, top: ly - 420, width: 190, boxShadow: shadow, transform: `translateY(${(1 - a) * 40}px)`, opacity: Math.min(1, a * 1.6) }}
              />
            )}
            <div style={{ position: "absolute", left: x - w / 2, width: w, top: ly - 120, textAlign: "center", transform: `translateY(${(1 - a) * 30}px)`, opacity: Math.min(1, a * 1.6) }}>
              <div style={{ fontFamily: F.display, fontWeight: 400, fontSize: j.annee.length > 6 ? 42 : 68, lineHeight: 1, color: col, letterSpacing: "-0.02em" }}>{j.annee}</div>
            </div>
            <div
              style={{
                position: "absolute",
                left: x - w / 2,
                width: w,
                top: ly + 44,
                textAlign: "center",
                fontFamily: F.sans,
                fontWeight: on ? 700 : 400,
                fontSize: 31,
                lineHeight: 1.22,
                color: on ? C.contrast : C.inkSoft,
                transform: `translateY(${(1 - a) * 30}px)`,
                opacity: Math.min(1, a * 1.6),
              }}
            >
              {nb(j.texte)}
            </div>
          </React.Fragment>
        );
      })}
      {data?.tampon && (
        <div style={{ position: "absolute", left: data.tampon.x ?? 1180, top: data.tampon.y ?? 860 }}>
          <StampMark at={cue(cues, data.tampon.k, 3)} text={data.tampon.text} size={data.tampon.size ?? 62} rotate={-6} />
        </div>
      )}
    </Paper>
  );
};

/* ================================================================== */
/* Duel: two verbatim quotes side by side, marked on the words.      */
/* data: { gauche: Carte, droite: Carte, centre?: { text, k } }        */
/* Carte : { date, auteur, k (apparition), segments: [{ t, marques?: [{ k, mode }] }] } */
type Seg = { t: string; marques?: { k: number; mode: string }[] };
type CarteD = { date: string; auteur: string; k: number; segments: Seg[]; lang?: string };
const CarteDuel: React.FC<{ c: CarteD; cues: number[]; left: boolean }> = ({ c, cues, left }) => {
  const t = useT();
  const sp = useSpringAt();
  const at = cue(cues, c.k, 0.2);
  const s = sp(at, { damping: 14, stiffness: 150 });
  if (t < at) return <div style={{ width: 780 }} />;
  return (
    <div
      style={{
        width: 780,
        background: "#FFFFFF",
        borderRadius: 18,
        boxShadow: shadow,
        padding: "44px 50px 50px",
        boxSizing: "border-box",
        transform: `translateY(${(1 - s) * 80}px) rotate(${left ? -1.2 : 1.2}deg)`,
        opacity: Math.min(1, s * 1.6),
      }}
    >
      <Eyebrow size={26}>{c.date}</Eyebrow>
      <div style={{ fontFamily: F.sans, fontSize: 26, color: C.muted, marginTop: 6 }}>{c.auteur}</div>
      <div style={{ height: 26 }} />
      <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 50, lineHeight: 1.3, color: C.contrast }} lang={c.lang ?? "en"}>
        {c.segments.map((sg, i) => {
          const bgs: string[] = [];
          const sizes: string[] = [];
          for (const m of sg.marques ?? []) {
            const ma = cue(cues, m.k, 99);
            const k = ramp(t, ma, ma + 0.45, easeStd);
            if (k <= 0) continue;
            if (m.mode === "barre") bgs.push(`linear-gradient(transparent 50%, ${C.accent} 50%, ${C.accent} 58%, transparent 58%)`);
            else bgs.push(`linear-gradient(transparent 8%, rgba(47,91,234,0.18) 8%, rgba(47,91,234,0.18) 88%, ${C.accent} 88%, ${C.accent} 94%, transparent 94%)`);
            sizes.push(`${k * 100}% 100%`);
          }
          const barre = (sg.marques ?? []).some((m) => m.mode === "barre" && t >= cue(cues, m.k, 99) + 0.3);
          return (
            <span
              key={i}
              style={{
                backgroundImage: bgs.join(", ") || undefined,
                backgroundSize: sizes.join(", ") || undefined,
                backgroundRepeat: "no-repeat",
                WebkitBoxDecorationBreak: "clone",
                boxDecorationBreak: "clone",
                color: barre ? C.muted : undefined,
              }}
            >
              {sg.t}
            </span>
          );
        })}
      </div>
    </div>
  );
};

export const Duel: React.FC<SceneProps> = ({ data, cues }) => {
  const sp = useSpringAt();
  const t = useT();
  const centre = data?.centre;
  const ca = centre ? cue(cues, centre.k, 99) : 99;
  const cs = sp(ca, { damping: 11, stiffness: 200 });
  return (
    <Paper drift={1}>
      {data?.eyebrow && (
        <div style={{ position: "absolute", left: 0, right: 0, top: 80, textAlign: "center" }}>
          <Rise at={0.05}>
            <Eyebrow size={30}>{data.eyebrow}</Eyebrow>
          </Rise>
        </div>
      )}
      <AbsoluteFill style={{ flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 90, paddingBottom: 40 }}>
        <CarteDuel c={data?.gauche} cues={cues} left />
        <CarteDuel c={data?.droite} cues={cues} left={false} />
      </AbsoluteFill>
      {centre && t >= ca && (
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 90, display: "flex", justifyContent: "center" }}>
          <div
            style={{
              padding: "20px 46px",
              borderRadius: 60,
              background: C.contrast,
              color: C.paperWarm,
              fontFamily: F.sans,
              fontWeight: 700,
              fontSize: 46,
              boxShadow: shadow,
              transform: `scale(${cs})`,
            }}
          >
            {nb(centre.text)}
          </div>
        </div>
      )}
    </Paper>
  );
};

/* ================================================================== */
/* Versus: two durations face to face ("3 days and 4 hours" against  */
/* "1 business day"). data: { eyebrow, gauche: {label, valeur, note},  */
/* droite: {...}, verdict? }; cues: [gauche, droite, verdict]         */
export const Versus: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const col = (c: any, i: number, accent: boolean) => {
    const at = cue(cues, i, 0.3 + i * 1.5);
    const s = sp(at, { damping: 12, stiffness: 170 });
    return (
      <div style={{ width: 760, textAlign: "center", opacity: t >= at ? Math.min(1, s * 1.6) : 0, transform: `translateY(${(1 - s) * 60}px)` }}>
        <Eyebrow size={32} color={accent ? C.accent : C.inkSoft}>
          {c?.label ?? ""}
        </Eyebrow>
        <div style={{ height: 18 }} />
        <div style={{ fontFamily: F.display, fontWeight: 300, fontSize: c?.size ?? 150, lineHeight: 1.04, letterSpacing: "-0.03em", color: accent ? C.accent : C.contrast }}>
          {nb(c?.valeur ?? "")}
        </div>
        {c?.note && <div style={{ fontFamily: F.sans, fontSize: 36, color: C.inkSoft, marginTop: 18 }}>{nb(c.note)}</div>}
      </div>
    );
  };
  const va = cue(cues, 2, 99);
  const vs = sp(va, { damping: 10, stiffness: 220 });
  return (
    <Paper drift={2}>
      {data?.eyebrow && (
        <div style={{ position: "absolute", left: 0, right: 0, top: 110, textAlign: "center" }}>
          <Rise at={0.05}>
            <Eyebrow size={30} color={C.contrast}>
              {data.eyebrow}
            </Eyebrow>
          </Rise>
        </div>
      )}
      <AbsoluteFill style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 40 }}>
        {col(data?.gauche, 0, true)}
        <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 64, color: C.muted, opacity: ramp(t, cue(cues, 1, 2) - 0.2, cue(cues, 1, 2)) }}>contre</div>
        {col(data?.droite, 1, false)}
      </AbsoluteFill>
      {data?.verdict && t >= va && (
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 120, display: "flex", justifyContent: "center" }}>
          <div style={{ padding: "18px 44px", borderRadius: 60, background: C.accent, color: "#fff", fontFamily: F.sans, fontWeight: 700, fontSize: 46, transform: `scale(${vs})` }}>
            {nb(data.verdict)}
          </div>
        </div>
      )}
    </Paper>
  );
};

/* ================================================================== */
/* Requests: a grid of N requests, ticked, half-done or struck out   */
/* along the voice. data: { eyebrow, titre, items: [string],          */
/* actions: [{ i?: number, etat: ok|moitie|non, reste?: true }], bilan } */
/* cues: [apparition, one per action, bilan]                           */
export const Demandes: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const items: string[] = data?.items ?? [];
  const actions: { i?: number; etat: string; reste?: boolean }[] = data?.actions ?? [];
  const a0 = cue(cues, 0, 0.2);
  const etat: (null | { e: string; at: number })[] = items.map(() => null);
  actions.forEach((a, j) => {
    const at = cue(cues, 1 + j, 99);
    if (a.reste) {
      etat.forEach((v, i) => {
        if (v === null || v.at > at) etat[i] = t >= at ? { e: a.etat, at: at + i * 0.04 } : etat[i];
      });
    } else if (typeof a.i === "number" && t >= at) {
      etat[a.i] = { e: a.etat, at };
    }
  });
  const ba = cue(cues, 1 + actions.length, 99);
  const bs = sp(ba, { damping: 9, stiffness: 240 });
  const cols = 4;
  return (
    <Paper drift={1}>
      <div style={{ position: "absolute", left: 130, top: 70 }}>
        <Rise at={0.05}>
          <Eyebrow size={30}>{data?.eyebrow ?? ""}</Eyebrow>
        </Rise>
        <Rise at={0.1}>
          <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 64, color: C.contrast, marginTop: 6 }}>{nb(data?.titre ?? "")}</div>
        </Rise>
      </div>
      <div style={{ position: "absolute", left: 130, top: 250, width: 1660, display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 22 }}>
        {items.map((it, i) => {
          const at = a0 + i * 0.07;
          const s = sp(at, { damping: 13, stiffness: 200 });
          const e = etat[i];
          const k = e ? ramp(t, e.at, e.at + 0.3, easeStd) : 0;
          const non = e?.e === "non";
          return (
            <div
              key={i}
              style={{
                position: "relative",
                height: 150,
                background: "#FFFFFF",
                borderRadius: 16,
                boxShadow: "0 10px 26px rgba(26,26,26,0.12)",
                padding: "20px 26px",
                boxSizing: "border-box",
                display: "flex",
                gap: 18,
                alignItems: "center",
                transform: `scale(${s})`,
                opacity: (t >= at ? 1 : 0) * (non ? 1 - 0.5 * k : 1),
              }}
            >
              <div style={{ fontFamily: F.display, fontWeight: 300, fontSize: 58, color: C.muted, width: 62, flexShrink: 0 }}>{i + 1}</div>
              <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 31, lineHeight: 1.18, color: C.contrast }}>{nb(it)}</div>
              {e?.e === "ok" && (
                <div style={{ position: "absolute", right: -14, top: -14 }}>
                  <Check at={e.at} size={58} />
                </div>
              )}
              {e?.e === "moitie" && (
                <div style={{ position: "absolute", right: -14, top: -14, width: 58, height: 58, borderRadius: 58, border: `5px solid ${C.accent}`, boxSizing: "border-box", overflow: "hidden", transform: `scale(${sp(e.at, { damping: 10, stiffness: 220 })})`, background: "#fff" }}>
                  <div style={{ position: "absolute", left: 0, top: 0, width: "50%", height: "100%", background: C.accent }} />
                </div>
              )}
              {non && <div style={{ position: "absolute", left: 16, top: 72, width: (1660 / cols - 54) * k, height: 6, background: C.accent, borderRadius: 3, transform: "rotate(-3deg)" }} />}
            </div>
          );
        })}
      </div>
      {data?.bilan && t >= ba && (
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 70, display: "flex", justifyContent: "center" }}>
          <div style={{ padding: "18px 50px", borderRadius: 60, background: C.contrast, color: C.paperWarm, fontFamily: F.sans, fontWeight: 700, fontSize: 52, boxShadow: shadow, transform: `scale(${bs})` }}>
            {nb(data.bilan)}
          </div>
        </div>
      )}
    </Paper>
  );
};

/* ================================================================== */
/* Texts: what the law requires, what I got. One line per cue.        */
/* data: { eyebrow, titres: [a, b], lignes: [{ texte, impose, eu }] }  */
export const Textes: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  // k: cue of the line (default: its rank); ke: cue of "what I got" (default: line + 0.8 s)
  const lignes: { texte: string; impose: string; eu: string; k?: number; ke?: number }[] = data?.lignes ?? [];
  const titres: string[] = data?.titres ?? ["What the text requires", "What I got"];
  return (
    <Paper drift={0.8}>
      <div style={{ position: "absolute", left: 120, top: 70 }}>
        <Rise at={0.05}>
          <Eyebrow size={30}>{data?.eyebrow ?? ""}</Eyebrow>
        </Rise>
      </div>
      <div style={{ position: "absolute", left: 120, right: 120, top: 140, display: "flex", fontFamily: F.sans, fontWeight: 700, fontSize: 30, letterSpacing: "0.06em", textTransform: "uppercase", color: C.muted, opacity: ramp(t, 0.1, 0.4) }}>
        <div style={{ width: 300 }} />
        <div style={{ flex: 1.15 }}>{titres[0]}</div>
        <div style={{ flex: 1, color: C.accent }}>{titres[1]}</div>
      </div>
      <div style={{ position: "absolute", left: 120, right: 120, top: 200, display: "flex", flexDirection: "column", gap: 16 }}>
        {lignes.map((l, i) => {
          const at = cue(cues, l.k ?? i, 0.4 + i * 2);
          const ae = Math.max(at + 0.3, typeof l.ke === "number" ? cue(cues, l.ke, at + 0.8) : at + 0.8);
          const a = sp(at, { damping: 14, stiffness: 180 });
          const b = sp(ae, { damping: 12, stiffness: 200 });
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 0, background: "#FFFFFF", borderRadius: 16, padding: "20px 0", boxShadow: "0 8px 22px rgba(26,26,26,0.10)", opacity: t >= at ? Math.min(1, a * 1.6) : 0, transform: `translateY(${(1 - a) * 40}px)` }}>
              <div style={{ width: 300, paddingLeft: 30, boxSizing: "border-box", fontFamily: F.sans, fontWeight: 700, fontSize: 30, color: C.contrast }}>{nb(l.texte)}</div>
              <div style={{ flex: 1.15, paddingRight: 30, fontFamily: F.display, fontStyle: "italic", fontSize: 36, lineHeight: 1.2, color: C.contrast }}>{nb(l.impose)}</div>
              <div style={{ flex: 1, paddingRight: 30, fontFamily: F.sans, fontWeight: 700, fontSize: 34, lineHeight: 1.2, color: C.accent, opacity: t >= ae ? Math.min(1, b * 1.6) : 0, transform: `translateX(${(1 - b) * 40}px)` }}>
                {nb(l.eu)}
              </div>
            </div>
          );
        })}
      </div>
    </Paper>
  );
};

/* ================================================================== */
/* Nodes: a backup diagram. A center, nodes around it,                */
/* linked along the voice; links that get cut; final stamp.           */
/* data: { eyebrow, titre, centre: {label, sub}, noeuds: [{label, sub, k}], */
/*          coupe?: { k, noeuds?: [index] }, croix?: k, tampon?: {text, k} } */
export const Noeuds: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const noeuds: { label: string; sub?: string; k: number }[] = data?.noeuds ?? [];
  const n = noeuds.length;
  const C0 = { x: 960, y: 600 };
  const R = { x: 640, y: 300 };
  const pos = noeuds.map((_, i) => {
    const a = Math.PI * (n === 1 ? 0.5 : 1 - i / (n - 1));
    return { x: C0.x + R.x * Math.cos(a), y: C0.y - R.y * Math.sin(a) * 0.9 + (n > 3 ? 40 : 0) };
  });
  const coupeAt = data?.coupe ? cue(cues, data.coupe.k, 99) : 99;
  const coupes: number[] | null = data?.coupe?.noeuds ?? null;
  const croixAt = typeof data?.croix === "number" ? cue(cues, data.croix, 99) : 99;
  const cs = sp(0.05, { damping: 14, stiffness: 150 });
  const box = (label: string, sub: string | undefined, accent: boolean, big = false): React.ReactNode => (
    <div style={{ background: accent ? C.contrast : "#FFFFFF", color: accent ? C.paperWarm : C.contrast, borderRadius: 20, boxShadow: shadow, padding: big ? "30px 44px" : "22px 32px", textAlign: "center", minWidth: big ? 420 : 300 }}>
      <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: big ? 44 : 36, lineHeight: 1.15, whiteSpace: "nowrap" }}>{nb(label)}</div>
      {sub && <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: big ? 36 : 32, marginTop: 8, color: accent ? "rgba(242,242,242,0.8)" : C.accent, whiteSpace: "nowrap" }}>{nb(sub)}</div>}
    </div>
  );
  return (
    <Paper drift={1}>
      <div style={{ position: "absolute", left: 120, top: 70 }}>
        <Rise at={0.05}>
          <Eyebrow size={30}>{data?.eyebrow ?? ""}</Eyebrow>
        </Rise>
        {data?.titre && (
          <Rise at={0.1}>
            <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 62, color: C.contrast, marginTop: 6 }}>{nb(data.titre)}</div>
          </Rise>
        )}
      </div>
      <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0 }}>
        {noeuds.map((nd, i) => {
          const at = cue(cues, nd.k, 1 + i);
          const k = ramp(t, at, at + 0.45, easeStd);
          if (k <= 0) return null;
          const p = pos[i];
          const cut = t >= coupeAt && (coupes === null || coupes.includes(i));
          return (
            <line
              key={i}
              x1={C0.x}
              y1={C0.y}
              x2={C0.x + (p.x - C0.x) * k}
              y2={C0.y + (p.y - C0.y) * k}
              stroke={cut ? C.accent : C.contrast}
              strokeWidth={6}
              strokeDasharray={cut ? "18 16" : undefined}
              opacity={cut ? 0.9 : 0.55}
            />
          );
        })}
      </svg>
      <div style={{ position: "absolute", left: C0.x, top: C0.y, transform: `translate(-50%, -50%) scale(${cs})` }}>
        {box(data?.centre?.label ?? "", data?.centre?.sub, true, true)}
        {t >= croixAt && (
          <svg width={200} height={200} viewBox="0 0 100 100" style={{ position: "absolute", left: "50%", top: "50%", transform: `translate(-50%, -50%) scale(${sp(croixAt, { damping: 9, stiffness: 240 })})` }}>
            <path d="M14 14 L86 86 M86 14 L14 86" stroke={C.accent} strokeWidth={12} strokeLinecap="round" />
          </svg>
        )}
      </div>
      {noeuds.map((nd, i) => {
        const at = cue(cues, nd.k, 1 + i);
        if (t < at) return null;
        const s = sp(at + 0.3, { damping: 12, stiffness: 190 });
        return (
          <div key={i} style={{ position: "absolute", left: pos[i].x, top: pos[i].y, transform: `translate(-50%, -50%) scale(${s})` }}>
            {box(nd.label, nd.sub, false)}
          </div>
        );
      })}
      {data?.tampon && (
        <div style={{ position: "absolute", left: data.tampon.x ?? 1250, top: data.tampon.y ?? 860 }}>
          <StampMark at={cue(cues, data.tampon.k, 99)} text={data.tampon.text} size={data.tampon.size ?? 60} rotate={-6} />
        </div>
      )}
    </Paper>
  );
};

/* ================================================================== */
/* Figures: a few giant numbers with their caption (the 3-2-1 rule).  */
/* data: { eyebrow, items: [{ v, label }] }; cues: one per number        */
export const Chiffres: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const items: { v: string; label: string }[] = data?.items ?? [];
  // the column and the body follow the length of the numbers: "100" at 380 px makes
  // 576 px wide, it used to overflow its 440 px onto its neighbor
  const longest = Math.max(1, ...items.map((it) => it.v.length));
  const w = items.length <= 2 ? 680 : items.length === 3 ? 520 : 400;
  const corps = Math.min(380, Math.floor(w / (0.54 * longest)));
  return (
    <Paper drift={2}>
      <div style={{ position: "absolute", left: 0, right: 0, top: 150, textAlign: "center" }}>
        <Rise at={0.05}>
          <Eyebrow size={34}>{data?.eyebrow ?? ""}</Eyebrow>
        </Rise>
      </div>
      <AbsoluteFill style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 120 }}>
        {items.map((it, i) => {
          const at = cue(cues, i, 0.3 + i);
          const s = sp(at, { damping: 10, stiffness: 200 });
          return (
            <div key={i} style={{ width: w, textAlign: "center", opacity: t >= at ? 1 : 0.12 }}>
              <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 300, fontSize: corps, lineHeight: 1, color: i === 0 ? C.accent : C.contrast, transform: `scale(${t >= at ? 0.7 + 0.3 * s : 0.7})` }}>{it.v}</div>
              <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 46, color: C.contrast, marginTop: 10, opacity: t >= at ? Math.min(1, s * 1.5) : 0 }}>{nb(it.label)}</div>
            </div>
          );
        })}
      </AbsoluteFill>
    </Paper>
  );
};

/* ================================================================== */
/* Shared folder: photo documentation, dozens of folders.             */
/* data: { titre, noms: [string], cible, phase: "remplir"|"partage",    */
/*          etiquettes: [{ text, k }] }                                  */
/* cues (fill): [folder, start of the fill, end?]: without an end, the */
/*                  folders drop in one go; with one, they accumulate */
/* cues (share): [share, scan, target spotted, context, stamp]        */
export const Dossier: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const noms: string[] = data?.noms ?? [];
  const cible: string = data?.cible ?? "";
  const partage = data?.phase === "partage";
  const fill = partage ? -1 : cue(cues, 1, 1.5);
  const pas = !partage && typeof cues?.[2] === "number" && noms.length > 1 ? Math.max(0.09, (cues[2] - fill) / (noms.length - 1)) : 0.09;
  const shareAt = partage ? cue(cues, 0, 0.5) : 99;
  const scanAt = partage ? cue(cues, 1, 99) : 99;
  const flagAt = partage ? cue(cues, 2, 99) : 99;
  const ctxAt = partage ? cue(cues, 3, 99) : 99;
  const tampAt = partage ? cue(cues, 4, 99) : 99;
  const ctx: string[] = data?.contexte ?? [];
  const sh = ramp(t, shareAt, shareAt + 0.9, easeStd);
  const s0 = sp(partage ? 0 : cue(cues, 0, 0.1), { damping: 15, stiffness: 140 });
  const cols = 4;
  const scanY = ramp(t, scanAt, scanAt + 2.2, easeStd);
  return (
    <Paper drift={0.8}>
      <div
        style={{
          position: "absolute",
          left: partage ? 110 - sh * 30 : (1920 - 1180) / 2,
          top: 110,
          width: 1180,
          height: 860,
          background: "#FFFFFF",
          borderRadius: 26,
          boxShadow: shadow,
          padding: "36px 40px",
          boxSizing: "border-box",
          transform: `scale(${(partage ? 1 : s0) * (1 - 0.06 * sh)})`,
          transformOrigin: partage ? "0 50%" : "50% 50%",
          overflow: "hidden",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 26 }}>
          <svg viewBox="0 0 24 24" width={54} height={54} fill="none" stroke={C.contrast} strokeWidth={1.8}>
            <path d="M3 6.5h6l2 2h10v10.5H3z" />
          </svg>
          <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 40, color: C.contrast }}>{data?.titre ?? "Documentation"}</div>
          <div style={{ marginLeft: "auto", fontFamily: F.sans, fontSize: 28, color: C.muted }}>{data?.compte ?? ""}</div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 16 }}>
          {noms.map((nm, i) => {
            const at = partage ? -1 : fill + i * pas;
            const a = partage ? 1 : sp(at, { damping: 13, stiffness: 220 });
            const isC = nm === cible && t >= flagAt;
            const isCtx = ctx.includes(nm) && t >= ctxAt;
            return (
              <div
                key={i}
                style={{
                  position: "relative",
                  height: 128,
                  borderRadius: 14,
                  background: isC ? C.accentWash : C.paperWarm,
                  border: `3px solid ${isC ? C.accent : isCtx ? C.contrast : "transparent"}`,
                  padding: "14px 18px",
                  boxSizing: "border-box",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  transform: `scale(${a})`,
                  opacity: partage || t >= at ? 1 : 0,
                }}
              >
                <svg viewBox="0 0 24 24" width={38} height={38} fill="none" stroke={isC ? C.accent : C.inkSoft} strokeWidth={1.8}>
                  <path d="M3 6.5h6l2 2h10v10.5H3z" />
                </svg>
                <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 25, lineHeight: 1.1, color: isC ? C.accent : C.contrast }}>{nm}</div>
                {isC && (
                  <div style={{ position: "absolute", right: -10, top: -18, padding: "6px 14px", borderRadius: 30, background: C.accent, color: "#fff", fontFamily: F.sans, fontWeight: 700, fontSize: 22, transform: `scale(${sp(flagAt, { damping: 9, stiffness: 240 })})` }}>
                    {data?.fichier ?? "1 fichier"}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {t >= scanAt && scanY < 1 && (
          <div style={{ position: "absolute", left: 0, right: 0, top: 120 + scanY * 700, height: 8, background: C.accent, boxShadow: `0 0 40px 12px rgba(47,91,234,0.35)` }} />
        )}
      </div>
      {partage && (
        <div style={{ position: "absolute", left: 1380, top: 370, width: 420, textAlign: "center", opacity: Math.min(1, sh * 1.5), transform: `translateX(${(1 - sh) * 80}px)` }}>
          <svg viewBox="0 0 120 40" width={240} height={80} style={{ display: "block", margin: "0 auto" }}>
            <path d={`M4 20 H${4 + 100 * sh}`} stroke={C.accent} strokeWidth={6} strokeLinecap="round" />
            {sh > 0.95 && <path d="M92 8 L108 20 L92 32" stroke={C.accent} strokeWidth={6} fill="none" strokeLinecap="round" strokeLinejoin="round" />}
          </svg>
          <div style={{ width: 150, height: 150, borderRadius: 150, background: C.contrast, margin: "20px auto 0", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg viewBox="0 0 24 24" width={90} height={90} fill="none" stroke={C.paperWarm} strokeWidth={1.6}>
              <circle cx="12" cy="8" r="3.6" />
              <path d="M4.5 20.5c.8-4.2 3.7-6.3 7.5-6.3s6.7 2.1 7.5 6.3" />
            </svg>
          </div>
          <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 38, color: C.contrast, marginTop: 20 }}>{data?.destinataire ?? "Another creator"}</div>
        </div>
      )}
      {partage && data?.tampon && (
        <div style={{ position: "absolute", right: 80, top: 760 }}>
          <StampMark at={tampAt} text={data.tampon} size={56} rotate={-7} />
        </div>
      )}
    </Paper>
  );
};

/* ================================================================== */
/* Search: a neutral search bar, the name is typed, results.          */
/* data: { texte, resultats: [{ titre, ligne }], tampon? }             */
/* cues: [typing, results, stamp]                                     */
export const Recherche: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const txt: string = data?.texte ?? "";
  const a0 = cue(cues, 0, 0.3);
  const n = Math.floor(interpolate(t, [a0, a0 + txt.length * 0.07], [0, txt.length], clamp));
  const ra = cue(cues, 1, a0 + txt.length * 0.07 + 0.4);
  const res: { titre: string; ligne: string }[] = data?.resultats ?? [];
  const s = sp(0.02, { damping: 15, stiffness: 150 });
  return (
    <Paper drift={1.5}>
      <AbsoluteFill style={{ alignItems: "center", paddingTop: 230 }}>
        <div style={{ width: 1300, height: 120, borderRadius: 70, background: "#FFFFFF", boxShadow: shadow, display: "flex", alignItems: "center", padding: "0 50px", gap: 30, transform: `scale(${0.9 + 0.1 * s})`, opacity: Math.min(1, s * 1.6) }}>
          <svg viewBox="0 0 24 24" width={54} height={54} fill="none" stroke={C.inkSoft} strokeWidth={2}>
            <circle cx="10.5" cy="10.5" r="6.5" />
            <path d="M15.5 15.5 L21 21" />
          </svg>
          <div style={{ fontFamily: F.sans, fontSize: 58, color: C.contrast }}>
            {txt.slice(0, n)}
            <span style={{ color: C.accent, opacity: n < txt.length || Math.floor(t * 2.2) % 2 === 0 ? 1 : 0 }}>|</span>
          </div>
        </div>
        <div style={{ height: 50 }} />
        {res.map((r, i) => {
          const at = ra + i * 0.25;
          const k = sp(at, { damping: 14, stiffness: 180 });
          return (
            <div key={i} style={{ width: 1300, padding: "22px 50px", boxSizing: "border-box", opacity: t >= at ? Math.min(1, k * 1.6) : 0, transform: `translateY(${(1 - k) * 30}px)` }}>
              <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 44, color: C.contrast }}>{nb(r.titre)}</div>
              <div style={{ fontFamily: F.sans, fontSize: 34, color: C.inkSoft, marginTop: 6 }}>{nb(r.ligne)}</div>
            </div>
          );
        })}
      </AbsoluteFill>
      {data?.tampon && (
        <div style={{ position: "absolute", left: 1250, top: 800 }}>
          <StampMark at={cue(cues, 2, 99)} text={data.tampon} size={60} rotate={-7} />
        </div>
      )}
    </Paper>
  );
};

/* ================================================================== */
/* Terminal: a command that types itself, its output, a highlighted line. */
/* data: { invite, commande, sortie: [string], surligne: [index] }     */
/* cues: [frappe, sortie, surlignage]                                  */
export const Terminal: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const cmd: string = data?.commande ?? "";
  const out: string[] = data?.sortie ?? [];
  const a0 = cue(cues, 0, 0.3);
  const n = Math.floor(interpolate(t, [a0, a0 + cmd.length * 0.05], [0, cmd.length], clamp));
  const oa = cue(cues, 1, a0 + cmd.length * 0.05 + 0.3);
  const ha = cue(cues, 2, 99);
  const surl: number[] = data?.surligne ?? [];
  const s = sp(0.02, { damping: 15, stiffness: 140 });
  return (
    <Paper drift={1}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ width: 1500, borderRadius: 22, overflow: "hidden", boxShadow: "0 40px 90px rgba(26,26,26,0.35)", transform: `translateY(${(1 - s) * 80}px)`, opacity: Math.min(1, s * 1.6) }}>
          <div style={{ height: 64, background: "#2A2A2A", display: "flex", alignItems: "center", gap: 14, padding: "0 26px" }}>
            {[0, 1, 2].map((i) => (
              <div key={i} style={{ width: 20, height: 20, borderRadius: 20, background: "#4A4A4A" }} />
            ))}
          </div>
          <div style={{ background: C.darkBg, padding: "40px 50px 50px", minHeight: 620, boxSizing: "border-box", fontFamily: F.mono, fontSize: 38, lineHeight: 1.45, color: C.paperWarm }}>
            <div>
              <span style={{ color: C.accent }}>{data?.invite ?? "$"} </span>
              {cmd.slice(0, n)}
              {t < oa && <span style={{ opacity: Math.floor(t * 2.4) % 2 === 0 ? 1 : 0 }}>▌</span>}
            </div>
            {out.map((l, i) => {
              const at = oa + i * 0.06;
              const hi = surl.includes(i) && t >= ha;
              const hk = hi ? ramp(t, ha, ha + 0.4, easeStd) : 0;
              return (
                <div key={i} style={{ whiteSpace: "pre", opacity: t >= at ? (surl.length && t >= ha && !hi ? 0.45 : 1) : 0, position: "relative" }}>
                  {hi && <div style={{ position: "absolute", left: -12, top: 2, height: "92%", width: `calc(${hk * 100}% + 24px)`, background: "rgba(47,91,234,0.32)", borderRadius: 6 }} />}
                  <span style={{ position: "relative" }}>{l || " "}</span>
                </div>
              );
            })}
          </div>
        </div>
      </AbsoluteFill>
    </Paper>
  );
};
