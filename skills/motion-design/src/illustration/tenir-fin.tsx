import React from "react";
import { Freeze, Sequence } from "remotion";

/* Renders `children` over `main` frames, then holds the last frame until the end of the
      composition. Used to render a file slightly LONGER than its Premiere clip: at 29.97,
      n sequence frames last n × 1.001 / 30 s, and a render of n frames at 30 fps used to end
      before its clip (Premiere then showed the track below, often the face, on the last
      frame or two). Animation exits, set on
      useVideoConfig().durationInFrames, do not move: the <Sequence> gives them `main`
      as duration (remotion/use-unsafe-video-config.js reads the duration from the SequenceContext). */
export const TenirFin: React.FC<{ main: number; children: React.ReactNode }> = ({ main, children }) => (
  <Freeze frame={main - 1} active={(f) => f >= main}>
    <Sequence durationInFrames={main}>{children}</Sequence>
  </Freeze>
);
