#!/usr/bin/env python3
"""Render the MESA README workflow scene as a static SVG/PNG and an optional GIF.

Story: the MESA robot hops across six stages. Strategy #1 is calculated and
analysed, the experimental observation comes back unsupported, a "next
strategy" arrow returns to the strategy stage, Strategy #2 builds a different
(doped) slab, the observation is supported, and only then is the manuscript
written. Each stage hands its output to the next one.

Usage (from the repository root):

    python3 assets/readme/source/workflow_motion.py            # static only
    python3 assets/readme/source/workflow_motion.py --gif      # static + GIF

Requires rsvg-convert; --gif also requires ffmpeg.
"""
from __future__ import annotations

import argparse
import base64
import math
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
CHARACTER = HERE / "character.png"

W, H = 1200, 530
FPS = 30
KEY = (255, 0, 255)  # GIF transparent corners

# Palette sampled from the MESA logo, plus verdict colours.
BG, INK, NAVY, ATOM, BLUE = "#F7F8FC", "#0B1020", "#203865", "#8EA9DB", "#0432FE"
MUTED, RULE, PAPER, GREY, SOFT, TEXT = "#5B6478", "#C3D0EA", "#FFFFFF", "#C9D1E0", "#EEF2FA", "#AEB8CC"
DOPANT = "#2F4E8C"
RED, RED_BG = "#D93036", "#FDECEC"
GREEN, GREEN_BG = "#1F9D55", "#E7F6EE"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

XS = [130 + 188 * i for i in range(6)]
ROW_Y, ATOM_R, PANEL_Y = 160, 24, 242
NAMES = ["Paper", "Literature", "Strategy", "Calculation", "Analysis", "Manuscript"]

# Timeline (seconds). "j_*" windows are robot hops; the rest are stage acts.
T = {
    "paper": (0.3, 1.6), "j_lit": (1.6, 2.2), "lit": (2.2, 3.4),
    "j_s1": (3.4, 4.0), "s1": (4.0, 5.4), "j_c1": (5.4, 6.0), "c1": (6.0, 7.4),
    "j_a1": (7.4, 8.0), "a1": (8.0, 9.4), "revise": (9.4, 10.0), "j_back": (10.0, 10.8),
    "s2": (10.8, 12.0), "j_c2": (12.0, 12.6), "c2": (12.6, 13.8),
    "j_a2": (13.8, 14.4), "a2": (14.4, 15.6), "j_ms": (15.6, 16.2), "ms": (16.2, 17.6),
    "exit": (19.6, 20.3),
}
MOVES = [("j_lit", 0, 1), ("j_s1", 1, 2), ("j_c1", 2, 3), ("j_a1", 3, 4), ("j_back", 4, 2),
         ("j_c2", 2, 3), ("j_a2", 3, 4), ("j_ms", 4, 5), ("exit", 5, 0)]
FADE_END, DURATION, STATIC_T, GIF_START = 19.95, 20.6, 18.6, 0.0

ROBOT_H = 92
ROBOT_W = ROBOT_H * 206 / 238
FEET = 0.86  # feet height as a fraction of the sprite height


# ---------------------------------------------------------------- helpers
def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def prog(t: float, a: float, b: float) -> float:
    return clamp((t - a) / (b - a))


def ease_out(p: float) -> float:
    return 1 - (1 - p) ** 3


def ease_in(p: float) -> float:
    return p * p


def ease_io(p: float) -> float:
    return p * p * (3 - 2 * p)


def lerp(a: float, b: float, p: float) -> float:
    return a + (b - a) * p


def frac(t: float, key: str) -> float:
    s, e = T[key]
    return (t - s) / (e - s)


def started(t: float, key: str) -> bool:
    return t >= T[key][0]


def done(t: float, key: str) -> bool:
    return t >= T[key][1]


def win(f: float, a: float, length: float) -> float:
    return clamp((f - a) / length)


def fade(t: float) -> float:
    return 1 - ease_io(prog(t, T["exit"][0], FADE_END))


