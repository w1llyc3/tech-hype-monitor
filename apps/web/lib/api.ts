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

export type AccountListItem = {
  id: number;
  platform: string;
  handle: string;
  display_name: string | null;
  primary_bucket: string | null;
  secondary_role: string | null;
  universe_tier: string | null;
  monitor_priority: string | null;
  conflict_risk: string | null;
  tech_to_crypto_relevance: string | null;
  enabled: boolean;
  last_ingested_post_at: string | null;
  events_30d: number;
  open_candidate_signals: number;
};

export type CandidateSignal = {
  id: number;
  raw_event_id: number;
  account_event_id: number | null;
  signal_type: string;
  candidate_text: string;
  normalized_text: string;
  extraction_method: string;
  source_role: string | null;
  trigger_reason: string | null;
  initial_priority: string | null;
  state: string;
  linked_hype_id: number | null;
  merged_into_signal_id: number | null;
  created_at: string;
  reviewed_at: string | null;
  review_note: string | null;
  account_handle: string | null;
  conflict_risk: string | null;
  post_preview: string | null;
  source_url: string | null;
  suggested_hype_ids: number[];
};

export type HypeCandidate = {
  id: number;
  canonical_name: string;
  plain_english: string | null;
  hype_unit_type: string | null;
  formation_pattern: string | null;
  public_disclosure_t0?: string | null;
  breakout_origin_t0?: string | null;
  candidate_status: string;
  created_at: string;
  last_activity_at: string | null;
  updated_at: string;
  aliases?: { id: number; alias: string; normalized_alias: string; alias_type: string | null }[];
  origin_account?: string | null;
  initial_trigger?: string | null;
  independent_accounts?: number | null;
  platforms?: number | null;
  github_repos?: number | null;
  hf_spaces?: number | null;
  hn_stories?: number | null;
  last_snapshot_at?: string | null;
  next_checkpoint?: string | null;
  next_checkpoint_due_at?: string | null;
  github_repos_preexisting?: number | null;
  hf_spaces_preexisting?: number | null;
  total_monitored_accounts?: number | null;
};

export type TimelineItem = {
  kind: string;
  at: string;
  title: string;
  detail: string | null;
  ref_id: number | null;
};

export type CandidateSnapshot = {
  id: number;
  hype_id: number;
  snapshot_at: string;
  checkpoint: string | null;
  mention_count: number | null;
  independent_account_count: number | null;
  high_quality_amplifier_count: number | null;
  platform_count: number | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
};

export type SnapshotSchedule = {
  id: number;
  hype_id: number;
  checkpoint: string;
  due_at: string;
  completed_at: string | null;
  status: string;
  attempts: number;
  last_error: string | null;
  skip_reason: string | null;
  created_at: string;
  updated_at: string;
  snapshot_at: string | null;
  late_by_seconds: number | null;
  timing_quality: string | null;
  scheduled_due_at: string | null;
};

export type ManualIngestResult = {
  raw_event_id: number;
  account_id: number | null;
  account_event_id: number | null;
  known_account: boolean;
  created_raw: boolean;
  candidate_signal_ids: number[];
  suggested_hype_ids: number[];
  candidate_signals_extracted: number;
};

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function apiSend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed: ${res.status} ${text}`);
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

export function getAccounts(params: Record<string, string | undefined> = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v) qs.set(k, v);
  });
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<AccountListItem[]>(`/api/accounts${suffix}`);
}

export function getCandidateSignals(params: Record<string, string | undefined> = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, v);
  });
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<CandidateSignal[]>(`/api/candidate-signals${suffix}`);
}

export function acceptSignal(id: number, body: Record<string, unknown> = {}) {
  return apiSend<HypeCandidate>(`/api/candidate-signals/${id}/accept`, "POST", body);
}

export function attachSignal(id: number, hypeId: number) {
  return apiSend<CandidateSignal>(`/api/candidate-signals/${id}/attach`, "POST", {
    hype_id: hypeId,
  });
}

export function rejectSignal(id: number, reason?: string, note?: string) {
  return apiSend<CandidateSignal>(`/api/candidate-signals/${id}/reject`, "POST", {
    reason,
    note,
  });
}

export function mergeSignal(id: number, intoSignalId: number) {
  return apiSend<CandidateSignal>(`/api/candidate-signals/${id}/merge`, "POST", {
    into_signal_id: intoSignalId,
  });
}

export function getHypeCandidates(params: Record<string, string | undefined> = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v) qs.set(k, v);
  });
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<HypeCandidate[]>(`/api/hype-candidates${suffix}`);
}

export function getHypeCandidate(id: number) {
  return apiGet<HypeCandidate>(`/api/hype-candidates/${id}`);
}

export function patchHypeCandidate(id: number, body: Record<string, unknown>) {
  return apiSend<HypeCandidate>(`/api/hype-candidates/${id}`, "PATCH", body);
}

export function addHypeAlias(id: number, alias: string) {
  return apiSend(`/api/hype-candidates/${id}/aliases`, "POST", { alias });
}

export function getHypeTimeline(id: number) {
  return apiGet<TimelineItem[]>(`/api/hype-candidates/${id}/timeline`);
}

export function getHypeSnapshots(id: number) {
  return apiGet<CandidateSnapshot[]>(`/api/hype-candidates/${id}/snapshots`);
}

export function getHypeSchedule(id: number) {
  return apiGet<SnapshotSchedule[]>(`/api/hype-candidates/${id}/schedule`);
}

export function manualXIngest(body: Record<string, unknown>) {
  return apiSend<ManualIngestResult>("/api/x/manual-ingest", "POST", body);
}

export function promoteEvent(eventId: number, body: Record<string, unknown>) {
  return apiSend<CandidateSignal>(`/api/events/${eventId}/promote`, "POST", body);
}

export { API_BASE };
