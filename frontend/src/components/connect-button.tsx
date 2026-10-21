"use client";
import { useI18n } from "@/lib/i18n";

import { useEffect, useRef, useState } from "react";
import { CheckCircle, Copy, ExternalLink, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, send } from "@/lib/api";

type Provider = "github" | "codex" | "claude";
type Attempt = {
  id: string;
  provider: Provider;
  status: string;
  verification_uri: string;
  user_code: string;
  input_required: boolean;
  message: string;
  expires_at: string;
};
const names: Record<Provider, string> = {
  github: "GitHub",
  codex: "ChatGPT",
  claude: "Claude",
};
const active = new Set(["STARTING", "AWAITING_USER"]);

export function ConnectButton({
  provider,
  onConnected,
}: {
  provider: Provider;
  onConnected: () => void;
}) {
  const { t, dateLocale } = useI18n();
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const connected = useRef("");
  const closing = useRef(false);
  const notify = useRef(onConnected);
  function accept(result: Attempt) {
    if (closing.current) return;
    setAttempt(result);
    if (result.status === "CONNECTED" && connected.current !== result.id) {
      connected.current = result.id;
      notify.current();
    }
  }
  useEffect(() => {
    notify.current = onConnected;
  }, [onConnected]);
  useEffect(() => {
    if (attempt && dialog.current && !dialog.current.open)
      dialog.current.showModal();
    if (!attempt && dialog.current?.open) dialog.current.close();
  }, [attempt]);
  useEffect(() => {
    if (!attempt || !active.has(attempt.status)) return;
    let alive = true;
    let pending = false;
    const poll = async () => {
      if (pending) return;
      pending = true;
      try {
        const result = await api<Attempt>(
          `/connections/attempts/${attempt.id}`,
        );
        if (!alive || closing.current) return;
        accept(result);
        setError("");
      } catch (e) {
        if (alive) setError((e as Error).message);
      } finally {
        pending = false;
      }
    };
    poll();
    const timer = setInterval(poll, 1500);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [attempt?.id, attempt?.status]);

  async function start() {
    closing.current = false;
    setBusy(true);
    setError("");
    setCode("");
    setCopied(false);
    try {
      accept(await send<Attempt>("/connections/start", { provider }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function close() {
    closing.current = true;
    if (attempt && active.has(attempt.status)) {
      setBusy(true);
      try {
        const result = await send<Attempt>(
          `/connections/attempts/${attempt.id}/cancel`,
        );
        if (result.status === "CONNECTED") notify.current();
      } catch (e) {
        closing.current = false;
        setError((e as Error).message);
        setBusy(false);
        return;
      }
      setBusy(false);
    }
    setAttempt(null);
    setError("");
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!attempt) return;
    setBusy(true);
    setError("");
    try {
      accept(
        await send<Attempt>(`/connections/attempts/${attempt.id}/code`, {
          code,
        }),
      );
      setCode("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-2">
      <Button
        disabled={busy || !!attempt}
        type="button"
        variant={provider === "claude" ? "outline" : "default"}
        onClick={start}
      >
        {busy && !attempt && (
          <LoaderCircle size={16} className="animate-spin" />
        )}
        {t("Connect with")} {names[provider]}
      </Button>
      {!attempt && error && (
        <p role="alert" className="max-w-xs text-sm text-red-700">
          {t(error)}
        </p>
      )}
      <dialog
        ref={dialog}
        aria-labelledby={`login-title-${provider}`}
        onCancel={(e) => {
          e.preventDefault();
          close();
        }}
        style={{ width: "calc(100% - 2rem)" }}
        className="fixed inset-0 m-auto max-h-[90dvh] max-w-lg overflow-y-auto rounded-xl border bg-card p-6 text-foreground shadow-xl backdrop:bg-black/40"
      >
        {attempt && (
          <>
            <h2 id={`login-title-${provider}`}>
              {t("Sign in with")} {names[provider]}
            </h2>
            <p className="mt-3 text-sm leading-6 muted">
              {attempt.status === "CONNECTED"
                ? t(
                    "Your account is ready. You can close this window and continue in SpecHelper.",
                  )
                : t(
                    "Sign in to your usual account. There is no key to create and no software to install.",
                  )}
            </p>
            {active.has(attempt.status) && (
              <p className="mt-2 text-xs leading-5 muted">
                {t("The authorization page may mention")}{" "}
                {provider === "github"
                  ? "GitHub CLI"
                  : provider === "codex"
                    ? "Codex"
                    : "Claude Code"}
                {t(", the official sign-in tool used by SpecHelper.")}
              </p>
            )}
            <div
              role={attempt.status === "ERROR" ? "alert" : "status"}
              className="mt-5 flex items-center gap-3 rounded-lg bg-muted p-4 text-sm"
            >
              {attempt.status === "CONNECTED" ? (
                <CheckCircle size={20} className="shrink-0 text-green-700" />
              ) : active.has(attempt.status) ? (
                <LoaderCircle
                  size={18}
                  className="shrink-0 animate-spin text-primary"
                />
              ) : null}
              <span>{t(attempt.message)}</span>
            </div>
            {active.has(attempt.status) && attempt.user_code && (
              <div className="mt-5">
                <p className="mb-2 text-sm font-medium">
                  {t("Enter this code on the website for")} {names[provider]} :
                </p>
                <div className="flex items-center justify-between gap-2 rounded-lg border p-4">
                  <code className="select-all text-2xl font-bold tracking-wider">
                    {attempt.user_code}
                  </code>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={t("Copy code")}
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(attempt.user_code);
                        setCopied(true);
                      } catch {
                        setError(t("Select the code to copy it."));
                      }
                    }}
                  >
                    <Copy size={16} />
                    {copied ? t("Copied") : t("Copy")}
                  </Button>
                </div>
              </div>
            )}
            {active.has(attempt.status) && attempt.verification_uri && (
              <Button asChild className="mt-5 w-full">
                <a
                  href={attempt.verification_uri}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t("Continue on")} {names[provider]}
                  <ExternalLink size={16} />
                </a>
              </Button>
            )}
            {active.has(attempt.status) && attempt.input_required && (
              <form onSubmit={submit} className="mt-5">
                <label htmlFor={`confirmation-${provider}`}>
                  {t("Confirmation code")}
                </label>
                <p className="mb-2 text-xs leading-5 muted">
                  {t("If")} {names[provider]}{" "}
                  {t("shows a code after sign-in, paste it here to finish.")}
                </p>
                <Input
                  id={`confirmation-${provider}`}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  required
                  maxLength={4096}
                  autoComplete="off"
                />
                <Button className="mt-3" disabled={busy || !code.trim()}>
                  {t("Confirm connection")}
                </Button>
              </form>
            )}
            {error && (
              <p role="alert" className="mt-4 text-sm text-red-700">
                {t(error)}
              </p>
            )}
            <div className="mt-6 flex justify-end gap-3">
              {["ERROR", "EXPIRED", "CANCELLED"].includes(attempt.status) && (
                <Button onClick={start} disabled={busy}>
                  {t("Retry")}
                </Button>
              )}
              <Button variant="outline" disabled={busy} onClick={close}>
                {active.has(attempt.status) ? t("Cancel") : t("Close")}
              </Button>
            </div>
          </>
        )}
      </dialog>
    </div>
  );
}
