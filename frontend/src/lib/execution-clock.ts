import type { AnalysisClock } from "@/lib/api";

export function executionSeconds(clock: AnalysisClock, now: number, unavailable = false) {
  if (clock.seconds === null || !Number.isFinite(clock.seconds)) return null;
  const observed = Date.parse(clock.observed_at);
  const extra = clock.running && !unavailable && Number.isFinite(observed)
    ? Math.max(0, (now - observed) / 1000) : 0;
  return Math.max(0, Math.floor(clock.seconds + extra));
}
