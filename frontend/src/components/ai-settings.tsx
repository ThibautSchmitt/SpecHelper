"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BookOpen, Bot, Network, Plug, UserRound, ShieldCheck } from "lucide-react";
import { AIConnections } from "@/components/ai-connections";
import { AILibrary } from "@/components/ai-library";
import { OrchestrationSettingsForm } from "@/components/orchestration-settings";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { publicRoles, roleLabels } from "@/lib/orchestration";
import type { OrchestrationSettings } from "@/components/orchestration-settings";

export function AISettings({ onChanged, simplified = false }: { onChanged: () => Promise<void>; simplified?: boolean }) {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const section = searchParams.get("section");
  const tab = section && ["connections", "roles", "skills"].includes(section)
    ? section
    : searchParams.has("library_draft")
      ? simplified || searchParams.get("library_kind") === "skill" ? "skills" : "agents"
      : "connections";
  function setTab(value: string) {
    router.replace(`/admin?tab=ai-agents&section=${value}`, { scroll: false });
  }
  const [coverage, setCoverage] = useState<OrchestrationSettings["role_coverage"]>();
  const [skillCount, setSkillCount] = useState<number | null>(null);
  useEffect(() => {
    let alive = true;
    const refresh = () => {
      api<OrchestrationSettings>("/orchestration-settings").then(value => { if (alive) setCoverage(value.role_coverage); }).catch(() => {});
      api<{ enabled: boolean; deleted?: boolean }[]>("/library/skill").then(values => { if (alive) setSkillCount(values.filter(value => value.enabled && !value.deleted).length); }).catch(() => {});
    };
    refresh(); window.addEventListener("connections-updated", refresh);
    return () => { alive = false; window.removeEventListener("connections-updated", refresh); };
  }, [tab]);
  const tabs = [
    { id: "connections", label: "Connections", icon: Plug },
    { id: "roles", label: "Orchestration", icon: Network },
    { id: "agents", label: "Agents", icon: Bot },
    { id: "skills", label: "Skills", icon: BookOpen },
  ].filter(item => item.id !== "agents");
  return (
    <div className="space-y-6">
      <nav className="flex flex-wrap gap-1" aria-label={t("AI settings")}>
        {tabs.map(({ id, label, icon: Icon }) => (
          <Button
            key={id}
            variant={tab === id ? "default" : "ghost"}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => setTab(id)}
          >
            <Icon size={16} aria-hidden="true" />
            {t(label)}
          </Button>
        ))}
      </nav>
      {tab === "connections" && <div className="ai-settings-layout"><AIConnections onChanged={onChanged} simplified={simplified} />
        <aside className="ai-settings-summary" aria-label={t("Analysis configuration")}>
          <section><h3><Network size={22} aria-hidden="true" />{t("Orchestration")}</h3><p className="muted">{t("Role coverage")}</p>
            <ul>{publicRoles.map(role => <li key={role}><span className="flex items-center gap-2">{role === "verifier" ? <ShieldCheck size={16} aria-hidden="true" /> : <UserRound size={16} aria-hidden="true" />}{t(roleLabels[role])}</span><span className="coverage-state" data-role-state={!coverage ? "unknown" : !coverage.roles[role]?.configured.length ? "missing" : !coverage.roles[role]?.available.length ? "waiting" : "covered"}>{t(!coverage ? "Unknown" : !coverage.roles[role]?.configured.length ? "Not covered" : !coverage.roles[role]?.available.length ? "Waiting" : "Covered")}</span></li>)}</ul>
            <button type="button" className="summary-action" onClick={() => setTab("roles")}>{t("View configuration")} →</button>
          </section>
          <section><h3><BookOpen size={22} aria-hidden="true" />{t("Skills")}</h3><p>{skillCount === null ? t("Not reported") : t("{count} active skills", { count: skillCount })}</p><p className="mt-3 muted">{t("Assistants discover compatible skills for each analysis.")}</p><button type="button" className="summary-action" onClick={() => setTab("skills")}>{t("Manage skills")} →</button></section>
        </aside></div>}
      {tab === "roles" && <OrchestrationSettingsForm />}
      {!simplified && tab === "agents" && <AILibrary kind="agent" />}
      {tab === "skills" && <AILibrary kind="skill" />}
    </div>
  );
}
