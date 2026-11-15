import { Download } from "lucide-react";
import { Card, Empty, StatusBadge } from "./ui";
import { VoiceoverUpload } from "./VoiceoverUpload";
import { getScripts, getStepState, getVoiceovers, type Voiceover } from "@/lib/queries";
import { r2Configured } from "@/lib/r2";
import { formatBytes } from "@/lib/format";

const KIND = { doc: { label: "Belgesel seslendirmesi", file: "documentary_voiceover.txt", range: "8–15 dk" },
  shorts: { label: "Shorts seslendirmesi", file: "shorts_voiceover.txt", range: "45–60 sn" } } as const;
const VO_STATUS: Record<string, string> = { uploaded: "running", analyzing: "running", analyzed: "done", failed: "failed" };

function fmt(sec: number) {
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function Analysis({ v }: { v: Voiceover }) {
  const a = v.analysis;
  if (v.status !== "analyzed" || !a) return <p className="text-xs text-zinc-500">Analiz bekleniyor: bulut işçisi sesi indirip süre, duraklama ve kelime zamanlarını çıkaracak.</p>;
  return (
    <div className="space-y-2 text-sm">
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div><dt className="text-xs text-zinc-500">Süre</dt><dd className="tabular-nums text-zinc-100">{fmt(a.duration_sec ?? 0)}</dd></div>
        <div><dt className="text-xs text-zinc-500">Senaryo eşleşmesi</dt><dd className="tabular-nums text-zinc-100">%{Math.round((a.coverage ?? 0) * 100)}</dd></div>
        <div><dt className="text-xs text-zinc-500">Konuşma hızı</dt><dd className="tabular-nums text-zinc-100">{a.wpm} kelime/dk</dd></div>
        <div><dt className="text-xs text-zinc-500">Duraklama</dt><dd className="tabular-nums text-zinc-100">{a.pauses} (en uzun {a.longest_pause_sec} sn)</dd></div>
      </dl>
      {(a.warnings ?? []).map((w) => <p key={w} className="text-xs text-amber-200">⚠ {w}</p>)}
    </div>
  );
}

export async function VoiceoverView({ projectId, slug }: { projectId: string; slug: string }) {
  const [vos, review, texts, scripts] = await Promise.all([
    getVoiceovers(projectId), getStepState(projectId, "script_review"), getStepState(projectId, "voiceover_texts"), getScripts(projectId)]);
  const approved = review?.status === "done";
  if (!approved) {
    return <Card title="Seslendirme"><Empty>Önce senaryoyu Senaryo sayfasında okuyup onaylayın. ElevenLabs metinleri onaylı senaryodan üretilir.</Empty></Card>;
  }
  const r2 = r2Configured();
  return (
    <>
      <Card title="1 · ElevenLabs metinlerini indirin">
        <p className="mb-3 text-sm text-zinc-400">
          Her dosyada yalnızca okunacak cümleler var; sahneler arasında boş satır bırakıldı (doğal duraklama).
          ElevenLabs&apos;te seslendirip MP3 veya WAV olarak indirin.
        </p>
        <div className="flex flex-wrap gap-3">
          {(["doc", "shorts"] as const).map((k) => {
            const s = k === "doc" ? scripts.doc : scripts.shorts;
            const chars = (k === "doc" ? scripts.docScenes : scripts.shortsScenes).reduce((n, x) => n + x.voiceover_text.length + 2, 0);
            return (
              <a key={k} href={`/api/projects/${slug}/voiceover-text/${k}`}
                 className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-zinc-200 ring-1 ring-inset ring-white/10 hover:bg-white/5">
                <Download size={15} /> {KIND[k].file}
                <span className="text-xs text-zinc-500">≈{chars.toLocaleString("tr-TR")} karakter{s?.word_count ? ` · ${s.word_count} kelime` : ""}</span>
              </a>
            );
          })}
        </div>
        <p className="mt-3 text-xs text-zinc-500">
          ElevenLabs ücretsiz planı ayda 10.000 kredi verir (karakter başına yaklaşık 1 kredi). Ticari kullanım lisansı ücretsiz planda yok görünüyor; kontrol edin.
          {texts?.status !== "done" && " Metinler bulut işçisinde de hazırlanıyor."}
        </p>
      </Card>

      <Card title="2 · Ses dosyalarını yükleyin">
        {!r2 && <p className="mb-3 text-sm text-amber-200">Cloudflare R2 yapılandırılmadığı için yükleme kapalı (Ayarlar → servis bağlantıları).</p>}
        <div className="grid gap-4 md:grid-cols-2">
          {(["doc", "shorts"] as const).map((k) => {
            const v = vos.find((x) => x.kind === k);
            return (
              <div key={k} className="space-y-3 rounded-lg border border-white/5 bg-zinc-950/40 p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-zinc-100">{KIND[k].label}</h3>
                  <span className="text-xs text-zinc-500">hedef {KIND[k].range}</span>
                </div>
                {v ? (
                  <>
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="truncate text-zinc-300">{v.filename} · {formatBytes(Number(v.bytes))}</span>
                      <StatusBadge status={VO_STATUS[v.status] ?? v.status} />
                    </div>
                    {r2 && <audio controls preload="none" src={`/api/projects/${slug}/voiceover/${k}`} className="w-full" />}
                    <Analysis v={v} />
                  </>
                ) : <p className="text-xs text-zinc-500">Henüz yüklenmedi.</p>}
                {r2 && <VoiceoverUpload slug={slug} kind={k} label={v ? "Yeniden" : k === "doc" ? "Belgesel sesi" : "Shorts sesi"} />}
              </div>
            );
          })}
        </div>
        <p className="mt-3 text-xs text-zinc-500">Dosyalar tarayıcıdan doğrudan Cloudflare R2&apos;ye gider; bilgisayarınızda bir şey saklanmaz. Gerçek ses yüklenmeden render başlamaz.</p>
      </Card>

      {vos.some((v) => v.status === "analyzed") && (
        <Card title="3 · Sahne zamanları (gerçek sesten)">
          {(["doc", "shorts"] as const).map((k) => {
            const v = vos.find((x) => x.kind === k && x.status === "analyzed");
            const scenes = k === "doc" ? scripts.docScenes : scripts.shortsScenes;
            const times = v?.analysis?.scene_times ?? [];
            if (!v) return null;
            return (
              <details key={k} className="mb-2" open={k === "shorts"}>
                <summary className="cursor-pointer text-sm text-zinc-300">{KIND[k].label} · {scenes.length} sahne</summary>
                <table className="mt-2 w-full text-left text-xs">
                  <tbody className="divide-y divide-white/5">
                    {scenes.map((s, i) => (
                      <tr key={s.id}>
                        <td className="w-10 py-1.5 font-mono text-zinc-500">#{s.idx}</td>
                        <td className="w-28 py-1.5 tabular-nums text-zinc-300">{times[i] ? `${fmt(times[i][0])} – ${fmt(times[i][1])}` : "—"}</td>
                        <td className="py-1.5 text-zinc-400">{s.voiceover_text.slice(0, 110)}{s.voiceover_text.length > 110 ? "…" : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            );
          })}
        </Card>
      )}
    </>
  );
}
