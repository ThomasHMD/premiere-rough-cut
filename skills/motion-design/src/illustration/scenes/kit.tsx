import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Easing,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { theme } from "../theme";

// Scene toolbox (animated graphics aligned to the voice).
// Everything derives from useCurrentFrame: no Math.random, no CSS animation.

export const C = theme.color;
export const F = theme.font;
export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const easeOut = Easing.bezier(0.0, 0.0, 0.2, 1);
export const easeStd = Easing.bezier(0.2, 0.0, 0, 1);

/** Current time in seconds. */
export const useT = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return f / fps;
};

/** 0 → 1 between a and b seconds, design system curve. */
export const ramp = (t: number, a: number, b: number, ease = easeOut) =>
  interpolate(t, [a, b], [0, 1], { ...clamp, easing: ease });

/** Spring that starts at `at` seconds (0 before). */
export const useSpringAt = () => {
  const { fps } = useVideoConfig();
  const t = useT();
  return (at: number, cfg: { damping?: number; stiffness?: number; mass?: number } = {}) =>
    t < at
      ? 0
      : spring({
          frame: Math.round((t - at) * fps),
          fps,
          config: { damping: 14, stiffness: 160, mass: 0.7, ...cfg },
        });
};

/** Fade-out over the last frames of a transparent overlay. */
export const useFadeOut = (frames = 9) => {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return interpolate(f, [durationInFrames - frames, durationInFrames - 1], [1, 0], clamp);
};

/** Deterministic pseudo-random (0..1) for scatterings. */
export const rnd = (seed: number) => {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};

/** Units that stick to the number before them ("2 m", "30 cm", "150 €", "80 %", "20 °C", "12 Mo", "3 ans"). Only after a digit, and   // fr-ok
 *  only the whole unit: in "3 mois", the "m" does not count as a meter, nor "s" in "3 sur 5" or "2 s'ensuit". */   // fr-ok
const UNITE = "(?:%|‰|€|\\$|£|°[CF]?|[kKMGT]o|(?:[kdcm]|µ|n)?m[²³]?|k?g|mg|[cdm]?l|k?Hz|MHz|GHz|k?Wh?|mAh|ms|min|px|dpi|ppp|s|h|ans?|mois|jours?|heures?|minutes?|secondes?|euros?)";   // fr-ok
const APRES_NOMBRE = new RegExp(`(\\d) (?=${UNITE}(?![\\p{L}\\d'’]))`, "gu");

/** French typography: non-breaking space before ? ! : ; » and after «, around ×, between a number and its unit ("2 m", "150 €", "80 %"), in a   // fr-ok
 *  number with thousands ("1 500", narrow non-breaking space like `fr`). Only touches spaces already there, never adds any. */
export const nb = (s: string) =>
  String(s ?? "")
    .replace(/ ([?!:;»])/g, "\u00a0$1")   // fr-ok
    .replace(/« /g, "«\u00a0")   // fr-ok
    .replace(/ ×/g, "\u00a0×")
    .replace(/× /g, "×\u00a0")
    .replace(/(?<=\d) (?=\d{3}(?!\d))/g, "\u00a0")
    .replace(APRES_NOMBRE, "$1\u00a0");

/** French-style thousands separator (narrow non-breaking space). */
export const fr = (n: number) => Math.round(n).toLocaleString("fr-FR").replace(/ | | /g, " ");

export const FONTS = [
  { name: "Source Serif", file: "SourceSerif4-Italic.woff2", style: "italic", weight: "100 900" },
  { name: "Source Serif", file: "SourceSerif4-Roman.woff2", style: "normal", weight: "100 900" },
  { name: "Inter", file: "Inter-Regular.woff2", style: "normal", weight: "400" },
  { name: "Inter", file: "Inter-Bold.woff2", style: "normal", weight: "700" },
  { name: "Inter", file: "Inter-Italic.woff2", style: "italic", weight: "400" },
  { name: "Inter", file: "Inter-BoldItalic.woff2", style: "italic", weight: "700" },
  // the neon art direction, reused by the retro scenes of a video
  { name: "Exo 2", file: "neon/Exo2-Roman.woff2", style: "normal", weight: "100 900" },
  { name: "Exo 2", file: "neon/Exo2-Italic.woff2", style: "italic", weight: "100 900" },
  { name: "Barlow", file: "neon/Barlow-Regular.woff2", style: "normal", weight: "400" },
  { name: "Barlow", file: "neon/Barlow-Bold.woff2", style: "normal", weight: "700" },
  { name: "Barlow", file: "neon/Barlow-Italic.woff2", style: "italic", weight: "400" },
  { name: "Barlow", file: "neon/Barlow-BoldItalic.woff2", style: "italic", weight: "700" },
];

