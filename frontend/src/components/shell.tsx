"use client";
import { I18nProvider, useI18n, type Language } from "@/lib/i18n";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  FileText,
  Settings,
  Sparkles,
  Tickets,
  PanelRightOpen,
  X,
} from "lucide-react";
import { TaskQueue, TaskQueueProvider } from "@/components/task-queue";
import { statuses } from "@/lib/api";
import { api } from "@/lib/api";

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      <TaskQueueProvider>
        <ShellContent>{children}</ShellContent>
      </TaskQueueProvider>
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
  const [connections, setConnections] = useState<{
    github: { status: string };
    ais: {
      agent: string;
      status: string;
      availability: string;
      enabled: boolean;
    }[];
  } | null>(null);
  useEffect(() => {
    let alive = true;
    const update = () =>
      api<typeof connections>("/connections")
        .then((v) => {
          if (alive) setConnections(v);
        })
        .catch(() => {
          if (alive) setConnections(null);
        });
    update();
    const timer = setInterval(update, 10000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
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
              label: "Requests",
              icon: FileText,
              active:
                !pathname.startsWith("/admin") &&
                !pathname.startsWith("/tickets"),
            },
            {
              href: "/tickets",
              label: "Tickets",
              icon: Tickets,
              active: pathname.startsWith("/tickets"),
            },
            {
              href: "/admin",
              label: "Settings",
              icon: Settings,
              active: pathname.startsWith("/admin"),
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
        <div
          className="connection-indicators"
          aria-label={t("Connection status")}
        >
          {(connections?.ais || []).map((ai) => (
            <p key={ai.agent}>
              <span
                className="connection-dot"
                data-connected={
                  ai.enabled &&
                  ai.status === "CONNECTED" &&
                  ["AVAILABLE", "BUSY"].includes(ai.availability)
                }
              />
              <span>
                {ai.agent === "codex" ? "ChatGPT / Codex" : "Claude"}
                <small>
                  {t(
                    ai.enabled === false
                      ? "Disabled"
                      : ai.status !== "CONNECTED"
                        ? statuses[ai.status] || "Unknown"
                        : statuses[ai.availability] || "Connected",
                  )}
                </small>
              </span>
            </p>
          ))}
          {!connections && (
            <p>
              {t("AI connections")}: {t("Unknown")}
            </p>
          )}
          <p>
            <span
              className="connection-dot"
              data-connected={connections?.github.status === "CONNECTED"}
            />
            <span>
              GitHub
              <small>
                {t(statuses[connections?.github.status || "UNKNOWN"])}
              </small>
            </span>
          </p>
        </div>
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
          if (e.target === e.currentTarget) drawer.current?.close();
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
