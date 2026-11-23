import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile } from "remotion";
import { C, F, clamp, easeOut, easeStd, nb, ramp, rnd, useT } from "./kit";
import { SceneProps } from "./opaque";

// "Nocturne" look: night as it comes out of the photos, not ink black. A deep urban night
// blue, and in it the only thing that matters when you photograph at night: the light of
// the street lamps. It is the subject of the video ("the danger is not the dark, it is the
// street lamps") and it drives the whole overlay language: everything that appears is
// LIT by a rising sodium halo, never pushed or slid in.
//
// Three motifs, all specific to the subject (a look follows its own direction, never
// another one's signature motif):
//   1. the street lamp halo : the warm glow that radiates from a point and fills the frame;
//   2. the long-exposure streak : a light trail that stretches for the length of the exposure
//                                (a train passing over a bridge, headlights);
//   3. the hand shake : a very slow 1 to 2 px oscillation that settles down.
//                                That is stabilization, the very subject of the video.
//
// Rules: night blue and sodium for the set, warm white for text, the design system red as
// a signal only (a corrected error, a keyword). Source Serif italic for what is said, Inter
// for what is explained, Courier Prime for what is measured (shooting data: the camera's
// own language). Never a logo.
// A photo is NEVER cropped and keeps a full border: its native ratio rules.
// All content comes from `data`, all timings from `cues` (seconds from the start).

export const NT = {
  nuit: "#080B14",
  fond: "#0D1220",
  voile: "#121A2C",
  sodium: "#F2A33C",
  sodiumPale: "#FFD9A0",
  mercure: "#7FA6D9",
  pale: "#E8E2D4",
  doux: "#A9B2C4",
  trait: "rgba(232,226,212,0.16)",
  mono: "Courier Prime, Courier New, monospace",
};

const cue = (cues: number[], i: number, fallback: number) =>
  typeof cues?.[i] === "number" ? cues[i] : fallback;

/** Warm glow of a text or a stroke lit by sodium light. */
export const lueur = (force = 1) =>
  `0 0 ${10 * force}px rgba(242,163,60,${0.45 * force}), 0 0 ${34 * force}px rgba(242,163,60,${0.16 * force})`;

/* ------------------------------------------------------------------ */
/* The background: night blue, street lamp halos, grain, hand shake. */

/** Street lamp halo: a very spread-out disc of warm light that breathes. */
const Halo: React.FC<{ x: number; y: number; r: number; force: number; teinte?: string }> = ({
  x,
  y,
  r,
  force,
  teinte = "242,163,60",
}) => (
  <div
    style={{
      position: "absolute",
      left: x - r,
      top: y - r,
      width: r * 2,
      height: r * 2,
      borderRadius: "50%",
      background: `radial-gradient(circle, rgba(${teinte},${0.3 * force}) 0%, rgba(${teinte},${
        0.12 * force
      }) 32%, rgba(${teinte},0) 70%)`,
      filter: "blur(2px)",
      pointerEvents: "none",
    }}
  />
);

/**
 * Background of every Nocturne scene. `allume` rises from 0 to 1: the night lights up.
 * `bouge`: amplitude of the handheld shake in px (0 = stabilized).
 */
