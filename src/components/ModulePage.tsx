import Link from "next/link";
import { Card, Empty, PageHeader, StatusBadge } from "./ui";
import { getProjectStatus, listProjects } from "@/lib/queries";

export type ModuleConfig = {
  title: string;
  description: string;
  stage: number;
  steps: string[];
  basePath: string;
  planned: string[];
  /** Modül çalışıyorsa "gelecekler" kartı gizlenir. */
  active?: boolean;
};

/** Modül sayfalarının ortak iskeleti: proje seçici + ilgili adımların durumu + bu modülde gelecekler. */
export async function ModulePage({ config, selected, render }: {
  config: ModuleConfig;
  selected?: string;
  /** Seçili proje için modüle özel içerik (ör. araştırma raporu). */
  render?: (project: { id: string; slug: string; title: string }) => Promise<React.ReactNode>;
}) {
  const projects = (await listProjects()).filter((p) => p.status !== "archived");
  const slug = selected ?? projects[0]?.slug;
  const status = slug ? await getProjectStatus(slug) : null;
  const steps = status?.steps.filter((s) => config.steps.includes(s.step_key)) ?? [];
  const extra = status && render ? await render(status.project) : null;

  return (
    <>
      <PageHeader title={config.title} description={config.description}>
        {!config.active && (
          <span className="rounded-full bg-white/5 px-2.5 py-1 text-xs text-zinc-400 ring-1 ring-inset ring-white/10">
            Stage {config.stage}&apos;te etkinleşecek
          </span>
        )}
      </PageHeader>

      {projects.length === 0 ? (
        <Empty>Henüz proje yok. <Link href="/yeni" className="text-amber-300 hover:underline">Yeni belgesel başlatın.</Link></Empty>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[14rem_minmax(0,1fr)]">
          <Card title="Proje">
            <ul className="space-y-0.5">
              {projects.map((p) => (
                <li key={p.id}>
                  <Link href={`${config.basePath}?p=${p.slug}`}
                        className={`block truncate rounded px-2 py-1.5 text-sm ${p.slug === slug ? "bg-amber-500/15 text-amber-300" : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"}`}>
                    {p.title}
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
          <div className="space-y-6">
            <Card title={status ? status.project.title : "Proje"}
                  action={status && <Link href={`/projeler/${status.project.slug}`} className="text-xs text-zinc-400 hover:text-zinc-200">Üretim hattı →</Link>}>
              {steps.length === 0 ? <Empty>Bu proje için ilgili adım yok.</Empty> : (
                <ul className="divide-y divide-white/5">
                  {steps.map((s) => (
                    <li key={s.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                      <span className="text-zinc-200">{s.label}</span>
                      <StatusBadge status={s.status} />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            {extra}
            {!config.active && (
              <Card title={`Stage ${config.stage} ile bu sayfaya gelecekler`}>
                <ul className="list-disc space-y-1.5 pl-4 text-sm text-zinc-400">
                  {config.planned.map((x) => <li key={x}>{x}</li>)}
                </ul>
              </Card>
            )}
          </div>
        </div>
      )}
    </>
  );
}
