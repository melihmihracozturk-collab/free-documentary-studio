"""Öneri videolarının sahne animasyonları: yapımı anlatan hareketli grafikler (Pillow katmanları + FFmpeg hareketi).

Düzenler (scenes.layout):
  host   : stüdyo arka planı (bokeh ışıklar), büyük kayan başlık; sunucu büyük
  title  : bulanık afiş arka planı + afiş kartı (aşağıdan kayarak gelir) + bilgi kartı (yıl, tür, bölüm, puan çubuğu)
  poster : afiş kartı hafifçe süzülür, ekran yazısı etiketi
  mood   : afişin baskın renginden üretilen palet; yüzen şekiller ve büyük ekran yazısı
  full   : sunucu gizli; afiş büyük ve ortada, bulanık afiş arka planı

Afiş yoksa kart, yapımın adı ve rengiyle çizilir. Hiçbir ücretli araç kullanılmaz.
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import math
import random
from pathlib import Path

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MOTION_VERSION = "m1"
ACCENT = (155, 123, 240)


# ----------------------------------------------------------------- yardımcılar
def font(size: int, bold: bool = True):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT, size)
    except OSError:
        return ImageFont.load_default()


def hex_rgb(h: str | None, default=(120, 90, 200)) -> tuple[int, int, int]:
    try:
        h = (h or "").lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return default


def shade(rgb, light: float | None = None, sat: float | None = None, hue_shift: float = 0.0):
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    h = (h + hue_shift) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, l if light is None else light, s if sat is None else sat)
    return int(r * 255), int(g * 255), int(b * 255)


GENRE_TR = {"Action": "Aksiyon", "Adventure": "Macera", "Comedy": "Komedi", "Drama": "Dram", "Fantasy": "Fantastik",
            "Horror": "Korku", "Mystery": "Gizem", "Romance": "Romantik", "Sci-Fi": "Bilim kurgu",
            "Science Fiction": "Bilim kurgu", "Slice of Life": "Gündelik hayat", "Sports": "Spor", "Supernatural": "Doğaüstü",
            "Thriller": "Gerilim", "Psychological": "Psikolojik", "Music": "Müzik", "Mecha": "Mecha", "Crime": "Suç",
            "Animation": "Animasyon", "Family": "Aile", "History": "Tarih", "War": "Savaş", "Western": "Western",
            "Documentary": "Belgesel", "Action & Adventure": "Aksiyon & Macera", "Sci-Fi & Fantasy": "Bilim kurgu & Fantastik",
            "War & Politics": "Savaş & Politika", "Kids": "Çocuk", "Mahou Shoujo": "Büyülü kız", "Ecchi": "Ecchi"}


def tr_upper(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def latin(s: str | None) -> bool:
    return bool(s) and all(ord(ch) < 0x2E80 for ch in s)


def wrap(draw, text: str, fnt, width: int, max_lines: int = 3) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=fnt) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,") + "…"
    return lines


def gradient(size, top, bottom):
    from PIL import Image

    w, h = size
    col = Image.new("RGB", (1, h))
    for y in range(h):
        u = y / max(1, h - 1)
        col.putpixel((0, y), tuple(int(a + (b - a) * u) for a, b in zip(top, bottom)))
    return col.resize((w, h))


def rounded(img, radius: int):
    from PIL import Image, ImageDraw

    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def shadowed(card, blur: int = 24, offset: int = 14, opacity: int = 150):
    """Kartın altına yumuşak gölge ekler (kenar payı = 2*blur)."""
    from PIL import Image, ImageFilter

    pad = blur * 2
    out = Image.new("RGBA", (card.width + pad * 2, card.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", card.size, (0, 0, 0, opacity))
    sh.putalpha(card.getchannel("A").point(lambda a: a * opacity // 255))
    out.alpha_composite(sh, (pad, pad + offset))
    out = out.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(card, (pad, pad))
    return out, pad


# ----------------------------------------------------------------- arka planlar
def studio_bg(size, color, seed: int = 0):
    """Sunucu sahnesi: koyu gradyan + yumuşak bokeh ışıkları + ışık huzmesi."""
    from PIL import Image, ImageDraw, ImageFilter

    w, h = size
    base = gradient(size, shade(color, 0.16, 0.45), shade(color, 0.07, 0.5, 0.05)).convert("RGBA")
    rnd = random.Random(seed)
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    for _ in range(26):
        r = rnd.randint(int(h * 0.02), int(h * 0.09))
        x, y = rnd.randint(0, w), rnd.randint(0, int(h * 0.8))
        c = shade(color, rnd.uniform(0.55, 0.8), 0.7, rnd.uniform(-0.08, 0.12))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(*c, rnd.randint(40, 110)))
    glow = glow.filter(ImageFilter.GaussianBlur(h * 0.012))
    base.alpha_composite(glow)
    beam = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(beam).polygon([(w * 0.55, 0), (w * 0.75, 0), (w * 0.95, h), (w * 0.35, h)], fill=(255, 255, 255, 18))
    base.alpha_composite(beam.filter(ImageFilter.GaussianBlur(h * 0.05)))
    floor = gradient((w, int(h * 0.25)), (0, 0, 0), shade(color, 0.05)).convert("RGBA")
    floor.putalpha(gradient((w, int(h * 0.25)), (0, 0, 0), (170, 170, 170)).convert("L"))
    base.alpha_composite(floor, (0, h - floor.height))
    return base.convert("RGB")


def poster_bg(size, poster, color):
    """Bulanık, koyulaştırılmış afiş + sola doğru kararan gradyan (yazı okunur)."""
    from PIL import Image, ImageFilter, ImageOps

    w, h = size
    if poster is None:
        return studio_bg(size, color, 7)
    bg = ImageOps.fit(poster.convert("RGB"), size).filter(ImageFilter.GaussianBlur(max(w, h) * 0.02))
    dark = Image.new("RGB", size, shade(color, 0.06, 0.4))
    bg = Image.blend(bg, dark, 0.55)
    side = gradient((h, w), (0, 0, 0), (110, 110, 110)).rotate(90, expand=True).convert("L")
    bg.paste(Image.new("RGB", size, (8, 8, 16)), (0, 0), side.point(lambda a: 150 - a))
    return bg


def mood_bg(size, color, seed: int = 0):
    """Yapımın renginden palet: çapraz gradyan + büyük yumuşak lekeler."""
    from PIL import Image, ImageDraw, ImageFilter

    w, h = size
    a, b = shade(color, 0.32, 0.65), shade(color, 0.14, 0.55, 0.12)
    base = gradient((w, h), a, b).convert("RGBA")
    rnd = random.Random(seed)
    blob = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(blob)
    for k in range(5):
        r = rnd.randint(int(h * 0.2), int(h * 0.45))
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(*shade(color, 0.5, 0.75, (k - 2) * 0.06), 90))
    base.alpha_composite(blob.filter(ImageFilter.GaussianBlur(h * 0.08)))
    return base.convert("RGB")


# ----------------------------------------------------------------- kartlar
def poster_card(poster, title: dict, height: int, color):
    from PIL import Image, ImageDraw

    w = int(height * 2 / 3)
    if poster is not None:
        from PIL import ImageOps
        card = ImageOps.fit(poster.convert("RGB"), (w, height))
    else:
        card = gradient((w, height), shade(color, 0.45, 0.6), shade(color, 0.18, 0.6)).convert("RGB")
        d = ImageDraw.Draw(card)
        f = font(int(height * 0.08))
        lines = wrap(d, title.get("name") or "", f, int(w * 0.8), 4)
        y = height * 0.4 - len(lines) * f.size * 0.6
        for ln in lines:
            d.text((w / 2, y), ln, font=f, fill=(255, 255, 255), anchor="mt")
            y += f.size * 1.2
    card = rounded(card, int(height * 0.03))
    border = Image.new("RGBA", (w + 8, height + 8), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle((0, 0, w + 7, height + 7), int(height * 0.03) + 4, fill=(255, 255, 255, 230))
    border.alpha_composite(card, (4, 4))
    return shadowed(border)


def meta_line(t: dict) -> str:
    parts = []
    if t.get("year"):
        parts.append(str(t["year"]))
    if t.get("format"):
        parts.append(str(t["format"]))
    if t.get("seasons"):
        parts.append(f"{t['seasons']} sezon")
    if t.get("episodes"):
        parts.append(f"{t['episodes']} bölüm")
    elif t.get("runtime") and t.get("kind") == "film":
        parts.append(f"{t['runtime']} dk")
    return " · ".join(parts)


def info_card(t: dict, rank: int | None, width: int, color, compact: bool = False):
    """Yapım bilgi kartı: sıra rozeti, ad, özgün ad, yıl/biçim/bölüm, tür etiketleri, puan çubuğu, stüdyo."""
    from PIL import Image, ImageDraw

    scale = 0.8 if compact else 1.0
    img = Image.new("RGBA", (width, int(760 * scale)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    acc = shade(color, 0.68, 0.8)
    y = 0
    if rank:
        f = font(int(40 * scale))
        label = f"#{rank}"
        tw = d.textlength(label, font=f)
        d.rounded_rectangle((0, y, tw + 44 * scale, y + 64 * scale), int(32 * scale), fill=(*acc, 255))
        d.text((22 * scale, y + 32 * scale), label, font=f, fill=(20, 16, 36), anchor="lm")
        y += int(88 * scale)
    f = font(int(66 * scale))
    for ln in wrap(d, t.get("name") or "", f, width, 3):
        d.text((0, y), ln, font=f, fill=(255, 255, 255))
        y += int(f.size * 1.15)
    orig = t.get("original") if latin(t.get("original")) else (t.get("name_en") if t.get("name_en") != t.get("name") else None)
    if orig and orig != t.get("name"):
        f2 = font(int(32 * scale), bold=False)
        d.text((0, y + 4), wrap(d, orig, f2, width, 1)[0], font=f2, fill=(220, 214, 240))
        y += int(52 * scale)
    y += int(14 * scale)
    d.rectangle((0, y, int(120 * scale), y + 6), fill=(*acc, 255))
    y += int(30 * scale)
    ml = meta_line(t)
    if ml:
        f3 = font(int(34 * scale), bold=False)
        for ln in wrap(d, ml, f3, width, 2):
            d.text((0, y), ln, font=f3, fill=(240, 236, 250))
            y += int(46 * scale)
        y += int(10 * scale)
    if t.get("genres"):
        f4 = font(int(28 * scale))
        x = 0
        for g in [GENRE_TR.get(x, x) for x in t["genres"][:4]]:
            gw = d.textlength(g, font=f4) + 36 * scale
            if x + gw > width:
                break
            d.rounded_rectangle((x, y, x + gw, y + 50 * scale), int(25 * scale), fill=(255, 255, 255, 40),
                                outline=(*acc, 255), width=2)
            d.text((x + gw / 2, y + 25 * scale), g, font=f4, fill=(255, 255, 255), anchor="mm")
            x += gw + 14 * scale
        y += int(74 * scale)
    if t.get("score"):
        f5 = font(int(32 * scale))
        sc = max(0.0, min(100.0, float(t["score"])))
        bar = int(min(width, 520 * scale))
        d.text((0, y), f"★ {sc:.0f}/100", font=f5, fill=(255, 214, 102))
        d.text((bar, y + 4), t.get("score_source") or "", font=font(int(24 * scale), bold=False), fill=(220, 214, 240), anchor="ra")
        y += int(50 * scale)
        d.rounded_rectangle((0, y, bar, y + 14 * scale), int(7 * scale), fill=(255, 255, 255, 50))
        d.rounded_rectangle((0, y, max(14, bar * sc / 100), y + 14 * scale), int(7 * scale), fill=(255, 214, 102, 255))
        y += int(40 * scale)
    if t.get("studio"):
        f6 = font(int(26 * scale), bold=False)
        d.text((0, y), wrap(d, f"Yapım: {t['studio']}", f6, width, 1)[0], font=f6, fill=(205, 198, 225))
        y += int(40 * scale)
    return img.crop((0, 0, width, max(10, y)))


def headline(text: str, width: int, size: int, color, sub: str | None = None):
    """Büyük başlık: vurgu çubuğu + kalın yazı (+ küçük üst etiket)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (width, size * 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    acc = shade(color, 0.7, 0.8)
    y = 0
    if sub:
        fs = font(int(size * 0.42))
        d.text((0, 0), tr_upper(sub), font=fs, fill=(*acc, 255))
        y += int(size * 0.7)
    f = font(size)
    lines = wrap(d, text, f, width, 3)
    for ln in lines:
        d.text((4, y + 4), ln, font=f, fill=(0, 0, 0, 110))
        d.text((0, y), ln, font=f, fill=(255, 255, 255))
        y += int(size * 1.15)
    d.rounded_rectangle((0, y + 10, int(size * 2.4), y + 22), 6, fill=(*acc, 255))
    return img.crop((0, 0, width, y + 30))


def chip(text: str, size: int, color):
    from PIL import Image, ImageDraw

    f = font(size)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = tmp.textlength(text, font=f)
    img = Image.new("RGBA", (int(tw + size * 1.6), int(size * 1.9)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, img.height - 1), img.height // 2, fill=(*shade(color, 0.2, 0.5), 225),
                        outline=(*shade(color, 0.7, 0.8), 255), width=3)
    d.text((img.width / 2, img.height / 2), text, font=f, fill=(255, 255, 255), anchor="mm")
    return img


def shape(kind: str, r: int, rgba):
    from PIL import Image, ImageDraw, ImageFilter

    img = Image.new("RGBA", (r * 2 + 20, r * 2 + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = (10 + r, 10 + r)
    if kind == "ring":
        d.ellipse((10, 10, 10 + 2 * r, 10 + 2 * r), outline=rgba, width=max(4, r // 8))
    elif kind == "tri":
        d.polygon([(c[0] + r * math.cos(a), c[1] + r * math.sin(a)) for a in (-math.pi / 2, math.pi / 6, 5 * math.pi / 6)],
                  outline=rgba, width=max(4, r // 9))
    elif kind == "star":
        pts = []
        for k in range(10):
            a = -math.pi / 2 + k * math.pi / 5
            rr = r if k % 2 == 0 else r * 0.45
            pts.append((c[0] + rr * math.cos(a), c[1] + rr * math.sin(a)))
        d.polygon(pts, fill=rgba)
    else:
        d.ellipse((10, 10, 10 + 2 * r, 10 + 2 * r), fill=rgba)
    return img.filter(ImageFilter.GaussianBlur(1.2))


# ----------------------------------------------------------------- sahne
def content_box(fmt_kind: str, w: int, h: int, layout: str) -> tuple[int, int, int, int]:
    """Grafiklerin yerleşeceği alan: sunucu ve altyazı alanı dışında kalır."""
    if fmt_kind == "shorts":
        return (60, 150, w - 60, 1090)
    if layout == "full":
        return (100, 60, w - 100, h - 170)
    return (90, 70, 1110, h - 190)


def ease(st: float, d: float) -> str:
    u = f"clip((t-{st:.2f})/{d:.2f},0,1)"
    return f"({u}*{u}*(3-2*{u}))"


class Layer:
    def __init__(self, img, x: str, y: str, fade_st: float = 0.0, fade_d: float = 0.0):
        self.img, self.x, self.y, self.fade_st, self.fade_d = img, x, y, fade_st, fade_d


def build(layout: str, fmt_kind: str, w: int, h: int, title: dict | None, poster, text: str | None,
          rank: int | None, heading: str | None, seed: int = 0):
    """Sahnenin arka planı ve hareketli katmanları. Dönüş: (arka plan RGB, kamera hareketi, [Layer])."""
    t = title or {}
    color = hex_rgb(t.get("color")) if t.get("color") else ((235, 120, 160) if not t else (120, 90, 200))
    x0, y0, x1, y1 = content_box(fmt_kind, w, h, layout)
    bw, bh = x1 - x0, y1 - y0
    layers: list[Layer] = []
    vertical = fmt_kind == "shorts"

    if layout == "host" or not t:
        bg = studio_bg((w, h), color, seed)
        hl = headline(text or heading or "", int(bw * (0.95 if vertical else 0.9)), 92 if not vertical else 84, color,
                      sub=heading if text and heading and heading != text else None)
        ty = y0 + (bh - hl.height) // 2 if not vertical else y0 + 120
        layers.append(Layer(hl, f"{x0}-{bw}*(1-{ease(0.15, 0.7)})", str(ty), 0.15, 0.5))
        for k in range(4):
            sh = shape(("star", "ring", "dot", "ring")[k], 18 + 10 * k, (*shade(color, 0.75, 0.8), 150))
            sx, sy = x0 + (k * 0.27 + 0.05) * bw, y0 + (0.1 + 0.8 * ((k * 37 + seed) % 10) / 10) * bh
            layers.append(Layer(sh, f"{sx:.0f}+30*sin(t*{0.5 + k * 0.17:.2f}+{k})", f"{sy:.0f}+24*cos(t*{0.4 + k * 0.13:.2f}+{k})",
                                0.4 + 0.2 * k, 0.8))
        return bg, "ken_burns", layers

    if layout == "mood":
        bg = mood_bg((w, h), color, seed)
        for k in range(6):
            r = int(min(w, h) * (0.04 + 0.03 * (k % 3)))
            sh = shape(("ring", "tri", "star", "dot", "ring", "tri")[k], r, (*shade(color, 0.8, 0.7, k * 0.04), 140))
            sx, sy = x0 + ((k * 0.19 + 0.08) % 1) * bw, y0 + ((k * 0.31 + 0.1) % 1) * bh
            layers.append(Layer(sh, f"{sx:.0f}+{40 + k * 8}*sin(t*{0.35 + k * 0.11:.2f}+{k})",
                                f"{sy:.0f}+{30 + k * 6}*cos(t*{0.3 + k * 0.09:.2f}+{k * 2})", 0.1 * k, 0.8))
        if poster is not None:
            card, pad = poster_card(poster, t, int(bh * (0.36 if vertical else 0.42)), color)
            cx = x1 - card.width + pad if not vertical else x0 + (bw - card.width) // 2
            layers.append(Layer(card, str(cx), f"{y1 - card.height + pad}+10*sin(t*0.8)", 0.5, 0.6))
        hl = headline(text or t.get("name") or "", int(bw * (0.62 if not vertical else 0.92)), 96 if not vertical else 80,
                      color, sub=t.get("name") if text else None)
        layers.append(Layer(hl, str(x0), f"{y0 + (bh * (0.3 if not vertical else 0.1)):.0f}+40*(1-{ease(0.2, 0.8)})", 0.2, 0.7))
        return bg, "zoom_in", layers

    bg = poster_bg((w, h), poster, color)
    if layout == "title":
        ph = int(bh * (0.95 if not vertical else 0.52))
        card, pad = poster_card(poster, t, ph, color)
        if vertical:
            cx, cy = x0 + (bw - card.width + 2 * pad) // 2 - pad, y0 - pad
        else:
            cx, cy = x0 - pad, y0 + (bh - ph) // 2 - pad
        layers.append(Layer(card, str(cx), f"{cy}+{int(h * 0.5)}*(1-{ease(0.0, 0.8)})", 0.0, 0.4))
        iw = (bw - (card.width - 2 * pad) - 60) if not vertical else bw
        info = info_card(t, rank, max(300, iw), color, compact=vertical)
        ix = x0 + card.width - 2 * pad + 60 if not vertical else x0
        iy = y0 + (bh - info.height) // 2 if not vertical else y0 + ph + 30
        layers.append(Layer(info, f"{ix}+120*(1-{ease(0.45, 0.7)})", str(iy), 0.45, 0.6))
        return bg, "static", layers

    # poster / full
    ph = int(bh * (0.98 if layout == "full" and not vertical else 0.9 if not vertical else 0.7))
    card, pad = poster_card(poster, t, ph, color)
    cx = x0 + (bw - card.width + 2 * pad) // 2 - pad
    if layout == "poster" and not vertical:
        cx = x0 + int(bw * 0.08) - pad
    cy = y0 + (bh - ph) // 2 - pad
    layers.append(Layer(card, f"{cx}+6*sin(t*0.6)", f"{cy}+10*sin(t*0.9)", 0.0, 0.5))
    if text:
        c = chip(text[:48], 40 if not vertical else 38, color)
        if layout == "poster" and not vertical:
            tx, ty_ = cx + card.width - pad + 50, y0 + bh // 2 - c.height // 2
        else:
            tx, ty_ = x0 + (bw - c.width) // 2, y1 - c.height + 20
        layers.append(Layer(c, f"{tx}+60*(1-{ease(0.5, 0.6)})", str(ty_), 0.5, 0.5))
    return bg, ("zoom_out" if layout == "full" else "pan_right"), layers


def scene_key(layout: str, title: dict | None, text: str | None, rank, heading, dur: float, fmt_kind: str, poster_sha: str | None) -> str:
    raw = json.dumps([MOTION_VERSION, layout, title or {}, text, rank, heading, round(dur, 3), fmt_kind, poster_sha],
                     sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def render_scene(out: Path, tmp: Path, dur: float, fmt, layout: str, title: dict | None, poster_path: Path | None,
                 text: str | None, rank: int | None, heading: str | None, seed: int = 0) -> None:
    """Sahne klibi (MP4, sessiz): hareketli arka plan + kayarak/solarak gelen katmanlar."""
    from PIL import Image

    from .render import motion_filter, run

    poster = Image.open(poster_path).convert("RGB") if poster_path and poster_path.exists() else None
    bg, move, layers = build(layout, fmt.kind, fmt.w, fmt.h, title, poster, text, rank, heading, seed)
    stem = out.stem
    bg_path = tmp / f"{stem}-bg.jpg"
    bg.save(bg_path, quality=92)
    vf, n = motion_filter(move, dur, fmt, seed)
    inputs = ["-i", str(bg_path)]
    fg = [f"[0:v]{vf}[b0]"]
    last = "[b0]"
    for k, L in enumerate(layers, 1):
        lp = tmp / f"{stem}-l{k}.png"
        L.img.save(lp)
        inputs += ["-loop", "1", "-framerate", str(fmt.fps), "-t", f"{dur + 0.5:.3f}", "-i", str(lp)]
        fade = f",fade=t=in:st={L.fade_st:.2f}:d={L.fade_d:.2f}:alpha=1" if L.fade_d > 0 else ""
        fg.append(f"[{k}:v]format=rgba{fade}[l{k}]")
        fg.append(f"{last}[l{k}]overlay=x='{L.x}':y='{L.y}':eval=frame:format=auto[b{k}]")
        last = f"[b{k}]"
    fg.append(f"{last}format=yuv420p[v]")
    run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fg), "-map", "[v]",
         "-frames:v", str(n), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
         "-r", str(fmt.fps), str(out)])
