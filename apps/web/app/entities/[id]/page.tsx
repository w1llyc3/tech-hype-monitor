"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EntityMetrics, getEntityMetrics } from "@/lib/api";

function fmt(ts: string | null) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

export default function EntityDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  const [data, setData] = useState<EntityMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(id)) {
      setError("Invalid entity id");
      return;
    }
    getEntityMetrics(id)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  if (error) {
    return (
      <main>
        <h1>Entity</h1>
        <p className="sub">{error}</p>
      </main>
    );
  }
  if (!data) {
    return (
      <main>
        <h1>Entity</h1>
        <p className="sub">Loading…</p>
      </main>
    );
  }

  const e = data.entity;
  const metrics = Object.keys(data.series);

  return (
    <main>
      <h1>{e.display_name || e.external_id}</h1>
      <p className="sub">
        {e.platform} · {e.entity_type} · first seen {fmt(e.first_seen_at)} · last seen{" "}
        {fmt(e.last_seen_at)}
      </p>
      <p>
        <a href={e.canonical_url || undefined} target="_blank" rel="noreferrer">
          {e.canonical_url || "No URL"}
        </a>
      </p>

      <section className="panel" style={{ marginBottom: 16 }}>
        <h2>Metadata</h2>
        <pre>{JSON.stringify(e.metadata_json, null, 2)}</pre>
      </section>

      {metrics.length === 0 ? (
        <p className="empty">Not enough history yet</p>
      ) : (
        metrics.map((metric) => {
          const points = data.series[metric] || [];
          const chart = points
            .filter((p) => p.value != null)
            .map((p) => ({
              t: new Date(p.observed_at).toLocaleString(),
              value: p.value as number,
            }));
          return (
            <section className="panel" key={metric} style={{ marginBottom: 16 }}>
              <h2>{metric}</h2>
              {chart.length < 2 ? (
                <p className="empty">Not enough history yet</p>
              ) : (
                <div style={{ width: "100%", height: 220 }}>
                  <ResponsiveContainer>
                    <LineChart data={chart}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#2a3542" />
                      <XAxis dataKey="t" stroke="#8b9aab" hide />
                      <YAxis stroke="#8b9aab" />
                      <Tooltip
                        contentStyle={{ background: "#171e26", border: "1px solid #2a3542" }}
                      />
                      <Line type="monotone" dataKey="value" stroke="#3d9cf0" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </section>
          );
        })
      )}
    </main>
  );
}
