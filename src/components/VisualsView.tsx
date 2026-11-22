import { Card, Empty, Stat } from "./ui";
import { VisualPicker } from "./VisualPicker";
import { getStepState, getVisuals } from "@/lib/queries";
import { isRestricted } from "@/lib/licenses";

export async function VisualsView({ projectId, slug }: { projectId: string; slug: string }) {
  const [{ scenes, assets }, review] = await Promise.all([getVisuals(projectId), getStepState(projectId, "visual_review")]);
  if (!assets.length) {
    return <Card title="Görseller"><Empty>Görsel eşleştirme henüz çalışmadı. Seslendirme analizinden sonra bulut işçisi arşivlerde arayacak.</Empty></Card>;
  }
  const chosen = assets.filter((a) => scenes.some((s) => s.asset_id === a.id));
  const count = (f: (a: (typeof assets)[number]) => boolean) => chosen.filter(f).length;
  return (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Görseli olan sahne" value={`${scenes.filter((s) => s.asset_id).length}/${scenes.length}`} />
        <Stat label="Kamu malı / CC0" value={count((a) => a.license_class === "pd" || a.license_class === "cc0")} hint="atıf gerekmez" />
        <Stat label="Atıf gerektiren" value={count((a) => ["by", "by-sa", "nc"].includes(a.license_class ?? ""))} hint="credits.txt'de listelenir" />
        <Stat label="Düşük çözünürlük" value={count((a) => (a.width ?? 9999) < 1600)} tone={count((a) => (a.width ?? 9999) < 1600) ? "warn" : "default"} hint="< 1600 px genişlik" />
      </div>
      {count((a) => isRestricted(a.license_class)) > 0 && (
        <p role="alert" className="rounded-lg border border-rose-500/50 bg-rose-500/10 p-3 text-sm text-rose-200">
          ⚠ {count((a) => isRestricted(a.license_class))} sahnede TELİFLİ (izinsiz) görsel var. Taslak için kullanılabilir;
          YouTube&apos;a yüklemeden önce bu sahnelerde “Görsel ara” ile açık lisanslı bir görsel seçin veya kendi görselinizi yükleyin.
        </p>
      )}
      {review?.status === "waiting_input" && (
        <p className="rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">
          Görseller onayınızı bekliyor. Her sahnede seçili görsele bakın, gerekirse alternatiflerden birini seçin, sonra onaylayın.
        </p>
      )}
      <Card>
        <VisualPicker slug={slug} scenes={scenes} assets={assets} approved={review?.status === "done"} canApprove={review?.status === "waiting_input"} />
      </Card>
      <p className="text-xs text-zinc-500">
        Lisans politikası: kamu malı, CC0, CC BY ve CC BY-SA kabul edilir; NC (ayarlardan açılmadıkça), ND ve lisansı belirsiz görseller elenir.
        Önizlemeler kaynak sitelerden gösterilir; seçilen görseller render için Cloudflare R2&apos;ye indirilir.
      </p>
    </>
  );
}