def group(x: float, y: float, body: str, opacity: float = 1.0, extra: str = "") -> str:
    if opacity <= 0.003 or not body:
        return ""
    op = f' opacity="{opacity:.3f}"' if opacity < 0.997 else ""
    return f'<g transform="translate({x:.2f} {y:.2f}){extra}"{op}>{body}</g>'


def fly(start, end, p, lift=56):
    ctrl = ((start[0] + end[0]) / 2, min(start[1], end[1]) - lift)
    x = (1 - p) ** 2 * start[0] + 2 * (1 - p) * p * ctrl[0] + p * p * end[0]
    y = (1 - p) ** 2 * start[1] + 2 * (1 - p) * p * ctrl[1] + p * p * end[1]
    return x, y


def text(x, y, s, size, color=INK, weight=400, anchor="start") -> str:
    return (f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" font-family="{SANS}" '
            f'font-size="{size}" font-weight="{weight}" fill="{color}">{s}</text>')


def badge(cx: float, cy: float, n: int, r: float = 11) -> str:
    return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{BLUE}"/>' + text(cx, cy + 4.5, n, 13, "#FFFFFF", 700, "middle")


def tick(x: float, y: float, p: float, color: str = BLUE, width: float = 2.6) -> str:
    if p <= 0:
        return ""
    return (f'<path d="M{x - 5:.2f} {y:.2f} l4 4.5 l8 -9.5" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" '
            f'stroke-dasharray="20" stroke-dashoffset="{20 * (1 - p):.2f}"/>')


def cross(x: float, y: float, color: str = "#FFFFFF", width: float = 2.4) -> str:
    return (f'<path d="M{x - 4:.2f} {y - 4:.2f} L{x + 4:.2f} {y + 4:.2f} M{x + 4:.2f} {y - 4:.2f} L{x - 4:.2f} {y + 4:.2f}" '
            f'stroke="{color}" stroke-width="{width}" stroke-linecap="round"/>')


# ---------------------------------------------------------------- stage 1: paper
HL = [1, 3, 5]
LINE_W = [62, 56, 66, 50, 62, 58, 38]


def paper_line_y(k: int) -> float:
    return 40 + 12 * k


def paper_bar_rest(j: int):
    return 44, 48 + 18 * j


def paper(t: float) -> str:
    f = frac(t, "paper")
    if f < 0:
        return ""
    q = win(f, 0.15, 0.7)
    mag_y = lerp(34, 118, q)
    mag_x = -6 + 10 * math.sin(2 * math.pi * 1.5 * q)
    out = [f'<rect x="-50" y="12" width="86" height="124" rx="6" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>',
           f'<rect x="-40" y="22" width="46" height="8" rx="3" fill="{INK}"/>']
    for k, w in enumerate(LINE_W):
        y = paper_line_y(k)
        lit = k in HL and mag_y >= y
        out.append(f'<rect x="-40" y="{y - 2.5}" width="{w}" height="5" rx="2.5" fill="{BLUE if lit else GREY}"/>')
    if t < T["j_lit"][0]:
        for j, k in enumerate(HL):
            fk = 0.15 + 0.7 * (paper_line_y(k) - 34) / 84
            if f < fk:
                continue
            p = ease_out(win(f, fk, 0.15))
            x1, y1 = paper_bar_rest(j)
            out.append(f'<rect x="{lerp(-40, x1, p):.2f}" y="{lerp(paper_line_y(k) - 3, y1 - 3, p):.2f}" '
                       f'width="28" height="6" rx="3" fill="{BLUE}"/>')
    out.append(f'<g transform="translate({mag_x:.2f} {mag_y:.2f})">'
               f'<line x1="12" y1="12" x2="26" y2="26" stroke="{NAVY}" stroke-width="7" stroke-linecap="round"/>'
               f'<circle r="17" fill="#FFFFFF" fill-opacity="0.35" stroke="{NAVY}" stroke-width="4"/></g>')
    return group(XS[0], PANEL_Y, "".join(out), ease_out(win(f, 0, 0.15)) * fade(t))


