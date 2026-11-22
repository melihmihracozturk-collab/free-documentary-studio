"""Sunucu karakter: kodla çizilmiş 2D anime tarzı kadın sunucu ve animasyon motoru (tamamen ücretsiz, bulutta).

Karakter katmanlı SVG olarak tanımlıdır (göz: açık/yarı/kapalı, kaş: normal/kalkık, ağız: 6 şekil). Katmanlar
cairosvg ile istenen ölçekte PNG'ye çevrilir; her kare Pillow ile birleştirilir:

- Nefes alma (gövde yavaşça iner/kalkar), baş salınımı ve konuşurken hafif baş sallama
- Rastgele aralıklarla göz kırpma
- Sese göre ağız hareketi (genlik + sıfır geçiş oranı → 6 ağız şekli; dudak senkronu)
- Cümle başlarında kaş kaldırma
- Sahne düzenine göre büyük / orta / gizli konumlar arasında yumuşak geçiş

Çıktı: saydam (alfa kanallı) VP9 WebM; render sırasında videonun üstüne bindirilir.
"""
from __future__ import annotations

import io
import math
import random
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PRESENTER_VERSION = "p1"
VIEW_W, VIEW_H = 1000, 1300
PIVOT = (500, 640)                 # boyun üstü: baş bu noktanın çevresinde döner
HEAD_BOX = (250, 110, 760, 760)    # baş katmanlarının kırpma kutusu (dönüş payı dahil)
BACK_BOX = (180, 110, 820, 1300)
BODY_BOX = (230, 580, 770, 1300)

C = {
    "skin": "#FBE5D8", "skin_sh": "#F1C3B0", "blush": "#F59AA6",
    "hair": "#3A2A5C", "hair_dark": "#2A1D45", "hair_hi": "#6B58A3",
    "iris": "#8A5CF0", "iris_dark": "#3E2185", "lash": "#24163A", "white": "#FFFFFF",
    "lip": "#D9636F", "mouth": "#7A2338", "tongue": "#E8838E", "teeth": "#FFFFFF",
    "hoodie": "#F4EFE8", "hoodie_sh": "#DCD3C8", "accent": "#9B7BF0",
    "phones": "#2F2C3D", "phones_hi": "#4A4660", "star": "#FFD166",
}

EYES = ("open", "half", "closed")
BROWS = ("neutral", "up")
MOUTHS = ("rest", "a", "b", "wide", "o", "e")


def _svg(body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW_W} {VIEW_H}" width="{VIEW_W}" height="{VIEW_H}">'
            f'<defs>'
            f'<radialGradient id="iris" cx="50%" cy="62%" r="60%"><stop offset="0" stop-color="{C["iris"]}"/>'
            f'<stop offset="1" stop-color="{C["iris_dark"]}"/></radialGradient>'
            f'<linearGradient id="hairg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C["hair"]}"/>'
            f'<stop offset="1" stop-color="{C["hair_dark"]}"/></linearGradient>'
            f'</defs>{body}</svg>')


# ----------------------------------------------------------------- katmanlar (SVG)
def layer_back_hair() -> str:
    return _svg(f"""
<path fill="url(#hairg)" d="M300 420 C270 250 380 150 500 150 C620 150 730 250 700 420
  C720 560 760 700 770 860 C772 930 740 990 700 1010 C690 940 660 900 640 880 L360 880
  C340 900 310 940 300 1010 C260 990 228 930 230 860 C240 700 280 560 300 420 Z"/>""")


