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

PRESENTER_VERSION = "p2"      # p2: ninja kostümü
VIEW_W, VIEW_H = 1000, 1300
PIVOT = (500, 640)                 # boyun üstü: baş bu noktanın çevresinde döner
HEAD_BOX = (250, 110, 760, 760)    # baş katmanlarının kırpma kutusu (dönüş payı dahil)
BACK_BOX = (180, 110, 820, 1300)
BODY_BOX = (230, 580, 770, 1300)

C = {
    "skin": "#F8E1D4", "skin_sh": "#E7B9A6", "blush": "#E87A86",
    "hair": "#262033", "hair_dark": "#120F1A", "hair_hi": "#9C2F45",
    "iris": "#FF4A3D", "iris_dark": "#7A0E1C", "lash": "#140E1C", "white": "#FFF8F4",
    "lip": "#B8424F", "mouth": "#5E1022", "tongue": "#D9707C", "teeth": "#FFFFFF",
    "suit": "#1E1C29", "suit_sh": "#13121B", "suit_hi": "#34314A", "mesh": "#4A4560",
    "scarf": "#C8202F", "scarf_sh": "#8E1220", "armor": "#3A3F4E", "armor_hi": "#6B7388",
    "metal": "#B9C0CC", "metal_sh": "#7E8696", "band": "#3A3650", "paint": "#D3202F",
    "wrap": "#C8202F", "blade": "#2A2833",
}

EYES = ("open", "half", "closed")
BROWS = ("neutral", "up")
MOUTHS = ("rest", "a", "b", "wide", "o", "e")


def _svg(body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW_W} {VIEW_H}" width="{VIEW_W}" height="{VIEW_H}">'
            f'<defs>'
            f'<radialGradient id="iris" cx="50%" cy="65%" r="60%"><stop offset="0" stop-color="{C["iris"]}"/>'
            f'<stop offset="1" stop-color="{C["iris_dark"]}"/></radialGradient>'
            f'<linearGradient id="hairg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C["hair"]}"/>'
            f'<stop offset="1" stop-color="{C["hair_dark"]}"/></linearGradient>'
            f'<linearGradient id="plate" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C["metal"]}"/>'
            f'<stop offset="1" stop-color="{C["metal_sh"]}"/></linearGradient>'
            f'</defs>{body}</svg>')


# ----------------------------------------------------------------- katmanlar (SVG)
def layer_back_hair() -> str:
    """Arka katman: başın arkası, yüksek at kuyruğu, alın bandının uçları ve sırttaki kılıcın kabzası."""
    c = C
    return _svg(f"""
<g transform="rotate(32 690 740)">
  <rect x="677" y="560" width="26" height="160" rx="6" fill="{c['wrap']}"/>
  <path fill="none" stroke="{c['scarf_sh']}" stroke-width="5" d="M677 580 L703 600 M677 605 L703 625 M677 630 L703 650 M677 655 L703 675 M677 680 L703 700 M703 580 L677 600 M703 605 L677 625 M703 630 L677 650 M703 655 L677 675 M703 680 L677 700"/>
  <rect x="671" y="548" width="38" height="16" rx="6" fill="{c['metal_sh']}"/>
  <ellipse cx="690" cy="724" rx="46" ry="12" fill="{c['metal']}" stroke="{c['metal_sh']}" stroke-width="4"/>
  <rect x="674" y="734" width="32" height="300" fill="{c['blade']}"/>
</g>
<path fill="url(#hairg)" d="M320 420 C300 260 390 170 500 170 C610 170 700 260 680 420 C690 520 660 600 600 640 L400 640 C340 600 310 520 320 420 Z"/>
<path fill="url(#hairg)" d="M470 190 C520 150 600 160 640 200 C700 260 700 360 670 460 C640 580 600 700 580 830
  C570 900 560 960 520 1030 C530 950 520 900 500 860 C470 760 470 640 500 520 C520 420 520 300 470 190 Z"/>
<path fill="none" stroke="{c['hair_hi']}" stroke-width="8" stroke-linecap="round" opacity="0.7" d="M630 260 C660 360 640 520 600 700"/>
<path fill="{c['band']}" d="M330 330 C300 360 260 400 222 470 C250 460 270 452 290 450 C300 420 320 380 345 350 Z"/>
<path fill="{c['band']}" d="M340 345 C320 400 300 470 282 540 C305 520 322 505 338 500 C340 450 350 400 362 360 Z"/>""")


