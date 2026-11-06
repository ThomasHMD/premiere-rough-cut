import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  continueRender,
  delayRender,
  interpolate,
  Easing,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { theme } from "../theme";

// Screencast: web browsing demo Tella-style (background, browser window,
// zooms that follow the action, animated cursor, spotlight, captions).
// ALL the dynamics (camera, cursor) are precomputed frame by frame by
// scripts/screencast-render.py: this component only displays the state of each frame.

export type ScreencastProps = {
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  video: string; // file in --public-dir
  win: { x: number; y: number; w: number; h: number; bar: number; radius: number; k: number };
  background: "dark" | "paper" | "accent";
  chrome: boolean;
  cursorSize: number;
  cam: number[][]; // [scale, cx, cy] in scene px
  cur: number[][]; // [x, y, tilt°, press 0-1] in scene px
  clicks: { f: number; x: number; y: number }[];
  spots: { f0: number; f1: number; x: number; y: number; w: number; h: number }[];
  captions: { f0: number; f1: number; text: string; eyebrow?: string | null }[];
  urls: { f: number; url: string }[];
};

export const screencastDefaults: ScreencastProps = {
  fps: 60,
  width: 1920,
  height: 1080,
  durationInFrames: 60,
  video: "",
  win: { x: 160, y: 68, w: 1600, h: 944, bar: 44, radius: 14, k: 1600 / 1440 },
  background: "dark",
  chrome: true,
  cursorSize: 42,
  cam: [[1, 960, 540]],
  cur: [[1100, 600, 0, 0]],
  clicks: [],
  spots: [],
  captions: [],
  urls: [{ f: 0, url: "https://exemple.com/" }],
};

const loadFonts = async () => {
  const families = [
    { name: "Source Serif", file: "SourceSerif4-Roman.woff2", style: "normal", weight: "100 900" },
    { name: "Inter", file: "Inter-Regular.woff2", style: "normal", weight: "400" },
    { name: "Inter", file: "Inter-Bold.woff2", style: "normal", weight: "700" },
  ];
  await Promise.all(
    families.map(async (f) => {
      const face = new FontFace(f.name, `url(${staticFile(`fonts/${f.file}`)}) format("woff2")`, {
        style: f.style as FontFaceDescriptors["style"],
        weight: f.weight,
      });
      (document.fonts as unknown as Set<FontFace>).add(await face.load());
    }),
  );
};

const BACKGROUNDS: Record<ScreencastProps["background"], string> = {
  dark: `radial-gradient(120% 90% at 30% 10%, #2B2B2B 0%, ${theme.color.darkBg} 55%, #0E0E0E 100%)`,
  paper: `radial-gradient(120% 90% at 30% 10%, #FAFAFA 0%, ${theme.color.paperWarm} 55%, #E2E2E2 100%)`,
  accent: `radial-gradient(120% 100% at 25% 0%, #6B8CFF 0%, ${theme.color.accent} 45%, ${theme.color.accentDark} 100%)`,
};

const at = <T,>(arr: T[], i: number): T => arr[Math.max(0, Math.min(arr.length - 1, i))];

const displayUrl = (u: string) => u.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");

const BrowserBar: React.FC<{ url: string; h: number }> = ({ url, h }) => (
  <div
    style={{
      position: "absolute",
      inset: 0,
      height: h,
      background: "#ECECEC",
      borderBottom: "1px solid #D8D8D8",
      display: "flex",
      alignItems: "center",
      fontFamily: theme.font.sans,
    }}
  >
    <div style={{ display: "flex", gap: 9, paddingLeft: 18 }}>
      {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
        <div key={c} style={{ width: 13, height: 13, borderRadius: 7, background: c }} />
      ))}
    </div>
    <div
      style={{
        position: "absolute",
        left: "50%",
        transform: "translateX(-50%)",
        minWidth: "42%",
        height: h - 14,
        borderRadius: 8,
        background: "#FFFFFF",
        boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.06)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        padding: "0 22px",
        fontSize: 16,
        color: theme.color.inkSoft,
        letterSpacing: "0.01em",
      }}
    >
      <svg width="11" height="13" viewBox="0 0 11 13">
        <rect x="0.5" y="5.5" width="10" height="7" rx="1.5" fill={theme.color.muted} />
        <path d="M2.8 5.5V3.8a2.7 2.7 0 0 1 5.4 0v1.7" fill="none" stroke={theme.color.muted} strokeWidth="1.4" />
      </svg>
      {displayUrl(url)}
    </div>
  </div>
);

