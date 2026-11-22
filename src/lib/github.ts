import "server-only";
import { env } from "./env";
import { db } from "./db";

export type DispatchResult = { dispatched: boolean; reason?: string };

const RETRY_DELAYS_MS = [0, 1500, 4000];

async function tryDispatch(reason: string): Promise<DispatchResult> {
  try {
    const res = await fetch(
      `https://api.github.com/repos/${env.githubRepo}/actions/workflows/${env.githubWorkflow}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.githubToken}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({ ref: "main", inputs: { reason: reason.slice(0, 100) } }),
        cache: "no-store",
      },
    );
    if (res.status === 204) return { dispatched: true };
    return { dispatched: false, reason: `GitHub yanıtı ${res.status}` };
  } catch (e) {
    return { dispatched: false, reason: `GitHub'a ulaşılamadı: ${(e as Error).message}` };
  }
}

/**
 * GitHub Actions işçisini hemen tetikler. Geçici hatalarda (ağ, 5xx, yeniden yayın sırasında) 3 kez dener.
 * Yine başaramazsa Dashboard'daki uyarılara yazar; işçi zamanlanmış çalışmayla (cron) kuyruğu yine de tarar.
 */
export async function dispatchWorker(reason: string): Promise<DispatchResult> {
  if (!env.githubToken || !env.githubRepo) {
    return { dispatched: false, reason: "GitHub tetikleme yapılandırılmadı; işçi zamanlanmış çalışmayla (cron) başlar." };
  }
  let last: DispatchResult = { dispatched: false };
  for (const delay of RETRY_DELAYS_MS) {
    if (delay) await new Promise((r) => setTimeout(r, delay));
    last = await tryDispatch(reason);
    if (last.dispatched) return last;
    if (/yanıtı (401|403|404|422)/.test(last.reason ?? "")) break;      // yetki/ayar hatası: tekrar denemek işe yaramaz
  }
  try {
    await db()`insert into error_logs (level, message)
               values ('warning', ${`İşçi otomatik başlatılamadı (${reason}): ${last.reason}. Zamanlanmış çalışmada sürecek.`})`;
  } catch {
    // günlük yazılamazsa yalnızca bilgi kaybolur; proje yine kuyrukta
  }
  return last;
}