def layer_body() -> str:
    c = C
    return _svg(f"""
<path fill="{c['skin_sh']}" d="M454 590 L546 590 L550 735 C530 750 470 750 450 735 Z"/>
<path fill="{c['skin_sh']}" opacity="0.9" d="M454 600 C470 640 530 640 546 600 L546 650 C525 670 475 670 454 650 Z"/>
<path fill="{c['suit']}" d="M250 1300 L258 900 C262 820 300 768 365 742 C410 726 440 728 462 740 L500 860 L538 740
  C560 728 590 726 635 742 C700 768 738 820 742 900 L750 1300 Z"/>
<path fill="{c['mesh']}" d="M462 740 L500 860 L538 740 C520 760 480 760 462 740 Z"/>
<path fill="none" stroke="{c['suit_sh']}" stroke-width="2" opacity="0.9"
  d="M468 752 L520 800 M476 770 L512 804 M486 792 L506 812 M532 752 L480 800 M524 770 L488 804 M514 792 L494 812"/>
<path fill="{c['suit_hi']}" d="M462 740 L520 905 L512 912 L452 748 Z"/>
<path fill="{c['suit_hi']}" d="M538 740 L486 870 L494 878 L548 748 Z" opacity="0.8"/>
<path fill="none" stroke="{c['suit_sh']}" stroke-width="6" stroke-linecap="round" d="M330 900 C335 1000 330 1120 325 1300"/>
<path fill="none" stroke="{c['suit_sh']}" stroke-width="6" stroke-linecap="round" d="M670 900 C665 1000 670 1120 675 1300"/>
<path fill="{c['scarf']}" d="M270 1170 L730 1150 L736 1235 L264 1250 Z"/>
<path fill="{c['scarf_sh']}" d="M270 1170 L730 1150 L731 1168 L270 1188 Z"/>
<path fill="{c['scarf']}" d="M560 1200 C590 1230 600 1270 596 1300 L560 1300 C560 1270 552 1240 536 1215 Z"/>
<path fill="{c['armor']}" d="M610 748 C670 744 728 780 744 850 C722 862 690 864 660 856 C650 812 632 780 600 764 Z"/>
<path fill="{c['armor_hi']}" d="M622 760 C670 760 712 790 726 838 C712 842 700 842 688 840 C676 806 656 780 618 770 Z" opacity="0.7"/>
<path fill="none" stroke="{c['suit_sh']}" stroke-width="5" d="M640 790 C680 790 712 816 724 846"/>
<path fill="{c['scarf']}" d="M405 735 C440 700 560 700 595 735 C602 760 596 785 585 800 C540 820 460 820 415 800 C404 785 398 760 405 735 Z"/>
<path fill="{c['scarf_sh']}" d="M415 790 C460 808 540 808 585 790 L585 800 C540 820 460 820 415 800 Z"/>
<path fill="none" stroke="{c['scarf_sh']}" stroke-width="5" stroke-linecap="round" d="M425 760 C470 776 530 776 575 760"/>
<path fill="{c['scarf']}" d="M420 790 C390 860 360 930 300 1010 C340 1000 370 990 395 970 C392 1000 380 1030 360 1060
  C410 1030 440 980 455 930 C465 880 462 840 458 810 Z"/>
<path fill="{c['scarf_sh']}" d="M440 812 C430 880 410 940 380 990 C400 970 420 940 434 900 C446 860 450 830 448 812 Z" opacity="0.8"/>""")


