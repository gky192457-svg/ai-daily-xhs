#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI 日报渲染管线 · 「零阶产品谱」赛博夜城 · 轻磨砂版
输入: 结构化 JSON (见 template_sample.json)
输出: 小红书标准图文笔记 (1080x1440 PNG 若干 + 文案 txt)
依赖: pillow
用法: python render.py <input.json> [--outdir output]

视觉规范 (v6, 从账号主页截图直接采色):
- 底: 深蓝 #05071E -> 靛蓝 #0B103C -> 暗紫 #1C103E 垂直渐变
- 三层柔和径向光晕(青蓝/紫/暖黄) + 胶片颗粒 + 边缘暗角 -> 夜景景深
- 面板: 仅'一丢丢'磨砂(极淡投影 + 细描边 + 竖直渐变染色) + 边缘亮色高光(rim light, 自上而下渐隐), 不用高饱和平涂
- 四主题强调色(偏亮色相): 青蓝 #4EA8FF / 翠绿 #35DDA0 / 紫 #9B7BFF / 橙 #FF8A42
- 字体: Noto Sans SC 可变字重 + Bahnschrift(DIN 数字) + Consolas(小标)
"""
import argparse
import datetime
import json
import os
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

# ---------------- 字体 ----------------
NOTO  = r"C:/Windows/Fonts/NotoSansSC-VF.ttf"
BAHN  = r"C:/Windows/Fonts/bahnschrift.ttf"
MONO  = r"C:/Windows/Fonts/consola.ttf"
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
    """中文 / 标题: Noto Sans SC 可变字重(100-900)"""
    return _load(NOTO, size, [weight], fallback=YAHEI)


def FB(size, weight=700):
    """数字: Bahnschrift (DIN 风)"""
    return _load(BAHN, size, [weight], fallback=YAHEI)


def FM(size, bold=False):
    """等宽小标: Consolas(仅纯拉丁/数字)"""
    return _load(MONO_B if bold else MONO, size, None, fallback=YAHEI)


# ---------------- 画布 / 调色盘(主页采色) ----------------
W, H = 1080, 1440
M = 76

BG_TOP = (5, 7, 30)        # #05071E
BG_MID = (11, 16, 60)      # #0B103C
BG_BOT = (28, 16, 62)      # #1C103E
INK    = (2, 4, 16)

TEXT  = (238, 238, 255)    # #EEEEFF
SOFT  = (214, 214, 242)
DIM   = (150, 148, 196)
FAINT = (104, 102, 148)
GRAY70 = (176, 176, 192)   # 70% 灰(偏冷, 融入夜空)
GRAY50 = (130, 132, 154)   # 50% 灰(更淡, 用于封面底部引导)
DEEP_BLUE = (46, 102, 226)  # 深蓝(蓝→深蓝渐变线尾端, 保留可辨识度)
LINE  = (54, 52, 104)

AZURE  = (78, 168, 255)    # #4EA8FF 青蓝
CYAN   = (59, 224, 255)    # #3BE0FF 青
GREEN  = (53, 221, 160)    # #35DDA0 翠绿
VIOLET = (155, 123, 255)   # #9B7BFF 紫
ORANGE = (255, 138, 66)    # #FF8A42 橙

TOPIC_ORDER = ["ai_industry_dev", "ai_latest", "ai_product_manager", "ai_salary"]
TOPIC_CN = {
    "ai_industry_dev": "AI 行业发展",
    "ai_latest": "AI 最新动态",
    "ai_product_manager": "AI 产品经理",
    "ai_salary": "AI 行业薪资",
}
ACCENT = {
    "ai_industry_dev": AZURE,
    "ai_latest": GREEN,
    "ai_product_manager": VIOLET,
    "ai_salary": ORANGE,
}

# 封面四色块: (顶部亮色, 底部深色) —— 更亮的色相, 各自独立可辨
TOPIC_GRAD = {
    "ai_industry_dev": ((78, 168, 255), (40, 104, 224)),
    "ai_latest": ((58, 226, 165), (18, 163, 118)),
    "ai_product_manager": ((170, 140, 255), (118, 82, 236)),
    "ai_salary": ((255, 168, 96), (238, 112, 40)),
}


# ---------------- 背景 ----------------
def _vgrad(size, stops):
    w, h = size
    img = Image.new("RGB", (1, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        col = stops[-1][1]
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                k = 0 if p1 == p0 else (t - p0) / (p1 - p0)
                col = tuple(int(c0[j] + (c1[j] - c0[j]) * k) for j in range(3))
                break
        d.point((0, y), fill=col)
    return img.resize((w, h), Image.BILINEAR)


def _glow(base, center, size, color, alpha):
    rad = Image.radial_gradient("L").resize((size, size))
    rad = ImageOps.invert(rad)
    a = rad.point(lambda v: int(v * alpha / 255))
    layer = Image.new("RGBA", (size, size), tuple(color) + (0,))
    layer.putalpha(a)
    base.alpha_composite(layer, (int(center[0] - size / 2), int(center[1] - size / 2)))


def _grain(img, amount=22):
    noise = Image.effect_noise((W, H), 26).convert("L")
    a = noise.point(lambda v: int(abs(v - 128) * amount / 128))
    spk = Image.new("RGBA", (W, H), (198, 202, 236, 255))
    spk.putalpha(a)
    img.alpha_composite(spk)


def _vignette(img, strength=86):
    v = Image.radial_gradient("L").resize((W, H))
    a = v.point(lambda p: int(p * strength / 255))
    dark = Image.new("RGBA", (W, H), INK + (255,))
    dark.putalpha(a)
    img.alpha_composite(dark)


def make_bg(c1=AZURE, c2=VIOLET, c3=ORANGE):
    base = _vgrad((W, H), [(0.0, BG_TOP), (0.46, BG_MID), (1.0, BG_BOT)]).convert("RGBA")
    _glow(base, (W * 0.85, H * 0.09), 1150, c1, 42)
    _glow(base, (W * 0.04, H * 0.66), 1250, c2, 36)
    _glow(base, (W * 0.55, H * 1.02), 1350, c3, 22)
    _grain(base)
    _vignette(base)
    return base


# ---------------- 磨砂玻璃工具(需在 RGBA 图上合成) ----------------
def _fill_alpha(img, box, color, alpha, radius=0):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle(box, radius=radius, fill=tuple(color) + (alpha,))
    img.alpha_composite(lay)


def _stroke(img, box, color, alpha, width=2, radius=0):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle(box, radius=radius,
                                          outline=tuple(color) + (alpha,), width=width)
    img.alpha_composite(lay)


def _hline_grad(img, x0, x1, y, c1, c2, width=2, alpha=255):
    """水平细线: 颜色沿长度从 c1 渐变到 c2(蓝 -> 深蓝), 低开销逐列绘制"""
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    n = max(1, x1 - x0)
    for i in range(n):
        t = i / n
        col = tuple(int(c1[j] + (c2[j] - c1[j]) * t) for j in range(3))
        ld.line((x0 + i, y, x0 + i, y + width - 1), fill=col + (alpha,))
    img.alpha_composite(lay)


def _vgrad_block(img, box, color, a_top, a_bot, radius=0):
    """竖直渐变玻璃块: 顶部更透亮, 底部渐深 (直角块)"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    h = max(2, y1 - y0)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    for i in range(h):
        k = i / (h - 1)
        a = int(a_top + (a_bot - a_top) * k)
        ld.line((x0, y0 + i, x1, y0 + i), fill=tuple(color) + (a,))
    img.alpha_composite(lay)


