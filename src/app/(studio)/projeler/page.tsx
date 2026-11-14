import Link from "next/link";
import { listProjects } from "@/lib/queries";
import { Card, Empty, PageHeader, StatusBadge, btnPrimary } from "@/components/ui";
import { formatDate } from "@/lib/format";

export default async function Projects() {
  const projects = await listProjects();
  return (
    <>
      <PageHeader title="Proje Arşivi" description="Her belgesel ayrı bir proje olarak bulutta saklanır.">
        <Link href="/yeni" className={btnPrimary}>Yeni belgesel</Link>
      </PageHeader>
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
                      <Link href={`/projeler/${p.slug}`} className="text-zinc-100 hover:text-amber-300">{p.title}</Link>
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
