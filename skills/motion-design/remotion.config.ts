import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(95);
Config.setOverwriteOutput(true);
// Concurrency as a percentage of cores: about 85% of the machine (12 tabs on a 14-core Mac),
// which leaves room to do something else during a render. A fixed number larger than the core count makes
// Remotion fail: never write one here. Measured: beyond 12 tabs in ONE browser,
// the process that captures the frames saturates a core and the render stops getting faster.
Config.setConcurrency("85%");
Config.setChromiumOpenGlRenderer("angle");
