"use client";

import { useActionState, useState } from "react";
import { createProject, type FormState } from "@/app/actions";
import { btnPrimary, input } from "./ui";

export function NewProjectForm({ defaultMinutes }: { defaultMinutes: number }) {
  const [state, action, pending] = useActionState<FormState, FormData>(createProject, undefined);
  const [minutes, setMinutes] = useState(defaultMinutes);
  const [format, setFormat] = useState<"documentary" | "vlog" | "review">("documentary");
  const vlog = format === "vlog";
  const review = format === "review";
  return (
    <form action={action} className="space-y-5">
      <fieldset>
        <legend className="mb-1.5 block text-sm text-zinc-300">Biçim</legend>
        <div className="grid gap-2 sm:grid-cols-3">
          {([["documentary", "Belgesel", "Sinematik anlatım, tarihsel olay örgüsü"],
             ["vlog", "Gezi vlogu", "Birinci ağızdan, durak durak; pratik ipuçlarıyla"],
             ["review", "Anime / dizi / film önerisi", "Animasyonlu kadın sunucu anlatır; spoiler'sız"]] as const).map(([v, label, hint]) => (
            <label key={v} className={`cursor-pointer rounded-lg border p-3 text-sm ${format === v ? "border-amber-500/60 bg-amber-500/10" : "border-white/10 bg-zinc-950/40"}`}>
              <input type="radio" name="format" value={v} checked={format === v} onChange={() => setFormat(v)} className="sr-only" />
              <span className="block font-medium text-zinc-100">{label}</span>
              <span className="block text-xs text-zinc-500">{hint}</span>
            </label>
          ))}
        </div>
      </fieldset>
      {review && (
        <div className="flex items-center gap-4 rounded-lg border border-violet-400/20 bg-violet-500/5 p-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/sunucu.svg" alt="Sunucu karakter Ayla" width={96} height={125} className="h-32 w-auto" />
          <p className="text-xs text-zinc-400">
            <span className="block text-sm font-medium text-zinc-100">Sunucu: Ayla</span>
            Kodla çizilmiş 2D anime tarzı ninja: kızıl gözler, pençe izli alın plakası, kırmızı atkı ve sırtında kılıç. Videoda göz kırpar, nefes alır, başını sallar ve ağzı sese göre
            hareket eder. Giriş/kapanışta büyük, yapım kartlarında köşede görünür; tam ekran afiş sahnelerinde çekilir.
          </p>
        </div>
      )}
      <div>
        <label htmlFor="topic" className="mb-1.5 block text-sm text-zinc-300">Konu</label>
        <input id="topic" name="topic" required minLength={3} maxLength={200} className={input}
               placeholder={review ? "Bleach (ya da: Bu kış izlenecek 3 fantastik anime)" : vlog ? "Roma Gezisi — Kolezyum'dan Vatikan'a" : "Pompei'nin Son Günü — Vezüv'ün Yok Ettiği Şehir"} />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor="language" className="mb-1.5 block text-sm text-zinc-300">Dil</label>
          <select id="language" name="language" className={input} defaultValue="tr">
            <option value="tr">Türkçe</option>
            <option value="en">English</option>
          </select>
        </div>
        {review ? (
          <div>
            <span className="mb-1.5 block text-sm text-zinc-300">Süre</span>
            <p className="text-sm text-violet-300">≈1 dakikalık Shorts (1080×1920)</p>
            <input type="hidden" name="target_minutes" value={8} />
          </div>
        ) : (
          <div>
            <label htmlFor="target_minutes" className="mb-1.5 block text-sm text-zinc-300">
              Süre: <span className="tabular-nums text-amber-300">{minutes} dakika</span>
            </label>
            <input id="target_minutes" name="target_minutes" type="range" min={8} max={15} step={1}
                   value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}
                   className="w-full accent-amber-500" />
            <div className="flex justify-between text-xs text-zinc-500"><span>8</span><span>15</span></div>
          </div>
        )}
      </div>
      <div>
        <label htmlFor="style" className="mb-1.5 block text-sm text-zinc-300">Anlatım</label>
        <input id="style" name="style" required className={input} key={format}
               defaultValue={review ? "Enerjik ve samimi öneri videosu" : vlog ? "Samimi gezi vlogu" : "Sinematik kısa belgesel"} />
      </div>
      <p className="text-xs text-zinc-500">
        {!review && "Aynı konudan 45–60 saniyelik bağımsız bir Shorts da üretilecek. Ana video 1920×1080 25 fps, Shorts 1080×1920 30 fps."}
        {review && "Uzun video üretilmez; yalnızca ≈1 dakikalık dikey Shorts (en fazla 3 yapım). Shorts'u kodla çizilmiş kadın sunucu (Ayla) anlatır: sesi ücretsiz otomatik seslendirmeyle üretilir, ağzı sese göre hareket eder. Yapım bilgileri AniList/TMDB/Vikipedi'den, görseller resmî afişler ve hareketli grafiklerdir."}
        {vlog && " Vlogda görüntüler açık lisanslı arşiv fotoğraflarıdır; fiyat/saat gibi pratik bilgiler senaryoda “kontrol edilmeli” diye işaretlenir."}
      </p>
      {state?.error && <p role="alert" className="text-sm text-rose-300">{state.error}</p>}
      <button className={btnPrimary} disabled={pending}>{pending ? "Oluşturuluyor…" : review ? "Öneri Shorts'unu başlat" : vlog ? "Vlogu başlat" : "Belgeseli başlat"}</button>
    </form>
  );
}
