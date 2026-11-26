#!/usr/bin/env python3
"""xdt.py — text → MemoBrain diagram (edit link + .xdt/.svg for mind maps + Mermaid preview
for flowcharts). Zero dependencies.

Usage:
  # mind map: input is an indented outline
  python xdt.py outline.txt                  # writes <name>.xdt + <name>.svg next to it
  python xdt.py outline.txt -o outdir        # write outputs into a directory
  python xdt.py outline.txt --name "Plan"    # override diagram name
  python xdt.py outline.txt --layout fishbone
  python xdt.py outline.txt --theme forest
  python xdt.py outline.txt --link           # also print the one-click web edit link
  python xdt.py outline.txt --png            # also try to rasterize a .png (best effort)
  python xdt.py outline.txt --open           # open the edit link in the default browser

  # flowchart: input is a flow outline JSON (decisions / branches / loops)
  python xdt.py flow.json --kind flow --name "Order flow"   # writes <name>.mmd + edit link
                                                            # + rendered <name>.svg/.png (best-effort)
  python xdt.py flow.json --kind flow --no-png              # skip the rendered images

Every run also writes <name>-link.txt and <name>.url — the one-click web edit link.

Outline format (mind map): plain indented text, one node per line. First line = root.
Bullets ("-", "*", "1.") are allowed and stripped. Tabs count as 4 spaces.

  Product Launch
    Team
      Roles
      Hiring
    Timeline
    Budget

The .xdt stores only the tree (labels + parent links, no coordinates) —
MemoBrain auto-layouts it when opened. Editable, not a frozen picture.

Flow outline format: see references/flow-outline.md next to SKILL.md. The outline is
validated here first (the same rules MemoBrain's in-app AI generation enforces); a
valid outline is packed into the edit link and MemoBrain lays the flowchart out when
the link opens — the script never computes geometry.
"""
import argparse
import base64
import json
import re
import sys
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ★ 2026-11-24 区域链接（双区矩阵：国内版/海外版独立站点、独立账号库）：此前写死海外站，
#   国内用户被导到访问慢的海外在线版。auto（默认）=本机时区 UTC+8 且内容为简体中文 → 国内站，
#   其余一律海外站（日文/韩文/繁体/英文与容器常见的 UTC 环境都落海外站）；--region cn|intl 强制。
APP_URLS = {"intl": "https://app.memobrain.net/", "cn": "https://app.memobrain.com.cn/"}
# 链接来源参数：应用端深链埋点（skill:import:* 事件）的 utmSource/utmMedium/utmContent/skillVersion
UTM_SOURCE, UTM_MEDIUM = "agent-skill", "draw-diagrams"
# 技能版本单一来源=技能根目录 VERSION（随链接带给应用端埋点）
_VER_FILE = Path(__file__).resolve().parent.parent / "VERSION"
SKILL_VERSION = _VER_FILE.read_text(encoding="utf-8").strip() if _VER_FILE.exists() else "0"
NODE_H = 34          # node height (svg)
VGAP = 18            # vertical gap between sibling slots（10-31 书籍大纲反馈：12px 中文长标签显拥挤）
HGAP = 72            # horizontal gap between depth columns（同上：64→72 留呼吸感）
MAX_TEXT_W = 360.0   # svg label max width before font-shrink-then-truncate
MIN_FS = 10.0        # 自适应字号下限——先缩字号保完整显示，缩无可缩才截断
# ★ 布局/主题清单与应用正册同源（src/core/ai/tools/setLayoutDirection.VALID_LAYOUT_DIRS
#   与 mindmapTheme 注册表）——改应用侧清单必须同步这里
LAYOUTS = ["right", "left", "side", "four-side", "tb", "bt", "h-timeline", "v-timeline",
           "fishbone", "fishbone-r", "s-timeline", "tree-table", "tree-table-v", "tree-table-l",
           "tree-side", "tree-side-up", "matrix-h", "matrix-v", "matrix-2", "brace-map",
           "cycle-map", "bubble-map", "fan-map", "dual-flow", "quad-map"]
THEMES = ["default", "classic", "forest", "sunset", "lavender", "minimal", "morandi", "journal", "blackboard"]
# brand-ish branch palette (root uses the MemoBrain orange)
PALETTE = ["#1a73e8", "#6D28D9", "#059669", "#E08900", "#DB2777", "#0891B2"]
ROOT_BG, ROOT_FG = "#FDA503", "#ffffff"

