import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { theme } from "../theme";

// Animated background for Tella-style edits: replaces the fixed gray gradient.
// A seamless loop of `periode` seconds: everything that moves is a periodic function
// of θ = 2π·t/periode (integer harmonics), so frame N equals frame 0.
//
// Three renders of the SAME background, aligned to the frame in Premiere:
//   mode "fond"  : the full-frame background (track V1, during movements and under the full-frame cam);
//   mode "ombre" : the background + the drop shadow of the cards of a layout (track V1, still shots);
//   mode "coins" : the "ombre" render reduced to the corners of each card outside the rounding, transparent
//                  elsewhere (track V4, above the cards, ProRes 4444): it is what rounds
//                  the cards. The rest of the image is transparent: light file.
// montage-tella.py places the loops in phase (entry point = clip start modulo the period).

export type Carte = [number, number, number, number]; // x0, y0, x1, y1 in canvas pixels

export type FondAnimeProps = {
  variante: "papier" | "nuit" | "brume";
  mode: "fond" | "ombre" | "coins";
  cartes: Carte[];
  rayon: number;
  periode: number; // secondes
  ondes: boolean;
};

export const fondAnimeDefaults: FondAnimeProps = {
  variante: "papier",
  mode: "fond",
  cartes: [],
  rayon: 40,
  periode: 20,
  ondes: true,
};

const C = theme.color;

type Tache = { x: number; y: number; r: number; ax: number; ay: number; m: number; n: number; ph: number; col: string };
type Palette = {
  base: string;
  taches: Tache[];
  trait: string;
  traitAccent: string;
  ombre: string;
  grain: number;
};

// x, y, r, ax, ay as fractions of the width; m, n harmonics (integers: seamless loop)
const PALETTES: Record<FondAnimeProps["variante"], Palette> = {
  papier: {
    base: `linear-gradient(160deg, #FAFAFA 0%, ${C.paperWarm} 45%, #E3E3E3 100%)`,
    taches: [
      { x: 0.12, y: 0.16, r: 0.46, ax: 0.08, ay: 0.05, m: 1, n: 1, ph: 0.0, col: "rgba(214,224,252,0.95)" },
      { x: 0.86, y: 0.82, r: 0.52, ax: 0.06, ay: 0.06, m: 1, n: 2, ph: 1.7, col: "rgba(208,208,214,0.9)" },
      { x: 0.66, y: 0.12, r: 0.34, ax: 0.08, ay: 0.04, m: 2, n: 1, ph: 3.1, col: "rgba(255,255,255,0.95)" },
      { x: 0.92, y: 0.3, r: 0.3, ax: 0.04, ay: 0.06, m: 1, n: 1, ph: 2.2, col: "rgba(47,91,234,0.16)" },
      { x: 0.26, y: 0.92, r: 0.32, ax: 0.06, ay: 0.03, m: 1, n: 1, ph: 4.4, col: "rgba(47,91,234,0.12)" },
    ],
    trait: "rgba(26,26,26,0.11)",
    traitAccent: "rgba(47,91,234,0.42)",
    ombre: "0 70px 160px rgba(28,28,36,0.30), 0 18px 40px rgba(28,28,36,0.16)",
    grain: 0.05,
  },
  nuit: {
    base: `linear-gradient(160deg, #262628 0%, ${C.darkBg} 50%, #0E0E0E 100%)`,
    taches: [
      { x: 0.2, y: 0.18, r: 0.45, ax: 0.07, ay: 0.05, m: 1, n: 1, ph: 0.0, col: "rgba(54,54,64,0.85)" },
      { x: 0.84, y: 0.8, r: 0.5, ax: 0.06, ay: 0.05, m: 1, n: 2, ph: 1.7, col: "rgba(47,91,234,0.16)" },
      { x: 0.6, y: 0.22, r: 0.34, ax: 0.08, ay: 0.04, m: 2, n: 1, ph: 3.1, col: "rgba(100,100,112,0.22)" },
      { x: 0.28, y: 0.88, r: 0.3, ax: 0.05, ay: 0.03, m: 1, n: 1, ph: 4.4, col: "rgba(30,63,176,0.14)" },
    ],
    trait: "rgba(255,255,255,0.08)",
    traitAccent: "rgba(47,91,234,0.45)",
    ombre: "0 80px 180px rgba(0,0,0,0.55), 0 20px 40px rgba(0,0,0,0.30)",
    grain: 0.06,
  },
  brume: {
    base: `linear-gradient(160deg, #E0E0E0 0%, #D0D0D0 50%, #C2C2C2 100%)`,
    taches: [
      { x: 0.18, y: 0.2, r: 0.42, ax: 0.07, ay: 0.05, m: 1, n: 1, ph: 0.0, col: "rgba(242,242,242,0.9)" },
      { x: 0.82, y: 0.78, r: 0.5, ax: 0.06, ay: 0.06, m: 1, n: 2, ph: 1.7, col: "rgba(160,160,168,0.7)" },
      { x: 0.62, y: 0.18, r: 0.36, ax: 0.08, ay: 0.04, m: 2, n: 1, ph: 3.1, col: "rgba(227,234,253,0.7)" },
      { x: 0.3, y: 0.86, r: 0.3, ax: 0.05, ay: 0.03, m: 1, n: 1, ph: 4.4, col: "rgba(47,91,234,0.12)" },
    ],
    trait: "rgba(26,26,26,0.09)",
    traitAccent: "rgba(47,91,234,0.38)",
    ombre: "0 70px 160px rgba(22,22,28,0.34), 0 18px 40px rgba(22,22,28,0.18)",
    grain: 0.05,
  },
};

