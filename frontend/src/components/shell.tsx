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
  Activity,
  LoaderCircle,
  X,
  ChevronRight,
} from "lucide-react";
import { AccessGate } from "@/components/access-gate";
import { ThemeProvider, applyAccent } from "@/lib/theme";
import { TaskQueue, TaskQueueProvider, useQueueAttention } from "@/components/task-queue";
import { api } from "@/lib/api";
import { SidebarAssistants } from "@/components/sidebar-assistants";
import { InstanceNameContext } from "@/lib/instance";

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
  const [queueCollapsed, setQueueCollapsed] = useState(true);
  const attention = useQueueAttention();
  useEffect(() => {
    try { setQueueCollapsed(localStorage.getItem("spechelper-queue-collapsed") !== "false"); } catch {}
  }, []);
  function toggleQueue() {
    setQueueCollapsed(value => {
      try { localStorage.setItem("spechelper-queue-collapsed", String(!value)); } catch {}
      return !value;
    });
  }
  useEffect(() => {
    if (drawer.current?.open) {
      drawer.current.close();
      setQueueCollapsed(true);
      try { localStorage.setItem("spechelper-queue-collapsed", "true"); } catch {}
    }
  }, [pathname]);
  useEffect(() => {
    const synchronize = () => {
      if (window.innerWidth < 1280 && !queueCollapsed) {
        if (!drawer.current?.open) drawer.current?.showModal();
      } else drawer.current?.close();
    };
    synchronize();
    window.addEventListener("resize", synchronize);
    return () => window.removeEventListener("resize", synchronize);
  }, [queueCollapsed]);
  function closeActivity() {
    setQueueCollapsed(true);
    drawer.current?.close();
    try { localStorage.setItem("spechelper-queue-collapsed", "true"); } catch {}
  }
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
    <InstanceNameContext.Provider value={name}><div className="dashboard" data-queue-collapsed={queueCollapsed}>
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
              aria-label={t(item.label)}
              aria-current={item.active ? "page" : undefined}
            >
              <item.icon size={18} />
              <span>{t(item.label)}</span>
            </Link>
          ))}
        </nav>
        <SidebarAssistants />
        <Link
          href="/admin?tab=ai-agents&section=connections"
          className="sidebar-admin"
          aria-label={t("Administration")}
          title={t("Administration")}
          aria-current={pathname.startsWith("/admin") ? "page" : undefined}
        >
          <span className="admin-avatar">
            {(shortLabel || name).slice(0, 1).toUpperCase()}
          </span>
          <span>
            {shortLabel || name}
            <small>{t("Administration")}</small>
          </span>
          <ChevronRight size={14} />
        </Link>
      </aside>
      <div className="dashboard-center">
        <div className="queue-toolbar">
          <button type="button" className="activity-toggle inline-flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-primary"
            aria-label={t("Activity")} aria-expanded={!queueCollapsed} aria-controls="desktop-task-queue activity-drawer" aria-describedby="activity-attention" onClick={toggleQueue}>
            <Activity size={18} aria-hidden="true" />{t("Activity")}
            {!!attention.count && <span className="queue-total" aria-hidden="true">{attention.count}</span>}
            {attention.running > 0 && <LoaderCircle size={12} className="queue-running-icon" aria-hidden="true" />}
          </button>
          <span id="activity-attention" className="sr-only" aria-live="polite">
            {attention.clarifications === 1 ? t("One analysis needs your answer") : attention.clarifications > 1 ? t("{count} analyses need your answer", { count: attention.clarifications }) : attention.count === 1 ? t("One action needs attention") : attention.count > 0 ? t("{count} actions need attention", { count: attention.count }) : t("No action needed")}
            {attention.running > 0 && ` · ${t("Analyses in progress")}`}
            {attention.error && ` · ${t("Activity updates unavailable")}`}
          </span>
        </div>
        <main className="min-w-0">{children}</main>
      </div>
      <aside id="desktop-task-queue" className="dashboard-queue" aria-label={t("Activity")} hidden={queueCollapsed}>
        {!queueCollapsed && <TaskQueue />}
      </aside>
      <dialog
        ref={drawer}
        id="activity-drawer"
        onCancel={event => { event.preventDefault(); closeActivity(); }}
        className="queue-drawer"
        aria-label={t("Activity")}
        onClick={(e) => {
          if (
            e.target === e.currentTarget ||
            (e.target instanceof Element && e.target.closest("a"))
          )
            closeActivity();
        }}
      >
        <button
          type="button"
          className="mb-5 inline-flex items-center gap-2 rounded border px-3 py-2"
          onClick={closeActivity}
        >
          <X size={18} />
          {t("Close")}
        </button>
        <TaskQueue />
      </dialog>
    </div></InstanceNameContext.Provider>
  );
}
