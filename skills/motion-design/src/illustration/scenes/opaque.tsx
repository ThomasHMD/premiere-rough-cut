import React from "react";
import { AbsoluteFill, Easing, Img, OffthreadVideo, interpolate, staticFile, useVideoConfig } from "remotion";
import {
  BoxBrackets,
  Brackets,
  C,
  Check,
  Draw,
  Eyebrow,
  F,
  Icon,
  Paper,
  Rise,
  clamp,
  easeOut,
  easeStd,
  fr,
  nb,
  ramp,
  rnd,
  shadow,
  useSpringAt,
  useT,
} from "./kit";

// Full-screen scenes (opaque, track V5). Each scene receives `data` (content) and
// `cues` (moments in seconds from the start of the scene, computed on the words
// of the transcript): nothing moves "roughly", everything lands on the voice.

export type SceneProps = { data: any; cues: number[] };

const cue = (cues: number[], i: number, fallback: number) =>
  typeof cues?.[i] === "number" ? cues[i] : fallback;

// Address shown in the footer of the light scenes: yours, or "" for none.
const SITE = "";

/* Scene footer: the site address, on the left (nothing if SITE is empty). No logo in a
   scene: it loads the image for nothing, the talking-head is enough to sign the video. */
export const Footer: React.FC<{ dark?: boolean; url?: boolean }> = ({ dark, url = true }) =>
  url && SITE ? (
    <div
      style={{
        position: "absolute",
        left: 120,
        bottom: 56,
        fontFamily: F.sans,
        fontSize: 24,
        letterSpacing: "0.04em",
        color: dark ? "rgba(242,242,242,0.55)" : C.muted,
      }}
    >
      {SITE}
    </div>
  ) : null;

export const Title: React.FC<{ at?: number; size?: number; children: React.ReactNode; color?: string; style?: React.CSSProperties }> = ({
  at = 0.05,
  size = 84,
  children,
  color = C.contrast,
  style,
}) => (
  <Rise at={at} dur={0.55}>
    <div
      style={{
        fontFamily: F.display,
        fontStyle: "italic",
        fontWeight: 400,
        fontSize: size,
        lineHeight: 1.06,
        letterSpacing: "-0.015em",
        color,
        ...style,
      }}
    >
      {children}
    </div>
  </Rise>
);

export const Card: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div style={{ background: "#FFFFFF", borderRadius: 18, boxShadow: shadow, ...style }}>{children}</div>
);

export const Pill: React.FC<{ at: number; children: React.ReactNode; check?: boolean; style?: React.CSSProperties }> = ({
  at,
  children,
  check = true,
  style,
}) => {
  const sp = useSpringAt();
  const s = sp(at, { damping: 12, stiffness: 190 });
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 18,
        padding: "16px 34px 16px 18px",
        borderRadius: 60,
        background: C.contrast,
        color: C.paperWarm,
        fontFamily: F.sans,
        fontWeight: 700,
        fontSize: 36,
        transform: `translateY(${(1 - s) * 40}px) scale(${0.85 + 0.15 * s})`,
        opacity: Math.min(1, s * 1.6),
        ...style,
      }}
    >
      {check && <Check at={at + 0.06} size={46} />}
      {children}
    </div>
  );
};

/* Address bar: the URL is typed letter by letter (`url`: the default site). */
export const UrlPill: React.FC<{ at: number; size?: number; dark?: boolean; typed?: boolean; url?: string }> = ({
  at,
  size = 44,
  dark = false,
  typed = true,
  url = SITE,
}) => {
  const t = useT();
  const sp = useSpringAt();
  const s = sp(at, { damping: 15, stiffness: 170 });
  const n = typed ? Math.floor(interpolate(t, [at + 0.12, at + 0.12 + url.length * 0.035], [0, url.length], clamp)) : url.length;
  const blink = Math.floor(t * 2.2) % 2 === 0;
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: size * 0.4,
        padding: `${size * 0.36}px ${size * 0.8}px`,
        borderRadius: size * 1.2,
        background: dark ? C.contrast : "#FFFFFF",
        boxShadow: shadow,
        fontFamily: F.sans,
        fontWeight: 700,
        fontSize: size,
        color: dark ? C.paperWarm : C.contrast,
        transform: `scale(${0.8 + 0.2 * s})`,
        opacity: Math.min(1, s * 1.5),
        whiteSpace: "nowrap",
      }}
    >
      <div style={{ width: size * 0.42, height: size * 0.42, borderRadius: size, background: C.accent }} />
      <span style={{ display: "inline-block", minWidth: size * 0.58 * url.length, textAlign: "left" }}>
        {url.slice(0, n)}
        <span style={{ opacity: n < url.length || blink ? 1 : 0, color: C.accent, fontWeight: 400 }}>|</span>
      </span>
    </div>
  );
};

