// Ortam değişkenleri. Gizli değerler yalnızca sunucuda okunur; arayüze sadece "tanımlı mı" bilgisi gider.
export const env = {
  databaseUrl: process.env.DATABASE_URL ?? "",
  adminPassword: process.env.ADMIN_PASSWORD ?? "",
  sessionSecret: process.env.SESSION_SECRET ?? "",
  githubToken: process.env.GITHUB_DISPATCH_TOKEN ?? "",
  githubRepo: process.env.GITHUB_REPO ?? "", // "kullanici/repo"
  githubWorkflow: process.env.GITHUB_WORKFLOW_FILE ?? "worker.yml",
  isProd: process.env.NODE_ENV === "production",
};

/** Ayarlar sayfasında gösterilen servis yapılandırma durumu (değerler asla gösterilmez). */
export function serviceStatus() {
  const has = (k: string) => Boolean(process.env[k]);
  return [
    { key: "DATABASE_URL", label: "Supabase Postgres bağlantısı", ok: has("DATABASE_URL"), stage: 2 },
    { key: "ADMIN_PASSWORD", label: "Panel şifresi", ok: has("ADMIN_PASSWORD"), stage: 2 },
    { key: "SESSION_SECRET", label: "Oturum imzalama anahtarı", ok: has("SESSION_SECRET"), stage: 2 },
    { key: "GITHUB_DISPATCH_TOKEN", label: "GitHub Actions tetikleme token'ı", ok: has("GITHUB_DISPATCH_TOKEN"), stage: 2 },
    { key: "GITHUB_REPO", label: "GitHub repo adı", ok: has("GITHUB_REPO"), stage: 2 },
    { key: "R2_ACCOUNT_ID", label: "Cloudflare R2 hesabı", ok: has("R2_ACCOUNT_ID"), stage: 4 },
    { key: "R2_ACCESS_KEY_ID", label: "Cloudflare R2 erişim anahtarı", ok: has("R2_ACCESS_KEY_ID"), stage: 4 },
    { key: "R2_SECRET_ACCESS_KEY", label: "Cloudflare R2 gizli anahtar", ok: has("R2_SECRET_ACCESS_KEY"), stage: 4 },
    { key: "R2_BUCKET", label: "Cloudflare R2 bucket adı", ok: has("R2_BUCKET"), stage: 4 },
  ];
}
