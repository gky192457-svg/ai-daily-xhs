#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模板B · 终端极简（Terminal Minimal）· 程序员审美 · 图文结合
输入: 结构化 JSON（schema 同模板A）
输出: 小红书标准图文笔记 (1080x1440 PNG 若干 + 文案 txt)
用法: python render.py <input.json> [--outdir output_b]

设计语言:
- 底色 GitHub Dark 系近黑 #0D1117，无光晕/无颗粒/无磨砂，极简
- 语法高亮四色: 蓝 #58A6FF(关键字) / 绿 #7EE787(字符串) / 紫 #D2A8FF(函数) / 橙 #FFA657(常量)
- 等宽字体跑英文/数字/命令, Noto Sans SC 跑中文; 注释灰 #8B949E
- 元素: 路径栏 / 行号 / // 注释 / $ 命令 / 细线卡片 / 迷你数据图(图文结合)
"""
import argparse
import datetime
import json
import os
import re

from PIL import Image, ImageDraw, ImageFont

# ---------------- 字体 ----------------
NOTO = r"C:/Windows/Fonts/NotoSansSC-VF.ttf"
BAHN = r"C:/Windows/Fonts/bahnschrift.ttf"
MONO = r"C:/Windows/Fonts/consola.ttf"
MONO_B = r"C:/Windows/Fonts/consolab.ttf"
YAHEI = r"C:/Windows/Fonts/msyh.ttc"

_cache = {}


def _load(path, size, axes=None, fallback=None):
    key = (path, size, tuple(axes) if axes else None, fallback)
    if key in _cache:
        return _cache[key]
    p = path
    if not os.path.exists(p):
        p = fallback or YAHEI
    f = ImageFont.truetype(p, size)
    if axes:
        try:
            f.set_variation_by_axes(axes)
        except Exception:
            try:
                f.set_variation_by_axes([axes[0]])
            except Exception:
                pass
    _cache[key] = f
    return f


def FS(size, weight=400):
    """中文: Noto Sans SC 可变字重"""
    return _load(NOTO, size, [weight], fallback=YAHEI)


def FB(size, weight=700):
    """数字: Bahnschrift"""
    return _load(BAHN, size, [weight], fallback=YAHEI)


def FM(size, bold=False):
    """等宽: Consolas(仅纯拉丁/数字)"""
    return _load(MONO_B if bold else MONO, size, None, fallback=YAHEI)


# ---------------- 调色盘(GitHub Dark 系) ----------------
W, H = 1080, 1440
M = 72

BG     = (13, 17, 23)     # #0D1117
CARD   = (22, 27, 34)     # #161B22
BORDER = (48, 54, 61)     # #30363D
GRID   = (28, 33, 40)     # 点阵
INK    = (10, 13, 18)

TEXT  = (230, 237, 243)   # #E6EDF3
SOFT  = (201, 209, 217)
DIM   = (139, 148, 158)   # #8B949E 注释灰
FAINT = (110, 118, 129)

BLUE   = (88, 166, 255)   # #58A6FF 关键字
GREEN  = (126, 231, 135)  # #7EE787 字符串
PURPLE = (210, 168, 255)  # #D2A8FF 函数
ORANGE = (255, 166, 87)   # #FFA657 常量
RED    = (255, 123, 114)  # #FF7B72

BRAND = "零阶产品谱"
PATH_BAR = "~/zero-order/ai-daily"

TOPIC_ORDER = ["ai_industry_dev", "ai_latest", "ai_product_manager", "ai_salary"]
TOPIC_CN = {
    "ai_industry_dev": "AI 行业发展",
    "ai_latest": "AI 最新动态",
    "ai_product_manager": "AI 产品经理",
    "ai_salary": "AI 行业薪资",
}
TOPIC_KEY = {
    "ai_industry_dev": "industry",
    "ai_latest": "latest",
    "ai_product_manager": "pm",
    "ai_salary": "salary",
}
ACCENT = {
    "ai_industry_dev": BLUE,
    "ai_latest": GREEN,
    "ai_product_manager": PURPLE,
    "ai_salary": ORANGE,
}


# ---------------- 背景: 纯色 + 极淡点阵 ----------------
def make_bg():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    step = 36
    for y in range(step, H, step):
        for x in range(step, W, step):
            d.point((x, y), fill=GRID)
    return img.convert("RGBA")


# ---------------- 细线卡片 ----------------
def _stroke(img, box, color, alpha, width=1):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rectangle(box, outline=tuple(color) + (alpha,), width=width)
    img.alpha_composite(lay)


def card(img, box, accent=None):
    """极简卡片: 1px 灰细线框 + 左侧主题色竖条"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    _stroke(img, (x0, y0, x1, y1), BORDER, 255, 1)
    if accent:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(lay).rectangle((x0, y0 + 1, x0 + 3, y1 - 1), fill=tuple(accent) + (255,))
        img.alpha_composite(lay)


