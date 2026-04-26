"use client";

import { useCallback, useEffect, useState } from "react";
import { getBackendBase, getHealth, postQuery } from "@/lib/api";
import { MOCK_QUERY_RESPONSE } from "@/lib/mock";
import type { Capabilities, HospitalResult, QueryResponse } from "@/lib/types";

const CAP_ORDER: (keyof Capabilities)[] = [
  "has_icu",
  "has_emergency",
  "has_surgery",
  "has_anesthesiologist",
  "has_oxygen",
  "has_oncology",
  "has_dialysis",
  "has_neonatal",
  "has_trauma",
  "has_lab",
  "has_imaging",
  "doctor_type",
];

function capLabel(k: keyof Capabilities): string {
  if (k === "doctor_type") return "Doctor";
  return k.replace("has_", "").replace(/_/g, " ");
}

function scoreColor(s: number): string {
  if (s >= 0.75) return "text-emerald-600";
  if (s >= 0.5) return "text-amber-600";
  return "text-rose-600";
}

function ringColor(s: number): string {
  if (s >= 0.75) return "stroke-emerald-500";
  if (s >= 0.5) return "stroke-amber-500";
  return "stroke-rose-500";
}

function TrustGauge({ score }: { score: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, score)) * 100);
  const dash = 2 * Math.PI * 36;
  const offset = dash * (1 - score);
  return (
    <div className="flex flex-col items-center">
      <svg className="h-20 w-20 -rotate-90" viewBox="0 0 80 80" aria-label={`Trust ${pct}%`}>
        <circle className="stroke-slate-200 dark:stroke-slate-600" fill="none" r="36" cx="40" cy="40" strokeWidth="8" />
        <circle
          className={ringColor(score)}
          fill="none"
          r="36"
          cx="40"
          cy="40"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${dash}`}
          style={{ strokeDashoffset: offset }}
        />
      </svg>
      <span className={`text-sm font-semibold ${scoreColor(score)}`}>{pct}</span>
    </div>
  );
}

function Badge({ value, label }: { value: string; label: string }) {
  const v = value;
  const bg =
    v === "yes" || v === "full-time"
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
      : v === "no" || v === "part-time"
        ? "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200"
        : "bg-slate-200 text-slate-700 dark:bg-slate-600 dark:text-slate-200";
  return (
    <span className={`inline-flex rounded-lg px-2 py-0.5 text-xs font-medium capitalize ${bg}`} title={label}>
      {label}: {v.replace(/-/g, " ")}
    </span>
  );
}

function ResultCard({ row }: { row: HospitalResult }) {
  const [openEv, setOpenEv] = useState(false);
  const [openWhy, setOpenWhy] = useState(false);
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm backdrop-blur dark:border-slate-700 dark:bg-slate-800/90">
      <div className="flex flex-col gap-4 sm:flex-row sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">{row.name}</h3>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            {row.location.district}, {row.location.state} · {row.location.pin}
            {row.location.rural ? " · rural" : ""}
          </p>
          {row.distance_km != null && (
            <span className="mt-1 inline-block rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-600 dark:text-slate-100">
              {row.distance_km.toFixed(1)} km
            </span>
          )}
        </div>
        <TrustGauge score={row.trust_score} />
      </div>
      <div className="mt-4 flex flex-wrap gap-1.5">
        {CAP_ORDER.map((k) => (
          <Badge
            key={k}
            label={capLabel(k)}
            value={String((row.capabilities as Record<string, string>)[k] ?? "unknown")}
          />
        ))}
      </div>
      {row.flags?.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-amber-800 dark:text-amber-200">
          {row.flags.map((f) => (
            <li key={f} className="flex gap-1">
              <span aria-hidden>▲</span> {f}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(["completeness", "consistency", "validator", "evidence_strength"] as const).map((k) => (
          <div key={k} className="rounded-lg bg-slate-50 p-2 dark:bg-slate-700/50">
            <div className="text-[10px] uppercase tracking-wide text-slate-500">{k}</div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-600">
              <div
                className="h-full rounded-full bg-indigo-500"
                style={{ width: `${Math.round(100 * (row.trust_breakdown[k] || 0))}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      <button
        type="button"
        className="mt-3 text-sm font-medium text-indigo-600 dark:text-indigo-400"
        onClick={() => setOpenEv(!openEv)}
      >
        {openEv ? "Hide" : "View"} evidence
      </button>
      {openEv && (
        <ul className="mt-2 space-y-1 text-sm text-slate-700 dark:text-slate-200">
          {Object.entries(row.evidence).map(
            ([k, v]) =>
              v && (
                <li key={k}>
                  <span className="font-medium text-slate-500">{k}:</span> {v}
                </li>
              )
          )}
        </ul>
      )}
      <button
        type="button"
        className="mt-2 block text-sm font-medium text-indigo-600 dark:text-indigo-400"
        onClick={() => setOpenWhy(!openWhy)}
      >
        {openWhy ? "Hide" : "Why this result?"}
      </button>
      {openWhy && <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">{row.reasoning}</p>}
    </div>
  );
}