// The "green Matrix terminal" art direction, apart from FONTS: the brand sheets read FONTS (paper) and their
// glyph check must not count fonts they do not display. JetBrains Mono variable (latin + greek for the Δ of ΔE), VT323.
export const FONTS_MATRIX: { name: string; file: string; style: string; weight: string; unicodeRange?: string }[] = [
  { name: "JetBrains Mono", file: "matrix/JetBrainsMono-latin.woff2", style: "normal", weight: "100 800",
    unicodeRange: "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD" },
  { name: "JetBrains Mono", file: "matrix/JetBrainsMono-greek.woff2", style: "normal", weight: "100 800",
    unicodeRange: "U+0370-0377, U+037A-037F, U+0384-038A, U+038C, U+038E-03A1, U+03A3-03FF" },
  { name: "VT323", file: "matrix/VT323-latin.woff2", style: "normal", weight: "400" },
];

export const useDsFonts = () => {
  const [handle] = useState(() => delayRender("Design system fonts"));
  useEffect(() => {
    Promise.all(
      [...FONTS, ...FONTS_MATRIX].map(async (f: { name: string; file: string; style: string; weight: string; unicodeRange?: string }) => {
        const face = new FontFace(f.name, `url(${staticFile(`fonts/${f.file}`)}) format("woff2")`, {
          style: f.style,
          weight: f.weight,
          ...(f.unicodeRange ? { unicodeRange: f.unicodeRange } : {}),
        });
        (document.fonts as unknown as Set<FontFace>).add(await face.load());
      }),
    )
      .catch((e) => console.error("Fonts", e))
      .finally(() => continueRender(handle));
  }, [handle]);
};

/* ------------------------------------------------------------------ */
/* Light grain: paper texture */
export const Grain: React.FC<{ opacity?: number }> = ({ opacity = 0.07 }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill style={{ opacity, mixBlendMode: "multiply", pointerEvents: "none" }}>
      <svg width={width} height={height}>
        <filter id={`g${frame}`}>
          <feTurbulence type="fractalNoise" baseFrequency={0.85} numOctaves={2} seed={frame % 61} />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter={`url(#g${frame})`} />
      </svg>
    </AbsoluteFill>
  );
};

