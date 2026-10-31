#!/usr/bin/env python3
"""xdt.py — outline text → MemoBrain mind map (.xdt + .svg + edit link). Zero dependencies.

Usage:
  python xdt.py outline.txt                  # writes <name>.xdt + <name>.svg next to it
  python xdt.py outline.txt -o outdir        # write outputs into a directory
  python xdt.py outline.txt --name "Plan"    # override diagram name
  python xdt.py outline.txt --layout fishbone
  python xdt.py outline.txt --theme forest
  python xdt.py outline.txt --link           # also print a one-click web edit link
  python xdt.py outline.txt --png            # also try to rasterize a .png (best effort)
  python xdt.py outline.txt --open           # open the edit link in the default browser

Outline format: plain indented text, one node per line. First line = root.
Bullets ("-", "*", "1.") are allowed and stripped. Tabs count as 4 spaces.

  Product Launch
    Team
      Roles
      Hiring
    Timeline
    Budget

The .xdt stores only the tree (labels + parent links, no coordinates) —
MemoBrain auto-layouts it when opened. Editable, not a frozen picture.
"""
import argparse
import base64
import json
import re
import sys
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path

APP_URL = "https://app.memobrain.net/"
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


def make_link(root, name: str, layout: str = "right", theme: str = "") -> str:
    payload = {"name": name, "root": root, "layout": layout}
    if theme and theme != "default":
        payload["theme"] = theme
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    b = base64.urlsafe_b64encode(zlib.compress(raw.encode("utf-8"), 9)).decode("ascii").rstrip("=")
    return f"{APP_URL}?import={b}&utm_source=agent-skill"


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
        vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg_path.read_text(encoding="utf-8")[:400])
        w, h = (int(vb.group(1)), int(vb.group(2))) if vb else (1200, 800)
    except Exception:
        w, h = 1200, 800
    for exe in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ):
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
    ap = argparse.ArgumentParser(description="outline text → MemoBrain mind map (.xdt/.svg/link)")
    ap.add_argument("outline", help="indented outline .txt file")
    ap.add_argument("-o", "--outdir", help="output directory (default: alongside the outline)")
    ap.add_argument("--name", help="diagram name (default: root label)")
    ap.add_argument("--layout", default="right", choices=LAYOUTS, help="mind map layout for the app (25 options, default: right)")
    ap.add_argument("--theme", default="default", choices=THEMES, help="color theme baked into the link payload, the .xdt (colorizeForTheme 口径) and the .svg preview (9 options, default: default)")
    ap.add_argument("--link", action="store_true", help="additionally print the one-click web edit link to stdout")
    ap.add_argument("--no-link", action="store_true", help="skip writing the -link.txt/.url files")
    ap.add_argument("--png", action="store_true", help="best-effort PNG rasterization")
    ap.add_argument("--open", action="store_true", help="open the edit link in the browser")
    args = ap.parse_args(argv)

    try:
        root = parse_outline(Path(args.outline).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
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

    if args.png:
        ok = try_png(svg_path)
        print(f"png {'written' if ok else 'skipped (no rasterizer found)'}")

    link = make_link(root, name, args.layout, args.theme)
    # ★ 2026-10-31：链接必落文件（交付纪律）——聊天内联 ~1KB base64 必被换行/截断弄坏
    #   （DS Harness 实战复现「在线编辑没生效」）。.txt=复制用 / .url=双击直开。
    #   --no-link 可关；--link 额外把 URL 打到 stdout。
    if not args.no_link:
        (outdir / f"{slug}-link.txt").write_text(link + "\n", encoding="utf-8")
        (outdir / f"{slug}.url").write_text("[InternetShortcut]\nURL=" + link + "\n", encoding="utf-8")
        print(f"wrote {outdir / f'{slug}-link.txt'} + .url (one-click web edit link — hand these files over, never paste the URL inline in chat)")
    if args.link or args.open:
        print(link)
    if args.open:
        import webbrowser
        webbrowser.open(link)
    return 0


if __name__ == "__main__":
    sys.exit(main())
