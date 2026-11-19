"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Check, Pencil, Trash2 } from "lucide-react";
import { approveScripts, deleteScene, unapproveScripts, updateSceneText } from "@/app/actions";
import { unsupportedNumbers } from "@/lib/numbers";
import { btnGhost, btnPrimary } from "./ui";

export type EditableScene = {
  id: string; kind: "doc" | "shorts"; idx: number; act: string | null; voiceover_text: string; claim_refs: string[];
  visual_description: string | null; word_count: number | null; est_duration_sec: string | null; needs_check?: boolean;
};

const ACT_TR: Record<string, string> = {
  giris: "Çarpıcı giriş", arka_plan: "Tarihsel arka plan", gelisme: "Olayların gelişimi",
  donum_noktasi: "Kritik dönüm noktası", sonuclar: "Sonuçlar", kapanis: "Güçlü kapanış", shorts: "Shorts",
};
const PRACTICAL_FLAG = "Kontrol edilmeli: fiyat, saat veya ulaşım bilgisi içeriyor — yayından önce resmî kaynaktan doğrulayın";
const HEDGES = /(kaynaklara göre|anlatılana göre|araştırmalara göre|uzmanlara göre|bazı kaynaklara göre)/gi;
// Rapor/ansiklopedi dili (worker/fds_worker/script.py report_style ile aynı kural)
const REPORT = /\p{L}+(mıştır|miştir|muştur|müştür|maktadır|mektedir)(?=[\s.,;]|$)/giu;
const reportStyle = (t: string) => (t.match(REPORT)?.length ?? 0) >= 2 || /çelişki vardır|genel kabul/i.test(t);

/** Kodla hesaplanabilen uyarılar. Kaynakta olmayan AYRINTILARI (ör. "kılıçlar çekildi") kod yakalayamaz: son okuma sizde. */
function flagsFor(scenes: EditableScene[], claims: string) {
  const refScenes = new Map<string, number[]>();
  scenes.forEach((s) => s.claim_refs.forEach((r) => refScenes.set(r, [...(refScenes.get(r) ?? []), s.idx])));
  const hedgeTotal = scenes.reduce((n, s) => n + (s.voiceover_text.match(HEDGES)?.length ?? 0), 0);
  return new Map(scenes.map((s) => {
    const f: string[] = [];
    if (s.needs_check) f.push(PRACTICAL_FLAG);
    const nums = unsupportedNumbers(s.voiceover_text, claims);
    if (nums.length) f.push(`Kaynakta olmayan sayı: ${nums.join(", ")}`);
    const rep = s.claim_refs.filter((r) => (refScenes.get(r) ?? []).length > 1)
      .map((r) => `${r} (sahne ${refScenes.get(r)!.filter((i) => i !== s.idx).join(", ")})`);
    if (rep.length) f.push(`Aynı bilgi başka sahnede de var: ${rep.join("; ")}`);
    if (reportStyle(s.voiceover_text)) f.push("Rapor dili (-mıştır/-mektedir): anlatım diline çevirin (ör. 'yıkılmıştır' → 'yıkıldı')");
    if (hedgeTotal > 3 && HEDGES.test(s.voiceover_text)) f.push(`"…göre" kalıbı senaryoda ${hedgeTotal} kez geçiyor (en fazla 3 önerilir)`);
    HEDGES.lastIndex = 0;
    return [s.id, f];
  }));
}

