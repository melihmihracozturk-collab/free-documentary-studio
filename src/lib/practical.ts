// Fiyat, saat, ulaşım, kural gibi değişebilen bilgiler (worker/fds_worker/script.py PRACTICAL_RE ile aynı kural).
// Model bu bilgileri her zaman "practical" kategorisine koymadığı için iddia METNİNDEN tanınır.
const PRACTICAL_RE =
  /(€|\beuro|\bavro|\bbilet|ücret|fiyat|rezerv|açılış saat|kapanış saat|\b\d{1,2}[:.]\d{2}\b|saatleri arasında|\btren|otobüs|vapur|vaporetto|otopark|konaklama vergisi|\bceza|yasak|emanet|\bkartı?\b)/i;

export function isPractical(text: string): boolean {
  return PRACTICAL_RE.test(text);
}

/** getClaimsText çıktısındaki ("C12 [weak] (2025) metin") pratik bilgi iddialarının kimlikleri. */
export function practicalRefs(claims: string): Set<string> {
  const out = new Set<string>();
  for (const line of claims.split("\n")) {
    const m = line.match(/^(C\d+)\s+\[[^\]]*\](?:\s+\([^)]*\))?\s+(.*)$/);
    if (m && isPractical(m[2])) out.add(m[1]);
  }
  return out;
}

export function needsCheck(scene: { needs_check?: boolean; claim_refs: string[] }, refs: Set<string>): boolean {
  return Boolean(scene.needs_check) || scene.claim_refs.some((r) => refs.has(r));
}
