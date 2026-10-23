"use client";
import { useEffect, useState } from "react";
import { LockKeyhole, LogOut } from "lucide-react";
import { accessSession, clearAccess, secureFetch, type AccessSession } from "@/lib/access";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function AccessGate({ children }: { children: React.ReactNode }) {
  const { t, language, setLanguage } = useI18n();
  const [session, setSession] = useState<AccessSession | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function refresh() {
    try { setSession(await accessSession(true)); setError(""); }
    catch (error) { setError((error as Error).message); }
  }
  useEffect(() => {
    refresh();
    const invalid = () => { setSession(null); clearAccess(); refresh(); };
    window.addEventListener("access-required", invalid);
    return () => window.removeEventListener("access-required", invalid);
  }, []);
  useEffect(() => {
    if (!session?.authenticated || !session.expires_at) return;
    const timer = window.setTimeout(() => { clearAccess(); setSession(null); refresh(); }, Math.max(0, Date.parse(session.expires_at) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [session]);
  if (session?.authenticated) return <>
    {children}
    {session.mode === "password" && <Button className="fixed bottom-3 right-3 z-40 shadow" variant="outline" size="sm" onClick={async () => {
      setBusy(true);
      try {
        const response = await secureFetch("/api/access/logout", { method: "POST" });
        if (!response.ok) throw new Error("Sign out failed. Try again.");
        clearAccess(); setSession(null); await refresh();
      } catch (error) { setError((error as Error).message); } finally { setBusy(false); }
    }} disabled={busy}><LogOut size={15} />{t("Sign out")}</Button>}
    {error && <p role="alert" className="fixed bottom-14 right-3 z-40 rounded border bg-card p-3 text-sm">{t(error)}</p>}
  </>;
  return <main className="mx-auto flex min-h-dvh max-w-md items-center px-6 py-12">
    <section className="w-full rounded-xl border bg-card p-6 shadow-sm">
      <div className="mb-5 flex items-center justify-between"><LockKeyhole size={24} /><select aria-label={t("Application language")} className="w-auto" value={language} onChange={(event) => setLanguage(event.target.value === "en" ? "en" : "fr")}><option value="fr">Français</option><option value="en">English</option></select></div>
      <h1 className="text-xl">SpecHelper</h1>
      <p className="mt-3 text-sm muted">{t("Sign in to your shared team instance.")}</p>
      {error && <p role="alert" className="mt-4 text-sm text-red-700">{t(error)}</p>}
      {!session && !error && <p className="mt-4 muted" role="status">{t("Checking access…")}</p>}
      {session?.mode === "password" && <form className="mt-5" onSubmit={async (event) => {
        event.preventDefault(); setBusy(true); setError("");
        try {
          const response = await secureFetch("/api/access/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
          if (!response.ok) { const value = await response.json(); throw new Error(value.detail || "Sign-in failed."); }
          setPassword(""); clearAccess(); await refresh();
        } catch (error) { setError((error as Error).message); } finally { setBusy(false); }
      }}>
        <label htmlFor="instance-password">{t("Instance password")}</label>
        <Input id="instance-password" type="password" autoComplete="current-password" maxLength={1024} value={password} onChange={(event) => setPassword(event.target.value)} required disabled={busy} />
        <Button className="mt-4 w-full" disabled={busy}>{t(busy ? "Signing in…" : "Sign in")}</Button>
      </form>}
      {(error || session?.mode === "unconfigured") && <Button className="mt-4" variant="outline" onClick={refresh}>{t("Retry")}</Button>}
    </section>
  </main>;
}