# ---------------------------------------------------------------- stage 2: literature
def query_bar(j: int):
    return -38 + 34 * j, 19


def lit_badge(k: int):
    return 52, 50 + 46 * k + 20


def literature(t: float) -> str:
    js, je = T["j_lit"]
    if t < js:
        return ""
    f = frac(t, "lit")
    out = [f'<rect x="-70" y="6" width="140" height="32" rx="16" fill="{PAPER}" stroke="{NAVY}" stroke-width="2"/>',
           f'<circle cx="-54" cy="20" r="6" fill="none" stroke="{NAVY}" stroke-width="2.5"/>'
           f'<line x1="-49.5" y1="24.5" x2="-45" y2="29" stroke="{NAVY}" stroke-width="2.5" stroke-linecap="round"/>']
    if t >= je:
        for j in range(3):
            x, y = query_bar(j)
            out.append(f'<rect x="{x}" y="{y}" width="28" height="6" rx="3" fill="{BLUE}"/>')
    for k in range(3):
        p = ease_out(win(f, 0.08 + 0.26 * k, 0.3))
        if p <= 0:
            continue
        y = 50 + 46 * k + 14 * (1 - p)
        card = (f'<rect x="-70" y="{y:.2f}" width="140" height="40" rx="8" fill="{PAPER}" stroke="{INK}" stroke-width="1.5"/>'
                f'<rect x="-62" y="{y + 7:.2f}" width="22" height="26" rx="3" fill="{ATOM}"/>'
                f'<rect x="-32" y="{y + 11:.2f}" width="58" height="5" rx="2.5" fill="{GREY}"/>'
                f'<rect x="-32" y="{y + 23:.2f}" width="40" height="5" rx="2.5" fill="{GREY}"/>'
                + badge(52, y + 20, k + 1))
        out.append(group(0, 0, card, p))
    return group(XS[1], PANEL_Y, "".join(out), ease_out(prog(t, js, js + 0.25)) * fade(t))


# ---------------------------------------------------------------- stage 3: strategy
CHECKS = {1: ["build slab", "add adsorbate", "compute ΔG"], 2: ["doped slab", "add adsorbate", "compute ΔG"]}
CITES = {1: (1, 2), 2: (2, 3)}
EVIDENCE = [(22, 73), (48, 73)]


def check_row_y(k: int) -> float:
    return 114 + 26 * k


def strategy_card(n: int, u: float, f: float, badges_on: bool) -> str:
    out = [f'<rect x="-74" y="2" width="148" height="186" rx="10" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>']
    p = ease_out(win(u, 0.15, 0.35))
    out.append(group(-8 * (1 - p), 0, text(-62, 30, f"Strategy #{n}", 18, INK, 700), p))
    p = ease_out(win(u, 0.35, 0.35))
    out.append(group(-8 * (1 - p), 0, text(-62, 56, "Goal", 15, BLUE, 700)
                     + f'<rect x="-18" y="48" width="80" height="6" rx="3" fill="{GREY}"/>', p))
    p = ease_out(win(u, 0.55, 0.35))
    out.append(group(-8 * (1 - p), 0, text(-62, 78, "Evidence", 15, BLUE, 700), p))
    if badges_on:
        out.append("".join(badge(x, y, c, 10) for (x, y), c in zip(EVIDENCE, CITES[n])))
    if f >= 0:
        out.append(group(0, 0, f'<line x1="-62" y1="92" x2="62" y2="92" stroke="{RULE}" stroke-width="1.5"/>',
                         ease_out(win(f, 0, 0.1))))
        for k, label in enumerate(CHECKS[n]):
            s = 0.1 + 0.28 * k
            p = ease_out(win(f, s, 0.18))
            y = check_row_y(k)
            row = (f'<rect x="-62" y="{y - 8}" width="16" height="16" rx="3" fill="{PAPER}" stroke="{NAVY}" stroke-width="2"/>'
                   + text(-38, y + 5, label, 15) + tick(-54, y, win(f, s + 0.12, 0.12)))
            out.append(group(-10 * (1 - p), 0, row, p))
    return "".join(out)