# ★ 主题定义与应用正册同源（src/mindmap/mindmapTheme.ts MINDMAP_BASE_THEMES）——改应用侧
#   主题配色/线型/画布必须同步这里（只收基础 9 套；色库 gallery 主题不入册）。
#   烤色语义逐字段对齐 colorizeForTheme：一级节点 fontColor 也写 childFg（应用实际观感，
#   branch 的 fontColor 不被 colorizeForTheme 消费）；rootDeco/default 特例（14/600）不在
#   烤色范围——default 走纯树不烤色。
THEME_DEFS = {
    "classic": {
        "canvasBg": "#ffffff", "canvasTexture": "none",
        "root": {"bg": "#1A73E8", "fg": "#ffffff", "fontSize": 18, "fontWeight": 700, "deco": "bubble"},
        "level1": [
            {"bg": "#FFEBEE", "border": "#EF5350", "lineType": "orthogonal", "line": "#EF5350"},
            {"bg": "#FFF8E1", "border": "#FFB300", "lineType": "orthogonal", "line": "#FFB300"},
            {"bg": "#E3F2FD", "border": "#42A5F5", "lineType": "orthogonal", "line": "#42A5F5"},
            {"bg": "#E8F5E9", "border": "#66BB6A", "lineType": "orthogonal", "line": "#66BB6A"},
        ],
        "childBg": "#fafafa", "childFg": "#555555", "childBorder": "#d0d5dd",
        "childFontSize": 12, "childFontWeight": 500, "fontFamily": "inherit", "lineWidth": 1,
    },
    "forest": {
        "canvasBg": "#f2f7f1", "canvasTexture": "grid",
        "root": {"bg": "#2E7D32", "fg": "#ffffff", "fontSize": 18, "fontWeight": 700, "deco": "wreath"},
        "level1": [
            {"bg": "#E0F2F1", "border": "#26A69A", "lineType": "smoothstep", "line": "#26A69A"},
            {"bg": "#E8F5E9", "border": "#66BB6A", "lineType": "smoothstep", "line": "#66BB6A"},
            {"bg": "#E3F2FD", "border": "#42A5F5", "lineType": "smoothstep", "line": "#42A5F5"},
            {"bg": "#FFF3E0", "border": "#FFA726", "lineType": "smoothstep", "line": "#FFA726"},
        ],
        "childBg": "#f5f5f5", "childFg": "#555555", "childBorder": "#bdbdbd",
        "childFontSize": 12, "childFontWeight": 500, "fontFamily": "inherit", "lineWidth": 1,
    },
    "sunset": {
        "canvasBg": "#fff8f0", "canvasTexture": "dusk",
        "root": {"bg": "#E65100", "fg": "#ffffff", "fontSize": 18, "fontWeight": 700, "deco": "ribbon"},
        "level1": [
            {"bg": "#FFF3E0", "border": "#FF9800", "lineType": "bezier", "line": "#FF9800"},
            {"bg": "#FFEBEE", "border": "#EF5350", "lineType": "bezier", "line": "#EF5350"},
            {"bg": "#FCE4EC", "border": "#E91E63", "lineType": "bezier", "line": "#E91E63"},
            {"bg": "#FFF8E1", "border": "#FFB300", "lineType": "bezier", "line": "#FFB300"},
        ],
        "childBg": "#faf5f0", "childFg": "#555555", "childBorder": "#d0d5dd",
        "childFontSize": 12, "childFontWeight": 500, "fontFamily": "inherit", "lineWidth": 1,
    },
    "lavender": {
        "canvasBg": "#f8f4fb", "canvasTexture": "mist",
        "root": {"bg": "#6A1B9A", "fg": "#ffffff", "fontSize": 18, "fontWeight": 700, "deco": "stitch"},
        "level1": [
            {"bg": "#F3E5F5", "border": "#AB47BC", "lineType": "arc", "line": "#AB47BC"},
            {"bg": "#E0F7FA", "border": "#26C6DA", "lineType": "arc", "line": "#26C6DA"},
            {"bg": "#FCE4EC", "border": "#E91E63", "lineType": "arc", "line": "#E91E63"},
            {"bg": "#E3F2FD", "border": "#42A5F5", "lineType": "arc", "line": "#42A5F5"},
        ],
        "childBg": "#f5f0f8", "childFg": "#555555", "childBorder": "#ce93d8",
        "childFontSize": 12, "childFontWeight": 500, "fontFamily": "inherit", "lineWidth": 1,
    },
    "minimal": {
        "canvasBg": "#fafafa", "canvasTexture": "none",
        "root": {"bg": "#37474F", "fg": "#ffffff", "fontSize": 18, "fontWeight": 700, "deco": "none"},
        "level1": [
            {"bg": "#ECEFF1", "border": "#78909C", "lineType": "straight", "line": "#78909C"},
            {"bg": "#E3F2FD", "border": "#64B5F6", "lineType": "straight", "line": "#64B5F6"},
            {"bg": "#E8F5E9", "border": "#81C784", "lineType": "straight", "line": "#81C784"},
            {"bg": "#FFF3E0", "border": "#FFB74D", "lineType": "straight", "line": "#FFB74D"},
        ],
        "childBg": "#ffffff", "childFg": "#555555", "childBorder": "#bdbdbd",
        "childFontSize": 12, "childFontWeight": 500, "fontFamily": "inherit", "lineWidth": 1,
    },
    "morandi": {
        "canvasBg": "#f5f2ec", "canvasTexture": "fabric",
        "root": {"bg": "#8A817C", "fg": "#ffffff", "fontSize": 18, "fontWeight": 700, "deco": "bubble"},
        "level1": [
            {"bg": "#DDE5D4", "border": "#9CAF88", "lineType": "arc", "line": "#9CAF88"},
            {"bg": "#E8E2D9", "border": "#C4B6A5", "lineType": "arc", "line": "#C4B6A5"},
            {"bg": "#E5E0E8", "border": "#B0A6C9", "lineType": "arc", "line": "#B0A6C9"},
            {"bg": "#F0E4DC", "border": "#D4B2A1", "lineType": "arc", "line": "#D4B2A1"},
        ],
        "childBg": "#f6f4f1", "childFg": "#5f6368", "childBorder": "#cfcac2",
        "childFontSize": 12, "childFontWeight": 500, "fontFamily": "inherit", "lineWidth": 1,
    },
    "journal": {
        "canvasBg": "#fff9f2", "canvasTexture": "lined",
        "root": {"bg": "#FFB4A2", "fg": "#6D2E2E", "fontSize": 18, "fontWeight": 700, "deco": "ribbon"},
        "level1": [
            {"bg": "#FFE8D6", "border": "#F4A261", "lineType": "bezier", "line": "#F4A261"},
            {"bg": "#FFF3B0", "border": "#E9C46A", "lineType": "bezier", "line": "#E9C46A"},
            {"bg": "#D8E2DC", "border": "#84A98C", "lineType": "bezier", "line": "#84A98C"},
            {"bg": "#F5CAC3", "border": "#E5989B", "lineType": "bezier", "line": "#E5989B"},
        ],
        "childBg": "#fffaf5", "childFg": "#6d5a50", "childBorder": "#e8cfc4",
        "childFontSize": 12, "childFontWeight": 500, "fontFamily": "inherit", "lineWidth": 1,
    },
    "blackboard": {
        "canvasBg": "#2f4a40", "canvasTexture": "blackboard",
        "root": {"bg": "#37474F", "fg": "#ECEFF1", "fontSize": 18, "fontWeight": 700, "deco": "stitch"},
        "level1": [
            {"bg": "#455A64", "border": "#78909C", "lineType": "straight", "line": "#90E0EF"},
            {"bg": "#455A64", "border": "#78909C", "lineType": "straight", "line": "#9BE1D2"},
            {"bg": "#455A64", "border": "#78909C", "lineType": "straight", "line": "#F5A9B8"},
            {"bg": "#455A64", "border": "#78909C", "lineType": "straight", "line": "#A3B7E8"},
        ],
        "childBg": "#3E5158", "childFg": "#ECEFF1", "childBorder": "#607D8B",
        "childFontSize": 12, "childFontWeight": 500, "fontFamily": "inherit", "lineWidth": 1,
    },
}


def text_w(s: str) -> float:
    """SVG 13.5px sans 近似测宽：全角/CJK（含全角标点，U+2E80 起）≈13.5px，其余 ≈7.5px。
    2026-10-30 修复：旧版按 len()*7.2 估宽，中文标签（约 13.5px/字）严重溢出节点框。"""
    return sum(13.5 if ord(c) >= 0x2E80 else 7.5 for c in s)


