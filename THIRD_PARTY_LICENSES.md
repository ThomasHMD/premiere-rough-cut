# Third-party licenses

premiere-rough-cut is under the MIT license ([LICENSE](LICENSE)). It bundles the files below, under their own licenses,
and relies on tools that you install yourself (nothing of them is redistributed here).

## Bundled

| What | Where | Upstream | License |
|---|---|---|---|
| Inter (fonts) | `skills/motion-design/public/fonts/Inter-*.woff2` | [rsms/inter](https://github.com/rsms/inter) | SIL Open Font License 1.1, full text in `OFL-Inter.txt` |
| Source Serif 4 (fonts) | `skills/motion-design/public/fonts/SourceSerif4-*.woff2` | [adobe-fonts/source-serif](https://github.com/adobe-fonts/source-serif) | SIL Open Font License 1.1, full text in `OFL-SourceSerif4.txt` |

The sound effects in `skills/motion-design/public/sfx/` are synthesized by the kit's own scripts (`make-sfx.py`) and are
under the MIT license like the rest of the code.

The figure `docs/images/rough-cut-example.svg` is drawn from the cut list of one of my own videos; it contains durations
only.

## Installed separately (not redistributed)

| Tool | Used by | License |
|---|---|---|
| [Remotion](https://www.remotion.dev) | motion-design (npm dependency) | Remotion License: free for individuals and companies of up to 3 people, company license above that ([remotion.pro/license](https://www.remotion.pro/license)) |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) and its models | rough-cut, subtitles, overlays | MIT |
| [ffmpeg](https://ffmpeg.org) | all skills | LGPL / GPL depending on the build |
| [ctc-forced-aligner](https://github.com/MahmoudAshraf97/ctc-forced-aligner) | subtitles | BSD 2-Clause (its alignment model downloads on first run, under its own terms) |
| [Playwright](https://playwright.dev) | overlays (site demos) | Apache 2.0 |
| numpy, scipy, soundfile, Pillow, fontTools, OpenCV | various scripts | BSD / MIT / HPND / Apache 2.0 |

Adobe Premiere Pro is a trademark of Adobe Inc. This project is not affiliated with or endorsed by Adobe, nor by
Anthropic.
