import React from "react";
import { Composition } from "remotion";
import { BrandedVideo } from "./compositions/BrandedVideo";
import { LowerThirdTrack } from "./compositions/LowerThirdTrack";
import { Screencast, screencastDefaults, ScreencastProps } from "./compositions/Screencast";
import { Scene, sceneDefaults, SceneCompProps } from "./scenes/Scene";
import { ControleTexte, controleDefaults, controleFrames, ControleProps } from "./controle";
import { FondAnime, fondAnimeDefaults, FondAnimeProps } from "./compositions/FondAnime";
import { AnimationScript, AnimationScriptSchema } from "./types";

const defaultScript: AnimationScript = {
  version: 1,
  fps: 30,
  width: 1920,
  height: 1080,
  segments: [
    {
      type: "motion",
      component: "quote-full",
      durationSec: 12,
      data: {
        text: "A picture is worth a thousand words, if you know how to look at it.",
        author: "Example",
        source: "Kit demo",
      },
    },
    {
      type: "section-title",
      durationSec: 4,
      data: {
        eyebrow: "Chapitre 1",
        title: "An approach, not a style",
      },
    },
    {
      type: "lower-third",
      kind: "lower-third-nom",
      durationSec: 6,
      data: {
        name: "Saul Leiter",
        years: "1923-2013",
        tag: "New York School",
      },
    },
  ],
};

// duration of the animations; the composition adds `tailFrames` frames of held last frame
export const mainFrames = (props: AnimationScript) =>
  Math.ceil(props.segments.reduce((acc, s) => acc + s.durationSec, 0) * (props.fps ?? 30));
const durationFrames = (props: AnimationScript) => mainFrames(props) + (props.tailFrames ?? 0);

export const IllustrationCompositions: React.FC = () => {
  return (
    <>
      <Composition
        id="BrandedVideo"
        component={BrandedVideo}
        durationInFrames={durationFrames(defaultScript)}
        fps={defaultScript.fps ?? 30}
        width={defaultScript.width ?? 1920}
        height={defaultScript.height ?? 1080}
        defaultProps={defaultScript}
        schema={AnimationScriptSchema}
        calculateMetadata={({ props }) => ({
          durationInFrames: durationFrames(props),
          fps: props.fps ?? 30,
          width: props.width ?? 1920,
          height: props.height ?? 1080,
        })}
      />
      <Composition
        id="LowerThirdTrack"
        component={LowerThirdTrack}
        durationInFrames={durationFrames(defaultScript)}
        fps={defaultScript.fps ?? 30}
        width={defaultScript.width ?? 1920}
        height={defaultScript.height ?? 1080}
        defaultProps={defaultScript}
        schema={AnimationScriptSchema}
        calculateMetadata={({ props }) => ({
          durationInFrames: durationFrames(props),
          fps: props.fps ?? 30,
          width: props.width ?? 1920,
          height: props.height ?? 1080,
        })}
      />
      <Composition
        id="Screencast"
        component={Screencast}
        durationInFrames={screencastDefaults.durationInFrames}
        fps={screencastDefaults.fps}
        width={screencastDefaults.width}
        height={screencastDefaults.height}
        defaultProps={screencastDefaults}
        calculateMetadata={({ props }: { props: ScreencastProps }) => ({
          durationInFrames: props.durationInFrames,
          fps: props.fps,
          width: props.width,
          height: props.height,
        })}
      />
      <Composition
        id="ControleTexte"
        component={ControleTexte}
        durationInFrames={1}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={controleDefaults}
        calculateMetadata={({ props }: { props: ControleProps }) => ({
          durationInFrames: Math.max(1, controleFrames(props)),
          fps: props.fps,
          width: props.width,
          height: props.height,
        })}
      />
      <Composition
        id="Scene"
        component={Scene}
        durationInFrames={Math.round(sceneDefaults.durationSec * sceneDefaults.fps)}
        fps={sceneDefaults.fps}
        width={sceneDefaults.width}
        height={sceneDefaults.height}
        defaultProps={sceneDefaults}
        calculateMetadata={({ props }: { props: SceneCompProps }) => ({
          durationInFrames: Math.max(1, Math.round(props.durationSec * props.fps)) + (props.tailFrames ?? 0),
          fps: props.fps,
          width: props.width,
          height: props.height,
        })}
      />
      {/* Animated background for Tella-style edits: loop of `periode` s, 4K, background (V1) and frame (V4, alpha) modes */}
      <Composition
        id="FondAnime"
        component={FondAnime}
        durationInFrames={600}
        fps={30}
        width={3840}
        height={2160}
        defaultProps={fondAnimeDefaults}
        calculateMetadata={({ props }: { props: FondAnimeProps }) => ({ durationInFrames: Math.round(props.periode * 30) })}
      />
    </>
  );
};