export const Nuit: React.FC<{
  children: React.ReactNode;
  allume?: number;
  bouge?: number;
  halos?: [number, number, number, number][];
}> = ({ children, allume = 1, bouge = 1.6, halos }) => {
  const t = useT();
  // shake: two slow, detuned sine waves, never a visible loop
  const dx = bouge * (Math.sin(t * 0.47) * 0.6 + Math.sin(t * 0.83 + 1.7) * 0.4);
  const dy = bouge * (Math.sin(t * 0.61 + 0.9) * 0.6 + Math.sin(t * 1.07) * 0.4);
  const pts: [number, number, number, number][] =
    halos ?? [
      [330, 210, 620, 1],
      [1660, 880, 520, 0.7],
      [980, -60, 760, 0.45],
    ];
  return (
    <AbsoluteFill style={{ background: NT.nuit, overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(130% 110% at 24% 18%, ${NT.voile} 0%, ${NT.fond} 46%, ${NT.nuit} 100%)`,
        }}
      />
      {pts.map(([x, y, r, f], i) => (
        <Halo key={i} x={x} y={y} r={r} force={f * allume} />
      ))}
      <Halo x={1820} y={1160} r={560} force={0.5 * allume} teinte="127,166,217" />
      <AbsoluteFill style={{ transform: `translate(${dx}px, ${dy}px)` }}>{children}</AbsoluteFill>
      <Grain />
      <AbsoluteFill
        style={{
          background: "radial-gradient(118% 100% at 50% 50%, rgba(0,0,0,0) 52%, rgba(0,0,0,0.5) 100%)",
          pointerEvents: "none",
        }}
      />
    </AbsoluteFill>
  );
};

/** Fine film grain: night pushes the ISO, and you can see it. Deterministic, no harsh animated noise. */
const Grain: React.FC<{ force?: number }> = ({ force = 0.07 }) => {
  const t = useT();
  const pas = Math.floor(t * 8); // the grain changes 8 times per second, not 30: less nervous
  return (
    <AbsoluteFill style={{ opacity: force, mixBlendMode: "overlay", pointerEvents: "none" }}>
      <svg width="100%" height="100%">
        <filter id={`gr${pas % 4}`}>
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed={pas % 4} />
        </filter>
        <rect width="100%" height="100%" filter={`url(#gr${pas % 4})`} />
      </svg>
    </AbsoluteFill>
  );
};

/** Long-exposure streak: a light trail that stretches, then fades out. */
export const File: React.FC<{ y: number; at: number; duree?: number; largeur?: number; teinte?: string }> = ({
  y,
  at,
  duree = 1.1,
  largeur = 1920,
  teinte = NT.sodiumPale,
}) => {
  const t = useT();
  const p = ramp(t, at, at + duree, easeOut);
  const fin = interpolate(t, [at + duree, at + duree + 0.9], [1, 0], clamp);
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: y,
        width: largeur * p,
        height: 3,
        background: `linear-gradient(to right, rgba(255,217,160,0) 0%, ${teinte} 70%, #FFFFFF 100%)`,
        boxShadow: lueur(1.1),
        opacity: fin,
      }}
    />
  );
};

/** Overline of the look: small spaced capitals, sodium rule. */
export const Surtitre: React.FC<{ children: React.ReactNode; at?: number }> = ({ children, at = 0 }) => {
  const t = useT();
  const o = ramp(t, at, at + 0.35);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 18, opacity: o }}>
      <div style={{ width: 46 * o, height: 2, background: NT.sodium, boxShadow: lueur(0.8) }} />
      <div
        style={{
          fontFamily: F.sans,
          fontWeight: 500,
          fontSize: 28,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: NT.sodium,
        }}
      >
        {children}
      </div>
    </div>
  );
};

