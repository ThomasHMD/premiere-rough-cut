import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, Sequence, interpolate, staticFile, useVideoConfig } from "remotion";
import { clamp, easeOut, easeStd, nb, ramp, rnd, useT } from "./kit";
import { SceneProps } from "./opaque";

// "Green Matrix terminal" art direction for a video about reading a camera's firmware.
// Concept: the screen of an old camera switched back on. The phosphor green of a retro menu
// becomes the terminal where the device's software is read; running thread: the block cursor that writes each diagram.
// Rules: black and green only for the interface; the selection = solid green bar, black text (like the menu);
// real color only appears when it is the data (photo, hue wheel). JetBrains Mono everywhere (VT323 optional).
// All the content comes from `data`, all the moments from `cues` (seconds from the start of the scene).

export const MX = {
  noir: "#010805",
  fond: "#020E08",
  vert: "#19FF7F",
  moyen: "#12AA56",
  sombre: "#0A4A27",
  trait: "rgba(25,255,127,0.22)",
  pale: "#CCFFE2",
  lueur: "rgba(25,255,127,0.55)",
  mono: "JetBrains Mono, Menlo, monospace",
  vt: "VT323, JetBrains Mono, monospace",
};

export const cueMX = (cues: number[], i: number, fallback: number) => (typeof cues?.[i] === "number" ? cues[i] : fallback);

/** Phosphor glow on a green text. */
export const glow = (force = 1) => `0 0 ${6 * force}px ${MX.lueur}, 0 0 ${18 * force}px rgba(25,255,127,${0.18 * force})`;

/* ------------------------------------------------------------------ */
/* The background: black screen, very discreet character rain, sweep.  */
const PLUIE = "0123456789ABCDEF";
const Colonne: React.FC<{ x: number; i: number; t: number; h: number; force: number }> = ({ x, i, t, h, force }) => {
  const pas = 34;
  const n = 18 + Math.floor(rnd(i * 7.1) * 14);
  const vitesse = 40 + rnd(i * 3.3) * 70; // px/s, slow: decor, not spectacle
  const longueur = n * pas;
  const y0 = -longueur + ((t * vitesse + rnd(i * 9.7) * (h + longueur)) % (h + longueur));
  const chars: string[] = [];
  for (let k = 0; k < n; k++) {
    const change = Math.floor(t * (1.5 + rnd(i + k) * 3) + rnd(k * 13 + i) * 10);
    chars.push(PLUIE[Math.floor(rnd(i * 31 + k * 17 + change * 7.7) * PLUIE.length)]);
  }
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y0,
        width: pas,
        fontFamily: MX.mono,
        fontSize: 26,
        lineHeight: `${pas}px`,
        color: MX.vert,
        whiteSpace: "pre",
        textAlign: "center",
        opacity: force * (0.55 + 0.45 * rnd(i * 5.5)),
        WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, rgba(0,0,0,0.35) 45%, #000 100%)",
        maskImage: "linear-gradient(to bottom, transparent 0%, rgba(0,0,0,0.35) 45%, #000 100%)",
      }}
    >
      {chars.join("\n")}
    </div>
  );
};

/** Scan lines, vignetting, slight flicker of the tube. */
export const Tube: React.FC<{ balayage?: number }> = ({ balayage = 0.22 }) => {
  const t = useT();
  const flicker = 0.025 * (Math.sin(t * 47) * 0.5 + Math.sin(t * 13.7) * 0.5);
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <AbsoluteFill style={{ background: `repeating-linear-gradient(0deg, rgba(0,0,0,${balayage}) 0px, rgba(0,0,0,${balayage}) 2px, transparent 2px, transparent 4px)` }} />
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 50%, transparent 55%, rgba(0,0,0,0.6) 100%)" }} />
      <AbsoluteFill style={{ background: "#000", opacity: Math.max(0, flicker) }} />
    </AbsoluteFill>
  );
};

