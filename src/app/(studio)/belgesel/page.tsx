import { ModulePage, type ModuleConfig } from "@/components/ModulePage";
import { RenderView } from "@/components/RenderView";

const config: ModuleConfig = {
  "title": "Ana Belgesel",
  "description": "1920×1080, 25 fps, H.264 MP4. Önizleme ve indirme.",
  "stage": 6,
  "active": true,
  "steps": [
    "subtitles",
    "render_doc",
    "preview_ready"
  ],
  "planned": [
    "Zoom, pan, parallax, sinematik geçişler, film grain ve renk düzenleme",
    "Gömülü altyazı ve ayrı SRT dosyası",
    "Müzik ve ses efekti miksajı, YouTube için ses seviyesi ayarı",
    "Tarayıcıda önizleme ve indirme"
  ],
  "basePath": "/belgesel"
};

export default async function Page({ searchParams }: PageProps<"/belgesel">) {
  const { p } = await searchParams;
  return (
    <ModulePage config={config} selected={typeof p === "string" ? p : undefined}
                render={async (proj) => <RenderView projectId={proj.id} slug={proj.slug} kind="doc" />} />
  );
}