/** "Lighting up" entrance: the light rises on the element, which barely moves. */
const Allume: React.FC<{ at: number; dur?: number; monte?: number; children: React.ReactNode }> = ({
  at,
  dur = 0.5,
  monte = 14,
  children,
}) => {
  const t = useT();
  const p = ramp(t, at, at + dur, easeStd);
  return (
    <div style={{ opacity: p, transform: `translateY(${(1 - p) * monte}px)`, filter: `brightness(${0.55 + 0.45 * p})` }}>
      {children}
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Fiche technique : la langue de l'appareil (Courier Prime).           */

export type Expo = { pose?: string; ouverture?: string; iso?: string; note?: string };

/** Shooting data, line by line. `at`: start; each line follows by 0.18 s. */
export const Fiche: React.FC<{ expo: Expo; at: number; align?: "left" | "right"; size?: number; ligne?: boolean }> = ({
  expo,
  at,
  align = "left",
  size = 34,
  ligne = false,
}) => {
  const lignes = [
    expo.pose && ["Exposure", expo.pose],
    expo.ouverture && ["Aperture", expo.ouverture],
    expo.iso && ["ISO", expo.iso],
  ].filter(Boolean) as [string, string][];
  // `ligne`: the settings side by side, for a banner above the cards of the screencast layout
  return (
    <div style={ligne ? { display: "flex", alignItems: "baseline", gap: 40 } : { textAlign: align }}>
      {lignes.map(([k, v], i) => (
        <Allume key={k} at={at + i * 0.18} dur={0.4} monte={8}>
          <div
            style={{
              display: "flex",
              justifyContent: align === "right" ? "flex-end" : "flex-start",
              alignItems: "baseline",
              gap: 16,
              marginBottom: ligne ? 0 : 8,
              fontFamily: NT.mono,
              fontSize: size,
              color: NT.doux,
            }}
          >
            <span style={{ letterSpacing: "0.08em", textTransform: "uppercase", fontSize: size * 0.72 }}>{k}</span>
            <span style={{ color: NT.sodiumPale, fontSize: size * 1.12, textShadow: lueur(0.5) }}>{nb(v)}</span>
          </div>
        </Allume>
      ))}
      {expo.note && (
        <Allume at={at + lignes.length * 0.18} dur={0.45} monte={8}>
          <div
            style={{
              marginTop: ligne ? 0 : 14,
              fontFamily: F.sans,
              fontWeight: 500,
              fontSize: size * 0.96,
              color: NT.pale,
              letterSpacing: "0.01em",
            }}
          >
            {nb(expo.note)}
          </div>
        </Allume>
      )}
    </div>
  );
};

/* ================================================================== */
/* 1. nt-photo: a whole photo, with its shooting data sheet.          */
/*    data : { src, orientation?, titre?, expo:{pose,ouverture,iso,note}, surtitre? } */
/*    cues: [0] the photo lights up, [1] the sheet is written            */
/* ================================================================== */

export const NtPhoto: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const c0 = cue(cues, 0, 0.1);
  const c1 = cue(cues, 1, c0 + 0.7);
  const portrait = !!data?.portrait;
  // full border, native ratio: the photo fits in a box, never cropped (editor's rule)
  const boite = portrait ? { w: 760, h: 1010 } : data?.fiche === false ? { w: 1560, h: 880 } : { w: 1180, h: 790 };
  const p = ramp(t, c0, c0 + 0.75, easeStd);
  // very slow breathing: 1.5% over the whole scene, in the direction of the long exposure
  const zoom = 1 + 0.015 * ramp(t, c0, c0 + 14, easeOut);
  const avecFiche = data?.fiche !== false && (data?.expo || data?.titre);
  return (
    <Nuit allume={ramp(t, c0 - 0.2, c0 + 1.1)} bouge={1.4}>
      <AbsoluteFill
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: avecFiche ? "space-between" : "center",
          padding: avecFiche ? "0 130px" : "0 120px",
          gap: 90,
        }}
      >
        <div
          style={{
            width: boite.w,
            height: boite.h,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            opacity: p,
            transform: `scale(${0.985 + 0.015 * p})`,
            flex: "0 0 auto",
          }}
        >
          <div style={{ position: "relative", overflow: "hidden", boxShadow: `0 40px 120px rgba(0,0,0,0.65)` }}>
            <Img
              src={staticFile(data.src)}
              style={{
                display: "block",
                maxWidth: boite.w,
                maxHeight: boite.h,
                width: "auto",
                height: "auto",
                transform: `scale(${zoom})`,
                transformOrigin: "50% 50%",
                filter: `brightness(${0.7 + 0.3 * p})`,
              }}
            />
          </div>
        </div>
        {avecFiche && (
          <div style={{ flex: "1 1 auto", maxWidth: 700 }}>
            {data?.surtitre && <Surtitre at={c0 + 0.1}>{data.surtitre}</Surtitre>}
            {data?.titre && (
              <Allume at={c0 + 0.25} dur={0.5}>
                <div
                  style={{
                    marginTop: 22,
                    marginBottom: 34,
                    fontFamily: F.display,
                    fontStyle: "italic",
                    fontWeight: 300,
                    fontSize: data.titre.length > 40 ? 64 : 78,
                    lineHeight: 1.1,
                    letterSpacing: "-0.015em",
                    color: NT.pale,
                    textWrap: "balance",
                  }}
                >
                  {nb(data.titre)}
                </div>
              </Allume>
            )}
            {data?.expo && <Fiche expo={data.expo} at={c1} />}
          </div>
        )}
      </AbsoluteFill>
    </Nuit>
  );
};

