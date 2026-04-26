import type { QueryResponse } from "./types";

function trimBase(url: string): string {
  return url.replace(/\/$/, "");
}

export function getBackendBase(): string | null {
  const u = process.env.NEXT_PUBLIC_BACKEND_URL?.trim();
  return u ? trimBase(u) : null;
}

export async function postQuery(
  query: string,
  opts?: { originLat?: number; originLng?: number; useLlmValidator?: boolean }
): Promise<QueryResponse> {
  const base = getBackendBase();
  if (!base) throw new Error("NEXT_PUBLIC_BACKEND_URL is not set");

  const r = await fetch(`${base}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      ...(opts?.originLat != null && opts?.originLng != null
        ? { origin_lat: opts.originLat, origin_lng: opts.originLng }
        : {}),
      use_llm_validator: opts?.useLlmValidator ?? true,
    }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`HTTP ${r.status}: ${t.slice(0, 400)}`);
  }
  return r.json() as Promise<QueryResponse>;
}

export async function getHealth(): Promise<{ ok: boolean } | null> {
  const base = getBackendBase();
  if (!base) return null;
  try {
    const r = await fetch(`${base}/health`, { method: "GET" });
    if (!r.ok) return { ok: false };
    return r.json() as Promise<{ ok: boolean }>;
  } catch {
    return { ok: false };
  }
}
