import React from "react";
import { AbsoluteFill } from "remotion";
import { useDsFonts } from "./kit";
import { TenirFin } from "../tenir-fin";
import * as O from "./opaque";
import * as A from "./alpha";
import * as P from "./preuves";
import * as M from "./murs";
import * as MXS from "./matrix";
import * as OF from "./offre";

// "Scene" composition: one scene = a component + its content (`data`) + its
// moments (`cues`, in seconds from the start of the scene). Rendered on its own by
// render-segments.py: opaque in h264 (V5) or transparent in ProRes 4444 (V6).

export type SceneCompProps = {
  component: string;
  data: Record<string, any>;
  cues: number[];
  durationSec: number;
  // extra frames, last frame held (the file covers its whole Premiere clip)
  tailFrames?: number;
  fps: number;
  width: number;
  height: number;
};

export const OPAQUE: Record<string, React.FC<O.SceneProps>> = {
  "chapter-card": O.ChapterCard,
  "question-card": O.QuestionCard,
  stat: O.Stat,
  "phone-demo": O.PhoneDemo,
  // proofs: documents, figures, generic diagrams
  preuve: P.Preuve,
  chapitre: P.Chapitre,
  titre: P.Titre,
  dialogue: P.Dialogue,
  frise: P.Frise,
  duel: P.Duel,
  versus: P.Versus,
  demandes: P.Demandes,
  textes: P.Textes,
  noeuds: P.Noeuds,
  chiffres: P.Chiffres,
  dossier: P.Dossier,
  recherche: P.Recherche,
  terminal: P.Terminal,
  // a video (the 5 walls): walls, sort, route, one-voice, hanging, funding, mosaic
  murs: M.Murs,
  tri: M.Tri,
  route: M.Route,
  "une-voix": M.UneVoix,
  accrochage: M.Accrochage,
  financement: M.Financement,
  mosaique: M.Mosaique,
  citation: M.Citation,
  // a video (photo books): map, funnel, retro art direction (80s neon, 90s terminal)
  // a video (camera reverse engineering): "green Matrix terminal" art direction, matrix.tsx module
  "mx-chapitre": MXS.MxChapitre,
  "mx-matrice": MXS.MxMatrice,
  "mx-extinction": MXS.MxExtinction,
  "mx-secteurs": MXS.MxSecteurs,
  "mx-tables": MXS.MxTables,
  "mx-panneaux": MXS.MxPanneaux,
  "mx-emulateur": MXS.MxEmulateur,
  "mx-flux": MXS.MxFlux,
  "mx-picture-control": MXS.MxPictureControl,
  "mx-terminal": MXS.MxTerminal,
  "mx-courbes": MXS.MxCourbes,
  "mx-vues": MXS.MxVues,
  // a video: the offer, in the design system (after the terminal switches off)
  "offre-boitiers": OF.OffreBoitiers,
  "offre-lien": OF.OffreLien,
};

export const ALPHA: Record<string, React.FC<O.SceneProps>> = {
  stamp: A.Stamp,
  "stamp-rain": A.StampRain,
  slam: A.Slam,
  "lien-description": A.LienDescription,
  "side-list": A.SideList,
  "stat-tag": A.StatTag,
  "bulle-dm": A.BulleDM,
  "url-bar": A.UrlBar,
  volet: A.Volet,
  gif: P.Gif,
  sondages: M.Sondages,
  gaufre: M.Gaufre,
  croyance: M.Croyance,
};

export const sceneDefaults: SceneCompProps = {
  component: "chapter-card",
  data: {},
  cues: [],
  durationSec: 8,
  fps: 30,
  width: 1920,
  height: 1080,
};

export const Scene: React.FC<SceneCompProps> = ({ component, data, cues, durationSec, fps }) => {
  useDsFonts();
  const Comp = OPAQUE[component] ?? ALPHA[component];
  if (!Comp) {
    return (
      <AbsoluteFill style={{ background: "#F2F2F2", alignItems: "center", justifyContent: "center", fontSize: 60 }}>
        {`Unknown scene: ${component}`}
      </AbsoluteFill>
    );
  }
  return (
    <TenirFin main={Math.max(1, Math.round(durationSec * fps))}>
      <Comp data={data ?? {}} cues={cues ?? []} />
    </TenirFin>
  );
};
