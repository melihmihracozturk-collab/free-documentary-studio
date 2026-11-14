import { Suspense } from "react";
import { LoginForm } from "./LoginForm";

async function Form({ searchParams }: { searchParams: PageProps<"/login">["searchParams"] }) {
  const { next } = await searchParams;
  return <LoginForm next={typeof next === "string" ? next : "/"} />;
}

export default function LoginPage({ searchParams }: PageProps<"/login">) {
  return (
    <main className="grid min-h-dvh place-items-center p-6">
      <div className="w-full max-w-sm rounded-xl border border-white/8 bg-zinc-900/60 p-6">
        <h1 className="text-lg font-semibold text-zinc-50">Free Documentary Studio</h1>
        <p className="mb-5 mt-1 text-sm text-zinc-400">Devam etmek için panel şifresini girin.</p>
        <Suspense fallback={null}><Form searchParams={searchParams} /></Suspense>
      </div>
    </main>
  );
}