def strategy(t: float) -> str:
    js, je = T["j_s1"]
    if t < js:
        return ""
    card1 = strategy_card(1, frac(t, "j_s1"), frac(t, "s1"), done(t, "j_s1"))
    if started(t, "j_back"):
        u = frac(t, "j_back")
        p = ease_out(win(u, 0, 0.4))
        body = (group(-6 * p, -6 * p, card1, 1 - 0.35 * p)
                + group(0, -16 * (1 - p), strategy_card(2, u, frac(t, "s2"), done(t, "j_back")), p))
    else:
        body = card1
    return group(XS[2], PANEL_Y, body, ease_out(prog(t, js, js + 0.2)) * fade(t))


# ---------------------------------------------------------------- stage 4: calculation
SLAB_ROWS = [(124, [-48, -16, 16, 48]), (142, [-64, -32, 0, 32, 64]), (160, [-48, -16, 16, 48])]
DOPED = {(124, 16), (142, -32), (160, 48)}
SITE = (16, 100)


def slab(f: float, start: float, step: float, doped: bool) -> str:
    out = []
    for k, (y, xs) in enumerate(SLAB_ROWS):
        p = ease_out(win(f, start + step * k, 0.22))
        row = "".join(f'<circle cx="{x}" cy="{y}" r="16" fill="{DOPANT if doped and (y, x) in DOPED else ATOM}" '
                      f'stroke="{INK}" stroke-width="1.5"/>' for x in xs)
        out.append(group(0, -18 * (1 - p), row, p))
    return "".join(out)


