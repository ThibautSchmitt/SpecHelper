"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { ProviderLogo } from "@/components/provider-logo";
import { publicationPlatforms, type TicketConnector } from "@/components/ticket-connectors";

function ConnectionLabel({ value }: { value: TicketConnector }) {
  const { t } = useI18n();
  return <><ProviderLogo provider={value.platform} /><span className="break-words">{value.name}</span>
    <span className="badge">{publicationPlatforms[value.platform] || value.platform}</span>
    <span className="badge" data-state={!value.enabled ? "DISABLED" : value.status}>{t(!value.enabled ? "Disabled" : value.status === "CONNECTED" ? "Connected" : value.status === "UNKNOWN" ? "Not tested" : value.status === "ERROR" ? "Failed" : value.status === "UNAVAILABLE" ? "Verification unavailable" : value.status)}</span></>;
}

export function PublicationConnectionsSummary({ values }: { values: TicketConnector[] }) {
  const { t } = useI18n();
  return <section className="mt-5 border-t pt-4" aria-label={t("Publication destinations")}>
    <h3 className="text-sm font-medium">{t("Publication destinations")}</h3>
    {values.length ? <ul className="mt-3 space-y-2">{values.map(value => <li key={value.id} className="title-tags text-sm"><ConnectionLabel value={value} /></li>)}</ul>
      : <p className="mt-2 text-xs muted">{t("No publication connection associated. You can still discuss and analyse.")}</p>}
  </section>;
}

export function PublicationConnectionPicker({ selected, onChange, disabled = false }: {
  selected: number[]; onChange: (ids: number[]) => void; disabled?: boolean;
}) {
  const { t } = useI18n();
  const [items, setItems] = useState<TicketConnector[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    const refresh = () => api<TicketConnector[]>("/ticket-connectors").then(values => {
      if (alive) { setItems(values); setError(false); }
    }).catch(() => { if (alive) setError(true); });
    void refresh();
    window.addEventListener("publication-connections-updated", refresh);
    return () => { alive = false; window.removeEventListener("publication-connections-updated", refresh); };
  }, []);
  return <fieldset className="mt-5 min-w-0 border-t pt-4" disabled={disabled}>
    <legend className="text-sm font-medium">{t("Publication destinations")}</legend>
    <p className="mt-2 text-xs muted">{t("Optional: choose the publication accounts this environment can use. Several accounts of the same provider are allowed.")}</p>
    {error && <p role="alert" className="mt-2 text-sm">{t("Publication connections could not be loaded. Existing selections are preserved.")}</p>}
    {items === null && !error && <p role="status" className="mt-2 text-xs muted">{t("Loading…")}</p>}
    {items?.map(value => <label key={value.id} className="mt-3 flex min-w-0 items-start gap-2 text-sm">
      <input type="checkbox" className="mt-1 shrink-0" checked={selected.includes(value.id)} onChange={event => onChange(event.target.checked ? [...selected, value.id] : selected.filter(id => id !== value.id))} />
      <span className="title-tags"><ConnectionLabel value={value} /></span>
    </label>)}
    <a className="mt-3 inline-block text-xs text-primary underline" href="/admin?tab=connectors" target="_blank" rel="noopener noreferrer">{t("Manage publication connections")}<span className="sr-only"> · {t("Opens in a new tab")}</span></a>
  </fieldset>;
}