def _tint(color, k=0.3, base=200):
    """把颜色向白色提亮, 用作边缘高光"""
    return tuple(min(255, int(c * (1 - k) + base * k)) for c in color)


def _grad_block(img, box, c_top, c_bot, radius=0):
    """实色竖直渐变块(顶部亮 -> 底部深), 颜色通透不发闷"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    w, h = max(1, x1 - x0), max(2, y1 - y0)
    strip = Image.new("RGB", (1, h))
    sd = ImageDraw.Draw(strip)
    for i in range(h):
        k = i / (h - 1)
        sd.point((0, i), fill=tuple(int(c_top[j] + (c_bot[j] - c_top[j]) * k)
                                     for j in range(3)))
    g = strip.resize((w, h), Image.BILINEAR).convert("RGBA")
    if radius:
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1),
                                               radius=radius, fill=255)
        img.paste(g, (x0, y0), mask)
    else:
        img.alpha_composite(g, (x0, y0))


def _rim(img, box, color, alpha, radius=0, width=2, fade=0.62):
    """边缘亮色高光: 沿轮廓画一条亮线, 自上而下渐隐(只留顶部一段)"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle((x0, y0, x1, y1), radius=radius,
                                          outline=tuple(color) + (255,), width=width)
    h = max(1, y1 - y0)
    fh = max(1, int(h * fade))
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    for i in range(fh):
        md.line((x0 - 4, y0 + i, x1 + 4, y0 + i), fill=int(alpha * (1 - i / fh)))
    lay.putalpha(ImageChops.multiply(lay.split()[3], mask))
    img.alpha_composite(lay)