const TAU = Math.PI * 2;

/** Waves: thin lines across the whole field, diagonal, undulating; two in the accent color.
 *  Whole field: the cards cover the center, the margins must show some. */
const Ondes: React.FC<{ th: number; W: number; H: number; pal: Palette }> = ({ th, W, H, pal }) => {
  const N = 16;
  const pts = 120;
  const paths: { d: string; accent: boolean }[] = [];
  for (let k = 0; k < N; k++) {
    const y0 = H * (-0.12 + k * 0.085);
    let d = "";
    for (let i = 0; i <= pts; i++) {
      const u = i / pts;
      const x = -0.05 * W + u * 1.1 * W;
      const pente = -0.28 * H * (u - 0.5); // the beam rises to the right
      const y =
        y0 +
        pente +
        H * 0.05 * Math.sin(TAU * (u * 1.1) + th + k * 0.38) +
        H * 0.02 * Math.sin(TAU * (u * 2.4) - 2 * th + k * 0.61) +
        H * 0.012 * Math.sin(TAU * (u * 0.55) + 3 * th + k * 1.1);
      d += `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    }
    paths.push({ d, accent: k === 3 || k === 11 });
  }
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
      {paths.map((p, i) => (
        <path
          key={i}
          d={p.d}
          fill="none"
          stroke={p.accent ? pal.traitAccent : pal.trait}
          strokeWidth={p.accent ? W / 1100 : W / 1500}
          strokeLinecap="round"
        />
      ))}
    </svg>
  );
};

/** The background alone, a function of θ (no Math.random): the same in both modes. */
const Fond: React.FC<{ th: number; W: number; H: number; pal: Palette; ondes: boolean }> = ({ th, W, H, pal, ondes }) => (
  <AbsoluteFill style={{ background: pal.base, overflow: "hidden" }}>
    {pal.taches.map((t, i) => {
      const cx = W * (t.x + t.ax * Math.sin(t.m * th + t.ph));
      const cy = W * (t.y * (H / W) + t.ay * Math.cos(t.n * th + t.ph * 0.7));
      const r = W * t.r * (1 + 0.06 * Math.sin(th + t.ph));
      return (
        <div
          key={i}
          style={{
            position: "absolute",
            left: cx - r,
            top: cy - r,
            width: 2 * r,
            height: 2 * r,
            borderRadius: "50%",
            background: `radial-gradient(circle at 50% 50%, ${t.col} 0%, transparent 70%)`,
          }}
        />
      );
    })}
    {ondes && <Ondes th={th} W={W} H={H} pal={pal} />}
    <Img
      src={staticFile("fond/grain.png")}
      style={{ position: "absolute", inset: 0, width: W, height: H, opacity: pal.grain, mixBlendMode: "multiply", objectFit: "cover" }}
    />
  </AbsoluteFill>
);

/** Mask of the frame mode: the corners of each card, minus the rounding. */
const masqueCoins = (cartes: Carte[], r: number, W: number, H: number) => {
  const carres = cartes
    .flatMap(([x0, y0, x1, y1]) => [
      [x0, y0],
      [x1 - r, y0],
      [x0, y1 - r],
      [x1 - r, y1 - r],
    ])
    .map(([x, y]) => `<rect x="${x}" y="${y}" width="${r}" height="${r}" fill="#000"/>`)
    .join("");
  const trous = cartes
    .map(([x0, y0, x1, y1]) => `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" rx="${r}" ry="${r}" fill="#000"/>`)
    .join("");
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">` +
    `<defs><mask id="m"><rect width="${W}" height="${H}" fill="#fff"/>${trous}</mask></defs>` +
    `<g mask="url(#m)">${carres}</g></svg>`;
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`;
};

const Ombres: React.FC<{ cartes: Carte[]; rayon: number; pal: Palette }> = ({ cartes, rayon, pal }) => (
  <>
    {cartes.map(([x0, y0, x1, y1], i) => (
      // box-shadow only draws outside the box: the inside stays the background
      <div
        key={i}
        style={{ position: "absolute", left: x0, top: y0, width: x1 - x0, height: y1 - y0, borderRadius: rayon, boxShadow: pal.ombre }}
      />
    ))}
  </>
);

export const FondAnime: React.FC<FondAnimeProps> = ({ variante, mode, cartes, rayon, periode, ondes }) => {
  const frame = useCurrentFrame();
  const { fps, width: W, height: H } = useVideoConfig();
  const n = Math.round(periode * fps);
  const th = (TAU * (frame % n)) / n;
  const pal = PALETTES[variante];
  const fond = <Fond th={th} W={W} H={H} pal={pal} ondes={ondes} />;
  if (mode === "fond") return fond;
  const ombre = (
    <AbsoluteFill>
      {fond}
      <Ombres cartes={cartes} rayon={rayon} pal={pal} />
    </AbsoluteFill>
  );
  if (mode === "ombre") return ombre;
  const masque = masqueCoins(cartes, rayon, W, H);
  return (
    <AbsoluteFill style={{ backgroundColor: "transparent" }}>
      <AbsoluteFill style={{ WebkitMaskImage: masque, maskImage: masque, WebkitMaskSize: "100% 100%" }}>{ombre}</AbsoluteFill>
    </AbsoluteFill>
  );
};
