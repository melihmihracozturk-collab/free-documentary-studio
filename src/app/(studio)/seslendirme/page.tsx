import { ModulePage, type ModuleConfig } from "@/components/ModulePage";
import { VoiceoverView } from "@/components/VoiceoverView";

const config: ModuleConfig = {
  "title": "Seslendirme",
  "description": "ElevenLabs için metinler ve sizin yüklediğiniz ses dosyalarının analizi.",
  "stage": 4,
  "active": true,
  "steps": [
    "script_review",
    "voiceover_texts",
    "voiceover_wait",
    "voiceover_analyze"
  ],
  "planned": [
    "documentary_voiceover.txt ve shorts_voiceover.txt indirme",
    "MP3/WAV dosyalarını doğrudan Cloudflare R2'ye yükleme",
    "Süre, duraklamalar ve kelime zamanları (faster-whisper)",
    "Sahne zamanlamalarını gerçek sese göre çıkarma"
  ],
  "basePath": "/seslendirme"
};

export default async function Page({ searchParams }: PageProps<"/seslendirme">) {
  const { p } = await searchParams;
  return (
    <ModulePage config={config} selected={typeof p === "string" ? p : undefined}
                render={async (proj) => <VoiceoverView projectId={proj.id} slug={proj.slug} />} />
  );
}
