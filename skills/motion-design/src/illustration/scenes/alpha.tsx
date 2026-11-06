import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, F, Eyebrow, clamp, easeOut, ramp, rnd, shadow, useFadeOut, useSpringAt, useT } from "./kit";
import { SceneProps, StampMark, UrlPill } from "./opaque";
import { MxTampon } from "./matrix";

// Overlays (transparent background, track V6, ProRes 4444). The speaker is framed in the
// center: everything goes in the left or right third, never on the face.
// CRITICAL: no solid background here, or the transparency is lost.

const cue = (cues: number[], i: number, fallback: number) =>
  typeof cues?.[i] === "number" ? cues[i] : fallback;

const sideX = (side: string | undefined, w: number) => (side === "left" ? 90 : 1920 - 90 - w);

/* "FREE" stamp with a counter: the gag that grows over the video.
   data: { text, count, side, x, y, size, rotate }; cues: [impact] */
export const Stamp: React.FC<SceneProps> = ({ data, cues }) => {
  const fade = useFadeOut(8);
  const size = data?.size ?? 92;
  const y = data?.y ?? 170;
  // right side without x: anchored to the right, 90 px from the edge whatever the length of the word
  // (long words used to start at x = 1300 and run out of the frame)
  // cx: imposed center (zone_libre.py computes it so that the stamp, its drop and its ring
  // stay off the head)
  const pos: React.CSSProperties =
    data?.cx != null
      ? { left: data.cx, transform: "translateX(-50%)" }
      : data?.x != null ? { left: data.x } : data?.side === "left" ? { left: 170 } : { right: 90 };
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <div style={{ position: "absolute", top: y, ...pos }}>
        {data?.theme === "matrix" ? (
          // terminal-green style: the menu selection bar, no rotation, no drop
          <MxTampon at={cue(cues, 0, 0.05)} text={data?.text ?? ""} size={size} />
        ) : (
          <StampMark at={cue(cues, 0, 0.05)} text={data?.text ?? "Approved"} size={size} rotate={data?.rotate ?? -9} count={data?.count} depart={data?.depart} anneau={data?.anneau} />
        )}
      </div>
    </AbsoluteFill>
  );
};

/* Stamp rain: one burst per moment, around the frame, then the countdown.
   data: { text, startCount, perBurst, total }; cues: [burst 1, burst 2, …, countdown] */
export const StampRain: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const fade = useFadeOut(10);
  const bursts = (data?.bursts ?? cues.length - 1) as number;
  const per = data?.perBurst ?? 5;
  const totalAt = cues?.[bursts];
  // 20 slots off the center (the face): two columns on each side, five
  // rows, served in a shuffled but fixed order.
  const grid: { x: number; y: number }[] = [];
  for (let r = 0; r < 5; r++) for (const x of [40, 300, 1300, 1540]) grid.push({ x, y: 56 + r * 182 });
  const orderIdx = grid.map((_, i) => i).sort((i, j) => rnd(i + 51) - rnd(j + 51));
  const slots = Array.from({ length: Math.min(grid.length, bursts * per) }).map((_, i) => {
    const g = grid[orderIdx[i]];
    return { x: g.x + (rnd(i + 7) - 0.5) * 50, y: g.y + (rnd(i + 31) - 0.5) * 50 };
  });
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      {slots.map((s, i) => {
        const b = Math.floor(i / per);
        const at = cue(cues, b, 0.2 + b) + (i % per) * 0.07;
        return (
          <div key={i} style={{ position: "absolute", left: s.x, top: s.y }}>
            <StampMark at={at} text={data?.text ?? "Approved"} size={40 + rnd(i + 3) * 22} rotate={-14 + rnd(i + 11) * 28} />
          </div>
        );
      })}
      {typeof totalAt === "number" && t >= totalAt && (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 90,
            display: "flex",
            justifyContent: "center",
            transform: `scale(${sp(totalAt, { damping: 9, stiffness: 230 })})`,
          }}
        >
          <div
            style={{
              padding: "20px 44px",
              borderRadius: 60,
              background: C.contrast,
              color: C.paperWarm,
              fontFamily: F.sans,
              fontWeight: 700,
              fontSize: 50,
              boxShadow: shadow,
            }}
          >
            {data?.totalLabel ?? "Approved."}
          </div>
        </div>
      )}
    </AbsoluteFill>
  );
};