def clip_text(s: str, max_w: float = MAX_TEXT_W) -> str:
    """按显示宽度截断（中文约 21 字、英文约 42 字符满宽），尾部加省略号。"""
    acc, out = 0.0, []
    for c in s:
        w = 13.5 if ord(c) >= 0x2E80 else 7.5
        if acc + w > max_w - 13.5:
            return "".join(out) + "…"
        acc += w
        out.append(c)
    return "".join(out)


def text_px(s: str, fs: float) -> float:
    """指定字号下的显示宽度（全角=1em、半角≈0.556em）。"""
    return sum(fs if ord(c) >= 0x2E80 else fs * 0.556 for c in s)


def fit_label(s: str, base_fs: float):
    """★ 2026-10-31 书籍大纲反馈根治：长标签先自适应缩字号（base→MIN_FS）保完整
    显示，缩无可缩才截断——旧版 320px 直接截断=「显示不全」。返回 (字号, 文本)。"""
    fs = base_fs
    while fs > MIN_FS:
        if text_px(s, fs) <= MAX_TEXT_W:
            return fs, s
        fs -= 0.5
    acc, out = 0.0, []
    for c in s:
        w = MIN_FS if ord(c) >= 0x2E80 else MIN_FS * 0.556
        if acc + w > MAX_TEXT_W - MIN_FS:
            return MIN_FS, "".join(out) + "…"
        acc += w
        out.append(c)
    return MIN_FS, "".join(out)


def _nid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def parse_outline(text: str):
    """Indented text → nested {label, children[]} tree. First line is the root."""
    stack = []          # (indent, node)
    root = None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        indent = raw[: len(raw) - len(raw.lstrip())].replace("\t", "    ").count(" ")
        line = raw.strip()
        line = re.sub(r"^([-*•]|\d+[.)])\s+", "", line)
        if not line:
            continue
        node = {"label": line, "children": []}
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            if root is not None:
                raise ValueError("multiple root-level lines (keep exactly one root)")
            root = node
        else:
            stack[-1][1]["children"].append(node)
        stack.append((indent, node))
    if root is None:
        raise ValueError("empty outline")
    return root


def tree_to_xdt(root, name: str, layout: str = "right", theme: str = "default") -> dict:
    """Tree → .xdt file JSON (positions all zero: MemoBrain auto-layouts).
    ★ 非 default 主题按应用 colorizeForTheme 语义烤进节点/边 + 页画布字段（isRoot/rootDeco/
    一级 15/700+branch 底色+childFg、二级+ childBg+branch 边框、边 branchLineType+User 双写+
    style.stroke、页 canvasBg/canvasTexture）——与 AI 落库/模板应用同一口径，桌面端直接拖入
    即得主题观感；default 保持纯树（应用端 MindMapNode 渲染 fallback 即默认观感）。"""
    th = THEME_DEFS.get(theme) if theme != "default" else None
    nodes, edges = [], []

    def walk(node, parent_id, branch, depth):
        nid = _nid("n")
        data = {"label": node["label"]}
        if th:
            if depth == 0:
                r = th["root"]
                data.update(isRoot=True, bgColor=r["bg"], fontColor=r["fg"],
                            fontSize=r["fontSize"], fontWeight=r["fontWeight"],
                            fontFamily=th["fontFamily"], rootDeco=r["deco"])
            elif depth == 1:
                data.update(bgColor=branch["bg"], fontColor=th["childFg"],
                            borderColor=branch["border"], fontSize=15, fontWeight=700,
                            fontFamily=th["fontFamily"])
            else:
                data.update(bgColor=th["childBg"], fontColor=th["childFg"],
                            borderColor=branch["border"], fontSize=th["childFontSize"],
                            fontWeight=th["childFontWeight"], fontFamily=th["fontFamily"])
        nodes.append({"id": nid, "type": "mindMapNode", "position": {"x": 0, "y": 0}, "data": data})
        if parent_id:
            edge = {"id": _nid("e"), "source": parent_id, "target": nid, "type": "mindMapEdge"}
            if th:
                edge["data"] = {"branchLineType": branch["lineType"], "branchLineTypeUser": branch["lineType"]}
                edge["style"] = {"stroke": branch["line"], "strokeWidth": th["lineWidth"]}
            edges.append(edge)
        for i, c in enumerate(node.get("children", [])):
            sub = th["level1"][i % len(th["level1"])] if th and depth == 0 else branch
            walk(c, nid, sub, depth + 1)

    walk(root, None, None, 0)  # root stays first in the array (required by the app's root detection)
    now = datetime.now(timezone.utc).isoformat()
    page = {"id": _nid("page"), "mode": "mindmap", "name": name,
            "nodes": nodes, "edges": edges, "layoutMode": layout}
    if th:
        page["canvasBg"] = th["canvasBg"]
        page["canvasTexture"] = th["canvasTexture"]
    return {
        "version": 1,
        "pages": [page],
        "metadata": {"name": name, "createdAt": now, "updatedAt": now},
    }


def _layout(root, fs_of=None):
    """Assign (x, y) to every node: leaves stack vertically, parents center on children.
    fs_of: depth → svg 字号（主题渲染各级字号不同，测宽随字号缩放；None=统一 13.5 恒旧行为）"""
    widths, cols = {}, {}

    def measure(node, depth):
        fs_base = fs_of(depth) if fs_of else 13.5
        fs, label = fit_label(node["label"], fs_base)
        node["_fs"], node["_label"] = fs, label
        w = max(48, int(text_px(label, fs)) + 28)
        widths[id(node)] = w
        cols.setdefault(depth, 0)
        cols[depth] = max(cols[depth], w)
        node["_d"] = depth
        for c in node.get("children", []):
            measure(c, depth + 1)

    measure(root, 0)
    col_x, acc = {}, 0.0
    for d in sorted(cols):
        col_x[d] = acc if d == 0 else acc + HGAP
        acc += cols[d]
    cursor = {"y": 0.0}

    def place(node):
        kids = node.get("children", [])
        if not kids:
            y = cursor["y"]
            cursor["y"] += NODE_H + VGAP
        else:
            for k in kids:
                place(k)
            y = (kids[0]["_y"] + kids[-1]["_y"]) / 2
        node["_x"] = col_x[node["_d"]]
        node["_y"] = y

    place(root)
    return widths, cursor["y"], acc