def layer_body() -> str:
    c = C
    return _svg(f"""
<path fill="{c['skin_sh']}" d="M452 590 L548 590 L552 735 C530 750 470 750 448 735 Z"/>
<path fill="{c['skin_sh']}" opacity="0.9" d="M452 600 C470 640 530 640 548 600 L548 650 C525 670 475 670 452 650 Z"/>
<path fill="{c['hoodie_sh']}" d="M360 742 C400 700 450 705 500 728 C550 705 600 700 640 742 L600 790 L400 790 Z"/>
<path fill="{c['hoodie']}" d="M250 1300 L262 900 C268 820 300 770 360 745 C410 728 445 730 470 752
  L500 800 L530 752 C555 730 590 728 640 745 C700 770 732 820 738 900 L750 1300 Z"/>
<path fill="none" stroke="{c['hoodie_sh']}" stroke-width="6" stroke-linecap="round" d="M330 900 C335 1000 330 1120 325 1300"/>
<path fill="none" stroke="{c['hoodie_sh']}" stroke-width="6" stroke-linecap="round" d="M670 900 C665 1000 670 1120 675 1300"/>
<path fill="{c['hoodie_sh']}" d="M470 752 L500 800 L530 752 C520 790 510 815 500 822 C490 815 480 790 470 752 Z"/>
<path fill="none" stroke="{c['accent']}" stroke-width="7" stroke-linecap="round" d="M468 790 C462 850 466 900 460 950"/>
<path fill="none" stroke="{c['accent']}" stroke-width="7" stroke-linecap="round" d="M532 790 C538 850 534 900 540 955"/>
<circle cx="460" cy="958" r="9" fill="{c['accent']}"/><circle cx="540" cy="962" r="9" fill="{c['accent']}"/>
<rect x="420" y="1080" width="160" height="110" rx="26" fill="{c['hoodie_sh']}" opacity="0.55"/>
<path fill="none" stroke="{c['phones']}" stroke-width="18" stroke-linecap="round" d="M392 742 C410 800 590 800 608 742"/>
<rect x="366" y="690" width="52" height="86" rx="24" fill="{c['phones']}" transform="rotate(-18 392 733)"/>
<rect x="582" y="690" width="52" height="86" rx="24" fill="{c['phones']}" transform="rotate(18 608 733)"/>
<rect x="378" y="706" width="26" height="54" rx="13" fill="{c['phones_hi']}" transform="rotate(-18 392 733)"/>
<rect x="596" y="706" width="26" height="54" rx="13" fill="{c['phones_hi']}" transform="rotate(18 608 733)"/>
<circle cx="392" cy="733" r="7" fill="{c['accent']}"/><circle cx="608" cy="733" r="7" fill="{c['accent']}"/>""")


def layer_face() -> str:
    c = C
    return _svg(f"""
<ellipse cx="362" cy="468" rx="22" ry="34" fill="{c['skin_sh']}"/>
<ellipse cx="638" cy="468" rx="22" ry="34" fill="{c['skin_sh']}"/>
<path fill="{c['skin']}" d="M362 380 C358 500 410 590 470 628 C488 640 512 640 530 628 C590 590 642 500 638 380
  C636 270 364 270 362 380 Z"/>
<ellipse cx="418" cy="530" rx="34" ry="16" fill="{c['blush']}" opacity="0.45"/>
<ellipse cx="582" cy="530" rx="34" ry="16" fill="{c['blush']}" opacity="0.45"/>
<path fill="none" stroke="{c['skin_sh']}" stroke-width="5" stroke-linecap="round" d="M500 508 L494 528 L503 530"/>""")


