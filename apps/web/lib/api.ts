const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export type SourceHealth = {
  id: number;
  name: string;
  platform: string;
  source_type: string;
  enabled: boolean;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error: string | null;
  events_24h: number;
  status: "Healthy" | "Stale" | "Error" | "Disabled" | string;
};

export type RawEvent = {
  id: number;
  source_id: number;
  platform: string;
  external_id: string | null;
  author: string | null;
  published_at: string | null;
  retrieved_at: string;
  canonical_url: string | null;
  title: string | null;
  raw_text: string | null;
  content_hash: string;
  event_type: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  source_name: string | null;
};

export type Dashboard = {
  healthy: number;
  stale: number;
  error: number;
  disabled: number;
  events_24h_by_group: Record<string, number>;
  recent_events: RawEvent[];
};

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function getDashboard() {
  return apiGet<Dashboard>("/api/dashboard");
}

export function getSourceHealth() {
  return apiGet<SourceHealth[]>("/api/sources/health");
}

export function getEvents(params: Record<string, string | undefined> = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v) qs.set(k, v);
  });
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<RawEvent[]>(`/api/events${suffix}`);
}

export function getEvent(id: number) {
  return apiGet<RawEvent>(`/api/events/${id}`);
}

export { API_BASE };
