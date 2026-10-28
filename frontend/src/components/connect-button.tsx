"use client";
import { useI18n } from "@/lib/i18n";

import { useEffect, useId, useRef, useState } from "react";
import { CheckCircle, Copy, ExternalLink, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, send } from "@/lib/api";

type Provider = "github" | "codex" | "claude" | "antigravity";
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
  antigravity: "Antigravity",
};
const active = new Set(["STARTING", "AWAITING_USER"]);

export function ConnectButton({
  provider,
  onConnected,
  startPath = "/connections/start",
  identityLabel,
  reconnect = false,
}: {
  provider: Provider;
  onConnected: () => void;
  startPath?: string;
  identityLabel?: string;
  reconnect?: boolean;
}) {
  const { t } = useI18n();
  const elementId = useId();
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);
  const [authChoiceOpen, setAuthChoiceOpen] = useState(false);
  const [keyMode, setKeyMode] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [billingConfirmed, setBillingConfirmed] = useState(false);
  const [keySaved, setKeySaved] = useState(false);
  const keyInput = useRef<HTMLInputElement>(null);
  const apiKeyPath = provider === "antigravity" && startPath.endsWith("/auth/start")
    ? startPath.replace(/\/start$/, "/api-key") : null;
  const dialog = useRef<HTMLDialogElement>(null);
  const connected = useRef("");
  const closing = useRef(false);
  const notify = useRef(onConnected);
  useEffect(() => { if (keyMode) keyInput.current?.focus(); }, [keyMode]);
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
    if ((attempt || authChoiceOpen) && dialog.current && !dialog.current.open)
      dialog.current.showModal();
    if (!attempt && !authChoiceOpen && dialog.current?.open) dialog.current.close();
  }, [attempt, authChoiceOpen]);
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
    setKeyMode(false);
    setApiKey("");
    setBillingConfirmed(false);
    setKeySaved(false);
    try {
      accept(
        await send<Attempt>(
          startPath,
          startPath === "/connections/start" ? { provider } : undefined,
        ),
      );
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
    setAuthChoiceOpen(false);
    setKeyMode(false);
    setApiKey("");
    setBillingConfirmed(false);
    setKeySaved(false);
    setError("");
  }
  async function saveApiKey(event: React.FormEvent) {
    event.preventDefault();
    if (!apiKeyPath || !billingConfirmed || !apiKey.trim()) return;
    const submitted = apiKey;
    setApiKey("");
    setBusy(true);
    setError("");
    try {
      await send(apiKeyPath, { api_key: submitted, confirm_billing: true });
      setKeyMode(false);
      setBillingConfirmed(false);
      setKeySaved(true);
      setAttempt(null);
      notify.current();
    } catch (e) {
      setError((e as Error).message.replaceAll(submitted, "[redacted]"));
    } finally {
      setBusy(false);
    }
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
        disabled={busy || !!attempt || authChoiceOpen}
        type="button"
        variant={provider === "claude" ? "outline" : "default"}
        onClick={() => {
          if (provider === "antigravity") {
            closing.current = false;
            setAuthChoiceOpen(true);
            setError("");
          } else start();
        }}
      >
        {busy && !attempt && (
          <LoaderCircle size={16} className="animate-spin" />
        )}
        {t(reconnect ? "Reconnect with" : "Connect with")} {names[provider]}
      </Button>
      {!attempt && !authChoiceOpen && error && (
        <p role="alert" className="max-w-xs text-sm text-red-700">
          {t(error)}
        </p>
      )}
      <dialog
        ref={dialog}
        aria-labelledby={`login-title-${elementId}`}
        onCancel={(e) => {
          e.preventDefault();
          close();
        }}
        style={{ width: "calc(100% - 2rem)" }}
        className="fixed inset-0 m-auto max-h-[90dvh] max-w-lg overflow-y-auto rounded-xl border bg-card p-6 text-foreground shadow-xl backdrop:bg-black/40"
      >
        {attempt && (
          <>
            <h2 id={`login-title-${elementId}`}>
              {t("Sign in with")} {names[provider]}
            </h2>
            {identityLabel && (
              <p className="mt-2 text-sm font-medium">{identityLabel}</p>
            )}
            <p className="mt-3 text-sm leading-6 muted">
              {attempt.status === "CONNECTED"
                ? t(
                    "Your account is ready. You can close this window and continue in SpecHelper.",
                  )
                : provider === "antigravity" ? t("Sign in with your Google account. Antigravity will verify whether your account can use the service. No API key is required.") : t(
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
                    : provider === "claude"
                      ? "Claude Code"
                      : "Antigravity CLI"}
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
                <label htmlFor={`confirmation-${elementId}`}>
                  {t("Confirmation code")}
                </label>
                <p className="mb-2 text-xs leading-5 muted">
                  {t("If")} {names[provider]}{" "}
                  {t("shows a code after sign-in, paste it here to finish.")}
                </p>
                <Input
                  id={`confirmation-${elementId}`}
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
            <div className="mt-6 flex flex-wrap justify-end gap-3">
              {apiKeyPath && !active.has(attempt.status) && attempt.status !== "CONNECTED" && <Button variant="outline" disabled={busy} onClick={() => { setAttempt(null); setKeyMode(true); setError(""); }}>{t("Use a Gemini API key")}</Button>}
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
        {!attempt && authChoiceOpen && <>
          <h2 id={`login-title-${elementId}`}>{t("Sign in with")} Antigravity</h2>
          {identityLabel && <p className="mt-2 text-sm font-medium">{identityLabel}</p>}
          {keySaved ? <p role="status" className="mt-4 text-sm">{t("Credential saved. Model access remains unverified until an analysis succeeds.")}</p> : <>
            <p className="mt-3 text-sm leading-6 muted">{t("Sign in with your Google account. Antigravity will verify whether your account can use the service. No API key is required.")}</p>
            {!keyMode && <div className="mt-5 flex flex-wrap gap-3">
              <Button disabled={busy} onClick={start}>{t("Continue with Google")}</Button>
              {apiKeyPath && <Button variant="outline" disabled={busy} onClick={() => { setKeyMode(true); setError(""); }}>{t("Use a Gemini API key")}</Button>}
            </div>}
          </>}
          {keyMode && apiKeyPath && <form onSubmit={saveApiKey} className="mt-5 space-y-4">
            <p className="text-sm muted">{t("Gemini API use may be billed by Google. SpecHelper uses this key only for this explicitly configured identity; it never inherits a key from your environment.")}</p>
            <div className="field"><label htmlFor={`api-key-${elementId}`}>{t("Gemini API key")}</label><Input ref={keyInput} id={`api-key-${elementId}`} type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} required maxLength={4096} autoComplete="off" spellCheck={false} disabled={busy} /></div>
            <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={billingConfirmed} onChange={(event) => setBillingConfirmed(event.target.checked)} disabled={busy} required />{t("I authorize use of this API key and accept any charges from my provider.")}</label>
            <Button disabled={busy || !apiKey.trim() || !billingConfirmed}>{t("Save API credential")}</Button>
          </form>}
          {error && <p role="alert" className="mt-4 text-sm text-red-700">{t(error)}</p>}
          <div className="mt-6 flex justify-end"><Button variant="outline" disabled={busy} onClick={close}>{t("Close")}</Button></div>
        </>}
      </dialog>
    </div>
  );
}
