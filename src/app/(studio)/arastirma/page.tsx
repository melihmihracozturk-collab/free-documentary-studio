import { ModulePage, type ModuleConfig } from "@/components/ModulePage";

const config: ModuleConfig = {
  "title": "Araştırma",
  "description": "Konunun kaynaklı araştırması, iddiaların doğrulanması ve çelişkilerin raporlanması.",
  "stage": 3,
  "steps": [
    "research_collect",
    "research_verify",
    "research_report",
    "research_review"
  ],
  "planned": [
    "Wikimedia, Internet Archive, Europeana, Library of Congress, OpenAlex ve Crossref aramaları",
    "Her iddia için kaynak kaydı; iki bağımsız kaynakla doğrulama",
    "Kaynaklar arası çelişkilerin ayrı listesi",
    "Araştırma raporunu okuyup onaylama ekranı"
  ],
  "basePath": "/arastirma"
};

export default async function Page({ searchParams }: PageProps<"/arastirma">) {
  const { p } = await searchParams;
  return <ModulePage config={config} selected={typeof p === "string" ? p : undefined} />;
}
