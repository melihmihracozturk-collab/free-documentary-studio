import { CheckCircle2, CircleDashed } from "lucide-react";
import { getSettings } from "@/lib/queries";
import { serviceStatus } from "@/lib/env";
import { Card, PageHeader } from "@/components/ui";
import { SettingsForm } from "@/components/SettingsForm";

const LIMITS = [
  ["GitHub Actions (public repo)", "Standart runner ücretsiz · 4 vCPU / 16 GB", "Doğrulandı"],
  ["Cloudflare R2", "10 GB depolama · indirme trafiği ücretsiz", "Doğrulandı · harcama tavanı yok"],
  ["Supabase Free", "500 MB veritabanı · 7 gün hareketsizlikte duraklar", "İşçi her 15 dk sorgu atar"],
  ["Vercel Hobby", "Fonksiyon başına 300 sn · ticari olmayan kullanım", "Kanal para kazanırsa taşınmalı"],
  ["Gemini API Free", "Kotalar değişken, AI Studio'da görünür", "Groq / OpenRouter yedek"],
  ["Cloudflare Workers AI", "Günde 10.000 neuron (≈5–7 görsel)", "Aşılınca hata verir, ücret almaz"],
];

export default async function SettingsPage() {
  const s = await getSettings();
  const services = serviceStatus();
  return (
    <>
      <PageHeader title="Ayarlar" description="Servis bağlantıları, ücretsiz kullanım sınırları ve üretim kuralları." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Üretim kuralları">
          <SettingsForm guardGb={Number(s.storage_guard_bytes ?? 0) / 1024 ** 3}
                        allowNc={s.license_allow_nc === true} allowSa={s.license_allow_sa !== false}
                        defaultMinutes={Number(s.default_minutes ?? 11)} />
        </Card>
        <Card title="Servis bağlantıları">
          <ul className="space-y-2 text-sm">
            {services.map((x) => (
              <li key={x.key} className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2">
                  {x.ok ? <CheckCircle2 size={16} className="text-emerald-400" /> : <CircleDashed size={16} className="text-zinc-600" />}
                  <span className={x.ok ? "text-zinc-200" : "text-zinc-400"}>{x.label}</span>
                </span>
                <span className="font-mono text-xs text-zinc-500">{x.key}{x.ok ? "" : ` · Stage ${x.stage}`}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-xs text-zinc-500">Anahtar değerleri burada asla gösterilmez. Vercel ortam değişkenlerine ve GitHub Secrets&apos;a girilir.</p>
        </Card>
        <Card title="Ücretsiz kullanım sınırları (Kasım 2026)" className="lg:col-span-2">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <tbody className="divide-y divide-white/5">
                {LIMITS.map(([svc, limit, note]) => (
                  <tr key={svc}>
                    <td className="py-2 pr-4 text-zinc-200">{svc}</td>
                    <td className="py-2 pr-4 text-zinc-400">{limit}</td>
                    <td className="py-2 text-xs text-zinc-500">{note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}
