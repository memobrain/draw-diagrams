# Changelog

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