def glass(img, box, color=(96, 120, 225), radius=16, a_top=44, a_bot=28,
          border=True, glow=False, glow_a=14, top_line=None, rim=0, rim_fade=0.62):
    """面板: 只留'一丢丢'磨砂感——极淡投影 + 竖直渐变填充 + 细描边 + 边缘亮色高光"""
    x0, y0, x1, y1 = box
    if glow:
        _glow(img, ((x0 + x1) / 2, (y0 + y1) / 2),
              int(max(x1 - x0, y1 - y0) * 1.2), color, glow_a)
    # 一丢丢磨砂: 极淡投影
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((x0 + 2, y0 + 5, x1 + 2, y1 + 5),
                                         radius=radius, fill=(0, 0, 0, 46))
    sh = sh.filter(ImageFilter.GaussianBlur(7))
    img.alpha_composite(sh)

    _vgrad_block(img, box, color, a_top, a_bot, radius=radius)
    if border:
        bd = tuple(min(255, int(c * 0.5 + 120)) for c in color)
        _stroke(img, box, bd, 64, width=1, radius=radius)
    # 边缘亮色高光: 亮化后的主题色, 顶部最亮、向下渐隐
    if rim:
        ec = tuple(min(255, int(c * 0.35 + 168)) for c in color)
        _rim(img, box, ec, rim, radius=radius, width=2, fade=rim_fade)
    # 顶边高光(磨砂感来源)默认关闭, 仅显式传入时才画
    if top_line:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(lay).line((x0 + 2, y0 + 1, x1 - 2, y0 + 1),
                                 fill=tuple(top_line) + (235,), width=3)
        img.alpha_composite(lay)


def text_glow(base, xy, text, font, color, blur=26, strength=70, anchor="ls"):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=font, fill=tuple(color) + (255,), anchor=anchor)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    a = layer.split()[3].point(lambda v: int(v * strength / 255))
    layer.putalpha(a)
    base.alpha_composite(layer)


# ---------------- 文本 / 版式工具 ----------------
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


def frame(img):
    """极细外框, 编辑式海报感"""
    _stroke(img, (38, 38, W - 38, H - 38), (140, 140, 210), 42, width=1)