# ---------------- 迷你数据图(图文结合) ----------------
def mini_bars(img, box, color):
    """渐高柱: 资本/增长"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    bw, gap = 18, 14
    base = y1
    hs = [int((y1 - y0) * 0.32), int((y1 - y0) * 0.58), int((y1 - y0) * 0.88)]
    x = x0
    for h in hs:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(lay).rectangle((x, base - h, x + bw, base), fill=tuple(color) + (235,))
        img.alpha_composite(lay)
        x += bw + gap


def mini_line(img, box, color):
    """折线箭头: 发布节奏"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    w_, h_ = x1 - x0, y1 - y0
    pts = [(x0, y0 + h_ * 0.78), (x0 + w_ * 0.32, y0 + h_ * 0.5),
           (x0 + w_ * 0.58, y0 + h_ * 0.62), (x0 + w_, y0 + h_ * 0.12)]
    d.line(pts, fill=tuple(color) + (240,), width=3, joint="curve")
    ex, ey = pts[-1]
    d.ellipse((ex - 6, ey - 6, ex + 6, ey + 6), fill=tuple(color) + (255,))
    img.alpha_composite(lay)


def mini_steps(img, box, color):
    """阶梯上升: 岗位裂变"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    w_, h_ = x1 - x0, y1 - y0
    sw = w_ / 3.4
    for i in range(3):
        sx = x0 + i * sw
        sy = y1 - h_ * (0.3 + 0.3 * i)
        d.rectangle((sx, sy, sx + sw - 5, y1), outline=tuple(color) + (235,), width=2)
        if i == 2:
            d.rectangle((sx, sy, sx + sw - 5, y1), fill=tuple(color) + (60,))
    img.alpha_composite(lay)


def mini_yen(img, box, color):
    """¥ + 横条: 薪资"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.text((x0, y0 - 4), "¥", font=FM(44, True), fill=tuple(color) + (255,), anchor="la")
    bx0 = x0 + 56
    for i, f in enumerate([1.0, 0.72, 0.5]):
        by = y0 + 6 + i * 20
        bw_ = int((x1 - bx0) * f)
        d.rectangle((bx0, by, bx0 + bw_, by + 8), fill=tuple(color) + (200 - i * 45,))
    img.alpha_composite(lay)


MINI = {
    "ai_industry_dev": mini_bars,
    "ai_latest": mini_line,
    "ai_product_manager": mini_steps,
    "ai_salary": mini_yen,
}


# ---------------- 文本工具 ----------------
PUNCT_NO_HEAD = set("。，、；：！？）】」』”’,.!?:;)]}…～%")


def wrap_text(draw, text, font, max_width):
    lines = []
    for para in str(text).split("\n"):
        if para == "":
            lines.append("")
            continue
        cur = ""
        for tok in re.findall(r"[A-Za-z0-9%$_+\-./:]+|.", para):
            test = cur + tok
            if draw.textlength(test, font=font) <= max_width:
                cur = test
            elif cur and tok in PUNCT_NO_HEAD:
                cur += tok
            else:
                if cur:
                    lines.append(cur)
                cur = tok
        lines.append(cur)
    return lines