def layer_face() -> str:
    c = C
    return _svg(f"""
<ellipse cx="364" cy="468" rx="20" ry="32" fill="{c['skin_sh']}"/>
<ellipse cx="636" cy="468" rx="20" ry="32" fill="{c['skin_sh']}"/>
<path fill="{c['skin']}" d="M364 380 C360 500 412 584 472 626 C490 640 510 640 528 626 C588 584 640 500 636 380
  C634 270 366 270 364 380 Z"/>
<ellipse cx="420" cy="534" rx="26" ry="10" fill="{c['blush']}" opacity="0.22"/>
<ellipse cx="580" cy="534" rx="26" ry="10" fill="{c['blush']}" opacity="0.22"/>
<path fill="{c['paint']}" d="M396 512 L446 506 L442 514 L398 518 Z"/>
<path fill="{c['paint']}" d="M604 512 L554 506 L558 514 L602 518 Z"/>
<path fill="none" stroke="{c['skin_sh']}" stroke-width="5" stroke-linecap="round" d="M500 506 L494 526 L503 528"/>""")


def _eye(cx: float, cy: float, state: str, flip: bool) -> str:
    """Badem biçimli, dış köşesi yukarı kalkık, kalın eyeliner'lı, dikey göz bebekli yırtıcı göz."""
    c = C
    s = -1 if flip else 1
    i, o = cx - 40 * s, cx + 42 * s               # iç ve dış köşe
    if state == "closed":
        return (f'<path fill="none" stroke="{c["lash"]}" stroke-width="9" stroke-linecap="round" '
                f'd="M{i} {cy + 4} C{cx - 10 * s} {cy + 16} {cx + 18 * s} {cy + 10} {o} {cy - 6}"/>'
                f'<path fill="{c["lash"]}" d="M{o} {cy - 6} L{o + 22 * s} {cy - 18} L{o + 4 * s} {cy + 2} Z"/>')
    shape = (f'M{i} {cy + 6} C{cx - 20 * s} {cy - 26} {cx + 18 * s} {cy - 34} {o} {cy - 12}'
             f' C{cx + 26 * s} {cy + 20} {cx - 16 * s} {cy + 26} {i} {cy + 6} Z')
    white = f'<path fill="{c["white"]}" d="{shape}"/>'
    iris = (f'<ellipse cx="{cx + 2 * s}" cy="{cy - 2}" rx="22" ry="27" fill="url(#iris)"/>'
            f'<ellipse cx="{cx + 2 * s}" cy="{cy - 2}" rx="4.5" ry="19" fill="{c["lash"]}"/>'
            f'<circle cx="{cx - 8 * s}" cy="{cy - 12}" r="6" fill="{c["white"]}"/>'
            f'<circle cx="{cx + 10 * s}" cy="{cy + 10}" r="3" fill="{c["white"]}" opacity="0.85"/>')
    clip = f'<clipPath id="e{int(cx)}"><path d="{shape}"/></clipPath>'
    lid = ""
    if state == "half":
        lid = f'<rect x="{cx - 50}" y="{cy - 45}" width="100" height="44" fill="{c["skin"]}"/>'
    if state == "half":
        top = (f'M{i - 2 * s} {cy + 2} C{cx - 10 * s} {cy - 6} {cx + 20 * s} {cy - 8} {o} {cy - 8}'
               f' L{o + 26 * s} {cy - 22} L{o + 6 * s} {cy - 2} C{cx + 18 * s} {cy - 2} {cx - 10 * s} {cy + 2} {i - 2 * s} {cy + 8} Z')
    else:
        top = (f'M{i - 4 * s} {cy + 8} C{cx - 22 * s} {cy - 30} {cx + 18 * s} {cy - 40} {o} {cy - 14}'
               f' L{o + 28 * s} {cy - 30} L{o + 8 * s} {cy - 6} C{cx + 16 * s} {cy - 28} {cx - 18 * s} {cy - 20} {i + 2 * s} {cy + 6} Z')
    lash = f'<path fill="{c["lash"]}" d="{top}"/>'
    lower = (f'<path fill="none" stroke="{c["lash"]}" stroke-width="3" stroke-linecap="round" opacity="0.55" '
             f'd="M{cx + 4 * s} {cy + 21} C{cx + 18 * s} {cy + 18} {cx + 30 * s} {cy + 10} {o} {cy - 8}"/>')
    return f'<defs>{clip}</defs><g clip-path="url(#e{int(cx)})">{white}{iris}{lid}</g>{lash}{lower}'


