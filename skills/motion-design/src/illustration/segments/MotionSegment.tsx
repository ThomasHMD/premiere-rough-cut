import React from "react";
import { z } from "zod";
import { MotionSegmentSchema } from "../types";
import { QuoteFull } from "../motion/QuoteFull";

type MotionSeg = z.infer<typeof MotionSegmentSchema>;

export const MotionSegment: React.FC<{ segment: MotionSeg }> = ({ segment }) => {
  switch (segment.component) {
    case "quote-full":
      return <QuoteFull {...(segment.data as any)} />;
    case "photo-compare":
    case "stat-fort":
    case "eyebrow-chapter":
    case "word-reveal":
      // Phase B: components to implement
      return (
        <div style={{ color: "#1A1A1A", fontFamily: "Inter", fontSize: 44 }}>
          [Component "{segment.component}" not implemented: Phase B]
        </div>
      );
    default:
      return null;
  }
};
