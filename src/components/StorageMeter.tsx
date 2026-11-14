import { formatBytes } from "@/lib/format";

export function StorageMeter({ used, limit, guard }: { used: number; limit: number; guard: number }) {
  const pct = Math.min(100, (used / limit) * 100);
  const guardPct = (guard / limit) * 100;
  const tone = used >= guard ? "bg-rose-400" : used >= guard * 0.8 ? "bg-amber-400" : "bg-emerald-400";
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className="tabular-nums text-zinc-100">{formatBytes(used)}</span>
        <span className="text-xs text-zinc-500">/ {formatBytes(limit)} R2 ücretsiz</span>
      </div>
      <div className="relative mt-2 h-2 overflow-hidden rounded-full bg-white/8" role="meter"
           aria-valuemin={0} aria-valuemax={limit} aria-valuenow={used} aria-label="Depolama kullanımı">
        <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
        <div className="absolute inset-y-0 w-px bg-rose-300/80" style={{ left: `${guardPct}%` }} title="Koruma eşiği" />
      </div>
      <p className="mt-2 text-xs text-zinc-500">
        {used >= guard
          ? "Koruma eşiği aşıldı: yeni render başlamaz. Eski render'ları silin."
          : `Koruma eşiği ${formatBytes(guard)}: aşılırsa yeni render otomatik durur.`}
      </p>
    </div>
  );
}
