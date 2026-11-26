# Flow outline protocol

The flow outline is the **logic** of a flowchart — main path, decisions, branches, loops —
written as one JSON object. It carries no geometry: when the edit link opens, MemoBrain's
layout engine places every step and routes every connector. The same protocol drives
MemoBrain's in-app AI generation, and the script validates the outline with the same rules.

## Shape

```json
{"skill":"OUTLINE","targetMode":"flow","summary":"One line describing the process",
 "mainline":["Start","step","step?","step","End"],
 "branches":[{"from":"step?","cond":"No","path":["step"],"join":"step"}],
 "loops":[{"from":"step","to":"step","meaning":"why it goes back"}]}
```

`skill` and `targetMode` are optional for the script. `branches` / `loops` may be empty arrays.

## Rules (the script enforces them — on failure it lists the issues; fix the file and re-run)

1. **`mainline`** — the ordered main path of the normal case, from `开始` to `结束`.
   Put **at least 4 steps** between the two ends (usually 5–10): each key stage of the
   real process gets its own step. Failure/exception/alternative paths do **not** go here —
   they are branches.
2. **Decision steps** — a step whose label reads as a question: ends with `?` / `？`, or
   contains `是否 / 能否 / 有无 / 若 / 如果`, or the words `if` / `whether`.
   A decision on the mainline continues to the **next mainline step** (that is exit 1) and
   must declare **exactly one** branch (exit 2). No branch, or two branches, is an error.
3. **`branches`** — `{ "from": <decision label>, "cond": <edge label>, "path": [...], "join": <label> }`
   - `cond` — the label on this exit: `否` / `是`, `No` / `Yes`, `通过` / `不通过` …
   - `path` — the ordered steps of that exit (may be empty = the decision joins directly)
   - `join` — where the branch converges: a mainline step, a branch step, or the end step.
     **Branches must converge** — no dead ends.
   - **Retry / redo:** express it through `join` — set `join` to the earlier step the flow
     returns to (it is drawn as a feedback line). Do **not** also add a `loops` entry for a
     node that belongs to a branch: one exit per branch node.
4. **`loops`** — `{ "from": <mainline step>, "to": <earlier mainline step>, "meaning": "…" }`.
     Only for redo loops that start at a mainline step; `to` must lie earlier on the mainline.
5. **Labels** — globally unique; short verb phrases (≤ 10 CJK characters, ≤ 6 words); one
     label per step. No coordinates, shapes, colors or styles — the outline is logic only.
6. **Language** — write every label in the user's language, with two exceptions:
   - the first step is exactly `开始` for Chinese and `Start` for every other language;
     the last is exactly `结束` for Chinese and `End` for every other language;
   - decision labels end with an ASCII `?` or `？` (other scripts' question marks are not detected).

## Examples

Chinese:

```json
{"skill":"OUTLINE","targetMode":"flow","summary":"电商下单到发货的主流程",
 "mainline":["开始","确认订单信息","库存是否充足","锁定库存","生成支付单","支付是否成功","安排发货","结束"],
 "branches":[{"from":"库存是否充足","cond":"否","path":["通知缺货"],"join":"确认订单信息"},
             {"from":"支付是否成功","cond":"否","path":["取消订单","释放库存"],"join":"结束"}],
 "loops":[{"from":"生成支付单","to":"确认订单信息","meaning":"重新修改订单后再次支付"}]}
```

English:

```json
{"skill":"OUTLINE","targetMode":"flow","summary":"E-commerce order fulfilment, from checkout to shipping",
 "mainline":["Start","Confirm order info","Stock sufficient?","Reserve stock","Create payment","Payment successful?","Arrange shipping","End"],
 "branches":[{"from":"Stock sufficient?","cond":"No","path":["Notify out of stock"],"join":"Confirm order info"},
             {"from":"Payment successful?","cond":"No","path":["Cancel order","Release stock"],"join":"End"}],
 "loops":[{"from":"Create payment","to":"Confirm order info","meaning":"Revise the order and retry payment"}]}
```

Both are the richness baseline: six steps on the mainline between the ends, two branches,
one loop. A real flowchart should be at least this complete.

## Reading the script's output

```
wrote <name>.png (screenshot of the online version — same engine and look as the app)
MENTION THIS IN YOUR REPLY -> online editing, double-click to open: <absolute path to <name>.url>>
```

On a validation failure nothing is written and the exit code is 2:

```
error: the flow outline has 2 issue(s) — fix the outline file, then re-run:
  - decision "库存是否充足" has no branch — …
```

Fix the outline file and run the same command again. Never edit or assemble the link yourself.

`.png` is a best-effort screenshot of the online version itself (a local browser
plus network). When it is skipped the output says why — the edit link still
delivers everything needed. Never draw a replacement image yourself. A Mermaid
text preview (`.mmd`) is written only with the explicit `--mmd` flag.