def top_bar(d, right_text, accent=AZURE):
    y = 96
    d.text((M, y), "零阶产品谱", font=FS(30, 800), fill=accent, anchor="lm")
    x = M + d.textlength("零阶产品谱", font=FS(30, 800)) + 16
    d.text((x, y + 1), "/ AI DAILY", font=FM(24), fill=FAINT, anchor="lm")
    d.text((W - M, y), right_text, font=FM(24), fill=FAINT, anchor="rm")
    d.line((M, 140, W - M, 140), fill=LINE, width=1)


def footer(d, page, total, accent=AZURE):
    d.line((M, H - 104, W - M, H - 104), fill=LINE, width=1)
    d.text((M, H - 68), "零阶产品谱 · AI DAILY", font=FS(20, 500), fill=FAINT, anchor="lm")
    d.text((W - M, H - 68), "P %02d / %02d" % (page, total), font=FB(22, 700),
           fill=accent, anchor="rm")


# ---------------- 封面 ----------------
def draw_cover(date_str, topics_meta, total_pages=6, hooks=None):
    img = make_bg(AZURE, VIOLET, ORANGE)
    d = ImageDraw.Draw(img)
    frame(img)
    top_bar(d, date_str)

    # 主标题 AI 日报
    fh = FS(148, 900)
    text_glow(img, (M - 4, 340), "AI", fh, AZURE, blur=30, strength=64, anchor="ls")
    d.text((M, 340), "AI", font=fh, fill=AZURE, anchor="ls")
    ax = M + d.textlength("AI", font=fh) + 10
    d.text((ax, 340), "日报", font=fh, fill=TEXT, anchor="ls")

    # 副标题 + 分隔短线
    d.text((M, 404), "过去 24 小时关注的重点", font=FS(32, 500), fill=DIM, anchor="ls")
    d.line((M, 440, M + 66, 440), fill=AZURE, width=3)

    # 今日速览标签
    d.text((M, 486), "今日速览", font=FS(25, 700), fill=SOFT, anchor="lm")
    d.text((W - M, 486), "TODAY / 04 SECTIONS", font=FM(19), fill=FAINT, anchor="rm")

    # 四个直角色块: 亮色相实色渐变 + 细描边 + 边缘高光
    # 版式参考小红书同类爆款封面: 每格不是"板块名", 而是"今日最炸的一条钩子"——目录即预告
    hooks = hooks or {}
    bw = (W - 2 * M - 20) / 2
    bh = 268
    gx, gy = 20, 22
    bx0, by0 = M, 522
    for i, key in enumerate(TOPIC_ORDER):
        ct, cb = TOPIC_GRAD[key]
        r, c = divmod(i, 2)
        bx = bx0 + c * (bw + gx)
        by = by0 + r * (bh + gy)
        box = (bx, by, bx + bw, by + bh)
        _grad_block(img, box, ct, cb)
        # 底部轻微压暗, 让白字在任何色相上都清晰
        _vgrad_block(img, (bx, by + bh * 0.5, bx + bw, by + bh), INK, 0, 78)
        _stroke(img, box, _tint(ct, 0.34, 210), 130, width=2)
        _rim(img, box, _tint(ct, 0.5, 235), 225, width=2, fade=0.8)

        # 序号: 白色半透明直角小方块 + 白字(爆款封面的视觉锚点)
        _fill_alpha(img, (bx + 26, by + 26, bx + 70, by + 70), (255, 255, 255), 48)
        d = ImageDraw.Draw(img)
        d.text((bx + 48, by + 48), "0%d" % (i + 1), font=FB(26, 700),
               fill=(255, 255, 255), anchor="mm")
        # 板块名
        d.text((bx + 86, by + 48), TOPIC_CN[key], font=FS(32, 800),
               fill=(255, 255, 255), anchor="lm")
        # 右上角条数(高级感: 小字、淡色)
        n_txt = (topics_meta or {}).get(key, "")
        if n_txt:
            d.text((bx + bw - 26, by + 48), n_txt, font=FS(17, 500),
                   fill=(196, 202, 224), anchor="rm")
        # 序号栏 / 钩子栏 之间的细分隔线(图层合成, 避免直接画成实心白线)
        _fill_alpha(img, (bx + 26, by + 94, bx + bw - 26, by + 95), (255, 255, 255), 66)

        # 今日钩子: 1-2 行, 带具体数字/事件(高级感: 字号小、颜色淡)
        d = ImageDraw.Draw(img)
        hook = (hooks.get(key) or "").strip()
        if not hook:
            hook = TOPIC_CN[key]
        hl = wrap_text(d, hook, FS(27, 500), bw - 56)[:2]
        yy = by + (154 if len(hl) > 1 else 176)
        for ln in hl:
            d.text((bx + 26, yy), ln, font=FS(27, 500),
                   fill=(210, 216, 238), anchor="lm")
            yy += 42

    # 关注引导: 无框、无底色, 50% 灰字单行 + 蓝->深蓝细渐变线(对齐四块左右边界)
    cta_y = 1204
    d.text((W / 2, cta_y), "关注牛马，早八更新，更早知道",
           font=FS(34, 600), fill=GRAY50, anchor="mm")
    _hline_grad(img, M, W - M, cta_y + 46, AZURE, DEEP_BLUE, width=2, alpha=210)

    # 底部信息栏: 与顶部页眉同构(细分隔线 + 左编号/日期 + 右出品)
    fy = H - 104
    d.line((M, fy, W - M, fy), fill=LINE, width=1)
    d.text((M, fy + 36), "NO.%03d  /  %s" % (serial_of(date_str), date_str),
           font=FM(20), fill=FAINT, anchor="lm")
    d.text((W - M, fy + 36), "零阶产品谱出品", font=FS(20, 500), fill=FAINT, anchor="rm")
    return img


