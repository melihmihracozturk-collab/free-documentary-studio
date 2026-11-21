"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Check, ExternalLink, ImageOff } from "lucide-react";
import { approveVisuals, selectAsset, unapproveVisuals } from "@/app/actions";
import type { VisualAsset, VisualScene } from "@/lib/queries";
import { btnGhost, btnPrimary } from "./ui";
import { SceneImageTools } from "./SceneImageTools";

const LIC: Record<string, { label: string; cls: string }> = {
  pd: { label: "Kamu malı", cls: "bg-emerald-500/15 text-emerald-300" },
  cc0: { label: "CC0", cls: "bg-emerald-500/15 text-emerald-300" },
  by: { label: "CC BY · atıf", cls: "bg-sky-500/15 text-sky-300" },
  "by-sa": { label: "CC BY-SA · atıf", cls: "bg-amber-500/15 text-amber-300" },
  nc: { label: "NC · ticari değil", cls: "bg-rose-500/15 text-rose-300" },
  own: { label: "Sizin yüklemeniz", cls: "bg-violet-500/15 text-violet-300" },
};
const SRC: Record<string, string> = { met: "Met Museum", commons: "Wikimedia Commons", openverse: "Openverse", smithsonian: "Smithsonian", upload: "Kullanıcı yüklemesi" };

/** Önizleme: Commons yalnızca standart genişlikleri verir (500, 960, 1280, 1920, 3840…) ve orijinal dosyaya doğrudan
 *  erişimi kota sınırına takar; her iki adres biçiminden de 500px küçük resim üretilir. */
function small(url: string | null) {
  if (!url) return "";
  const orig = /^https:\/\/upload\.wikimedia\.org\/wikipedia\/commons\/([0-9a-f])\/([0-9a-f]{2})\/([^/?]+\.(?:jpe?g|png|gif|webp))(?:\?.*)?$/i.exec(url);
  if (orig) return `https://upload.wikimedia.org/wikipedia/commons/thumb/${orig[1]}/${orig[2]}/${orig[3]}/500px-${orig[3]}`;
  return url.replace(/\/(\d{3,4})px-/, "/500px-");
}

