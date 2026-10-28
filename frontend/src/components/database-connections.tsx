"use client";
import { useI18n } from "@/lib/i18n";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { send } from "@/lib/api";

export type DatabaseConnection = {
  id: number;
  name: string;
  status: string;
  host: string;
  database: string;
};
type Probe = {
  status: string;
  checks: { connection: boolean; read: boolean; read_only: boolean };
};
const empty = {
  name: "",
  url: "",
  host: "",
  port: 5432,
  database: "",
  username: "",
  password: "",
  sslmode: "require",
};

export function DatabaseConnections({
  values,
  onChanged,
}: {
  values: DatabaseConnection[];
  onChanged: () => Promise<void>;
}) {
  const { t } = useI18n();
  const [show, setShow] = useState(false);
  const [useURL, setUseURL] = useState(false);
  const [value, setValue] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [checks, setChecks] = useState<Probe["checks"] | null>(null);
  async function probe(id?: number) {
    setBusy(true);
    setError("");
    setChecks(null);
    try {
      const result = await send<Probe>(
        id ? `/connections/databases/${id}/test` : "/connections/databases",
        id
          ? undefined
          : {
              ...value,
              url: useURL ? value.url : "",
              host: useURL ? "" : value.host,
            },
      );
      setChecks(result.checks);
      await onChanged();
      if (!id) {
        setValue(empty);
        setShow(false);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card aria-label={t("PostgreSQL connections")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2>
          {t("PostgreSQL connections")}{" "}
          <span className="text-sm font-normal muted">{t("optional")}</span>
        </h2>
        <Button
          variant="outline"
          onClick={() => {
            setShow(!show);
            setError("");
            setChecks(null);
          }}
        >
          {show ? t("Close") : t("Add connection")}
        </Button>
      </div>
      <p className="mt-3 text-sm muted">
        {t(
          "Associate a database with an environment only if the analysis needs it. Use read-only access.",
        )}
      </p>
      {values.map((database) => (
        <div
          key={database.id}
          className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3"
        >
          <div>
            <p className="font-medium">{database.name}</p>
            <p className="text-xs muted">
              {database.status === "CONNECTED"
                ? t("Connection verified")
                : t("Connection needs verification")}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => probe(database.id)}
          >
            {t("Test connection")}
          </Button>
        </div>
      ))}
      {show && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            probe();
          }}
        >
          <div className="field">
            <label htmlFor="db-name">{t("Connection name")}</label>
            <Input
              id="db-name"
              required
              maxLength={100}
              value={value.name}
              onChange={(e) => setValue({ ...value, name: e.target.value })}
            />
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={useURL}
              onChange={(e) => setUseURL(e.target.checked)}
            />
            {t("Use a PostgreSQL URL")}
          </label>
          {useURL ? (
            <div className="field">
              <label htmlFor="db-url">{t("PostgreSQL URL")}</label>
              <Input
                id="db-url"
                type="password"
                required
                maxLength={2048}
                autoComplete="off"
                placeholder={t("postgresql://host/database")}
                value={value.url}
                onChange={(e) => setValue({ ...value, url: e.target.value })}
              />
              <p className="mt-2 text-xs muted">
                {t(
                  "The username and password can be included in the URL or entered below.",
                )}
              </p>
            </div>
          ) : (
            <div className="grid gap-x-5 sm:grid-cols-2">
              {[
                { key: "host", label: t("Host") },
                { key: "port", label: t("Port") },
                { key: "database", label: t("Database") },
              ].map((field) => (
                <div className="field" key={field.key}>
                  <label htmlFor={`db-${field.key}`}>{t(field.label)}</label>
                  <Input
                    id={`db-${field.key}`}
                    required
                    type={field.key === "port" ? "number" : "text"}
                    value={value[field.key as "host" | "port" | "database"]}
                    onChange={(e) =>
                      setValue({
                        ...value,
                        [field.key]:
                          field.key === "port"
                            ? Number(e.target.value)
                            : e.target.value,
                      })
                    }
                  />
                </div>
              ))}
            </div>
          )}
          <div className="grid gap-x-5 sm:grid-cols-2">
            <div className="field">
              <label htmlFor="db-username">{t("PostgreSQL username")}</label>
              <Input
                id="db-username"
                required={!useURL}
                maxLength={100}
                value={value.username}
                onChange={(e) =>
                  setValue({ ...value, username: e.target.value })
                }
              />
            </div>
            <div className="field">
              <label htmlFor="db-password">{t("Password")}</label>
              <Input
                id="db-password"
                type="password"
                required={!useURL}
                maxLength={1000}
                autoComplete="new-password"
                value={value.password}
                onChange={(e) =>
                  setValue({ ...value, password: e.target.value })
                }
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="db-sslmode">{t("TLS encryption")}</label>
            <select
              id="db-sslmode"
              value={value.sslmode}
              onChange={(e) => setValue({ ...value, sslmode: e.target.value })}
            >
              <option value="require">{t("Require TLS")}</option>
              <option value="verify-full">
                {t("Verify certificate and host")}
              </option>
              <option value="verify-ca">{t("Verify certificate")}</option>
              <option value="disable">{t("Disabled (local network)")}</option>
            </select>
          </div>
          <Button className="mt-5" disabled={busy}>
            {busy ? t("Verifying…") : t("Test connection")}
          </Button>
          <p className="mt-2 text-xs muted">
            {t("A verified connection is saved for your environments.")}
          </p>
        </form>
      )}
      {checks && (
        <div
          role="status"
          className="mt-4 flex flex-wrap gap-3 text-sm text-green-800"
        >
          <span>{t("✓ Connection OK")}</span>
          <span>{t("✓ Read query OK")}</span>
          <span>{t("✓ Read-only")}</span>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {t(error)}
        </p>
      )}
    </Card>
  );
}