def _eye(cx: float, cy: float, state: str, flip: bool) -> str:
    c = C
    s = -1 if flip else 1
    if state == "closed":
        return (f'<path fill="none" stroke="{c["lash"]}" stroke-width="9" stroke-linecap="round" '
                f'd="M{cx - 40} {cy + 2} C{cx - 20} {cy + 20} {cx + 20} {cy + 20} {cx + 40} {cy + 2}"/>'
                f'<path fill="none" stroke="{c["lash"]}" stroke-width="5" stroke-linecap="round" '
                f'd="M{cx + 40 * s} {cy + 2} L{cx + 52 * s} {cy - 6}"/>')
    white = (f'<path fill="{c["white"]}" d="M{cx - 40} {cy - 4} C{cx - 30} {cy - 38} {cx + 30} {cy - 38} {cx + 40} {cy - 4}'
             f' C{cx + 34} {cy + 30} {cx - 34} {cy + 30} {cx - 40} {cy - 4} Z"/>')
    iris = (f'<ellipse cx="{cx}" cy="{cy + 2}" rx="25" ry="31" fill="url(#iris)"/>'
            f'<ellipse cx="{cx}" cy="{cy + 6}" rx="11" ry="15" fill="{c["iris_dark"]}"/>'
            f'<circle cx="{cx - 9 * s}" cy="{cy - 10}" r="9" fill="{c["white"]}"/>'
            f'<circle cx="{cx + 10 * s}" cy="{cy + 14}" r="4" fill="{c["white"]}" opacity="0.9"/>')
    clip = f'<clipPath id="e{int(cx)}"><path d="M{cx - 40} {cy - 4} C{cx - 30} {cy - 38} {cx + 30} {cy - 38} {cx + 40} {cy - 4} C{cx + 34} {cy + 30} {cx - 34} {cy + 30} {cx - 40} {cy - 4} Z"/></clipPath>'
    lid = ""
    top = cy - 30                       # üst kirpik çizgisinin orta yüksekliği
    if state == "half":
        lid = f'<rect x="{cx - 45}" y="{cy - 45}" width="90" height="46" fill="{c["skin"]}"/>'
        top = cy - 4
    o = cx + 44 * s                      # dış köşe
    i = cx - 42 * s                      # iç köşe
    lash = (f'<path fill="{c["lash"]}" d="M{i} {top + 26} C{cx - 22 * s} {top - 4} {cx + 22 * s} {top - 4} {o} {top + 20}'
            f' L{o + 14 * s} {top + 8} C{cx + 24 * s} {top - 16} {cx - 24 * s} {top - 14} {i - 4 * s} {top + 20} Z"/>')
    lower = (f'<path fill="none" stroke="{c["lash"]}" stroke-width="3" stroke-linecap="round" opacity="0.35" '
             f'd="M{cx + 6 * s} {cy + 28} C{cx + 18 * s} {cy + 27} {cx + 28 * s} {cy + 24} {cx + 34 * s} {cy + 18}"/>')
    return f'<defs>{clip}</defs><g clip-path="url(#e{int(cx)})">{white}{iris}{lid}</g>{lash}{lower}'


def layer_eyes(state: str) -> str:
    return _svg(_eye(438, 460, state, True) + _eye(562, 460, state, False))


def layer_brows(state: str) -> str:
    dy = -14 if state == "up" else 0
    c = C
    return _svg(f"""
<path fill="none" stroke="{c['hair_dark']}" stroke-width="8" stroke-linecap="round" d="M400 {404 + dy} C420 {392 + dy} 450 {390 + dy} 474 {398 + dy}"/>
<path fill="none" stroke="{c['hair_dark']}" stroke-width="8" stroke-linecap="round" d="M526 {398 + dy} C550 {390 + dy} 580 {392 + dy} 600 {404 + dy}"/>""")


def layer_mouth(shape: str) -> str:
    c = C
    x, y = 500, 572
    if shape == "rest":
        body = (f'<path fill="none" stroke="{c["mouth"]}" stroke-width="6" stroke-linecap="round" '
                f'd="M{x - 22} {y - 2} C{x - 10} {y + 10} {x + 10} {y + 10} {x + 22} {y - 2}"/>')
    elif shape == "a":
        body = (f'<path fill="{c["mouth"]}" d="M{x - 20} {y - 4} C{x - 10} {y - 8} {x + 10} {y - 8} {x + 20} {y - 4}'
                f' C{x + 14} {y + 12} {x - 14} {y + 12} {x - 20} {y - 4} Z"/>')
    elif shape == "b":
        body = (f'<path fill="{c["mouth"]}" d="M{x - 26} {y - 6} C{x - 12} {y - 10} {x + 12} {y - 10} {x + 26} {y - 6}'
                f' C{x + 20} {y + 22} {x - 20} {y + 22} {x - 26} {y - 6} Z"/>'
                f'<path fill="{c["tongue"]}" d="M{x - 13} {y + 12} C{x - 6} {y + 4} {x + 6} {y + 4} {x + 13} {y + 12}'
                f' C{x + 6} {y + 17} {x - 6} {y + 17} {x - 13} {y + 12} Z"/>')
    elif shape == "wide":
        body = (f'<path fill="{c["mouth"]}" d="M{x - 30} {y - 8} C{x - 14} {y - 12} {x + 14} {y - 12} {x + 30} {y - 8}'
                f' C{x + 26} {y + 34} {x - 26} {y + 34} {x - 30} {y - 8} Z"/>'
                f'<path fill="{c["teeth"]}" d="M{x - 24} {y - 7} C{x - 10} {y - 10} {x + 10} {y - 10} {x + 24} {y - 7}'
                f' L{x + 22} {y} C{x + 8} {y + 2} {x - 8} {y + 2} {x - 22} {y} Z"/>'
                f'<path fill="{c["tongue"]}" d="M{x - 16} {y + 22} C{x - 8} {y + 12} {x + 8} {y + 12} {x + 16} {y + 22}'
                f' C{x + 8} {y + 28} {x - 8} {y + 28} {x - 16} {y + 22} Z"/>')
    elif shape == "o":
        body = (f'<ellipse cx="{x}" cy="{y + 6}" rx="14" ry="18" fill="{c["mouth"]}"/>'
                f'<ellipse cx="{x}" cy="{y + 15}" rx="8" ry="6" fill="{c["tongue"]}"/>')
    else:  # "e": geniş, dişler görünür
        body = (f'<path fill="{c["mouth"]}" d="M{x - 30} {y - 4} C{x - 14} {y - 8} {x + 14} {y - 8} {x + 30} {y - 4}'
                f' C{x + 24} {y + 14} {x - 24} {y + 14} {x - 30} {y - 4} Z"/>'
                f'<path fill="{c["teeth"]}" d="M{x - 25} {y - 4} C{x - 10} {y - 7} {x + 10} {y - 7} {x + 25} {y - 4}'
                f' L{x + 22} {y + 3} C{x + 8} {y + 5} {x - 8} {y + 5} {x - 22} {y + 3} Z"/>')
    return _svg(body)