/* ================================================================== */
/* Stamp (also used as an overlay, see alpha.tsx)                    */
/** The scale the stamp drops from (in 0.14 s, down to 1): its maximum size. `depart` caps it when the stamp must fit in a narrow zone. */
export const ECHELLE_CHUTE_TAMPON = 2.6;
/** `text` can span several lines (\n), centered. `anneau`: how much the ring widens (0.35 = +35%);
 *  as an overlay next to the face, 0.15 (zone_libre.py of overlays accounts for its box). */
export const StampMark: React.FC<{ at: number; text: string; size?: number; rotate?: number; count?: number; color?: string; depart?: number; anneau?: number; da?: Record<string, string | number | undefined> }> = ({
  at,
  text,
  size = 96,
  rotate = -9,
  count,
  color = C.accent,
  depart = ECHELLE_CHUTE_TAMPON,
  anneau = 0.35,
  da,
}) => {
  const t = useT();
  const sp = useSpringAt();
  if (t < at) return null;
  const k = ramp(t, at, at + 0.14, easeOut);
  const scale = interpolate(k, [0, 1], [depart, 1]);
  const settle = sp(at + 0.12, { damping: 8, stiffness: 300 });
  const shake = Math.sin((t - at) * 90) * 5 * Math.exp(-(t - at) * 14);
  const ring = ramp(t, at + 0.1, at + 0.55, easeOut);
  const cs = typeof count === "number" ? sp(at + 0.22, { damping: 9, stiffness: 260 }) : 0;
  return (
    <div style={{ position: "relative", display: "inline-block", transform: `rotate(${rotate}deg) translateX(${shake}px)` }}>
      {/* the ring is only rendered while it lives (0.45 s), in a `contain: layout` wrapper: at scale 1.35 it
          would stick out of the stamp's box and count in the `scrollWidth` of the ancestors (overflow measurement of a
          scene) although it is almost transparent. Same box, same pixels (tested in Remotion's Chrome). */}
      {ring < 1 && (
        <div style={{ position: "absolute", inset: 0, contain: "layout", pointerEvents: "none" }}>
          <div
            style={{
              position: "absolute",
              inset: -size * 0.3,
              borderRadius: size * 0.5,
              border: `${size * 0.05}px solid ${color}`,
              opacity: (1 - ring) * 0.55,
              transform: `scale(${1 + ring * anneau})`,
            }}
          />
        </div>
      )}
      <div
        {...da}
        style={{
          padding: `${size * 0.16}px ${size * 0.46}px`,
          border: `${size * 0.1}px solid ${color}`,
          borderRadius: size * 0.2,
          color,
          fontFamily: F.sans,
          fontWeight: 700,
          fontSize: size,
          letterSpacing: "0.08em",
          lineHeight: 1,
          textTransform: "uppercase",
          whiteSpace: text.includes("\n") ? "pre" : "nowrap",
          textAlign: "center",
          transform: `scale(${scale * (0.96 + 0.04 * settle)})`,
          opacity: Math.min(1, k * 2),
          background: "rgba(242,242,242,0.88)",
          boxShadow: "0 10px 30px rgba(26,26,26,0.22)",
        }}
      >
        {text}
      </div>
      {typeof count === "number" && (
        <div
          style={{
            position: "absolute",
            right: -size * 0.42,
            top: -size * 0.42,
            minWidth: size * 0.95,
            height: size * 0.95,
            padding: `0 ${size * 0.14}px`,
            boxSizing: "border-box",
            borderRadius: size,
            background: C.contrast,
            color: C.paperWarm,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: F.sans,
            fontWeight: 700,
            fontSize: size * 0.46,
            transform: `scale(${cs}) rotate(${-rotate}deg)`,
          }}
        >
          {`×${count}`}
        </div>
      )}
    </div>
  );
};

