# Answer me with HTML adaptations

Source: https://github.com/QingYunA/answer-me-with-html
Revision: 43d53147d2a1414b7843a9ed6ef5bbd9977680f1 (reviewed 2026-10-11)
License: MIT, retained in LICENSE.

QuickUI starts from the upstream compact-draft → parsed components → local layout → independent theme architecture. Reused code: sequence parser from src/components/sequence.js, component line/error helpers from src/components/error.js, chart niceScale from src/components/limits.js, WCAG color helpers from src/themes/color.js. React replaces the upstream HTML string templates and runtime DOM mutations; CSS grid replaces its costly measured photo-wall layout for stable in-chat panels. Existing sanitized Mermaid supplies flow/ER diagrams, with lazy loading. Timeline, callout, metadata, limit and panel concepts map to trusted React blocks.

Upstream is a Node >=20 CLI, not a browser rendering package. Its current package.json lists marked, @dagrejs/dagre and temml. Its raw HTML/SVG fences, arbitrary local-file readers, CLI configuration, generated scripts, video/TTS and full themes are intentionally excluded from the app. No upstream dependency or executable bundle is installed. No benchmark token or latency claims are inherited. The short JSON specification, original Markdown fallback and local reusable assets are persisted/cached separately from appearance. The copied modules do not access files or networks.