def layer_front_hair() -> str:
    c = C
    return _svg(f"""
<path fill="url(#hairg)" d="M352 470 C330 330 400 205 500 200 C600 205 670 330 648 470
  L632 430 C628 380 612 345 596 330 L604 412 C584 370 566 340 548 326 L548 398 C530 360 512 336 496 326
  L486 402 C470 366 452 340 440 332 L426 408 C410 376 396 356 384 346 C378 380 372 420 368 470 Z"/>
<path fill="url(#hairg)" d="M366 420 C340 500 342 590 362 660 C368 620 380 590 392 560 C384 520 380 470 384 430 Z"/>
<path fill="url(#hairg)" d="M634 420 C660 500 658 590 638 660 C632 620 620 590 608 560 C616 520 620 470 616 430 Z"/>
<path fill="none" stroke="{c['hair_hi']}" stroke-width="10" stroke-linecap="round" opacity="0.8"
  d="M410 262 C450 238 550 238 590 262"/>
<path fill="none" stroke="{c['hair_hi']}" stroke-width="6" stroke-linecap="round" opacity="0.6" d="M560 252 C575 262 588 272 596 284"/>
<path fill="{c['star']}" d="M612 300 L620 318 L640 320 L625 333 L630 353 L612 342 L594 353 L599 333 L584 320 L604 318 Z"/>
<circle cx="586" cy="356" r="6" fill="{c['accent']}"/>""")


# ----------------------------------------------------------------- PNG'ye çevirme
def _raster(svg: str, scale: float):
    import cairosvg
    from PIL import Image

    w, h = round(VIEW_W * scale), round(VIEW_H * scale)
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=w, output_height=h)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def _crop(img, box, scale):
    return img.crop(tuple(round(v * scale) for v in box))


@lru_cache(maxsize=16)
def layers(scale: float) -> dict:
    """Bir ölçek için tüm katmanlar (kırpılmış). Ölçekler 0.025 adımlarla önbelleğe alınır."""
    out = {
        "back": _crop(_raster(layer_back_hair(), scale), BACK_BOX, scale),
        "body": _crop(_raster(layer_body(), scale), BODY_BOX, scale),
        "face": _crop(_raster(layer_face(), scale), HEAD_BOX, scale),
        "front": _crop(_raster(layer_front_hair(), scale), HEAD_BOX, scale),
    }
    for e in EYES:
        out[f"eyes_{e}"] = _crop(_raster(layer_eyes(e), scale), HEAD_BOX, scale)
    for b in BROWS:
        out[f"brows_{b}"] = _crop(_raster(layer_brows(b), scale), HEAD_BOX, scale)
    for m in MOUTHS:
        out[f"mouth_{m}"] = _crop(_raster(layer_mouth(m), scale), HEAD_BOX, scale)
    return out


ANGLE_STEP = 0.15                  # baş eğimi bu adımlarla önbelleğe alınır (yarıçap ~300 px'te < 1 px)
MAX_ANGLE = 4.5
FEATURE_BOX = {"eyes": (372, 400, 628, 505), "brows": (388, 366, 612, 418), "mouth": (458, 548, 542, 612)}