/* Words that slam in, one per moment, on paper labels.
   data: { lines: [{text, accent?}], side, y, size, right?, depart? }; cues: one per line
   depart: entry scale (2.2); the label grows toward the left, toward the face */
export const Slam: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const fade = useFadeOut(8);
  const lines: { text: string; accent?: boolean }[] = data?.lines ?? [];
  const size = data?.size ?? 92;
  const left = data?.side === "left";
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <div
        style={{
          position: "absolute",
          left: left ? 90 : undefined,
          right: left ? undefined : data?.right ?? 90,
          top: data?.y ?? 200,
          display: "flex",
          flexDirection: "column",
          alignItems: left ? "flex-start" : "flex-end",
          gap: size * 0.2,
        }}
      >
        {lines.map((l, i) => {
          const at = cue(cues, i, 0.1 + i * 0.7);
          if (t < at) return <div key={i} style={{ height: size * 1.5 }} />;
          const k = ramp(t, at, at + 0.13, easeOut);
          const settle = sp(at + 0.1, { damping: 8, stiffness: 300 });
          const shake = Math.sin((t - at) * 80) * 6 * Math.exp(-(t - at) * 12);
          return (
            <div
              key={i}
              style={{
                height: size * 1.5,
                display: "flex",
                alignItems: "center",
                transform: `translateX(${shake}px) rotate(${(i % 2 ? 1.6 : -1.8)}deg) scale(${interpolate(k, [0, 1], [Number(data?.depart ?? 2.2), 1]) * (0.97 + 0.03 * settle)})`,
                transformOrigin: left ? "0 50%" : "100% 50%",
                opacity: Math.min(1, k * 2),
              }}
            >
              <div
                style={{
                  padding: `${size * 0.1}px ${size * 0.36}px`,
                  background: l.accent ? C.accent : C.paperWarm,
                  color: l.accent ? "#fff" : C.contrast,
                  fontFamily: F.display,
                  fontStyle: "italic",
                  fontWeight: 500,
                  fontSize: size,
                  lineHeight: 1.15,
                  whiteSpace: "nowrap",
                  boxShadow: "0 14px 40px rgba(0,0,0,0.35)",
                }}
              >
                {l.text}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/* "Link in description": label + arrow pointing down.
   data: { side, right?, bottom?, size?, text?, eyebrow? } */
export const LienDescription: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const fade = useFadeOut(8);
  const at = cue(cues, 0, 0.05);
  const s = sp(at, { damping: 11, stiffness: 190 });
  const bob = Math.sin((t - at) * 6.5) * 12;
  const left = data?.side === "left";
  const neon = data?.theme === "neon"; // 80s art direction
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <div
        style={{
          position: "absolute",
          left: left ? 90 : undefined,
          right: left ? undefined : data?.right ?? 90,
          bottom: data?.bottom ?? 120,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          transform: `translateY(${(1 - s) * 120}px)`,
          opacity: Math.min(1, s * 1.6),
        }}
      >
        <div
          style={{
            padding: "22px 40px",
            borderRadius: 22,
            background: neon ? "#120D30" : C.paperWarm,
            boxShadow: neon ? "0 0 0 3px #5FF2FF, 0 0 26px rgba(95,242,255,0.55), 0 14px 40px rgba(0,0,0,0.35)" : "0 14px 40px rgba(0,0,0,0.35)",
            textAlign: "center",
          }}
        >
          {data?.eyebrow && <Eyebrow size={24} color={neon ? "#FF3DA8" : undefined}>{data.eyebrow}</Eyebrow>}
          <div style={{ fontFamily: neon ? "'Exo 2', sans-serif" : F.display, fontStyle: "italic", fontWeight: neon ? 700 : undefined, fontSize: data?.size ?? 58, color: neon ? "#F4F1FF" : C.contrast, lineHeight: 1.15, whiteSpace: "nowrap" }}>
            {data?.text ?? "Link in description"}
          </div>
        </div>
        <svg viewBox="0 0 60 80" width={72} height={96} style={{ marginTop: 10, transform: `translateY(${bob}px)` }}>
          <path d="M30 4 V66 M8 46 L30 70 L52 46" fill="none" stroke={neon ? "#FF3DA8" : C.accent} strokeWidth={9} strokeLinecap="round" strokeLinejoin="round"
            style={neon ? { filter: "drop-shadow(0 0 8px #FF3DA8)" } : undefined} />
        </svg>
      </div>
    </AbsoluteFill>
  );
};

/* Side list: kicker, title, items that drop in one by one.
   data: { eyebrow, title, items, side, y, width }; cues: [titre, item1, item2, …] */
export const SideList: React.FC<SceneProps> = ({ data, cues }) => {
  const sp = useSpringAt();
  const fade = useFadeOut(8);
  const w = data?.width ?? 520;
  const items: string[] = data?.items ?? [];
  const s = sp(cue(cues, 0, 0.05), { damping: 14, stiffness: 170 });
  const left = data?.side === "left";
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <div style={{ position: "absolute", left: sideX(data?.side, w), top: data?.y ?? 210, width: w }}>
        <div
          style={{
            background: C.paperWarm,
            borderLeft: `10px solid ${C.accent}`,
            padding: "26px 34px",
            boxShadow: "0 14px 40px rgba(0,0,0,0.35)",
            transform: `translateX(${(1 - s) * (left ? -160 : 160)}px)`,
            opacity: Math.min(1, s * 1.6),
          }}
        >
          {data?.eyebrow && <Eyebrow size={24}>{data.eyebrow}</Eyebrow>}
          {data?.title && (
            <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: data?.titleSize ?? 58, lineHeight: 1.1, color: C.contrast, marginTop: 6 }}>
              {data.title}
            </div>
          )}
        </div>
        <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 12, alignItems: left ? "flex-start" : "flex-end" }}>
          {items.map((it, i) => {
            const p = sp(cue(cues, 1 + i, 0.6 + i * 0.5), { damping: 11, stiffness: 210 });
            return (
              <div
                key={i}
                style={{
                  padding: "12px 28px",
                  borderRadius: 50,
                  background: C.contrast,
                  color: C.paperWarm,
                  fontFamily: F.sans,
                  fontWeight: 700,
                  fontSize: 38,
                  boxShadow: "0 10px 26px rgba(0,0,0,0.3)",
                  transform: `scale(${p})`,
                  transformOrigin: left ? "0 50%" : "100% 50%",
                  whiteSpace: "nowrap",
                }}
              >
                {it}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* Overlaid figure: counter in a paper label.
   data: { value, prefix, suffix, label, side, y, right?, size?, labelWidth? }; cues: [start] */
export const StatTag: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const fade = useFadeOut(8);
  const at = cue(cues, 0, 0.05);
  const s = sp(at, { damping: 12, stiffness: 180 });
  const k = ramp(t, at, at + 0.8, easeOut);
  const v = Math.round((data?.value ?? 0) * k).toLocaleString("fr-FR").replace(/\s/g, " ");
  const left = data?.side === "left";
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <div
        style={{
          position: "absolute",
          left: left ? 90 : undefined,
          right: left ? undefined : data?.right ?? 90,
          top: data?.y ?? 200,
          background: C.paperWarm,
          padding: "22px 44px 28px",
          boxShadow: "0 14px 40px rgba(0,0,0,0.35)",
          borderLeft: `10px solid ${C.accent}`,
          transform: `translateX(${(1 - s) * (left ? -200 : 200)}px) rotate(${left ? -1.5 : 1.5}deg)`,
          opacity: Math.min(1, s * 1.6),
        }}
      >
        {data?.prefix && <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 44, color: C.inkSoft }}>{data.prefix}</div>}
        <div style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
          <span style={{ fontFamily: F.display, fontWeight: 300, fontSize: data?.size ?? 190, lineHeight: 1, letterSpacing: "-0.03em", color: C.contrast, fontVariantNumeric: "tabular-nums" }}>{v}</span>
          {data?.suffix && <span style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 80, color: C.accent }}>{data.suffix}</span>}
        </div>
        {/* labelWidth: the caption wraps in a narrow column (right column
    of the Tella-style edit); without it, a single line as before */}
        <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: data?.labelSize ?? 38, color: C.contrast, ...(data?.labelWidth ? { maxWidth: data.labelWidth, textWrap: "balance" } : { whiteSpace: "nowrap" }) }}>{data?.label ?? ""}</div>
      </div>
    </AbsoluteFill>
  );
};

