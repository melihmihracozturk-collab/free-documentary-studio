const TR: Record<string, string> = { ç: "c", ğ: "g", ı: "i", İ: "i", ö: "o", ş: "s", ü: "u", â: "a", î: "i", û: "u" };

/** "Pompei'nin Son Günü — Vezüv" → "pompeinin-son-gunu-vezuv" */
export function slugify(input: string, max = 48) {
  const s = input
    .split("")
    .map((c) => TR[c] ?? TR[c.toLowerCase()] ?? c)
    .join("")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/['’`]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return (s.slice(0, max).replace(/-+$/g, "") || "belgesel");
}