@lru_cache(maxsize=220)
def rotated(scale: float, name: str, angle: float):
    """Statik baş katmanı (yüz / ön saç) döndürülmüş hâli; pivot boyun üstü."""
    from PIL import Image

    img = layers(scale)[name]
    if not angle:
        return img
    cx, cy = PIVOT[0] * scale - HEAD_BOX[0] * scale, PIVOT[1] * scale - HEAD_BOX[1] * scale
    return img.rotate(angle, resample=Image.BICUBIC, center=(cx, cy))


@lru_cache(maxsize=64)
def feature(scale: float, kind: str, state: str):
    """Göz / kaş / ağız katmanının sıkı kırpılmış hâli."""
    box = FEATURE_BOX[kind]
    return layers(scale)[f"{kind}_{state}"].crop(tuple(round((v - o) * scale) for v, o in
                                                       zip(box, (HEAD_BOX[0], HEAD_BOX[1], HEAD_BOX[0], HEAD_BOX[1]))))


def head(scale: float, eyes: str, brows: str, mouth: str, angle: float = 0.0):
    """Baş (HEAD_BOX kırpımı): döndürülmüş yüz + döndürülmüş yüz parçaları + döndürülmüş ön saç."""
    from PIL import Image

    angle = max(-MAX_ANGLE, min(MAX_ANGLE, round(angle / ANGLE_STEP) * ANGLE_STEP))
    img = rotated(scale, "face", angle).copy()
    rad = math.radians(angle)
    px, py = PIVOT
    for kind, state in (("eyes", eyes), ("brows", brows), ("mouth", mouth)):
        f = feature(scale, kind, state)
        box = FEATURE_BOX[kind]
        mx, my = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        # Parça merkezini pivot çevresinde döndür (PIL: pozitif açı = saat yönünün tersi)
        dx, dy = mx - px, my - py
        rx = px + dx * math.cos(rad) + dy * math.sin(rad)
        ry = py - dx * math.sin(rad) + dy * math.cos(rad)
        if angle:
            f = f.rotate(angle, resample=Image.BICUBIC, expand=True)
        x = round((rx - HEAD_BOX[0]) * scale - f.width / 2)
        y = round((ry - HEAD_BOX[1]) * scale - f.height / 2)
        img.alpha_composite(f, dest=(x, y))
    img.alpha_composite(rotated(scale, "front", angle))
    return img


def full_svg(eyes: str = "open", brows: str = "neutral", mouth: str = "rest") -> str:
    """Panelde gösterilecek tek parça SVG (önizleme)."""
    import re

    parts = [layer_back_hair(), layer_body(), layer_face(), layer_eyes(eyes), layer_brows(brows), layer_mouth(mouth),
             layer_front_hair()]
    # Her katmanın dış <svg> etiketi ve ortak gradyan tanımı (ilk <defs>) atılır, tek SVG'de birleştirilir
    inner = [re.sub(r"<defs>.*?</defs>", "", re.sub(r"^<svg[^>]*>|</svg>$", "", x), count=1) for x in parts]
    return _svg("".join(inner))


# ----------------------------------------------------------------- kare çizimi
@dataclass
class Pose:
    scale: float
    x: float                 # karakter tuvalinin sol üst köşesi (bölge koordinatı)
    y: float
    angle: float = 0.0       # baş eğimi (derece)
    breath: float = 0.0      # gövde dikey kayması (görünüm birimi)
    bob: float = 0.0         # baş dikey kayması (görünüm birimi)
    eyes: str = "open"
    brows: str = "neutral"
    mouth: str = "rest"


def quant(scale: float) -> float:
    return round(round(scale / 0.025) * 0.025, 3)