/* Messaging bubbles: they write, he replies, to everyone.
   data: { messages: [{from: "them"|"me", text}], side }; cues: one per bubble */
export const BulleDM: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const fade = useFadeOut(8);
  const msgs: { from: string; text: string }[] = data?.messages ?? [];
  const w = 540;
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      <div style={{ position: "absolute", left: sideX(data?.side, w), top: data?.y ?? 170, width: w, display: "flex", flexDirection: "column", gap: 16 }}>
        {msgs.map((m, i) => {
          const at = cue(cues, i, 0.2 + i * 0.8);
          const s = sp(at, { damping: 12, stiffness: 210 });
          const me = m.from === "me";
          const typing = me && t >= at && t < at + 0.55;
          return (
            <div
              key={i}
              style={{
                alignSelf: me ? "flex-end" : "flex-start",
                maxWidth: 470,
                padding: "18px 28px",
                borderRadius: 34,
                borderBottomRightRadius: me ? 8 : 34,
                borderBottomLeftRadius: me ? 34 : 8,
                background: me ? C.accent : C.paperWarm,
                color: me ? "#fff" : C.contrast,
                fontFamily: F.sans,
                fontSize: 36,
                lineHeight: 1.22,
                boxShadow: "0 12px 30px rgba(0,0,0,0.32)",
                transform: `scale(${s})`,
                transformOrigin: me ? "100% 100%" : "0 100%",
              }}
            >
              {typing ? (
                <span style={{ letterSpacing: 6, fontWeight: 700 }}>{"•".repeat(1 + (Math.floor((t - at) * 9) % 3))}</span>
              ) : (
                m.text
              )}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/* Site address at the bottom of the frame, typed letter by letter. */
export const UrlBar: React.FC<SceneProps> = ({ data, cues }) => {
  const fade = useFadeOut(8);
  return (
    <AbsoluteFill style={{ opacity: fade, alignItems: "center", justifyContent: "flex-end", paddingBottom: data?.bottom ?? 96 }}>
      <UrlPill at={cue(cues, 0, 0.05)} size={data?.size ?? 56} url={data?.url} />
    </AbsoluteFill>
  );
};

/* Wipe: a curtain crosses the frame and hides the cut (talking-head <-> scene).
   15 frames: it covers the whole frame from frame 6 to frame 8, the cut sits on 7.
   data: { color, dir: 1 (left to right) | -1 } */
export const Volet: React.FC<SceneProps> = ({ data }) => {
  const f = useCurrentFrame();
  const { durationInFrames: n, width, height } = useVideoConfig();
  const mid = (n - 1) / 2;
  const ease = Easing.bezier(0.65, 0, 0.35, 1);
  const inK = interpolate(f, [0, mid - 1], [0, 1], { ...clamp, easing: ease });
  const outK = interpolate(f, [mid + 1, n - 1], [0, 1], { ...clamp, easing: ease });
  const dir = data?.dir === -1 ? -1 : 1;
  const x0 = outK * width, x1 = inK * width;
  const band = 26;
  const flip: React.CSSProperties = dir === -1 ? { transform: "scaleX(-1)" } : {};
  return (
    <AbsoluteFill style={flip}>
      <div style={{ position: "absolute", left: x0, top: 0, width: Math.max(0, x1 - x0), height, background: data?.color ?? C.contrast }} />
      {inK < 1 && inK > 0 && <div style={{ position: "absolute", left: x1 - band / 2, top: 0, width: band, height, background: C.accent }} />}
      {outK > 0 && outK < 1 && <div style={{ position: "absolute", left: x0 - band / 2, top: 0, width: band, height, background: C.accent }} />}
    </AbsoluteFill>
  );
};
