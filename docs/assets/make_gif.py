#!/usr/bin/env python3
"""Render docs/assets/token-savings.gif — a terminal-style loop showing token savings.

Numbers come from the README's documented example report
(50,000 total -> 3,500 sent -> 46,500 saved, 93.0%).
"""
from __future__ import annotations

import math
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H = 960, 600
BG = (13, 17, 23)
FG = (201, 209, 217)
DIM = (125, 133, 144)
GREEN = (63, 185, 80)
BLUE = (88, 166, 255)
PURPLE = (188, 140, 255)
YELLOW = (210, 153, 34)
BORDER = (48, 54, 61)
HEADER = (22, 27, 34)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def find_font() -> str:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    out = subprocess.run(
        ["fc-match", "-f", "%{file}", "monospace"], capture_output=True, text=True
    ).stdout.strip()
    if out and os.path.exists(out):
        return out
    raise SystemExit("no monospace font found")


FONT_PATH = find_font()
F = ImageFont.truetype(FONT_PATH, 22)
FB = ImageFont.truetype(FONT_PATH, 24)
FS = ImageFont.truetype(FONT_PATH, 15)
FBIG = ImageFont.truetype(FONT_PATH, 34)

LINE_H = 34
PAD = 26

TOTAL_TOKENS = 50_000
SENT_TOKENS = 3_500
SAVED_TOKENS = TOTAL_TOKENS - SENT_TOKENS
PCT = 93.0

USER_LINE = "You > how does authentication work in this project?"
CALL_LINE = 'context-broker > search_codebase("authentication middleware")'
SCAN_LINE = "indexed 312 files in 1.8s - query cache ready"
RESULTS = [
    ("src/auth/middleware.py", 0.94),
    ("src/auth/tokens.py", 0.89),
    ("src/api/login.py", 0.83),
]

# timeline (seconds)
T_TYPE_END = 1.6
T_CALL_END = 2.4
T_SCAN_END = 3.2
T_RESULTS_END = 4.2
T_COUNT_END = 5.6
T_HOLD_END = 7.4
FPS = 12
FRAMES = int(T_HOLD_END * FPS)


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def typed(text: str, start: float, end: float, t: float) -> str:
    if t <= start:
        return ""
    n = int(len(text) * ease((t - start) / (end - start)))
    return text[:n]


def count_up(target: int, start: float, end: float, t: float) -> int:
    if t <= start:
        return 0
    return int(target * ease((t - start) / (end - start)))


def draw_frame(t: float) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # window chrome
    d.rounded_rectangle([8, 8, W - 8, H - 8], radius=14, outline=BORDER, width=2, fill=BG)
    d.rectangle([9, 9, W - 9, 52], fill=HEADER)
    d.rounded_rectangle([8, 8, W - 8, H - 8], radius=14, outline=BORDER, width=2)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([28 + i * 30, 24, 44 + i * 30, 40], fill=c)
    d.text((W // 2 - 110, 20), "context-broker - mcp", font=FS, fill=DIM)

    y = 52 + PAD

    # user prompt (typed)
    line = typed(USER_LINE, 0.2, T_TYPE_END, t)
    d.text((PAD, y), line, font=F, fill=FG)
    if t < T_TYPE_END:
        x = PAD + d.textlength(line, font=F)
        if int(t * 3) % 2 == 0:
            d.rectangle([x + 2, y, x + 14, y + 24], fill=FG)
        return img
    y += LINE_H + 6

    # tool call
    if t >= T_TYPE_END + 0.15:
        d.text((PAD, y), typed(CALL_LINE, T_TYPE_END + 0.15, T_CALL_END, t), font=F, fill=BLUE)
        y += LINE_H
    if t < T_CALL_END:
        return img

    # scan line
    spin = "|/-\\"[int(t * 8) % 4]
    if t < T_SCAN_END:
        d.text((PAD, y), f"{spin} scanning project...", font=F, fill=DIM)
        return img
    d.text((PAD, y), f"done {SCAN_LINE}", font=F, fill=DIM)
    y += LINE_H + 8

    # results
    nres = min(len(RESULTS), max(0, int((t - T_SCAN_END) / 0.3) + 1))
    for path, score in RESULTS[:nres]:
        d.text((PAD, y), f"  {path}", font=F, fill=FG)
        d.text((W - PAD - 150, y), f"{score:.2f}", font=F, fill=PURPLE)
        y += LINE_H
    if t < T_RESULTS_END:
        return img
    y += 12

    # token report box
    box_top = y
    box_h = 3 * LINE_H + 46
    d.rounded_rectangle([PAD, box_top, W - PAD, box_top + box_h], radius=10, outline=GREEN, width=2)
    d.text((PAD + 18, box_top + 12), "TOKEN EFFICIENCY REPORT", font=FS, fill=GREEN)

    cs, ce = T_RESULTS_END + 0.1, T_COUNT_END
    ry = box_top + 12 + 26
    total = count_up(TOTAL_TOKENS, cs, ce - 0.9, t)
    sent = count_up(SENT_TOKENS, cs + 0.3, ce - 0.5, t)
    saved = count_up(SAVED_TOKENS, cs + 0.6, ce, t)
    d.text((PAD + 18, ry), f"Total project tokens   {total:>7,}", font=F, fill=FG)
    d.text((PAD + 18, ry + LINE_H), f"Context sent           {sent:>7,}", font=F, fill=BLUE)
    d.text((PAD + 18, ry + 2 * LINE_H), f"Tokens saved           {saved:>7,}", font=F, fill=GREEN)

    # savings bar + big percent after count-up
    if t >= ce:
        p = ease((t - ce) / 0.7)
        bar_y = box_top + box_h + 26
        bar_w = W - 2 * PAD - 220
        d.rounded_rectangle([PAD, bar_y, PAD + bar_w, bar_y + 26], radius=13, outline=BORDER, width=2)
        fill_w = int(bar_w * (PCT / 100) * p)
        if fill_w > 8:
            d.rounded_rectangle([PAD, bar_y, PAD + fill_w, bar_y + 26], radius=13, fill=GREEN)
        pulse = 1 + 0.03 * math.sin(t * 4)
        big = ImageFont.truetype(FONT_PATH, int(34 * pulse))
        d.text((PAD + bar_w + 30, bar_y - 8), f"{PCT:.0f}%", font=big, fill=YELLOW)
        d.text((PAD, bar_y + 42), "fewer tokens sent to the model - same answers", font=F, fill=DIM)

    return img


def main() -> None:
    out_dir = os.path.join("docs", "assets")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "token-savings.gif")
    frames = [draw_frame(i / FPS) for i in range(FRAMES)]
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / FPS),
        loop=0,
        optimize=True,
    )
    size = os.path.getsize(out)
    print(f"wrote {out} ({size/1024:.0f} KiB, {FRAMES} frames)")


if __name__ == "__main__":
    main()