def serial_of(date_str):
    try:
        y, m, dd = [int(v) for v in date_str.split("-")]
        return (datetime.date(y, m, dd) - datetime.date(y, 1, 1)).days + 1
    except Exception:
        return 1


# ---------------- 封面 ----------------
def draw_cover(date_str, topics_meta, total_pages=6, hooks=None):
    img = make_bg()
    d = ImageDraw.Draw(img)
    hooks = hooks or {}

    # 顶栏: 路径 + 日期 + 细线(像编辑器状态栏)
    d.text((M, 92), PATH_BAR, font=FM(24), fill=DIM, anchor="lm")
    d.text((W - M, 92), date_str, font=FM(24), fill=DIM, anchor="rm")
    d.line((M, 128, W - M, 128), fill=BORDER, width=1)

    # 主标题: 中文大字 + 等宽版本号标签
    d.text((M, 330), "AI 日报", font=FS(132, 900), fill=TEXT, anchor="ls")
    tx = M + d.textlength("AI 日报", font=FS(132, 900)) + 18
    d.text((tx, 316), "v1.0", font=FM(22), fill=DIM, anchor="ls")

    # 注释副标(程序员熟悉的 // 注释)
    d.text((M, 396), "// 过去 24 小时关注的重点", font=FS(30, 400), fill=DIM, anchor="ls")

    # 命令行: ls ./sections/
    d.text((M, 486), "$", font=FM(24, True), fill=GREEN, anchor="lm")
    d.text((M + 22, 486), "ls ./sections/  --sort=hot", font=FM(24), fill=SOFT, anchor="lm")

    # 四张目录卡: 行号 + key + 中文名 + 钩子 + 迷你图
    bw = (W - 2 * M - 20) / 2
    bh = 262
    gx, gy = 20, 20
    bx0, by0 = M, 528
    for i, key in enumerate(TOPIC_ORDER):
        col = ACCENT[key]
        r, c = divmod(i, 2)
        bx = bx0 + c * (bw + gx)
        by = by0 + r * (bh + gy)
        box = (bx, by, bx + bw, by + bh)
        card(img, box, col)
        d = ImageDraw.Draw(img)
        # 行号 + 英文 key(等宽)
        d.text((bx + 26, by + 44), "%02d" % (i + 1), font=FM(24, True), fill=DIM, anchor="lm")
        d.text((bx + 74, by + 44), TOPIC_KEY[key], font=FM(22), fill=DIM, anchor="lm")
        n_txt = (topics_meta or {}).get(key, "")
        if n_txt:
            d.text((bx + bw - 26, by + 44), n_txt, font=FM(20), fill=FAINT, anchor="rm")
        # 中文板块名
        d.text((bx + 26, by + 100), TOPIC_CN[key], font=FS(36, 700), fill=TEXT, anchor="lm")
        # 钩子(注释风)
        hook = (hooks.get(key) or "").strip() or TOPIC_CN[key]
        hl = wrap_text(d, hook, FS(24, 400), bw - 190)[:2]
        yy = by + 156
        for ln in hl:
            d.text((bx + 26, yy), ln, font=FS(24, 400), fill=DIM, anchor="lm")
            yy += 40
        # 迷你数据图(右下)
        MINI[key](img, (bx + bw - 150, by + 128, bx + bw - 30, by + 226), col)
        d = ImageDraw.Draw(img)

    # 底部: $ echo CTA(中文部分走 Noto, 命令部分走等宽) + 细线 + 页脚
    d.text((M, 1216), "$", font=FM(24, True), fill=GREEN, anchor="lm")
    d.text((M + 22, 1216), "echo ", font=FM(24), fill=DIM, anchor="lm")
    cx = M + 22 + d.textlength("echo ", font=FM(24))
    d.text((cx, 1216), '"关注牛马，早八更新，更早知道"', font=FS(24, 400), fill=DIM, anchor="lm")
    d.line((M, H - 96, W - M, H - 96), fill=BORDER, width=1)
    d.text((M, H - 62), "%s · AI DAILY" % BRAND, font=FS(20, 400), fill=FAINT, anchor="lm")
    d.text((W - M, H - 62), "NO.%03d / %s" % (serial_of(date_str), date_str),
           font=FM(20), fill=FAINT, anchor="rm")
    return img


