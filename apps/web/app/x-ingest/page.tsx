"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useMemo, useState } from "react";
import { ManualIngestResult, manualXIngest } from "@/lib/api";

function XIngestForm() {
  const params = useSearchParams();
  const router = useRouter();
  const [url, setUrl] = useState(params.get("url") || "");
  const [handle, setHandle] = useState(params.get("handle") || "");
  const [postedAt, setPostedAt] = useState("");
  const [postType, setPostType] = useState("original");
  const [text, setText] = useState("");
  const [parentUrl, setParentUrl] = useState("");
  const [quotedUrl, setQuotedUrl] = useState("");
  const [likes, setLikes] = useState("");
  const [reposts, setReposts] = useState("");
  const [replies, setReplies] = useState("");
  const [views, setViews] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ManualIngestResult | null>(null);

  const bookmarklet = useMemo(() => {
    const code = `javascript:(function(){window.open('http://localhost:3000/x-ingest?url='+encodeURIComponent(location.href),'_blank')})();`;
    return code;
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const visible_metrics: Record<string, number> = {};
      if (likes) visible_metrics.likes = Number(likes);
      if (reposts) visible_metrics.reposts = Number(reposts);
      if (replies) visible_metrics.replies = Number(replies);
      if (views) visible_metrics.views = Number(views);
      const res = await manualXIngest({
        url,
        handle,
        text,
        posted_at: postedAt ? new Date(postedAt).toISOString() : null,
        post_type: postType,
        parent_url: parentUrl || null,
        quoted_url: quotedUrl || null,
        visible_metrics: Object.keys(visible_metrics).length ? visible_metrics : null,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>X Manual Ingest</h1>
      <p className="sub">Paste an X post. No scraping — local evidence only.</p>

      <section className="panel" style={{ marginBottom: 16 }}>
        <form onSubmit={onSubmit} className="form-grid">
          <label>
            X URL
            <input required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://x.com/.../status/..." />
          </label>
          <label>
            Handle
            <input required value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="@karpathy" />
          </label>
          <label>
            Posted time
            <input type="datetime-local" value={postedAt} onChange={(e) => setPostedAt(e.target.value)} />
          </label>
          <label>
            Post type
            <select value={postType} onChange={(e) => setPostType(e.target.value)}>
              <option value="original">original</option>
              <option value="reply">reply</option>
              <option value="quote">quote</option>
              <option value="repost">repost</option>
              <option value="unknown">unknown</option>
            </select>
          </label>
          <label className="full">
            Post text
            <textarea required rows={6} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <label>
            Parent URL
            <input value={parentUrl} onChange={(e) => setParentUrl(e.target.value)} />
          </label>
          <label>
            Quoted URL
            <input value={quotedUrl} onChange={(e) => setQuotedUrl(e.target.value)} />
          </label>
          <label>
            Likes
            <input value={likes} onChange={(e) => setLikes(e.target.value)} />
          </label>
          <label>
            Reposts
            <input value={reposts} onChange={(e) => setReposts(e.target.value)} />
          </label>
          <label>
            Replies
            <input value={replies} onChange={(e) => setReplies(e.target.value)} />
          </label>
          <label>
            Views
            <input value={views} onChange={(e) => setViews(e.target.value)} />
          </label>
          <div className="full">
            <button className="btn" type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save & Analyze"}
            </button>
          </div>
        </form>
      </section>

      {error && <p className="sub">Error: {error}</p>}

      {result && (
        <section className="panel">
          <h2>Result</h2>
          <p>
            Known monitored account:{" "}
            <strong>{result.known_account ? "yes" : "no — Unknown account"}</strong>
          </p>
          <p>Raw event saved: #{result.raw_event_id}{result.created_raw ? " (new)" : " (deduped)"}</p>
          <p>Candidate signals extracted: {result.candidate_signals_extracted}</p>
          {result.candidate_signal_ids.length > 0 && (
            <p>
              <Link href="/candidate-inbox">Open Candidate Inbox →</Link>
            </p>
          )}
          {!result.known_account && (
            <p className="muted">Raw event kept. Create/link account later if needed.</p>
          )}
          <button type="button" className="btn" onClick={() => router.push("/candidate-inbox")}>
            Review signals
          </button>
        </section>
      )}

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Bookmarklet helper</h2>
        <p className="muted">Drag this to bookmarks (opens ingest with current URL):</p>
        <a className="mono" href={bookmarklet}>
          THM X Ingest
        </a>
      </section>
    </main>
  );
}

export default function XIngestPage() {
  return (
    <Suspense fallback={<main><h1>X Manual Ingest</h1><p className="sub">Loading…</p></main>}>
      <XIngestForm />
    </Suspense>
  );
}
