import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { theme } from "../theme";

type Props = { eyebrow?: string; title: string };

// SectionTitle: transparent overlay centered (bottom of the frame).
// Accent eyebrow + Source Serif italic title. No background, just text.
// To dress up a sub-section transition in an editorial video.
export const SectionTitle: React.FC<Props> = ({ eyebrow, title }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 85, mass: 0.6 } });
  const translateY = interpolate(enter, [0, 1], [30, 0]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 18, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "flex-end",
        paddingBottom: 200,
        opacity: opacity * fadeOut,
      }}
    >
      <div
        style={{
          textAlign: "center",
          transform: `translateY(${translateY}px)`,
          background: "rgba(255,255,255,0.92)",
          padding: "36px 64px",
          borderTop: `2px solid ${theme.color.accent}`,
          borderBottom: `2px solid ${theme.color.accent}`,
        }}
      >
        {eyebrow && (
          <p
            style={{
              margin: "0 0 16px 0",
              fontFamily: theme.font.sans,
              fontWeight: theme.weight.bold,
              fontSize: theme.size.eyebrow,
              letterSpacing: theme.ls.eyebrow,
              textTransform: "uppercase",
              color: theme.color.accent,
            }}
          >
            {eyebrow}
          </p>
        )}
        <h2
          style={{
            margin: 0,
            fontFamily: theme.font.display,
            fontStyle: "italic",
            fontWeight: theme.weight.light,
            fontSize: 88,
            lineHeight: 1.15,
            letterSpacing: theme.ls.heading,
            color: theme.color.contrast,
          }}
        >
          {title}
        </h2>
      </div>
    </AbsoluteFill>
  );
};