def oh(x: float, y: float) -> str:
    return (f'<circle cx="{x + 11:.2f}" cy="{y - 9:.2f}" r="7" fill="#FFFFFF" stroke="{INK}" stroke-width="1.5"/>'
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="11" fill="{BLUE}" stroke="{INK}" stroke-width="1.5"/>')


def adsorbate_round1(f: float):
    """Land, lift off, and land again."""
    if f < 0.45:
        return None
    if f < 0.62:
        return lerp(36, SITE[1], ease_in(win(f, 0.45, 0.17)))
    if f < 0.70:
        return SITE[1]
    if f < 0.82:
        return lerp(SITE[1], 60, ease_out(win(f, 0.70, 0.12)))
    if f < 0.95:
        return lerp(60, SITE[1], ease_in(win(f, 0.82, 0.13)))
    return SITE[1]


def adsorbate_round2(f: float):
    if f < 0.5:
        return None
    return lerp(36, SITE[1], ease_in(win(f, 0.5, 0.18)))


def cleared(t: float) -> float:
    """Round-1 calculation and analysis clear while the robot hops back."""
    s = T["j_back"][0]
    return ease_io(prog(t, s, s + 0.4))


def calculation(t: float) -> str:
    if t < T["c1"][0]:
        return ""
    f1 = frac(t, "c1")
    first = slab(f1, 0, 0.12, False)
    y1 = adsorbate_round1(f1)
    if y1 is not None:
        first += group(0, 0, oh(SITE[0], y1), ease_out(win(f1, 0.45, 0.06)))
    q = cleared(t)
    body = group(0, 10 * q, first, 1 - q)
    if started(t, "c2"):
        f2 = frac(t, "c2")
        body += slab(f2, 0, 0.12, True)
        y2 = adsorbate_round2(f2)
        if y2 is not None:
            body += group(0, 0, oh(SITE[0], y2), ease_out(win(f2, 0.5, 0.06)))
    return group(XS[3], PANEL_Y, body, fade(t))


# ---------------------------------------------------------------- stage 5: analysis
PROFILES = {
    1: ([(-54, 36), (-27, 74), (0, 52), (27, 92), (54, 114)], RED),    # large uphill step
    2: ([(-54, 36), (-27, 60), (0, 56), (27, 86), (54, 114)], GREEN),  # nearly downhill
}
LEVEL_W = 16
PROFILE_CENTER = (8, 75)


def profile_body(n: int) -> str:
    levels, color = PROFILES[n]
    out = []
    for k in range(len(levels) - 1):
        (x0, y0), (x1, y1) = levels[k], levels[k + 1]
        if k == 1:
            out.append(f'<line x1="{x0 + LEVEL_W}" y1="{y0}" x2="{x1}" y2="{y1}" stroke="{color}" stroke-width="3" stroke-linecap="round"/>')
        else:
            out.append(f'<line x1="{x0 + LEVEL_W}" y1="{y0}" x2="{x1}" y2="{y1}" stroke="{NAVY}" stroke-width="2" stroke-dasharray="4 4"/>')
    for x, y in levels:
        out.append(f'<line x1="{x}" y1="{y}" x2="{x + LEVEL_W}" y2="{y}" stroke="{INK}" stroke-width="4.5" stroke-linecap="round"/>')
    return "".join(out)


def reveal(n: int, width: float) -> str:
    if width <= 0.5:
        return ""
    return (f'<clipPath id="reveal{n}"><rect x="-62" y="20" width="{width:.2f}" height="104"/></clipPath>'
            f'<g clip-path="url(#reveal{n})">{profile_body(n)}</g>')


def verdict(n: int, p: float) -> str:
    ok = n == 2
    color, bg = (GREEN, GREEN_BG) if ok else (RED, RED_BG)
    label = "Supported" if ok else "Unsupported"
    label_w = 86 if ok else 104
    left = -(17 + 6 + label_w) / 2
    icon = (f'<circle cx="{left + 8.5:.2f}" cy="173" r="8.5" fill="{color}"/>'
            + (tick(left + 8.5 - 1, 173, 1, "#FFFFFF", 2.4) if ok else cross(left + 8.5, 173)))
    body = (f'<rect x="-86" y="136" width="172" height="50" rx="10" fill="{bg}" stroke="{color}" stroke-width="1.5"/>'
            + text(0, 156, "Experimental observation", 13.5, MUTED, 600, "middle")
            + icon + text(left + 23, 179, label, 17, color, 700))
    s = lerp(1.12, 1.0, p)
    return f'<g transform="translate(0 161) scale({s:.4f}) translate(0 -161)" opacity="{p:.3f}">{body}</g>'


AXES = (f'<line x1="-64" y1="6" x2="-64" y2="124" stroke="{INK}" stroke-width="2"/>'
        f'<line x1="-64" y1="124" x2="74" y2="124" stroke="{INK}" stroke-width="2"/>'
        f'<path d="M-69 12 L-64 2 L-59 12 Z" fill="{INK}"/>'
        f'<path d="M68 119 L78 124 L68 129 Z" fill="{INK}"/>'
        + text(-54, 16, "ΔG", 15, INK, 700))


def analysis_round(t: float, n: int, hop_key: str, act_key: str) -> str:
    js = T[hop_key][0]
    if t < js:
        return ""
    f = frac(t, act_key)
    body = AXES
    if f >= 0:
        body += reveal(n, 140 * ease_io(win(f, 0.05, 0.55)))
        pv = ease_out(win(f, 0.65, 0.2))
        if pv > 0:
            body += verdict(n, pv)
    return group(0, 0, body, ease_out(prog(t, js, js + 0.25)))


def analysis(t: float) -> str:
    body = (group(0, 0, analysis_round(t, 1, "j_a1", "a1"), 1 - cleared(t))
            + analysis_round(t, 2, "j_a2", "a2"))
    return group(XS[4], PANEL_Y, body, fade(t))


def revise_arrow(t: float) -> str:
    s, e = T["revise"]
    if t < s:
        return ""
    p = ease_io(prog(t, s, e))
    a, b = XS[4], XS[2]
    y0, yc, y1 = PANEL_Y + 194, PANEL_Y + 262, PANEL_Y + 204
    left = lerp(a + 10, b - 12, p)
    body = (f'<clipPath id="revise"><rect x="{left:.2f}" y="{y0 - 6}" width="{a + 10 - left:.2f}" height="{yc - y0 + 12}"/></clipPath>'
            f'<path d="M{a} {y0} C{a} {yc} {b} {yc} {b} {y1}" fill="none" stroke="{NAVY}" stroke-width="2.5" '
            f'stroke-dasharray="7 6" clip-path="url(#revise)"/>')
    if p > 0.9:
        body += f'<path d="M{b - 8} {y1 + 2} L{b} {y1 - 12} L{b + 8} {y1 + 2} Z" fill="{NAVY}"/>'
    pl = ease_out(win(p, 0.4, 0.4))
    mid = (a + b) / 2
    body += group(0, 0, f'<rect x="{mid - 70}" y="474" width="140" height="28" rx="6" fill="{BG}"/>'
                  + text(mid, 494, "next strategy", 18, BLUE, 700, "middle"), pl)
    landed = T["j_back"][1]  # erase once the robot is back on the strategy stage
    return group(0, 0, body, 1 - ease_io(prog(t, landed - 0.15, landed + 0.3)))


# ---------------------------------------------------------------- stage 6: manuscript
MS_W = [88, 80, 90, 70, 86, 52]
FIG_CENTER, FIG_SCALE = (0, 62), 0.55


def ms_line_y(k: int) -> float:
    return 106 + 13 * k


def pen(x: float, y: float) -> str:
    return (f'<g transform="translate({x:.2f} {y - 1:.2f}) rotate(32)">'
            f'<rect x="-3.5" y="-34" width="7" height="26" rx="1.5" fill="{NAVY}"/>'
            f'<path d="M-3.5 -8 L3.5 -8 L0 0 Z" fill="{BLUE}"/></g>')


def mini_profile(cx: float, cy: float, s: float, n: int = 2) -> str:
    return (f'<g transform="translate({cx:.2f} {cy:.2f}) scale({s:.4f}) '
            f'translate({-PROFILE_CENTER[0]} {-PROFILE_CENTER[1]})">{profile_body(n)}</g>')


def manuscript(t: float) -> str:
    js, je = T["j_ms"]
    if t < js:
        return ""
    f = frac(t, "ms")
    out = [f'<rect x="-58" y="2" width="116" height="186" rx="6" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>',
           f'<rect x="-46" y="14" width="70" height="9" rx="3" fill="{INK}"/>',
           f'<rect x="-46" y="32" width="92" height="60" rx="4" fill="{SOFT}" stroke="{RULE}" stroke-width="1.5"/>']
    if t >= je:
        out.append(mini_profile(*FIG_CENTER, FIG_SCALE))
    if f >= 0:
        q = win(f, 0.05, 0.85) * len(MS_W)
        tip = None
        for k, w in enumerate(MS_W):
            part = clamp(q - k)
            if part <= 0:
                break
            y = ms_line_y(k)
            out.append(f'<rect x="-46" y="{y - 2.5}" width="{w * part:.2f}" height="5" rx="2.5" fill="{TEXT}"/>')
            tip = (-46 + w * part, y)
        if tip:
            out.append(pen(*tip))
    return group(XS[5], PANEL_Y, "".join(out), ease_out(prog(t, js, js + 0.25)) * fade(t))


# ---------------------------------------------------------------- hand-offs between stages
def carriers(t: float) -> str:
    def hop(key):
        s, e = T[key]
        return ease_io(prog(t, s, e)) if s <= t < e else None

    out = []
    if (p := hop("j_lit")) is not None:  # extracted lines become the search query
        for j in range(3):
            bx, by = paper_bar_rest(j)
            qx, qy = query_bar(j)
            x, y = fly((XS[0] + bx, PANEL_Y + by - 3), (XS[1] + qx, PANEL_Y + qy), p, 50 + 8 * j)
            out.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="28" height="6" rx="3" fill="{BLUE}"/>')
    for key, n in (("j_s1", 1), ("j_back", 2)):  # citations become strategy evidence
        if (p := hop(key)) is not None:
            for (ex, ey), c in zip(EVIDENCE, CITES[n]):
                bx, by = lit_badge(c - 1)
                x, y = fly((XS[1] + bx, PANEL_Y + by), (XS[2] + ex, PANEL_Y + ey), p, 60)
                out.append(badge(x, y, c, lerp(11, 10, p)))
    for key in ("j_c1", "j_c2"):  # the checklist drives the calculation
        if (p := hop(key)) is not None:
            x, y = fly((XS[2] + 64, PANEL_Y + check_row_y(0)), (XS[3], PANEL_Y + 110), p, 36)
            chip = f'<rect x="-11" y="-11" width="22" height="22" rx="5" fill="{BLUE}"/>' + tick(0, 0, 1, "#FFFFFF", 2.6)
            out.append(group(x, y, chip, 1 - ease_in(win(p, 0.75, 0.25)), f" scale({lerp(1, 0.7, p):.3f})"))
    for key, n in (("j_a1", 1), ("j_a2", 2)):  # computed energy becomes the first profile point
        if (p := hop(key)) is not None:
            lx, ly = PROFILES[n][0][0]
            x, y = fly((XS[3] + SITE[0], PANEL_Y + SITE[1]), (XS[4] + lx + 8, PANEL_Y + ly), p, 60)
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6" fill="{BLUE}" stroke="{INK}" stroke-width="1.5"/>')
    if (p := hop("j_ms")) is not None:  # the supported profile becomes the manuscript figure
        x, y = fly((XS[4] + PROFILE_CENTER[0], PANEL_Y + PROFILE_CENTER[1]),
                   (XS[5] + FIG_CENTER[0], PANEL_Y + FIG_CENTER[1]), p, 40)
        out.append(mini_profile(x, y, lerp(1, FIG_SCALE, p)))
    return "".join(out)


# ---------------------------------------------------------------- robot and stage row
def robot_state(t: float):
    base = ROW_Y - ATOM_R + 2
    pos = 0
    for key, a, b in MOVES:
        s, e = T[key]
        if s <= t < e:
            p = ease_io(prog(t, s, e))
            peak = 50 if abs(b - a) == 1 else 54
            return lerp(XS[a], XS[b], p), base - peak * 4 * p * (1 - p), None
        if t >= e:
            pos = b
    return XS[pos], base, pos


def stage_row(active) -> str:
    out = [f'<line x1="{XS[0]}" y1="{ROW_Y}" x2="{XS[-1]}" y2="{ROW_Y}" stroke="{RULE}" stroke-width="3"/>']
    for i, (x, name) in enumerate(zip(XS, NAMES)):
        on = i == active
        out.append(f'<circle cx="{x}" cy="{ROW_Y}" r="{ATOM_R}" fill="{BLUE if on else ATOM}" stroke="{INK}" stroke-width="2.5"/>'
                   + text(x, ROW_Y + 6.5, i + 1, 18, "#FFFFFF" if on else INK, 700, "middle")
                   + text(x, ROW_Y + 52, name, 22, BLUE if on else INK, 700, "middle"))
    return "".join(out)


def scene(t: float, href: str, key_background: bool) -> str:
    rx, ry, active = robot_state(t)
    robot = (f'<image href="{href}" x="{rx - ROBOT_W / 2:.2f}" y="{ry - FEET * ROBOT_H:.2f}" '
             f'width="{ROBOT_W:.2f}" height="{ROBOT_H}"/>')
    background = (f'<rect width="{W}" height="{H}" fill="#{KEY[0]:02X}{KEY[1]:02X}{KEY[2]:02X}"/>'
                  f'<rect width="{W}" height="{H}" rx="22" fill="{BG}" shape-rendering="crispEdges"/>'
                  if key_background else f'<rect width="{W}" height="{H}" rx="22" fill="{BG}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
            f'aria-labelledby="title desc">'
            f'<title id="title">The MESA research loop</title>'
            f'<desc id="desc">The MESA robot hops from paper to literature, strategy, calculation, and analysis. '
            f'Strategy #1 leaves the experimental observation unsupported, so the robot returns for the next '
            f'strategy, builds a doped slab, finds the observation supported, and writes the manuscript.</desc>'
            f'{background}{stage_row(active)}'
            f'{paper(t)}{literature(t)}{strategy(t)}{calculation(t)}{analysis(t)}{manuscript(t)}'
            f'{revise_arrow(t)}{carriers(t)}{robot}</svg>')


# ---------------------------------------------------------------- output
def render(svg_path: Path, png_path: Path, width: int) -> None:
    subprocess.run(["rsvg-convert", "-w", str(width), str(svg_path), "-o", str(png_path)], check=True)


def gif_mark_transparent(path: Path, key) -> None:
    """Mark the reserved key palette entry transparent in every frame's control block."""
    data = bytearray(path.read_bytes())
    packed = data[10]
    if not packed & 0x80:
        sys.exit("GIF has no global palette")
    gct_len = 3 * 2 ** ((packed & 7) + 1)
    gct = data[13:13 + gct_len]
    idx = next((i for i in range(gct_len // 3) if tuple(gct[3 * i:3 * i + 3]) == key), None)
    if idx is None:
        sys.exit("transparent key colour missing from GIF palette")
    pos, gces, images = 13 + gct_len, [], 0
    while pos < len(data):
        b = data[pos]
        if b == 0x21:
            if data[pos + 1] == 0xF9:
                gces.append(pos)
            pos += 2
            while data[pos]:
                pos += data[pos] + 1
            pos += 1
        elif b == 0x2C:
            images += 1
            lp = data[pos + 9]
            pos += 10 + (3 * 2 ** ((lp & 7) + 1) if lp & 0x80 else 0) + 1
            while data[pos]:
                pos += data[pos] + 1
            pos += 1
        elif b == 0x3B:
            break
        else:
            sys.exit(f"unexpected GIF block 0x{b:02X} at {pos}")
    if len(gces) != images:
        sys.exit(f"expected one control block per frame, found {len(gces)} for {images}")
    for g in gces:
        data[g + 3] |= 0x01
        data[g + 6] = idx
    path.write_bytes(data)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gif", action="store_true", help="also render the animated GIF")
    ap.add_argument("--static-time", type=float, default=STATIC_T)
    args = ap.parse_args()
    if not shutil.which("rsvg-convert"):
        sys.exit("rsvg-convert is required")

    root = OUT.parent.parent
    static_svg = HERE / "workflow.svg"
    static_svg.write_text(scene(args.static_time, CHARACTER.name, False), encoding="utf-8")
    render(static_svg, OUT / "workflow.png", 2 * W)
    print(f"wrote {static_svg.relative_to(root)} and {(OUT / 'workflow.png').relative_to(root)}")
    if not args.gif:
        return
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required for --gif")

    data_uri = "data:image/png;base64," + base64.b64encode(CHARACTER.read_bytes()).decode()
    n = round(DURATION * FPS)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def job(i: int) -> None:
            svg = tmp / f"frame-{i:04d}.svg"
            svg.write_text(scene((GIF_START + i / FPS) % DURATION, data_uri, True), encoding="utf-8")
            render(svg, tmp / f"frame-{i:04d}.png", W)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(job, range(n)))
        gif = OUT / "workflow.gif"
        pattern = str(tmp / "frame-%04d.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", pattern,
                        "-vf", "palettegen=stats_mode=full:max_colors=256:reserve_transparent=0",
                        str(tmp / "palette.png")], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", pattern, "-i", str(tmp / "palette.png"),
                        "-lavfi", "paletteuse=dither=none:diff_mode=rectangle", "-gifflags", "+offsetting-transdiff",
                        "-loop", "0", str(gif)], check=True)
        gif_mark_transparent(gif, KEY)
    print(f"wrote {gif.relative_to(root)} ({gif.stat().st_size / 1e6:.2f} MB, {n} frames)")


if __name__ == "__main__":
    main()