def layer_eyes(state: str) -> str:
    return _svg(_eye(438, 462, state, True) + _eye(562, 462, state, False))


def layer_brows(state: str) -> str:
    """Çatık, keskin kaşlar: iç uçlar aşağıda (kararlı / yırtıcı ifade). 'up' = kaşlar kalkar ama keskin kalır."""
    dy = -12 if state == "up" else 0
    tilt = 6 if state == "up" else 14
    c = C
    return _svg(f"""
<path fill="{c['hair_dark']}" d="M398 {396 + dy} C420 {388 + dy} 450 {394 + dy} 478 {396 + dy + tilt} L476 {404 + dy + tilt} C450 {402 + dy} 424 {398 + dy} 400 {403 + dy} Z"/>
<path fill="{c['hair_dark']}" d="M602 {396 + dy} C580 {388 + dy} 550 {394 + dy} 522 {396 + dy + tilt} L524 {404 + dy + tilt} C550 {402 + dy} 576 {398 + dy} 600 {403 + dy} Z"/>""")


def _fang(x: float, y: float) -> str:
    return f'<path fill="{C["teeth"]}" d="M{x - 6} {y} L{x + 6} {y} L{x} {y + 13} Z"/>'


def layer_mouth(shape: str) -> str:
    c = C
    x, y = 500, 572
    if shape == "rest":                                        # alaycı yarım gülümseme + küçük köpek dişi
        body = (f'<path fill="none" stroke="{c["mouth"]}" stroke-width="6" stroke-linecap="round" '
                f'd="M{x - 20} {y + 2} C{x - 6} {y + 6} {x + 10} {y + 4} {x + 24} {y - 8}"/>'
                + _fang(x + 12, y + 2))
    elif shape == "a":
        body = (f'<path fill="{c["mouth"]}" d="M{x - 20} {y - 4} C{x - 10} {y - 8} {x + 10} {y - 10} {x + 22} {y - 8}'
                f' C{x + 14} {y + 12} {x - 14} {y + 12} {x - 20} {y - 4} Z"/>' + _fang(x + 12, y - 7))
    elif shape == "b":
        body = (f'<path fill="{c["mouth"]}" d="M{x - 26} {y - 6} C{x - 12} {y - 10} {x + 12} {y - 12} {x + 28} {y - 10}'
                f' C{x + 20} {y + 22} {x - 20} {y + 22} {x - 26} {y - 6} Z"/>'
                f'<path fill="{c["tongue"]}" d="M{x - 13} {y + 12} C{x - 6} {y + 4} {x + 6} {y + 4} {x + 13} {y + 12}'
                f' C{x + 6} {y + 17} {x - 6} {y + 17} {x - 13} {y + 12} Z"/>' + _fang(x + 15, y - 9) + _fang(x - 14, y - 7))
    elif shape == "wide":
        body = (f'<path fill="{c["mouth"]}" d="M{x - 30} {y - 8} C{x - 14} {y - 12} {x + 14} {y - 14} {x + 32} {y - 12}'
                f' C{x + 26} {y + 34} {x - 26} {y + 34} {x - 30} {y - 8} Z"/>'
                f'<path fill="{c["teeth"]}" d="M{x - 24} {y - 7} C{x - 10} {y - 10} {x + 10} {y - 11} {x + 26} {y - 9}'
                f' L{x + 22} {y} C{x + 8} {y + 2} {x - 8} {y + 2} {x - 22} {y} Z"/>'
                f'<path fill="{c["tongue"]}" d="M{x - 16} {y + 22} C{x - 8} {y + 12} {x + 8} {y + 12} {x + 16} {y + 22}'
                f' C{x + 8} {y + 28} {x - 8} {y + 28} {x - 16} {y + 22} Z"/>' + _fang(x + 18, y - 2) + _fang(x - 17, y - 1))
    elif shape == "o":
        body = (f'<ellipse cx="{x}" cy="{y + 6}" rx="14" ry="18" fill="{c["mouth"]}"/>'
                f'<ellipse cx="{x}" cy="{y + 15}" rx="8" ry="6" fill="{c["tongue"]}"/>')
    else:  # "e": geniş, dişler ve köpek dişleri görünür (sırıtma)
        body = (f'<path fill="{c["mouth"]}" d="M{x - 30} {y - 4} C{x - 14} {y - 8} {x + 14} {y - 10} {x + 32} {y - 8}'
                f' C{x + 24} {y + 14} {x - 24} {y + 14} {x - 30} {y - 4} Z"/>'
                f'<path fill="{c["teeth"]}" d="M{x - 25} {y - 4} C{x - 10} {y - 7} {x + 10} {y - 8} {x + 27} {y - 6}'
                f' L{x + 22} {y + 3} C{x + 8} {y + 5} {x - 8} {y + 5} {x - 22} {y + 3} Z"/>' + _fang(x + 19, y + 1) + _fang(x - 18, y + 2))
    return _svg(body)


