"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
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
  environment_name: string;
  request_id: string;
  version_number: number;
  status: string;
  created_at: string;
  error: string;
};
export default function TicketsPage() {
  const { t, dateLocale } = useI18n();
  const [data, setData] = useState<{
    items: Ticket[];
    total: number;
    page: number;
    page_size: number;
    environments?: string[];
  }>({ items: [], total: 0, page: 1, page_size: 20 });
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [platform, setPlatform] = useState("");
  const [environment, setEnvironment] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api<Environment[]>("/environments")
      .then(setEnvironments)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    const timer = setTimeout(
      () =>
        api<typeof data>(
          `/tickets?${new URLSearchParams({ platform, environment, search, page: String(page) })}`,
        )
          .then((v) => {
            if (alive) {
              setData(v);
              setError("");
            }
          })
          .catch((e) => {
            if (alive) setError(e.message);
          })
          .finally(() => {
            if (alive) setLoading(false);
          }),
      200,
    );
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [platform, environment, search, page]);
  return (
    <div className="space-y-6">
      <div>
        <h1>{t("Tickets")}</h1>
        <p className="mt-2 muted">
          {t(
            "Tickets published by SpecHelper, linked to their exact analysis version.",
          )}
        </p>
      </div>
      <Card>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="ticket-search">{t("Search tickets")}</label>
            <Input
              id="ticket-search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div>
            <label htmlFor="ticket-platform">{t("Platform")}</label>
            <select
              id="ticket-platform"
              value={platform}
              onChange={(e) => {
                setPlatform(e.target.value);
                setPage(1);
              }}
            >
              <option value="">{t("All platforms")}</option>
              {["github", "gitlab", "jira", "glpi"].map((p) => (
                <option key={p} value={p}>
                  {p === "github"
                    ? "GitHub"
                    : p === "gitlab"
                      ? "GitLab"
                      : p === "jira"
                        ? "Jira"
                        : "GLPI"}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="ticket-environment">{t("Environment")}</label>
            <select
              id="ticket-environment"
              value={environment}
              onChange={(e) => {
                setEnvironment(e.target.value);
                setPage(1);
              }}
            >
              <option value="">{t("All environments")}</option>
              {(
                data.environments ||
                Array.from(new Set(environments.map((e) => e.name)))
              ).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>
      {error && (
        <p role="alert" className="text-red-700">
          {t(error)}
        </p>
      )}
      {loading && <p role="status">{t("Loading tickets…")}</p>}
      {!loading && !data.items.length && (
        <Card>{t("No published tickets match these filters.")}</Card>
      )}
      <div className="space-y-4">
        {data.items.map((ticket) => (
          <Card key={ticket.id}>
            <div className="flex flex-wrap justify-between gap-3">
              <h2 className="break-words">{ticket.title}</h2>
              <span className="badge">{t(ticket.status)}</span>
            </div>
            <p className="mt-2 break-words text-sm muted">
              {ticket.platform} · {ticket.project} ·{" "}
              {ticket.external_key || ticket.external_id} ·{" "}
              {ticket.environment_name}
            </p>
            <p className="mt-2 text-xs muted">
              {new Date(ticket.created_at).toLocaleString(dateLocale)}
            </p>
            <div className="mt-4 flex flex-wrap gap-4 text-sm">
              <a
                className="text-primary underline"
                href={ticket.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("Open ticket")}
              </a>
              <Link
                className="text-primary underline"
                href={`/requests/${ticket.request_id}?version=${ticket.version_number}`}
              >
                {t("Published analysis · v{number}", {
                  number: ticket.version_number,
                })}
              </Link>
            </div>
            {ticket.error && (
              <p role="alert" className="mt-3 text-red-700">
                {t(ticket.error)}
              </p>
            )}
          </Card>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button
          variant="outline"
          disabled={page === 1 || loading}
          onClick={() => setPage(page - 1)}
        >
          {t("Previous")}
        </Button>
        <p className="text-sm muted">
          {t("Page {page} · {total} tickets", { page, total: data.total })}
        </p>
        <Button
          variant="outline"
          disabled={page * data.page_size >= data.total || loading}
          onClick={() => setPage(page + 1)}
        >
          {t("Next")}
        </Button>
      </div>
    </div>
  );
}
