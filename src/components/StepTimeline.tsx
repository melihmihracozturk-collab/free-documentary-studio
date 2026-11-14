"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Circle, CircleAlert, Hand, Loader2, MinusCircle } from "lucide-react";
import { approveStep, retryStep } from "@/app/actions";
import { StatusBadge, btnGhost, btnPrimary } from "./ui";

export type TimelineStep = {
  id: string;
  step_key: string;
  label: string;
  stage: number;
  status: string;
  attempts: number;
  max_attempts: number;
  error: string | null;
  output: Record<string, unknown> | null;
  heartbeat_at: string | null;
};

const ACTIVE = new Set(["queued", "running"]);

function Icon({ status }: { status: string }) {
  const c = "shrink-0";
  if (status === "done") return <CheckCircle2 size={18} className={`${c} text-emerald-400`} />;
  if (status === "running") return <Loader2 size={18} className={`${c} animate-spin text-sky-400`} />;
  if (status === "failed") return <CircleAlert size={18} className={`${c} text-rose-400`} />;
  if (status === "waiting_input") return <Hand size={18} className={`${c} text-amber-400`} />;
  if (status === "cancelled" || status === "skipped") return <MinusCircle size={18} className={`${c} text-zinc-600`} />;
  return <Circle size={18} className={`${c} text-zinc-600`} />;
}

export function StepTimeline({ slug, initialSteps, initialJobStatus }: {
  slug: string; initialSteps: TimelineStep[]; initialJobStatus: string;
}) {
  // Sunucudan gelen yeni props (router.refresh) her zaman önceliklidir; anketle gelen veri yalnızca
  // aynı props üzerinden geldiyse kullanılır.
  const [polled, setPolled] = useState<{ from: TimelineStep[]; steps: TimelineStep[]; status: string } | null>(null);
  const fresh = polled && polled.from === initialSteps ? polled : null;
  const steps = fresh?.steps ?? initialSteps;
  const jobStatus = fresh?.status ?? initialJobStatus;
  const [pending, start] = useTransition();
  const router = useRouter();

  // Tarayıcı açıkken 4 sn'de bir durum çekilir; iş bulutta tarayıcıdan bağımsız sürer.
  useEffect(() => {
    if (!ACTIVE.has(jobStatus)) return;
    const t = setInterval(async () => {
      const res = await fetch(`/api/projects/${slug}/status`, { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      setPolled({ from: initialSteps, steps: data.steps, status: data.job?.status ?? "queued" });
    }, 4000);
    return () => clearInterval(t);
  }, [slug, jobStatus, initialSteps]);

  const act = (fn: () => Promise<void>) => start(async () => { await fn(); router.refresh(); });

  return (
    <ol className="relative space-y-1">
      {steps.map((s, i) => {
        const isNext = s.status !== "done" && steps.slice(0, i).every((p) => p.status === "done" || p.status === "skipped");
        const dry = s.output && (s.output as { dry_run?: boolean }).dry_run;
        return (
          <li key={s.id}
              className={`flex items-start gap-3 rounded-lg px-3 py-2.5 ${isNext ? "bg-white/[0.04] ring-1 ring-inset ring-white/8" : ""}`}>
            <Icon status={s.status} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className={`text-sm ${s.status === "done" ? "text-zinc-300" : "text-zinc-100"}`}>
                  <span className="mr-2 tabular-nums text-zinc-500">{String(i + 1).padStart(2, "0")}</span>
                  {s.label}
                </span>
                <StatusBadge status={s.status} />
                {dry ? <span className="text-xs text-zinc-500">test çıktısı</span> : null}
                {s.attempts > 1 && <span className="text-xs text-zinc-500">deneme {s.attempts}/{s.max_attempts}</span>}
                {s.status === "pending" && isNext && (
                  <span className="text-xs text-zinc-500">Stage {s.stage}&apos;te etkinleşecek</span>
                )}
              </div>
              {s.error && <p className="mt-1 break-words text-xs text-rose-300/90">{s.error}</p>}
              {s.status === "waiting_input" && s.step_key === "research_review" && (
                <div className="mt-2 flex items-center gap-2">
                  <button className={btnPrimary} disabled={pending} onClick={() => act(() => approveStep(s.id, slug))}>
                    Araştırmayı onayla
                  </button>
                  <span className="text-xs text-zinc-500">Raporu Araştırma sayfasında inceleyin.</span>
                </div>
              )}
              {s.status === "waiting_input" && s.step_key === "voiceover_wait" && (
                <p className="mt-1 text-xs text-amber-200/80">
                  Seslendirme sayfasından belgesel ve Shorts ses dosyalarını yükleyin. İkisi de yüklenince süreç kendiliğinden devam eder.
                </p>
              )}
              {s.status === "failed" && (
                <button className={`${btnGhost} mt-2`} disabled={pending} onClick={() => act(() => retryStep(s.id, slug))}>
                  Yeniden dene
                </button>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
