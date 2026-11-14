"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Archive, Cpu, Film, Images, LayoutDashboard, Mic, PlusCircle, ScrollText, Search, Settings, Smartphone,
} from "lucide-react";
import { NAV } from "@/lib/nav";

const ICONS = { Archive, Cpu, Film, Images, LayoutDashboard, Mic, PlusCircle, ScrollText, Search, Settings, Smartphone };

export function Sidebar() {
  const path = usePathname();
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Ana menü">
      {NAV.map((item) => {
        const Icon = ICONS[item.icon];
        const active = item.href === "/" ? path === "/" : path.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
              active ? "bg-amber-500/15 text-amber-300" : "text-zinc-400 hover:bg-white/5 hover:text-zinc-100"
            }`}
          >
            <Icon size={17} strokeWidth={1.75} aria-hidden />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