/** Full-screen background: green-black, rain (strength 0 to 1, 0.12 by default: it must never get in the way of reading), tube. */
export const FondMX: React.FC<{ children?: React.ReactNode; pluie?: number; balayage?: number }> = ({ children, pluie = 0.12, balayage }) => {
  const t = useT();
  const { width, height } = useVideoConfig();
  const cols = Math.ceil(width / 46);
  return (
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 45%, ${MX.fond} 0%, ${MX.noir} 75%)`, overflow: "hidden" }}>
      {pluie > 0 && (
        <AbsoluteFill style={{ filter: "blur(0.6px)" }}>
          {Array.from({ length: cols }, (_, i) => (rnd(i * 2.9) < 0.62 ? <Colonne key={i} i={i} x={i * 46 + 6} t={t} h={height} force={pluie} /> : null))}
        </AbsoluteFill>
      )}
      {children}
      <Tube balayage={balayage} />
    </AbsoluteFill>
  );
};

/* ------------------------------------------------------------------ */
/* Writing: the block cursor that types.                               */
/** Number of visible characters of a text typed at `cps` characters per second since `at`. */
export const signes = (t: number, at: number, s: string, cps = 30) => Math.max(0, Math.min(s.length, Math.floor((t - at) * cps)));
/** Moment when a text typed at `cps` is finished. */
export const finTape = (at: number, s: string, cps = 30) => at + s.length / cps;

export const Curseur: React.FC<{ t: number; actif?: boolean; couleur?: string; h?: string }> = ({ t, actif, couleur = MX.vert, h = "0.95em" }) => (
  <span
    style={{
      display: "inline-block",
      width: "0.58em",
      height: h,
      marginLeft: "0.06em",
      verticalAlign: "-0.12em",
      background: couleur,
      boxShadow: glow(0.8),
      opacity: actif || Math.floor(t * 2.2) % 2 === 0 ? 1 : 0,
    }}
  />
);

/** A text typed letter by letter, block cursor while typing (and after if `garder`). */
export const Tape: React.FC<{ texte: string; at: number; cps?: number; garder?: boolean; style?: React.CSSProperties }> = ({ texte, at, cps = 30, garder, style }) => {
  const t = useT();
  const s = nb(texte);
  const n = signes(t, at, s, cps);
  if (t < at) return <span style={style}>{garder ? <Curseur t={t} /> : null}</span>;
  const tape = n < s.length;
  return (
    <span style={style}>
      {s.slice(0, n)}
      {(tape || garder) && <Curseur t={t} actif={tape} />}
    </span>
  );
};

/** A number that "decodes": scrambled digits then the real value (duration `d`). */
export const decode = (t: number, at: number, valeur: string, d = 0.5) => {
  if (t < at) return "";
  if (t >= at + d) return valeur;
  const tick = Math.floor((t - at) * 30);
  const k = (t - at) / d;
  return [...valeur]
    .map((ch, i) => (/[0-9]/.test(ch) && i / valeur.length >= k ? String(Math.floor(rnd(tick * 7.3 + i * 11.1) * 10)) : ch))
    .join("");
};

/** Selection bar of the menu: solid green, black text, stretching from left to right starting at `at`. */
export const Selection: React.FC<{ at: number; children: React.ReactNode; style?: React.CSSProperties; pad?: string }> = ({ at, children, style, pad = "0.05em 0.3em" }) => {
  const t = useT();
  const k = ramp(t, at, at + 0.25, easeStd);
  return (
    <span style={{ position: "relative", display: "inline-block", padding: pad, ...style }}>
      <span style={{ position: "absolute", inset: 0, background: MX.vert, boxShadow: k > 0 ? glow(0.7) : undefined, transformOrigin: "left", transform: `scaleX(${k})` }} />
      <span style={{ position: "relative", color: k > 0.5 ? MX.noir : "inherit", textShadow: k > 0.5 ? "none" : undefined }}>{children}</span>
    </span>
  );
};

/** Terminal stamp (overlay, one video): the word in a selection bar, like the chosen entry of a retro menu.
 *  Lines separated by \n, each with its bar; JetBrains Mono bold; no rotation (box: zone_libre.tampon_dims). */
export const MxTampon: React.FC<{ at: number; text: string; size: number }> = ({ at, text, size }) => {
  const t = useT();
  const k = ramp(t, at - 0.12, at + 0.1, easeOut);
  return (
    <div style={{ fontFamily: MX.mono, fontWeight: 800, fontSize: size, lineHeight: 1.2, opacity: k, display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
      {nb(text).split("\n").map((l, i) => (
        <Selection key={i} at={at + i * 0.08} pad="0.04em 0.3em">{l}</Selection>
      ))}
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Diagram frame: terminal window, tab in reverse video.               */
const Coin: React.FC<{ c: string; k: number }> = ({ c, k }) => {
  const L = 34 * k;
  const pos: React.CSSProperties =
    c === "hg" ? { left: -4, top: -4, borderLeft: `4px solid ${MX.vert}`, borderTop: `4px solid ${MX.vert}` }
    : c === "hd" ? { right: -4, top: -4, borderRight: `4px solid ${MX.vert}`, borderTop: `4px solid ${MX.vert}` }
    : c === "bg" ? { left: -4, bottom: -4, borderLeft: `4px solid ${MX.vert}`, borderBottom: `4px solid ${MX.vert}` }
    : { right: -4, bottom: -4, borderRight: `4px solid ${MX.vert}`, borderBottom: `4px solid ${MX.vert}` };
  return <div style={{ position: "absolute", width: L, height: L, filter: `drop-shadow(0 0 6px ${MX.lueur})`, ...pos }} />;
};

/** Diagram window. `onglet` = title in reverse video; `chemin` = where the data comes from (on the right, in medium green);
 *  `pied` = help line at the bottom, like the menu. Opens at `at` (line that draws itself, tab that types itself). */
export const Fenetre: React.FC<{
  at?: number;
  onglet: string;
  chemin?: string;
  pied?: string;
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  children?: React.ReactNode;
}> = ({ at = 0, onglet, chemin, pied, x = 120, y = 110, w = 1680, h = 860, children }) => {
  const t = useT();
  const k = ramp(t, at, at + 0.45, easeOut);
  const kc = ramp(t, at + 0.1, at + 0.5, easeOut);
  const ongletAt = at + 0.25;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          border: `2px solid ${MX.moyen}`,
          background: "rgba(1,8,5,0.82)",
          clipPath: `inset(0 ${(1 - k) * 100}% ${(1 - k) * 100}% 0)`,
          boxShadow: `inset 0 0 60px rgba(25,255,127,0.05)`,
        }}
      />
      {["hg", "hd", "bg", "bd"].map((c) => <Coin key={c} c={c} k={kc} />)}
      <div style={{ position: "absolute", left: 32, top: -26, display: "flex", alignItems: "center", gap: 20, fontFamily: MX.mono, fontSize: 36, fontWeight: 800, letterSpacing: "0.04em" }}>
        <div style={{ background: MX.noir, padding: "0 14px" }}>
          <span style={{ display: "inline-block", background: t >= ongletAt ? MX.vert : "transparent", color: MX.noir, padding: "4px 18px", boxShadow: t >= ongletAt ? glow(0.8) : undefined }}>
            <Tape texte={onglet.toUpperCase()} at={ongletAt} cps={40} style={{ color: MX.noir }} />
          </span>
        </div>
      </div>
      {chemin && (
        <div style={{ position: "absolute", right: 36, top: -20, background: MX.noir, padding: "0 14px", fontFamily: MX.mono, fontSize: 28, color: MX.moyen, opacity: ramp(t, at + 0.5, at + 0.8) }}>
          {chemin}
        </div>
      )}
      <div style={{ position: "absolute", inset: "70px 64px 90px 64px" }}>{children}</div>
      {pied && (
        <div style={{ position: "absolute", left: 40, right: 40, bottom: 26, borderTop: `2px solid ${MX.sombre}`, paddingTop: 14, fontFamily: MX.mono, fontSize: 30, color: MX.moyen, opacity: ramp(t, at + 0.6, at + 1.0) }}>
          {nb(pied)}
        </div>
      )}
    </div>
  );
};

/** Scrolling terminal: lines arrive one by one (moments `ats`), the oldest ones rise and leave through the top
 *  when there are more than `max`. Each line starts with `>` (output) or `$` (command, typed). */
export const Defile: React.FC<{ lignes: string[]; ats: number[]; max?: number; taille?: number; interligne?: number; cps?: number }> = ({ lignes, ats, max = 9, taille = 40, interligne = 1.5, cps = 34 }) => {
  const t = useT();
  const pas = taille * interligne;
  const visibles = lignes.filter((_, i) => t >= (ats[i] ?? 99)).length;
  let decal = 0;
  for (let i = max; i < lignes.length; i++) decal += pas * ramp(t, ats[i] ?? 99, (ats[i] ?? 99) + 0.22, easeStd);
  return (
    <div style={{ position: "relative", height: max * pas, overflow: "hidden", fontFamily: MX.mono, fontSize: taille, lineHeight: `${pas}px` }}>
      <div style={{ transform: `translateY(${-decal}px)` }}>
        {lignes.map((l, i) => {
          const at = ats[i] ?? 99;
          if (t < at) return <div key={i} style={{ height: pas }} />;
          const cmd = l.startsWith("$ ");
          const corps = cmd ? l.slice(2) : l.replace(/^> ?/, "");
          const derniere = i === visibles - 1;
          return (
            <div key={i} style={{ whiteSpace: "pre", color: cmd ? MX.pale : MX.vert, textShadow: glow(cmd ? 0.6 : 0.8) }}>
              <span style={{ color: MX.moyen }}>{cmd ? "$ " : "> "}</span>
              {cmd ? <Tape texte={corps} at={at} cps={cps} garder={derniere} /> : nb(corps)}
            </div>
          );
        })}
      </div>
    </div>
  );
};

/* ================================================================== */
/* Test scene 1: chapter card.                                          */
/* data: { numero, total, titre, commande?, police?: "mono" | "vt" }   */
/* cues: [commande, titre]                                             */
export const MxChapitre: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const num: number = data?.numero ?? 1;
  const total: number = data?.total ?? 7;
  const titre: string = data?.titre ?? "";
  const cmd: string = data?.commande ?? `chapitre ${num}`;
  const police = data?.police === "vt" ? MX.vt : MX.mono;
  const a0 = cueMX(cues, 0, 0.3);
  const a1 = cueMX(cues, 1, finTape(a0, cmd, 34) + 0.25);
  const cpsTitre: number = data?.cpsTitre ?? 40;   // 40 and not 26: at 26 the title was still typing when the card ended
  const finTitre = finTape(a1, titre, cpsTitre);
  const vt = data?.police === "vt";
  return (
    <FondMX pluie={0.14}>
      <div style={{ position: "absolute", left: 170, top: 230, right: 170 }}>
        <div style={{ fontFamily: MX.mono, fontSize: 40, color: MX.pale, textShadow: glow(0.6), whiteSpace: "pre" }}>
          <span style={{ color: MX.moyen }}>$ </span>
          <Tape texte={cmd} at={a0} cps={34} garder={t < a1} />
        </div>
        <div style={{ marginTop: 44, display: "flex", alignItems: "center", gap: 26, opacity: t >= a1 - 0.05 ? 1 : 0 }}>
          <Selection at={a1 - 0.05} style={{ fontFamily: MX.mono, fontSize: 40, fontWeight: 800, letterSpacing: "0.08em" }} pad="6px 20px">
            {`CHAPITRE ${String(num).padStart(2, "0")} / ${String(total).padStart(2, "0")}`}
          </Selection>
          <div style={{ display: "flex", gap: 10 }}>
            {Array.from({ length: total }, (_, i) => {
              const on = i < num;
              const ki = ramp(t, a1 + 0.05 * i, a1 + 0.05 * i + 0.15);
              return <div key={i} style={{ width: 44, height: 26, border: `2px solid ${MX.moyen}`, background: on ? MX.vert : "transparent", opacity: ki, boxShadow: on ? glow(0.6) : undefined }} />;
            })}
          </div>
        </div>
        <div
          style={{
            marginTop: 54,
            fontFamily: police,
            fontSize: vt ? 128 : 92,
            fontWeight: vt ? 400 : 700,
            lineHeight: vt ? 1.0 : 1.18,
            letterSpacing: vt ? "0.01em" : "-0.01em",
            color: MX.vert,
            textShadow: glow(1.1),
            maxWidth: 1580,
            textWrap: "balance" as any,
          }}
        >
          <Tape texte={titre} at={a1 + 0.2} cps={cpsTitre} garder />
        </div>
        <div style={{ marginTop: 40, fontFamily: MX.mono, fontSize: 32, color: MX.moyen, opacity: ramp(t, finTitre + 0.3, finTitre + 0.7) }}>
          {data?.sous ? nb(data.sous) : ""}
        </div>
      </div>
    </FondMX>
  );
};

/* ================================================================== */
/* Test scene 2: the mix, a 3 × 3 matrix (two recipes).                */
/* data: { commande, chemin, gauche: {nom, m: 9 entiers}, droite: {nom, m}, echelle (512), note, pied,                     */
/*   entetes?: { capteur, image, colonnes: [3], lignes: [3] } (plain-language labels: "taken from the sensor: red green blue",    */
/*   "in the image: red = "), sommes?: false (no Σ column), legende? (under each grid), ecartsDesDeuxCotes? }    */
/* cues: [command, left matrix, right matrix, sums, note]; without sums: [command, left, right, gaps, note] */
type Entetes = { capteur?: string; image?: string; colonnes?: string[]; lignes?: string[] };
const Grille: React.FC<{ nom: string; m: number[]; at: number; atSomme: number; echelle: number; ecarts?: number[]; atEcart?: number; legendeEcart?: string; entetes?: Entetes; sommes?: boolean; legende?: string }> = ({ nom, m, at, atSomme, echelle, ecarts, atEcart = 99, legendeEcart = "", entetes, sommes = true, legende }) => {
  const t = useT();
  const entrees = ["R", "V", "B"];
  const clair = !!entetes;   // plain-language labels (proofreading): wider row-label column, smaller body
  const cell = { width: clair ? 150 : 158, textAlign: "right" as const };
  const wLig = clair ? 190 : 100;
  return (
    <div style={{ fontFamily: MX.mono, color: MX.vert }}>
      <div style={{ fontSize: 36, fontWeight: 700, marginBottom: clair ? 12 : 22, opacity: ramp(t, at - 0.2, at), textShadow: glow(0.6) }}>{nb(nom)}</div>
      {clair && entetes?.capteur && (
        <div style={{ display: "flex", fontSize: 26, color: MX.moyen, opacity: ramp(t, at - 0.1, at + 0.1) }}>
          <div style={{ width: wLig }} />
          <div style={{ width: cell.width * 3, textAlign: "center" }}>{nb(entetes.capteur)}</div>
        </div>
      )}
      <div style={{ display: "flex", alignItems: "baseline", fontSize: 30, color: MX.moyen, marginBottom: 8, opacity: ramp(t, at - 0.1, at + 0.1) }}>
        <div style={{ width: wLig, fontSize: clair ? 26 : 30 }}>{clair ? nb(entetes?.image ?? "") : "sortie"}</div>
        {entrees.map((e, c) => <div key={e} style={cell}>{clair ? nb(entetes?.colonnes?.[c] ?? e) : `${e} capt.`}</div>)}
        {sommes && <div style={{ ...cell, width: 150 }}>Σ</div>}
      </div>
      {entrees.map((sortie, r) => {
        const somme = m[r * 3] + m[r * 3 + 1] + m[r * 3 + 2];
        return (
          <div key={sortie} style={{ display: "flex", alignItems: "center", fontSize: clair ? 50 : 56, fontWeight: 700, height: 92, borderTop: `2px solid ${MX.sombre}` }}>
            <div style={{ width: wLig, fontSize: clair ? 30 : 40, color: MX.moyen, opacity: ramp(t, at, at + 0.1), whiteSpace: "nowrap" }}>{clair ? nb(entetes?.lignes?.[r] ?? sortie) : `${sortie} →`}</div>
            {[0, 1, 2].map((c) => {
              const i = r * 3 + c;
              const a = at + 0.12 * i;
              const fort = ecarts && ecarts.includes(i) && t >= atEcart;
              const v = decode(t, a, String(m[i]), 0.45);
              return (
                <div key={c} style={{ ...cell, textShadow: glow(0.8), color: MX.vert }}>
                  {fort ? <Selection at={atEcart + 0.08 * ecarts!.indexOf(i)} pad={clair ? "0.05em 0.15em" : undefined}>{v}</Selection> : v}
                </div>
              );
            })}
            {sommes && (
              <div style={{ ...cell, width: 150, fontSize: 46 }}>
                {t >= atSomme + 0.1 * r ? <Selection at={atSomme + 0.1 * r}>{String(somme)}</Selection> : null}
              </div>
            )}
          </div>
        );
      })}
      <div style={{ marginTop: 14, fontSize: clair ? 26 : 30, color: MX.moyen, opacity: ramp(t, at + 1.1, at + 1.4), whiteSpace: "nowrap" }}>
        {ecarts && t >= atEcart && legendeEcart ? nb(legendeEcart) : legende != null ? nb(legende) : `scale ${echelle}: ${echelle} = 1.0`}
      </div>
    </div>
  );
};

export const MxMatrice: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const cmd: string = data?.commande ?? "";
  const a0 = cueMX(cues, 0, 0.9);
  const a1 = cueMX(cues, 1, finTape(a0, cmd, 34) + 0.3);
  const a2 = cueMX(cues, 2, a1 + 1.4);
  const a3 = cueMX(cues, 3, a2 + 1.6);
  const a4 = cueMX(cues, 4, a3 + 0.9);
  const g = data?.gauche ?? { nom: "", m: [] };
  const d = data?.droite ?? { nom: "", m: [] };
  const echelle: number = data?.echelle ?? 512;
  const ecarts = (d.m as number[]).map((v, i) => [Math.abs(v - g.m[i]), i]).sort((a, b) => b[0] - a[0]).slice(0, data?.nEcarts ?? 2).map((x) => x[1]);
  // without a Σ column, the 4th cue is the gaps one (in bar on both sides: "14 becomes −153, 512 becomes 627")
  const sommes = data?.sommes !== false;
  const atSomme = sommes ? a3 : 99;
  const atEcart = sommes ? a4 + 0.4 : a3;
  const deux = !!data?.ecartsDesDeuxCotes;
  return (
    <FondMX pluie={0.08}>
      <Fenetre at={0} onglet={data?.onglet ?? "mix"} chemin={data?.chemin} pied={data?.pied}>
        <div style={{ fontFamily: MX.mono, fontSize: 38, color: MX.pale, textShadow: glow(0.6), whiteSpace: "pre", height: 60 }}>
          <span style={{ color: MX.moyen }}>$ </span>
          <Tape texte={cmd} at={a0} cps={34} garder={t < a1} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 40 }}>
          <Grille nom={g.nom} m={g.m} at={a1} atSomme={atSomme} echelle={echelle} entetes={data?.entetes} sommes={sommes} legende={data?.legende}
            ecarts={deux ? ecarts : undefined} atEcart={atEcart} />
          <div style={{ width: 2, background: MX.sombre, opacity: ramp(t, a2 - 0.3, a2) }} />
          <Grille nom={d.nom} m={d.m} at={a2} atSomme={atSomme} echelle={echelle} ecarts={ecarts} atEcart={atEcart} entetes={data?.entetes} sommes={sommes} legende={data?.legende}
            legendeEcart={data?.legendeEcart ?? "the biggest gaps from the reference"} />
        </div>
        <div style={{ marginTop: 36, fontFamily: MX.mono, fontSize: 38, color: MX.vert, textShadow: glow(0.8) }}>
          {t >= a4 && <><span style={{ color: MX.moyen }}>{"> "}</span><Tape texte={data?.note ?? ""} at={a4} cps={36} garder /></>}
        </div>
      </Fenetre>
    </FondMX>
  );
};

/* ================================================================== */
/* The switch to the user's art direction: the terminal screen turns off like */
/* a cathode-ray tube (the image collapses into a line, then a dot),    */
/* and the design system's paper appears behind it.                      */
/* data: { lignes: [string], papier?: false } (papier: the DS background  */
/*   appears behind; false when the face follows)                        */
/* cues: [extinction]                                                  */
export const MxExtinction: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const lignes: string[] = data?.lignes ?? ["$ publish --all", "> transfer complete"];
  const a = cueMX(cues, 0, 0.3 + lignes.length * 0.45 + 0.4);
  const ats = lignes.map((_, i) => 0.2 + i * 0.45);
  const ky = interpolate(t, [a, a + 0.18], [1, 0.006], { ...clamp, easing: easeStd });
  const kx = interpolate(t, [a + 0.16, a + 0.34], [1, 0.0], { ...clamp, easing: easeStd });
  const point = interpolate(t, [a + 0.3, a + 0.38, a + 0.6], [0, 1, 0], clamp);
  const papier = ramp(t, a + 0.45, a + 0.8, easeOut);
  const blanc = interpolate(t, [a, a + 0.18], [0, 0.8], clamp);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <AbsoluteFill style={{ transform: `scale(${kx}, ${ky})`, filter: `brightness(${1 + blanc * 2})`, opacity: kx > 0.01 ? 1 : 0 }}>
        <FondMX pluie={0.1}>
          <div style={{ position: "absolute", left: 170, top: 380, right: 170 }}>
            <Defile lignes={lignes} ats={ats} max={6} taille={52} />
          </div>
        </FondMX>
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 960 - 14, top: 540 - 14, width: 28, height: 28, borderRadius: 28, background: MX.pale, boxShadow: `0 0 40px 18px ${MX.lueur}`, opacity: point }} />
      {data?.papier !== false && <AbsoluteFill style={{ background: "#F2F2F2", opacity: papier }} />}
    </AbsoluteFill>
  );
};

/* ================================================================== */
/* Wheel of 16 sectors: retouching hue by hue.                          */
/* data: { onglet, chemin, roue (staticFile), noeuds: [16 angles °],   */
/*   etapes: [{ nom, commande, fleches: [[angle, cb0, cr0, cb1, cr1]] (radius 1 = edge of the wheel), sortie }], legende, pied, */
/*   numeros? (false: no numbers 0 to 15, as long as the voice has not explained them), cueNoeuds? (index of the cue where the */
/*   16 nodes come out one by one, at the pace of son.cascade: 0.08 s) }                                                      */
/* cues: [wheel, step 0, step 1, …]; the legend (of the arrows) comes in with the first step that has moving ones         */
const RoueSecteurs: React.FC<{ roue: string; noeuds: number[]; fleches?: number[][]; atRoue: number; atFleches: number; R: number; numeros?: boolean; atNoeuds?: number; pasNoeuds?: number }> = ({ roue, noeuds, fleches, atRoue, atFleches, R, numeros = true, atNoeuds, pasNoeuds = 0.05 }) => {
  const t = useT();
  const kr = ramp(t, atRoue, atRoue + 0.6, easeOut);
  const D = 2 * R;
  const pad = 70;
  return (
    <div style={{ position: "relative", width: D + 2 * pad, height: D + 2 * pad }}>
      <Img src={staticFile(roue)} style={{ position: "absolute", left: pad, top: pad, width: D, height: D, clipPath: `circle(${kr * 50}% at 50% 50%)`, opacity: 0.92 }} />
      <svg width={D + 2 * pad} height={D + 2 * pad} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        <circle cx={R + pad} cy={R + pad} r={R} fill="none" stroke={MX.moyen} strokeWidth={2} opacity={kr} />
        {noeuds.map((a, k) => {
          const at = (atNoeuds ?? atRoue + 0.4) + k * pasNoeuds;
          const kk = ramp(t, at, at + 0.25, easeOut);
          const th = (a * Math.PI) / 180;
          const x = R + pad + Math.cos(th) * R * (1 + 0.04);
          const y = R + pad - Math.sin(th) * R * (1 + 0.04);
          const xt = R + pad + Math.cos(th) * (R + 38);
          const yt = R + pad - Math.sin(th) * (R + 38);
          return (
            <g key={k} opacity={kk}>
              <line x1={R + pad} y1={R + pad} x2={x} y2={y} stroke={MX.noir} strokeOpacity={0.55} strokeWidth={3} />
              <line x1={R + pad + Math.cos(th) * R * 0.97} y1={R + pad - Math.sin(th) * R * 0.97} x2={x} y2={y} stroke={MX.vert} strokeWidth={4} />
              {numeros && (
                <text x={xt} y={yt + 11} textAnchor="middle" fontFamily={MX.mono} fontWeight={700} fontSize={30} fill={MX.vert} style={{ filter: `drop-shadow(0 0 4px ${MX.lueur})` }}>
                  {k}
                </text>
              )}
            </g>
          );
        })}
        {(fleches ?? []).map((f, i) => {
          const [, cb0, cr0, cb1, cr1] = f;
          const at = atFleches + (i / Math.max(1, (fleches ?? []).length)) * 0.9;
          const k = ramp(t, at, at + 0.35, easeOut);
          const x0 = R + pad + cb0 * R, y0 = R + pad - cr0 * R;
          const x1f = R + pad + cb1 * R, y1f = R + pad - cr1 * R;
          const x1 = x0 + (x1f - x0) * k, y1 = y0 + (y1f - y0) * k;
          const ang = Math.atan2(y1 - y0, x1 - x0);
          const L = Math.hypot(x1 - x0, y1 - y0);
          return (
            <g key={i} opacity={ramp(t, at - 0.05, at)}>
              <line x1={x0} y1={y0} x2={x1} y2={y1} stroke={MX.noir} strokeWidth={7} strokeLinecap="round" />
              <line x1={x0} y1={y0} x2={x1} y2={y1} stroke={MX.pale} strokeWidth={3.5} strokeLinecap="round" />
              <circle cx={x0} cy={y0} r={5} fill={MX.pale} stroke={MX.noir} strokeWidth={2} />
              {L > 8 && [150, -150].map((da) => (
                <line key={da} x1={x1} y1={y1} x2={x1 + 13 * Math.cos(ang + (da * Math.PI) / 180)} y2={y1 + 13 * Math.sin(ang + (da * Math.PI) / 180)} stroke={MX.pale} strokeWidth={3.5} strokeLinecap="round" />
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
};

export const MxSecteurs: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const etapes: { nom: string; commande?: string; fleches?: number[][]; sortie?: string }[] = data?.etapes ?? [];
  const aRoue = cueMX(cues, 0, 0.6);
  const ats = etapes.map((_, i) => cueMX(cues, 1 + i, aRoue + 1.6 + i * 2.6));
  const actif = Math.max(0, ats.filter((a) => t >= a).length - 1);
  const e = etapes[actif];
  const bouge = etapes.findIndex((x) => (x.fleches ?? []).some((f) => Math.hypot(f[3] - f[1], f[4] - f[2]) > 1e-3));
  const aLeg = ats[bouge >= 0 ? bouge : 0] ?? 99;
  const aNoeuds = typeof data?.cueNoeuds === "number" ? cueMX(cues, data.cueNoeuds, aRoue + 0.4) : undefined;
  const lignes: string[] = [];
  const latLignes: number[] = [];
  etapes.forEach((et, i) => {
    if (et.commande) { lignes.push(`$ ${et.commande}`); latLignes.push(ats[i]); }
    if (et.sortie) { lignes.push(`> ${et.sortie}`); latLignes.push(ats[i] + 0.25 + (et.commande ?? "").length / 34); }
  });
  return (
    <FondMX pluie={0.06}>
      <Fenetre at={0} onglet={data?.onglet ?? "hue by hue"} chemin={data?.chemin} pied={data?.pied}>
        <div style={{ display: "flex", gap: 40, alignItems: "flex-start", marginTop: -30 }}>
          <RoueSecteurs roue={data?.roue ?? "scenes/332/roue.png"} noeuds={data?.noeuds ?? []} fleches={t >= ats[actif] ? e?.fleches : undefined} atRoue={aRoue} atFleches={ats[actif] + 0.2} R={data?.rayon ?? 260}
            numeros={data?.numeros ?? true} atNoeuds={aNoeuds} pasNoeuds={aNoeuds != null ? 0.08 : 0.05} />
          <div style={{ flex: 1, paddingTop: 40 }}>
            <div style={{ fontFamily: MX.mono, fontSize: 46, fontWeight: 800, minHeight: 70, color: MX.vert, textShadow: glow(0.9) }}>
              {t >= (ats[0] ?? 99) && e ? <Selection at={ats[actif]} pad="4px 18px">{nb(e.nom)}</Selection> : null}
            </div>
            <div style={{ height: 30 }} />
            <Defile lignes={lignes} ats={latLignes} max={7} taille={32} interligne={1.45} />
            <div style={{ marginTop: 20, fontFamily: MX.mono, fontSize: 28, lineHeight: 1.45, color: MX.moyen, opacity: ramp(t, aLeg + 1.2, aLeg + 1.6) }}>
              {(data?.legende ?? []).map((l: string, i: number) => <div key={i}>{nb(l)}</div>)}
            </div>
          </div>
        </div>
      </Fenetre>
    </FondMX>
  );
};

/* ================================================================== */
/* A recipe = three tables: the mix, the curve, the sectors.            */
/* data: { onglet, chemin, commande, matrice: 9 entiers, nMatrices, courbe: [256 valeurs], courbeMax, courbeN,     */
/*   courbeRef?: [256] (reference, dotted), roue, noeuds, fleches, titres: [3], sous: [3], note, pied,            */
/*   focus? (index of the panel that keeps its bar from the note on: only one thing lit at a time) }          */
/* cues: [command, mix, curve, sectors, note]                           */
export const MxTables: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const cmd: string = data?.commande ?? "";
  const a0 = cueMX(cues, 0, 0.8);
  const a1 = cueMX(cues, 1, finTape(a0, cmd, 34) + 0.3);
  const a2 = cueMX(cues, 2, a1 + 1.6);
  const a3 = cueMX(cues, 3, a2 + 1.8);
  const a4 = cueMX(cues, 4, a3 + 2.0);
  const titres: string[] = data?.titres ?? ["1. The mix", "2. The curve", "3. The sectors"];
  const sous: string[] = data?.sous ?? [];
  const titreLong = Math.max(...titres.map((x) => x.length)) > 17;   // "3. Hue by hue" does not fit in 38 in 470 px
  const m: number[] = data?.matrice ?? [];
  const courbe: number[] = data?.courbe ?? [];
  const ref: number[] | undefined = data?.courbeRef;
  const cmax: number = data?.courbeMax ?? 4095;
  const W = 430, H = 330;
  const path = (c: number[], k: number) => {
    const n = Math.max(2, Math.floor(c.length * k));
    return c.slice(0, n).map((v, i) => `${i === 0 ? "M" : "L"}${((i / (c.length - 1)) * W).toFixed(1)} ${(H - (v / cmax) * H).toFixed(1)}`).join(" ");
  };
  const Panneau: React.FC<{ at: number; i: number; children: React.ReactNode }> = ({ at, i, children }) => (
    <div style={{ width: 470, opacity: ramp(t, at - 0.15, at + 0.1) }}>
      <div style={{ fontFamily: MX.mono, fontSize: titreLong ? 33 : 38, fontWeight: 800, height: 58, whiteSpace: "nowrap" }}>
        {t >= at && (typeof data?.focus !== "number" || t < a4 || i === data.focus
          ? <Selection at={at} pad="2px 14px">{titres[i]}</Selection>
          : <span style={{ color: MX.moyen, padding: "2px 14px" }}>{titres[i]}</span>)}
      </div>
      <div style={{ height: 380, marginTop: 14, border: `2px solid ${MX.sombre}`, display: "flex", alignItems: "center", justifyContent: "center", position: "relative", overflow: "hidden" }}>{children}</div>
      <div style={{ marginTop: 14, fontFamily: MX.mono, fontSize: 30, color: MX.moyen, minHeight: 80, opacity: ramp(t, at + 0.6, at + 0.9) }}>{nb(sous[i] ?? "")}</div>
    </div>
  );
  return (
    <FondMX pluie={0.06}>
      <Fenetre at={0} onglet={data?.onglet ?? "a recipe"} chemin={data?.chemin} pied={data?.pied}>
        <div style={{ fontFamily: MX.mono, fontSize: 38, color: MX.pale, textShadow: glow(0.6), whiteSpace: "pre", height: 56 }}>
          <span style={{ color: MX.moyen }}>$ </span>
          <Tape texte={cmd} at={a0} cps={34} garder={t < a1} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 24 }}>
          <Panneau at={a1} i={0}>
            <div style={{ fontFamily: MX.mono, fontWeight: 700, fontSize: 44, color: MX.vert, textShadow: glow(0.8), display: "grid", gridTemplateColumns: "repeat(3, 120px)", rowGap: 18, textAlign: "right" }}>
              {m.map((v, i) => <div key={i}>{decode(t, a1 + 0.1 + i * 0.07, String(v), 0.4)}</div>)}
            </div>
          </Panneau>
          <Panneau at={a2} i={1}>
            <svg width={W} height={H} style={{ overflow: "visible" }}>
              {[0.25, 0.5, 0.75].map((g) => <line key={g} x1={g * W} y1={0} x2={g * W} y2={H} stroke={MX.sombre} strokeWidth={1.5} />)}
              {[0.25, 0.5, 0.75].map((g) => <line key={`h${g}`} x1={0} y1={g * H} x2={W} y2={g * H} stroke={MX.sombre} strokeWidth={1.5} />)}
              {ref && <path d={path(ref, ramp(t, a2 + 0.2, a2 + 1.0))} fill="none" stroke={MX.moyen} strokeWidth={3} strokeDasharray="8 8" />}
              <path d={path(courbe, ramp(t, a2 + 0.3, a2 + 1.3, easeStd))} fill="none" stroke={MX.vert} strokeWidth={5} style={{ filter: `drop-shadow(0 0 6px ${MX.lueur})` }} />
            </svg>
          </Panneau>
          <Panneau at={a3} i={2}>
            <div style={{ transform: "scale(0.62)", transformOrigin: "50% 50%", marginTop: -8 }}>
              <RoueSecteurs roue={data?.roue ?? "scenes/332/roue.png"} noeuds={data?.noeuds ?? []} fleches={data?.fleches} atRoue={a3} atFleches={a3 + 0.8} R={250} numeros={false} />
            </div>
          </Panneau>
        </div>
        <div style={{ marginTop: 6, fontFamily: MX.mono, fontSize: 36, color: MX.vert, textShadow: glow(0.8) }}>
          {t >= a4 && <><span style={{ color: MX.moyen }}>{"> "}</span><Tape texte={data?.note ?? ""} at={a4} cps={36} garder /></>}
        </div>
      </Fenetre>
    </FondMX>
  );
};

/* ================================================================== */
/* Image panels (before / after, contact sheets, screenshots).          */
/* data: { onglet, chemin, commande, panneaux: [{ src, ratio (l/h), titre, sous?, valeur?, pixel? }], hauteurMax?, */
/*   note?, mention? (bottom right corner, e.g. "look modeling powered by <tool>"), pied? }                          */
/* cues: [command, one moment per panel…, values, note]           */
/* Each image draws itself from top to bottom, like a screen sweep.     */
export const MxPanneaux: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const cmd: string = data?.commande ?? "";
  const pans: { src: string; ratio: number; titre?: string; sous?: string; valeur?: string; pixel?: boolean; echelle?: number; video?: boolean }[] = data?.panneaux ?? [];
  const { fps } = useVideoConfig();
  const a0 = cueMX(cues, 0, 0.8);
  const ats = pans.map((_, i) => cueMX(cues, 1 + i, (cmd ? finTape(a0, cmd, 34) + 0.3 : a0) + i * 0.9));
  const aVal = cueMX(cues, 1 + pans.length, (ats[pans.length - 1] ?? 1) + 1.0);
  const aNote = cueMX(cues, 2 + pans.length, aVal + 0.9);
  const largeur = 1552;
  const gap = 36;
  const hMax: number = data?.hauteurMax ?? (cmd ? 470 : 540);
  const somme = pans.reduce((s, p) => s + p.ratio * (p.echelle ?? 1), 0);
  const h = Math.min(hMax, (largeur - gap * (pans.length - 1)) / somme);
  return (
    <FondMX pluie={0.06}>
      <Fenetre at={0} onglet={data?.onglet ?? "image"} chemin={data?.chemin} pied={data?.pied}>
        {cmd && (
          <div style={{ fontFamily: MX.mono, fontSize: 38, color: MX.pale, textShadow: glow(0.6), whiteSpace: "pre", height: 56 }}>
            <span style={{ color: MX.moyen }}>$ </span>
            <Tape texte={cmd} at={a0} cps={34} garder={t < (ats[0] ?? 99)} />
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "center", alignItems: "flex-end", gap, marginTop: cmd ? 22 : 10 }}>
          {pans.map((p, i) => {
            const at = ats[i];
            const k = ramp(t, at, at + 0.55, easeStd);
            const hp = h * (p.echelle ?? 1);
            const w = hp * p.ratio;
            return (
              <div key={i} style={{ width: w }}>
                <div style={{ fontFamily: MX.mono, fontSize: 36, fontWeight: 800, height: 54, whiteSpace: "nowrap", opacity: ramp(t, at - 0.1, at + 0.1) }}>
                  {p.titre && t >= at && <Selection at={at} pad="2px 14px">{nb(p.titre)}</Selection>}
                </div>
                <div style={{ position: "relative", width: w, height: hp, marginTop: 12, border: `2px solid ${MX.moyen}`, background: MX.noir, boxSizing: "content-box" }}>
                  {p.video ? (
                    // video (phone held upright): it starts when its panel enters, without sound
                    <Sequence from={Math.round(at * fps)} layout="none">
                      <OffthreadVideo src={staticFile(p.src)} muted style={{ width: w, height: hp, objectFit: "contain", display: "block", clipPath: `inset(0 0 ${(1 - k) * 100}% 0)` }} />
                    </Sequence>
                  ) : (
                    <Img src={staticFile(p.src)} style={{ width: w, height: hp, objectFit: "contain", display: "block", imageRendering: p.pixel ? "pixelated" : "auto", clipPath: `inset(0 0 ${(1 - k) * 100}% 0)` }} />
                  )}
                  {k > 0 && k < 1 && <div style={{ position: "absolute", left: 0, right: 0, top: k * hp - 2, height: 4, background: MX.pale, boxShadow: glow(1.2) }} />}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12, minHeight: 56 }}>
                  <div style={{ fontFamily: MX.mono, fontSize: 28, color: MX.moyen, opacity: ramp(t, at + 0.4, at + 0.7) }}>{nb(p.sous ?? "")}</div>
                  {p.valeur && (
                    <div style={{ fontFamily: MX.mono, fontSize: 44, fontWeight: 800, color: MX.vert, textShadow: glow(0.9) }}>
                      {t >= aVal + 0.1 * i ? <Selection at={aVal + 0.1 * i} pad="0 14px">{decode(t, aVal + 0.1 * i, p.valeur, 0.45)}</Selection> : null}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {data?.note && (
          // hanging indent: a long note (mandatory mention) wraps under its text, not under the ">"
          <div style={{ marginTop: 18, fontFamily: MX.mono, fontSize: 36, color: MX.vert, textShadow: glow(0.8), paddingLeft: "2ch", textIndent: "-2ch" }}>
            {t >= aNote && <><span style={{ color: MX.moyen }}>{"> "}</span><Tape texte={data.note} at={aNote} cps={36} garder /></>}
          </div>
        )}
      </Fenetre>
      {data?.mention && (
        <div style={{ position: "absolute", right: 140, bottom: 34, fontFamily: MX.mono, fontSize: 24, color: MX.moyen, opacity: ramp(t, 0.6, 1.0) }}>{data.mention}</div>
      )}
    </FondMX>
  );
};

/* ================================================================== */
/* The emulator: the camera's screens drawn by its real software.       */
/* data: { onglet, chemin, ecrans: [{ src, duree (s), touche? }], legende? }  (screenshots 640 × 480 or 1280 × 960, enlarged with sharp pixels) */
/* cues: [screen 0, screen 1, …] (otherwise: end to end according to `duree`)    */
export const MxEmulateur: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const ecrans: { src: string; duree?: number; touche?: string }[] = data?.ecrans ?? [];
  const debuts: number[] = [];
  let acc = 0.6;
  ecrans.forEach((e, i) => { debuts.push(cueMX(cues, i, acc)); acc = debuts[i] + (e.duree ?? 1.6); });
  const i = Math.max(0, debuts.filter((d) => t >= d).length - 1);
  const e = ecrans[i];
  const flash = t >= debuts[i] && t < debuts[i] + 0.07 && i > 0;
  const allume = ramp(t, 0.15, 0.5, easeOut);
  const H = 780, W = (H * 4) / 3;
  const lignes = ecrans.map((x) => (x.touche ? `$ ${x.touche}` : "")).filter(Boolean);
  const ats = ecrans.map((x, j) => (x.touche ? debuts[j] - 0.05 : -1)).filter((a) => a >= 0);
  return (
    <FondMX pluie={0.05}>
      <div style={{ position: "absolute", left: 110, top: 150, width: W + 60, height: H + 60, borderRadius: 34, background: "#0B0F0D", border: `2px solid ${MX.sombre}`, boxShadow: "0 30px 80px rgba(0,0,0,0.6)" }}>
        <div style={{ position: "absolute", left: 30, top: 30, width: W, height: H, background: "#000", overflow: "hidden" }}>
          {e && (
            <Img src={staticFile(e.src)} style={{ width: W, height: H, imageRendering: "pixelated", opacity: allume * (flash ? 0.55 : 1), transform: `scaleY(${0.02 + 0.98 * allume})` }} />
          )}
          <AbsoluteFill style={{ background: "repeating-linear-gradient(0deg, rgba(0,0,0,0.18) 0px, rgba(0,0,0,0.18) 1px, transparent 1px, transparent 3px)" }} />
        </div>
      </div>
      <div style={{ position: "absolute", left: 110, top: 70, fontFamily: MX.mono, fontSize: 36, fontWeight: 800 }}>
        <Selection at={0.2} pad="2px 14px">{(data?.onglet ?? "emulator").toUpperCase()}</Selection>
        <span style={{ marginLeft: 22, fontSize: 28, fontWeight: 400, color: MX.moyen }}>{data?.chemin ?? ""}</span>
      </div>
      <div style={{ position: "absolute", left: W + 230, top: 170, right: 90 }}>
        <Defile lignes={lignes} ats={ats} max={11} taille={34} interligne={1.5} />
        <div style={{ marginTop: 30, fontFamily: MX.mono, fontSize: 28, lineHeight: 1.45, color: MX.moyen }}>
          {(data?.legende ?? []).map((l: string, j: number) => <div key={j}>{nb(l)}</div>)}
        </div>
      </div>
    </FondMX>
  );
};

/* ================================================================== */
/* Flow diagram: linked boxes, drawn along the voice.                   */
/* data: { onglet, chemin, commande?, colonnes (boxes per row, 3 by default), noeuds: [{ titre, texte?, etat?: "alerte" | "ok" | "clef" }], */
/*   liens?: [[from, to, label?]] (otherwise: each box to the next one), note?, pied? }                                                       */
/* cues: [command, one box…, note]                                     */
export const MxFlux: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const cmd: string = data?.commande ?? "";
  const noeuds: { titre: string; texte?: string; etat?: string }[] = data?.noeuds ?? [];
  const cols: number = data?.colonnes ?? 3;
  const a0 = cueMX(cues, 0, 0.8);
  const ats = noeuds.map((_, i) => cueMX(cues, 1 + i, (cmd ? finTape(a0, cmd, 34) + 0.3 : a0) + i * 1.1));
  const aNote = cueMX(cues, 1 + noeuds.length, (ats[noeuds.length - 1] ?? 1) + 1.2);
  const rangs = Math.ceil(noeuds.length / cols);
  const zoneW = 1552, zoneH = (cmd ? 560 : 620) - (data?.note ? 70 : 0);
  const gx = 110, gy = 70;
  const bw = (zoneW - gx * (cols - 1)) / cols;
  const bh = Math.min(240, (zoneH - gy * (rangs - 1)) / rangs);
  const pos = noeuds.map((_, i) => {
    const r = Math.floor(i / cols);
    const c = r % 2 === 0 || !data?.serpent ? i % cols : cols - 1 - (i % cols);
    return { x: c * (bw + gx), y: r * (bh + gy) };
  });
  const liens: [number, number, string?][] = data?.liens ?? noeuds.slice(1).map((_, i) => [i, i + 1] as [number, number]);
  return (
    <FondMX pluie={0.06}>
      <Fenetre at={0} onglet={data?.onglet ?? "diagram"} chemin={data?.chemin} pied={data?.pied}>
        {cmd && (
          <div style={{ fontFamily: MX.mono, fontSize: 38, color: MX.pale, textShadow: glow(0.6), whiteSpace: "pre", height: 56 }}>
            <span style={{ color: MX.moyen }}>$ </span>
            <Tape texte={cmd} at={a0} cps={34} garder={t < (ats[0] ?? 99)} />
          </div>
        )}
        <div style={{ position: "relative", width: zoneW, height: zoneH, marginTop: cmd ? 30 : 10 }}>
          <svg width={zoneW} height={zoneH} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
            {liens.map(([a, b, lib], j) => {
              const A = pos[a], B = pos[b];
              if (!A || !B) return null;
              const at = ats[b] - 0.25;
              const k = ramp(t, at, at + 0.35, easeStd);
              let x1, y1, x2, y2;
              if (Math.abs(A.y - B.y) < 1) { const g = B.x > A.x; x1 = A.x + (g ? bw : 0); y1 = A.y + bh / 2; x2 = B.x + (g ? 0 : bw); y2 = B.y + bh / 2; }
              else { x1 = A.x + bw / 2; y1 = A.y + bh; x2 = B.x + bw / 2; y2 = B.y; }
              const xe = x1 + (x2 - x1) * k, ye = y1 + (y2 - y1) * k;
              const ang = Math.atan2(y2 - y1, x2 - x1);
              return (
                <g key={j}>
                  <line x1={x1} y1={y1} x2={xe} y2={ye} stroke={MX.vert} strokeWidth={4} style={{ filter: `drop-shadow(0 0 5px ${MX.lueur})` }} />
                  {k > 0.95 && [150, -150].map((da) => <line key={da} x1={x2} y1={y2} x2={x2 + 18 * Math.cos(ang + (da * Math.PI) / 180)} y2={y2 + 18 * Math.sin(ang + (da * Math.PI) / 180)} stroke={MX.vert} strokeWidth={4} />)}
                  {lib && (Math.abs(x1 - x2) < 1
                    ? <text x={x1 + 16} y={(y1 + y2) / 2 + 9} textAnchor="start" fontFamily={MX.mono} fontSize={26} fill={MX.moyen} opacity={k}>{lib}</text>
                    : <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 14} textAnchor="middle" fontFamily={MX.mono} fontSize={26} fill={MX.moyen} opacity={k}>{lib}</text>)}
                </g>
              );
            })}
          </svg>
          {noeuds.map((n, i) => {
            const at = ats[i];
            const k = ramp(t, at, at + 0.3, easeOut);
            const alerte = n.etat === "alerte";
            const clef = n.etat === "clef";
            const clign = alerte && t > at + 0.4 ? (Math.floor((t - at) * 3) % 2 === 0 ? 1 : 0.35) : 1;
            return (
              <div key={i} style={{ position: "absolute", left: pos[i].x, top: pos[i].y, width: bw, height: bh, boxSizing: "border-box", border: `${clef || alerte ? 4 : 2}px ${alerte ? "dashed" : "solid"} ${clef || alerte ? MX.vert : MX.moyen}`, background: "rgba(1,8,5,0.9)", padding: "18px 24px", clipPath: `inset(0 ${(1 - k) * 100}% 0 0)`, boxShadow: clef ? `0 0 24px ${MX.lueur}` : undefined }}>
                <div style={{ fontFamily: MX.mono, fontSize: 38, fontWeight: 800, color: MX.vert, textShadow: glow(0.8), opacity: clign, lineHeight: 1.15 }}>
                  {clef || alerte ? <Selection at={at + 0.2} pad="0 10px">{nb(n.titre)}</Selection> : nb(n.titre)}
                </div>
                {n.texte && <div style={{ marginTop: 12, fontFamily: MX.mono, fontSize: 29, lineHeight: 1.35, color: MX.pale, opacity: 0.85 * ramp(t, at + 0.3, at + 0.6) }}>{nb(n.texte)}</div>}
              </div>
            );
          })}
        </div>
        {data?.note && (
          <div style={{ marginTop: 16, fontFamily: MX.mono, fontSize: 36, color: MX.vert, textShadow: glow(0.8) }}>
            {t >= aNote && <><span style={{ color: MX.moyen }}>{"> "}</span><Tape texte={data.note} at={aNote} cps={36} garder /></>}
          </div>
        )}
      </Fenetre>
    </FondMX>
  );
};

/* ================================================================== */
/* A picture profile: what it contains, its size, where it goes.       */
/* data: { onglet, chemin, commande, champs: [{ nom, valeur, plage? }], lut: number[] (0 to 32767), courbeTitre?, courbeSous?, */
/*   octets: [{ n, lib }] (the chunks of the block, to scale), total?, emplacements: [string], actif (index), statut?, note?, pied? } */
/* cues: [command, fields, curve, block, slots, note]                   */
/* On the left the settings typed line by line, in the middle the custom curve, on the right the nine slots of the camera; below, */
/* the block sent over USB, chunk by chunk. The selection bar lands on the slot written.                        */
export const MxPictureControl: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const cmd: string = data?.commande ?? "";
  const champs: { nom: string; valeur: string; plage?: string }[] = data?.champs ?? [];
  const lut: number[] = data?.lut ?? [];
  const octets: { n: number; lib: string }[] = data?.octets ?? [];
  const emp: string[] = data?.emplacements ?? [];
  const actif: number = data?.actif ?? 0;
  const a0 = cueMX(cues, 0, 0.8);
  const aChamps = cueMX(cues, 1, cmd ? finTape(a0, cmd, 34) + 0.3 : a0);
  const aCourbe = cueMX(cues, 2, aChamps + champs.length * 0.32 + 0.3);
  const aBloc = cueMX(cues, 3, aCourbe + 1.5);
  const aEmp = cueMX(cues, 4, aBloc + 1.4);
  const aNote = cueMX(cues, 5, aEmp + 1.8);
  // custom curve: 257 values on 15 bits, drawn from left to right, dotted reference diagonal
  const CW = 360, CH = 280;
  const kC = ramp(t, aCourbe, aCourbe + 1.1, easeStd);
  const pts = lut.map((v, i) => `${((i / (lut.length - 1)) * CW).toFixed(1)},${(CH - (v / 32767) * CH).toFixed(1)}`).join(" ");
  const total = octets.reduce((s, o) => s + o.n, 0) || 1;
  const BW = 1552;
  return (
    <FondMX pluie={0.06}>
      <Fenetre at={0} onglet={data?.onglet ?? "Picture Control"} chemin={data?.chemin} pied={data?.pied}>
        {cmd && (
          <div style={{ fontFamily: MX.mono, fontSize: 38, color: MX.pale, textShadow: glow(0.6), whiteSpace: "pre", height: 56 }}>
            <span style={{ color: MX.moyen }}>$ </span>
            <Tape texte={cmd} at={a0} cps={34} garder={t < aChamps} />
          </div>
        )}
        <div style={{ display: "flex", gap: 56, marginTop: 24, alignItems: "flex-start" }}>
          {/* the settings */}
          <div style={{ width: 620 }}>
            {champs.map((c, i) => {
              const a = aChamps + i * 0.32;
              return (
                <div key={i} style={{ display: "flex", alignItems: "baseline", height: 46, fontFamily: MX.mono, opacity: ramp(t, a - 0.05, a + 0.1) }}>
                  <div style={{ width: 200, flexShrink: 0, fontSize: 30, color: MX.moyen }}>{nb(c.nom)}</div>
                  <div style={{ width: 300, flexShrink: 0, fontSize: 32, fontWeight: 800, color: MX.vert, textShadow: glow(0.8), whiteSpace: "nowrap" }}>{t >= a ? decode(t, a, c.valeur, 0.35) : ""}</div>
                  <div style={{ fontSize: 24, color: MX.moyen, opacity: 0.8, whiteSpace: "nowrap" }}>{nb(c.plage ?? "")}</div>
                </div>
              );
            })}
          </div>
          {/* the custom curve */}
          <div style={{ width: CW, opacity: ramp(t, aCourbe - 0.1, aCourbe + 0.1) }}>
            <div style={{ fontFamily: MX.mono, fontSize: 32, fontWeight: 800, height: 50 }}>
              {t >= aCourbe && <Selection at={aCourbe} pad="2px 12px">{nb(data?.courbeTitre ?? "custom curve")}</Selection>}
            </div>
            <svg width={CW} height={CH} style={{ display: "block", marginTop: 8, border: `2px solid ${MX.sombre}`, overflow: "visible" }}>
              {[0.25, 0.5, 0.75].map((g) => <line key={g} x1={g * CW} y1={0} x2={g * CW} y2={CH} stroke={MX.sombre} strokeWidth={1} />)}
              {[0.25, 0.5, 0.75].map((g) => <line key={`h${g}`} x1={0} y1={g * CH} x2={CW} y2={g * CH} stroke={MX.sombre} strokeWidth={1} />)}
              <line x1={0} y1={CH} x2={CW} y2={0} stroke={MX.moyen} strokeWidth={2} strokeDasharray="8 8" />
              <polyline points={pts} fill="none" stroke={MX.vert} strokeWidth={5} pathLength={1} strokeDasharray={`${kC} 1`} style={{ filter: `drop-shadow(0 0 6px ${MX.lueur})` }} />
            </svg>
            <div style={{ marginTop: 8, fontFamily: MX.mono, fontSize: 24, color: MX.moyen, whiteSpace: "nowrap", opacity: ramp(t, aCourbe + 0.6, aCourbe + 0.9) }}>{nb(data?.courbeSous ?? "")}</div>
          </div>
          {/* the nine slots of the camera */}
          <div style={{ flex: 1 }}>
            {emp.map((e, i) => {
              const a = aEmp + i * 0.07;
              const on = i === actif && t >= aEmp + 0.9;
              return (
                <div key={i} style={{ height: 38, fontFamily: MX.mono, fontSize: 28, fontWeight: on ? 800 : 400, color: MX.pale, opacity: ramp(t, a, a + 0.15) * (on ? 1 : 0.75), whiteSpace: "nowrap" }}>
                  {on ? <Selection at={aEmp + 0.9} pad="0 10px">{nb(e)}</Selection> : nb(e)}
                </div>
              );
            })}
            {data?.statut && (
              <div style={{ marginTop: 10, fontFamily: MX.mono, fontSize: 28, color: MX.vert, textShadow: glow(0.6), whiteSpace: "nowrap" }}>
                {t >= aEmp + 1.1 && <Tape texte={data.statut} at={aEmp + 1.1} cps={36} garder={false} />}
              </div>
            )}
          </div>
        </div>
        {/* the block sent over USB (absent without `octets`: no empty frame) */}
        {octets.length > 0 && <div style={{ marginTop: 18, opacity: ramp(t, aBloc - 0.1, aBloc + 0.1) }}>
          <div style={{ display: "flex", width: BW, height: 54, border: `2px solid ${MX.moyen}`, boxSizing: "border-box" }}>
            {octets.map((o, i) => {
              const a = aBloc + i * 0.45;
              const k = ramp(t, a, a + 0.5, easeStd);
              const w = (o.n / total) * (BW - 4);
              return (
                <div key={i} style={{ position: "relative", width: w, height: "100%", borderLeft: i ? `2px solid ${MX.noir}` : undefined }}>
                  <div style={{ position: "absolute", inset: 0, width: `${k * 100}%`, background: i % 2 ? MX.moyen : MX.vert, boxShadow: glow(0.6) }} />
                </div>
              );
            })}
          </div>
          <div style={{ display: "flex", width: BW, marginTop: 10, fontFamily: MX.mono, fontSize: 28, color: MX.pale }}>
            {octets.map((o, i) => {
              const a = aBloc + i * 0.45 + 0.3;
              return (
                <div key={i} style={{ width: i === octets.length - 1 ? undefined : Math.max(420, (o.n / total) * BW), flex: i === octets.length - 1 ? 1 : undefined, opacity: ramp(t, a, a + 0.2), whiteSpace: "nowrap" }}>
                  <span style={{ color: MX.vert, fontWeight: 800 }}>{nb(String(o.n))}</span> {nb(o.lib)}
                </div>
              );
            })}
            {data?.total && <div style={{ fontWeight: 800, color: MX.vert, textShadow: glow(0.7), opacity: ramp(t, aBloc + octets.length * 0.45 + 0.3, aBloc + octets.length * 0.45 + 0.5), whiteSpace: "nowrap" }}>{nb(data.total)}</div>}
          </div>
        </div>}
        {data?.note && (
          <div style={{ marginTop: 18, fontFamily: MX.mono, fontSize: 32, color: MX.vert, textShadow: glow(0.8), whiteSpace: "nowrap" }}>
            {t >= aNote && <><span style={{ color: MX.moyen }}>{"> "}</span><Tape texte={data.note} at={aNote} cps={38} garder /></>}
          </div>
        )}
      </Fenetre>
    </FondMX>
  );
};


/* ================================================================== */
/* Terminal that writes its lines one by one, each on its word.         */
/* data: { onglet, chemin?, lignes: ["$ typed command", "> output", …], selection?: [indices], pied? }                 */
/* cues: [one line…, selection]  (the chosen lines switch to a solid selection bar, like the menu entry)    */
export const MxTerminal: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const lignes: string[] = data?.lignes ?? [];
  const ats = lignes.map((_, i) => cueMX(cues, i, 0.6 + i * 0.9));
  const sel: number[] = data?.selection ?? [];
  const aSel = cueMX(cues, lignes.length, 99);
  const taille = lignes.length > 8 ? 40 : 46;
  const pas = Math.round(taille * 1.5);
  return (
    <FondMX pluie={0.08}>
      <Fenetre at={0} onglet={data?.onglet ?? "terminal"} chemin={data?.chemin} pied={data?.pied}>
        <div style={{ fontFamily: MX.mono, fontSize: taille, lineHeight: `${pas}px`, marginTop: 6 }}>
          {lignes.map((l, i) => {
            const at = ats[i];
            if (t < at) return <div key={i} style={{ height: pas }} />;
            const cmd = l.startsWith("$ ");
            const corps = cmd ? l.slice(2) : l.replace(/^> ?/, "");
            const derniere = ats.filter((a) => t >= a).length - 1 === i;
            const choisie = sel.includes(i) && t >= aSel;
            return (
              <div key={i} style={{ whiteSpace: "pre", color: cmd ? MX.pale : MX.vert, textShadow: glow(cmd ? 0.6 : 0.8), fontWeight: choisie ? 800 : 400 }}>
                <span style={{ color: MX.moyen }}>{cmd ? "$ " : "> "}</span>
                {cmd ? <Tape texte={corps} at={at} cps={34} garder={derniere} />
                  : choisie ? <Selection at={aSel + 0.08 * sel.indexOf(i)} pad="0 12px">{nb(corps)}</Selection>
                  : <Tape texte={corps} at={at} cps={70} garder={derniere} />}
              </div>
            );
          })}
        </div>
      </Fenetre>
    </FondMX>
  );
};

/* ================================================================== */
/* Measurement curve drawn along the voice (probe, sensitivities, a film's data sheet).                                       */
/* data: { onglet, chemin?, commande?, axeX, axeY, x: [min, max], y: [min, max], graduationsX, unite,                    */
/*   series: [{ nom, points: [[x, y]…], style: "trait" | "points", couleur?: "rouge" | "vert" | "bleu" }],                 */
/*   noeuds?: [x…] (thin vertical lines), spectre?: bool (band of wavelengths), note?, pied? }                     */
/* cues: [command, drawing, note]. Without `spectre`, a band of hues (Cb/Cr angle) runs under the axis when the unit is "°". */
const longueurOnde = (nm: number) => {
  // approximate color of a wavelength (the real color is the data here)
  let r = 0, g = 0, b = 0;
  if (nm < 440) { r = -(nm - 440) / 60; b = 1; } else if (nm < 490) { g = (nm - 440) / 50; b = 1; } else if (nm < 510) { g = 1; b = -(nm - 510) / 20; }
  else if (nm < 580) { r = (nm - 510) / 70; g = 1; } else if (nm < 645) { r = 1; g = -(nm - 645) / 65; } else { r = 1; }
  const f = nm < 420 ? 0.3 + (0.7 * (nm - 380)) / 40 : nm > 700 ? 0.3 + (0.7 * (780 - nm)) / 80 : 1;
  const c = (v: number) => Math.round(255 * Math.pow(Math.max(0, Math.min(1, v * f)), 0.8));
  return `rgb(${c(r)},${c(g)},${c(b)})`;
};
const teinteCbCr = (deg: number) => {
  const a = (deg * Math.PI) / 180, cb = 0.12 * Math.cos(a), cr = 0.12 * Math.sin(a);
  const c = (v: number) => Math.round(255 * Math.max(0, Math.min(1, v)));
  return `rgb(${c(0.5 + 1.402 * cr)},${c(0.5 - 0.344136 * cb - 0.714136 * cr)},${c(0.5 + 1.772 * cb)})`;
};
const COULEURS: Record<string, string> = { rouge: "#FF4A4A", vert: MX.vert, bleu: "#4A8BFF" };

export const MxCourbes: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const cmd: string = data?.commande ?? "";
  const a0 = cueMX(cues, 0, 0.6);
  const aTrace = cueMX(cues, 1, (cmd ? finTape(a0, cmd, 34) : a0) + 0.4);
  const aNote = cueMX(cues, 2, aTrace + 2.4);
  const [x0, x1]: number[] = data?.x ?? [0, 1];
  const [y0, y1]: number[] = data?.y ?? [0, 1];
  const series: { nom: string; points: number[][]; style?: string; couleur?: string }[] = data?.series ?? [];
  const W = 1420, H = data?.note ? 400 : 450, G = 90;
  const sx = (x: number) => G + ((x - x0) / (x1 - x0)) * (W - G);
  const sy = (y: number) => H - ((y - y0) / (y1 - y0)) * H;
  const DUREE = 1.6;   // the line sweeps the axis in 1.6 s; each following series starts 0.35 s later
  const front = (i: number) => x0 + (x1 - x0) * ramp(t, aTrace + i * 0.35, aTrace + i * 0.35 + DUREE, easeStd);
  const unite: string = data?.unite ?? "";
  const bande = data?.spectre ? longueurOnde : unite === "°" ? teinteCbCr : null;
  const kAxes = ramp(t, cmd ? finTape(a0, cmd, 34) : 0.3, (cmd ? finTape(a0, cmd, 34) : 0.3) + 0.4);
  return (
    <FondMX pluie={0.05}>
      <Fenetre at={0} onglet={data?.onglet ?? "mesure"} chemin={data?.chemin} pied={data?.pied}>
        {cmd && (
          <div style={{ fontFamily: MX.mono, fontSize: 38, color: MX.pale, textShadow: glow(0.6), whiteSpace: "pre", height: 56 }}>
            <span style={{ color: MX.moyen }}>$ </span>
            <Tape texte={cmd} at={a0} cps={34} garder={t < aTrace} />
          </div>
        )}
        <div style={{ position: "relative", height: H + 120, marginTop: 64 }}>
          <svg width={W + 40} height={H + 110} style={{ position: "absolute", left: 0, top: 0, overflow: "visible", opacity: kAxes }}>
            {[0, 0.5, 1].map((f) => <line key={f} x1={G} x2={W} y1={sy(y0 + f * (y1 - y0))} y2={sy(y0 + f * (y1 - y0))} stroke={MX.trait} strokeWidth={2} />)}
            {(data?.noeuds ?? []).map((v: number, j: number) => <line key={j} x1={sx(v)} x2={sx(v)} y1={0} y2={H} stroke={MX.moyen} strokeWidth={2} strokeDasharray="6 8" />)}
            <line x1={G} x2={G} y1={0} y2={H} stroke={MX.moyen} strokeWidth={3} />
            <line x1={G} x2={W} y1={H} y2={H} stroke={MX.moyen} strokeWidth={3} />
            {bande && Array.from({ length: 180 }, (_, k) => {
              const v = x0 + ((k + 0.5) / 180) * (x1 - x0);
              return <rect key={k} x={sx(x0 + (k / 180) * (x1 - x0))} y={H + 12} width={(W - G) / 180 + 1} height={16} fill={bande(v)} />;
            })}
            {(data?.graduationsX ?? []).map((v: number) => (
              <text key={v} x={sx(v)} y={H + (bande ? 64 : 44)} textAnchor="middle" fontFamily={MX.mono} fontSize={26} fill={MX.moyen}>{`${v}${unite === "°" ? "°" : ""}`}</text>
            ))}
            <text x={W} y={H + (bande ? 100 : 82)} textAnchor="end" fontFamily={MX.mono} fontSize={26} fill={MX.pale}>{data?.axeX ?? ""}</text>
            <text x={G - 16} y={-16} textAnchor="start" fontFamily={MX.mono} fontSize={26} fill={MX.pale}>{data?.axeY ?? ""}</text>
            {series.map((s, i) => {
              const f = front(i);
              const col = s.couleur ? COULEURS[s.couleur] ?? MX.vert : s.style === "points" ? MX.vert : series.some((z) => z.style === "points") ? MX.pale : MX.vert;
              const vis = s.points.filter((p) => p[0] <= f);
              if (s.style === "points") {
                return <g key={i}>{vis.map((p, j) => <circle key={j} cx={sx(p[0])} cy={sy(p[1])} r={6} fill={col} style={{ filter: `drop-shadow(0 0 4px ${MX.lueur})` }} />)}</g>;
              }
              if (vis.length < 2) return null;
              const d = vis.map((p, j) => `${j ? "L" : "M"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ");
              return <path key={i} d={d} fill="none" stroke={col} strokeWidth={series.some((z) => z.style === "points") ? 3 : 5} strokeLinejoin="round" style={{ filter: `drop-shadow(0 0 6px ${col})` }} />;
            })}
          </svg>
          <div style={{ position: "absolute", right: 0, top: -6, display: "flex", gap: 34, fontFamily: MX.mono, fontSize: 26, color: MX.pale }}>
            {series.length > 1 && series.map((s, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, opacity: ramp(t, aTrace + i * 0.35, aTrace + i * 0.35 + 0.3) }}>
                <span style={{ display: "inline-block", width: 26, height: s.style === "points" ? 12 : 5, borderRadius: s.style === "points" ? 6 : 0, background: s.couleur ? COULEURS[s.couleur] : s.style === "points" ? MX.vert : MX.pale }} />
                {nb(s.nom)}
              </div>
            ))}
          </div>
        </div>
        {data?.note && (
          <div style={{ fontFamily: MX.mono, fontSize: 36, color: MX.vert, textShadow: glow(0.8) }}>
            {t >= aNote && <><span style={{ color: MX.moyen }}>{"> "}</span><Tape texte={data.note} at={aNote} cps={36} garder /></>}
          </div>
        )}
      </Fenetre>
    </FondMX>
  );
};

