// Paneldeki tarayıcı yüklemesini birebir taklit eder: imzalı PUT adresi (panelle aynı SDK/ayarlar),
// panel adresinden CORS ön isteği ve gerçek PUT. Gizli değer yazdırmaz.
import { DeleteObjectCommand, PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const e = (k) => (process.env[k] ?? "").trim();
const ORIGIN = e("TEST_ORIGIN") || "https://free-documentary-studio.vercel.app";
const s3 = new S3Client({
  region: e("R2_REGION") || "auto",
  endpoint: e("R2_ENDPOINT") || `https://${e("R2_ACCOUNT_ID")}.r2.cloudflarestorage.com`,
  forcePathStyle: Boolean(e("R2_ENDPOINT")),
  credentials: { accessKeyId: e("R2_ACCESS_KEY_ID"), secretAccessKey: e("R2_SECRET_ACCESS_KEY") },
});
const Key = `healthcheck/upload-test-${Date.now()}.mp3`;
const url = await getSignedUrl(s3, new PutObjectCommand({ Bucket: e("R2_BUCKET"), Key, ContentType: "audio/mpeg" }), { expiresIn: 300 });
const u = new URL(url);
console.log("imzalı adres sunucusu:", u.hostname.replace(/^[^.]+\.(?=[^.]+\.r2)/, "<bucket>.").replace(/[0-9a-f]{32}/, "<hesap>"));
console.log("imzalı parametreler:", [...u.searchParams.keys()].join(", "));

const pre = await fetch(url, { method: "OPTIONS", headers: { Origin: ORIGIN, "Access-Control-Request-Method": "PUT", "Access-Control-Request-Headers": "content-type" } });
console.log(`ön istek (OPTIONS): ${pre.status}; allow-origin=${pre.headers.get("access-control-allow-origin")}; allow-headers=${pre.headers.get("access-control-allow-headers")}; allow-methods=${pre.headers.get("access-control-allow-methods")}`);

const put = await fetch(url, { method: "PUT", headers: { Origin: ORIGIN, "Content-Type": "audio/mpeg" }, body: new Uint8Array([1, 2, 3]) });
const body = await put.text();
console.log(`yükleme (PUT): ${put.status}; allow-origin=${put.headers.get("access-control-allow-origin")}; yanıt=${body.replace(/<RequestId>.*?<\/RequestId>/g, "").slice(0, 300)}`);
if (put.ok) await s3.send(new DeleteObjectCommand({ Bucket: e("R2_BUCKET"), Key }));
