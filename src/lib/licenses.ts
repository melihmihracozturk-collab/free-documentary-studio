// Görsel lisans sınıflandırması — worker/fds_worker/licenses.py ile AYNI kurallar (iki tarafın testleri aynı örnekleri kullanır).
// Sınıflar: pd, cc0, by, by-sa, nc, nd, unknown; "own" = kullanıcının kendi yüklediği (hak sahibi beyanı).
export type LicenseClass = "pd" | "cc0" | "by" | "by-sa" | "nc" | "nd" | "unknown" | "own" | "restricted";

/** Yayında kullanılmaması gereken sınıflar (taslak modunda önerilir, kırmızı işaretlenir). */
export const RESTRICTED = new Set(["nc", "nd", "unknown", "restricted"]);
export const isRestricted = (cls: string | null | undefined) => RESTRICTED.has(cls ?? "unknown");

export function classify(...texts: (string | null | undefined)[]): LicenseClass {
  let t = texts.filter(Boolean).join(" ").toLowerCase().replace(/[_\s]+/g, " ");
  if (!t.trim()) return "unknown";
  t = ` ${t} `;
  const nd = /\bnd\b|no ?deriv|noderiv|-nd\b|\/nd\/|by-nc-nd|by-nd/.test(t);
  const nc = /\bnc\b|non ?commercial|noncommercial|-nc\b|\/by-nc|by-nc/.test(t);
  if (nd) return "nd";
  if (nc) return "nc";
  if (/\bcc0\b|cc-zero|publicdomain\/zero|zero\/1\.0|cc zero/.test(t)) return "cc0";
  if (/public ?domain|\bpd\b|pd-|publicdomain\/mark|\bpdm\b|no known copyright|no restrictions|ispublicdomain/.test(t)) return "pd";
  if (/by-sa|by sa|sharealike|share ?alike|\/by-sa\//.test(t)) return "by-sa";
  if (/cc[- ]?by\b|cc by \d|creativecommons\.org\/licenses\/by\/|\bby \d\.\d|attribution/.test(t)) return "by";
  return "unknown";
}

export function allowed(cls: LicenseClass, allowNc = false, allowSa = true, allowRestricted = false): boolean {
  if (allowRestricted) return true;                                  // kullanıcının açtığı taslak modu
  if (cls === "pd" || cls === "cc0" || cls === "by" || cls === "own") return true;
  if (cls === "by-sa") return allowSa;
  if (cls === "nc") return allowNc;
  return false;
}