type Tab = "search" | "deserts";

export default function Home() {
  const [q, setQ] = useState("Find emergency surgery hospital in rural Bihar with part-time doctors");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<QueryResponse | null>(null);
  const [useMock, setUseMock] = useState(false);
  const [health, setHealth] = useState<string>("…");
  const [tab, setTab] = useState<Tab>("search");
  const [traceOpen, setTraceOpen] = useState(false);
  const [desertCap, setDesertCap] = useState("icu");
  const [desertJson, setDesertJson] = useState<string>("");

  const base = getBackendBase();

  useEffect(() => {
    (async () => {
      if (!base) {
        setHealth("no URL");
        return;
      }
      const h = await getHealth();
      setHealth(h?.ok ? "ok" : "unreachable");
    })();
  }, [base]);

  const run = useCallback(async () => {
    setLoading(true);
    setUseMock(false);
    setRes(null);
    try {
      if (!base) {
        setRes(MOCK_QUERY_RESPONSE);
        setUseMock(true);
        return;
      }
      const data = await postQuery(q);
      setRes(data);
    } catch (e) {
      setRes(MOCK_QUERY_RESPONSE);
      setUseMock(true);
    } finally {
      setLoading(false);
    }
  }, [q, base]);

  const runDesert = useCallback(async () => {
    setDesertJson("");
    if (!base) {
      setDesertJson("Set NEXT_PUBLIC_BACKEND_URL in Vercel to load desert data.");
      return;
    }
    try {
      const r = await fetch(
        `${base}/desert-map/pins?capability=${encodeURIComponent(desertCap)}&top=15`
      );
      const t = await r.text();
      setDesertJson(t);
    } catch (e) {
      setDesertJson(String(e));
    }
  }, [base, desertCap]);

  const trace = res?.trace;
  const cost = trace && typeof trace === "object" && "cost" in trace ? (trace as { cost: Record<string, number> }).cost : null;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-100 to-white dark:from-slate-950 dark:to-slate-900">
      <header className="border-b border-slate-200/80 bg-white/70 backdrop-blur dark:border-slate-800 dark:bg-slate-900/70">
        <div className="mx-auto flex max-w-4xl flex-col gap-2 px-4 py-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Healthcare Intelligence Agent
            </h1>
            <p className="text-slate-600 dark:text-slate-300">
              Find reliable medical care using AI reasoning over 10,000 India facilities
            </p>
          </div>
          <div className="text-right text-sm text-slate-500">
            API: {base || "(mock)"}
            <br />
            /health: {health}
            {useMock && (
              <span className="ml-1 rounded bg-amber-100 px-1 text-amber-900 dark:bg-amber-900/50 dark:text-amber-100">
                mock
              </span>
            )}
          </div>
        </div>
        <div className="mx-auto flex max-w-4xl gap-2 border-t border-slate-100 px-4 py-2 dark:border-slate-800">
          <button
            type="button"
            onClick={() => setTab("search")}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              tab === "search"
                ? "bg-indigo-100 text-indigo-900 dark:bg-indigo-900/50 dark:text-indigo-100"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            Search
          </button>
          <button
            type="button"
            onClick={() => setTab("deserts")}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              tab === "deserts"
                ? "bg-indigo-100 text-indigo-900 dark:bg-indigo-900/50 dark:text-indigo-100"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            Medical deserts
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-8">
        {tab === "search" && (
          <>
            <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-md dark:border-slate-700 dark:bg-slate-800/80">
              <label className="sr-only" htmlFor="q">
                Search
              </label>
              <div className="flex flex-col gap-3 sm:flex-row">
                <input
                  id="q"
                  className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 shadow-inner outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900 dark:text-white"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && run()}
                  placeholder="Find emergency surgery hospital in rural Bihar with part-time doctors"
                />
                <button
                  type="button"
                  className="rounded-xl bg-indigo-600 px-6 py-3 font-semibold text-white shadow hover:bg-indigo-500 disabled:opacity-50"
                  onClick={run}
                  disabled={loading}
                >
                  {loading ? "…" : "Search"}
                </button>
              </div>
            </div>

            {loading && (
              <p className="mt-6 text-center text-slate-500">Analyzing 10,000 hospital records…</p>
            )}

            {res && !loading && (
              <div className="mt-8 space-y-4">
                {res.results.map((r) => (
                  <ResultCard key={r.facility_id} row={r} />
                ))}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => setTraceOpen(true)}
                    className="text-sm font-medium text-indigo-600 dark:text-indigo-400"
                  >
                    View reasoning trace
                  </button>
                  {cost && (
                    <p className="text-xs text-slate-500">
                      Cost: ${(cost.estimated_cost_usd ?? 0).toFixed(4)} — {cost.prompt_tokens ?? 0} prompt,{" "}
                      {cost.completion_tokens ?? 0} completion
                    </p>
                  )}
                </div>
              </div>
            )}
          </>
        )}

        {tab === "deserts" && (
          <div className="space-y-4 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-md dark:border-slate-700 dark:bg-slate-800/80">
            <p className="text-sm text-slate-600 dark:text-slate-300">
              PIN-level crisis zones from <code className="rounded bg-slate-100 px-1 dark:bg-slate-700">/desert-map/pins</code>
            </p>
            <div className="flex flex-wrap items-end gap-2">
              <div>
                <label className="text-xs text-slate-500">Capability</label>
                <select
                  className="mt-0.5 block rounded-lg border border-slate-200 bg-slate-50 px-2 py-2 text-sm dark:border-slate-600 dark:bg-slate-900"
                  value={desertCap}
                  onChange={(e) => setDesertCap(e.target.value)}
                >
                  {["icu", "emergency", "surgery", "anesthesiologist", "oxygen", "oncology", "dialysis", "neonatal", "trauma", "lab", "imaging"].map(
                    (c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    )
                  )}
                </select>
              </div>
              <button
                type="button"
                onClick={runDesert}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white"
              >
                Load JSON
              </button>
            </div>
            {desertJson && (
              <pre className="max-h-96 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">{desertJson}</pre>
            )}
          </div>
        )}
      </main>

      {traceOpen && res && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" role="dialog" aria-modal>
          <div className="h-full w-full max-w-lg overflow-y-auto border-l border-slate-200 bg-white p-4 shadow-xl dark:border-slate-700 dark:bg-slate-900">
            <div className="mb-2 flex justify-between">
              <h2 className="font-semibold">Trace</h2>
              <button type="button" className="text-slate-500" onClick={() => setTraceOpen(false)}>
                Close
              </button>
            </div>
            <pre className="whitespace-pre-wrap break-all text-xs text-slate-700 dark:text-slate-200">
              {JSON.stringify(res.trace, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
