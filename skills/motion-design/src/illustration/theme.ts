// Kit theme: colors, fonts, sizes, margins. This is WHERE you set your own graphic identity
// (README, "Setting up your brand"). The scenes read these values; the fonts are loaded
// from public/fonts/ by scenes/kit.tsx and compositions/*.tsx (identical family names).

export const theme = {
  color: {
    base: "#FFFFFF",
    contrast: "#1A1A1A",
    inkSoft: "#4A4A4A",
    muted: "#6B6B6B",
    surface: "#F5F5F5",
    line: "#E5E5E5",
    accent: "#2F5BEA",
    accentDark: "#1E3FB0",
    accentWash: "#E3EAFD",
    darkBg: "#1A1A1A",
    paperWarm: "#F2F2F2",
  },
  font: {
    display: "Source Serif, Inter, Georgia, serif", // Inter as a fallback: Source Serif has no ≈, ≠ or arrows
    sans: "Inter, sans-serif",
    mono: "Courier Prime, Courier New, monospace",
  },
  // 1920×1080 scale: ~2.5× the web sizes of the design system to stay readable in 1080p YouTube
  size: {
    hero: 192,
    h1: 128,
    h2: 80,
    h3: 56,
    body: 44,
    lead: 52,
    meta: 32,
    eyebrow: 28,
    caption: 28,
  },
  weight: {
    light: 300,
    regular: 400,
    medium: 500,
    bold: 700,
  },
  ls: {
    heading: "-0.01em",
    headingTight: "-0.015em",
    button: "0.02em",
    eyebrow: "0.12em",
    caption: "0.01em",
  },
  motion: {
    // durations in frames @ 60fps (Remotion default)
    fast: 9,
    base: 15,
    slow: 24,
  },
  // Inner full-screen margins 1920×1080
  layout: {
    padH: 140,
    padV: 160,
    safeWidth: 1920 - 280,
    safeHeight: 1080 - 320,
  },
} as const;
