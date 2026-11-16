#!/usr/bin/env python3
"""Vẽ ảnh "code snap" (khung cửa sổ tối, tô màu cú pháp, số dòng) cho các khối mã trong báo cáo.

  python tools/make_snaps.py

Ảnh ghi vào Images/code/. Mọi ảnh dùng chung tỉ lệ (DPI ghi trong file PNG) nên khi chèn bằng
\\includegraphics không cần width, cỡ chữ trong PDF giống nhau ở mọi ảnh.
Tệp dài hơn MAX_LINES dòng được chia thành nhiều ảnh, số dòng chạy tiếp.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import BashLexer, PythonLexer
from pygments.styles import get_style_by_name

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "Images", "code")
SNIP = os.path.join(ROOT, "tools", "snippets")

# (tệp nguồn, tên hiện trên thanh tiêu đề, tên ảnh, lexer)
SNAPS = [
    ("code/flproto.py", "flproto.py", "flproto", PythonLexer),
    ("code/fl_server.py", "fl_server.py", "fl_server", PythonLexer),
    ("code/fl_client.py", "fl_client.py", "fl_client", PythonLexer),
    ("code/topo.py", "topo.py", "topo", PythonLexer),
    ("code/run_experiments.py", "run_experiments.py", "run_experiments", PythonLexer),
    ("code/summarize.py", "summarize.py", "summarize", PythonLexer),
    ("code/model.py", "model.py", "model", PythonLexer),
    ("tools/snippets/setup.sh", "Terminal: cài đặt và chạy thí nghiệm", "setup", BashLexer),
    ("tools/snippets/run_all.sh", "Terminal: chạy toàn bộ kịch bản", "run_all", BashLexer),
    ("tools/snippets/tcpdump.sh", "Mininet CLI: bắt gói", "tcpdump", BashLexer),
]

SCALE = 2
FONT = "C:/Windows/Fonts/CascadiaMono.ttf"
UI_FONT = "C:/Windows/Fonts/segoeui.ttf"
FONT_PX = 15 * SCALE
LINE_H = int(FONT_PX * 1.45)
FULL_COLS = 116            # độ rộng ảnh mã nguồn đầy đủ (dòng dài nhất 115 ký tự)
PAGE_CM = 14.8             # ảnh rộng FULL_COLS cột sẽ rộng chừng này trong PDF
MAX_LINES = 60
PAD = 22 * SCALE           # lề trong khung
BAR_H = 34 * SCALE         # thanh tiêu đề
MARGIN = 12 * SCALE        # lề ngoài, chỗ cho bóng đổ
RADIUS = 10 * SCALE

style = get_style_by_name("one-dark")
BG = style.background_color
font = ImageFont.truetype(FONT, FONT_PX)
ui_font = ImageFont.truetype(UI_FONT, 13 * SCALE)
CHAR_W = font.getlength("M")
GUTTER_COLS = 4


def color_of(ttype):
    while ttype is not None:
        st = style.style_for_token(ttype)
        if st["color"]:
            return "#" + st["color"]
        ttype = ttype.parent
    return "#abb2bf"


def colored_lines(text, lexer):
    """Trả về danh sách dòng, mỗi dòng là danh sách (chuỗi, màu)."""
    lines, cur = [], []
    for ttype, val in lex(text, lexer()):
        col = color_of(ttype)
        parts = val.expandtabs(4).split("\n")
        for i, p in enumerate(parts):
            if i:
                lines.append(cur)
                cur = []
            if p:
                cur.append((p, col))
    if cur:
        lines.append(cur)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def canvas_width(cols):
    return int(2 * MARGIN + 2 * PAD + (GUTTER_COLS + 2 + cols) * CHAR_W)


def render(lines, first_no, title, cols, path):
    w = canvas_width(cols)
    h = 2 * MARGIN + BAR_H + 2 * PAD + len(lines) * LINE_H - (LINE_H - FONT_PX)
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    # bóng đổ mềm: vài lớp viền xám nhạt
    for i in range(6, 0, -1):
        g = 255 - 6 * (7 - i)
        d.rounded_rectangle([MARGIN - i, MARGIN - i + 3, w - MARGIN + i, h - MARGIN + i + 3],
                            RADIUS + i, fill=(g, g, g))
    d.rounded_rectangle([MARGIN, MARGIN, w - MARGIN, h - MARGIN], RADIUS, fill=BG)
    # ba nút cửa sổ
    cy = MARGIN + BAR_H // 2
    for k, c in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        cx = MARGIN + PAD + k * 20 * SCALE
        r = 6 * SCALE
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    tw = d.textlength(title, font=ui_font)
    d.text(((w - tw) / 2, cy), title, font=ui_font, fill="#8b93a1", anchor="lm")
    # mã
    x0 = MARGIN + PAD
    y = MARGIN + BAR_H + PAD
    for i, line in enumerate(lines):
        no = str(first_no + i).rjust(GUTTER_COLS)
        d.text((x0, y), no, font=font, fill="#5c6370")
        x = x0 + (GUTTER_COLS + 2) * CHAR_W
        for s, col in line:
            d.text((x, y), s, font=font, fill=col)
            x += font.getlength(s)
        y += LINE_H
    dpi = canvas_width(FULL_COLS) / (PAGE_CM / 2.54)
    img.save(path, dpi=(dpi, dpi))
    print(f"wrote {os.path.relpath(path, ROOT)} {w}x{h}")


def main():
    os.makedirs(OUT, exist_ok=True)
    for src, title, name, lexer in SNAPS:
        with open(os.path.join(ROOT, src), encoding="utf-8") as f:
            text = f.read()
        lines = colored_lines(text, lexer)
        longest = max(sum(len(s) for s, _ in ln) for ln in lines)
        # mã nguồn dùng đủ bề rộng; đoạn lệnh ngắn chỉ rộng vừa nội dung
        cols = FULL_COLS if lexer is PythonLexer else max(longest + 2, 60)
        parts = math.ceil(len(lines) / MAX_LINES)
        size = math.ceil(len(lines) / parts)
        for p in range(parts):
            chunk = lines[p * size:(p + 1) * size]
            t = title if parts == 1 else f"{title}  ({p + 1}/{parts})"
            suffix = "" if parts == 1 else f"_{p + 1}"
            render(chunk, p * size + 1, t, cols, os.path.join(OUT, f"{name}{suffix}.png"))


if __name__ == "__main__":
    main()