def draw(pose: Pose, size: tuple[int, int]):
    """Bölge boyutunda saydam kare."""
    from PIL import Image

    frame = Image.new("RGBA", size, (0, 0, 0, 0))
    s = quant(pose.scale)
    if s <= 0:
        return frame
    L = layers(s)
    ox, oy = pose.x, pose.y

    def paste(img, box, dx=0.0, dy=0.0):
        x, y = ox + box[0] * s + dx, oy + box[1] * s + dy
        if _inside(frame, img, x, y):
            frame.alpha_composite(img, dest=(round(x), round(y)))
        else:
            _paste_clip(frame, img, x, y)

    breath = pose.breath * s
    # Arka saç dönmez (pahalı): başın eğimine göre hafifçe yana kayar
    paste(L["back"], BACK_BOX, dx=-pose.angle * 2.2 * s, dy=breath * 0.6 + pose.bob * s * 0.5)
    paste(L["body"], BODY_BOX, dy=breath)
    paste(head(s, pose.eyes, pose.brows, pose.mouth, pose.angle), HEAD_BOX, dy=breath * 0.7 + pose.bob * s)
    return frame


def _inside(frame, img, x, y) -> bool:
    return x >= 0 and y >= 0 and x + img.width <= frame.width and y + img.height <= frame.height


def _paste_clip(frame, img, x, y):
    x, y = round(x), round(y)
    l, t = max(0, -x), max(0, -y)
    r, b = min(img.width, frame.width - x), min(img.height, frame.height - y)
    if r <= l or b <= t:
        return
    frame.alpha_composite(img.crop((l, t, r, b)), dest=(x + l, y + t))


