const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "https://foodbridge-api-aqg35pktda-el.a.run.app";

function requireApiBase(): string {
  if (!API_BASE) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is required and must point to backend.");
  }
  return API_BASE;
}

// Reads the current Firebase ID token from the DOM (set by AuthProvider)
function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return (window as any).__fbToken ?? null;
}

async function buildHeaders(): Promise<Record<string, string>> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

type CacheEnvelope<T> = { at: number; value: T };
function getCacheKey(path: string): string {
  return `fb_cache:${path}`;
}

export async function apiGet<T>(path: string, fallback?: T): Promise<T> {
  try {
    const base = requireApiBase();
    const headers = await buildHeaders();
    const response = await fetch(`${base}${path}`, { headers, cache: "no-store" });
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || `GET ${path} failed: ${response.status}`);
    }
    return (await response.json()) as T;
  } catch (err) {
    if (fallback !== undefined) return fallback;
    throw err;
  }
}

export async function apiGetCached<T>(path: string, ttlMs = 10000, fallback?: T): Promise<T> {
  if (typeof window !== "undefined") {
    const raw = window.sessionStorage.getItem(getCacheKey(path));
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as CacheEnvelope<T>;
        if (Date.now() - parsed.at <= ttlMs) {
          return parsed.value;
        }
      } catch {
        // ignore parse errors
      }
    }
  }
  const fresh = await apiGet<T>(path, fallback);
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(getCacheKey(path), JSON.stringify({ at: Date.now(), value: fresh }));
  }
  return fresh;
}

export async function apiGetOrFallback<T>(path: string, fallback: T): Promise<T> {
  return apiGet<T>(path, fallback);
}

export async function apiSend<T = any>(path: string, payload: unknown, method: "POST" | "PATCH" = "POST"): Promise<T> {
  const base = requireApiBase();
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${base}${path}`, {
    method,
    headers,
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

/** Multipart (e.g. donation `payload` JSON + food `photo`). Do not set Content-Type — browser sets boundary. */
export async function apiSendForm<T = any>(
  path: string,
  formData: FormData,
  method: "POST" | "PATCH" = "POST"
): Promise<T> {
  const base = requireApiBase();
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${base}${path}`, {
    method,
    headers,
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function replayPendingActions(maxAgeMs = 5 * 60 * 1000): Promise<void> {
  if (typeof window === "undefined") return;
  const pendingKey = "fb_pending_actions";
  const raw = window.localStorage.getItem(pendingKey);
  if (!raw) return;
  const actions = (JSON.parse(raw) as any[]).filter((item) => Date.now() - (item.at || 0) <= maxAgeMs);
  const base = requireApiBase();
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const survivors: any[] = [];
  for (const item of actions) {
    try {
      const res = await fetch(`${base}${item.path}`, {
        method: item.method || "POST",
        headers,
        body: JSON.stringify(item.payload ?? {}),
      });
      if (!res.ok) survivors.push(item);
    } catch {
      survivors.push(item);
    }
  }
  window.localStorage.setItem(pendingKey, JSON.stringify(survivors));
}
