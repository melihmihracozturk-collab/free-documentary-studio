import { Card, PageHeader } from "@/components/ui";
import { NewProjectForm } from "@/components/NewProjectForm";
import { getSettings } from "@/lib/queries";

export default async function NewDocumentary() {
  const settings = await getSettings();
  return (
    <>
      <PageHeader title="Yeni Proje"
                  description="Yalnızca konuyu girin. Araştırmadan render'a kadar 15 aşama bulutta sırayla yürütülür; sizden yalnızca araştırma onayı ve seslendirme dosyaları istenir." />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2"><NewProjectForm defaultMinutes={Number(settings.default_minutes ?? 11)} /></Card>
        <Card title="Sizden istenecekler">
          <ol className="list-decimal space-y-2 pl-4 text-sm text-zinc-400">
            <li>Araştırma raporunu inceleyip onaylamak.</li>
            <li><code className="text-zinc-300">documentary_voiceover.txt</code> ve <code className="text-zinc-300">shorts_voiceover.txt</code> metinlerini ElevenLabs&apos;te seslendirmek.</li>
            <li>MP3/WAV dosyalarını Seslendirme sayfasından yüklemek.</li>
          </ol>
          <p className="mt-4 text-xs text-zinc-500">Gerçek ses dosyaları yüklenmeden nihai render başlamaz.</p>
        </Card>
      </div>
    </>
  );
}