/* ================================================================== */
/* 5. Part card: "Part 3 of 5", giant number, name, bar               */
/* data: { n, total, name, eyebrow?, icon?, sub?, label?, size? }       */
export const ChapterCard: React.FC<SceneProps> = ({ data }) => {
  const t = useT();
  const sp = useSpringAt();
  const n: number = data?.n ?? 1;
  const total: number = data?.total ?? 5;
  const label: string = data?.label ?? "Part";
  const s = sp(0.02, { damping: 14, stiffness: 150 });
  return (
    <Paper drift={2}>
      <AbsoluteFill style={{ padding: "0 120px", flexDirection: "row", alignItems: "center" }}>
        <div style={{ width: 640, overflow: "hidden", height: 520 }}>
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
            <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
              {data?.icon && <Icon name={data.icon} size={56} color={C.accent} stroke={1.9} />}
              {data?.eyebrow && <Eyebrow size={32}>{data.eyebrow}</Eyebrow>}
            </div>
          </Rise>
          <div style={{ height: 22 }} />
          <Title at={0.16} size={data?.size ?? 132}>
            {data?.name ?? ""}
          </Title>
          {data?.sub && (
            <>
              <div style={{ height: 22 }} />
              <Rise at={0.32}>
                <div style={{ fontFamily: F.sans, fontSize: 42, color: C.inkSoft, lineHeight: 1.25 }}>{data.sub}</div>
              </Rise>
            </>
          )}
        </div>
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 120, right: 120, bottom: 110, display: "flex", gap: 12, alignItems: "center" }}>
        {Array.from({ length: total }).map((_, i) => {
          const on = i < n;
          const kk = ramp(t, 0.25 + i * 0.04, 0.5 + i * 0.04, easeStd);
          return (
            <div key={i} style={{ flex: 1, height: 10, borderRadius: 6, background: "rgba(26,26,26,0.14)", overflow: "hidden" }}>
              <div style={{ width: `${on ? kk * 100 : 0}%`, height: "100%", background: i === n - 1 ? C.accent : C.contrast }} />
            </div>
          );
        })}
        <div style={{ marginLeft: 20, fontFamily: F.sans, fontWeight: 700, fontSize: 28, letterSpacing: "0.08em", color: C.contrast, whiteSpace: "nowrap" }}>
          {`${label.toUpperCase()} ${n} / ${total}`}
        </div>
      </div>
    </Paper>
  );
};

/* ================================================================== */
/* 6. Question card (dark background: pacing break)                    */
export const QuestionCard: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const words: string[] = String(data?.question ?? "And now?").split(" ");
  const step = data?.step ?? 0.13;
  const lockAt = cue(cues, 0, 0.25 + words.length * step);
  return (
    <Paper dark drift={2.5}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <Rise at={0.02}>
          <Eyebrow size={32}>{data?.eyebrow ?? ""}</Eyebrow>
        </Rise>
        <div style={{ height: 34 }} />
        <div style={{ display: "flex", gap: 44, flexWrap: "wrap", justifyContent: "center", maxWidth: 1600 }}>
          {words.map((w, i) => (
            <Rise key={i} at={0.12 + i * step} dur={0.42}>
              <span
                style={{
                  fontFamily: F.display,
                  fontStyle: "italic",
                  fontWeight: 400,
                  fontSize: data?.size ?? 190,
                  lineHeight: 1.08,
                  letterSpacing: "-0.02em",
                  color: w === "?" ? C.accent : C.paperWarm,
                }}
              >
                {w}
              </span>
            </Rise>
          ))}
        </div>
        {data?.sub && (
          <>
            <div style={{ height: 40 }} />
            <Rise at={lockAt}>
              <div style={{ fontFamily: F.sans, fontSize: 42, color: "rgba(242,242,242,0.72)" }}>{data.sub}</div>
            </Rise>
          </>
        )}
      </AbsoluteFill>
      <Brackets x={170} y={250} w={1580} h={580} at={lockAt} arm={54} stroke={6} />
      <div style={{ opacity: ramp(t, 0.2, 0.6) }}>
        <Footer dark url={false} />
      </div>
    </Paper>
  );
};

