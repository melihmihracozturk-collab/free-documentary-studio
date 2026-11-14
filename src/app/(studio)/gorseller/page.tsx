import { ModulePage, type ModuleConfig } from "@/components/ModulePage";

const config: ModuleConfig = {
  "title": "Görsel Arşivi",
  "description": "Sahnelere uygun, lisansı doğrulanmış arşiv görselleri ve 2D grafikler.",
  "stage": 5,
  "steps": [
    "visual_plan",
    "asset_match"
  ],
  "planned": [
    "Wikimedia Commons, Openverse, Met Museum, Smithsonian, Europeana ve LoC araması",
    "Lisans filtresi: PD, CC0, CC BY (ve işaretli CC BY-SA); NC varsayılan kapalı",
    "Her görselin kaynak, lisans ve atıf kaydı; otomatik credits.txt",
    "Sahneye görsel atama ve değiştirme"
  ],
  "basePath": "/gorseller"
};

export default async function Page({ searchParams }: PageProps<"/gorseller">) {
  const { p } = await searchParams;
  return <ModulePage config={config} selected={typeof p === "string" ? p : undefined} />;
}