/* ================================================================== */
/* 2. nt-pose: the exposure time in large type, the shutter, the streak. */
/*    data : { valeur, unite?, sous?, note?, main? }                   */
/*    cues : [0] l'iris s'ouvre, [1] le chiffre, [2] la note           */
/* ================================================================== */

/** Central shutter: the blades open then close. The speaker mentions it ("an iris"). */
const Iris: React.FC<{ at: number; duree: number; r?: number }> = ({ at, duree, r = 210 }) => {
  const t = useT();
  const ouvre = ramp(t, at, at + 0.45, easeOut);
  const ferme = interpolate(t, [at + duree, at + duree + 0.4], [0, 1], clamp);
  const o = Math.max(0, ouvre - ferme);
  const lames = 7;
  return (
    <svg width={r * 2} height={r * 2} viewBox={`0 0 ${r * 2} ${r * 2}`} style={{ position: "absolute" }}>
      <circle cx={r} cy={r} r={r - 6} fill="none" stroke={NT.trait} strokeWidth={2} />
      {Array.from({ length: lames }).map((_, i) => {
        const a = (i / lames) * 360;
        const d = (1 - o) * r * 0.86;
        return (
          <g key={i} transform={`rotate(${a} ${r} ${r})`}>
            <path
              d={`M ${r} ${r - r * 0.92} L ${r + r * 0.62} ${r - r * 0.42} L ${r} ${r + r * 0.1} Z`}
              fill="none"
              stroke={NT.sodium}
              strokeWidth={2.5}
              opacity={0.55}
              transform={`translate(0 ${-d})`}
            />
          </g>
        );
      })}
      <circle cx={r} cy={r} r={(r - 20) * o} fill="rgba(242,163,60,0.1)" />
    </svg>
  );
};

export const NtPose: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const c0 = cue(cues, 0, 0.1);
  const c1 = cue(cues, 1, c0 + 0.5);
  const c2 = cue(cues, 2, c1 + 1.2);
  const duree = data?.duree ?? 3.2;
  return (
    <Nuit allume={ramp(t, c0 - 0.2, c0 + 1)} bouge={data?.main === false ? 0.4 : 2.2}>
      <File y={104} at={c0 + 0.3} duree={Math.max(1.0, duree * 0.8)} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        {/* the shutter opens ABOVE the number: behind it, its blades cut the text */}
        <div style={{ position: "relative", width: 200, height: 200, marginBottom: 34 }}>
          <Iris at={c0} duree={duree} r={100} />
        </div>
        <div style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Allume at={c1} dur={0.45} monte={10}>
            <div style={{ textAlign: "center", position: "relative" }}>
              <div
                style={{
                  fontFamily: F.display,
                  fontWeight: 300,
                  fontSize: 240,
                  lineHeight: 1,
                  letterSpacing: "-0.03em",
                  color: NT.pale,
                  textShadow: lueur(0.9),
                }}
              >
                {nb(String(data?.valeur ?? ""))}
                {data?.unite && (
                  <span style={{ fontSize: 96, color: NT.sodiumPale, marginLeft: 14 }}>{nb(data.unite)}</span>
                )}
              </div>
            </div>
          </Allume>
        </div>
        {data?.sous && (
          <Allume at={c1 + 0.2} dur={0.4}>
            <div
              style={{
                marginTop: 28,
                fontFamily: NT.mono,
                fontSize: 38,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: NT.doux,
              }}
            >
              {nb(data.sous)}
            </div>
          </Allume>
        )}
        {data?.note && (
          <Allume at={c2} dur={0.5}>
            <div
              style={{
                marginTop: 58,
                maxWidth: 1180,
                textAlign: "center",
                fontFamily: F.display,
                fontStyle: "italic",
                fontWeight: 300,
                fontSize: 70,
                lineHeight: 1.14,
                color: NT.sodiumPale,
                textWrap: "balance",
              }}
            >
              {nb(data.note)}
            </div>
          </Allume>
        )}
      </AbsoluteFill>
    </Nuit>
  );
};

