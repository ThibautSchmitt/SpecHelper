"use client";
import { I18nProvider, useI18n, type Language } from "@/lib/i18n";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { FileText, Settings, Sparkles } from "lucide-react";
import { api } from "@/lib/api";

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      <ShellContent>{children}</ShellContent>
    </I18nProvider>
  );
}

function ShellContent({ children }: { children: React.ReactNode }) {
  const { t, setLanguage } = useI18n();
  const [name, setName] = useState("SpecHelper");
  const [shortLabel, setShortLabel] = useState("");
  const pathname = usePathname();
  useEffect(() => {
    const update = () =>
      api<{
        name: string;
        primary_color: string;
        short_label: string;
        language: Language;
      }>("/settings")
        .then((s) => {
          setName(s.name);
          setShortLabel(s.short_label || "");
          setLanguage(s.language === "en" ? "en" : "fr");
          document.documentElement.style.setProperty(
            "--primary",
            s.primary_color,
          );
          const rgb = s.primary_color
            .slice(1)
            .match(/.{2}/g)!
            .map((v) => parseInt(v, 16) / 255)
            .map((v) =>
              v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4,
            );
          const luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
          document.documentElement.style.setProperty(
            "--primary-ink",
            luminance > 0.179 ? "#172033" : s.primary_color,
          );
          document.documentElement.style.setProperty(
            "--primary-foreground",
            luminance > 0.179 ? "#172033" : "#ffffff",
          );
        })
        .catch(() => {});
    update();
    const timer = window.setInterval(update, 15000);
    window.addEventListener("settings-updated", update);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("settings-updated", update);
    };
  }, []);
  return (
    <>
      <header className="border-b bg-card">
        <div className="mx-auto flex min-h-18 max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4">
          <Link
            href="/"
            className="flex min-w-0 items-center gap-3 font-bold text-lg"
          >
            <span className="rounded-lg bg-primary p-2 text-primary-foreground">
              <Sparkles size={21} />
            </span>
            <span className="break-words">
              {name}
              {shortLabel && (
                <span className="mt-1 block text-xs font-normal muted">
                  {shortLabel}
                </span>
              )}
            </span>
          </Link>
          <nav aria-label={t("Main navigation")} className="flex gap-2 text-sm">
            <Link
              className={`flex items-center gap-2 rounded-md px-3 py-2 ${!pathname.startsWith("/admin") ? "bg-primary text-primary-foreground" : "muted"}`}
              href="/"
            >
              <FileText size={16} />
              {t("Requests")}
            </Link>
            <Link
              className={`flex items-center gap-2 rounded-md px-3 py-2 ${pathname.startsWith("/admin") ? "bg-primary text-primary-foreground" : "muted"}`}
              href="/admin"
            >
              <Settings size={16} />
              {t("Administration")}
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-5 py-9">{children}</main>
      <footer className="mx-auto max-w-6xl px-5 pb-8 text-xs muted">
        {t("SpecHelper · A clear need, a well-prepared change.")}
      </footer>
    </>
  );
}
