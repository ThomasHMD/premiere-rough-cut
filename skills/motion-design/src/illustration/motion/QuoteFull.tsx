import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { theme } from "../theme";

type Props = {
  text: string;
  author?: string;
  source?: string;
};

// Striking quote: Source Serif italic 300, 8px accent left border,
// Courier attribution at the bottom. Centered. White background.
export const QuoteFull: React.FC<Props> = ({ text, author, source }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Entry: slide-up + fade-in
  const enter = spring({ frame, fps, config: { damping: 200, stiffness: 80, mass: 0.6 } });
  const translateY = interpolate(enter, [0, 1], [40, 0]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);

  // Exit: fade over the last 18 frames
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
        justifyContent: "center",
        opacity: opacity * fadeOut,
      }}
    >
      <div
        style={{
          maxWidth: theme.layout.safeWidth - 200,
          borderLeft: `8px solid ${theme.color.accent}`,
          paddingLeft: 72,
          paddingRight: 24,
          transform: `translateY(${translateY}px)`,
        }}
      >
        <p
          style={{
            margin: 0,
            fontFamily: theme.font.display,
            fontStyle: "italic",
            fontWeight: theme.weight.light,
            fontSize: 96,
            lineHeight: 1.2,
            letterSpacing: theme.ls.heading,
            color: theme.color.contrast,
            textWrap: "balance" as any,
          }}
        >
          “{text}”
        </p>
        {(author || source) && (
          <p
            style={{
              marginTop: 56,
              marginBottom: 0,
              fontFamily: theme.font.mono,
              fontSize: theme.size.caption,
              color: theme.color.muted,
              letterSpacing: theme.ls.caption,
            }}
          >
            {author}
            {author && source ? "  ·  " : ""}
            {source}
          </p>
        )}
      </div>
    </AbsoluteFill>
  );
};
