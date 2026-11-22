import { Download } from "lucide-react";
import { Card, Empty, Stat } from "./ui";
import { getProjectFormat, getRenders, getStepState } from "@/lib/queries";
import { db } from "@/lib/db";
import { formatBytes, formatDate } from "@/lib/format";

function fmt(sec: number) {
  return `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")}`;
}

const STEP_LABEL: Record<string, string> = { pending: "sırada", running: "çalışıyor", failed: "hata", done: "tamam", waiting_input: "sizi bekliyor" };

export async function RenderView({ projectId, slug, kind }: { projectId: string; slug: string; kind: "doc" | "shorts" }) {
  const [renders, step, subs] = await Promise.all([
    getRenders(projectId), getStepState(projectId, kind === "doc" ? "render_doc" : "render_shorts"), getStepState(projectId, "subtitles")]);
  if (kind === "doc" && (await getProjectFormat(projectId)) === "review") {
    return <Card title="Ana video"><Empty>Bu bir Ayla öneri projesi: yalnızca ≈1 dakikalık Shorts üretilir. Videoyu Shorts sayfasında bulabilirsiniz.</Empty></Card>;
  }
  const r = renders.find((x) => x.kind === kind);
  const [{ n: restricted }] = await db()<{ n: number }[]>`
    select count(*)::int n from scenes s join assets a on a.id = s.asset_id
     where s.project_id = ${projectId} and s.kind = ${kind}
       and coalesce(a.license_class, 'unknown') in ('nc', 'nd', 'unknown', 'restricted')`;
  const warn = restricted > 0 && (
    <p role="alert" className="mb-3 rounded-lg border border-rose-500/50 bg-rose-500/10 p-3 text-sm text-rose-200">
      ⚠ Bu videoda {restricted} TELİFLİ görsel var (taslak). Yayınlamadan önce Görseller sayfasında değiştirip yeniden render alın;
      aksi hâlde YouTube telif bildirimi gelebilir.
    </p>
  );
  if (!r) {
    return (
      <Card title={kind === "doc" ? "Ana belgesel" : "Shorts"}>
        <Empty>
          Henüz render yok. Altyazı: {STEP_LABEL[subs?.status ?? "pending"] ?? subs?.status} · Render: {STEP_LABEL[step?.status ?? "pending"] ?? step?.status}.
          {" "}Render bulut işçisinde (GitHub Actions) yapılır; 12 dakikalık bir belgesel yaklaşık 15–30 dakika sürer.
        </Empty>
      </Card>
    );
  }
  const vertical = kind === "shorts";
  return (
    <>
      {warn}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Süre" value={fmt(Number(r.duration_sec))} />
        <Stat label="Çözünürlük" value={`${r.width}×${r.height}`} hint={`${Number(r.fps)} fps · H.264`} />
        <Stat label="Dosya" value={formatBytes(Number(r.bytes))}
              hint={`${((Number(r.bytes) * 8) / Number(r.duration_sec) / 1e6).toFixed(1)} Mbps · MP4 · AAC 192k`} />
        <Stat label="Render" value={formatDate(r.created_at)} />
      </div>
      <Card title="Kontrol kareleri (videodan 9 kare)">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={`/api/projects/${slug}/render/${kind}/poster`} alt="Videodan eşit aralıklı 9 kare" loading="lazy"
             className={`mx-auto rounded-lg ${vertical ? "max-h-[70vh]" : "w-full"}`} />
      </Card>
      <Card title="Önizleme">
        <video controls preload="metadata" src={`/api/projects/${slug}/render/${kind}`}
               className={`mx-auto rounded-lg bg-black ${vertical ? "max-h-[75vh] aspect-[9/16]" : "w-full aspect-video"}`} />
        <div className="mt-4 flex flex-wrap gap-3">
          <a href={`/api/projects/${slug}/render/${kind}?download=1`} className="flex items-center gap-2 rounded-md bg-amber-500 px-3 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400">
            <Download size={15} /> Videoyu indir (MP4)
          </a>
          <a href={`/api/projects/${slug}/subtitles/${kind}`} className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-zinc-200 ring-1 ring-inset ring-white/10 hover:bg-white/5">
            <Download size={15} /> Altyazı (SRT)
          </a>
          <a href={`/api/projects/${slug}/credits`} className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-zinc-200 ring-1 ring-inset ring-white/10 hover:bg-white/5">
            <Download size={15} /> Görsel kaynakları (credits.txt)
          </a>
          <a href={`/api/projects/${slug}/deliverable/${kind === "doc" ? "youtube_description.txt" : "shorts_description.txt"}`}
             className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-zinc-200 ring-1 ring-inset ring-white/10 hover:bg-white/5">
            <Download size={15} /> YouTube açıklaması
          </a>
        </div>
        <p className="mt-3 text-xs text-zinc-500">
          Altyazılar videoya gömülüdür; SRT dosyasını YouTube&apos;a ayrıca yükleyebilirsiniz. credits.txt içeriğini video açıklamasına ekleyin (CC BY görseller için zorunlu).
          SHA-256: <span className="font-mono">{r.sha256?.slice(0, 16)}…</span>
        </p>
      </Card>
    </>
  );
}
