"use client";

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { ExternalLink, Search, Upload } from "lucide-react";
import { addSceneImage } from "@/app/actions";
import type { Candidate } from "@/lib/imageSearch";
import { btnGhost, btnPrimary, input } from "./ui";

const LIC: Record<string, string> = {
  pd: "Kamu malı", cc0: "CC0", by: "CC BY · atıf", "by-sa": "CC BY-SA · atıf", nc: "NC · ticari değil",
};

/** Bir sahne için: arşivlerde (Commons + Openverse) arama ve kullanıcının kendi görselini yükleme. */
export function SceneImageTools({ slug, sceneId, suggestion, vertical }: {
  slug: string; sceneId: string; suggestion: string; vertical: boolean;
}) {
  const [open, setOpen] = useState<"search" | "upload" | null>(null);
  const [q, setQ] = useState(suggestion);
  const [results, setResults] = useState<Candidate[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok?: string; error?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [rights, setRights] = useState(false);
  const [pending, start] = useTransition();
  const file = useRef<HTMLInputElement>(null);
  const router = useRouter();

  async function search(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null); setResults(null);
    try {
      const r = await fetch(`/api/projects/${slug}/images/search?q=${encodeURIComponent(q)}`);
      const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? "Arama başarısız");
      setResults(j.results);
      setNote(`${j.results.length} uygun görsel${j.rejected ? ` · ${j.rejected} lisansı uygun olmadığı için gizlendi` : ""}` +
              (j.errors?.length ? ` · ulaşılamayan arşiv: ${j.errors.join(", ")} (yoğunluk olabilir, biraz sonra tekrar deneyin)` : ""));
    } catch (err) {
      setMsg({ error: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const choose = (c: Candidate) => start(async () => {
    const r = await addSceneImage(slug, sceneId, c);
    setMsg(r ?? null);
    if (r?.ok) { setOpen(null); router.refresh(); }
  });

  async function upload() {
    const f = file.current?.files?.[0];
    if (!f) return setMsg({ error: "Bir görsel dosyası seçin" });
    if (!rights) return setMsg({ error: "Kullanım hakkı onayını işaretleyin" });
    setBusy(true); setMsg(null);
    try {
      const meta = { sceneId, filename: f.name, size: f.size, type: f.type };
      const pr = await fetch(`/api/projects/${slug}/images/presign`, { method: "POST", body: JSON.stringify(meta) });
      const p = await pr.json();
      if (!pr.ok) throw new Error(p.error ?? "Yükleme başlatılamadı");
      const put = await fetch(p.url, { method: "PUT", body: f, headers: { "Content-Type": p.contentType } });
      if (!put.ok) throw new Error(`Depoya yüklenemedi (${put.status})`);
      const cr = await fetch(`/api/projects/${slug}/images/complete`, { method: "POST", body: JSON.stringify({ ...meta, key: p.key, rights: true }) });
      const c = await cr.json();
      if (!cr.ok) throw new Error(c.error ?? "Yükleme tamamlanamadı");
      setMsg({ ok: "Görsel yüklendi ve sahneye eklendi" });
      setOpen(null);
      router.refresh();
    } catch (err) {
      setMsg({ error: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3">
      <div className="flex flex-wrap gap-2">
        <button className={btnGhost} onClick={() => setOpen(open === "search" ? null : "search")} aria-expanded={open === "search"}>
          <Search size={14} className="mr-1 inline" /> Görsel ara
        </button>
        <button className={btnGhost} onClick={() => setOpen(open === "upload" ? null : "upload")} aria-expanded={open === "upload"}>
          <Upload size={14} className="mr-1 inline" /> Kendi görselimi yükle
        </button>
      </div>
      {msg?.error && <p role="alert" className="mt-2 text-xs text-rose-300">{msg.error}</p>}
      {msg?.ok && <p role="status" className="mt-2 text-xs text-emerald-300">{msg.ok}</p>}

      {open === "search" && (
        <div className="mt-2 rounded-md border border-white/10 bg-zinc-950/60 p-3">
          <form onSubmit={search} className="flex gap-2">
            <input aria-label="Görsel arama" className={input} value={q} onChange={(e) => setQ(e.target.value)}
                   placeholder="ör. Santiago Bernabéu, Arda Güler, Kolezyum" />
            <button className={btnPrimary} disabled={busy || q.trim().length < 2}>{busy ? "Aranıyor…" : "Ara"}</button>
          </form>
          <p className="mt-1 text-[11px] text-zinc-500">
            Wikimedia Commons ve Openverse; yalnızca kamu malı, CC0, CC BY ve CC BY-SA görseller gösterilir. İngilizce arama genelde daha çok sonuç verir.
          </p>
          {note && <p className="mt-2 text-xs text-zinc-400">{note}</p>}
          {results && (
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
              {results.map((c) => (
                <figure key={c.file_url} className="overflow-hidden rounded-md bg-zinc-900 ring-1 ring-white/10">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={c.thumb_url} alt={c.title} loading="lazy" className={`w-full object-cover ${vertical ? "aspect-[3/4]" : "aspect-video"}`} />
                  <figcaption className="space-y-1 p-1.5 text-[11px]">
                    <p className="line-clamp-2 text-zinc-200" title={c.title}>{c.title}</p>
                    <p className="text-zinc-500">
                      {LIC[c.license_class] ?? c.license_class} · {c.width && c.height ? `${c.width}×${c.height}` : "boyut ?"}
                      {c.width && c.width < 1280 ? " · düşük çöz." : ""}
                    </p>
                    <div className="flex items-center justify-between gap-1">
                      <button className="rounded bg-amber-500/90 px-2 py-0.5 text-black hover:bg-amber-400 disabled:opacity-50"
                              disabled={pending} onClick={() => choose(c)}>Bu sahneye koy</button>
                      <a href={c.page_url} target="_blank" rel="noreferrer" className="text-zinc-400 hover:text-amber-300" aria-label="Kaynağı aç">
                        <ExternalLink size={12} />
                      </a>
                    </div>
                  </figcaption>
                </figure>
              ))}
            </div>
          )}
        </div>
      )}

      {open === "upload" && (
        <div className="mt-2 space-y-2 rounded-md border border-white/10 bg-zinc-950/60 p-3 text-sm">
          <input ref={file} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Görsel dosyası"
                 className="block w-full text-xs text-zinc-300 file:mr-3 file:rounded file:border-0 file:bg-zinc-800 file:px-3 file:py-1.5 file:text-zinc-200" />
          <label className="flex items-start gap-2 text-xs text-zinc-300">
            <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} className="mt-0.5 accent-amber-500" />
            Bu görseli videoda kullanma hakkım var (kendi çektiğim fotoğraf ya da kullanım izni aldığım görsel).
            Başkasına ait telifli görselleri (maç fotoğrafları, haber sitesi görselleri, TV görüntüleri) yüklemeyin.
          </label>
          <p className="text-[11px] text-zinc-500">JPG, PNG veya WEBP · en fazla 25 MB · {vertical ? "Shorts için dikey görsel önerilir" : "yatay ve en az 1920 px genişlik önerilir"}.</p>
          <button className={btnPrimary} disabled={busy || !rights} onClick={upload}>{busy ? "Yükleniyor…" : "Yükle ve sahneye koy"}</button>
        </div>
      )}
    </div>
  );
}