/* ================================================================== */
/* 3. nt-mur: 2 to 4 photos hung in the night, one per word.           */
/*    data : { surtitre?, photos:[{src, legende?, portrait?}] }        */
/*    cues : une par photo                                             */
/* ================================================================== */

export const NtMur: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const photos: any[] = data?.photos ?? [];
  const n = Math.max(1, photos.length);
  const marge = 120;
  const gap = n >= 4 ? 44 : 60;
  const large = (1920 - marge * 2 - gap * (n - 1)) / n;
  const haut = data?.surtitre ? 700 : 780;
  const c0 = cue(cues, 0, 0.15);
  return (
    <Nuit allume={ramp(t, c0 - 0.2, c0 + 1.2)} bouge={1.2}>
      <AbsoluteFill style={{ flexDirection: "column", justifyContent: "center", padding: `0 ${marge}px` }}>
        {data?.surtitre && (
          <div style={{ marginBottom: 52 }}>
            <Surtitre at={c0}>{data.surtitre}</Surtitre>
          </div>
        )}
        <div style={{ display: "flex", alignItems: "flex-start", gap, justifyContent: "center" }}>
          {photos.map((p, i) => {
            const at = cue(cues, data?.surtitre ? i + 1 : i, c0 + i * 0.9);
            const a = ramp(t, at, at + 0.6, easeStd);
            return (
              <div key={i} style={{ width: large, opacity: a, transform: `translateY(${(1 - a) * 18}px)` }}>
                <div
                  style={{
                    height: haut,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    overflow: "hidden",
                    boxShadow: "0 30px 90px rgba(0,0,0,0.6)",
                  }}
                >
                  <Img
                    src={staticFile(p.src)}
                    style={{
                      display: "block",
                      maxWidth: large,
                      maxHeight: haut,
                      width: "auto",
                      height: "auto",
                      filter: `brightness(${0.6 + 0.4 * a})`,
                    }}
                  />
                </div>
                {p.legende && (
                  <div
                    style={{
                      marginTop: 20,
                      fontFamily: NT.mono,
                      fontSize: 28,
                      lineHeight: 1.3,
                      color: NT.doux,
                      opacity: ramp(t, at + 0.25, at + 0.6),
                    }}
                  >
                    {nb(p.legende)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </Nuit>
  );
};

/* ================================================================== */
/* 4. nt-citation: a sentence that lights up in the night.             */
/*    data : { lignes:[], auteur?, source?, accent? }                  */
/* ================================================================== */

export const NtCitation: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const lignes: string[] = data?.lignes ?? [];
  const c0 = cue(cues, 0, 0.15);
  const size = data?.size ?? (lignes.some((l) => l.length > 34) ? 78 : 94);
  const barre = ramp(t, c0, c0 + 0.6, easeStd);
  return (
    <Nuit allume={ramp(t, c0 - 0.2, c0 + 1.2)} bouge={1.5} halos={[[420, 300, 700, 1], [1560, 920, 480, 0.55]]}>
      <AbsoluteFill style={{ justifyContent: "center", padding: "0 230px" }}>
        <div style={{ position: "relative", paddingLeft: 64 }}>
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 10,
              bottom: 10,
              width: 8,
              background: NT.sodium,
              boxShadow: lueur(0.9),
              transform: `scaleY(${barre})`,
              transformOrigin: "50% 0",
            }}
          />
          {lignes.map((l, i) => (
            <Allume key={i} at={cue(cues, i + 1, c0 + 0.25 + i * 0.8)} dur={0.55} monte={16}>
              <div
                style={{
                  fontFamily: F.display,
                  fontStyle: "italic",
                  fontWeight: 300,
                  fontSize: size,
                  lineHeight: 1.14,
                  letterSpacing: "-0.012em",
                  color: data?.accent === i ? NT.sodiumPale : NT.pale,
                  textWrap: "balance",
                }}
              >
                {nb(l)}
              </div>
            </Allume>
          ))}
          {(data?.auteur || data?.source) && (
            <Allume at={cue(cues, lignes.length + 1, c0 + 0.4 + lignes.length * 0.8)} dur={0.5}>
              <div style={{ marginTop: 44, fontFamily: NT.mono, fontSize: 32, color: NT.doux }}>
                {data?.auteur && <span style={{ color: NT.sodiumPale }}>{nb(data.auteur)}</span>}
                {data?.source && <span style={{ marginLeft: 18 }}>{nb(data.source)}</span>}
              </div>
            </Allume>
          )}
        </div>
      </AbsoluteFill>
    </Nuit>
  );
};

/* ================================================================== */
/* 5. nt-fiche: a visual on the left, data lines on the right.         */
/*    Serves a photographer (portrait + dates) and a camera.           */
/*    data : { src, portrait?, surtitre, titre, sous?, lignes:[[k,v]] } */
/* ================================================================== */

export const NtFiche: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const c0 = cue(cues, 0, 0.1);
  const lignes: [string, string][] = data?.lignes ?? [];
  const boite = data?.portrait ? { w: 660, h: 880 } : { w: 900, h: 720 };
  const a = ramp(t, c0, c0 + 0.7, easeStd);
  return (
    <Nuit allume={ramp(t, c0 - 0.2, c0 + 1.1)} bouge={1.3}>
      <AbsoluteFill
        style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 100, padding: "0 130px" }}
      >
        <div
          style={{
            width: boite.w,
            height: boite.h,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flex: "0 0 auto",
            opacity: a,
          }}
        >
          <div style={{ overflow: "hidden", boxShadow: "0 36px 100px rgba(0,0,0,0.66)" }}>
            <Img
              src={staticFile(data.src)}
              style={{
                display: "block",
                maxWidth: boite.w,
                maxHeight: boite.h,
                width: "auto",
                height: "auto",
                filter: `brightness(${0.62 + 0.38 * a})`,
              }}
            />
          </div>
        </div>
        <div style={{ flex: "1 1 auto", maxWidth: 740 }}>
          <Surtitre at={c0 + 0.15}>{data.surtitre}</Surtitre>
          <Allume at={c0 + 0.3} dur={0.5}>
            <div
              style={{
                marginTop: 20,
                fontFamily: F.display,
                fontStyle: "italic",
                fontWeight: 300,
                fontSize: data?.titre?.length > 22 ? 86 : 108,
                lineHeight: 1.04,
                letterSpacing: "-0.02em",
                color: NT.pale,
              }}
            >
              {nb(data.titre)}
            </div>
          </Allume>
          {data?.sous && (
            <Allume at={c0 + 0.45} dur={0.45}>
              <div style={{ marginTop: 12, fontFamily: NT.mono, fontSize: 34, color: NT.sodiumPale }}>
                {nb(data.sous)}
              </div>
            </Allume>
          )}
          <div style={{ marginTop: 46 }}>
            {lignes.map(([k, v], i) => (
              <Allume key={k} at={cue(cues, i + 1, c0 + 0.9 + i * 0.7)} dur={0.45} monte={10}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 20, marginBottom: 18 }}>
                  <span
                    style={{
                      fontFamily: NT.mono,
                      fontSize: 26,
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      color: NT.doux,
                      minWidth: 210,
                    }}
                  >
                    {k}
                  </span>
                  <span style={{ fontFamily: F.sans, fontWeight: 500, fontSize: 46, color: NT.pale }}>{nb(v)}</span>
                </div>
              </Allume>
            ))}
          </div>
        </div>
      </AbsoluteFill>
    </Nuit>
  );
};