# ---------------- 主题页 ----------------
def draw_header(d, key, page_index, total, date_str, accent):
    y = 96
    d.text((M, y), "AI 日报", font=FS(26, 700), fill=accent, anchor="lm")
    d.text((M, y + 34), "零阶产品谱", font=FS(18, 500), fill=FAINT, anchor="lm")
    d.text((W - M, y), "0%d / 04" % page_index, font=FB(24, 700), fill=DIM, anchor="rm")
    d.text((W - M, y + 34), date_str, font=FM(18), fill=FAINT, anchor="rm")
    d.line((M, 156, W - M, 156), fill=LINE, width=1)

    d.text((M, 236), TOPIC_CN[key], font=FS(62, 900), fill=TEXT, anchor="lm")
    d.line((M, 286, M + 92, 286), fill=accent, width=4)
    return 322


def draw_band(img, sumtxt, accent, y=322):
    """『小编说』磨砂玻璃引文块"""
    d = ImageDraw.Draw(img)
    lines = wrap_text(d, sumtxt, FS(28, 400), (W - M - 36) - (M + 54))[:3]
    h = 66 + len(lines) * 44
    glass(img, (M, y, W - M, y + h), color=accent, radius=14,
          a_top=52, a_bot=30, rim=118, rim_fade=0.5)
    d = ImageDraw.Draw(img)
    d.line((M + 22, y + 22, M + 22, y + h - 22), fill=accent, width=4)
    d.text((M + 54, y + 40), "小编说", font=FS(21, 800), fill=accent, anchor="lm")
    yy = y + 74
    for ln in lines:
        d.text((M + 54, yy), ln, font=FS(28, 400), fill=SOFT, anchor="lm")
        yy += 44
    return y + h


def item_metrics(d, it, tw):
    hl = wrap_text(d, it.get("headline", ""), FS(31, 700), tw)
    dl = wrap_text(d, it.get("detail", ""), FS(23, 400), tw)
    src = it.get("source", "")
    h = 22 + len(hl) * 44 + 4 + len(dl) * 33 + (22 if src else 2) + 16
    return hl, dl, src, max(h, 136)