# ---------------- 内页通用 ----------------
def draw_header(d, key, page_index, total, date_str, accent):
    d.text((M, 92), "%s/%s/%02d-%s.md" % (PATH_BAR, date_str, page_index, TOPIC_KEY[key]),
           font=FM(20), fill=DIM, anchor="lm")
    d.text((W - M, 92), "%02d / 04" % page_index, font=FM(24, True), fill=DIM, anchor="rm")
    d.line((M, 128, W - M, 128), fill=BORDER, width=1)

    # markdown 标题: ## + 中文
    d.text((M, 208), "##", font=FM(40, True), fill=accent, anchor="ls")
    d.text((M + 66, 208), TOPIC_CN[key], font=FS(60, 900), fill=TEXT, anchor="ls")
    return 300


def draw_band(img, sumtxt, accent, y=300):
    """// NOTE: 注释块"""
    d = ImageDraw.Draw(img)
    lines = wrap_text(d, sumtxt, FS(26, 400), (W - M - 30) - (M + 46))[:3]
    h = 52 + len(lines) * 42 + 18
    x0, y0, x1, y1 = M, y, W - M, y + h
    _stroke(img, (x0, y0, x1, y1), BORDER, 255, 1)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rectangle((x0, y0 + 1, x0 + 3, y1 - 1), fill=tuple(accent) + (255,))
    img.alpha_composite(lay)
    d = ImageDraw.Draw(img)
    d.text((M + 26, y0 + 36), "// NOTE:", font=FM(22, True), fill=accent, anchor="lm")
    yy = y0 + 72
    for ln in lines:
        d.text((M + 26, yy), ln, font=FS(26, 400), fill=SOFT, anchor="lm")
        yy += 42
    return y1


def item_metrics(d, it, tw):
    hl = wrap_text(d, it.get("headline", ""), FS(29, 700), tw)
    dl = wrap_text(d, it.get("detail", ""), FS(22, 400), tw)
    src = it.get("source", "")
    h = 26 + len(hl) * 40 + 6 + len(dl) * 32 + (26 if src else 4) + 16
    return hl, dl, src, max(h, 120)


def draw_items(img, data, y_start, accent, max_items=4, gap=14):
    d = ImageDraw.Draw(img)
    tw = (W - M - 28) - (M + 92)
    metas = [item_metrics(d, it, tw) for it in data.get("items", [])[:max_items]]
    avail = (H - 120) - y_start
    n = len(metas)
    while n > 1 and sum(m[3] for m in metas[:n]) + gap * (n - 1) > avail:
        n -= 1
    metas = metas[:n]
    if not metas:
        return y_start
    total = sum(m[3] for m in metas)
    extra = max(0, avail - total - gap * (len(metas) - 1))
    pad = min(extra / (len(metas) + 0.6), 18)
    y = y_start + pad
    for i, (hl, dl, src, h) in enumerate(metas):
        card(img, (M, y, W - M, y + h), accent)
        d = ImageDraw.Draw(img)
        d.text((M + 26, y + 30), "%02d" % (i + 1), font=FM(22, True), fill=FAINT, anchor="lm")
        cy = y + 32
        for ln in hl:
            d.text((M + 92, cy), ln, font=FS(29, 700), fill=TEXT, anchor="lm")
            cy += 40
        cy += 4
        for ln in dl:
            d.text((M + 92, cy), ln, font=FS(22, 400), fill=DIM, anchor="lm")
            cy += 32
        if src:
            d.text((M + 92, y + h - 22), "// ", font=FM(18), fill=FAINT, anchor="lm")
            sx = M + 92 + d.textlength("// ", font=FM(18))
            d.text((sx, y + h - 22), src, font=FS(18, 400), fill=FAINT, anchor="lm")
        y += h + gap + pad
    return y


