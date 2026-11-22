import Link from "next/link";
import { listProjects } from "@/lib/queries";
import { Card, Empty, FormatBadge, PageHeader, StatusBadge, btnPrimary } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { FORMATS } from "@/lib/nav";

export default async function Projects({ searchParams }: PageProps<"/projeler">) {
  const { f } = await searchParams;
  const all = await listProjects();
  const active = FORMATS.some((x) => x.key === f) ? (f as string) : "all";
  const projects = active === "all" ? all : all.filter((p) => (p.format ?? "documentary") === active);
  const tabs = [{ key: "all", label: "Tümü" }, ...FORMATS];
  return (
    <>
      <PageHeader title="Proje Arşivi" description="Her proje ayrı saklanır; belgesel, vlog ve Ayla'nın öneri videoları ayrı sekmelerde.">
        <Link href="/yeni" className={btnPrimary}>Yeni proje</Link>
      </PageHeader>
      <nav className="mb-4 flex flex-wrap gap-2" aria-label="Biçim">
        {tabs.map((t) => {
          const n = t.key === "all" ? all.length : all.filter((p) => (p.format ?? "documentary") === t.key).length;
          return (
            <Link key={t.key} href={t.key === "all" ? "/projeler" : `/projeler?f=${t.key}`}
                  className={`rounded-full px-3 py-1 text-sm ring-1 ring-inset ${active === t.key ? "bg-white/10 text-zinc-50 ring-white/20" : "text-zinc-400 ring-white/10 hover:bg-white/5"}`}>
              {t.label} <span className="tabular-nums text-zinc-500">{n}</span>
            </Link>
          );
        })}
      </nav>
      <Card>
        {projects.length === 0 ? <Empty>Henüz proje yok.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-zinc-500">
                <tr className="border-b border-white/8">
                  <th className="py-2 pr-4 font-medium">Proje</th>
                  <th className="py-2 pr-4 font-medium">İlerleme</th>
                  <th className="py-2 pr-4 font-medium">Durum</th>
                  <th className="py-2 font-medium">Oluşturma</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {projects.map((p) => (
                  <tr key={p.id}>
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        <Link href={`/projeler/${p.slug}`} className="text-zinc-100 hover:text-amber-300">{p.title}</Link>
                        <FormatBadge format={p.format} />
                      </div>
                      <div className="font-mono text-xs text-zinc-500">{p.slug}</div>
                    </td>
                    <td className="py-3 pr-4 tabular-nums text-zinc-400">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-white/8">
                          <div className="h-full bg-amber-400" style={{ width: `${p.total_steps ? (p.done_steps / p.total_steps) * 100 : 0}%` }} />
                        </div>
                        {p.done_steps}/{p.total_steps}
                      </div>
                    </td>
                    <td className="py-3 pr-4"><StatusBadge status={p.status} /></td>
                    <td className="py-3 text-zinc-400">{formatDate(p.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
