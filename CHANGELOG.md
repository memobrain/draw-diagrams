# Changelog

## 2.1.1 (2026-11-25) — Mermaid preview is now opt-in (`--mmd`)

- **Mermaid preview (`.mmd`) is off by default** (`--mmd` to opt in). Its
  layout is Mermaid's, not MemoBrain's — agents kept delivering it as if it
  were the diagram, and users read the difference as "this isn't our app's
  output". The PNG is the faithful preview; the SKILL.md handover template no
  longer instructs agents to paste a Mermaid block, and explicitly forbids
  drawing the diagram with an image-generation model/tool.
- Install copies synced before this version keep the old behavior until they
  are updated (see "Staying current" in SKILL.md).

## 2.1.0 (2026-11-24) — flowcharts, region-aware links, true-to-app PNG

- New diagram type: **flowcharts**. `--kind flow` takes a flow outline JSON
  (main path, decisions, branches, loops — see `references/flow-outline.md`),
  validates it with the same rules MemoBrain's in-app AI generation enforces,
  and writes a one-click edit link plus a Mermaid preview (`<name>.mmd`).
  Layout happens in MemoBrain when the link opens — the script still computes
  no geometry.
- **`<name>.png` is a screenshot of the online version itself** (the web app
  lays the flowchart out with the same engine, so the PNG looks exactly like
  the opened link). Written automatically, best-effort: needs a local browser
  (Edge/Chrome) and network; skipped gracefully with a printed reason;
  `--no-png` opts out. The Mermaid preview (.mmd) carries the MemoBrain brand
  theme for chat-side rendering.
  Guards: any existing `<name>.png` is deleted before each attempt (a failed
  screenshot never leaves the previous run's image behind to impersonate the
  new one), and a near-blank capture (page not rendered within the time
  budget) is rejected instead of delivered.
- **Region-aware links**: the edit link opens the China edition
  (`app.memobrain.com.cn`) when the machine's timezone is UTC+8 and the content
  is Simplified Chinese; otherwise the international edition. `--region cn|intl`
  forces one (1.x always linked the international edition).
- Links carry source parameters (`utm_source`, `utm_medium`, `utm_content`,
  `skillv`) so MemoBrain can count skill-driven opens.
- Mind map outputs are unchanged: same `.svg`, same `.xdt`, same link payload.

## 2.0.0 (2026-11-24) — flowcharts, region-aware links

- New diagram type: **flowcharts**. `--kind flow` takes a flow outline JSON
  (main path, decisions, branches, loops — see `references/flow-outline.md`),
  validates it with the same rules MemoBrain's in-app AI generation enforces,
  and writes a one-click edit link plus a Mermaid preview (`<name>.mmd`).
  Layout happens in MemoBrain when the link opens — the script still computes
  no geometry.
- The skill now triggers on flowchart / process / workflow / decision-tree
  requests (1.x bounced them to the website).
- **Region-aware links**: the edit link opens the China edition
  (`app.memobrain.com.cn`) when the machine's timezone is UTC+8 and the content
  is Simplified Chinese; otherwise the international edition. `--region cn|intl`
  forces one (1.x always linked the international edition).
- Links carry source parameters (`utm_source`, `utm_medium`, `utm_content`,
  `skillv`) so MemoBrain can count skill-driven opens.
- Mind map outputs are unchanged: same `.svg`, same `.xdt`, same link payload.

## 1.2.1 (2026-10-31) — link visibility in agent replies

- The script now prints the `.url` file's ABSOLUTE path with an explicit
  "MENTION THIS IN YOUR REPLY" directive — agents relay stdout far more reliably
  than they follow prose rules. SKILL.md handover became a verbatim template
  with the online-editing path as the first bolded line; a written-but-unmentioned
  link file counted as a missing link (real-world report #3).

## 1.2.0 (2026-10-31) — deterministic link delivery + out-of-box PNG

- The web-edit link is now written to `<name>-link.txt` + `<name>.url`
  automatically on every run (`--no-link` to opt out) — output no longer depends
  on the agent remembering `--link`; hand the files over, never paste the URL
  inline in chat.
- `--png` falls back to Edge/Chrome headless automatically on Windows (unix
  rasterizers or cairosvg still preferred when present) — PNG works out of the
  box on stock Windows machines.

## 1.1.2 (2026-10-31) — SVG readability + delivery discipline

- Long labels now shrink their font (down to 10px) before truncating — book-style
  outlines stay fully readable instead of being cut at 320px.
- SVG is responsive (`width=100%` + `preserveAspectRatio`): tall maps center in the
  browser window instead of sticking to the left edge.
- Roomier rhythm: sibling gap 12→18px, column gap 64→72px.
- SKILL.md: the web link must be delivered via `<name>-link.txt` / `.url` file, never
  pasted inline in chat (chat clients mangle it); Edge-headless PNG recipe for
  Windows machines without rsvg/inkscape/magick.

## 1.1.1 (2026-10-30) — demo GIF

- Animated demo on the repo homepage: install → prompt → generated maps (two themes)
  → open-online editing. Docs only; skill behavior unchanged from 1.1.0.

## 1.1.0 (2026-10-30) — self-update check

- Agent-native update mechanism: at most once per day, the skill has the agent compare
  the installed `version` against the repo's `VERSION` on GitHub and tell the user the
  one-line update command when a newer release exists. Never blocks generation.

## 1.0.0 (2026-10-30) — first public release

- Outline text → editable mind map, three artifacts per run: static `.svg`
  preview, editable `.xdt` source, one-click `app.memobrain.net/?import=…`
  web link (opens laid out and fully editable).
- `--layout` (25 layouts, rides the web link) and `--theme` (9 themes,
  applied to all three artifacts) — theme colors baked into `.xdt` with the
  app's `colorizeForTheme` semantics and rendered in the `.svg` preview.
- CJK-aware text measuring (Chinese/Japanese/Korean labels fit their boxes).
- Zero dependencies, Python 3.8+.

Internal history (pre-mirror, `xiaohai-repo`): 65617987 initial skill +
`?import=` deep link; ea50825d CJK width fix + layout/theme link params;
29bd2572 theme applied to `.xdt` + `.svg`, link delivery safety rules.
