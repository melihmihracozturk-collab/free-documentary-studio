import { ModulePage, type ModuleConfig } from "@/components/ModulePage";

const config: ModuleConfig = {
  "title": "Senaryo",
  "description": "8–15 dakikalık belgesel ve 45–60 saniyelik Shorts senaryoları, sahne sahne.",
  "stage": 3,
  "steps": [
    "script_doc",
    "script_shorts"
  ],
  "planned": [
    "Giriş, arka plan, gelişme, dönüm noktası, sonuçlar ve kapanış yapısı",
    "Her sahne: numara, süre, seslendirme, görsel, kamera, geçiş, müzik, ses efekti",
    "Shorts için ilk 3 saniyede güçlü kanca",
    "Senaryoyu düzenleyip yeni sürüm kaydetme"
  ],
  "basePath": "/senaryo"
};

export default async function Page({ searchParams }: PageProps<"/senaryo">) {
  const { p } = await searchParams;
  return <ModulePage config={config} selected={typeof p === "string" ? p : undefined} />;
}
