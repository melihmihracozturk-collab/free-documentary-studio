import Link from "next/link";
import { Suspense } from "react";
import { connection } from "next/server";
import { Clapperboard, LogOut } from "lucide-react";
import { Sidebar } from "@/components/Sidebar";
import { authDisabled } from "@/lib/auth";
import { env } from "@/lib/env";
import { logout } from "@/app/actions";

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-white/8 bg-zinc-950 p-4 md:flex">
        <Link href="/" className="mb-6 flex items-center gap-2.5 px-2">
          <span className="grid size-8 place-items-center rounded-md bg-amber-500 text-zinc-950">
            <Clapperboard size={18} strokeWidth={2} />
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-semibold text-zinc-50">Free Documentary</span>
            <span className="block text-xs text-zinc-500">Studio</span>
          </span>
        </Link>
        <Suspense fallback={<div className="h-96" />}><Sidebar /></Suspense>
        <div className="mt-auto space-y-2 px-2 text-xs text-zinc-500">
          <form action={logout}>
            <button className="flex items-center gap-2 hover:text-zinc-300"><LogOut size={14} /> Çıkış</button>
          </form>
          <p>Stage 2 · altyapı</p>
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <Suspense fallback={null}><EnvBanner /></Suspense>
        <main className="mx-auto max-w-6xl px-6 py-8">
          <Suspense fallback={<div className="animate-pulse text-sm text-zinc-500">Yükleniyor…</div>}>{children}</Suspense>
        </main>
      </div>
    </div>
  );
}

/** Çalışma anında okunur (derleme anında değil): eksik yapılandırma uyarısı. */
async function EnvBanner() {
  await connection();
  const noAuth = authDisabled();
  if (!noAuth && env.databaseUrl) return null;
  return (
    <div className="border-b border-amber-500/20 bg-amber-500/10 px-6 py-2 text-xs text-amber-200">
      {!env.databaseUrl
        ? "DATABASE_URL tanımlı değil: panel veritabanına bağlanamaz. Ayarlar sayfasındaki kurulum adımlarına bakın."
        : "Yerel geliştirme modu: ADMIN_PASSWORD tanımlı olmadığı için giriş kapalı. Yayına alırken mutlaka tanımlayın."}
    </div>
  );
}
