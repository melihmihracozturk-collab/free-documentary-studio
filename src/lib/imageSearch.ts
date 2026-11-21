import "server-only";
import { z } from "zod";
import { classify, type LicenseClass } from "./licenses";

// Panelden anlık görsel araması (Wikimedia Commons + Openverse). İşçideki images.py ile aynı alanları üretir;
// seçilen görsel render öncesi işçi tarafından R2'ye indirilir (download_selected).

export const Candidate = z.object({
  source: z.enum(["commons", "openverse"]),
  title: z.string().max(300),
  page_url: z.string().url(),
  file_url: z.string().url(),
  thumb_url: z.string().url(),
  license_raw: z.string().max(200),
  license_url: z.string().nullable(),
  author: z.string().max(300).nullable(),
  attribution: z.string().max(600).nullable(),
  width: z.number().int().nullable(),
  height: z.number().int().nullable(),
});
export type Candidate = z.infer<typeof Candidate> & { license_class: LicenseClass };

const UA = "FreeDocumentaryStudio/0.3 (open-source documentary research bot)";
const STANDARD_WIDTHS = [3840, 1920, 1280, 960, 500];

const strip = (s?: string | null) =>
  (s ?? "").replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/\s+/g, " ").trim();

/** Commons orijinal adresinden standart genişlikte küçük resim (orijinale toplu erişim kota sınırına takılır). */
export function commonsThumb(url: string, width = 500): string {
  const m = /^https:\/\/upload\.wikimedia\.org\/wikipedia\/commons\/([0-9a-f])\/([0-9a-f]{2})\/([^/?]+\.(?:jpe?g|png|gif|webp))(?:\?.*)?$/i.exec(url);
  return m ? `https://upload.wikimedia.org/wikipedia/commons/thumb/${m[1]}/${m[2]}/${m[3]}/${width}px-${m[3]}` : url;
}

export function commonsDownloadUrl(url: string, width: number | null): string {
  if (url.includes("/commons/thumb/")) return url;
  const w = STANDARD_WIDTHS.find((x) => width && x <= width) ?? 1920;
  return commonsThumb(url, w);
}

async function getJson(url: string): Promise<unknown> {
  const r = await fetch(url, { headers: { "User-Agent": UA }, signal: AbortSignal.timeout(15000), cache: "no-store" });
  if (!r.ok) throw new Error(`${new URL(url).host}: ${r.status}`);
  return r.json();
}

type CommonsPage = { title?: string; imageinfo?: { url?: string; descriptionurl?: string; width?: number; height?: number; mime?: string;
  extmetadata?: Record<string, { value?: string }> }[] };

export async function searchCommons(q: string, limit = 24): Promise<Candidate[]> {
  const p = new URLSearchParams({
    action: "query", format: "json", generator: "search", gsrnamespace: "6", gsrsearch: `${q} filetype:bitmap`,
    gsrlimit: String(limit), prop: "imageinfo", iiprop: "url|extmetadata|size|mime", origin: "*",
  });
  const data = (await getJson(`https://commons.wikimedia.org/w/api.php?${p}`)) as { query?: { pages?: Record<string, CommonsPage & { index?: number }> } };
  const pages = Object.values(data.query?.pages ?? {}).sort((a, b) => (a.index ?? 0) - (b.index ?? 0));
  const out: Candidate[] = [];
  for (const pg of pages) {
    const ii = pg.imageinfo?.[0];
    if (!ii?.url || !String(ii.mime ?? "").startsWith("image/")) continue;
    const md = Object.fromEntries(Object.entries(ii.extmetadata ?? {}).map(([k, v]) => [k, v?.value ?? ""]));
    let lic = [md.LicenseShortName, md.License, md.UsageTerms].filter(Boolean).join(" ");
    if (String(md.Copyrighted).toLowerCase() === "false" && !lic) lic = "public domain";
    const fileTitle = (pg.title ?? "").replace(/^File:/, "").replace(/\.[^.]+$/, "").replace(/_/g, " ");
    const obj = strip(md.ObjectName);
    const title = (obj && !obj.includes("QS:") && obj.length < 140 ? obj : fileTitle).slice(0, 300);
    const author = strip(md.Artist) || null;
    out.push({
      source: "commons", title, page_url: ii.descriptionurl ?? `https://commons.wikimedia.org/wiki/${pg.title}`,
      file_url: commonsDownloadUrl(ii.url, ii.width ?? null), thumb_url: commonsThumb(ii.url),
      license_raw: lic.slice(0, 200), license_url: md.LicenseUrl || null, license_class: classify(lic, md.LicenseUrl),
      author: author?.slice(0, 300) ?? null,
      attribution: `${title} — ${author ?? "bilinmeyen"} — ${md.LicenseShortName || lic} — Wikimedia Commons`.slice(0, 600),
      width: ii.width ?? null, height: ii.height ?? null,
    });
  }
  return out;
}

type OvResult = { title?: string; foreign_landing_url?: string; url?: string; thumbnail?: string; license?: string; license_version?: string;
  license_url?: string; creator?: string; attribution?: string; width?: number; height?: number };

export async function searchOpenverse(q: string, limit = 12): Promise<Candidate[]> {
  // commercial + modification: NC ve ND lisanslar sunucu tarafında elenir
  const p = new URLSearchParams({ q, license_type: "commercial,modification", page_size: String(limit), mature: "false" });
  const data = (await getJson(`https://api.openverse.org/v1/images/?${p}`)) as { results?: OvResult[] };
  return (data.results ?? []).filter((r) => r.url && r.foreign_landing_url).map((r) => {
    const lic = `${r.license ?? ""} ${r.license_version ?? ""}`.trim();
    const cls = r.license === "cc0" || r.license === "pdm" ? classify(r.license) : classify(`cc ${lic}`, r.license_url);
    return {
      source: "openverse" as const, title: (r.title || "Untitled").slice(0, 300), page_url: r.foreign_landing_url!, file_url: r.url!,
      thumb_url: r.thumbnail || r.url!, license_raw: lic.slice(0, 200), license_url: r.license_url ?? null, license_class: cls,
      author: r.creator?.slice(0, 300) ?? null, attribution: r.attribution?.slice(0, 600) ?? null,
      width: r.width ?? null, height: r.height ?? null,
    };
  });
}
