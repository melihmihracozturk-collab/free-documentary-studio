import { FORMATS, STATUS_LABEL } from "@/lib/nav";

const TONE: Record<string, string> = {
  done: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  running: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  rendering: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  waiting_input: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  failed: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  error: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  warning: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
};

const FORMAT_TONE: Record<string, string> = {
  documentary: "bg-amber-500/10 text-amber-300 ring-amber-500/25",
  vlog: "bg-sky-500/10 text-sky-300 ring-sky-500/25",
  review: "bg-violet-500/15 text-violet-300 ring-violet-500/30",
};

/** Projenin biçimi: Belgesel (amber), Vlog (mavi), Öneri · Ayla (mor). Sistemler panelde karışmasın diye her yerde gösterilir. */
export function FormatBadge({ format }: { format: string | null | undefined }) {
  const f = format ?? "documentary";
  return (
    <span className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${FORMAT_TONE[f] ?? FORMAT_TONE.documentary}`}>
      {FORMATS.find((x) => x.key === f)?.short ?? f}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
        TONE[status] ?? "bg-zinc-500/10 text-zinc-400 ring-zinc-500/25"
      }`}
    >
      {status === "running" && <span className="size-1.5 animate-pulse rounded-full bg-sky-300" />}
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function Card({ title, action, children, className = "" }: {
  title?: string; action?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <section className={`rounded-xl border border-white/8 bg-zinc-900/60 p-5 ${className}`}>
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold text-zinc-200">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, tone = "default" }: {
  label: string; value: React.ReactNode; hint?: string; tone?: "default" | "warn" | "bad";
}) {
  const color = tone === "bad" ? "text-rose-300" : tone === "warn" ? "text-amber-300" : "text-zinc-50";
  return (
    <div className="rounded-xl border border-white/8 bg-zinc-900/60 p-4">
      <div className="text-xs text-zinc-400">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-zinc-500">{hint}</div>}
    </div>
  );
}

export function PageHeader({ title, description, children }: {
  title: string; description?: string; children?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-zinc-400">{description}</p>}
      </div>
      {children}
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border border-dashed border-white/10 p-6 text-center text-sm text-zinc-500">{children}</div>;
}

export const btn =
  "inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
export const btnPrimary = `${btn} bg-amber-500 text-zinc-950 hover:bg-amber-400`;
export const btnGhost = `${btn} text-zinc-300 ring-1 ring-inset ring-white/10 hover:bg-white/5`;
export const btnDanger = `${btn} text-rose-300 ring-1 ring-inset ring-rose-500/30 hover:bg-rose-500/10`;
export const input =
  "w-full rounded-md border border-white/10 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-amber-500/60 focus:outline-none focus:ring-2 focus:ring-amber-500/20";
