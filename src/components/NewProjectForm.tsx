"use client";

import { useActionState, useState } from "react";
import { createProject, type FormState } from "@/app/actions";
import { btnPrimary, input } from "./ui";

export function NewProjectForm({ defaultMinutes }: { defaultMinutes: number }) {
  const [state, action, pending] = useActionState<FormState, FormData>(createProject, undefined);
  const [minutes, setMinutes] = useState(defaultMinutes);
  const [format, setFormat] = useState<"documentary" | "vlog">("documentary");
  const vlog = format === "vlog";
  return (
    <form action={action} className="space-y-5">
      <fieldset>
        <legend className="mb-1.5 block text-sm text-zinc-300">Biçim</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {([["documentary", "Belgesel", "Sinematik anlatım, tarihsel olay örgüsü"],
             ["vlog", "Gezi vlogu", "Birinci ağızdan, durak durak; pratik ipuçlarıyla"]] as const).map(([v, label, hint]) => (
            <label key={v} className={`cursor-pointer rounded-lg border p-3 text-sm ${format === v ? "border-amber-500/60 bg-amber-500/10" : "border-white/10 bg-zinc-950/40"}`}>
              <input type="radio" name="format" value={v} checked={format === v} onChange={() => setFormat(v)} className="sr-only" />
              <span className="block font-medium text-zinc-100">{label}</span>
              <span className="block text-xs text-zinc-500">{hint}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div>
        <label htmlFor="topic" className="mb-1.5 block text-sm text-zinc-300">Konu</label>
        <input id="topic" name="topic" required minLength={3} maxLength={200} className={input}
               placeholder={vlog ? "Roma Gezisi — Kolezyum'dan Vatikan'a" : "Pompei'nin Son Günü — Vezüv'ün Yok Ettiği Şehir"} />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor="language" className="mb-1.5 block text-sm text-zinc-300">Dil</label>
          <select id="language" name="language" className={input} defaultValue="tr">
            <option value="tr">Türkçe</option>
            <option value="en">English</option>
          </select>
        </div>
        <div>
          <label htmlFor="target_minutes" className="mb-1.5 block text-sm text-zinc-300">
            Süre: <span className="tabular-nums text-amber-300">{minutes} dakika</span>
          </label>
          <input id="target_minutes" name="target_minutes" type="range" min={8} max={15} step={1}
                 value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}
                 className="w-full accent-amber-500" />
          <div className="flex justify-between text-xs text-zinc-500"><span>8</span><span>15</span></div>
        </div>
      </div>
      <div>
        <label htmlFor="style" className="mb-1.5 block text-sm text-zinc-300">Anlatım</label>
        <input id="style" name="style" required className={input} key={format}
               defaultValue={vlog ? "Samimi gezi vlogu" : "Sinematik kısa belgesel"} />
      </div>
      <p className="text-xs text-zinc-500">
        Aynı konudan 45–60 saniyelik bağımsız bir Shorts da üretilecek. Ana video 1920×1080 25 fps, Shorts 1080×1920 30 fps.
        {vlog && " Vlogda görüntüler açık lisanslı arşiv fotoğraflarıdır; fiyat/saat gibi pratik bilgiler senaryoda “kontrol edilmeli” diye işaretlenir."}
      </p>
      {state?.error && <p role="alert" className="text-sm text-rose-300">{state.error}</p>}
      <button className={btnPrimary} disabled={pending}>{pending ? "Oluşturuluyor…" : vlog ? "Vlogu başlat" : "Belgeseli başlat"}</button>
    </form>
  );
}