def _mix(hex_color: str, ratio: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    f = lambda v: int(v + (255 - v) * ratio)
    return f"#{f(r):02x}{f(g):02x}{f(b):02x}"


def tree_to_svg(root, theme: str = "default") -> str:
    """default = 品牌橙预览（恒旧行为）；命名主题 = 按应用主题观感渲染——配色/线型/画布
    底色与 mindmapTheme.ts 同源，连线形状随主题 lineType（straight=直线 /
    orthogonal·smoothstep=直角肘 / bezier·arc=贝塞尔）。"""
    th = THEME_DEFS.get(theme) if theme != "default" else None
    fs_of = (lambda d: {0: 15.0, 1: 14.0}.get(d, 12.5)) if th else (lambda d: 15.0 if d == 0 else 13.5)
    widths, total_h, total_w = _layout(root, fs_of)

    def branch_color(node, depth, parent_color):
        if depth == 0:
            return ROOT_BG
        if depth == 1:
            return PALETTE[(node.get("_bi", 0)) % len(PALETTE)]
        return _mix(parent_color, 0.55)

    for i, c in enumerate(root.get("children", [])):
        c["_bi"] = i
    if th:
        def mark(node, branch):
            node["_br"] = branch
            for i, c in enumerate(node.get("children", [])):
                mark(c, th["level1"][i % len(th["level1"])] if branch is None else branch)
        mark(root, None)

    parts = []
    # ★ 响应式居中（10-31 反馈「只在左侧不居中」）：width=100%+viewBox+meet=横向
    #   随容器居中、纵向原比例顶对齐；固定像素宽在宽窗口里顶左锚定=高瘦图贴左墙
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{int(total_h + 80)}" '
        f'viewBox="0 0 {int(total_w + 80)} {int(total_h + 80)}" preserveAspectRatio="xMidYMin meet">'
    )
    parts.append(f'<rect width="100%" height="100%" fill="{th["canvasBg"] if th else "#ffffff"}"/>')
    parts.append('<g font-family="Segoe UI, Arial, sans-serif" transform="translate(40,40)">')

    def esc(s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    def draw(node, depth, color):
        for k in node.get("children", []):
            kc = branch_color(k, depth + 1, color)
            draw(k, depth + 1, kc)
            # connector: parent right edge → child left edge（形状随主题 lineType）
            x1, y1 = node["_x"] + widths[id(node)], node["_y"] + NODE_H / 2
            x2, y2 = k["_x"], k["_y"] + NODE_H / 2
            mx = (x1 + x2) / 2
            if th:
                b = k["_br"]
                stroke, sw, lt = b["line"], 1.2, b["lineType"]
                opacity = '1'
            else:
                stroke, sw, lt = kc, 2.2, "bezier"
                opacity = "0.85"
            if lt == "straight":
                seg = f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}"'
                tail = "/>"
            elif lt in ("orthogonal", "smoothstep"):
                seg = f'<path d="M{x1:.0f} {y1:.0f} H {mx:.0f} V {y2:.0f} H {x2:.0f}"'
                tail = "/>"
            else:
                seg = (f'<path d="M{x1:.0f} {y1:.0f} C {mx:.0f} {y1:.0f}, {mx:.0f} {y2:.0f}, '
                       f'{x2:.0f} {y2:.0f}"')
                tail = "/>"
            parts.append(f'{seg} fill="none" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"{tail}')
        label, fs = node["_label"], node["_fs"]
        w, x, y = widths[id(node)], node["_x"], node["_y"]
        if th:
            b = node["_br"]
            if depth == 0:
                bg, fg, border = th["root"]["bg"], th["root"]["fg"], th["root"]["bg"]
                fw = "700"
            elif depth == 1:
                bg, fg, border = b["bg"], th["childFg"], b["border"]
                fw = "700"
            else:
                bg, fg, border = th["childBg"], th["childFg"], b["border"]
                fw = "500"
        else:
            bg = "#FDA503" if depth == 0 else _mix(color, 0.72)
            fg = "#ffffff" if depth == 0 else "#1f2937"
            fw = "700" if depth == 0 else "500"
            border = color if depth > 0 else ROOT_BG
        parts.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{NODE_H}" rx="9" fill="{bg}" stroke="{border}" stroke-width="{1.6 if depth == 0 else 1.1}"/>')
        parts.append(f'<text x="{x + w / 2:.0f}" y="{y + NODE_H / 2 + fs * 0.34:.1f}" text-anchor="middle" font-size="{fs}" font-weight="{fw}" fill="{fg}">{esc(label)}</text>')

    draw(root, 0, ROOT_BG)
    parts.append("</g></svg>")
    return "".join(parts)


# ── 区域判定 ───────────────────────────────────────────────────────────────
_KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")          # 平假名/片假名
_HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
_HAN = re.compile(r"[\u4e00-\u9fff]")
# 高频繁体专用字（简体文本里不出现的字形）——命中即视为繁体中文，默认海外站
_TRAD_ONLY = set("們這個來時間學會開關後為與從對應該發現實點數據網線圖標準確認執業務單價貨庫")


def looks_simplified_chinese(text: str) -> bool:
    """有汉字、无假名/谚文、无繁体专用字。"""
    if not _HAN.search(text) or _KANA.search(text) or _HANGUL.search(text):
        return False
    return not any(ch in _TRAD_ONLY for ch in text)


def pick_region(text: str, region: str = "auto") -> str:
    """链接落哪个站：显式 cn/intl 优先；auto=本机时区 UTC+8 且内容为简体中文才落国内站。"""
    if region in APP_URLS:
        return region
    if region != "auto":
        raise ValueError(f"unknown region '{region}' (use auto, cn or intl)")
    local_offset = datetime.now().astimezone().utcoffset()
    if local_offset == timedelta(hours=8) and looks_simplified_chinese(text):
        return "cn"
    return "intl"


# ── 流程图大纲（应用内流程图两段式生成的第 1 段协议）────────────────────────
# ★ 校验规则与应用正册同源（src/core/ai/flowOutline.ts validateFlowOutline）——改应用侧
#   规则必须同步这里。这里严格（不过不出链接，agent 迭代到过）；应用端兜底宽松（有问题
#   仍按可识别部分落页并提示）。
# 判断节点识别与 JS 正则逐位同义：\b 在 JS 只认 ASCII 词边界，Python 用环视显式还原
_DECISION_RE = re.compile(r"是否|能否|有无|若|如果|[?？]|(?<![A-Za-z0-9_])(?:if|whether)(?![A-Za-z0-9_])", re.I)


