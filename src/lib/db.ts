import "server-only";
import postgres from "postgres";
import { env } from "./env";

declare global {
  var __fdsSql: ReturnType<typeof postgres> | undefined;
}

/** Tek bağlantı havuzu. prepare:false → Supabase havuzlayıcısı (transaction mode) ile uyumlu. */
export function db() {
  if (!env.databaseUrl) throw new Error("DATABASE_URL tanımlı değil");
  if (!globalThis.__fdsSql) {
    globalThis.__fdsSql = postgres(env.databaseUrl, {
      prepare: false,
      max: 5,
      idle_timeout: 20,
      onnotice: () => {},
    });
  }
  return globalThis.__fdsSql;
}
