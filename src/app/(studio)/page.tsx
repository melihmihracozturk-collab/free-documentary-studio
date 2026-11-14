import Link from "next/link";
import { getDashboard } from "@/lib/queries";
import { Card, Empty, PageHeader, Stat, StatusBadge, btnPrimary } from "@/components/ui";
import { StorageMeter } from "@/components/StorageMeter";
import { timeAgo } from "@/lib/format";

export default async function Dashboard() {
  const { counts, errors, active, storage } = await getDashboard();
  return (
    <>
      <PageHeader title="Dashboard" description="Projelerin, bekleyen işlerin ve ücretsiz kotaların genel durumu.">
        <Link href="/yeni" className={btnPrimary}>Yeni belgesel</Link>
      </PageHeader>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Aktif projeler" value={counts.active} />
        <Stat label="Tamamlanan videolar" value={counts.renders_done} hint={`${counts.done} proje bitti`} />
        <Stat label="Bekleyen seslendirmeler" value={counts.waiting_voice}
              tone={counts.waiting_voice ? "warn" : "default"} hint="ElevenLabs dosyası bekleniyor" />
        <Stat label="Render durumu" value={`${counts.running_steps} çalışıyor`}
              hint={`${counts.queued_steps} sırada · ${counts.failed_steps} hatalı`}
              tone={counts.failed_steps ? "bad" : "default"} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Aktif projeler" className="lg:col-span-2"
              action={<Link href="/projeler" className="text-xs text-zinc-400 hover:text-zinc-200">Tümü →</Link>}>
          {active.length === 0 ? (
            <Empty>Henüz aktif proje yok. <Link href="/yeni" className="text-amber-300 hover:underline">İlk belgeseli başlatın.</Link></Empty>
          ) : (
            <ul className="divide-y divide-white/5">
              {active.map((p) => (
                <li key={p.id}>
                  <Link href={`/projeler/${p.slug}`} className="flex items-center justify-between gap-4 py-3 hover:text-white">
                    <div className="min-w-0">
                      <div className="truncate text-sm text-zinc-100">{p.title}</div>
                      <div className="text-xs text-zinc-500">{p.current_label ?? "—"} · {timeAgo(p.updated_at)}</div>
                    </div>
                    <StatusBadge status={p.current_status ?? p.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Depolama (Cloudflare R2)">
          <StorageMeter {...storage} />
        </Card>
      </div>

      <Card title="Hata kayıtları" className="mt-6">
        {errors.length === 0 ? (
          <Empty>Kayıtlı hata yok.</Empty>
        ) : (
          <ul className="divide-y divide-white/5 text-sm">
            {errors.map((e) => (
              <li key={e.id} className="flex items-start gap-3 py-2.5">
                <StatusBadge status={e.level} />
                <div className="min-w-0 flex-1">
                  <p className="break-words text-zinc-200">{e.message}</p>
                  <p className="text-xs text-zinc-500">
                    {e.slug ? <Link className="hover:text-zinc-300" href={`/projeler/${e.slug}`}>{e.slug}</Link> : "sistem"}
                    {e.step_key ? ` · ${e.step_key}` : ""} · {timeAgo(e.created_at)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
