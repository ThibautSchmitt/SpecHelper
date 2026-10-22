"use client";
import { useI18n } from "@/lib/i18n";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Paperclip, Plus, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  send,
  statuses,
  type Environment,
  type RequestItem,
} from "@/lib/api";

export default function Home() {
  const { t, dateLocale } = useI18n();
  const router = useRouter();
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [requests, setRequests] = useState<RequestItem[]>([]);
  const [environment, setEnvironment] = useState("");
  const [need, setNeed] = useState("");
  const [confrontation, setConfrontation] = useState(false);
  const [allowConfrontation, setAllowConfrontation] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ allow_confrontation: boolean }>("/settings")
      .then((v) => setAllowConfrontation(v.allow_confrontation !== false))
      .catch(() => {});
    Promise.all([
      api<Environment[]>("/environments"),
      api<RequestItem[]>("/requests"),
    ])
      .then(([e, r]) => {
        setEnvironments(e);
        setRequests(r);
      })
      .catch((e) => setError(e.message));
  }, []);
  async function analyze(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (files.length > 20)
        throw new Error(t("A maximum of 20 attachments is allowed."));
      if (files.some((file) => file.size > 25 * 1024 * 1024))
        throw new Error(t("Each file must be smaller than 25 MB."));
      if (
        files.some(
          (file) =>
            !/\.(png|jpe?g|gif|webp|pdf|docx|txt|md|csv|json|log)$/i.test(
              file.name,
            ),
        )
      )
        throw new Error(t("One of the file formats is not allowed."));
      let id = draftId;
      if (!id) {
        const created = await send<RequestItem>("/requests", {
          environment_id: Number(environment),
          need,
          confrontation,
        });
        id = created.id;
        setDraftId(id);
      }
      for (let i = uploaded; i < files.length; i++) {
        const body = new FormData();
        body.append("file", files[i]);
        await api(`/requests/${id}/attachments`, { method: "POST", body });
        setUploaded(i + 1);
      }
      await send(`/requests/${id}/analyze`);
      router.push(`/requests/${id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-8">
      <div>
        <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-primary">
          {t("Your workspace")}
        </div>
        <h1>{t("From need to ticket, simply.")}</h1>
        <p className="muted mt-2">
          {t(
            "Describe your idea. SpecHelper assesses its impact and prepares an actionable ticket.",
          )}
        </p>
      </div>
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800"
        >
          {t(error)}
        </div>
      )}
      <div className="grid items-start gap-7">
        <Card>
          <h2 className="flex items-center gap-2">
            <Plus size={19} className="text-primary" /> {t("New request")}
          </h2>
          <form onSubmit={analyze}>
            <div className="field">
              <label htmlFor="environment">{t("Environment")}</label>
              <select
                id="environment"
                required
                value={environment}
                disabled={busy || !!draftId}
                onChange={(e) => setEnvironment(e.target.value)}
              >
                <option value="">{t("Choose an environment")}</option>
                {environments
                  .filter((e) => e.status === "READY")
                  .map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name}
                    </option>
                  ))}
              </select>
              {!environments.some((e) => e.status === "READY") && (
                <p className="mt-2 text-sm muted">
                  {t("No environment is available.")}{" "}
                  <Link href="/admin" className="text-primary underline">
                    {t("Set up the instance")}
                  </Link>
                </p>
              )}
            </div>
            <div className="field">
              <label htmlFor="need">{t("Describe your need")}</label>
              <Textarea
                id="need"
                required
                minLength={10}
                maxLength={30000}
                className="min-h-48"
                value={need}
                disabled={busy || !!draftId}
                onChange={(e) => setNeed(e.target.value)}
                placeholder={t(
                  "When a manager updates a contract, I would like…",
                )}
              />
              <p className="mt-2 text-xs muted">
                {t(
                  "Explain who is affected, the expected outcome and any special cases.",
                )}
              </p>
            </div>
            <div className="field">
              <label htmlFor="attachments" className="flex items-center gap-2">
                <Paperclip size={16} /> {t("Attachments")}{" "}
                <span className="font-normal muted">{t("(optional)")}</span>
              </label>
              <input
                id="attachments"
                type="file"
                multiple
                disabled={busy || !!draftId}
                accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.docx,.txt,.md,.csv,.json,.log"
                onChange={(e) => setFiles(Array.from(e.target.files || []))}
                className="w-full text-sm file:mr-3 file:rounded-md file:border file:bg-muted file:px-3 file:py-2"
              />
              <p className="mt-2 text-xs muted">
                {t(
                  "Images, PDF, Word or text · 25 MB per file · up to 20 files.",
                )}
              </p>
            </div>
            {allowConfrontation && (
              <div className="mt-6">
                <label className="flex items-center gap-2 text-sm font-medium">
                  <input
                    type="checkbox"
                    checked={confrontation}
                    disabled={busy || !!draftId}
                    onChange={(e) => setConfrontation(e.target.checked)}
                  />
                  {t("Compare multiple analyses")}
                </label>
                <p className="mt-2 text-xs muted">
                  {t(
                    "Compare two independent analyses before preparing the ticket. This option may take longer.",
                  )}
                </p>
              </div>
            )}
            <Button className="mt-7 w-full" disabled={busy || !environment}>
              <Sparkles size={17} />
              {busy
                ? t("Sending your request…")
                : draftId
                  ? t("Resume submission")
                  : t("Analyze request")}
              <ArrowRight size={17} />
            </Button>
          </form>
        </Card>
        <div className="space-y-5">
          <Card className="border-primary/20">
            <h2>{t("Analysis grounded in your project")}</h2>
            <ol className="mt-5 space-y-5 text-sm">
              {[
                t("You describe the desired outcome."),
                t("SpecHelper asks questions when needed."),
                t("The analysis uses your environment."),
                t("You receive a ticket ready to share."),
              ].map((t, i) => (
                <li className="flex gap-3" key={t}>
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-primary text-xs font-bold">
                    {i + 1}
                  </span>
                  <span>{t}</span>
                </li>
              ))}
            </ol>
          </Card>
          <p className="px-2 text-sm muted">
            {t(
              "Analysis may take a few minutes. You can return to your requests at any time.",
            )}
          </p>
        </div>
      </div>
      <section>
        <h2 className="mb-4">
          {t("Recent requests")}{" "}
          <span className="ml-2 text-sm font-normal muted">
            {requests.length}
          </span>
        </h2>
        {requests.length ? (
          <div className="overflow-hidden rounded-xl border bg-card">
            {requests.map((r) => (
              <Link
                key={r.id}
                href={`/requests/${r.id}`}
                className="flex items-center justify-between gap-4 border-b p-5 last:border-0 hover:bg-muted"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{r.need}</p>
                  <p className="mt-1 text-xs muted">
                    {r.environment_name} ·{" "}
                    {new Date(r.created_at).toLocaleDateString(dateLocale)}
                  </p>
                </div>
                <span className="badge shrink-0" data-state={r.status}>
                  {t(statuses[r.status] || r.status)}
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <Card className="py-10 text-center muted">
            {t("Your requests will appear here.")}
          </Card>
        )}
      </section>
    </div>
  );
}
