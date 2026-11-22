export const NAV = [
  { href: "/", label: "Dashboard", icon: "LayoutDashboard" },
  { href: "/yeni", label: "Yeni Proje", icon: "PlusCircle" },
  { href: "/arastirma", label: "Araştırma", icon: "Search" },
  { href: "/senaryo", label: "Senaryo", icon: "ScrollText" },
  { href: "/gorseller", label: "Görsel Arşivi", icon: "Images" },
  { href: "/seslendirme", label: "Seslendirme", icon: "Mic" },
  { href: "/belgesel", label: "Ana Belgesel", icon: "Film" },
  { href: "/shorts", label: "Shorts", icon: "Smartphone" },
  { href: "/render", label: "Render Merkezi", icon: "Cpu" },
  { href: "/projeler", label: "Proje Arşivi", icon: "Archive" },
  { href: "/ayarlar", label: "Ayarlar", icon: "Settings" },
] as const;

/** Proje biçimleri: panelde ayrı sekme ve renkli etiketle gösterilir. */
export const FORMATS = [
  { key: "documentary", label: "Belgesel", short: "Belgesel" },
  { key: "vlog", label: "Gezi vlogu", short: "Vlog" },
  { key: "review", label: "Anime / dizi / film önerisi", short: "Öneri · Ayla" },
] as const;
export type FormatKey = (typeof FORMATS)[number]["key"];

export const STATUS_LABEL: Record<string, string> = {
  pending: "Sırada",
  queued: "Sırada",
  running: "Çalışıyor",
  waiting_input: "Sizi bekliyor",
  done: "Tamamlandı",
  failed: "Hata",
  skipped: "Atlandı",
  cancelled: "İptal",
  active: "Aktif",
  rendering: "Render",
  archived: "Arşivde",
};
