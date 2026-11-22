import { Card, Empty, Stat } from "./ui";
import { getClaimsText, getScripts, getStepState, type Scene, type Script } from "@/lib/queries";
import { SceneEditor } from "./SceneEditor";
import { needsCheck, practicalRefs } from "@/lib/practical";

const ACT_TR: Record<string, string> = {
  giris: "Çarpıcı giriş", arka_plan: "Tarihsel arka plan", gelisme: "Olayların gelişimi",
  donum_noktasi: "Kritik dönüm noktası", sonuclar: "Sonuçlar", kapanis: "Güçlü kapanış", shorts: "Shorts",
};
const CAM_TR: Record<string, string> = {
  zoom_in: "Yaklaşma", zoom_out: "Uzaklaşma", pan_left: "Sola pan", pan_right: "Sağa pan", pan_up: "Yukarı pan",
  pan_down: "Aşağı pan", parallax: "Parallax", ken_burns: "Ken Burns", static: "Sabit",
};
const TR_TR: Record<string, string> = {
  cut: "Kesme", crossfade: "Çapraz geçiş", fade_black: "Siyaha geçiş", dip_white: "Beyaza geçiş", wipe: "Silme", slide: "Kaydırma",
};

function fmtSec(sec: number) {
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function SceneTable({ scenes, actTitles }: { scenes: Scene[]; actTitles?: Record<string, string> }) {
  const starts = scenes.map((_, i) => scenes.slice(0, i).reduce((a, x) => a + Number(x.est_duration_sec ?? 0), 0));
  return (
    <ol className="space-y-2">
      {scenes.map((s, i) => {
        const start = starts[i];
        const header = s.act !== "shorts" && s.act !== scenes[i - 1]?.act ? s.act : null;
        return (
          <li key={s.id}>
            {header && <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-amber-300/80">{actTitles?.[header] ?? ACT_TR[header] ?? header}</h3>}
            <div className="grid gap-3 rounded-lg border border-white/5 bg-zinc-950/40 p-3 md:grid-cols-[5.5rem_1fr_16rem]">
              <div className="text-xs text-zinc-500">
                <div className="font-mono text-sm text-zinc-300">#{s.idx}</div>
                <div className="tabular-nums">{fmtSec(start)} · {Number(s.est_duration_sec).toFixed(0)} sn</div>
                <div>{s.word_count} kelime</div>
              </div>
              <div className="min-w-0">
                <p className="text-sm leading-relaxed text-zinc-100">{s.voiceover_text}</p>
                {s.claim_refs.length > 0 && <p className="mt-1 font-mono text-xs text-zinc-500">{s.claim_refs.join(" ")}</p>}
              </div>
              <dl className="space-y-1 text-xs">
                <div><dt className="inline text-zinc-500">Görsel: </dt><dd className="inline text-zinc-300">{s.visual_description}</dd></div>
                {s.on_screen_text && <div><dt className="inline text-zinc-500">Ekran yazısı: </dt><dd className="inline text-zinc-300">{s.on_screen_text}</dd></div>}
                <div><dt className="inline text-zinc-500">Kamera: </dt><dd className="inline text-zinc-300">{CAM_TR[s.camera_move ?? ""] ?? s.camera_move}</dd>
                  <dt className="ml-2 inline text-zinc-500">Geçiş: </dt><dd className="inline text-zinc-300">{TR_TR[s.transition ?? ""] ?? s.transition}</dd></div>
                <div><dt className="inline text-zinc-500">Müzik: </dt><dd className="inline text-zinc-300">{s.music}</dd></div>
                <div><dt className="inline text-zinc-500">Efekt: </dt><dd className="inline text-zinc-300">{s.sfx}</dd></div>
                <div className="text-zinc-500">Arama: {s.search_keywords.join(", ")}</div>
              </dl>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function ScriptCard({ title, script, scenes, slug, claims, canApprove, showApprove, label }: {
  title: string; script: Script | null; scenes: Scene[]; slug: string; claims: string; canApprove: boolean; showApprove: boolean;
  label: string;
}) {
  if (!script) return <Card title={title}><Empty>Henüz yazılmadı.</Empty></Card>;
  const errs = script.validation.errors ?? [];
  return (
    <Card title={`${title} · ${script.content.title ?? ""} · sürüm ${script.version}`}
          action={<a className="text-xs text-amber-300 hover:underline" href={`/api/projects/${slug}/script/${script.kind}`}>İndir (.md)</a>}>
      {script.content.logline && <p className="mb-3 text-sm italic text-zinc-400">{script.content.logline}</p>}
      {errs.length > 0 && (
        <div className="mb-3 rounded-md bg-amber-500/10 p-3 text-xs text-amber-200">
          <p className="font-medium">Otomatik kontrol uyarıları (düzeltme denemelerinden sonra kalanlar):</p>
          <ul className="mt-1 list-disc pl-4">{errs.slice(0, 8).map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      )}
      <SceneEditor slug={slug} claims={claims} approved={Boolean(script.approved_at)} canApprove={canApprove && showApprove}
                   actTitles={script.content.act_titles} label={label}
                   scenes={scenes.map((x) => ({ id: x.id, kind: x.kind, idx: x.idx, act: x.act, voiceover_text: x.voiceover_text,
                     claim_refs: x.claim_refs, visual_description: x.visual_description, word_count: x.word_count,
                     est_duration_sec: x.est_duration_sec, needs_check: x.needs_check }))} />
      <details className="mt-4">
        <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-300">Kamera, geçiş, müzik ve efekt planı</summary>
        <div className="mt-2"><SceneTable scenes={scenes} actTitles={script.content.act_titles} /></div>
      </details>
    </Card>
  );
}

export async function ScriptView({ projectId, slug }: { projectId: string; slug: string }) {
  const [{ doc, shorts, docScenes, shortsScenes }, claims, review] = await Promise.all([
    getScripts(projectId), getClaimsText(projectId), getStepState(projectId, "script_review")]);
  const canApprove = review?.status === "waiting_input";
  const label = doc?.content.format === "vlog" ? "Vlog" : doc?.content.format === "review" ? "Öneri videosu" : "Belgesel";
  const refs = practicalRefs(claims);
  const checks = [...docScenes, ...shortsScenes].filter((s) => needsCheck(s, refs)).length;
  if (!doc && !shorts) {
    return <Card title="Senaryo"><Empty>Senaryo henüz yazılmadı. Araştırma onaylandıktan sonra bulut işçisi yazacak.</Empty></Card>;
  }
  return (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={`${label} sahnesi`} value={docScenes.length} />
        <Stat label={`Tahmini ${label.toLowerCase()} süresi`} value={doc?.est_seconds ? fmtSec(Number(doc.est_seconds)) : "—"} hint={`${doc?.word_count ?? 0} kelime · gerçek süre sesten ölçülecek`} />
        <Stat label="Shorts sahnesi" value={shortsScenes.length} />
        <Stat label="Tahmini Shorts süresi" value={shorts?.est_seconds ? `${Math.round(Number(shorts.est_seconds))} sn` : "—"} hint={`${shorts?.word_count ?? 0} kelime`} />
      </div>
      {review?.status === "waiting_input" && (
        <p className="rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">
          Senaryo onayınızı bekliyor. Sahneleri okuyun, gerekirse düzenleyin, sonra onaylayın. ElevenLabs metinleri onaylı hâlden üretilir.
        </p>
      )}
      {checks > 0 && (
        <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
          {checks} sahnede fiyat, saat veya ulaşım bilgisi var. Bu bilgiler değişebilir; seslendirmeden önce resmî
          sitelerden kontrol edin ve gerekirse metni düzenleyin.
        </p>
      )}
      <ScriptCard title={`Ana ${label.toLowerCase()}`} script={doc} scenes={docScenes} slug={slug} claims={claims} canApprove={canApprove} showApprove label={label} />
      <ScriptCard title="Shorts" script={shorts} scenes={shortsScenes} slug={slug} claims={claims} canApprove={canApprove} showApprove={false} label={label} />
    </>
  );
}
