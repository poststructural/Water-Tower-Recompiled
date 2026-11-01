"""Draw the launcher's artwork into animaniacs_launcher/assets/ui/.

Everything here is drawn from scratch: an original studio-lot night scene with
our water tower (the launcher icon's), the wordmark in Luckiest Guy (Apache
2.0, assets/fonts), and the buttons and glass panels. Nothing comes from the
game. The PNGs are committed, so only run this to change the art:

    python -m pip install pillow
    python launcher/tools/make_art.py
"""

from __future__ import annotations

import math
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "animaniacs_launcher", "assets")
OUT = os.path.join(ASSETS, "ui")
FONT = os.path.join(ASSETS, "fonts", "LuckiestGuy-Regular.ttf")

GOLD = (245, 184, 46)
GOLD_HI = (255, 214, 102)
GOLD_LO = (196, 120, 18)
INK = (20, 12, 34)
SS = 2  # supersampling for the vector parts


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def gradient(size, stops, horizontal=False):
    """A gradient image through (position, colour) stops."""
    w, h = size
    n = w if horizontal else h
    line = Image.new("RGBA", (n, 1))
    px = line.load()
    for i in range(n):
        t = i / max(1, n - 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                px[i, 0] = lerp(c0, c1, (t - p0) / max(1e-6, p1 - p0))
                break
    line = line.resize((n, 1))
    return line.resize((w, h)) if horizontal else line.rotate(-90, expand=True).resize((w, h))


def rounded(size, radius, fill, outline=None, width=0):
    w, h = size
    im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), radius * SS, fill=fill,
                        outline=outline, width=width * SS)
    return im.resize((w, h), Image.LANCZOS)


def mask_round(size, radius):
    return rounded(size, radius, (255, 255, 255, 255)).getchannel("A")


def glow(im, radius, colour, strength=1.0):
    a = im.getchannel("A").filter(ImageFilter.GaussianBlur(radius))
    if strength != 1.0:
        a = a.point(lambda v: min(255, int(v * strength)))
    g = Image.new("RGBA", im.size, colour + (0,))
    g.putalpha(a)
    return g


# ── The scene ───────────────────────────────────────────────────────────

def water_tower(h):
    """The icon's water tower, lit warm from the front, on a transparent canvas."""
    w = int(h * 0.62)
    S = SS
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = w * S // 2
    tank_w, tank_h = int(w * 0.80) * S, int(h * 0.36) * S
    tank_top = int(h * 0.20) * S
    left, right = cx - tank_w // 2, cx + tank_w // 2
    # legs and braces
    leg = (150, 92, 20, 255)
    base = h * S - 1
    for x0, x1 in ((left + tank_w * 0.16, left + tank_w * 0.06), (right - tank_w * 0.16, right - tank_w * 0.06)):
        d.polygon([(x0 - 9 * S, tank_top + tank_h), (x0 + 9 * S, tank_top + tank_h),
                   (x1 + 11 * S, base), (x1 - 11 * S, base)], fill=leg)
    for frac in (0.55, 0.78):
        y = tank_top + tank_h + (base - tank_top - tank_h) * frac
        d.rectangle((left + tank_w * 0.10, y - 6 * S, right - tank_w * 0.10, y + 6 * S), fill=leg)
    # tank body with a cylinder shade
    body = gradient((tank_w, tank_h), [(0, GOLD_LO + (255,)), (0.32, GOLD_HI + (255,)),
                                       (0.62, GOLD + (255,)), (1, (150, 86, 14, 255))], horizontal=True)
    m = Image.new("L", (tank_w, tank_h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, tank_w - 1, tank_h - 1), 18 * S, fill=255)
    im.paste(body, (left, tank_top), m)
    # bands
    for frac in (0.12, 0.88):
        y = tank_top + int(tank_h * frac)
        d.rectangle((left, y - 4 * S, right, y + 4 * S), fill=(120, 70, 12, 255))
    # roof cone and knob
    overhang = int(tank_w * 0.07)
    roof_top = int(h * 0.04) * S
    d.polygon([(left - overhang, tank_top + 6 * S), (right + overhang, tank_top + 6 * S), (cx, roof_top)],
              fill=(214, 146, 28, 255))
    d.polygon([(cx, roof_top), (right + overhang, tank_top + 6 * S), (cx + tank_w * 0.10, tank_top + 6 * S)],
              fill=(170, 104, 18, 255))
    r = int(h * 0.028) * S
    d.ellipse((cx - r, roof_top - r * 1.6, cx + r, roof_top + r * 0.4), fill=(214, 146, 28, 255))
    # the letter, as on the icon
    font = ImageFont.truetype(FONT, int(tank_h * 0.62))
    d.text((cx, tank_top + tank_h * 0.56), "A", font=font, anchor="mm", fill=INK + (255,))
    return im.resize((w, h), Image.LANCZOS)


