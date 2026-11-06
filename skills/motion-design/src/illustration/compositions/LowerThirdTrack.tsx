import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Sequence,
  useVideoConfig,
  delayRender,
  continueRender,
  staticFile,
} from "remotion";
import { AnimationScript } from "../types";
import { TenirFin } from "../tenir-fin";
import { LowerThird } from "../motion/LowerThird";
import { SectionTitle } from "../motion/SectionTitle";

const loadFonts = async () => {
  const families = [
    { name: "Source Serif", file: "SourceSerif4-Italic.woff2", style: "italic", weight: "100 900" },
    { name: "Source Serif", file: "SourceSerif4-Roman.woff2", style: "normal", weight: "100 900" },
    { name: "Inter", file: "Inter-Regular.woff2", style: "normal", weight: "400" },
    { name: "Inter", file: "Inter-Bold.woff2", style: "normal", weight: "700" },
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

// LowerThirdTrack: composition with a TRANSPARENT background for ProRes 4444 alpha render (V6 Premiere).
// CRITICAL: do NOT add a background here, or the transparency is lost.
export const LowerThirdTrack: React.FC<AnimationScript> = (props) => {
  const { fps } = useVideoConfig();
  const [handle] = useState(() => delayRender("Chargement des fonts (alpha track)"));

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
      <AbsoluteFill>
        {props.segments.map((seg, i) => {
          const durFrames = Math.ceil(seg.durationSec * fps);
          const from = cursor;
          cursor += durFrames;

          if (seg.type === "lower-third") {
            return (
              <Sequence key={i} from={from} durationInFrames={durFrames}>
                <LowerThird kind={seg.kind ?? "lower-third-term"} data={seg.data} />
              </Sequence>
            );
          }
          if (seg.type === "section-title") {
            return (
              <Sequence key={i} from={from} durationInFrames={durFrames}>
                <SectionTitle eyebrow={seg.data.eyebrow} title={seg.data.title} />
              </Sequence>
            );
          }
          // Premiums: transparent (rendered separately in BrandedVideo)
          return null;
        })}
      </AbsoluteFill>
    </TenirFin>
  );
};
