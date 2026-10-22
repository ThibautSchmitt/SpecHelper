"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import { RefreshCw, Tickets } from "lucide-react";
import { api, type Environment } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type Ticket = {
  id: string;
  title: string;
  external_id: string;
  external_key: string;
  url: string;
  platform: string;
  project: string;
  connector_name?: string;
  environment_name: string;
  request_id: string;
  version_number: number;
  status: string;
  created_at: string;
  updated_at?: string;
  error: string;
};
type TicketDetail = Ticket & {
  description: string;
  labels: string[];
  payload_available: boolean;
};
type TicketList = {
  items: Ticket[];
  total: number;
  page: number;
  page_size: number;
  environments?: string[];
  statuses?: string[];
};
const publicationStatuses: Record<string, string> = {
  PUBLISHED: "Published",
  PUBLISHING: "Publishing",
  PENDING: "Queued",
  ERROR: "Publication failed",
  UNCERTAIN: "Publication uncertain",
  FAILED: "Publication failed",
};
const platformName = (name: string) =>
  ({ github: "GitHub", gitlab: "GitLab", jira: "Jira", glpi: "GLPI" })[name] ||
  name;
function safeExternalUrl(value: string) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

export default function TicketsPage() {
  const { t, dateLocale } = useI18n();
  const [data, setData] = useState<TicketList>({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [platform, setPlatform] = useState("");
  const [environment, setEnvironment] = useState("");
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [error, setError] = useState("");
  const [environmentError, setEnvironmentError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const selected = data.items.find((ticket) => ticket.id === selectedId);
  const date = (value: string) => new Date(value).toLocaleString(dateLocale);
  useEffect(() => {
    let alive = true;
    api<Environment[]>("/environments")
      .then((items) => {
        if (alive) {
          setEnvironments(items);
          setEnvironmentError("");
        }
      })
      .catch(() => {
        if (alive)
          setEnvironmentError(
            "Environment options could not be loaded. Other filters remain available.",
          );
      });
    return () => {
      alive = false;
    };
  }, [revision]);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    const timer = setTimeout(() => {
      api<TicketList>(
        `/tickets?${new URLSearchParams({ platform, environment, status, search, page: String(page) })}`,
      )
        .then((value) => {
          if (!alive) return;
          setData(value);
          setSelectedId((current) =>
            value.items.some((ticket) => ticket.id === current)
              ? current
              : value.items[0]?.id || null,
          );
          setError("");
        })
        .catch((e) => {
          if (alive) setError(e.message);
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    }, 200);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [platform, environment, status, search, page, revision]);
  useEffect(() => {
    let alive = true;
    setDetail(null);
    setDetailError("");
    if (!selectedId) {
      setDetailLoading(false);
      return;
    }
    setDetailLoading(true);
    api<TicketDetail>(`/tickets/${selectedId}`)
      .then((value) => {
        if (alive) setDetail(value);
      })
      .catch((e) => {
        if (alive) setDetailError(e.message);
      })
      .finally(() => {
        if (alive) setDetailLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [selectedId, revision]);
  const externalUrl = selected && safeExternalUrl(selected.url);
  return (
    <div className="space-y-6 min-w-0">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1>{t("Tickets")}</h1>
          <p className="mt-2 muted max-w-xl">
            {t(
              "Tickets and publication attempts, linked to their exact analysis version.",
            )}
          </p>
        </div>
        <Button
          variant="outline"
          disabled={loading || detailLoading}
          onClick={() => setRevision((value) => value + 1)}
        >
          <RefreshCw size={16} aria-hidden="true" />
          {t("Refresh records")}
        </Button>
      </header>
      <Card className="p-4 sm:p-5">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <div>
            <label htmlFor="ticket-search">{t("Search tickets")}</label>
            <Input
              id="ticket-search"
              value={search}
              placeholder={t("Title, reference or project")}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
            />
          </div>
          <div>
            <label htmlFor="ticket-platform">{t("Platform")}</label>
            <select
              id="ticket-platform"
              value={platform}
              onChange={(event) => {
                setPlatform(event.target.value);
                setPage(1);
              }}
            >
              <option value="">{t("All platforms")}</option>
              {["github", "gitlab", "jira", "glpi"].map((value) => (
                <option key={value} value={value}>
                  {platformName(value)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="ticket-environment">{t("Environment")}</label>
            <select
              id="ticket-environment"
              value={environment}
              onChange={(event) => {
                setEnvironment(event.target.value);
                setPage(1);
              }}
            >
              <option value="">{t("All environments")}</option>
              {(
                data.environments ||
                Array.from(new Set(environments.map((item) => item.name)))
              ).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="ticket-status">{t("Publication status")}</label>
            <select
              id="ticket-status"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(1);
              }}
            >
              <option value="all">{t("All publication statuses")}</option>
              {(
                data.statuses || [
                  "PUBLISHED",
                  "UNCERTAIN",
                  "ERROR",
                  "PUBLISHING",
                ]
              ).map((value) => (
                <option key={value} value={value}>
                  {t(publicationStatuses[value] || value)}
                </option>
              ))}
            </select>
          </div>
        </div>
        {environmentError && (
          <p role="status" className="mt-3 text-sm muted">
            {t(environmentError)}
          </p>
        )}
      </Card>
      {error && (
        <div role="alert" className="rounded-xl border p-4">
          <p>{t(error)}</p>
          <p className="mt-1 text-sm muted">
            {t(
              "Refresh to try again. Previously loaded records may be out of date.",
            )}
          </p>
        </div>
      )}
      <Card
        className="p-0 overflow-hidden"
        aria-label={t("Ticket publications")}
      >
        <div className="border-b px-5 py-4 flex flex-wrap justify-between gap-2">
          <h2>{t("Ticket publications")}</h2>
          <span className="text-sm muted">
            {t("{total} tickets", { total: data.total })}
          </span>
        </div>
        {loading && (
          <p role="status" className="px-5 py-3 text-sm muted">
            {t("Loading tickets…")}
          </p>
        )}
        {!loading && !error && !data.items.length && (
          <div className="px-5 py-10 text-center">
            <Tickets
              className="mx-auto mb-3 muted"
              size={28}
              aria-hidden="true"
            />
            <h3>{t("No ticket publications match these filters.")}</h3>
            <p className="mt-2 text-sm muted">
              {t(
                "Publish a completed request to your ticket platform, or adjust these filters.",
              )}
            </p>
            <Link
              className="inline-block mt-4 text-primary underline text-sm"
              href="/"
            >
              {t("View requests")}
            </Link>
          </div>
        )}
        {!!data.items.length && (
          <div
            className="overflow-x-auto"
            tabIndex={0}
            role="region"
            aria-label={t("Ticket table")}
            aria-busy={loading}
          >
            <table className="w-full text-left text-sm">
              <thead className="bg-muted text-xs muted">
                <tr>
                  <th scope="col" className="px-5 py-3 font-medium">
                    {t("Ticket")}
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    {t("Publication status")}
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    {t("Environment")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((ticket) => (
                  <tr
                    key={ticket.id}
                    className={
                      selectedId === ticket.id
                        ? "bg-muted"
                        : "hover:bg-muted/50"
                    }
                  >
                    <td className="border-t px-5 py-4 min-w-48 max-w-sm align-top">
                      <button
                        type="button"
                        className="text-left font-semibold text-primary break-words [overflow-wrap:anywhere]"
                        aria-pressed={selectedId === ticket.id}
                        onClick={() => setSelectedId(ticket.id)}
                      >
                        {ticket.title}
                      </button>
                      <p className="mt-1 text-xs muted break-words">
                        {platformName(ticket.platform)} ·{" "}
                        {ticket.external_key ||
                          ticket.external_id ||
                          t("No external reference")}
                      </p>
                    </td>
                    <td className="border-t px-4 py-4 align-top">
                      <span
                        className="badge"
                        data-state={
                          ticket.status === "PUBLISHED"
                            ? "DONE"
                            : ticket.status === "UNCERTAIN"
                              ? "PAUSED"
                              : ticket.status === "FAILED" ||
                                  ticket.status === "ERROR"
                                ? "ERROR"
                                : ticket.status === "PUBLISHING"
                                  ? "RUNNING"
                                  : "QUEUED"
                        }
                      >
                        {t(publicationStatuses[ticket.status] || ticket.status)}
                      </span>
                    </td>
                    <td className="border-t px-4 py-4 align-top break-words max-w-40">
                      {ticket.environment_name}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="border-t px-4 py-3 flex flex-wrap items-center justify-between gap-3">
          <Button
            variant="ghost"
            size="sm"
            disabled={page === 1 || loading}
            onClick={() => setPage((value) => value - 1)}
          >
            {t("Previous")}
          </Button>
          <p className="text-xs muted">
            {t("Page {page} · {total} tickets", { page, total: data.total })}
          </p>
          <Button
            variant="ghost"
            size="sm"
            disabled={page * data.page_size >= data.total || loading}
            onClick={() => setPage((value) => value + 1)}
          >
            {t("Next")}
          </Button>
        </div>
      </Card>
      {selected && (
        <Card aria-label={t("Selected ticket")} className="p-4 sm:p-6 min-w-0">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b pb-4">
            <div className="min-w-0">
              <p className="text-xs muted mb-1">{t("Selected ticket")}</p>
              <h2 className="break-words [overflow-wrap:anywhere]">
                {selected.title}
              </h2>
            </div>
            {externalUrl && (
              <Button variant="outline" size="sm" asChild>
                <a href={externalUrl} target="_blank" rel="noopener noreferrer">
                  {t("Open ticket")}
                </a>
              </Button>
            )}
          </div>
          {detailLoading && (
            <p role="status" className="mt-4 muted">
              {t("Loading ticket details…")}
            </p>
          )}
          {detailError && (
            <p role="alert" className="mt-4">
              {t(detailError)} ·{" "}
              {t("Refresh records to retry loading the selected ticket.")}
            </p>
          )}
          {!detailLoading && detail && (
            <div className="mt-5 space-y-6">
              {!detail.payload_available && (
                <p
                  role="status"
                  className="rounded-lg border p-3 text-sm muted"
                >
                  {t(
                    "The submitted content is unavailable for this record. Publication metadata remains visible.",
                  )}
                </p>
              )}
              <div>
                <h3 className="mb-2">{t("Description")}</h3>
                {detail.description ? (
                  <div
                    className="markdown-preview text-sm"
                    data-testid="ticket-description"
                  >
                    <ReactMarkdown>{detail.description}</ReactMarkdown>
                  </div>
                ) : (
                  <p className="text-sm muted">
                    {t("No description was stored.")}
                  </p>
                )}
              </div>
              <div>
                <h3 className="mb-2">{t("Labels / tags")}</h3>
                <div className="flex flex-wrap gap-2">
                  {detail.labels.length ? (
                    detail.labels.map((label, index) => (
                      <span
                        key={`${label}-${index}`}
                        className="rounded-md border bg-muted px-2 py-1 text-xs max-w-full break-words [overflow-wrap:anywhere]"
                      >
                        {label}
                      </span>
                    ))
                  ) : (
                    <p className="text-sm muted">
                      {t("No labels were submitted.")}
                    </p>
                  )}
                </div>
              </div>
              <div className="grid gap-5 sm:grid-cols-2 border-t pt-5">
                <section aria-label={t("Analysis provenance")}>
                  <h3>{t("Analysis provenance")}</h3>
                  <p className="mt-2 text-sm break-words">
                    {detail.environment_name} · {platformName(detail.platform)}{" "}
                    · {detail.project}
                  </p>
                  <Link
                    className="inline-block mt-2 text-primary underline text-sm"
                    href={`/requests/${detail.request_id}?version=${detail.version_number}`}
                  >
                    {t("Published analysis · v{number}", {
                      number: detail.version_number,
                    })}
                  </Link>
                  <p className="mt-2 text-xs muted">
                    {t("Created")}: {date(detail.created_at)}
                  </p>
                </section>
                <section aria-label={t("Publication and synchronization")}>
                  <h3>{t("Publication and synchronization")}</h3>
                  <p className="mt-2 text-sm">
                    {t(publicationStatuses[detail.status] || detail.status)}
                  </p>
                  {detail.updated_at && (
                    <p className="mt-2 text-xs muted">
                      {t("Record updated")}: {date(detail.updated_at)}
                    </p>
                  )}
                  <p className="mt-2 text-xs muted">
                    {t(
                      "This is SpecHelper’s publication record, not a live external ticket status. Refresh reloads local records only.",
                    )}
                  </p>
                </section>
              </div>
              {detail.error && (
                <p role="alert" className="rounded-lg border p-3 text-sm">
                  {t(detail.error)}
                </p>
              )}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
