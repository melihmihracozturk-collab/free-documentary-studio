import Link from "next/link";
import { notFound } from "next/navigation";
import { getProjectStatus } from "@/lib/queries";
import { Card, PageHeader, StatusBadge, btnDanger, btnGhost } from "@/components/ui";
import { StepTimeline, type TimelineStep } from "@/components/StepTimeline";
import { archiveProject, cancelJob, restartPipeline } from "@/app/actions";
import { formatDate } from "@/lib/format";

export default async function ProjectPage({ params }: PageProps<"/projeler/[slug]">) {
  const { slug } = await params;
  const data = await getProjectStatus(slug);
  if (!data) notFound();
  const { project: p, job, steps } = data;
  const done = steps.filter((s) => s.status === "done" || s.status === "skipped").length;
  const finished = job && ["done", "failed", "cancelled"].includes(job.status);

  return (
    <>
      <PageHeader title={p.title} description={`${p.language.toUpperCase()} · ${Number(p.target_minutes)} dk ${p.format === "vlog" ? "gezi vlogu" : "belgesel"} + ${p.shorts_seconds} sn Shorts · ${p.style}`}>
        <div className="flex items-center gap-2">
          {job && <StatusBadge status={job.status} />}
          {job && !finished && (
            <form action={cancelJob.bind(null, job.id, slug)}><button className={btnDanger}>İşi iptal et</button></form>
          )}
          {finished && (
            <form action={restartPipeline.bind(null, p.id, slug)}><button className={btnGhost}>Yeniden başlat</button></form>
          )}
          {p.status !== "archived" && (
            <form action={archiveProject.bind(null, p.id, slug)}><button className={btnGhost}>Arşivle</button></form>
          )}
        </div>
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title={`Üretim hattı · ${done}/${steps.length}`} className="lg:col-span-2">
          {job ? (
            <StepTimeline slug={slug} initialJobStatus={job.status}
                          initialSteps={JSON.parse(JSON.stringify(steps)) as TimelineStep[]} />
          ) : <p className="text-sm text-zinc-500">Bu proje için iş yok.</p>}
        </Card>
        <div className="space-y-6">
          <Card title="Proje">
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between gap-3"><dt className="text-zinc-500">Kısa ad</dt><dd className="font-mono text-xs text-zinc-300">{p.slug}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-zinc-500">Oluşturma</dt><dd className="text-zinc-300">{formatDate(p.created_at)}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-zinc-500">Durum</dt><dd><StatusBadge status={p.status} /></dd></div>
            </dl>
          </Card>
          <Card title="Bulut klasörü">
            <pre className="overflow-x-auto text-xs leading-relaxed text-zinc-400">{`projects/${p.slug}/
  research/   scripts/
  voiceover/  assets/
  scenes/     subtitles/
  renders/    shorts/`}</pre>
            <p className="mt-2 text-xs text-zinc-500">Dosyalar Cloudflare R2&apos;de tutulur (Stage 4 ile etkin).</p>
          </Card>
          <Card title="Modüller">
            <ul className="space-y-1 text-sm">
              {[["arastirma","Araştırma"],["senaryo","Senaryo"],["gorseller","Görsel Arşivi"],["seslendirme","Seslendirme"],["belgesel","Ana Belgesel"],["shorts","Shorts"]].map(([h,l]) => (
                <li key={h}><Link className="text-zinc-400 hover:text-amber-300" href={`/${h}?p=${slug}`}>{l} →</Link></li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