def soundstage(d, x, y, w, h, colour, windows, rnd):
    """A barrel-roofed soundstage with a few lit windows."""
    roof = w * 0.16
    d.rectangle((x, y, x + w, y + h), fill=colour)
    d.chord((x, y - roof, x + w, y + roof), 180, 360, fill=colour)
    if windows:
        for _ in range(rnd.randint(1, 4)):
            wx = x + rnd.randint(8, max(9, int(w) - 24))
            wy = y + rnd.randint(int(h * 0.2), max(int(h * 0.2) + 1, int(h * 0.7)))
            d.rectangle((wx, wy, wx + 10, wy + 14), fill=(255, 206, 120, 255))


def hero(size=(1920, 1080)):
    """The scene. The launcher pins its bottom-right corner, so the tower keeps its
    place at the right whatever the window's size, and the left fades to night."""
    rnd = random.Random(1993)
    w, h = size
    sky = gradient(size, [(0, (10, 6, 28, 255)), (0.38, (40, 16, 66, 255)), (0.62, (122, 38, 80, 255)),
                          (0.74, (232, 104, 58, 255)), (0.80, (250, 170, 90, 255)), (1, (40, 16, 40, 255))])
    im = sky.copy()
    d = ImageDraw.Draw(im)
    for _ in range(260):  # stars
        x, y = rnd.randrange(w), int(rnd.random() ** 1.8 * h * 0.55)
        a = rnd.randint(70, 230)
        r = rnd.choice((1, 1, 1, 2))
        d.ellipse((x, y, x + r, y + r), fill=(255, 245, 220, a))

    # searchlights sweeping up from behind the lot
    beams = Image.new("RGBA", size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(beams)
    for bx, ang, spread in ((w - 900, -62, 5), (w - 620, -105, 6), (w - 60, -118, 5), (w - 380, -80, 4)):
        L = h * 1.3
        a0, a1 = math.radians(ang - spread), math.radians(ang + spread)
        p = [(bx, h * 0.78), (bx + L * math.cos(a0), h * 0.78 + L * math.sin(a0)),
             (bx + L * math.cos(a1), h * 0.78 + L * math.sin(a1))]
        bd.polygon(p, fill=(255, 236, 190, 46))
    im.alpha_composite(beams.filter(ImageFilter.GaussianBlur(14)))

    # glow behind the tower
    tx, ty = w - 250, int(h * 0.52)
    halo = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((tx - 380, ty - 330, tx + 380, ty + 330), fill=(255, 170, 70, 120))
    im.alpha_composite(halo.filter(ImageFilter.GaussianBlur(120)))

    # far skyline, then near soundstages
    far = Image.new("RGBA", size, (0, 0, 0, 0))
    fd = ImageDraw.Draw(far)
    x = -20
    while x < w:
        bw, bh = rnd.randint(60, 150), rnd.randint(40, 120)
        fd.rectangle((x, h * 0.80 - bh, x + bw, h), fill=(70, 26, 70, 255))
        x += bw - 6
    im.alpha_composite(far.filter(ImageFilter.GaussianBlur(2)))

    tower = water_tower(int(h * 0.56))
    tw, th = tower.size
    pos = (tx - tw // 2, int(h * 0.90) - th)
    lit = Image.new("RGBA", size, (0, 0, 0, 0))
    lit.alpha_composite(tower, pos)
    im.alpha_composite(glow(lit, 26, (255, 190, 90), 0.9))
    im.alpha_composite(lit)

    near = Image.new("RGBA", size, (0, 0, 0, 0))
    nd = ImageDraw.Draw(near)
    x = -40
    while x < w:
        bw, bh = rnd.randint(150, 260), rnd.randint(50, 100)
        soundstage(nd, x, h * 0.90 - bh, bw, bh + h * 0.2, (34, 14, 44, 255), True, rnd)
        x += bw + rnd.randint(10, 40)
    im.alpha_composite(near)

    # the street, lamps
    d = ImageDraw.Draw(im)
    d.rectangle((0, int(h * 0.90), w, h), fill=(18, 8, 26, 255))
    lamps = Image.new("RGBA", size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(lamps)
    for lx in range(80, w, 260):
        ld.rectangle((lx - 3, h * 0.80, lx + 3, h * 0.92), fill=(14, 6, 20, 255))
        ld.ellipse((lx - 26, h * 0.80 - 26, lx + 26, h * 0.80 + 26), fill=(255, 210, 130, 70))
        ld.ellipse((lx - 7, h * 0.80 - 7, lx + 7, h * 0.80 + 7), fill=(255, 232, 170, 255))
    im.alpha_composite(lamps.filter(ImageFilter.GaussianBlur(1.5)))

    # shade the left side for the wordmark and buttons, and the bottom for the card
    shade = gradient(size, [(0, (8, 4, 18, 235)), ((w - 1000) / w, (8, 4, 18, 205)),
                            ((w - 520) / w, (8, 4, 18, 0)), (1, (8, 4, 18, 0))], horizontal=True)
    im.alpha_composite(shade)
    im.alpha_composite(gradient(size, [(0, (0, 0, 0, 0)), (0.70, (0, 0, 0, 0)), (1, (6, 3, 12, 200))]))
    return im.convert("RGB")


def page_banner(size=(1600, 96)):
    """A thin strip of the scene for the top of the settings pages."""
    full = hero()
    strip = full.crop((320, 380, 1920, 380 + size[1] * 2)).resize(size, Image.LANCZOS).convert("RGBA")
    strip.alpha_composite(gradient(size, [(0, (14, 10, 24, 120)), (1, (14, 10, 24, 255))]))
    return strip.convert("RGB")


# ── Wordmark ────────────────────────────────────────────────────────────

def wordmark():
    big = ImageFont.truetype(FONT, 132 * SS)
    small = ImageFont.truetype(FONT, 34 * SS)
    tag = ImageFont.truetype(FONT, 22 * SS)
    W, H = 900 * SS, 280 * SS
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    text = "ANIMANIACS"
    x0, y0 = 14 * SS, 14 * SS
    # outline + shadow
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((x0 + 8 * SS, y0 + 10 * SS), text, font=big, fill=(0, 0, 0, 200),
                            stroke_width=10 * SS, stroke_fill=(0, 0, 0, 200))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6 * SS)))
    ImageDraw.Draw(im).text((x0, y0), text, font=big, fill=INK + (255,), stroke_width=10 * SS,
                            stroke_fill=INK + (255,))
    # gradient fill through the letters
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).text((x0, y0), text, font=big, fill=255)
    bbox = m.getbbox()
    fill = gradient(im.size, [(0, GOLD_HI + (255,)), (bbox[1] / H + 0.02, GOLD_HI + (255,)),
                              (bbox[3] / H, GOLD_LO + (255,)), (1, GOLD_LO + (255,))])
    im.paste(fill, (0, 0), m)
    # a glossy highlight on the top half of the letters
    hl = Image.new("L", im.size, 0)
    ImageDraw.Draw(hl).rectangle((0, bbox[1], W, bbox[1] + (bbox[3] - bbox[1]) * 0.42), fill=70)
    hl = ImageChops.multiply(hl, m)
    white = Image.new("RGBA", im.size, (255, 255, 255, 255))
    white.putalpha(hl)
    im.alpha_composite(white)

    d = ImageDraw.Draw(im)
    sub_y = bbox[3] + 18 * SS
    d.text((x0 + 6 * SS, sub_y), "THE GREAT EDGAR HUNT", font=small, fill=(255, 248, 236, 255),
           stroke_width=4 * SS, stroke_fill=INK + (255,))
    # the project's tag as a pill
    label = "WATER TOWER RECOMPILED"
    tb = d.textbbox((0, 0), label, font=tag)
    pw, ph = tb[2] - tb[0] + 34 * SS, 40 * SS
    px, py = x0 + 6 * SS, sub_y + 52 * SS
    d.rounded_rectangle((px, py, px + pw, py + ph), ph // 2, fill=(196, 52, 46, 255),
                        outline=INK + (255,), width=3 * SS)
    d.text((px + pw // 2, py + ph // 2 + 2 * SS), label, font=tag, anchor="mm", fill=(255, 244, 228, 255))
    im = im.crop(im.getbbox())
    width = 600  # fits the Home page at the launcher's smallest size
    return im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)


# ── Buttons and panels ──────────────────────────────────────────────────

def play_button(state):
    w, h, r = 400, 92, 24
    pad = 14
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    if state == "disabled":
        face = rounded((w, h), r, (70, 62, 82, 235), outline=(120, 110, 132, 255), width=2)
        im.alpha_composite(face, (pad, pad))
        return im
    lip = rounded((w, h), r, (126, 66, 10, 255))
    top = GOLD_HI if state == "focus" else (252, 200, 74)
    face = gradient((w, h - 8), [(0, top + (255,)), (1, GOLD + (255,))])
    face.putalpha(mask_round((w, h - 8), r))
    shape = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shape.alpha_composite(lip)
    shape.alpha_composite(face)
    shine = rounded((w - 24, (h - 8) // 2 - 6), r - 8, (255, 255, 255, 60))
    shape.alpha_composite(shine, (12, 6))
    ImageDraw.Draw(shape).rounded_rectangle((1, 1, w - 2, h - 2), r, outline=INK + (255,), width=3)
    if state == "focus":
        base = Image.new("RGBA", im.size, (0, 0, 0, 0))
        base.alpha_composite(rounded((w, h), r, (255, 255, 255, 255)), (pad, pad))
        im.alpha_composite(glow(base, 7, (255, 236, 160), 1.4))
    im.alpha_composite(shape, (pad, pad))
    # play triangle
    d = ImageDraw.Draw(im)
    cx, cy = pad + 52, pad + (h - 8) // 2
    d.polygon([(cx - 14, cy - 20), (cx - 14, cy + 20), (cx + 20, cy)], fill=INK + (255,))
    return im


def soft_button(state, w=156, h=50):
    r = 14
    pad = 8
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    if state == "focus":
        fill, border = (48, 34, 70, 230), GOLD + (255,)
        base = Image.new("RGBA", im.size, (0, 0, 0, 0))
        base.alpha_composite(rounded((w, h), r, (255, 255, 255, 255)), (pad, pad))
        im.alpha_composite(glow(base, 4, GOLD, 0.9))
    elif state == "disabled":
        fill, border = (20, 16, 30, 150), (70, 64, 84, 200)
    else:
        fill, border = (18, 12, 32, 190), (255, 255, 255, 60)
    im.alpha_composite(rounded((w, h), r, fill, outline=border, width=2), (pad, pad))
    return im


def glass(size, r=18, alpha=185):
    w, h = size
    im = rounded(size, r, (12, 8, 24, alpha), outline=(255, 255, 255, 46), width=1)
    im.alpha_composite(rounded((w - 2, 2), 1, (255, 255, 255, 30)), (1, 1))
    return im


def status_icon(kind, d=44):
    im = Image.new("RGBA", (d * SS, d * SS), (0, 0, 0, 0))
    g = ImageDraw.Draw(im)
    colour = {"ok": (95, 207, 128), "warn": (245, 184, 46), "bad": (224, 90, 71), "busy": (120, 170, 255)}[kind]
    g.ellipse((2 * SS, 2 * SS, (d - 2) * SS, (d - 2) * SS), outline=colour + (255,), width=3 * SS)
    s = SS
    if kind == "ok":
        g.line([(13 * s, 23 * s), (19 * s, 29 * s), (31 * s, 15 * s)], fill=colour + (255,), width=4 * s, joint="curve")
    elif kind in ("warn", "bad"):
        g.line([(22 * s, 12 * s), (22 * s, 25 * s)], fill=colour + (255,), width=4 * s)
        g.ellipse((20 * s, 29 * s, 24 * s, 33 * s), fill=colour + (255,))
    else:
        g.arc((12 * s, 12 * s, 32 * s, 32 * s), 30, 300, fill=colour + (255,), width=4 * s)
    return im.resize((d, d), Image.LANCZOS)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)

    def save(im, name):
        path = os.path.join(OUT, name)
        im.save(path, optimize=True)
        print(f"{name:24} {im.size[0]}x{im.size[1]}  {os.path.getsize(path) // 1024} KB")

    save(hero(), "hero.png")
    save(page_banner(), "banner.png")
    save(wordmark(), "wordmark.png")
    for s in ("normal", "focus", "disabled"):
        save(play_button(s), f"play_{s}.png")
        save(soft_button(s), f"button_{s}.png")
    save(glass((840, 132)), "card.png")
    for k in ("ok", "warn", "bad", "busy"):
        save(status_icon(k), f"status_{k}.png")


if __name__ == "__main__":
    main()