/* ================================================================== */
/* 6. nt-titre: chapter card, the street lamp lights up behind it.     */
/*    data : { surtitre?, titre, sous? }                               */
/* ================================================================== */

export const NtTitre: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const c0 = cue(cues, 0, 0.1);
  const allume = ramp(t, c0, c0 + 0.9, easeOut);
  // the lamp does not light up at once: it hesitates, like a tube striking
  const papillote = allume * (t < c0 + 0.5 ? (rnd(Math.floor(t * 22)) > 0.42 ? 1 : 0.42) : 1);
  return (
    <Nuit allume={papillote} bouge={1.8} halos={[[960, 300, 860, 1.15], [250, 980, 430, 0.5]]}>
      <File y={1010} at={c0 + 0.55} duree={1.5} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", padding: "0 180px" }}>
        {data?.surtitre && (
          <div style={{ marginBottom: 40 }}>
            <Surtitre at={c0 + 0.25}>{data.surtitre}</Surtitre>
          </div>
        )}
        <Allume at={c0 + 0.35} dur={0.6} monte={20}>
          <div
            style={{
              fontFamily: F.display,
              fontStyle: "italic",
              fontWeight: 300,
              fontSize: data?.titre?.length > 26 ? 120 : 154,
              lineHeight: 1.02,
              letterSpacing: "-0.025em",
              color: NT.pale,
              textAlign: "center",
              textShadow: lueur(0.7 * papillote),
              textWrap: "balance",
            }}
          >
            {nb(data.titre)}
          </div>
        </Allume>
        {data?.sous && (
          <Allume at={c0 + 0.7} dur={0.5}>
            <div
              style={{
                marginTop: 38,
                fontFamily: NT.mono,
                fontSize: 36,
                letterSpacing: "0.08em",
                color: NT.doux,
                textAlign: "center",
              }}
            >
              {nb(data.sous)}
            </div>
          </Allume>
        )}
      </AbsoluteFill>
    </Nuit>
  );
};

