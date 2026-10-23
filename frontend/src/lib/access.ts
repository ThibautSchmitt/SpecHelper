export type AccessSession = {
  mode: "local" | "password" | "unconfigured";
  authenticated: boolean;
  csrf_token: string;
  expires_at: string | null;
};

let current: AccessSession | null = null;
let pending: Promise<AccessSession> | null = null;

export async function accessSession(force = false): Promise<AccessSession> {
  if (current && !force) return current;
  if (pending && !force) return pending;
  const task = fetch("/api/access/session", { cache: "no-store", credentials: "same-origin" })
    .then(async (response) => {
      if (!response.ok) throw new Error("Instance access is unavailable. Check the server configuration.");
      const value: AccessSession = await response.json();
      current = value;
      return value;
    });
  pending = task;
  try { return await task; } finally { if (pending === task) pending = null; }
}

export function clearAccess() { current = null; }

export async function secureFetch(input: string, options: RequestInit = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const session = await accessSession();
    if (session.csrf_token) headers.set("X-CSRFToken", session.csrf_token);
  }
  const response = await fetch(input, { ...options, credentials: "same-origin", headers });
  if (response.status === 401) {
    current = null;
    window.dispatchEvent(new Event("access-required"));
  }
  return response;
}