# ----------------------------------------------------------------- sesten dudak senkronu
def envelope(samples, sr: int, fps: int, n_frames: int, tempo: float = 1.0) -> list[tuple[float, float]]:
    """Kare başına (genlik 0-1, sıfır geçiş oranı 0-1). Genlik 95. yüzdeliğe göre normalleştirilir."""
    import numpy as np

    x = np.asarray(samples, dtype=np.float32)
    hop = sr * tempo / fps
    win = int(sr / fps * 1.5)
    rms, zcr = [], []
    for i in range(n_frames):
        c = int(i * hop)
        seg = x[max(0, c - win // 2): c + win // 2]
        if len(seg) < 8:
            rms.append(0.0)
            zcr.append(0.0)
            continue
        rms.append(float(np.sqrt(np.mean(seg * seg))))
        zcr.append(float(np.mean(np.abs(np.diff(np.sign(seg))) > 0)))
    ref = float(np.percentile([r for r in rms if r > 0] or [1.0], 95)) or 1.0
    return [(min(1.0, r / ref), z) for r, z in zip(rms, zcr)]


def mouth_track(env: list[tuple[float, float]], seed: int = 7) -> list[str]:
    """Genlikten ağız şekli; histerezis + en az 2 kare tutma (titreşimsiz)."""
    rnd = random.Random(seed)
    out, cur, hold = [], "rest", 0
    for a, z in env:
        if a < 0.10:
            want = "rest"
        elif a < 0.30:
            want = "a"
        elif a < 0.55:
            want = "e" if z > 0.25 else "b"
        else:
            want = "o" if (z < 0.06 and rnd.random() < 0.5) else ("e" if z > 0.3 else "wide")
        if want != cur and hold <= 0:
            cur, hold = want, 2
        hold -= 1
        out.append(cur)
    return out


def blink_track(n: int, fps: int, seed: int = 3) -> list[str]:
    rnd = random.Random(seed)
    out = ["open"] * n
    t = rnd.uniform(1.0, 3.0)
    while True:
        i = int(t * fps)
        if i + 3 >= n:
            break
        out[i], out[i + 1], out[i + 2] = "half", "closed", "half"
        if rnd.random() < 0.15 and i + 7 < n:          # ara sıra çift kırpma
            out[i + 4], out[i + 5], out[i + 6] = "half", "closed", "half"
        t += rnd.uniform(2.4, 5.5)
    return out


def brow_track(env: list[tuple[float, float]], fps: int) -> list[str]:
    """Sessizlikten sonra konuşma başlarken (cümle başı) kaşlar ~0.6 sn kalkar."""
    out, quiet, up = [], 0, 0
    for a, _ in env:
        if a < 0.08:
            quiet += 1
        else:
            if quiet >= int(0.35 * fps) and a > 0.3:
                up = int(0.6 * fps)
            quiet = 0
        out.append("up" if up > 0 else "neutral")
        up -= 1
    return out


# ----------------------------------------------------------------- yerleşim
@dataclass(frozen=True)
class Stage:
    """Sunucunun video üstündeki bölgesi ve kip başına ölçek/konum (bölge koordinatı)."""
    region_x: int
    region_y: int
    w: int
    h: int
    modes: dict                    # kip → (ölçek, x, y); "hidden" bölge dışına kayar


DOC_STAGE = Stage(1100, 0, 820, 1080, {
    "big": (1.0, -95, 0),
    "medium": (0.82, 20, 190),
    "hidden": (0.82, 900, 190),
})
SHORTS_STAGE = Stage(0, 1140, 1080, 780, {
    "big": (0.80, 140, -60),
    "medium": (0.68, 200, 30),
    "hidden": (0.68, 200, 820),
})

LAYOUT_MODE = {"host": "big", "title": "medium", "poster": "medium", "mood": "medium", "full": "hidden"}


def _ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def mode_at(timeline: list[tuple[float, float, str]], t: float, stage: Stage, trans: float = 0.6) -> tuple[float, float, float]:
    """Zamana göre (ölçek, x, y): sahne sınırlarında bir önceki kipten yumuşak geçiş."""
    k = 0
    for i, (s, e, _) in enumerate(timeline):
        if s <= t:
            k = i
    cur = stage.modes[LAYOUT_MODE.get(timeline[k][2], "medium")] if timeline else stage.modes["big"]
    if k == 0 or not timeline:
        return cur
    prev = stage.modes[LAYOUT_MODE.get(timeline[k - 1][2], "medium")]
    u = _ease((t - timeline[k][0]) / trans)
    return tuple(a + (b - a) * u for a, b in zip(prev, cur))  # type: ignore[return-value]


def poses(n: int, fps: int, env, timeline, stage: Stage, seed: int = 11):
    mouths = mouth_track(env, seed)
    eyes = blink_track(n, fps, seed)
    brows = brow_track(env, fps)
    rnd = random.Random(seed)
    ph1, ph2 = rnd.uniform(0, 6), rnd.uniform(0, 6)
    energy = 0.0
    for i in range(n):
        t = i / fps
        a = env[i][0] if i < len(env) else 0.0
        energy = energy * 0.9 + a * 0.1                      # yumuşatılmış konuşma enerjisi
        scale, x, y = mode_at(timeline, t, stage)
        angle = 1.6 * math.sin(2 * math.pi * t / 5.3 + ph1) + 0.8 * math.sin(2 * math.pi * t / 2.1 + ph2)
        angle += 2.2 * energy * math.sin(2 * math.pi * t / 0.9)          # konuşurken hafif baş sallama
        yield Pose(scale=scale, x=x, y=y, angle=angle,
                   breath=4.0 * math.sin(2 * math.pi * t / 3.6),
                   bob=3.0 * energy * math.sin(2 * math.pi * t / 0.45),
                   eyes=eyes[i], brows=brows[i], mouth=mouths[i] if i < len(mouths) else "rest")


# ----------------------------------------------------------------- video
def render(out: Path, duration: float, fps: int, stage: Stage, timeline: list[tuple[float, float, str]],
           samples=None, sr: int = 16000, tempo: float = 1.0, seed: int = 11) -> int:
    """Saydam sunucu videosu (VP9 + alfa, WebM). Dönüş: kare sayısı."""
    n = max(1, int(round(duration * fps)))
    env = envelope(samples, sr, fps, n, tempo) if samples is not None else [(0.0, 0.0)] * n
    cmd = ["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
           "-s", f"{stage.w}x{stage.h}", "-r", str(fps), "-i", "-", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
           "-b:v", "0", "-crf", "30", "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1", "-auto-alt-ref", "0",
           str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for pose in poses(n, fps, env, timeline, stage, seed):
            proc.stdin.write(draw(pose, (stage.w, stage.h)).tobytes())  # type: ignore[union-attr]
        proc.stdin.close()  # type: ignore[union-attr]
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
    if proc.wait() != 0:
        raise RuntimeError(f"sunucu videosu üretilemedi: {err[-600:]}")
    return n


def preview_png(path: Path, scale: float = 0.5, **state) -> Path:
    """Tek kare önizleme (panel ve dokümantasyon)."""
    from PIL import Image

    s = quant(scale)
    img = Image.new("RGBA", (round(VIEW_W * s), round(VIEW_H * s)), (0, 0, 0, 0))
    img.alpha_composite(draw(Pose(scale=s, x=0, y=0, **state), img.size))
    img.save(path)
    return path
