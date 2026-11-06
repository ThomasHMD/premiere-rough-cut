import React from "react";
import { AbsoluteFill } from "remotion";
import { C, Check, Eyebrow, F, Paper, Rise, easeStd, nb, ramp, shadow, useSpringAt, useT } from "./kit";
import { Footer, SceneProps, StampMark, Title, UrlPill } from "./opaque";

// Overlay graphics for the offer of a video ("Reveal and offer" and conclusion), in the user's design system: the
// video switches out of the green terminal (scene `mx-extinction` of matrix.tsx) at the moment the speaker gives everything away. Data contract
// at the top of each component, content in `data`, moments in `cues` (seconds from the start of the scene). No logo.

const cue = (cues: number[], i: number, fallback: number) => (typeof cues?.[i] === "number" ? cues[i] : fallback);

/* ================================================================== */
/* What I give, device by device.                                      */
/* data: { eyebrow, titre, boitiers: [{ nom, meta, items: [string] }], methode: { titre, texte }, tampon, licence } */
/* cues: [one moment per device…, method, stamp, license]               */
/* Left column: the devices, like a table of contents; the one being discussed turns black. On the right, its list,   */
/* ticked line by line (body 46: readable on a phone). The method arrives last, large, then the stamp.     */
export const OffreBoitiers: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const boitiers: { nom: string; meta?: string; items: string[] }[] = data?.boitiers ?? [];
  const n = boitiers.length;
  const ats = boitiers.map((_, i) => cue(cues, i, 0.6 + i * 2.6));
  const aMethode = cue(cues, n, (ats[n - 1] ?? 0) + 2.6);
  const aTampon = cue(cues, n + 1, aMethode + 1.6);
  const aLicence = cue(cues, n + 2, aTampon + 0.9);
  const actif = t >= aMethode ? n : Math.max(0, ats.filter((a) => t >= a).length - 1);
  const kMethode = ramp(t, aMethode, aMethode + 0.55, easeStd);
  return (
    <Paper drift={1}>
      <AbsoluteFill style={{ padding: "96px 120px 0" }}>
        <Rise at={0.05}>
          <Eyebrow>{data?.eyebrow ?? "Free, in full"}</Eyebrow>
        </Rise>
        <div style={{ height: 10 }} />
        <Title at={0.12} size={78}>{nb(data?.titre ?? "Everything I showed you")}</Title>
        <div style={{ height: 50 }} />
        <div style={{ display: "flex", gap: 56, alignItems: "flex-start" }}>
          {/* table of contents of the devices */}
          <div style={{ width: 470, display: "flex", flexDirection: "column", gap: 18 }}>
            {boitiers.map((b, i) => {
              const s = sp(ats[i] - 0.25, { damping: 15, stiffness: 170 });
              const on = i === actif && t < aMethode;
              const fait = t >= ats[i] && !on;
              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "20px 28px",
                    borderRadius: 16,
                    background: on ? C.contrast : "#FFFFFF",
                    boxShadow: shadow,
                    transform: `translateX(${(1 - s) * -60}px)`,
                    opacity: Math.min(1, s * 1.6) * (t >= aMethode ? 1 - 0.45 * kMethode : 1),
                  }}
                >
                  <div>
                    <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 44, color: on ? C.paperWarm : C.contrast }}>{nb(b.nom)}</div>
                    {b.meta && <div style={{ fontFamily: F.sans, fontSize: 28, letterSpacing: "0.02em", marginTop: 2, color: on ? "rgba(242,242,242,0.7)" : C.muted }}>{nb(b.meta)}</div>}
                  </div>
                  {fait && <Check at={ats[i + 1] ?? aMethode} size={44} />}
                </div>
              );
            })}
          </div>
          {/* list of the current device, then the method */}
          <div style={{ position: "relative", flex: 1, height: 560 }}>
            {boitiers.map((b, i) => {
              if (i !== actif) return null;
              const k = ramp(t, ats[i], ats[i] + 0.4, easeStd);
              return (
                <div key={i} style={{ position: "absolute", inset: 0, transform: `translateY(${(1 - k) * 40}px)`, opacity: k }}>
                  {b.items.map((it, j) => {
                    const a = ats[i] + 0.35 + j * (data?.pas ?? 0.45);
                    return (
                      <div key={j} style={{ display: "flex", alignItems: "center", gap: 22, minHeight: 92, borderBottom: `2px solid ${C.line}`, opacity: ramp(t, a - 0.1, a + 0.15) }}>
                        <Check at={a} size={50} />
                        <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 46, lineHeight: 1.12, color: C.contrast }}>{nb(it)}</div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
            {t >= aMethode && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  borderRadius: 22,
                  background: C.contrast,
                  boxShadow: shadow,
                  padding: "56px 64px",
                  boxSizing: "border-box",
                  transform: `translateY(${(1 - kMethode) * 60}px) scale(${0.94 + 0.06 * kMethode})`,
                  opacity: kMethode,
                }}
              >
                <Eyebrow color={C.accent} size={30}>{data?.methode?.surtitre ?? "And above all"}</Eyebrow>
                <div style={{ height: 18 }} />
                <div style={{ fontFamily: F.display, fontStyle: "italic", fontSize: 92, lineHeight: 1.04, color: C.paperWarm }}>{nb(data?.methode?.titre ?? "The method")}</div>
                <div style={{ height: 26 }} />
                <div style={{ fontFamily: F.sans, fontSize: 44, lineHeight: 1.3, color: "rgba(242,242,242,0.86)", maxWidth: 900, textWrap: "balance" as any }}>{nb(data?.methode?.texte ?? "")}</div>
              </div>
            )}
          </div>
        </div>
      </AbsoluteFill>
      {t >= aTampon - 0.05 && (
        <div style={{ position: "absolute", right: 150, top: 120 }}>
          <StampMark at={aTampon} text={data?.tampon ?? "Free"} size={92} rotate={-8} />
        </div>
      )}
      <div style={{ position: "absolute", left: 120, bottom: 60, fontFamily: F.sans, fontSize: 30, letterSpacing: "0.02em", color: C.inkSoft, opacity: ramp(t, aLicence, aLicence + 0.4) }}>
        {nb(data?.licence ?? "")}
      </div>
      <Footer url={false} />
    </Paper>
  );
};

/* ================================================================== */
/* The link in the description: three steps.                             */
/* data: { eyebrow, titre, url, etapes: [{ titre, texte }] }           */
/* cues: [address, step 1, step 2, step 3]                             */
export const OffreLien: React.FC<SceneProps> = ({ data, cues }) => {
  const t = useT();
  const sp = useSpringAt();
  const etapes: { titre: string; texte?: string }[] = data?.etapes ?? [];
  const aUrl = cue(cues, 0, 0.5);
  return (
    <Paper drift={1}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", padding: "0 120px" }}>
        <Rise at={0.05}>
          <Eyebrow>{data?.eyebrow ?? "The link is in the description"}</Eyebrow>
        </Rise>
        <div style={{ height: 12 }} />
        <Title at={0.12} size={80} style={{ textAlign: "center" }}>{nb(data?.titre ?? "")}</Title>
        <div style={{ height: 46 }} />
        <UrlPill at={aUrl} size={42} url={data?.url ?? "example.com/free-guide"} />
        <div style={{ height: 70 }} />
        <div style={{ display: "flex", gap: 40 }}>
          {etapes.map((e, i) => {
            const a = cue(cues, 1 + i, aUrl + 1.2 + i * 0.9);
            const s = sp(a, { damping: 13, stiffness: 180 });
            return (
              <div
                key={i}
                style={{
                  width: 470,
                  minHeight: 250,
                  borderRadius: 20,
                  background: "#FFFFFF",
                  boxShadow: shadow,
                  padding: "34px 38px",
                  boxSizing: "border-box",
                  transform: `translateY(${(1 - s) * 70}px)`,
                  opacity: Math.min(1, s * 1.6),
                }}
              >
                <div style={{ fontFamily: F.display, fontStyle: "italic", fontWeight: 300, fontSize: 96, lineHeight: 0.9, color: C.accent }}>{i + 1}</div>
                <div style={{ height: 14 }} />
                <div style={{ fontFamily: F.sans, fontWeight: 700, fontSize: 46, lineHeight: 1.1, color: C.contrast }}>{nb(e.titre)}</div>
                {e.texte && <div style={{ fontFamily: F.sans, fontSize: 34, lineHeight: 1.25, marginTop: 10, color: C.inkSoft }}>{nb(e.texte)}</div>}
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
      <Footer url={false} />
    </Paper>
  );
};