def _is_start(label) -> bool:
    return label == "开始" or (isinstance(label, str) and re.fullmatch(r"start", label, re.I) is not None)


def _is_end(label) -> bool:
    return label == "结束" or (isinstance(label, str) and re.fullmatch(r"end", label, re.I) is not None)


def _str_arr(v) -> list:
    """JS 口径 String(x ?? '').trim() 后滤空。"""
    return [str(x if x is not None else "").strip() for x in v if str(x if x is not None else "").strip()] if isinstance(v, list) else []


def _text(v) -> str:
    return str(v).strip() if isinstance(v, str) else ""


def parse_flow_outline(text: str) -> dict:
    """文件文本 → 大纲 dict（{summary?, mainline, branches, loops}）。结构归一口径=应用
    normalizeOutline：脏项滤掉/空白 trim；取首 { 到尾 }（允许包在说明文字或 ```json 围栏里）。"""
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        raise ValueError("no JSON object found — the file must contain the flow outline JSON")
    txt = text[s:e + 1]
    try:
        obj = json.loads(txt)
    except json.JSONDecodeError:
        try:
            obj = json.loads(re.sub(r",\s*([}\]])", r"\1", txt))   # 尾逗号修复
        except json.JSONDecodeError as ex:
            raise ValueError(f"outline is not valid JSON: {ex}") from None
    if not isinstance(obj, dict) or not isinstance(obj.get("mainline"), list):
        raise ValueError('outline JSON must have a "mainline" array')
    branches = []
    for b in (obj.get("branches") if isinstance(obj.get("branches"), list) else []):
        if not isinstance(b, dict) or not _text(b.get("from")):
            continue
        branches.append({"from": _text(b.get("from")), "cond": _text(b.get("cond")),
                         "path": _str_arr(b.get("path")), "join": _text(b.get("join"))})
    loops = []
    for lp in (obj.get("loops") if isinstance(obj.get("loops"), list) else []):
        if not isinstance(lp, dict) or not _text(lp.get("from")) or not _text(lp.get("to")):
            continue
        loops.append({"from": _text(lp.get("from")), "to": _text(lp.get("to")),
                      "meaning": lp["meaning"] if isinstance(lp.get("meaning"), str) else None})
    out = {"mainline": _str_arr(obj["mainline"]), "branches": branches, "loops": loops}
    summary = obj.get("summary")
    if isinstance(summary, str) and summary.strip():
        out["summary"] = summary.strip()
    return out


def outline_steps(o: dict) -> list:
    return list(o["mainline"]) + [s for b in o["branches"] for s in b["path"]]


def _main_pos(o: dict, label):
    """环节 → 主干序号（分支环节返回其挂点的主干序号；不在图内返回 None）。"""
    ml = o["mainline"]
    if label in ml:
        return ml.index(label)
    for b in o["branches"]:
        if label in b["path"] and b["from"] in ml:
            return ml.index(b["from"])
    return None


def validate_flow_outline(o: dict) -> list:
    """大纲确定性校验，返回人读问题清单（空=通过）。规则逐条对应 validateFlowOutline。"""
    issues = []
    ml = o["mainline"]
    if len(ml) < 3:
        issues.append('mainline needs at least 3 steps ("开始"/"Start" -> at least 1 step -> "结束"/"End")')
    mid = len(ml) - 2
    if mid < 4:
        issues.append(f"mainline too thin: only {mid} step(s) between Start and End — spell out each key stage of the "
                      "main process (usually 5~10 steps); branches only hold failure/exception/alternative paths; don't pad with filler")
    # 哨兵检查不做空数组保护——与应用同款：主干为空时首尾两条同样报出（裁决与问题数逐位一致）
    if not _is_start(ml[0] if ml else ""):
        issues.append('the first mainline step must be exactly "开始" (or "Start")')
    if not _is_end(ml[-1] if ml else ""):
        issues.append('the last mainline step must be exactly "结束" (or "End")')

    all_steps = outline_steps(o)
    known = set(all_steps)
    dup = next((x for i, x in enumerate(all_steps) if all_steps.index(x) != i), None)
    if dup:
        issues.append(f'duplicate step label "{dup}" — every step label must be globally unique')

    for b in o["branches"]:
        if b["from"] not in known:
            issues.append(f'branch source "{b["from"]}" does not exist (it must be a step in mainline or in a branch path)')
        if b["join"] not in known:
            issues.append(f'the branch from "{b["from"]}" joins "{b["join"]}" which does not exist — a branch must converge to an existing step (or "结束"/"End")')
        if not b["cond"]:
            issues.append(f'the branch from "{b["from"]}" is missing its edge label cond (e.g. "否"/"No")')

    conds_by_from = {}
    for b in o["branches"]:
        conds_by_from.setdefault(b["from"], []).append(b["cond"])
    for frm, conds in conds_by_from.items():
        d = next((c for i, c in enumerate(conds) if conds.index(c) != i), None)
        if d:
            issues.append(f'decision "{frm}" has duplicate branch conditions "{d}" — the exits of one decision must be mutually exclusive')

    for label in all_steps:
        if not _DECISION_RE.search(label):
            continue
        n = len(conds_by_from.get(label, []))
        if n == 0:
            issues.append(f'decision "{label}" has no branch — a decision has exactly 2 exits (the sequence continuation takes 1); declare the other one in branches')
        elif n > 1:
            issues.append(f'decision "{label}" declares {n} branches — a decision has only 2 exits (the sequence continuation takes 1); declare exactly 1 branch')
    for frm in conds_by_from:
        if not _DECISION_RE.search(frm):
            issues.append(f'branch source "{frm}" is not a decision — only a step whose label reads as a question (ends with "?", or contains '
                          "是否/能否/有无/若/如果, or the words if/whether) can declare a branch; put ordinary steps directly into mainline or a branch path")

    loop_from_to = {lp["from"]: lp["to"] for lp in o["loops"]}
    for b in o["branches"]:
        for name in [b["from"]] + list(b["path"]):
            if name in loop_from_to:
                issues.append(f'the exit "{name}" of the branch from "{b["from"]}" declares both a join (→ "{b["join"]}") and a loop '
                              f'(→ "{loop_from_to[name]}") — for retry/redo set this branch\'s join to the loop target and delete the loops entry; '
                              "loops are only for redo loops that start at a mainline step")
                break
    for lp in o["loops"]:
        if lp["from"] not in known:
            issues.append(f'loop source "{lp["from"]}" does not exist')
            continue
        if lp["from"] == lp["to"]:
            issues.append("loop source and target are the same (meaningless loop)")
        to_pos = ml.index(lp["to"]) if lp["to"] in ml else -1
        if to_pos == -1:
            issues.append(f'loop "{lp["from"]}" → "{lp["to"]}" must land on a mainline step — a loop goes back to the main flow to retry/redo')
            continue
        from_pos = _main_pos(o, lp["from"])
        on_main = lp["from"] in ml
        if from_pos is not None:
            ok = (to_pos < from_pos) if on_main else (to_pos <= from_pos)
            if not ok:
                issues.append(f'loop "{lp["from"]}" → "{lp["to"]}" points downstream or at itself — a loop must return to an earlier step')
    return issues