def draw_items(img, data, y_start, accent, max_items=4, gap=16):
    d = ImageDraw.Draw(img)
    tw = (W - M - 26) - (M + 106)
    metas = [item_metrics(d, it, tw) for it in data.get("items", [])[:max_items]]
    avail = (H - 130) - y_start
    n = len(metas)
    while n > 1 and sum(m[3] for m in metas[:n]) + gap * (n - 1) > avail:
        n -= 1
    metas = metas[:n]
    if not metas:
        return y_start

    total = sum(m[3] for m in metas)
    extra = max(0, avail - total - gap * (len(metas) - 1))
    pad = min(extra / (len(metas) + 0.6), 20)
    y = y_start + pad
    for i, (hl, dl, src, h) in enumerate(metas):
        glass(img, (M, y, W - M, y + h), color=accent, radius=14,
              a_top=46, a_bot=26, glow=False, rim=104, rim_fade=0.5)
        d = ImageDraw.Draw(img)
        d.line((M, y + 18, M, y + h - 18), fill=accent, width=4)
        d.text((M + 30, y + 32), "%02d" % (i + 1), font=FB(22, 700), fill=accent, anchor="lm")
        cy = y + 34
        for ln in hl:
            d.text((M + 106, cy), ln, font=FS(31, 700), fill=TEXT, anchor="lm")
            cy += 44
        cy += 2
        for ln in dl:
            d.text((M + 106, cy), ln, font=FS(23, 400), fill=DIM, anchor="lm")
            cy += 33
        if src:
            d.text((M + 106, y + h - 26), "来源 · " + src, font=FS(18, 400),
                   fill=FAINT, anchor="lm")
        y += h + gap + pad
    return y


def draw_topic_page(key, data, page_index, total, date_str):
    accent = ACCENT[key]
    img = make_bg(accent, VIOLET, ORANGE)
    frame(img)
    d = ImageDraw.Draw(img)
    draw_header(d, key, page_index, total, date_str, accent)
    end = draw_band(img, data.get("summary", ""), accent)
    draw_items(img, data, end + 26, accent)
    footer(d, page_index + 1, total, accent)
    return img


# ---------------- 薪资页(含图表) ----------------
def draw_chart(img, box, chart, accent):
    x0, y0, x1, y1 = box
    glass(img, box, color=accent, radius=14, a_top=46, a_bot=26, glow=False,
          rim=104, rim_fade=0.5)
    d = ImageDraw.Draw(img)
    d.text((x0 + 32, y0 + 42), chart.get("title", "年薪代表值（万元）"),
           font=FS(26, 700), fill=TEXT, anchor="lm")
    d.text((x1 - 32, y0 + 43), "SALARY INDEX", font=FM(17), fill=FAINT, anchor="rm")

    labels = chart.get("labels", [])
    values = chart.get("values", [])
    maxv = max(values) if values else 1
    lab_w = 264
    bx0 = x0 + 32 + lab_w
    bx1 = x1 - 32 - 82
    rows = max(len(labels), 1)
    top = y0 + 90
    avail = (y1 - 28) - top
    rh = min(avail / rows, 82)
    for i, (lab, val) in enumerate(zip(labels, values)):
        cy = top + rh * i + rh / 2
        ll = wrap_text(d, lab, FS(22, 500), lab_w - 26)[:2]
        ty = cy - (len(ll) - 1) * 15
        for ln in ll:
            d.text((x0 + 32, ty), ln, font=FS(22, 500), fill=SOFT, anchor="lm")
            ty += 30
        _fill_alpha(img, (bx0, cy - 11, bx1, cy + 11), (60, 62, 120), 90, radius=11)
        fw = max(int((bx1 - bx0) * (val / maxv)), 16)
        _fill_alpha(img, (bx0, cy - 11, bx0 + fw, cy + 11), accent, 235, radius=11)
        d = ImageDraw.Draw(img)
        d.text((bx1 + 18, cy), str(val), font=FB(26, 700), fill=TEXT, anchor="lm")


