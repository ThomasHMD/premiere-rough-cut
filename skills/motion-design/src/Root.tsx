import React from "react";
import { IllustrationCompositions } from "./illustration/Compositions";

// One composition = one deliverable. Default props can be overridden with --props at render time.
// Video graphics (BrandedVideo, LowerThirdTrack, Screencast, Scene): driven by
// ../illustration-video/scripts (render-segments.py, screencast-render.py).
// A whole video in motion design = a new composition here (SKILL.md, "Pipeline").
export const RemotionRoot: React.FC = () => (
  <>
    <IllustrationCompositions />
  </>
);
