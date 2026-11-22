"use client";

import { useActionState } from "react";
import { saveSettings, type FormState } from "@/app/actions";
import { btnPrimary, input } from "./ui";

export function SettingsForm({ guardGb, allowNc, allowSa, allowRestricted, defaultMinutes }: {
  guardGb: number; allowNc: boolean; allowSa: boolean; allowRestricted: boolean; defaultMinutes: number;
}) {
  const [state, action, pending] = useActionState<FormState, FormData>(saveSettings, undefined);
  return (
    <form action={action} className="space-y-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label htmlFor="storage_guard_gb" className="mb-1.5 block text-sm text-zinc-300">Depolama koruma eşiği (GB)</label>
          <input id="storage_guard_gb" name="storage_guard_gb" type="number" min={0.5} max={10} step={0.5}
                 defaultValue={guardGb} className={input} />
          <p className="mt-1 text-xs text-zinc-500">R2 ücretsiz sınırı 10 GB. Eşik aşılınca yeni render başlamaz.</p>
        </div>
        <div>
          <label htmlFor="default_minutes" className="mb-1.5 block text-sm text-zinc-300">Varsayılan belgesel süresi (dk)</label>
          <input id="default_minutes" name="default_minutes" type="number" min={8} max={15} defaultValue={defaultMinutes} className={input} />
        </div>
      </div>
      <fieldset className="space-y-3">
        <legend className="mb-2 text-sm text-zinc-300">Görsel lisans politikası</legend>
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" name="license_allow_nc" defaultChecked={allowNc} className="mt-0.5 accent-amber-500" />
          <span><span className="text-zinc-200">NC (ticari olmayan) lisanslara izin ver</span>
            <span className="block text-xs text-zinc-500">Kanal para kazanmaya başlarsa bu görseller sorun olur. Önerilen: kapalı.</span></span>
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" name="license_allow_sa" defaultChecked={allowSa} className="mt-0.5 accent-amber-500" />
          <span><span className="text-zinc-200">CC BY-SA lisanslara izin ver</span>
            <span className="block text-xs text-zinc-500">Kullanılabilir; atıf zorunlu ve görsel üzerinde yapılan değişiklikler aynı lisansla paylaşılır.</span></span>
        </label>
        <label className="flex items-start gap-3 rounded-md border border-rose-500/30 bg-rose-500/5 p-2 text-sm">
          <input type="checkbox" name="license_allow_restricted" defaultChecked={allowRestricted} className="mt-0.5 accent-rose-500" />
          <span><span className="text-zinc-200">Telifli görselleri de öner (taslak modu)</span>
            <span className="block text-xs text-zinc-500">
              Lisansa bakmadan en ilgili görseller seçilir; araştırmadaki haber/kurum sayfalarının görselleri de havuza girer.
              Telifli olanlar kırmızı “TELİFLİ” etiketiyle işaretlenir. Yayından önce bunları değiştirmek sizin sorumluluğunuzdadır
              (aksi hâlde YouTube telif bildirimi gelebilir).
            </span></span>
        </label>
      </fieldset>
      {state?.error && <p role="alert" className="text-sm text-rose-300">{state.error}</p>}
      {state?.ok && <p role="status" className="text-sm text-emerald-300">{state.ok}</p>}
      <button className={btnPrimary} disabled={pending}>Kaydet</button>
    </form>
  );
}