/* Paper background of the full-screen scenes, with a very light camera movement. */
export const Paper: React.FC<{ children: React.ReactNode; dark?: boolean; drift?: number }> = ({
  children,
  dark = false,
  drift = 1,
}) => {
  const t = useT();
  const { durationInFrames, fps } = useVideoConfig();
  const total = durationInFrames / fps;
  const s = 1 + 0.018 * drift * (t / Math.max(total, 1));
  return (
    <AbsoluteFill style={{ background: dark ? C.darkBg : C.paperWarm, overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${s})`, transformOrigin: "50% 55%" }}>{children}</AbsoluteFill>
      <Grain opacity={dark ? 0.12 : 0.07} />
    </AbsoluteFill>
  );
};

/* Accent kicker in spaced capitals. */
export const Eyebrow: React.FC<{ children: React.ReactNode; size?: number; color?: string; style?: React.CSSProperties }> = ({
  children,
  size = 30,
  color = C.accent,
  style,
}) => (
  <div
    style={{
      fontFamily: F.sans,
      fontWeight: 700,
      fontSize: size,
      letterSpacing: "0.14em",
      textTransform: "uppercase",
      color,
      // on two lines, equal lines: "… ÇA SE / VOIT ?" left a single word alone   // fr-ok
      textWrap: "balance",
      ...style,
    }}
  >
    {children}
  </div>
);

/* Text that rises behind a mask (line-by-line reveal). */
export const Rise: React.FC<{
  at: number;
  dur?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
  distance?: number;
}> = ({ at, dur = 0.5, children, style, distance = 110 }) => {
  const t = useT();
  const k = ramp(t, at, at + dur, easeStd);
  return (
    <div style={{ overflow: "hidden", paddingBottom: "0.14em", marginBottom: "-0.14em", ...style }}>
      <div style={{ transform: `translateY(${(1 - k) * distance}%)`, opacity: k > 0 ? 1 : 0 }}>{children}</div>
    </div>
  );
};

/* Stroke that draws itself (underline, arrow, circle). */
export const Draw: React.FC<{
  d: string;
  at: number;
  dur?: number;
  width?: number;
  color?: string;
  length: number;
  viewBox: string;
  style?: React.CSSProperties;
}> = ({ d, at, dur = 0.5, width = 6, color = C.accent, length, viewBox, style }) => {
  const t = useT();
  const k = ramp(t, at, at + dur, easeStd);
  return (
    <svg viewBox={viewBox} style={{ position: "absolute", overflow: "visible", ...style }}>
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={width}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={length}
        strokeDashoffset={(1 - k) * length}
        opacity={k > 0 ? 1 : 0}
      />
    </svg>
  );
};

/* Autofocus brackets that lock onto a frame (the channel's signature). */
export const Brackets: React.FC<{
  x: number;
  y: number;
  w: number;
  h: number;
  at: number;
  color?: string;
  arm?: number;
  stroke?: number;
}> = ({ x, y, w, h, at, color = C.accent, arm = 38, stroke = 5 }) => {
  const sp = useSpringAt();
  const t = useT();
  if (t < at) return null;
  const s = sp(at, { damping: 13, stiffness: 140 });
  const spread = (1 - s) * 70;
  const x0 = x - spread, y0 = y - spread, x1 = x + w + spread, y1 = y + h + spread;
  const d = [
    `M${x0},${y0 + arm} L${x0},${y0} L${x0 + arm},${y0}`,
    `M${x1 - arm},${y0} L${x1},${y0} L${x1},${y0 + arm}`,
    `M${x1},${y1 - arm} L${x1},${y1} L${x1 - arm},${y1}`,
    `M${x0 + arm},${y1} L${x0},${y1} L${x0},${y1 - arm}`,
  ].join(" ");
  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity: ramp(t, at, at + 0.12) }}>
      <svg width="100%" height="100%">
        <path d={d} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="square" />
      </svg>
    </AbsoluteFill>
  );
};

/* Brackets placed around the parent block (which must be position: relative). */
export const BoxBrackets: React.FC<{ at: number; pad?: number; arm?: number; stroke?: number; color?: string }> = ({
  at,
  pad = 26,
  arm = 40,
  stroke = 5,
  color = C.accent,
}) => {
  const sp = useSpringAt();
  const t = useT();
  if (t < at) return null;
  const s = sp(at, { damping: 13, stiffness: 140 });
  const d = -(pad + (1 - s) * 70);
  const b = `${stroke}px solid ${color}`;
  const base: React.CSSProperties = { position: "absolute", width: arm, height: arm, opacity: ramp(t, at, at + 0.12), pointerEvents: "none" };
  return (
    <>
      <div style={{ ...base, left: d, top: d, borderLeft: b, borderTop: b }} />
      <div style={{ ...base, right: d, top: d, borderRight: b, borderTop: b }} />
      <div style={{ ...base, right: d, bottom: d, borderRight: b, borderBottom: b }} />
      <div style={{ ...base, left: d, bottom: d, borderLeft: b, borderBottom: b }} />
    </>
  );
};

/* Checkmark drawn in an accent circle. */
export const Check: React.FC<{ at: number; size?: number }> = ({ at, size = 64 }) => {
  const sp = useSpringAt();
  const t = useT();
  const s = sp(at, { damping: 10, stiffness: 220 });
  const k = ramp(t, at + 0.08, at + 0.36, easeStd);
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: size,
        background: C.accent,
        transform: `scale(${s})`,
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <svg viewBox="0 0 24 24" width={size * 0.62} height={size * 0.62}>
        <path
          d="M4.5 12.5 L10 18 L19.5 7"
          fill="none"
          stroke="#fff"
          strokeWidth={3.2}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={24}
          strokeDashoffset={(1 - k) * 24}
        />
      </svg>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Line pictograms (data.icon of the scenes): tag, barcode, books, house, spark, person, pin, news, calendar, heart… */
const ICONS: Record<string, React.ReactNode> = {
  tag: (
    <>
      <path d="M3 12.5V4h8.5l9.5 9.5-8.5 8.5L3 12.5z" />
      <circle cx="7.6" cy="8.6" r="1.4" />
    </>
  ),
  barcode: <path d="M4 5v14M7 5v14M10 5v10M13 5v14M16 5v10M19 5v14M9.5 18.5h7" />,
  books: <path d="M4 20V5h4v15M8 20V8h4v12M13.2 20l-2-13.5 3.8-.6 2.2 14.1M3 20h18" />,
  house: <path d="M3 20h18M5 20V9l7-5 7 5v11M9.5 20v-5.5h5V20M9 10.5h6" />,
  spark: <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.8 5.8l2.7 2.7M15.5 15.5l2.7 2.7M18.2 5.8l-2.7 2.7M8.5 15.5l-2.7 2.7" />,
  person: (
    <>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M4.5 20.5c.8-4.2 3.7-6.3 7.5-6.3s6.7 2.1 7.5 6.3" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21.5s7-6.4 7-11.8A7 7 0 0 0 5 9.7c0 5.400 7 11.800 7 11.800z" />
      <circle cx="12" cy="9.700" r="2.500" />
    </>
  ),
  news: <path d="M4 5h13v15H6a2 2 0 0 1-2-2V5zM17 9h3v9a2 2 0 0 1-2 2M7.500 9h6M7.500 12.500h6M7.500 16h3.500" />,
  calendar: <path d="M4 6.500h16V20H4zM4 10.500h16M8 4v4M16 4v4M8 14h2.500M13.500 14H16" />,
  heart: <path d="M12 20.500S4 15.300 4 9.600A4.300 4.300 0 0 1 12 7.400a4.300 4.300 0 0 1 8 2.200c0 5.700-8 10.900-8 10.900z" />,
};

export const Icon: React.FC<{ name: string; size?: number; color?: string; stroke?: number }> = ({
  name,
  size = 48,
  color = C.contrast,
  stroke = 1.7,
}) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round">
    {ICONS[name]}
  </svg>
);

export const shadow = "0 18px 44px rgba(26,26,26,0.16), 0 2px 6px rgba(26,26,26,0.10)";
