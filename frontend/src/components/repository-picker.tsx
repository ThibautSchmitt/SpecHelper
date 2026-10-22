"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { GitConnection } from "@/components/git-sources";

type Project = {
  id: string | number;
  remote_id: string;
  path: string;
  default_branch: string;
  is_fork: boolean;
  parent: { path: string; url: string } | null;
};
type Page<T> = { items: T[]; has_more: boolean };
export type SourceSelection = {
  git_connection_id?: number;
  remote_id?: string;
  repository: string;
  branch: string;
  is_fork?: boolean;
  parent?: { path: string; url: string } | null;
};
export function sourcePayload(value: SourceSelection) {
  return value.git_connection_id && value.remote_id
    ? {
        git_connection_id: value.git_connection_id,
        remote_id: value.remote_id,
        branch: value.branch,
      }
    : { repository: value.repository, branch: value.branch };
}
export function duplicateSources(values: SourceSelection[]) {
  const keys = values.map(
    (v) =>
      `${v.git_connection_id || "legacy"}:${v.remote_id || v.repository}:${v.branch}`,
  );
  return new Set(keys).size !== keys.length;
}
export function RepositoryPicker({
  values,
  onChange,
  disabled,
  prefix,
}: {
  values: SourceSelection[];
  onChange: (value: SourceSelection[]) => void;
  disabled?: boolean;
  prefix: string;
}) {
  const { t } = useI18n();
  const [connections, setConnections] = useState<GitConnection[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    api<GitConnection[]>("/git-connections")
      .then((v) => {
        if (alive) setConnections(v);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, []);
  function update(index: number, value: SourceSelection) {
    onChange(values.map((row, i) => (i === index ? value : row)));
  }
  return (
    <div className="mt-5 space-y-4">
      <h3>{t("Projects and versions")}</h3>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {t(error)}
        </p>
      )}
      {values.map((value, index) => (
        <RepositoryRow
          key={`${prefix}-${index}`}
          value={value}
          connections={connections}
          onChange={(v) => update(index, v)}
          disabled={disabled}
          id={`${prefix}-${index}`}
          number={index + 1}
          onRemove={
            values.length > 1
              ? () => onChange(values.filter((_, i) => i !== index))
              : undefined
          }
        />
      ))}
      {duplicateSources(values) && (
        <p role="alert" className="text-sm text-red-700">
          {t("This connection, project and branch are already selected.")}
        </p>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() => onChange([...values, { repository: "", branch: "" }])}
      >
        {t("Add a project")}
      </Button>
    </div>
  );
}
function RepositoryRow({
  value,
  connections,
  onChange,
  disabled,
  id,
  number,
  onRemove,
}: {
  value: SourceSelection;
  connections: GitConnection[];
  onChange: (value: SourceSelection) => void;
  disabled?: boolean;
  id: string;
  number: number;
  onRemove?: () => void;
}) {
  const { t } = useI18n();
  const [projects, setProjects] = useState<Project[]>([]);
  const [branches, setBranches] = useState<{ name: string }[]>([]);
  const [search, setSearch] = useState("");
  const [branchSearch, setBranchSearch] = useState("");
  const [projectPage, setProjectPage] = useState(1);
  const [branchPage, setBranchPage] = useState(1);
  const [moreProjects, setMoreProjects] = useState(false);
  const [moreBranches, setMoreBranches] = useState(false);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [loadingBranches, setLoadingBranches] = useState(false);
  const [error, setError] = useState("");
  const projectsVersion = useRef(0);
  const branchesVersion = useRef(0);
  useEffect(() => {
    const version = ++projectsVersion.current;
    setProjects([]);
    setProjectPage(1);
    setMoreProjects(false);
    setLoadingProjects(false);
    if (!value.git_connection_id) return;
    setLoadingProjects(true);
    const timer = setTimeout(() => {
      api<Page<Project>>(
        `/git-connections/${value.git_connection_id}/projects?search=${encodeURIComponent(search)}&page=1`,
      )
        .then((v) => {
          if (version !== projectsVersion.current) return;
          setProjects(v.items);
          setMoreProjects(v.has_more);
          setError("");
        })
        .catch((e) => {
          if (version === projectsVersion.current) setError(e.message);
        })
        .finally(() => {
          if (version === projectsVersion.current) setLoadingProjects(false);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      projectsVersion.current++;
    };
  }, [value.git_connection_id, search]);
  useEffect(() => {
    const version = ++branchesVersion.current;
    setBranches([]);
    setBranchPage(1);
    setMoreBranches(false);
    setLoadingBranches(false);
    if (!value.git_connection_id || !value.remote_id) return;
    setLoadingBranches(true);
    const timer = setTimeout(() => {
      api<Page<{ name: string }>>(
        `/git-connections/${value.git_connection_id}/branches?remote_id=${encodeURIComponent(value.remote_id!)}&search=${encodeURIComponent(branchSearch)}&page=1`,
      )
        .then((v) => {
          if (version !== branchesVersion.current) return;
          setBranches(v.items);
          setMoreBranches(v.has_more);
          setError("");
        })
        .catch((e) => {
          if (version === branchesVersion.current) setError(e.message);
        })
        .finally(() => {
          if (version === branchesVersion.current) setLoadingBranches(false);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      branchesVersion.current++;
    };
  }, [value.git_connection_id, value.remote_id, branchSearch]);
  async function more(kind: "projects" | "branches") {
    const isProjects = kind === "projects";
    const version = isProjects
      ? projectsVersion.current
      : branchesVersion.current;
    const page = (isProjects ? projectPage : branchPage) + 1;
    if (isProjects) setLoadingProjects(true);
    else setLoadingBranches(true);
    try {
      const result = await api<Page<Project & { name: string }>>(
        `/git-connections/${value.git_connection_id}/${kind}?search=${encodeURIComponent(isProjects ? search : branchSearch)}&page=${page}${isProjects ? "" : `&remote_id=${encodeURIComponent(value.remote_id!)}`}`,
      );
      if (
        version !==
        (isProjects ? projectsVersion.current : branchesVersion.current)
      )
        return;
      if (isProjects) {
        setProjects((old) => [...old, ...result.items]);
        setProjectPage(page);
        setMoreProjects(result.has_more);
      } else {
        setBranches((old) => [...old, ...result.items]);
        setBranchPage(page);
        setMoreBranches(result.has_more);
      }
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      if (
        version ===
        (isProjects ? projectsVersion.current : branchesVersion.current)
      ) {
        if (isProjects) setLoadingProjects(false);
        else setLoadingBranches(false);
      }
    }
  }
  const selected = projects.find(
    (p) => String(p.remote_id || p.id) === value.remote_id,
  );
  return (
    <fieldset disabled={disabled} className="min-w-0 rounded-lg border p-4">
      <legend className="px-1 text-sm font-medium">
        {t("Project")} {number}
      </legend>
      <div className="field">
        <label htmlFor={`${id}-connection`}>{t("Git connection")}</label>
        <select
          id={`${id}-connection`}
          required={!value.repository}
          value={value.git_connection_id || ""}
          onChange={(e) => {
            setSearch("");
            setBranchSearch("");
            setError("");
            onChange({
              git_connection_id: Number(e.target.value) || undefined,
              remote_id: "",
              repository: "",
              branch: "",
            });
          }}
        >
          <option value="">
            {value.repository && !value.git_connection_id
              ? t("Existing source")
              : t("Choose a connection")}
          </option>
          {connections.map((c) => (
            <option
              key={c.id}
              value={c.id}
              disabled={!c.enabled && c.id !== value.git_connection_id}
            >
              {c.name} · {c.provider === "github" ? "GitHub" : "GitLab"}
              {!c.enabled ? ` · ${t("Disabled")}` : ""}
            </option>
          ))}
        </select>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-search`}>{t("Search projects")}</label>
          <Input
            id={`${id}-search`}
            disabled={!value.git_connection_id}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <label className="mt-3 block" htmlFor={`${id}-repository`}>
            {t("Project")} {number}
          </label>
          <select
            id={`${id}-repository`}
            required
            disabled={!value.git_connection_id && !value.repository}
            value={value.remote_id || value.repository}
            onChange={(e) => {
              const project = projects.find(
                (p) => String(p.remote_id || p.id) === e.target.value,
              );
              setBranchSearch("");
              onChange({
                ...value,
                remote_id: project
                  ? String(project.remote_id || project.id)
                  : "",
                repository: project?.path || "",
                branch: "",
                is_fork: project?.is_fork,
                parent: project?.parent,
              });
            }}
          >
            <option value="">{t("Choose a project")}</option>
            {(value.remote_id || value.repository) && !selected && (
              <option value={value.remote_id || value.repository}>
                {value.repository}
              </option>
            )}
            {projects.map((p) => (
              <option
                key={String(p.remote_id || p.id)}
                value={String(p.remote_id || p.id)}
              >
                {p.path}
                {p.is_fork ? ` · ${t("Fork")}` : ""}
              </option>
            ))}
          </select>
          {loadingProjects && (
            <p role="status" className="mt-2 text-xs muted">
              {t("Loading projects…")}
            </p>
          )}
          {moreProjects && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={loadingProjects}
              onClick={() => more("projects")}
            >
              {t("More projects")}
            </Button>
          )}
        </div>
        <div>
          <label htmlFor={`${id}-branch-search`}>{t("Search branches")}</label>
          <Input
            id={`${id}-branch-search`}
            disabled={!value.remote_id}
            value={branchSearch}
            onChange={(e) => setBranchSearch(e.target.value)}
          />
          <label className="mt-3 block" htmlFor={`${id}-branch`}>
            {t("Version")} {number}
          </label>
          <select
            id={`${id}-branch`}
            required
            disabled={!value.remote_id && !value.branch}
            value={value.branch}
            onChange={(e) => onChange({ ...value, branch: e.target.value })}
          >
            <option value="">{t("Choose a version")}</option>
            {value.branch && !branches.some((b) => b.name === value.branch) && (
              <option>{value.branch}</option>
            )}
            {branches.map((b) => (
              <option key={b.name}>{b.name}</option>
            ))}
          </select>
          {loadingBranches && (
            <p role="status" className="mt-2 text-xs muted">
              {t("Loading branches…")}
            </p>
          )}
          {moreBranches && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={loadingBranches}
              onClick={() => more("branches")}
            >
              {t("More versions")}
            </Button>
          )}
        </div>
      </div>
      {(selected?.is_fork || value.is_fork) && (
        <p className="mt-3 break-words text-xs muted">
          {t("Fork")}
          {(selected?.parent || value.parent)?.path &&
            ` · ${t("Parent repository")}: ${(selected?.parent || value.parent)?.path}`}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {t(error)}
        </p>
      )}
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="mt-3"
        disabled={!onRemove}
        aria-label={t("Remove project {number}", { number })}
        onClick={onRemove}
      >
        {t("Remove")}
      </Button>
    </fieldset>
  );
}