def _mmd_text(s: str) -> str:
    """Mermaid 标签转义：控制字符压成空格（Mermaid 是行式语法，换行即断句）；原文的 & 与 #
    先行转义——Mermaid 会把标签里的 `#ok;` 这类序列当实体码解码（真引擎实测「100% #ok;」
    被渲染成「&ok;」），原文 # 一律写成 #35;；随后引号/尖括号/反斜杠走实体码；竖线会撞
    边标签语法直接替换。"""
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", s)
    return (s.replace("&", "&amp;").replace("#", "#35;").replace('"', "#quot;").replace("<", "#lt;")
            .replace(">", "#gt;").replace("\\", "#92;").replace("|", "/"))


def outline_to_mmd(o: dict) -> str:
    """大纲 → Mermaid flowchart（快速预览用；正式排版与编辑走链接）。与链接载荷同源同序：
    开始/结束 stadium、判断菱形、分支出线带 cond 标签、回环带 meaning 标签。
    ★ 2026-11-24 主题对齐（公子「PNG/SVG 没用我们的主题格式」）：配色对齐应用商务蓝
    默认主题（步骤浅蓝/判断琥珀/开始结束蓝底白字/连线 #555）——排版仍是 Mermaid 几何，
    权威排版是链接打开的应用引擎。"""
    steps = outline_steps(o)
    ids = {}
    for i, label in enumerate(steps):
        ids.setdefault(label, f"n{i}")
    ml = o["mainline"]
    startend_ids, decision_ids, step_ids = [], [], []
    lines = ["flowchart TD"]

    def node(label: str, i: int) -> str:
        if (i == 0 and _is_start(label)) or (i == len(ml) - 1 and _is_end(label)):
            startend_ids.append(ids[label])
            return f'{ids[label]}(["{_mmd_text(label)}"])'
        if _DECISION_RE.search(label):
            decision_ids.append(ids[label])
            return f'{ids[label]}{{"{_mmd_text(label)}"}}'
        step_ids.append(ids[label])
        return f'{ids[label]}["{_mmd_text(label)}"]'

    for i, label in enumerate(steps):
        lines.append(f"    {node(label, i)}")

    def edge(a: str, b: str, label=None):
        if a not in ids or b not in ids or a == b:
            return
        tag = f"|{_mmd_text(label)}|" if label else ""
        lines.append(f"    {ids[a]} -->{tag} {ids[b]}")

    for i in range(len(ml) - 1):
        edge(ml[i], ml[i + 1])
    for b in o["branches"]:
        cur, leaving = b["from"], True
        for step in b["path"]:
            edge(cur, step, b["cond"] if leaving and b["cond"] else None)
            leaving, cur = False, step
        if b["join"]:
            edge(cur, b["join"], b["cond"] if leaving and b["cond"] else None)
    for lp in o["loops"]:
        edge(lp["from"], lp["to"], lp.get("meaning"))

    init = ('%%{init: {"theme":"base","themeVariables":{'
            '"primaryColor":"#E3F2FD","primaryBorderColor":"#1976D2","primaryTextColor":"#1F2937",'
            '"lineColor":"#555555","edgeLabelBackground":"#F5F5F5",'
            '"fontFamily":"Segoe UI, Arial, sans-serif","fontSize":"14px"}}}%%')
    tail = [
        "classDef startend fill:#1A73E8,stroke:#125CA9,color:#ffffff,font-weight:bold",
        "classDef decision fill:#FEF3C7,stroke:#D97706,color:#92400E",
        "classDef step fill:#E3F2FD,stroke:#1976D2,color:#1F2937",
    ]
    if startend_ids:
        tail.append("class " + ",".join(startend_ids) + " startend")
    if decision_ids:
        tail.append("class " + ",".join(decision_ids) + " decision")
    if step_ids:
        tail.append("class " + ",".join(step_ids) + " step")
    return "\n".join([init] + lines + tail) + "\n"


def make_link(payload: dict, kind: str, region: str) -> str:
    """载荷 → 一键在线编辑链接：base64url(zlib(JSON))（应用端 DecompressionStream('deflate') 同构）
    + 来源参数（utm_* 与 skillv 供应用端深链埋点）。"""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    b = base64.urlsafe_b64encode(zlib.compress(raw.encode("utf-8"), 9)).decode("ascii").rstrip("=")
    base = APP_URLS[pick_region(raw, region)]
    return f"{base}?import={b}&utm_source={UTM_SOURCE}&utm_medium={UTM_MEDIUM}&utm_content={kind}&skillv={SKILL_VERSION}"


def write_link_files(link: str, outdir: Path, slug: str) -> None:
    """★ 2026-10-31：链接必落文件（交付纪律）——聊天内联 ~1KB base64 必被换行/截断弄坏
    （DS Harness 实战复现「在线编辑没生效」）。.txt=复制用 / .url=双击直开。
    ★ 指令式 stdout：agent 对 stdout 的转述远比自由发挥可靠——必须把绝对路径顶到它脸上，
    聊天回复里才见得到在线编辑入口（10-31 三报「成果没连到在线编辑」）。"""
    (outdir / f"{slug}-link.txt").write_text(link + "\n", encoding="utf-8")
    (outdir / f"{slug}.url").write_text("[InternetShortcut]\nURL=" + link + "\n", encoding="utf-8")
    url_file = (outdir / f"{slug}.url").resolve()
    print(f"MENTION THIS IN YOUR REPLY -> online editing, double-click to open: {url_file}")
    print(f"  (raw URL in {(outdir / f'{slug}-link.txt').resolve()}; deliver file paths, never paste the URL inline in chat)")


# 无头渲染用浏览器探测（Windows 常态；unix 无这些则 svg/png 跳过——与 --png 兜底同一组）
_BROWSER_EXES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)