def draw_topic_page(key, data, page_index, total, date_str):
    accent = ACCENT[key]
    img = make_bg()
    d = ImageDraw.Draw(img)
    y = draw_header(d, key, page_index, total, date_str, accent)
    end = draw_band(img, data.get("summary", ""), accent, y)
    draw_items(img, data, end + 22, accent)
    footer(d, page_index + 1, total, accent)
    return img


def footer(d, page, total, accent):
    d.line((M, H - 96, W - M, H - 96), fill=BORDER, width=1)
    d.text((M, H - 62), "%s · AI DAILY" % BRAND, font=FS(20, 400), fill=FAINT, anchor="lm")
    d.text((W - M, H - 62), "P %02d / %02d" % (page, total), font=FM(20), fill=accent, anchor="rm")


# ---------------- 薪资页 ----------------
def draw_chart(img, box, chart, accent):
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    _stroke(img, (x0, y0, x1, y1), BORDER, 255, 1)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rectangle((x0, y0 + 1, x0 + 3, y1 - 1), fill=tuple(accent) + (255,))
    img.alpha_composite(lay)
    d = ImageDraw.Draw(img)
    d.text((x0 + 28, y0 + 40), chart.get("title", "年薪代表值（万元）"),
           font=FS(26, 700), fill=TEXT, anchor="lm")
    d.text((x1 - 28, y0 + 42), "// salary.index", font=FM(17), fill=FAINT, anchor="rm")

    labels = chart.get("labels", [])
    values = chart.get("values", [])
    maxv = max(values) if values else 1
    lab_w = 250
    bx0 = x0 + 28 + lab_w
    bx1 = x1 - 28 - 84
    rows = max(len(labels), 1)
    top = y0 + 88
    avail = (y1 - 26) - top
    rh = min(avail / rows, 76)
    for i, (lab, val) in enumerate(zip(labels, values)):
        cy = top + rh * i + rh / 2
        ll = wrap_text(d, lab, FS(21, 400), lab_w - 20)[:2]
        ty = cy - (len(ll) - 1) * 14
        for ln in ll:
            d.text((x0 + 28, ty), ln, font=FS(21, 400), fill=SOFT, anchor="lm")
            ty += 28
        # 轨道 + 填充(细线程序员风)
        d.line((bx0, cy, bx1, cy), fill=BORDER, width=1)
        fw = max(int((bx1 - bx0) * (val / maxv)), 12)
        d.line((bx0, cy, bx0 + fw, cy), fill=accent, width=7)
        d.text((bx1 + 16, cy), str(val), font=FM(24, True), fill=TEXT, anchor="lm")


def draw_salary_page(data, page_index, total, date_str):
    accent = ACCENT["ai_salary"]
    img = make_bg()
    d = ImageDraw.Draw(img)
    y = draw_header(d, "ai_salary", page_index, total, date_str, accent)
    end = draw_band(img, data.get("summary", ""), accent, y)

    y = end + 22
    chart = data.get("chart")
    if chart:
        tw = (W - M - 28) - (M + 92)
        items = data.get("items", [])[:2]
        items_h = sum(item_metrics(d, it, tw)[3] for it in items) + 14 * max(len(items) - 1, 0)
        ch = (H - 120) - y - (items_h + 22 if items else 0)
        ch = max(340, min(ch, 560))
        draw_chart(img, (M, y, W - M, y + ch), chart, accent)
        y += ch + 20
    draw_items(img, data, y, accent, max_items=2)
    footer(d, page_index + 1, total, accent)
    return img


