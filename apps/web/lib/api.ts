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
  status: string;
  rate_limit_remaining?: number | null;
  rate_limit_reset_at?: string | null;
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
  rate_limited?: number;
  events_24h_by_group: Record<string, number>;
  recent_events: RawEvent[];
  tracked_entities?: Record<string, number>;
  recent_derivative_activity?: Record<string, number>;
};

export type TrackedEntity = {
  id: number;
  source_id: number | null;
  platform: string;
  entity_type: string;
  external_id: string;
  canonical_url: string | null;
  display_name: string | null;
  first_seen_at: string;
  last_seen_at: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type EntityMetrics = {
  entity: TrackedEntity;
  series: Record<string, { observed_at: string; value: number | null; text?: string | null }[]>;
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

export function discoverGithub(q: string, limit = 30) {
  return apiGet<Record<string, unknown>[]>(
    `/api/discovery/github?q=${encodeURIComponent(q)}&limit=${limit}`
  );
}

export function discoverHf(kind: "models" | "datasets" | "spaces", q: string, limit = 30) {
  return apiGet<Record<string, unknown>[]>(
    `/api/discovery/huggingface/${kind}?q=${encodeURIComponent(q)}&limit=${limit}`
  );
}

export function getEntity(id: number) {
  return apiGet<TrackedEntity>(`/api/entities/${id}`);
}

export function getEntityMetrics(id: number) {
  return apiGet<EntityMetrics>(`/api/entities/${id}/metrics`);
}

export function listEntities(params: Record<string, string | undefined> = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v) qs.set(k, v);
  });
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<TrackedEntity[]>(`/api/entities${suffix}`);
}

export { API_BASE };
