import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Sequence,
  useVideoConfig,
  delayRender,
  continueRender,
  staticFile,
  Img,
} from "remotion";
import { AnimationScript } from "../types";
import { TenirFin } from "../tenir-fin";
import { theme } from "../theme";
import { MotionSegment } from "../segments/MotionSegment";

// Loading the local woff2 fonts of the kit's design system
const loadFonts = async () => {
  const families = [
    { name: "Source Serif", file: "SourceSerif4-Italic.woff2", style: "italic", weight: "100 900" },
    { name: "Source Serif", file: "SourceSerif4-Roman.woff2", style: "normal", weight: "100 900" },
    { name: "Inter", file: "Inter-Regular.woff2", style: "normal", weight: "400" },
    { name: "Inter", file: "Inter-Bold.woff2", style: "normal", weight: "700" },
    { name: "Inter", file: "Inter-Italic.woff2", style: "italic", weight: "400" },
    { name: "Inter", file: "Inter-BoldItalic.woff2", style: "italic", weight: "700" },
  ];
  await Promise.all(
    families.map(async (f) => {
      const url = staticFile(`fonts/${f.file}`);
      const face = new FontFace(f.name, `url(${url}) format("woff2")`, {
        style: f.style as FontFaceDescriptors["style"],
        weight: f.weight,
      });
      const loaded = await face.load();
      (document.fonts as unknown as Set<FontFace>).add(loaded);
    }),
  );
};

export const BrandedVideo: React.FC<AnimationScript> = (props) => {
  const { fps } = useVideoConfig();
  const [handle] = useState(() => delayRender("Loading theme fonts"));

  useEffect(() => {
    loadFonts()
      .then(() => continueRender(handle))
      .catch((e) => {
        console.error("Font load error", e);
        continueRender(handle);
      });
  }, [handle]);

  let cursor = 0;
  return (
    <TenirFin main={Math.max(1, Math.ceil(props.segments.reduce((acc, s) => acc + s.durationSec, 0) * fps))}>
      <AbsoluteFill style={{ background: theme.color.base }}>
        {props.segments.map((seg, i) => {
          const durFrames = Math.ceil(seg.durationSec * fps);
          const from = cursor;
          cursor += durFrames;

          // BrandedVideo only displays the premiums (motion).
          // The lower thirds / section titles are rendered in LowerThirdTrack (alpha).
          if (seg.type !== "motion") return null;

          return (
            <Sequence key={i} from={from} durationInFrames={durFrames}>
              <BrandedFrame>
                <MotionSegment segment={seg} />
              </BrandedFrame>
            </Sequence>
          );
        })}
      </AbsoluteFill>
    </TenirFin>
  );
};

// Common frame for the premiums: white background, inner padding. No logo: it loads the image for nothing.
const BrandedFrame: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill
    style={{
      background: theme.color.base,
      paddingTop: theme.layout.padV,
      paddingBottom: theme.layout.padV,
      paddingLeft: theme.layout.padH,
      paddingRight: theme.layout.padH,
      boxSizing: "border-box",
    }}
  >
    {children}
  </AbsoluteFill>
);