# ---------------- 总结页(CHANGELOG 风) ----------------
def draw_summary_page(takeaways, hashtags, date_str, total):
    img = make_bg()
    d = ImageDraw.Draw(img)
    d.text((M, 92), PATH_BAR, font=FM(24), fill=DIM, anchor="lm")
    d.text((W - M, 92), date_str, font=FM(24), fill=DIM, anchor="rm")
    d.line((M, 128, W - M, 128), fill=BORDER, width=1)

    d.text((M, 208), "##", font=FM(40, True), fill=GREEN, anchor="ls")
    d.text((M + 66, 208), "今日要点", font=FS(60, 900), fill=TEXT, anchor="ls")
    d.text((M, 252), "// CHANGELOG · daily digest", font=FM(20), fill=DIM, anchor="ls")

    y = 316
    cycle = [BLUE, GREEN, PURPLE, ORANGE, BLUE]
    rows = takeaways[:5]
    for i, t in enumerate(rows):
        col = cycle[i % len(cycle)]
        lines = wrap_text(d, t, FS(25, 500), (W - M - 40) - (M + 96))[:2]
        h = 44 + len(lines) * 38 + 26
        card(img, (M, y, W - M, y + h), col)
        d = ImageDraw.Draw(img)
        d.text((M + 28, y + 34), "+", font=FM(26, True), fill=col, anchor="lm")
        yy = y + 40
        for ln in lines:
            d.text((M + 96, yy), ln, font=FS(25, 500), fill=SOFT, anchor="lm")
            yy += 38
        y += h + 14

    # 互动区: $ comment
    y += 8
    d.text((M, y + 40), "$", font=FM(24, True), fill=GREEN, anchor="lm")
    d.text((M + 22, y + 40), "你怎么看？评论区唠唠", font=FS(28, 700), fill=TEXT, anchor="lm")
    d.text((M + 22, y + 84), "点赞 · 收藏 · 关注，AI 圈大事不迷路", font=FS(22, 400), fill=DIM, anchor="lm")
    d.line((M, y + 118, W - M, y + 118), fill=BORDER, width=1)
    d.text((M, y + 150), " ".join(hashtags[:6]), font=FS(19, 400), fill=FAINT, anchor="lm")

    d.line((M, H - 96, W - M, H - 96), fill=BORDER, width=1)
    d.text((M, H - 62), "NO.%03d / %s / %s" % (serial_of(date_str), date_str, BRAND),
           font=FS(20, 400), fill=FAINT, anchor="lm")
    return img


# ---------------- 主流程 ----------------
def render(input_path, outdir):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs(outdir, exist_ok=True)
    date_str = data.get("date", "")
    topics = data.get("topics", {})

    meta = {}
    hooks = {}
    for k, v in topics.items():
        n = len(v.get("items", []) or [])
        meta[k] = "%d条" % n if n else ""
        hk = (v.get("cover_hook") or "").strip()
        if not hk:
            items = v.get("items") or []
            hk = (items[0].get("headline", "") if items else "")[:24]
        hooks[k] = hk

    total = 1 + len([k for k in TOPIC_ORDER if k in topics]) + 1
    pages = [("cover", draw_cover(date_str, meta, total, hooks))]

    pidx = 1
    for key in TOPIC_ORDER:
        if key not in topics:
            continue
        if key == "ai_salary":
            pages.append((key, draw_salary_page(topics[key], pidx, total, date_str)))
        else:
            pages.append((key, draw_topic_page(key, topics[key], pidx, total, date_str)))
        pidx += 1

    takeaways = data.get("takeaways", [])
    hashtags = data.get("hashtags", [])
    pages.append(("summary", draw_summary_page(takeaways, hashtags, date_str, total)))

    saved = []
    for name, img in pages:
        path = os.path.join(outdir, "%s.png" % name)
        img.convert("RGB").save(path, "PNG")
        saved.append(path)

    caption = data.get("caption", "")
    with open(os.path.join(outdir, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(caption + "\n\n" + " ".join(hashtags) + "\n")

    print("已生成 %d 张图片:" % len(saved))
    for s in saved:
        print("  ", s)
    print("文案: ", os.path.join(outdir, "caption.txt"))
    return saved


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="输入 JSON 路径")
    ap.add_argument("--outdir", default="output_b", help="输出目录")
    args = ap.parse_args()
    render(args.input, args.outdir)
