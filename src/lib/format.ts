export function formatBytes(n: number) {
  if (!Number.isFinite(n) || n <= 0) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), u.length - 1);
  return `${(n / 1024 ** i).toLocaleString("tr-TR", { maximumFractionDigits: i >= 3 ? 2 : 0 })} ${u[i]}`;
}

const rtf = new Intl.RelativeTimeFormat("tr", { numeric: "auto" });

export function timeAgo(d: Date | string | null | undefined) {
  if (!d) return "—";
  const sec = Math.round((new Date(d).getTime() - Date.now()) / 1000);
  const abs = Math.abs(sec);
  if (abs < 60) return rtf.format(sec, "second");
  if (abs < 3600) return rtf.format(Math.round(sec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(sec / 3600), "hour");
  return rtf.format(Math.round(sec / 86400), "day");
}

export function formatDate(d: Date | string) {
  return new Date(d).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" });
}
