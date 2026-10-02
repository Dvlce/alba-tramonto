# Theme

## Part 1 — Compact token summary

Plain CSS. No Tailwind configuration or theme provider. Theme is stored in localStorage under `alba.theme`, visual surface style under `alba.surfaceStyle`; selectors are `:root[data-theme=dark]` and `[data-style=neo|glass]`.

| Token | Light | Dark |
| --- | --- | --- |
| --bg | #f4f5ee | #111c18 |
| --surface | #fffef9 | #192820 |
| --surface-alt | #edf1e7 | #23362a |
| --text | #263c31 | #e2eadd |
| --muted | #788275 | #9aa99a |
| --line | #e4e8dc | #2d3f31 |
| --accent | #456b43 | #aed087 |
| --accent-text | #fffef9 | #172318 |
| --shadow | 0 8px 32px #253a2510 | 0 8px 32px #00000020 |

Tramonto accent: sunset mark #d58c57, dot #cc8554; cover palettes #e9dfc2, #d2e3d4, #eecfb6, #d9d3e8, #c4dce7. Chart colors #347c9d, #dc8a50, #8772ad, #5a9672, #d36776, #8f753c.

Typography: system sans body `-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif` at 15px/1.6; editorial Georgia/Cambria serif for brand and titles. Tramonto brand 32px, page title 31px/1.35, panel/tool headings 23px; existing controls 10–12px. Editor serif/sans/mono/round selectors; A4 body 16px/28px, heading baseline multiples 56px. Mono `ui-monospace,SFMono-Regular,Consolas,monospace`. No webfont except local KaTeX fonts.

Spacing is literal px rather than tokenized: 4/5/7/8/10/12/14/16/18/20/22/24/25/27/28/34/35/42/60. Main notes shell max-width 1580px, horizontal padding 34px; sidebar 275px, gap 22px, workspace padding 27px. A4 sheet 794×1123px, padding 60px; editor 674×960px. Radius 7–13px controls, 16–20px panels, 3px/15px cover spine, 4px A4 frame. Borders 1px; soft low-opacity green/black shadows. No dark-specific notebook token file.

Responsive conditions in source are listed below. Print uses A4 210×297mm and @page margin 0; it hides chrome and shows only text pane. Motion honors prefers-reduced-motion.

Media conditions: `(max-width:1050px)`, `(max-width:390px)`, `(max-width:500px)`, `(max-width:700px)`, `(max-width:740px)`, `(max-width:760px)`, `(max-width:850px)`, `(max-width:960px)`, `(prefers-reduced-motion:reduce)`, `print`