function fmt(sec: string | null) {
  if (sec == null) return "";
  const s = Number(sec);
  return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

export function VisualPicker({ slug, scenes, assets, approved, canApprove }: {
  slug: string; scenes: VisualScene[]; assets: VisualAsset[]; approved: boolean; canApprove: boolean;
}) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<{ ok?: string; error?: string } | null>(null);
  const [kind, setKind] = useState<"doc" | "shorts">("doc");
  const router = useRouter();
  const byScene = new Map<string, VisualAsset[]>();
  assets.forEach((a) => byScene.set(a.scene_id, [...(byScene.get(a.scene_id) ?? []), a]));
  const missing = scenes.filter((s) => !s.asset_id).length;
  const act = (fn: () => Promise<{ ok?: string; error?: string } | undefined>) => start(async () => { setMsg((await fn()) ?? null); router.refresh(); });

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-zinc-950/60 p-3 text-sm">
        <div className="flex gap-1" role="tablist">
          {(["doc", "shorts"] as const).map((k) => (
            <button key={k} role="tab" aria-selected={kind === k} onClick={() => setKind(k)}
                    className={`rounded-md px-3 py-1.5 ${kind === k ? "bg-amber-500/15 text-amber-300" : "text-zinc-400 hover:text-zinc-200"}`}>
              {k === "doc" ? "Ana belgesel" : "Shorts"} ({scenes.filter((s) => s.kind === k).length})
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <a className="text-xs text-amber-300 hover:underline" href={`/api/projects/${slug}/credits`}>credits.txt indir</a>
          {approved ? (
            <>
              <span className="flex items-center gap-1 text-emerald-300"><Check size={16} /> Onaylandı</span>
              <button className={btnGhost} disabled={pending} onClick={() => act(() => unapproveVisuals(slug))}>Onayı geri al</button>
            </>
          ) : canApprove ? (
            <button className={btnPrimary} disabled={pending || missing > 0} onClick={() => act(() => approveVisuals(slug))}>
              Görselleri onayla
            </button>
          ) : null}
        </div>
      </div>
      {missing > 0 && <p className="mb-3 text-sm text-amber-200">{missing} sahnede uygun lisanslı görsel bulunamadı.</p>}
      {msg?.error && <p role="alert" className="mb-3 text-sm text-rose-300">{msg.error}</p>}
      {msg?.ok && <p role="status" className="mb-3 text-sm text-emerald-300">{msg.ok}</p>}

      <ol className="space-y-3">
        {scenes.filter((s) => s.kind === kind).map((s) => {
          const cands = byScene.get(s.id) ?? [];
          const chosen = cands.find((a) => a.id === s.asset_id);
          return (
            <li key={s.id} className="grid gap-4 rounded-lg border border-white/5 bg-zinc-950/40 p-3 lg:grid-cols-[18rem_1fr]">
              <div>
                {chosen ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={small(chosen.thumb_url)} alt={chosen.title ?? ""} loading="lazy"
                       className={`w-full rounded-md object-cover ${kind === "shorts" ? "aspect-[9/16] max-h-80" : "aspect-video"}`} />
                ) : (
                  <div className="grid aspect-video place-items-center rounded-md bg-zinc-900 text-zinc-600"><ImageOff /></div>
                )}
                {chosen && (
                  <div className="mt-2 space-y-1 text-xs">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className={`rounded px-1.5 py-0.5 ${LIC[chosen.license_class ?? ""]?.cls ?? "bg-zinc-700 text-zinc-300"}`}>
                        {LIC[chosen.license_class ?? ""]?.label ?? chosen.license}
                      </span>
                      <span className="text-zinc-500">{SRC[chosen.source ?? ""] ?? chosen.source}</span>
                      {chosen.width && <span className="text-zinc-500">{chosen.width}×{chosen.height}</span>}
                    </div>
                    <p className="line-clamp-2 text-zinc-300">{chosen.title}</p>
                    <p className="text-zinc-500">{chosen.author}</p>
                    {chosen.source_url && (
                      <a href={chosen.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-zinc-400 hover:text-amber-300">
                        Kaynak <ExternalLink size={11} />
                      </a>
                    )}
                  </div>
                )}
              </div>
              <div className="min-w-0">
                <div className="mb-1 text-xs text-zinc-500">
                  <span className="font-mono text-zinc-300">#{s.idx}</span>{s.start_sec != null && ` · ${fmt(s.start_sec)}–${fmt(s.end_sec)}`}
                  {s.visual_description && ` · istenen: ${s.visual_description}`}
                </div>
                <p className="mb-3 text-sm text-zinc-200">{s.voiceover_text}</p>
                {cands.length > 1 && (
                  <div>
                    <p className="mb-1.5 text-xs text-zinc-500">Alternatifler (seçmek için tıklayın):</p>
                    <div className="flex gap-2 overflow-x-auto pb-1">
                      {cands.filter((a) => a.id !== s.asset_id).map((a) => (
                        <button key={a.id} disabled={pending || approved} onClick={() => act(() => selectAsset(slug, s.id, a.id))}
                                title={`${a.title} — ${LIC[a.license_class ?? ""]?.label ?? a.license}`}
                                className="group relative w-28 shrink-0 overflow-hidden rounded-md ring-1 ring-white/10 hover:ring-amber-400 disabled:opacity-50">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={small(a.thumb_url)} alt={a.title ?? ""} loading="lazy" className="aspect-video w-full object-cover" />
                          <span className="absolute bottom-0 left-0 right-0 truncate bg-black/70 px-1 text-[10px] text-zinc-300">
                            {LIC[a.license_class ?? ""]?.label ?? a.license_class}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {!approved && (
                  <SceneImageTools slug={slug} sceneId={s.id} vertical={kind === "shorts"}
                                   suggestion={s.search_keywords?.[0] ?? s.visual_description?.slice(0, 60) ?? ""} />
                )}
                {approved && <p className="mt-2 text-xs text-zinc-500">Görsel aramak veya yüklemek için önce onayı geri alın.</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
