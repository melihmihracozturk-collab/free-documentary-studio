import Link from "next/link";
import { getRenderQueue, getStorageUsage } from "@/lib/queries";
import { Card, Empty, PageHeader, StatusBadge } from "@/components/ui";
import { StorageMeter } from "@/components/StorageMeter";
import { timeAgo } from "@/lib/format";

export default async function RenderCenter() {
  const [queue, storage] = await Promise.all([getRenderQueue(), getStorageUsage()]);
  return (
    <>
      <PageHeader title="Render Merkezi"
                  description="Bulut işçisinin (GitHub Actions) üzerindeki işler. Tarayıcıyı kapatsanız da işler sürer; yarım kalan adımlar kaldığı yerden devam eder." />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Kuyruk" className="lg:col-span-2">
          {queue.length === 0 ? <Empty>Kuyrukta iş yok.</Empty> : (
            <ul className="divide-y divide-white/5">
              {queue.map((s) => (
                <li key={s.id} className="flex items-start justify-between gap-3 py-3 text-sm">
                  <div className="min-w-0">
                    <div className="text-zinc-100">{s.label}</div>
                    <div className="text-xs text-zinc-500">
                      <Link href={`/projeler/${s.slug}`} className="hover:text-zinc-300">{s.title}</Link>
                      {s.status === "running" && ` · son sinyal ${timeAgo(s.heartbeat_at)}`}
                      {s.status === "pending" && ` · Stage ${s.stage} işleyicisi bekleniyor`}
                    </div>
                    {s.error && <p className="mt-1 break-words text-xs text-rose-300/90">{s.error}</p>}
                  </div>
                  <StatusBadge status={s.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="space-y-6">
          <Card title="Depolama"><StorageMeter {...storage} /></Card>
          <Card title="Render hedefleri">
            <dl className="space-y-2 text-sm">
              <div><dt className="text-zinc-500">Ana belgesel</dt><dd className="text-zinc-300">1920×1080 · 16:9 · 25 fps · H.264 · MP4</dd></div>
              <div><dt className="text-zinc-500">Shorts</dt><dd className="text-zinc-300">1080×1920 · 9:16 · 30 fps · H.264 · MP4</dd></div>
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}