/* ================================================================== */
/* OVERLAYS (alpha): placed over the speaker's face or over a photo.   */
/* All are anchored BY an edge (left or right), never by a            */
/* position computed from the text length.                            */
/* ================================================================== */

/* 7. nt-exif: the shooting data sheet placed in a corner.
      data : { expo:{pose,ouverture,iso,note}, surtitre?, left?, bottom?, right? } */
export const NtExif: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const c0 = cue(cues, 0, 0.05);
  const a = ramp(t, c0, c0 + 0.45, easeStd);
  const droite = typeof data?.right === "number";
  const ligne = !!data?.ligne;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          ...(droite ? { right: data.right } : { left: data?.left ?? 110 }),
          ...(typeof data?.top === "number" ? { top: data.top } : { bottom: data?.bottom ?? 150 }),
          padding: ligne ? "22px 32px" : "30px 38px",
          background: "rgba(8,11,20,0.82)",
          borderLeft: droite ? undefined : `4px solid ${NT.sodium}`,
          borderRight: droite ? `4px solid ${NT.sodium}` : undefined,
          boxShadow: "0 24px 70px rgba(0,0,0,0.55)",
          opacity: a,
          transform: `translateY(${(1 - a) * 14}px)`,
        }}
      >
        {data?.surtitre && !ligne && (
          <div
            style={{
              marginBottom: 16,
              fontFamily: F.sans,
              fontWeight: 500,
              fontSize: 26,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: NT.sodium,
            }}
          >
            {data.surtitre}
          </div>
        )}
        <Fiche expo={data.expo} at={c0 + 0.1} align={droite ? "right" : "left"} size={data?.size ?? 32} ligne={ligne} />
      </div>
    </AbsoluteFill>
  );
};

