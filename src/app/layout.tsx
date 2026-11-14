import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Free Documentary Studio",
  description: "Tek konu girişiyle belgesel ve Shorts üreten web tabanlı stüdyo",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body className="min-h-dvh font-sans antialiased">{children}</body>
    </html>
  );
}