def layer_front_hair() -> str:
    """Keskin, sivri perçemler; alında pençe izi amblemli metal plakalı bant (hitai-ate benzeri, özgün amblem)."""
    c = C
    return _svg(f"""
<path fill="url(#hairg)" d="M350 480 C326 330 396 205 500 200 C604 205 674 330 650 480
  L636 410 C632 380 622 360 610 350 L612 430 C596 392 578 366 560 352 L566 418 C548 380 528 356 506 346
  L500 426 C486 380 464 356 446 348 L452 420 C432 384 414 364 396 354 C386 392 374 440 366 490 Z"/>
<path fill="url(#hairg)" d="M366 420 C334 510 336 600 352 690 C362 650 372 618 386 590 C380 540 378 480 386 430 Z"/>
<path fill="url(#hairg)" d="M634 420 C666 510 664 600 648 690 C638 650 628 618 614 590 C620 540 622 480 614 430 Z"/>
<path fill="url(#hairg)" d="M540 350 C520 400 488 440 452 468 C480 436 498 400 508 356 Z"/>
<path fill="none" stroke="{c['hair_hi']}" stroke-width="6" stroke-linecap="round" opacity="0.75" d="M420 250 C460 228 540 228 580 250"/>
<path fill="{c['band']}" d="M352 320 C420 286 580 286 648 320 L652 362 C580 330 420 330 348 362 Z"/>
<rect x="436" y="300" width="128" height="52" rx="8" fill="url(#plate)" stroke="{c['metal_sh']}" stroke-width="3"/>
<circle cx="446" cy="312" r="3.5" fill="{c['metal_sh']}"/><circle cx="554" cy="312" r="3.5" fill="{c['metal_sh']}"/>
<circle cx="446" cy="340" r="3.5" fill="{c['metal_sh']}"/><circle cx="554" cy="340" r="3.5" fill="{c['metal_sh']}"/>
<path fill="none" stroke="{c['paint']}" stroke-width="6" stroke-linecap="round" d="M474 342 L494 310 M494 344 L514 310 M514 344 L532 312"/>""")


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