export function SceneEditor({ slug, scenes, claims, approved, canApprove, actTitles, label = "Belgesel" }: {
  slug: string; scenes: EditableScene[]; claims: string; approved: boolean; canApprove: boolean;
  actTitles?: Record<string, string>; label?: string;
}) {
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok?: string; error?: string } | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();

  const current = scenes.map((s) => ({ ...s, voiceover_text: texts[s.id] ?? s.voiceover_text }));
  const flags = useMemo(() => flagsFor(current, claims), [current, claims]);
  const flagged = current.filter((s) => (flags.get(s.id) ?? []).length).length;

  const save = (id: string) => start(async () => {
    const r = await updateSceneText(slug, id, texts[id]);
    setMsg(r ?? null);
    if (r?.ok) { setEditing(null); router.refresh(); }
  });
  const act = (fn: () => Promise<{ ok?: string; error?: string } | undefined>) => start(async () => {
    setMsg((await fn()) ?? null);
    router.refresh();
  });

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-zinc-950/60 p-3 text-sm">
        <span className={flagged ? "text-amber-200" : "text-emerald-300"}>
          {flagged ? `${flagged} sahnede otomatik uyarı var.` : "Otomatik uyarı yok."}{" "}
          <span className="text-zinc-500">Kaynakta olmayan ayrıntıları kod yakalayamaz; seslendirmeden önce metni okuyun.</span>
        </span>
        {approved ? (
          <span className="flex items-center gap-2">
            <span className="flex items-center gap-1 text-emerald-300"><Check size={16} /> Onaylandı</span>
            <button className={btnGhost} disabled={pending} onClick={() => act(() => unapproveScripts(slug))}>Onayı geri al</button>
          </span>
        ) : canApprove ? (
          <button className={btnPrimary} disabled={pending} onClick={() => act(() => approveScripts(slug))}>
            {label} + Shorts senaryosunu onayla
          </button>
        ) : null}
      </div>
      {msg?.error && <p role="alert" className="mb-3 text-sm text-rose-300">{msg.error}</p>}
      {msg?.ok && <p role="status" className="mb-3 text-sm text-emerald-300">{msg.ok}</p>}
      <ol className="space-y-2">
        {current.map((s, i) => {
          const f = flags.get(s.id) ?? [];
          const header = s.act !== "shorts" && s.act !== current[i - 1]?.act ? s.act : null;
          const isEditing = editing === s.id;
          return (
            <li key={s.id}>
              {header && <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-amber-300/80">{actTitles?.[header] ?? ACT_TR[header] ?? header}</h3>}
              <div className={`rounded-lg border p-3 ${f.length ? "border-amber-500/40 bg-amber-500/[0.06]" : "border-white/5 bg-zinc-950/40"}`}>
                <div className="mb-1 flex items-center justify-between gap-3 text-xs text-zinc-500">
                  <span><span className="font-mono text-zinc-300">#{s.idx}</span> · {s.word_count} kelime · ~{Number(s.est_duration_sec ?? 0).toFixed(0)} sn
                    {s.claim_refs.length > 0 && <span className="ml-2 font-mono">{s.claim_refs.join(" ")}</span>}</span>
                  {!approved && !isEditing && (
                    <span className="flex items-center gap-3">
                      <button className="flex items-center gap-1 hover:text-zinc-200" onClick={() => setEditing(s.id)} aria-label={`Sahne ${s.idx} düzenle`}>
                        <Pencil size={13} /> Düzenle
                      </button>
                      <button className="flex items-center gap-1 hover:text-rose-300" disabled={pending} aria-label={`Sahne ${s.idx} sil`}
                              onClick={() => { if (window.confirm(`Sahne ${s.idx} silinsin mi?`)) act(() => deleteScene(slug, s.id)); }}>
                        <Trash2 size={13} /> Sil
                      </button>
                    </span>
                  )}
                </div>
                {isEditing ? (
                  <div className="space-y-2">
                    <textarea aria-label={`Sahne ${s.idx} metni`} className="min-h-28 w-full rounded-md border border-white/10 bg-zinc-950 p-2 text-sm text-zinc-100 focus:border-amber-500/60 focus:outline-none"
                              value={s.voiceover_text} onChange={(e) => setTexts({ ...texts, [s.id]: e.target.value })} />
                    <div className="flex gap-2">
                      <button className={btnPrimary} disabled={pending} onClick={() => save(s.id)}>Kaydet</button>
                      <button className={btnGhost} onClick={() => { setEditing(null); const t = { ...texts }; delete t[s.id]; setTexts(t); }}>Vazgeç</button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm leading-relaxed text-zinc-100">{s.voiceover_text}</p>
                )}
                {f.map((x) => (
                  <p key={x} className="mt-1 flex items-start gap-1.5 text-xs text-amber-200"><AlertTriangle size={13} className="mt-0.5 shrink-0" />{x}</p>
                ))}
                {s.visual_description && <p className="mt-1 text-xs text-zinc-500">Görsel: {s.visual_description}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
