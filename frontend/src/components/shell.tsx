"use client";
import { I18nProvider, useI18n, type Language } from "@/lib/i18n";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  FileText,
  House,
  Settings,
  Sparkles,
  Tickets,
  PanelRightOpen,
  X,
  ChevronRight,
} from "lucide-react";
import { AccessGate } from "@/components/access-gate";
import { ThemeProvider, applyAccent } from "@/lib/theme";
import { TaskQueue, TaskQueueProvider } from "@/components/task-queue";
import { api } from "@/lib/api";
import { SidebarAssistants } from "@/components/sidebar-assistants";

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      <ThemeProvider>
        <AccessGate>
          <TaskQueueProvider>
            <ShellContent>{children}</ShellContent>
          </TaskQueueProvider>
        </AccessGate>
      </ThemeProvider>
    </I18nProvider>
  );
}

function ShellContent({ children }: { children: React.ReactNode }) {
  const { t, setLanguage } = useI18n();
  const [name, setName] = useState("SpecHelper");
  const [shortLabel, setShortLabel] = useState("");
  const pathname = usePathname();
  const drawer = useRef<HTMLDialogElement>(null);
  const settingsVersion = useRef(0);
  useEffect(() => {
    drawer.current?.close();
  }, [pathname]);
  useEffect(() => {
    const update = () => {
      const version = ++settingsVersion.current;
      return api<{
        name: string;
        primary_color: string;
        short_label: string;
        language: Language;
      }>("/settings")
        .then((s) => {
          if (version !== settingsVersion.current) return;
          setName(s.name);
          setShortLabel(s.short_label || "");
          setLanguage(s.language === "en" ? "en" : "fr");
          applyAccent(s.primary_color);
        })
        .catch(() => {});
    };
    update();
    const timer = window.setInterval(update, 15000);
    window.addEventListener("settings-updated", update);
    return () => {
      settingsVersion.current += 1;
      window.clearInterval(timer);
      window.removeEventListener("settings-updated", update);
    };
  }, []);
  return (
    <div className="dashboard">
      <aside
        className="dashboard-sidebar"
        aria-label={t("Instance navigation")}
      >
        <Link href="/" aria-label={name} className="instance-brand">
          <span className="rounded-lg bg-primary p-2 text-primary-foreground">
            <Sparkles size={21} />
          </span>
          <span className="instance-name">
            {name}
            {shortLabel && <small>{shortLabel}</small>}
          </span>
        </Link>
        <nav aria-label={t("Main navigation")} className="dashboard-nav">
          {[
            {
              href: "/",
              label: "Home",
              icon: House,
              active: pathname === "/",
            },
            {
              href: "/analyses",
              label: "Analyses",
              icon: FileText,
              active: ["/analyses", "/questions", "/requests"].some((path) => pathname.startsWith(path)),
            },
            {
              href: "/tickets",
              label: "Tickets",
              icon: Tickets,
              active: pathname.startsWith("/tickets"),
            },
          ].map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={item.active ? "page" : undefined}
            >
              <item.icon size={18} />
              <span>{t(item.label)}</span>
            </Link>
          ))}
        </nav>
        <SidebarAssistants />
        <Link
          href="/admin"
          className="sidebar-admin"
          aria-label={t("Settings")}
          title={t("Settings")}
          aria-current={pathname.startsWith("/admin") ? "page" : undefined}
        >
          <span className="admin-avatar">
            <Settings size={18} />
          </span>
          <span>
            {t("Settings")}
            <small>{t("Administration")}</small>
          </span>
          <ChevronRight size={14} />
        </Link>
      </aside>
      <div className="dashboard-center">
        <div className="queue-toolbar">
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm"
            onClick={() => drawer.current?.showModal()}
          >
            <PanelRightOpen size={18} />
            {t("Task queue")}
          </button>
        </div>
        <main className="min-w-0">{children}</main>
        <footer className="mt-10 text-xs muted">
          {t("SpecHelper · A clear need, a well-prepared change.")}
        </footer>
      </div>
      <aside className="dashboard-queue" aria-label={t("Task queue")}>
        <TaskQueue />
      </aside>
      <dialog
        ref={drawer}
        className="queue-drawer"
        aria-label={t("Task queue")}
        onClick={(e) => {
          if (
            e.target === e.currentTarget ||
            (e.target instanceof Element && e.target.closest("a"))
          )
            drawer.current?.close();
        }}
      >
        <button
          type="button"
          className="mb-5 inline-flex items-center gap-2 rounded border px-3 py-2"
          onClick={() => drawer.current?.close()}
        >
          <X size={18} />
          {t("Close")}
        </button>
        <TaskQueue />
      </dialog>
    </div>
  );
}
