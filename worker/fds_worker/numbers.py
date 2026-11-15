"""Anlatımdaki sayıların iddialarda geçip geçmediğini kontrol eder (Türkçe yazıyla sayılar dahil).

Amaç: LLM'in senaryoya kaynakta olmayan bir sayı (yıl, ölü sayısı, sıcaklık...) eklemesini kodla yakalamak.
"""
from __future__ import annotations

import re

UNITS = {"sıfır": 0, "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9}
TENS = {"on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60, "yetmiş": 70, "seksen": 80, "doksan": 90}
WORDS = {**UNITS, **TENS, "yüz": 100, "bin": 1000, "milyon": 10**6, "milyar": 10**9, "buçuk": 0.5}
# Bir sayı dizisinin SON kelimesine eklenebilen hâl ekleri ("yetmiş dokuzda", "altmış ikide")
SUFFIXES = sorted(["deki", "daki", "teki", "taki", "ndeki", "ndaki", "nde", "nda", "da", "de", "ta", "te", "dan", "den", "tan", "ten", "ında", "inde", "unda", "ünde", "ında", "ın", "in",
                   "un", "ün", "a", "e", "ya", "ye", "yı", "yi", "yu", "yü", "ı", "i", "u", "ü"], key=len, reverse=True)
IGNORE_BELOW = 2  # "bir" çoğu zaman belirsiz tanımlık ("bir şehir")


def _tok(text: str) -> list[str]:
    return re.findall(r"[0-9][0-9.,]*|[a-zçğıöşü]+", text.lower().replace("'", " ").replace("’", " "))


SOFT = {"dörd": "dört"}  # ünsüz yumuşaması: dördü, dördünde


def _strip_suffix(tok: str) -> str | None:
    if tok in WORDS:
        return tok
    for soft, w in SOFT.items():
        if tok.startswith(soft) and tok[len(soft):] in SUFFIXES:
            return w
    for w in WORDS:
        if tok.startswith(w):
            rest = tok[len(w):]
            if rest in SUFFIXES:
                return w
    return None


def _continues(seq: list[str], nxt: str) -> bool:
    """Sonraki kelime aynı sayının devamı mı? ("yirmi dört" evet; "yirmi dört yirmi beş" → iki ayrı sayı)."""
    last = seq[-1]
    if nxt in ("yüz", "bin", "milyon", "milyar", "buçuk"):
        return True
    if last in UNITS:                       # birlikten sonra yalnızca çarpan gelebilir
        return False
    if last in TENS:                        # onluktan sonra yalnızca birlik
        return nxt in UNITS
    return True                             # yüz/bin/milyon'dan sonra her şey


def _value(seq: list[str]) -> float:
    total, current = 0.0, 0.0
    for w in seq:
        v = WORDS[w]
        if w == "buçuk":
            current += 0.5
        elif v == 100:
            current = (current or 1) * 100
        elif v >= 1000:
            total += (current or 1) * v
            current = 0
        else:
            current += v
    return total + current


def _digits(tok: str) -> float | None:
    t = tok.rstrip(".,")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):          # 1.500 → 1500
        t = t.replace(".", "")
    t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def extract(text: str) -> set[float]:
    """Metindeki sayısal değerler (rakamlar + Türkçe yazıyla sayılar)."""
    toks = _tok(text)
    out: set[float] = set()
    i = 0
    while i < len(toks):
        t = toks[i]
        if t[0].isdigit():
            v = _digits(t)
            if v is not None:
                mult = WORDS.get(toks[i + 1]) if i + 1 < len(toks) and toks[i + 1] in ("bin", "milyon", "milyar") else None
                out.add(v * mult if mult else v)
            i += 2 if mult else 1
            continue
        if t in WORDS and t != "buçuk":
            seq = [t]
            j = i + 1
            while j < len(toks):
                nxt = toks[j] if toks[j] in WORDS else _strip_suffix(toks[j])
                if not nxt or not _continues(seq, nxt):
                    break
                seq.append(nxt)
                j += 1
                if toks[j - 1] not in WORDS:      # ekli kelime diziyi bitirir
                    break
            out.add(_value(seq))
            i = j
            continue
        i += 1
    return {v for v in out if v >= IGNORE_BELOW}


def unsupported(narration: str, claims_text: str) -> set[float]:
    """Anlatımda olup iddialarda hiç geçmeyen sayılar."""
    allowed = extract(claims_text)
    return {v for v in extract(narration) if v not in allowed}


def fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)