def draw_salary_page(data, page_index, total, date_str):
    accent = ACCENT["ai_salary"]
    img = make_bg(accent, VIOLET, AZURE)
    frame(img)
    d = ImageDraw.Draw(img)
    draw_header(d, "ai_salary", page_index, total, date_str, accent)
    end = draw_band(img, data.get("summary", ""), accent)

    y = end + 26
    chart = data.get("chart")
    if chart:
        tw = (W - M - 26) - (M + 106)
        items = data.get("items", [])[:2]
        items_h = sum(item_metrics(d, it, tw)[3] for it in items) + 16 * max(len(items) - 1, 0)
        ch = (H - 130) - y - (items_h + 26 if items else 0)
        ch = max(360, min(ch, 590))
        draw_chart(img, (M, y, W - M, y + ch), chart, accent)
        y += ch + 22

    draw_items(img, data, y, accent, max_items=2)
    d = ImageDraw.Draw(img)
    footer(d, page_index + 1, total, accent)
    return img


# ---------------- 总结页 ----------------
def draw_summary_page(takeaways, hashtags, date_str, total):
    img = make_bg(AZURE, VIOLET, ORANGE)
    frame(img)
    d = ImageDraw.Draw(img)

    top_bar(d, date_str)
    d.text((M, 236), "今日要点", font=FS(62, 900), fill=TEXT, anchor="lm")
    d.text((W - M, 236), "TOP TAKEAWAYS", font=FM(20), fill=FAINT, anchor="rm")
    d.line((M, 286, M + 92, 286), fill=AZURE, width=4)

    y = 336
    cycle = [AZURE, GREEN, VIOLET, ORANGE]
    rows = takeaways[:5]
    row_h, gap = 126, 20
    for i, t in enumerate(rows):
        col = cycle[i % len(cycle)]
        glass(img, (M, y, W - M, y + row_h), color=col, radius=14,
              a_top=44, a_bot=24, glow=False, rim=104, rim_fade=0.5)
        d = ImageDraw.Draw(img)
        d.text((M + 40, y + row_h / 2), "%02d" % (i + 1), font=FB(36, 700),
               fill=col, anchor="lm")
        d.line((M + 96, y + 26, M + 96, y + row_h - 26), fill=LINE, width=1)
        lines = wrap_text(d, t, FS(27, 600), (W - M - 34) - (M + 126))[:2]
        yy = y + row_h / 2 - (len(lines) - 1) * 22
        for ln in lines:
            d.text((M + 126, yy), ln, font=FS(27, 600), fill=TEXT, anchor="lm")
            yy += 44
        y += row_h + gap

    y += 6
    glass(img, (M, y, W - M, y + 128), color=CYAN, radius=14,
          a_top=50, a_bot=28, rim=118, rim_fade=0.5)
    d = ImageDraw.Draw(img)
    d.line((M + 22, y + 22, M + 22, y + 106), fill=CYAN, width=4)
    d.text((M + 54, y + 46), "你怎么看？评论区唠唠", font=FS(31, 800), fill=TEXT, anchor="lm")
    d.text((M + 54, y + 92), "点赞 · 收藏 · 关注，AI 圈大事不迷路",
           font=FS(22, 500), fill=DIM, anchor="lm")

    ht = "  ".join(hashtags[:6])
    d.text((M, y + 172), ht, font=FS(20, 400), fill=FAINT, anchor="lm")

    d.text((M, H - 68), "NO.%03d  /  %s  /  零阶产品谱出品" % (serial_of(date_str), date_str),
           font=FS(20, 500), fill=FAINT, anchor="lm")
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
        meta[k] = "%02d 条" % n if n else ""
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
    ap.add_argument("--outdir", default="output", help="输出目录")
    args = ap.parse_args()
    render(args.input, args.outdir)
