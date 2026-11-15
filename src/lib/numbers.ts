// Anlatımdaki sayıların iddialarda geçip geçmediğini kontrol eder (worker/fds_worker/numbers.py ile aynı mantık).
// Panelde senaryo düzenlenirken uyarılar canlı hesaplanır.

const UNITS: Record<string, number> = { sıfır: 0, bir: 1, iki: 2, üç: 3, dört: 4, beş: 5, altı: 6, yedi: 7, sekiz: 8, dokuz: 9 };
const TENS: Record<string, number> = { on: 10, yirmi: 20, otuz: 30, kırk: 40, elli: 50, altmış: 60, yetmiş: 70, seksen: 80, doksan: 90 };
const WORDS: Record<string, number> = { ...UNITS, ...TENS, yüz: 100, bin: 1000, milyon: 1e6, milyar: 1e9, buçuk: 0.5 };
const SUFFIXES = ["deki", "daki", "teki", "taki", "ndeki", "ndaki", "nde", "nda", "da", "de", "ta", "te", "dan", "den", "tan", "ten",
  "ında", "inde", "unda", "ünde", "ın", "in", "un", "ün", "a", "e", "ya", "ye", "yı", "yi", "yu", "yü", "ı", "i", "u", "ü"]
  .sort((a, b) => b.length - a.length);
const SOFT: Record<string, string> = { dörd: "dört" };
const IGNORE_BELOW = 2;

function tokens(text: string): string[] {
  return text.toLocaleLowerCase("tr").replace(/['’]/g, " ").match(/[0-9][0-9.,]*|[a-zçğıöşü]+/g) ?? [];
}

function stripSuffix(tok: string): string | null {
  if (tok in WORDS) return tok;
  for (const [soft, w] of Object.entries(SOFT)) if (tok.startsWith(soft) && SUFFIXES.includes(tok.slice(soft.length))) return w;
  for (const w of Object.keys(WORDS)) if (tok.startsWith(w) && SUFFIXES.includes(tok.slice(w.length))) return w;
  return null;
}

function continues(seq: string[], next: string): boolean {
  const last = seq[seq.length - 1];
  if (["yüz", "bin", "milyon", "milyar", "buçuk"].includes(next)) return true;
  if (last in UNITS) return false;
  if (last in TENS) return next in UNITS;
  return true;
}

function value(seq: string[]): number {
  let total = 0, current = 0;
  for (const w of seq) {
    const v = WORDS[w];
    if (w === "buçuk") current += 0.5;
    else if (v === 100) current = (current || 1) * 100;
    else if (v >= 1000) { total += (current || 1) * v; current = 0; }
    else current += v;
  }
  return total + current;
}

function digits(tok: string): number | null {
  let t = tok.replace(/[.,]+$/, "");
  if (/^\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, "");
  const n = Number(t.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

export function extractNumbers(text: string): Set<number> {
  const toks = tokens(text);
  const out = new Set<number>();
  let i = 0;
  while (i < toks.length) {
    const t = toks[i];
    if (/^\d/.test(t)) {
      const v = digits(t);
      const next = toks[i + 1];
      const mult = next && ["bin", "milyon", "milyar"].includes(next) ? WORDS[next] : null;
      if (v !== null) out.add(mult ? v * mult : v);
      i += mult ? 2 : 1;
      continue;
    }
    if (t in WORDS && t !== "buçuk") {
      const seq = [t];
      let j = i + 1;
      while (j < toks.length) {
        const raw = toks[j];
        const nxt = raw in WORDS ? raw : stripSuffix(raw);
        if (!nxt || !continues(seq, nxt)) break;
        seq.push(nxt);
        j++;
        if (!(raw in WORDS)) break;
      }
      out.add(value(seq));
      i = j;
      continue;
    }
    i++;
  }
  return new Set([...out].filter((v) => v >= IGNORE_BELOW));
}

export function unsupportedNumbers(narration: string, claimsText: string): number[] {
  const allowed = extractNumbers(claimsText);
  return [...extractNumbers(narration)].filter((v) => !allowed.has(v)).sort((a, b) => a - b);
}
