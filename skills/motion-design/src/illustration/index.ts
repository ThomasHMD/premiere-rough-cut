import { registerRoot } from "remotion";
import { IllustrationCompositions } from "./Compositions";

// Test entry: only the graphics compositions (the main Root includes them too).
registerRoot(IllustrationCompositions);
