"use client";

import { useActionState } from "react";
import { login, type FormState } from "@/app/actions";
import { btnPrimary, input } from "@/components/ui";

export function LoginForm({ next }: { next: string }) {
  const [state, action, pending] = useActionState<FormState, FormData>(login, undefined);
  return (
    <form action={action} className="space-y-4">
      <input type="hidden" name="next" value={next} />
      <label htmlFor="password" className="sr-only">Şifre</label>
      <input id="password" name="password" type="password" required autoFocus className={input} placeholder="Şifre" />
      {state?.error && <p role="alert" className="text-sm text-rose-300">{state.error}</p>}
      <button className={`${btnPrimary} w-full`} disabled={pending}>Giriş yap</button>
    </form>
  );
}
