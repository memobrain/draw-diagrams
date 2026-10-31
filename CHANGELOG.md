# Changelog

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
