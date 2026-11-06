import { z } from "zod";

// ---- Premium full-screen components (V5 Premiere, opaque)
export const PremiumComponent = z.enum([
  "quote-full",
  "photo-compare",
  "stat-fort",
  "eyebrow-chapter",
  "word-reveal",
]);
export type PremiumComponent = z.infer<typeof PremiumComponent>;

// ---- Lower-thirds (V6 Premiere, alpha)
export const LowerThirdKind = z.enum([
  "lower-third-term",
  "lower-third-nom",
  "lower-third-oeuvre",
  "lower-third-lieu",
]);
export type LowerThirdKind = z.infer<typeof LowerThirdKind>;

// ---- Segment commun
const SegmentBase = z.object({
  durationSec: z.number().positive(),
  timecode: z.string().optional(),
  note: z.string().optional(),
  sfx: z
    .object({
      file: z.string(),
      offsetMs: z.number().optional(),
      gainDb: z.number().optional(),
    })
    .optional(),
});

export const MotionSegmentSchema = SegmentBase.extend({
  type: z.literal("motion"),
  component: PremiumComponent,
  data: z.record(z.string(), z.any()),
});

export const LowerThirdSegmentSchema = SegmentBase.extend({
  type: z.literal("lower-third"),
  kind: LowerThirdKind.default("lower-third-term"),
  data: z.record(z.string(), z.any()),
});

export const SectionTitleSegmentSchema = SegmentBase.extend({
  type: z.literal("section-title"),
  data: z.object({
    eyebrow: z.string().optional(),
    title: z.string(),
  }),
});

export const SegmentSchema = z.discriminatedUnion("type", [
  MotionSegmentSchema,
  LowerThirdSegmentSchema,
  SectionTitleSegmentSchema,
]);
export type Segment = z.infer<typeof SegmentSchema>;

export const AnimationScriptSchema = z.object({
  version: z.literal(1).or(z.literal(2)),
  audioPath: z.string().optional(),
  title: z.string().optional(),
  fps: z.number().default(30),
  width: z.number().default(1920),
  height: z.number().default(1080),
  sfxDefaults: z
    .object({
      "lower-third": z.string().optional(),
      "section-title": z.string().optional(),
      motion: z.string().optional(),
    })
    .optional(),
  segments: z.array(SegmentSchema),
  // extra frames, last frame held (the file covers its whole Premiere clip)
  tailFrames: z.number().int().nonnegative().optional(),
});
export type AnimationScript = z.infer<typeof AnimationScriptSchema>;
