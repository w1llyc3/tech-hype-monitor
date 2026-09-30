"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Dashboard, getDashboard } from "@/lib/api";

function fmt(ts: string | null) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

export default function HomePage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboard()
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <main>
        <h1>Dashboard</h1>
        <p className="sub">Could not reach API: {error}</p>
      </main>
    );
  }

  if (!data) {
    return (
      <main>
        <h1>Dashboard</h1>
        <p className="sub">Loading…</p>
      </main>
    );
  }

  const chartData = Object.entries(data.events_24h_by_group).map(([name, value]) => ({
    name,
    value,
  }));

  return (
    <main>
      <h1>Dashboard</h1>
      <p className="sub">
        Source status, tracked entities, and recent evidence. Discovery is descriptive — not hype scoring.
      </p>

      <section className="grid grid-4" style={{ marginBottom: 16 }}>
        <div className="panel">
          <div className="stat" style={{ color: "var(--ok)" }}>{data.healthy}</div>
          <div className="stat-label">Healthy</div>
        </div>
        <div className="panel">
          <div className="stat" style={{ color: "var(--warn)" }}>{data.stale}</div>
          <div className="stat-label">Stale</div>
        </div>
        <div className="panel">
          <div className="stat" style={{ color: "var(--bad)" }}>{data.error}</div>
          <div className="stat-label">Error</div>
        </div>
        <div className="panel">
          <div className="stat" style={{ color: "var(--disabled)" }}>
            {data.disabled}
            {data.rate_limited ? ` / RL ${data.rate_limited}` : ""}
          </div>
          <div className="stat-label">Disabled / Rate Limited</div>
        </div>
      </section>

      <section className="grid grid-2">
        <div className="panel">
          <h2>Events 24h</h2>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a3542" />
                <XAxis dataKey="name" stroke="#8b9aab" />
                <YAxis stroke="#8b9aab" allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "#171e26", border: "1px solid #2a3542" }}
                />
                <Bar dataKey="value" fill="#3d9cf0" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="panel">
          <h2>Tracked Entities</h2>
          {Object.entries(data.tracked_entities || {}).map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span className="muted">{k}</span>
              <strong>{v}</strong>
            </div>
          ))}
          <h2 style={{ marginTop: 18 }}>Recent derivative activity (24h)</h2>
          {Object.entries(data.recent_derivative_activity || {}).map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span className="muted">{k}</span>
              <strong>{v}</strong>
            </div>
          ))}
          <p className="empty" style={{ marginTop: 12 }}>
            No hype candidates yet. Candidate engine arrives later.
          </p>
          <p>
            <Link href="/discovery">Open Discovery →</Link>
          </p>
        </div>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Recent events</h2>
        {data.recent_events.length === 0 ? (
          <p className="empty">No events yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Platform</th>
                  <th>Source</th>
                  <th>Title</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_events.map((e) => (
                  <tr key={e.id}>
                    <td className="mono">{fmt(e.retrieved_at)}</td>
                    <td>{e.platform}</td>
                    <td>{e.source_name || e.source_id}</td>
                    <td>{e.title || e.raw_text?.slice(0, 80) || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