# ★ 2026-11-24 二轮（公子「url 是在线编辑入口，需要再加个 PNG 的格式」）：流程图图片产物。
# 渲染页=无头浏览器打开 → mermaid 把 .mmd 画成 SVG（--dump-dom 取回）→ 既有 try_png 栅格化
# 出 .png。htmlLabels:false 意图是标签落 <text>（独立 .svg 更可移植）——★11.12 实测该开关
# 被忽略、仍走 foreignObject+tspan，但在我们的链路无害：栅格化走 Edge/Chrome（浏览器原生
# 渲染 foreignObject，真管线标签逐字保真实测含反斜杠/引号/尖括号/#xx;/中文/分号边标签）；
# useMaxWidth:false 同样被忽略（svg 用 max-width 样式，try_png 的 viewBox 扫描窗已放宽到
# 1200 字符并兼容小数）。CDN=npmmirror 优先（国内快且稳）、jsdelivr 兜底；全败/无浏览器=
# svg/png 如实跳过，.mmd 与链接不受影响。
# ★ 2026-11-24 三轮（公子「PNG 和 SVG 还是没渲染正确，格式上和在线版完全不一样」）：
# PNG 改为【在线版本身的截图】——无头浏览器打开深链（匿名访客），等水合+落页+引擎排布
# +fit 完成（virtual-time 预算），截全窗后裁掉应用固定 UI（左栏 72 / 顶栏 ~90 / 底栏 ~36）
# 只留画布。和在线版逐像素同源：同一引擎排布、同一主题、同一连线几何。PIL 可选：有则裁
# UI，无则交付全窗截图（仍是在线版本貌）。
_APP_SHOT_WINDOW = (1680, 1260)
_APP_CROP = {"left": 74, "top": 92, "bottom": 38}


def try_app_png(link: str, out_png: Path) -> bool:
    import subprocess
    tmp = out_png.with_suffix(".raw.png")
    w, h = _APP_SHOT_WINDOW
    for exe in _BROWSER_EXES:
        if not Path(exe).exists():
            continue
        try:
            tmp.unlink(missing_ok=True)
            subprocess.run(
                [exe, "--headless", "--disable-gpu", f"--screenshot={tmp}",
                 f"--window-size={w},{h}", "--virtual-time-budget=45000",
                 "--default-background-color=FFFFFFFF", link],
                capture_output=True, timeout=240)
            if not (tmp.exists() and tmp.stat().st_size > 20000):
                continue
            try:
                from PIL import Image  # type: ignore
                im = Image.open(tmp)
                # ★ 白屏守卫（2026-11-24 四轮）：virtual-time 预算内页面没渲染完 =
                #   全白截图冒充成功交付。近白占比 >99.5% 判未渲染，换下一个浏览器，
                #   全败则如实跳过（不留白图）。
                small = im.convert("L").resize((160, 120))
                px = list(small.getdata())
                if sum(1 for v in px if v > 245) / len(px) > 0.995:
                    continue
                c = {"left": _APP_CROP["left"], "top": _APP_CROP["top"],
                     "right": im.width, "bottom": im.height - _APP_CROP["bottom"]}
                if c["right"] - c["left"] > 300 and c["bottom"] - c["top"] > 300:
                    im.crop((c["left"], c["top"], c["right"], c["bottom"])).save(out_png)
                else:
                    im.save(out_png)
            except ImportError:
                tmp.replace(out_png)  # 无 PIL：交付全窗截图（仍是在线版本貌）
            tmp.unlink(missing_ok=True)
            if out_png.exists() and out_png.stat().st_size > 20000:
                return True
        except Exception:
            continue
    tmp.unlink(missing_ok=True)
    return False



def try_png(svg_path: Path) -> bool:
    import shutil
    import subprocess
    out = svg_path.with_suffix(".png")
    for cmd in (
        ["rsvg-convert", "-w", "1600", str(svg_path), "-o", str(out)],
        ["inkscape", str(svg_path), "--export-type=png", f"--export-filename={out}"],
        ["magick", "-density", "144", str(svg_path), str(out)],
    ):
        if shutil.which(cmd[0]):
            return subprocess.run(cmd, capture_output=True).returncode == 0 and out.exists()
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2png(url=str(svg_path), write_to=str(out), output_width=1600)
        return out.exists()
    except Exception:
        pass
    # ★ 2026-10-31：Windows 常态无 unix 栅格化工具（DS Harness 实战反馈「--png 没
    #   生成」）——Edge/Chrome headless 兜底，开箱即得，不再依赖 agent 照食谱手动跑。
    #   窗口尺寸取 svg viewBox（svg 本体是 width=100% 响应式，头里 width 不可用）。
    try:
        # 1200 字符扫描窗：mermaid 的 <svg> 标签属性比导图预览的长（viewBox 可能带小数）
        vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg_path.read_text(encoding="utf-8")[:1200])
        w, h = (int(float(vb.group(1))), int(float(vb.group(2)))) if vb else (1200, 800)
    except Exception:
        w, h = 1200, 800
    for exe in _BROWSER_EXES:
        if not Path(exe).exists():
            continue
        try:
            subprocess.run(
                [exe, "--headless", "--disable-gpu", f"--screenshot={out}",
                 f"--window-size={w + 2},{h + 2}", "--default-background-color=FFFFFFFF",
                 svg_path.resolve().as_uri()],
                capture_output=True, timeout=180)
            if out.exists() and out.stat().st_size > 0:
                return True
        except Exception:
            continue
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="outline → MemoBrain diagram: mind map (.xdt/.svg/link) or flowchart (edit link + Mermaid preview)")
    ap.add_argument("outline", help="mind map: indented outline .txt  |  --kind flow: flow outline JSON file")
    ap.add_argument("--kind", default="mindmap", choices=["mindmap", "flow"],
                    help="mindmap (default): the input is an indented outline | flow: the input is a flow outline JSON (decisions/branches/loops)")
    ap.add_argument("-o", "--outdir", help="output directory (default: alongside the outline)")
    ap.add_argument("--name", help="diagram name (default: root label / outline summary)")
    ap.add_argument("--layout", default="right", choices=LAYOUTS, help="mind map layout for the app (25 options, default: right)")
    ap.add_argument("--theme", default="default", choices=THEMES, help="color theme baked into the link payload, the .xdt (colorizeForTheme 口径) and the .svg preview (9 options, default: default)")
    ap.add_argument("--region", default="auto", choices=["auto", "cn", "intl"],
                    help="which MemoBrain web app the edit link opens: auto (default) = China edition when the machine "
                         "timezone is UTC+8 and the content is Simplified Chinese, otherwise the international edition; cn / intl force one")
    ap.add_argument("--link", action="store_true", help="additionally print the one-click web edit link to stdout")
    ap.add_argument("--no-link", action="store_true", help="skip writing the -link.txt/.url files")
    ap.add_argument("--png", action="store_true", help="best-effort PNG rasterization (mind maps)")
    ap.add_argument("--no-png", action="store_true", help="skip rendered images (flow: the app-screenshot .png; mind map: --png rasterization)")
    ap.add_argument("--mmd", action="store_true", help="flow: also write a Mermaid text preview (.mmd) — OFF by default (2026-11-25: "
                    "agents kept pasting the Mermaid sketch whose layout is Mermaid's, not MemoBrain's; the PNG is the faithful preview)")
    ap.add_argument("--open", action="store_true", help="open the edit link in the default browser")
    args = ap.parse_args(argv)

    try:
        text = Path(args.outline).read_text(encoding="utf-8")
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.kind == "flow":
        if args.layout != "right" or args.theme != "default":
            print("error: --layout/--theme apply to --kind mindmap only", file=sys.stderr)
            return 2
        return run_flow(text, args)
    return run_mindmap(text, args)