/* ================================================================== */
/* The hook: the views taken out of the camera, full frame, the name of the preset in a selection bar.                     */
/* data: { vues: [{ src, ratio, titre }], legende? }   cues: [one view…]  (hard cut from one view to the next, 2-frame flash) */
export const MxVues: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const vues: { src: string; ratio: number; titre?: string }[] = data?.vues ?? [];
  const ats = vues.map((_, i) => cueMX(cues, i, 0.2 + i * 2.5));
  const i = Math.max(0, ats.filter((a) => t >= a).length - 1);
  const v = vues[i];
  const k = ramp(t, ats[0], ats[0] + 0.45, easeStd);
  const eclair = i > 0 && t >= ats[i] && t < ats[i] + 2 / 30;
  const Hm = 900, Wm = 1720;
  const h = Math.min(Hm, Wm / (v?.ratio ?? 1.5)), w = h * (v?.ratio ?? 1.5);
  return (
    <FondMX pluie={0.04}>
      {v && (
        <div style={{ position: "absolute", left: (1920 - w) / 2, top: (1080 - h) / 2 + 20, width: w, height: h, border: `2px solid ${MX.moyen}`, boxShadow: `0 0 30px rgba(25,255,127,0.25)` }}>
          <Img src={staticFile(v.src)} style={{ width: w, height: h, objectFit: "cover", display: "block", clipPath: `inset(0 0 ${(1 - k) * 100}% 0)` }} />
          {k > 0 && k < 1 && <div style={{ position: "absolute", left: 0, right: 0, top: k * h - 2, height: 4, background: MX.pale, boxShadow: glow(1.2) }} />}
          {v.titre && t >= ats[i] + 0.1 && (
            <div style={{ position: "absolute", left: -2, top: -64, fontFamily: MX.mono, fontSize: 40, fontWeight: 800, whiteSpace: "nowrap" }}>
              <Selection at={ats[i] + 0.1} pad="4px 18px">{nb(v.titre)}</Selection>
            </div>
          )}
          {data?.legende && (
            <div style={{ position: "absolute", right: 0, bottom: -44, fontFamily: MX.mono, fontSize: 26, color: MX.moyen, opacity: ramp(t, ats[0] + 0.4, ats[0] + 0.8) }}>{nb(data.legende)}</div>
          )}
        </div>
      )}
      {eclair && <AbsoluteFill style={{ background: MX.vert, opacity: 0.18 }} />}
    </FondMX>
  );
};