/* ================================================================== */
/* 7. Chiffre fort                                                      */
/* cues: [counter start, then one moment per note]                    */
export const Stat: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const c0 = cue(cues, 0, 0.15);
  const dur = data?.countDur ?? 0.9;
  const value: number = data?.value ?? 8000;
  const from: number = data?.from ?? 0;
  const k = ramp(t, c0, c0 + dur, easeOut);
  const v = from + (value - from) * k;
  const done = useSpringAt()(c0 + dur, { damping: 8, stiffness: 260 });
  const notes: string[] = data?.notes ?? [];
  return (
    <Paper drift={2}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <Rise at={0.03}>
          <Eyebrow size={32}>{data?.eyebrow ?? ""}</Eyebrow>
        </Rise>
        {/* 40 and not 8: the box of the digit in Source Serif 430 sticks out 41 px above its line and covered the kicker (controle-texte) */}
        <div style={{ height: 40 }} />
        <div style={{ display: "flex", alignItems: "baseline", gap: 30 }}>
          {data?.prefix && (
            <Rise at={0.05}>
              <span style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 92, color: C.inkSoft }}>{data.prefix}</span>
            </Rise>
          )}
          <span
            style={{
              fontFamily: F.display,
              fontWeight: 300,
              fontSize: data?.size ?? 430,
              lineHeight: 1.05,
              letterSpacing: "-0.04em",
              color: C.contrast,
              fontVariantNumeric: "tabular-nums",
              transform: `scale(${1 + 0.05 * (1 - done) * (k >= 1 ? 1 : 0)})`,
              opacity: ramp(t, c0 - 0.1, c0 + 0.1),
            }}
          >
            {fr(v)}
          </span>
          {data?.suffix && (
            <span style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 150, color: C.accent, opacity: ramp(t, c0, c0 + 0.3) }}>
              {data.suffix}
            </span>
          )}
        </div>
        <div style={{ position: "relative", width: 900, height: 30 }}>
          <Draw d="M10 16 C 220 2, 520 30, 890 10" at={c0 + dur - 0.1} dur={0.45} length={900} viewBox="0 0 900 30" width={7} style={{ left: 0, top: 0, width: 900, height: 30 }} />
        </div>
        <div style={{ height: 22 }} />
        <Rise at={c0 + 0.2}>
          <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 58, color: C.contrast }}>{data?.label ?? ""}</div>
        </Rise>
        <div style={{ height: 34 }} />
        <div style={{ display: "flex", gap: 24, minHeight: 80 }}>
          {notes.map((n, i) => (
            <Pill key={i} at={cue(cues, 1 + i, c0 + dur + 0.4 + i * 0.6)} check={data?.check !== false}>
              {n}
            </Pill>
          ))}
        </div>
      </AbsoluteFill>
      {/* data.site === false: no site address (videos unrelated to the apps) */}
      <Footer url={data?.site !== false} />
    </Paper>
  );
};

/* ================================================================== */
/* 8. Phone demo (screenshot in a mockup)                             */
/* cues: one moment per step                                          */
export const PhoneDemo: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const { durationInFrames, fps } = useVideoConfig();
  const steps: string[] = data?.steps ?? [];
  const s = sp(0.05, { damping: 14, stiffness: 120 });
  const W = 384, H = 832;
  const float = Math.sin(t * 0.9) * 8;
  const tilt = -4 + 1.5 * Math.sin(t * 0.5);
  const active = steps.reduce((acc, _, i) => (t >= cue(cues, i, 1 + i * 3) ? i : acc), -1);
  return (
    <Paper>
      <AbsoluteFill style={{ flexDirection: "row", alignItems: "center", padding: "0 120px" }}>
        <div style={{ width: 640, display: "flex", justifyContent: "center" }}>
          <div
            style={{
              width: W,
              height: H,
              borderRadius: 58,
              background: C.contrast,
              padding: 13,
              boxSizing: "content-box",
              boxShadow: "0 50px 90px rgba(26,26,26,0.30), 0 8px 18px rgba(26,26,26,0.18)",
              transform: `translateY(${(1 - s) * 500 + float}px) rotate(${tilt}deg)`,
            }}
          >
            <div style={{ width: W, height: H, borderRadius: 46, overflow: "hidden", background: "#000" }}>
              {data?.video && (
                <OffthreadVideo
                  src={staticFile(data.video)}
                  muted
                  style={{ width: W, height: H, objectFit: "cover" }}
                  endAt={Math.round((data?.videoDur ?? durationInFrames / fps) * fps)}
                />
              )}
            </div>
          </div>
        </div>
        <div style={{ flex: 1, paddingLeft: 60 }}>
          <Rise at={0.1}>
            <Eyebrow>{data?.eyebrow ?? ""}</Eyebrow>
          </Rise>
          <div style={{ height: 16 }} />
          <Title at={0.15} size={92}>
            {data?.title ?? ""}
          </Title>
          <div style={{ height: 50 }} />
          {steps.map((st, i) => {
            const at = cue(cues, i, 1 + i * 3);
            const a = sp(at, { damping: 13, stiffness: 180 });
            const on = i === active;
            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 28,
                  marginBottom: 30,
                  transform: `translateX(${(1 - a) * 80}px)`,
                  opacity: Math.min(1, a * 1.6) * (on || active < 0 ? 1 : 0.42),
                }}
              >
                <div
                  style={{
                    width: 72,
                    height: 72,
                    borderRadius: 72,
                    background: on ? C.accent : C.contrast,
                    color: "#fff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: F.sans,
                    fontWeight: 700,
                    fontSize: 36,
                    flexShrink: 0,
                  }}
                >
                  {i + 1}
                </div>
                <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 48, lineHeight: 1.15, color: C.contrast }}>{st}</div>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
      <Footer url={false} />
    </Paper>
  );
};
