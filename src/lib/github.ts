import "server-only";
import { env } from "./env";

export type DispatchResult = { dispatched: boolean; reason?: string };

/**
 * GitHub Actions işçisini hemen tetikler. Token yoksa sorun değil:
 * cron (15 dk) kuyruğu zaten tarar; bu yalnızca beklemeyi kısaltır.
 */
export async function dispatchWorker(reason: string): Promise<DispatchResult> {
  if (!env.githubToken || !env.githubRepo) {
    return { dispatched: false, reason: "GitHub tetikleme yapılandırılmadı; işçi en geç 15 dk içinde cron ile başlar." };
  }
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