def run_mindmap(text: str, args) -> int:
    try:
        root = parse_outline(text)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    name = args.name or root["label"]
    slug = re.sub(r"[^\w\-]+", "-", name).strip("-")[:60] or "mindmap"
    outdir = Path(args.outdir) if args.outdir else Path(args.outline).parent
    outdir.mkdir(parents=True, exist_ok=True)

    xdt_path = outdir / f"{slug}.xdt"
    xdt_path.write_text(json.dumps(tree_to_xdt(root, name, args.layout, args.theme), ensure_ascii=False, indent=1), encoding="utf-8")
    svg_path = outdir / f"{slug}.svg"
    svg_path.write_text(tree_to_svg(root, args.theme), encoding="utf-8")
    print(f"wrote {xdt_path} (layout={args.layout}, theme={args.theme})")
    print(f"wrote {svg_path}")

    if args.png and not args.no_png:
        # ★ 产物先删旧（同 run_flow 四轮守卫）：栅格化失败时不让上一版的 png 冒充
        out_png = svg_path.with_suffix(".png")
        try:
            out_png.unlink()
        except FileNotFoundError:
            pass
        ok = try_png(svg_path)
        print(f"png {'written' if ok else 'skipped (no rasterizer found)'}")

    # 载荷形态逐位不变（v1：name/root/layout + 非 default 才带 theme）——存量技能/链接零影响
    payload = {"name": name, "root": root, "layout": args.layout}
    if args.theme and args.theme != "default":
        payload["theme"] = args.theme
    link = make_link(payload, "mindmap", args.region)
    # --no-link 可关；--link 额外把 URL 打到 stdout（链接必落文件的交付纪律见 write_link_files）
    if not args.no_link:
        write_link_files(link, outdir, slug)
    if args.link or args.open:
        print(link)
    if args.open:
        import webbrowser
        webbrowser.open(link)
    return 0


def run_flow(text: str, args) -> int:
    """流程图大纲 → Mermaid 预览 + 编辑链接。校验不过不出链接（agent 按问题清单改大纲重跑）；
    排布与连线全部在应用端打开时由布局引擎完成——脚本不碰几何。"""
    try:
        outline = parse_flow_outline(text)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    issues = validate_flow_outline(outline)
    if issues:
        print(f"error: the flow outline has {len(issues)} issue(s) — fix the outline file, then re-run:", file=sys.stderr)
        for i in issues:
            print(f"  - {i}", file=sys.stderr)
        return 2

    name = args.name or outline.get("summary") or "Flowchart"
    slug = re.sub(r"[^\w\-]+", "-", name).strip("-")[:60] or "flowchart"
    outdir = Path(args.outdir) if args.outdir else Path(args.outline).parent
    outdir.mkdir(parents=True, exist_ok=True)

    mmd_path = outdir / f"{slug}.mmd"
    # ★ 2026-11-25 五轮：.mmd 默认停发（--mmd 选配）——agent 反复把 Mermaid 排版的
    #   预览图当交付物（公子三次反馈「这不是我们的软件生成的图」）。忠实预览=在线版
    #   截图 .png；.mmd 只在显式 --mmd 时出（离线可看、贴聊天可渲染品牌主题）。
    if getattr(args, "mmd", False):
        # LF 恒定（Windows 文本模式默认写 CRLF，agent 原样贴进聊天块会带 \r）
        with open(mmd_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(outline_to_mmd(outline))
        print(f"wrote {mmd_path} (Mermaid preview: {len(outline_steps(outline))} steps, "
              f"{len(outline['branches'])} branch(es), {len(outline['loops'])} loop(s))")

    payload = {"v": 2, "kind": "flow", "name": name, "outline": outline}
    link = make_link(payload, "flow", args.region)

    # ★ 2026-11-24 三轮：图片产物=在线版本身截图（同一引擎/主题/连线几何，逐像素同源），
    #   best-effort 默认开（无浏览器如实跳过），--no-png 关。
    if not args.no_png:
        png_path = outdir / f"{slug}.png"
        # ★ 产物先删旧（2026-11-24 四轮，公子截图「PNG 根本不是我们的软件生成的图」）：
        #   旧版本（Mermaid 渲染时代）留在输出目录的同名 png 会在此轮截图失败时冒充
        #   新产物被交付（agent 复用输出目录的坑）。截图是 best-effort——先删旧再尝试，
        #   失败就如实无图，绝不让上一版的产物冒充这一版。
        try:
            png_path.unlink()
        except FileNotFoundError:
            pass
        if try_app_png(link, png_path):
            print(f"wrote {png_path} (screenshot of the online version — same engine and look as the app)")
        else:
            print("png skipped (headless browser unavailable here) — deliver the link and files; "
                  "never substitute an AI-generated image")

    if not args.no_link:
        write_link_files(link, outdir, slug)
        if getattr(args, "mmd", False):
            mmd_abs = mmd_path.resolve()
            print(f"PREVIEW -> paste the content of {mmd_abs} inside a ```mermaid code block in your reply "
                  "(only when the chat renders diagrams; otherwise just mention the file)")
    if args.link or args.open:
        print(link)
    if args.open:
        import webbrowser
        webbrowser.open(link)
    return 0


if __name__ == "__main__":
    sys.exit(main())
