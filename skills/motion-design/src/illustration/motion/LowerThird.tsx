import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { theme } from "../theme";
import { LowerThirdKind } from "../types";

type Data = Record<string, string | undefined>;
type Props = { kind: LowerThirdKind; data: Data };

// LowerThird: transparent overlay at the bottom left.
// 4 kinds: term / nom / oeuvre / lieu: same visual chrome, different content.
// Chrome: white block at 95% opacity, 4px accent left border, subtle shadow.
// Animation: slide-up + fade-in on entry, fade-out over the last 18 frames.
export const LowerThird: React.FC<Props> = ({ kind, data }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const vertical = height > width; // reel 9:16

  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 90, mass: 0.6 } });
  const translateY = interpolate(enter, [0, 1], [40, 0]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 18, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // Layout adapted to the ratio. In 16:9: bottom left, wide maxWidth.
  // In 9:16 (reel): the block must fit within 1080 wide and sit above
  // the bottom subtitle/UI zone (~340px reserved on a reel).
  const sideMargin = vertical ? 48 : 120;
  const bottomPos = vertical ? 440 : 140;
  const maxW = width - sideMargin * 2;

  return (
    <div
      style={{
        position: "absolute",
        left: sideMargin,
        bottom: bottomPos,
        opacity: opacity * fadeOut,
        transform: `translateY(${translateY}px)`,
        background: "rgba(255,255,255,0.96)",
        borderLeft: `${vertical ? 6 : 4}px solid ${theme.color.accent}`,
        padding: vertical ? "24px 36px 24px 30px" : "28px 44px 28px 36px",
        boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
        borderRadius: 4,
        maxWidth: maxW,
      }}
    >
      {renderContent(kind, data, vertical)}
    </div>
  );
};

function renderContent(kind: LowerThirdKind, d: Data, vertical = false) {
  const termStyle = vertical ? termStyleV : termStyleH;
  const subStyle = vertical ? subStyleV : subStyleH;
  switch (kind) {
    case "lower-third-term":
      return (
        <>
          <p style={termStyle}>{d.term}</p>
          {d.subtitle && <p style={subStyle}>{d.subtitle}</p>}
        </>
      );
    case "lower-third-nom":
      return (
        <>
          <p style={termStyle}>{d.name}</p>
          <p style={subStyle}>
            {d.years}
            {d.years && d.tag ? "  ·  " : ""}
            {d.tag}
          </p>
        </>
      );
    case "lower-third-oeuvre":
      return (
        <>
          <p style={{ ...termStyle, fontFamily: theme.font.display, fontStyle: "italic", fontWeight: theme.weight.regular }}>
            {d.title}
          </p>
          <p style={subStyle}>
            {d.author}
            {d.author && d.year ? "  ·  " : ""}
            {d.year}
          </p>
        </>
      );
    case "lower-third-lieu":
      return (
        <>
          <p style={termStyle}>{d.place}</p>
          <p style={{ ...subStyle, fontFamily: theme.font.mono }}>{d.date}</p>
        </>
      );
  }
}

const termStyleH: React.CSSProperties = {
  margin: 0,
  fontFamily: theme.font.sans,
  fontWeight: theme.weight.bold,
  fontSize: 64,
  lineHeight: 1.1,
  letterSpacing: theme.ls.heading,
  color: theme.color.contrast,
};

const subStyleH: React.CSSProperties = {
  margin: "10px 0 0 0",
  fontFamily: theme.font.sans,
  fontWeight: theme.weight.regular,
  fontSize: 32,
  lineHeight: 1.3,
  color: theme.color.muted,
};

// 9:16 variants: slightly more compact title to fit on ≤2 lines in 1080 wide,
// slightly smaller subtitle. Same chrome, same hierarchy.
const termStyleV: React.CSSProperties = { ...termStyleH, fontSize: 56 };
const subStyleV: React.CSSProperties = { ...subStyleH, fontSize: 30 };
