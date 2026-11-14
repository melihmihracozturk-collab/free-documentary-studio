import { Card, Empty, Stat } from "./ui";
import { getResearch, type Claim } from "@/lib/queries";
import { formatDate } from "@/lib/format";

const CLAIM_TONE: Record<string, { label: string; cls: string }> = {
  verified: { label: "Doğrulandı", cls: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30" },
  weak: { label: "Tek kaynak", cls: "bg-zinc-500/15 text-zinc-300 ring-zinc-500/30" },
  conflict: { label: "Çelişkili", cls: "bg-rose-500/15 text-rose-300 ring-rose-500/30" },
};
const TYPE_TR: Record<string, string> = {
  encyclopedia: "Ansiklopedi", academic: "Akademik", archive: "Arşiv", official: "Resmî", museum: "Müze", news: "Haber", web: "Web",
};

function ClaimRow({ c }: { c: Claim }) {
  const tone = CLAIM_TONE[c.status] ?? CLAIM_TONE.weak;
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <span className="font-mono text-xs text-zinc-500">{c.ref}</span>
        <span className={`rounded-full px-2 py-0.5 text-xs ring-1 ring-inset ${tone.cls}`}>{tone.label}</span>
        {c.event_date && <span className="text-xs text-amber-200/80">{c.event_date}</span>}
        <span className="text-xs text-zinc-500">{c.independent_sources} bağımsız kaynak</span>
      </div>
      <p className="mt-1 text-sm text-zinc-100">{c.text}</p>
      {c.conflict_note && <p className="mt-1 text-xs text-rose-300/90">⚠ {c.conflict_note}</p>}
      <details className="mt-1">
        <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-300">Alıntılar ({c.support.length})</summary>
        <ul className="mt-1 space-y-1">
          {c.support.map((s, i) => (
            <li key={i} className="text-xs text-zinc-400"><span className="font-mono text-zinc-500">{s.source_ref}</span> “{s.quote}”</li>
          ))}
        </ul>
      </details>
    </li>
  );
}

export async function ResearchView({ projectId, slug }: { projectId: string; slug: string }) {
  const { report, claims, sources } = await getResearch(projectId);
  if (!report && claims.length === 0) {
    return <Card title="Araştırma raporu"><Empty>Araştırma henüz çalışmadı. Bulut işçisi LLM anahtarıyla çalıştığında rapor burada görünecek.</Empty></Card>;
  }
  const count = (s: string) => claims.filter((c) => c.status === s).length;
  const conflicts = claims.filter((c) => c.status === "conflict");
  return (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Kaynak" value={sources.length} />
        <Stat label="Doğrulanmış bilgi" value={count("verified")} hint="≥2 bağımsız kaynak" />
        <Stat label="Tek kaynak" value={count("weak")} hint="dikkatli ifade edilir" />
        <Stat label="Çelişki" value={count("conflict")} tone={count("conflict") ? "warn" : "default"} />
      </div>
      {report && (
        <Card title={`Özet · sürüm ${report.version}`}
              action={<a className="text-xs text-amber-300 hover:underline" href={`/api/projects/${slug}/research`}>Raporu indir (.md)</a>}>
          <p className="whitespace-pre-line text-sm leading-relaxed text-zinc-200">{report.summary}</p>
          <p className="mt-3 text-xs text-zinc-500">{formatDate(report.created_at)}</p>
        </Card>
      )}
      {conflicts.length > 0 && (
        <Card title="Kaynaklar arasındaki çelişkiler">
          <ul className="divide-y divide-white/5">{conflicts.map((c) => <ClaimRow key={c.id} c={c} />)}</ul>
        </Card>
      )}
      <Card title={`Bilgiler ve kaynak durumu (${claims.length})`}>
        <ul className="divide-y divide-white/5">{claims.filter((c) => c.status !== "conflict").map((c) => <ClaimRow key={c.id} c={c} />)}</ul>
      </Card>
      <Card title={`Kaynaklar (${sources.length})`}>
        <ul className="space-y-2 text-sm">
          {sources.map((s) => (
            <li key={s.id} className="flex gap-3">
              <span className="w-8 shrink-0 font-mono text-xs text-zinc-500">{s.ref}</span>
              <div className="min-w-0">
                <a href={s.url} target="_blank" rel="noreferrer" className="break-words text-zinc-100 hover:text-amber-300">{s.title}</a>
                <div className="text-xs text-zinc-500">{s.publisher}{s.published ? ` · ${s.published}` : ""} · {TYPE_TR[s.source_type] ?? s.source_type}</div>
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
