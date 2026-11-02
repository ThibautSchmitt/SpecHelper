import type { AIConnection, QuotaWindow } from "@/components/ai-connections";

type AvailabilityInput = Pick<AIConnection, "model" | "availability"> & { agent: string } &
  Partial<Pick<AIConnection, "enabled" | "status" | "quota_windows" | "quota_status" | "availability_issue">>;

/** Presentation only: never changes eligibility, retries or provider selection. */
export function connectionAvailability(connection: AvailabilityInput, now = Date.now()) {
  const state = (key: string, label: string, reason = "") => ({ key, label, reason });
  if (connection.enabled === false) return state("unavailable", "Unavailable", "Disabled");
  if (["AUTH_ERROR", "DISCONNECTED", "ERROR", "UNAVAILABLE"].includes(connection.status || ""))
    return state("unavailable", "Unavailable", "Authentication or connection error");
  if ([connection.availability, connection.availability_issue].some(state => ["MODEL_UNAVAILABLE", "ERROR", "AUTH_ERROR", "UNAVAILABLE"].includes(state || "")))
    return state("unavailable", "Unavailable", connection.availability === "MODEL_UNAVAILABLE" ? "Model unavailable" : "Connection unavailable");
  const pool = connection.agent === "antigravity" ? connection.model?.startsWith("gemini-") ? "gemini" : /^(claude-|gpt-)/.test(connection.model || "") ? "claude_gpt" : "" : "";
  const windows = Object.entries(connection.quota_windows || {}).filter(([name, window]) => {
    const windowPool = window.model_pool || (name === "gemini-weekly" ? "gemini" : name === "3p-weekly" ? "claude_gpt" : "");
    if (windowPool ? windowPool !== pool : window.scope && window.scope !== "account") return false;
    const reset = Date.parse(window.reset_at || window.resets_at || "");
    const observed = Date.parse(window.observed_at || "");
    // Crossing a reset time is not evidence of renewed availability.
    if (Number.isFinite(reset) && reset <= now && (!Number.isFinite(observed) || observed < reset)) return false;
    return window.exhausted === true || remainingPercent(window) === 0;
  });
  if (windows.some(([name, window]) => name === "weekly" || ["gemini-weekly", "3p-weekly"].includes(name) || window.window_type === "weekly" || window.window_minutes === 10080))
    return state("quota_exhausted", "Quota exhausted", "Weekly limit reached");
  if (windows.length && windows.every(([, window]) => window.window_minutes === 300))
    return state("waiting", "Waiting", "Five-hour limit reached");
  if (windows.some(([name, window]) => ["daily", "credits"].includes(name) || ["daily", "credits"].includes(window.window_type || "") || !!window.window_minutes && window.window_minutes !== 300))
    return state("unavailable", "Unavailable", "Another reported quota limit is blocking this connection. See quota details.");
  if (windows.length || connection.availability === "QUOTA_EXHAUSTED") return state("unknown", "Quota limit reported", "The provider has not identified the quota period.");
  if (connection.availability === "BUSY") return state("unavailable", "Unavailable", "Assistant busy");
  if (connection.status === "CONNECTED" && connection.availability === "AVAILABLE") return state("available", "Available");
  return state("unknown", "Availability unknown");
}

export function remainingPercent(window?: QuotaWindow): number | null {
  const value = window?.remaining_percent ?? (typeof window?.used_percent === "number" ? 100 - window.used_percent : null);
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
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
