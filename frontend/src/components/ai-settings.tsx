"use client";

import { useEffect, useState } from "react";
import { BookOpen, Bot, Layers, Network, Plug } from "lucide-react";
import { AIConnections } from "@/components/ai-connections";
import { AILibrary } from "@/components/ai-library";
import { AIModels } from "@/components/ai-models";
import { OrchestrationSettingsForm } from "@/components/orchestration-settings";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

export function AISettings({ onChanged, simplified = false }: { onChanged: () => Promise<void>; simplified?: boolean }) {
  const { t } = useI18n();
  const [tab, setTab] = useState("connections");
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    if (query.has("library_draft"))
      setTab(simplified || query.get("library_kind") === "skill" ? "skills" : "agents");
  }, [simplified]);
  const tabs = [
    { id: "connections", label: "Connections", icon: Plug },
    { id: "models", label: "Models", icon: Layers },
    { id: "roles", label: "Roles and orchestration", icon: Network },
    { id: "agents", label: "Agents", icon: Bot },
    { id: "skills", label: "Skills", icon: BookOpen },
  ].filter(item => !simplified || item.id !== "agents");
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
      {tab === "connections" && <AIConnections onChanged={onChanged} simplified={simplified} />}
      {tab === "models" && <AIModels />}
      {tab === "roles" && <OrchestrationSettingsForm />}
      {!simplified && tab === "agents" && <AILibrary kind="agent" />}
      {tab === "skills" && <AILibrary kind="skill" />}
    </div>
  );
}
