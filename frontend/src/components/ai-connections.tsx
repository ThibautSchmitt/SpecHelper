"use client";
import { useI18n } from "@/lib/i18n";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConnectButton } from "@/components/connect-button";
import { send, statuses } from "@/lib/api";

export type AIConnection = {
  id: number;
  agent: "codex" | "claude";
  status: string;
  availability: string;
  enabled: boolean;
  account: string;
};

export function AIConnections({
  values,
  onChanged,
}: {
  values: AIConnection[];
  onChanged: () => Promise<void>;
}) {
  const { t, dateLocale } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  async function action(task: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
      await onChanged();
      setNotice(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-4">
      {(["codex", "claude"] as const).map((provider) => {
        const connection = values.find((c) => c.agent === provider);
        const name = provider === "codex" ? "ChatGPT" : "Claude";
        return (
          <Card key={provider} aria-labelledby={`assistant-${provider}`}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 id={`assistant-${provider}`}>{name}</h2>
              <span className="badge" data-state={connection?.availability}>
                {connection?.enabled === false
                  ? t("Disabled")
                  : t(statuses[connection?.availability || "UNKNOWN"])}
              </span>
            </div>
            <p className="mt-3 text-sm muted">
              {t(
                "Connect your usual account. SpecHelper automatically selects an available assistant for each request.",
              )}
            </p>
            <div className="mt-5 flex flex-wrap items-start gap-3">
              <ConnectButton
                provider={provider}
                onConnected={() => {
                  action(
                    async () => {},
                    t("{name} connected.", { name: name }),
                  );
                }}
              />
              {connection?.status === "CONNECTED" && (
                <Button
                  variant="outline"
                  disabled={busy || connection.availability === "BUSY"}
                  onClick={() =>
                    action(
                      async () => {
                        const result = await send<AIConnection>(
                          `/connections/ai/${connection.id}/test`,
                        );
                        if (result.status !== "CONNECTED")
                          throw new Error(
                            t("Reconnect this assistant to use it."),
                          );
                      },
                      t(
                        "{name}: connection verified. Remaining quota is not provided.",
                        { name: name },
                      ),
                    )
                  }
                >
                  {t("Test connection")}
                </Button>
              )}
            </div>
            {connection?.status === "CONNECTED" && (
              <label className="mt-4 flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={connection.enabled}
                  disabled={busy}
                  onChange={(e) =>
                    action(
                      () =>
                        send(
                          `/connections/ai/${connection.id}`,
                          { enabled: e.target.checked },
                          "PATCH",
                        ),
                      t("Preference saved."),
                    )
                  }
                />
                {t("Use this assistant for requests")}
              </label>
            )}
            {connection?.availability === "QUOTA_EXHAUSTED" && (
              <p className="mt-3 text-sm muted">
                {t(
                  "The provider reported an exhausted quota. Requests use the other assistant when available. Check and retry when your quota is restored.",
                )}
              </p>
            )}
          </Card>
        );
      })}
      <p className="text-xs muted">
        {t(
          "Connections are shared by the team. Remaining quotas and reset times are not estimated.",
        )}
      </p>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {t(error)}
        </p>
      )}
      {notice && (
        <p role="status" className="text-sm text-green-800">
          {t(notice)}
        </p>
      )}
    </div>
  );
}
