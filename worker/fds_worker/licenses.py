"""Görsel lisans sınıflandırması ve kullanım politikası.

Sınıflar: pd (kamu malı), cc0, by, by-sa, nc (ticari olmayan), nd (türev yasak), unknown.
Politika:
  - pd, cc0, by          → kabul
  - by-sa                → ayara bağlı (varsayılan kabul; atıf + aynı lisansla paylaşım koşulu kayda geçer)
  - nc                   → ayara bağlı (varsayılan RET; kanal para kazanırsa sorun olur)
  - nd                   → her zaman RET (Ken Burns/kırpma/renk düzenleme türev eser sayılabilir)
  - unknown              → her zaman RET
NC ve ND birlikte geçiyorsa (ör. CC BY-NC-ND) en kısıtlayıcı olan (nd) esas alınır.
"""
from __future__ import annotations

import re

ORDER = ["pd", "cc0", "by", "by-sa", "nc", "nd", "unknown"]


def classify(*texts: str | None) -> str:
    """Lisans adı/URL/kullanım şartı metinlerinden lisans sınıfı çıkarır."""
    t = " ".join(x for x in texts if x).lower()
    t = re.sub(r"[_\s]+", " ", t)
    if not t.strip():
        return "unknown"
    nd = bool(re.search(r"\bnd\b|no ?deriv|noderiv|-nd\b|/nd/|by-nc-nd|by-nd", t))
    nc = bool(re.search(r"\bnc\b|non ?commercial|noncommercial|-nc\b|/by-nc|by-nc", t))
    if nd:
        return "nd"
    if nc:
        return "nc"
    if re.search(r"\bcc0\b|cc-zero|publicdomain/zero|zero/1\.0|cc zero", t):
        return "cc0"
    if re.search(r"public ?domain|\bpd\b|pd-|publicdomain/mark|\bpdm\b|no known copyright|no restrictions|ispublicdomain", t):
        return "pd"
    if re.search(r"by-sa|by sa|sharealike|share ?alike|/by-sa/", t):
        return "by-sa"
    if re.search(r"cc[- ]?by\b|cc by \d|creativecommons\.org/licenses/by/|\bby \d\.\d|attribution", t):
        return "by"
    return "unknown"


def allowed(cls: str, allow_nc: bool = False, allow_sa: bool = True) -> tuple[bool, str]:
    """(kullanılabilir mi, gerekçe)"""
    if cls == "promo":
        return True, "telifli tanıtım görseli (afiş): yalnızca inceleme/eleştiri amaçlı, kaynak belirtilir"
    if cls == "own":
        return True, "kullanıcının kendi yüklemesi (kullanım hakkı beyanı)"
    if cls in ("pd", "cc0", "by"):
        return True, "serbest kullanım" if cls in ("pd", "cc0") else "atıf zorunlu"
    if cls == "by-sa":
        return (allow_sa, "atıf + aynı lisansla paylaşım" if allow_sa else "CC BY-SA ayarlardan kapalı")
    if cls == "nc":
        return (allow_nc, "ticari olmayan kullanım (kanal para kazanırsa sorun)" if allow_nc else "NC lisans: ticari kullanım yasak")
    if cls == "nd":
        return False, "ND lisans: değiştirmek (kırpma/hareket) yasak"
    return False, "lisans bilinmiyor"


def needs_attribution(cls: str) -> bool:
    return cls in ("by", "by-sa", "nc", "promo")
