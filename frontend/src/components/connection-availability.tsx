"use client";

import { connectionAvailability } from "@/lib/quota";
import { useI18n } from "@/lib/i18n";

export function ConnectionAvailability({ connection, className = "" }: {
  connection: Parameters<typeof connectionAvailability>[0]; className?: string;
}) {
  const { t } = useI18n();
  const status = connectionAvailability(connection);
  return <span className={`badge ai-availability ${className}`} data-availability={status.key}
    title={status.reason ? t(status.reason) : undefined}>{t(status.label)}</span>;
}