/* 8. nt-correction: what the speaker said, struck through; the right value next to it.
      Serves the deviations from the script found in the rough cut (a number, a name).
      data : { dit, juste, note?, left?, top? } ; cues: [0] the card, [1] the strike, [2] the right value */
export const NtCorrection: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const c0 = cue(cues, 0, 0.05);
  const c1 = cue(cues, 1, c0 + 0.5);
  const c2 = cue(cues, 2, c1 + 0.25);
  const a = ramp(t, c0, c0 + 0.4, easeStd);
  const barre = ramp(t, c1, c1 + 0.35, easeOut);
  const b = ramp(t, c2, c2 + 0.4, easeStd);
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: data?.left ?? 110,
          top: data?.top ?? 170,
          maxWidth: data?.w ?? 560,
          padding: "30px 36px",
          background: "rgba(8,11,20,0.86)",
          boxShadow: "0 26px 76px rgba(0,0,0,0.6)",
          opacity: a,
          transform: `translateY(${(1 - a) * 12}px)`,
        }}
      >
        <div style={{ position: "relative", display: "inline-block" }}>
          <div style={{ fontFamily: F.sans, fontWeight: 500, fontSize: 48, color: NT.doux }}>{nb(data.dit)}</div>
          <div
            style={{
              position: "absolute",
              left: -4,
              right: -4,
              top: "52%",
              height: 5,
              background: C.accent,
              transform: `scaleX(${barre})`,
              transformOrigin: "0 50%",
            }}
          />
        </div>
        <div style={{ opacity: b, transform: `translateY(${(1 - b) * 10}px)`, marginTop: 14 }}>
          <div
            style={{
              fontFamily: F.display,
              fontStyle: "italic",
              fontWeight: 300,
              fontSize: data?.size ?? 72,
              lineHeight: 1.05,
              color: NT.sodiumPale,
              textShadow: lueur(0.6),
            }}
          >
            {nb(data.juste)}
          </div>
          {data?.note && (
            <div style={{ marginTop: 12, fontFamily: NT.mono, fontSize: 28, color: NT.doux }}>{nb(data.note)}</div>
          )}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* 9. nt-note: a word or a number that lights up like a sign, and stays.
      data : { texte, sous?, left?, top?, size? } */
export const NtNote: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const c0 = cue(cues, 0, 0.05);
  const a = ramp(t, c0, c0 + 0.4, easeStd);
  const papillote = a * (t < c0 + 0.45 ? (rnd(Math.floor(t * 24)) > 0.38 ? 1 : 0.45) : 1);
  const size = data?.size ?? 76;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: data?.left ?? 110,
          top: data?.top ?? 240,
          maxWidth: data?.w ?? 620,
          // night background: placed over a bright photo, a sign without a background is unreadable
          ...(data?.fond === false
            ? {}
            : { padding: "26px 34px", background: `rgba(8,11,20,${0.84 * a})`, boxShadow: `0 24px 70px rgba(0,0,0,${0.5 * a})` }),
        }}
      >
        <div
          style={{
            fontFamily: F.display,
            fontStyle: "italic",
            fontWeight: 300,
            fontSize: size,
            lineHeight: 1.06,
            letterSpacing: "-0.02em",
            color: NT.pale,
            opacity: papillote,
            textShadow: lueur(0.85 * papillote),
            textWrap: "balance",
          }}
        >
          {nb(data.texte)}
        </div>
        {data?.sous && (
          <div
            style={{
              marginTop: 16,
              fontFamily: NT.mono,
              fontSize: size * 0.4,
              letterSpacing: "0.06em",
              color: NT.sodiumPale,
              opacity: ramp(t, c0 + 0.3, c0 + 0.65),
            }}
          >
            {nb(data.sous)}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
