import "server-only";
import { HeadObjectCommand, PutObjectCommand, GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

// Cloudflare R2 (S3 uyumlu). Tarayıcı dosyayı imzalı URL ile DOĞRUDAN R2'ye yükler (Vercel'in 4,5 MB gövde sınırına takılmaz).
export function r2Configured() {
  return Boolean(process.env.R2_ACCESS_KEY_ID && process.env.R2_SECRET_ACCESS_KEY && process.env.R2_BUCKET &&
    (process.env.R2_ACCOUNT_ID || process.env.R2_ENDPOINT));
}

let client: S3Client | null = null;
function s3() {
  if (!client) {
    client = new S3Client({
      region: process.env.R2_REGION ?? "auto",
      endpoint: process.env.R2_ENDPOINT ?? `https://${process.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
      forcePathStyle: Boolean(process.env.R2_ENDPOINT),
      credentials: { accessKeyId: process.env.R2_ACCESS_KEY_ID!, secretAccessKey: process.env.R2_SECRET_ACCESS_KEY! },
    });
  }
  return client;
}
const bucket = () => process.env.R2_BUCKET!;

export const projectKey = (slug: string, ...parts: string[]) => ["projects", slug, ...parts].join("/");

export async function presignPut(key: string, contentType: string, expiresIn = 900) {
  return getSignedUrl(s3(), new PutObjectCommand({ Bucket: bucket(), Key: key, ContentType: contentType }), { expiresIn });
}

export async function presignGet(key: string, filename?: string, expiresIn = 3600) {
  return getSignedUrl(s3(), new GetObjectCommand({
    Bucket: bucket(), Key: key,
    ResponseContentDisposition: filename ? `attachment; filename="${filename}"` : undefined,
  }), { expiresIn });
}

export async function headObject(key: string) {
  try {
    const r = await s3().send(new HeadObjectCommand({ Bucket: bucket(), Key: key }));
    return { size: r.ContentLength ?? 0, contentType: r.ContentType ?? "" };
  } catch {
    return null;
  }
}
