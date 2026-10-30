import type { AIConnection, QuotaWindow } from "@/components/ai-connections";

export function remainingPercent(window?: QuotaWindow): number | null {
  const value = window?.remaining_percent ?? (typeof window?.used_percent === "number" ? 100 - window.used_percent : null);
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
}

export function weeklyQuotaExhausted(connection: AIConnection): boolean {
  const weekly = Object.entries(connection.quota_windows || {}).filter(([name, window]) =>
    name === "weekly" || window.window_type === "weekly" || window.window_minutes === 10080 || name === "gemini-weekly" || name === "3p-weekly",
  );
  const exhausted = (window: QuotaWindow) => window.exhausted === true || remainingPercent(window) === 0;
  // Both known Antigravity families must be exhausted; missing data is not zero.
  if (connection.agent === "antigravity") return ["gemini", "claude_gpt"].every(pool =>
    weekly.some(([name, window]) => (window.model_pool || (name === "gemini-weekly" ? "gemini" : name === "3p-weekly" ? "claude_gpt" : "")) === pool && exhausted(window)),
  );
  return weekly.some(([, window]) => (!window.scope || window.scope === "account") && !window.model_pool && exhausted(window));
}

export function observedQuota(connection: AIConnection, now = Date.now()) {
  const windows = Object.entries(connection.quota_windows || {}).map(([name, window]) => ({
    name, window, remaining: remainingPercent(window),
  }));
  const pool = connection.agent === "antigravity" ? connection.model?.startsWith("gemini-") ? "gemini" : /^(claude-|gpt-)/.test(connection.model || "") ? "claude_gpt" : "" : "";
  const applicable = windows.filter(item => !item.window.scope || item.window.scope === "account" || (item.window.scope === "model_pool" && !!pool && item.window.model_pool === pool));
  const quantified = applicable.filter(item => item.remaining !== null);
  const limiting = quantified.sort((a, b) => a.remaining! - b.remaining!)[0];
  const observed = limiting?.window.observed_at || (connection.quota_status?.state === "available" ? connection.quota_status.checked_at : undefined);
  const timestamp = observed ? Date.parse(observed) : NaN;
  const reset = limiting?.window.reset_at || limiting?.window.resets_at;
  const expired = !!reset && Date.parse(reset) <= now && (!observed || Date.parse(observed) < Date.parse(reset));
  const stale = expired || !Number.isFinite(timestamp) || now - timestamp > 300000 || connection.quota_status?.state === "error" || connection.quota_status?.state === "unavailable";
  const authentication = connection.status !== "CONNECTED";
  const exhausted = connection.availability === "QUOTA_EXHAUSTED" || applicable.some(item => item.window.exhausted || item.remaining === 0);
  // A known exhausted but unquantified limit overrides another window's percentage.
  const unquantifiedExhaustion = exhausted && !applicable.some(item => item.remaining === 0);
  const remaining = authentication || !connection.enabled || unquantifiedExhaustion ? null : limiting?.remaining ?? null;
  return {
    windows, observed: Number.isFinite(timestamp) ? observed : null, stale, remaining,
    limiting: limiting?.name || "", limitingWindow: limiting?.window,
    partiallyAvailable: !!pool && connection.enabled && !authentication && !exhausted && quantified.some(item => item.remaining! > 0) && windows.some(item => item.window.scope === "model_pool" && item.window.model_pool && item.window.model_pool !== pool && (item.window.exhausted || item.remaining === 0)),
    state: !connection.enabled ? "Disabled" : authentication ? "Authentication required" : exhausted ? "Quota exhausted" : remaining === null ? "Quota unknown" : "Quota remaining",
    color: remaining === null ? "unknown" : remaining < 20 ? "red" : remaining < 60 ? "orange" : "green",
  };
}
