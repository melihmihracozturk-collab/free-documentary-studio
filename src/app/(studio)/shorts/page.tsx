import { ModulePage, type ModuleConfig } from "@/components/ModulePage";

const config: ModuleConfig = {
  "title": "Shorts",
  "description": "1080×1920, 30 fps, H.264 MP4. Ana belgeselden bağımsız kurgu.",
  "stage": 7,
  "steps": [
    "render_shorts"
  ],
  "planned": [
    "Dikey kompozisyon için yeniden kırpma",
    "Kelime kelime vurgulanan büyük altyazı",
    "Ana belgesele yönlendiren doğal kapanış"
  ],
  "basePath": "/shorts"
};

export default async function Page({ searchParams }: PageProps<"/shorts">) {
  const { p } = await searchParams;
  return <ModulePage config={config} selected={typeof p === "string" ? p : undefined} />;
}