// macOS arrow, tip at (6, 3) in the 24×24 viewBox.
const Cursor: React.FC<{ x: number; y: number; tilt: number; press: number; size: number; camScale: number }> = ({
  x,
  y,
  tilt,
  press,
  size,
  camScale,
}) => {
  const tipX = (6 / 24) * size;
  const tipY = (3 / 24) * size;
  // The cursor lives in the zoomed layer; we partly compensate the zoom so
  // that it grows a little (readable) without becoming huge.
  const s = (1 / Math.sqrt(camScale)) * (1 - 0.16 * press);
  return (
    <div
      style={{
        position: "absolute",
        left: x - tipX,
        top: y - tipY,
        width: size,
        height: size,
        transformOrigin: `${tipX}px ${tipY}px`,
        transform: `rotate(${tilt}deg) scale(${s})`,
        filter: "drop-shadow(0 3px 4px rgba(0,0,0,0.35))",
      }}
    >
      <svg width={size} height={size} viewBox="0 0 24 24">
        <path
          d="M6 3 L6 19.2 L9.9 15.5 L12.4 21.2 L15.3 19.9 L12.8 14.3 L18.2 14.3 Z"
          fill="#111111"
          stroke="#FFFFFF"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
};

const Ripple: React.FC<{ x: number; y: number; age: number; fps: number; camScale: number }> = ({
  x,
  y,
  age,
  fps,
  camScale,
}) => {
  const dur = 0.5 * fps;
  if (age < 0 || age > dur) return null;
  const k = age / dur;
  const r = interpolate(k, [0, 1], [6, 34], { easing: Easing.out(Easing.cubic) }) / Math.sqrt(camScale);
  const o = interpolate(k, [0, 0.15, 1], [0, 0.9, 0]);
  return (
    <div
      style={{
        position: "absolute",
        left: x - r,
        top: y - r,
        width: 2 * r,
        height: 2 * r,
        borderRadius: "50%",
        border: `${3 / Math.sqrt(camScale)}px solid ${theme.color.accent}`,
        background: "rgba(47,91,234,0.12)",
        opacity: o,
      }}
    />
  );
};

export const Screencast: React.FC<ScreencastProps> = (p) => {
  const frame = useCurrentFrame();
  const { fps, width: W, height: H } = useVideoConfig();
  const [handle] = useState(() => delayRender("Chargement des fonts (screencast)"));
  useEffect(() => {
    loadFonts()
      .then(() => continueRender(handle))
      .catch(() => continueRender(handle));
  }, [handle]);

  const [s, cx, cy] = at(p.cam, frame);
  const [mx, my, tilt, press] = at(p.cur, frame);
  const tx = W / 2 - cx * s;
  const ty = H / 2 - cy * s;
  const url = [...p.urls].reverse().find((u) => u.f <= frame)?.url ?? p.urls[0]?.url ?? "";
  const { win } = p;
  const screenH = win.h - win.bar;

  return (
    <AbsoluteFill style={{ background: BACKGROUNDS[p.background] }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: W,
          height: H,
          transformOrigin: "0 0",
          transform: `translate(${tx}px, ${ty}px) scale(${s})`,
        }}
      >
        <div
          style={{
            position: "absolute",
            left: win.x,
            top: win.y,
            width: win.w,
            height: win.h,
            borderRadius: win.radius,
            overflow: "hidden",
            background: "#FFFFFF",
            boxShadow: "0 40px 90px rgba(0,0,0,0.45), 0 0 0 1px rgba(0,0,0,0.08)",
          }}
        >
          {p.chrome ? <BrowserBar url={url} h={win.bar} /> : null}
          <div style={{ position: "absolute", left: 0, top: win.bar, width: win.w, height: screenH, overflow: "hidden" }}>
            {p.video ? (
              <OffthreadVideo src={staticFile(p.video)} muted style={{ width: win.w, height: screenH, display: "block" }} />
            ) : null}
            {p.spots.map((sp, i) => {
              if (frame < sp.f0 - 1 || frame > sp.f1 + 0.3 * fps) return null;
              const o = Math.min(
                interpolate(frame, [sp.f0, sp.f0 + 0.3 * fps], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
                interpolate(frame, [sp.f1, sp.f1 + 0.3 * fps], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
              );
              return (
                <div
                  key={i}
                  style={{
                    position: "absolute",
                    left: sp.x - win.x,
                    top: sp.y - win.y - win.bar,
                    width: sp.w,
                    height: sp.h,
                    borderRadius: 12,
                    boxShadow: `0 0 0 4000px rgba(12,12,12,${0.55 * o}), 0 0 0 ${2 / s}px rgba(255,255,255,${0.9 * o})`,
                  }}
                />
              );
            })}
          </div>
        </div>
        {p.clicks.map((c, i) => (
          <Ripple key={i} x={c.x} y={c.y} age={frame - c.f} fps={fps} camScale={s} />
        ))}
        <Cursor x={mx} y={my} tilt={tilt} press={press} size={p.cursorSize} camScale={s} />
      </div>

      {p.captions.map((c, i) => {
        if (frame < c.f0 || frame > c.f1 + 0.4 * fps) return null;
        const inK = interpolate(frame, [c.f0, c.f0 + 0.35 * fps], [0, 1], {
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.cubic),
        });
        const outK = interpolate(frame, [c.f1, c.f1 + 0.3 * fps], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const o = Math.min(inK, outK);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: "50%",
              bottom: 54,
              transform: `translate(-50%, ${(1 - inK) * 24}px)`,
              opacity: o,
              background: "rgba(26,26,26,0.92)",
              borderRadius: 14,
              padding: "16px 30px 18px",
              boxShadow: "0 18px 40px rgba(0,0,0,0.35)",
              textAlign: "center",
              fontFamily: theme.font.sans,
              whiteSpace: "nowrap",
            }}
          >
            {c.eyebrow ? (
              <div
                style={{
                  fontSize: 17,
                  fontWeight: 700,
                  letterSpacing: theme.ls.eyebrow,
                  textTransform: "uppercase",
                  color: "#6B8CFF",
                  marginBottom: 6,
                }}
              >
                {c.eyebrow}
              </div>
            ) : null}
            <div style={{ fontSize: 34, fontWeight: 700, color: "#FFFFFF", letterSpacing: "-0.005em" }}>{c.text}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
