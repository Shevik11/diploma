import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, GitCompare, Plus, X, Radio } from "lucide-react";
import {
  api,
  BenchmarkResultFile,
  BenchmarkSummary,
  DeploymentState,
  TestScriptResult,
} from "@/app/services/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/app/components/ui/select";

type Better = "higher" | "lower" | "none";

interface MetricRow {
  key: string;
  label: string;
  better: Better;
  unit?: string;
  get: (s: BenchmarkSummary["summary"]) => number | undefined;
}

const SUMMARY_METRICS: MetricRow[] = [
  {
    key: "total_prompts",
    label: "Total prompts",
    better: "none",
    get: (s) => s.total_prompts,
  },
  {
    key: "successful",
    label: "Successful",
    better: "higher",
    get: (s) => s.successful,
  },
  { key: "failed", label: "Failed", better: "lower", get: (s) => s.failed },
  {
    key: "success_rate",
    label: "Success rate",
    better: "higher",
    unit: "%",
    get: (s) => s.success_rate,
  },
  {
    key: "avg_tokens_per_second",
    label: "Avg tokens / sec",
    better: "higher",
    unit: " tok/s",
    get: (s) => s.avg_tokens_per_second,
  },
  {
    key: "avg_latency_ms",
    label: "Avg latency",
    better: "lower",
    unit: " ms",
    get: (s) => s.avg_latency_ms,
  },
  {
    key: "avg_first_token_latency_ms",
    label: "Avg first-token latency",
    better: "lower",
    unit: " ms",
    get: (s) => s.avg_first_token_latency_ms,
  },
  {
    key: "total_tokens_generated",
    label: "Total tokens generated",
    better: "higher",
    get: (s) => s.total_tokens_generated,
  },
  {
    key: "avg_cpu_percent",
    label: "Avg CPU usage",
    better: "lower",
    unit: "%",
    get: (s) => s.avg_cpu_percent,
  },
  {
    key: "avg_memory_percent",
    label: "Avg memory usage",
    better: "lower",
    unit: "%",
    get: (s) => s.avg_memory_percent,
  },
];

function fmtNumber(v: number | undefined, unit?: string): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  const rounded =
    Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 100) / 100;
  return `${rounded}${unit ?? ""}`;
}

/** Returns the set of indices that hold the best value. */
function bestIndices(
  values: (number | undefined)[],
  better: Better,
): Set<number> {
  if (better === "none") return new Set();
  const valid = values
    .map((v, i) => ({ v, i }))
    .filter(({ v }) => v !== undefined && !Number.isNaN(v)) as {
    v: number;
    i: number;
  }[];
  if (valid.length === 0) return new Set();
  const best =
    better === "higher"
      ? Math.max(...valid.map((x) => x.v))
      : Math.min(...valid.map((x) => x.v));
  return new Set(valid.filter(({ v }) => v === best).map(({ i }) => i));
}

function cellClass(isBest: boolean) {
  return isBest ? "bg-green-50 text-green-800 font-semibold" : "text-gray-800";
}

// Aggregated data for one model across all its result files
interface ModelAggregate {
  model: string;
  fileCount: number;
  platforms: string[];
  technologies: string[];
  latestTimestamp?: string;
  summary: BenchmarkSummary["summary"];
  testByName: Map<
    string,
    { passed: number; failed: number; total: number; avgDuration: number }
  >;
}

function avg(nums: number[]): number {
  const vals = nums.filter((n) => typeof n === "number" && !Number.isNaN(n));
  if (vals.length === 0) return 0;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function sum(nums: number[]): number {
  return nums
    .filter((n) => typeof n === "number" && !Number.isNaN(n))
    .reduce((a, b) => a + b, 0);
}

function aggregateModel(
  model: string,
  summaries: BenchmarkSummary[],
): ModelAggregate {
  const platforms = Array.from(
    new Set(summaries.map((s) => s.platform).filter(Boolean)),
  );
  const technologies = Array.from(
    new Set(summaries.map((s) => s.technology).filter(Boolean)),
  );
  const timestamps = summaries
    .map((s) => s.timestamp)
    .filter(Boolean)
    .sort();

  const s = summaries.map((x) => x.summary).filter(Boolean);
  const aggSummary: BenchmarkSummary["summary"] = {
    total_prompts: sum(s.map((x) => x.total_prompts || 0)),
    successful: sum(s.map((x) => x.successful || 0)),
    failed: sum(s.map((x) => x.failed || 0)),
    success_rate: avg(s.map((x) => x.success_rate || 0)),
    avg_tokens_per_second: avg(s.map((x) => x.avg_tokens_per_second || 0)),
    avg_latency_ms: avg(s.map((x) => x.avg_latency_ms || 0)),
    avg_first_token_latency_ms: avg(
      s.map((x) => x.avg_first_token_latency_ms || 0),
    ),
    total_tokens_generated: sum(s.map((x) => x.total_tokens_generated || 0)),
    avg_cpu_percent: avg(s.map((x) => x.avg_cpu_percent || 0)),
    avg_memory_percent: avg(s.map((x) => x.avg_memory_percent || 0)),
  };

  const testByName = new Map<
    string,
    { passed: number; failed: number; total: number; avgDuration: number }
  >();
  const durationAcc = new Map<string, number[]>();
  summaries.forEach((sm) => {
    (sm.test_results || []).forEach((t: TestScriptResult) => {
      const entry = testByName.get(t.name) || {
        passed: 0,
        failed: 0,
        total: 0,
        avgDuration: 0,
      };
      entry.total += 1;
      if (t.status === "passed") entry.passed += 1;
      else entry.failed += 1;
      testByName.set(t.name, entry);
      const arr = durationAcc.get(t.name) || [];
      if (typeof t.duration === "number") arr.push(t.duration);
      durationAcc.set(t.name, arr);
    });
  });
  testByName.forEach((v, k) => {
    v.avgDuration = avg(durationAcc.get(k) || []);
  });

  return {
    model,
    fileCount: summaries.length,
    platforms,
    technologies,
    latestTimestamp: timestamps[timestamps.length - 1],
    summary: aggSummary,
    testByName,
  };
}

export function ModelCompare() {
  const [files, setFiles] = useState<BenchmarkResultFile[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [errorList, setErrorList] = useState<string | null>(null);

  // Array of selected model names (slots); undefined = no model chosen yet
  const [selectedModels, setSelectedModels] = useState<(string | undefined)[]>([
    undefined,
    undefined,
  ]);

  // Cache of loaded full summaries keyed by filename
  const [summaryCache, setSummaryCache] = useState<
    Record<string, BenchmarkSummary>
  >({});
  const [loadingModels, setLoadingModels] = useState<Set<string>>(new Set());

  // Live metrics streamed over WebSocket (refreshed every 2s by backend heartbeat)
  const [liveMetrics, setLiveMetrics] = useState<{
    container: DeploymentState;
    vm: DeploymentState;
  } | null>(null);
  const [liveUpdatedAt, setLiveUpdatedAt] = useState<number | null>(null);
  const selectedModelsRef = useRef(selectedModels);
  selectedModelsRef.current = selectedModels;

  // List of unique models derived from files
  const models = useMemo(() => {
    const map = new Map<string, number>();
    files.forEach((f) => {
      if (!f.model) return;
      map.set(f.model, (map.get(f.model) || 0) + 1);
    });
    return Array.from(map.entries())
      .map(([model, count]) => ({ model, count }))
      .sort((a, b) => a.model.localeCompare(b.model));
  }, [files]);

  useEffect(() => {
    setLoadingList(true);
    api
      .getBenchmarkResults()
      .then((r) => {
        setFiles(r);
        setErrorList(null);
      })
      .catch((e) =>
        setErrorList(e.message || "Failed to load benchmark results"),
      )
      .finally(() => setLoadingList(false));
  }, []);

  // Auto-pick defaults when models list arrives
  useEffect(() => {
    if (models.length === 0) return;
    setSelectedModels((prev) =>
      prev.map((v, i) =>
        v !== undefined
          ? v
          : models[i] !== undefined
            ? models[i].model
            : models[0].model,
      ),
    );
  }, [models]);

  const filesForModel = (model: string) =>
    files.filter((f) => f.model === model);

  const loadSummariesFor = async (model: string) => {
    const targetFiles = filesForModel(model);
    const missing = targetFiles.filter((f) => !summaryCache[f.filename]);
    if (missing.length === 0) return;
    setLoadingModels((prev) => new Set(prev).add(model));
    try {
      const loaded = await Promise.all(
        missing.map((f) =>
          api
            .getBenchmarkResult(f.filename)
            .then((s) => [f.filename, s] as const)
            .catch(() => null),
        ),
      );
      setSummaryCache((prev) => {
        const next = { ...prev };
        loaded.forEach((entry) => {
          if (entry) next[entry[0]] = entry[1];
        });
        return next;
      });
    } finally {
      setLoadingModels((prev) => {
        const next = new Set(prev);
        next.delete(model);
        return next;
      });
    }
  };

  // Load summaries whenever selectedModels or files change
  useEffect(() => {
    selectedModels.forEach((m) => {
      if (m) loadSummariesFor(m);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModels, files]);

  // Real-time metrics streaming via WebSocket. The backend pushes updates on
  // every client ping (2s heartbeat in api.connectWebSocket), so each message
  // is our cue to (a) refresh the live CPU/Memory/Latency overlay and (b)
  // re-pull the list of benchmark result files plus any newly-completed
  // summaries for the currently selected models. This satisfies the project
  // guideline that frontend metric visualizations refresh every 2 seconds.
  useEffect(() => {
    let ws: WebSocket | null = null;
    let cancelled = false;
    let lastFilesRefresh = 0;
    let lastSummaryRefresh = 0;

    const refreshFiles = async () => {
      try {
        const r = await api.getBenchmarkResults();
        if (!cancelled) setFiles(r);
      } catch {
        /* keep previous snapshot on transient failure */
      }
    };

    const refreshSelectedSummaries = async () => {
      const current = selectedModelsRef.current;
      // Force re-fetch latest summary for every selected model so the
      // aggregated comparison numbers stay live.
      await Promise.all(
        current.map(async (m) => {
          if (!m) return;
          try {
            const targetFiles = files.filter((f) => f.model === m);
            const fresh = await Promise.all(
              targetFiles.map((f) =>
                api
                  .getBenchmarkResult(f.filename)
                  .then((s) => [f.filename, s] as const)
                  .catch(() => null),
              ),
            );
            if (cancelled) return;
            setSummaryCache((prev) => {
              const next = { ...prev };
              fresh.forEach((entry) => {
                if (entry) next[entry[0]] = entry[1];
              });
              return next;
            });
          } catch {
            /* ignore individual model refresh failures */
          }
        }),
      );
    };

    try {
      ws = api.connectWebSocket((data) => {
        if (cancelled) return;
        setLiveMetrics(data);
        setLiveUpdatedAt(Date.now());

        // Throttle expensive REST refreshes to the 2s WS cadence so we never
        // pile up overlapping requests if the socket fires faster than expected.
        const now = Date.now();
        if (now - lastFilesRefresh >= 2000) {
          lastFilesRefresh = now;
          void refreshFiles();
        }
        if (now - lastSummaryRefresh >= 2000) {
          lastSummaryRefresh = now;
          void refreshSelectedSummaries();
        }
      });
    } catch {
      // WebSocket unavailable; comparison still works with the initial REST snapshot.
    }

    return () => {
      cancelled = true;
      if (ws && ws.readyState !== WebSocket.CLOSED) {
        try {
          ws.close();
        } catch {
          /* noop */
        }
      }
    };
    // We intentionally do not depend on `files`/`selectedModels` directly:
    // they are read via the ref / closure on each tick to keep a single
    // long-lived WS connection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const aggregateFor = (model: string | undefined): ModelAggregate | null => {
    if (!model) return null;
    const targetFiles = filesForModel(model);
    const summaries = targetFiles
      .map((f) => summaryCache[f.filename])
      .filter((s): s is BenchmarkSummary => !!s);
    if (summaries.length === 0) return null;
    return aggregateModel(model, summaries);
  };

  const aggregates = useMemo(
    () => selectedModels.map((m) => aggregateFor(m)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedModels, summaryCache, files],
  );

  const testRows = useMemo(() => {
    const names = new Set<string>();
    aggregates.forEach((agg) =>
      agg?.testByName.forEach((_v, k) => names.add(k)),
    );
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [aggregates]);

  const addModel = () =>
    setSelectedModels((prev) => [...prev, undefined]);

  const removeModel = (idx: number) =>
    setSelectedModels((prev) => prev.filter((_, i) => i !== idx));

  const setModel = (idx: number, value: string) =>
    setSelectedModels((prev) => prev.map((v, i) => (i === idx ? value : v)));

  const n = selectedModels.length;
  // Dynamic grid: label col + n model cols
  const gridStyle = {
    gridTemplateColumns: `minmax(180px,1fr) repeat(${n}, minmax(120px,1fr))`,
  };

  const isLoading = selectedModels.some((m) => m && loadingModels.has(m));

  return (
    <div className="bg-white border border-zinc-200 rounded-lg p-6 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <GitCompare className="w-5 h-5 text-zinc-700" />
        <h2 className="text-xl font-semibold text-zinc-800">Compare SLMs</h2>
      </div>
      <p className="text-sm text-zinc-600 mb-6">
        Select any number of models and compare aggregated stats across{" "}
        <strong>all their benchmark runs</strong> in the <code>results/</code>{" "}
        folder.
      </p>

      {errorList && (
        <div className="mb-4 bg-red-50/50 border border-red-100 rounded p-3 text-sm text-red-700">
          {errorList}
        </div>
      )}

      {/* Selectors row */}
      <div className="flex flex-wrap gap-3 items-end mb-6">
        {selectedModels.map((model, idx) => (
          <div key={idx} className="flex items-end gap-1">
            <ModelSelect
              label={`Model ${String.fromCharCode(65 + idx)}`}
              models={models}
              value={model}
              onChange={(v) => setModel(idx, v)}
              loading={loadingList}
            />
            {n > 2 && (
              <button
                type="button"
                onClick={() => removeModel(idx)}
                className="h-10 w-10 mb-0 rounded-full border-2 border-zinc-300 bg-zinc-50 hover:border-red-400 hover:bg-red-50 flex items-center justify-center transition-colors"
                title="Remove"
              >
                <X className="w-4 h-4 text-zinc-500 hover:text-red-500" />
              </button>
            )}
          </div>
        ))}
        <button
          type="button"
          onClick={addModel}
          className="h-10 px-4 flex items-center gap-2 rounded-lg border-2 border-dashed border-zinc-300 text-zinc-500 hover:border-zinc-500 hover:text-zinc-700 text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add model
        </button>
      </div>

      {/* Comparison table */}
      <div className="border border-zinc-200 rounded-lg overflow-x-auto bg-white shadow-sm">
        {/* Header */}
        <div
          className="grid bg-zinc-100 border-b border-zinc-200 text-zinc-800"
          style={gridStyle}
        >
          <div className="p-4 border-r border-zinc-200 font-semibold text-zinc-900">
            Metric
          </div>
          {aggregates.map((agg, idx) => (
            <ModelHeader
              key={idx}
              agg={agg}
              fallback={selectedModels[idx]}
              last={idx === n - 1}
            />
          ))}
        </div>

        {/* Summary section */}
        <SectionHeader title="Aggregated benchmark summary (averaged across all runs)" />
        {isLoading && (
          <div className="p-4 flex items-center gap-2 text-sm text-zinc-500 border-t border-zinc-100">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading stats from all
            result files…
          </div>
        )}
        {SUMMARY_METRICS.map((row) => {
          const values = aggregates.map((agg) =>
            agg ? row.get(agg.summary) : undefined,
          );
          const best = bestIndices(values, row.better);
          return (
            <div
              key={row.key}
              className="grid border-t border-zinc-100"
              style={gridStyle}
            >
              <div className="p-3 bg-zinc-50/50 text-sm text-zinc-600 border-r border-zinc-100">
                {row.label}
              </div>
              {values.map((v, idx) => (
                <div
                  key={idx}
                  className={`p-3 text-sm ${idx < n - 1 ? "border-r border-zinc-100" : ""} ${cellClass(best.has(idx))}`}
                >
                  {fmtNumber(v, row.unit)}
                </div>
              ))}
            </div>
          );
        })}

        {/* Meta */}
        <SectionHeader title="Run info" />
        <MetaRow
          label="Result files"
          values={aggregates.map((agg) =>
            agg ? String(agg.fileCount) : undefined,
          )}
          gridStyle={gridStyle}
        />
        <MetaRow
          label="Platforms"
          values={aggregates.map((agg) => agg?.platforms.join(", "))}
          gridStyle={gridStyle}
        />
        <MetaRow
          label="Technologies"
          values={aggregates.map((agg) => agg?.technologies.join(", "))}
          gridStyle={gridStyle}
        />
        <MetaRow
          label="Latest run"
          values={aggregates.map((agg) => agg?.latestTimestamp)}
          gridStyle={gridStyle}
        />

        {/* Live metrics (WebSocket, 2s) */}
        <SectionHeader
          title={
            liveUpdatedAt
              ? `Live container metrics (WebSocket · updated ${Math.max(
                  0,
                  Math.round((Date.now() - liveUpdatedAt) / 1000),
                )}s ago)`
              : "Live container metrics (WebSocket · waiting…)"
          }
        />
        <LiveMetricsRow
          label={
            <span className="inline-flex items-center gap-1">
              <Radio
                className={`w-3 h-3 ${liveMetrics ? "text-green-600" : "text-zinc-400"}`}
              />
              CPU (live)
            </span>
          }
          aggregates={aggregates}
          live={liveMetrics?.container}
          field="cpu"
          unit="%"
          gridStyle={gridStyle}
        />
        <LiveMetricsRow
          label={
            <span className="inline-flex items-center gap-1">
              <Radio
                className={`w-3 h-3 ${liveMetrics ? "text-green-600" : "text-zinc-400"}`}
              />
              Memory (live)
            </span>
          }
          aggregates={aggregates}
          live={liveMetrics?.container}
          field="memory"
          unit="%"
          gridStyle={gridStyle}
        />
        <LiveMetricsRow
          label={
            <span className="inline-flex items-center gap-1">
              <Radio
                className={`w-3 h-3 ${liveMetrics ? "text-green-600" : "text-zinc-400"}`}
              />
              Latency (live)
            </span>
          }
          aggregates={aggregates}
          live={liveMetrics?.container}
          field="latency"
          unit=" ms"
          gridStyle={gridStyle}
        />

        {/* Tests */}
        {testRows.length > 0 && (
          <>
            <SectionHeader title="Test scripts (pass rate across all runs)" />
            {testRows.map((name) => {
              const entries = aggregates.map((agg) =>
                agg?.testByName.get(name),
              );
              const rates = entries.map((e) =>
                e ? e.passed / e.total : undefined,
              );
              const best = bestIndices(rates, "higher");
              return (
                <div
                  key={name}
                  className="grid border-t border-zinc-100"
                  style={gridStyle}
                >
                  <div className="p-3 bg-zinc-50/50 text-sm text-zinc-600 border-r border-zinc-100">
                    {name}
                  </div>
                  {entries.map((e, idx) => (
                    <div
                      key={idx}
                      className={`p-3 text-sm ${idx < n - 1 ? "border-r border-zinc-100" : ""} ${cellClass(best.has(idx))}`}
                    >
                      {e
                        ? `${e.passed}/${e.total} · avg ${e.avgDuration.toFixed(1)}s`
                        : "—"}
                    </div>
                  ))}
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}

function LiveMetricsRow({
  label,
  aggregates,
  live,
  field,
  unit,
  gridStyle,
}: {
  label: React.ReactNode;
  aggregates: (ModelAggregate | null)[];
  live: DeploymentState | undefined;
  field: "cpu" | "memory" | "latency";
  unit?: string;
  gridStyle: React.CSSProperties;
}) {
  const n = aggregates.length;
  return (
    <div className="grid border-t border-zinc-100" style={gridStyle}>
      <div className="p-3 bg-zinc-50/50 text-sm text-zinc-600 border-r border-zinc-100">
        {label}
      </div>
      {aggregates.map((agg, idx) => {
        // Show live readings only for the model that is currently deployed
        // in the container; other slots show "—" because the WS stream only
        // reports a single active workload.
        const isActive =
          !!agg && !!live && live.status === "running" && live.model === agg.model;
        const value = isActive ? (live as DeploymentState)[field] : undefined;
        const display =
          typeof value === "number" && !Number.isNaN(value)
            ? `${value}${unit ?? ""}`
            : "—";
        return (
          <div
            key={idx}
            className={`p-3 text-sm ${idx < n - 1 ? "border-r border-zinc-100" : ""} ${
              isActive ? "text-green-700 font-semibold" : "text-zinc-500"
            }`}
          >
            {display}
          </div>
        );
      })}
    </div>
  );
}

function ModelHeader({
  agg,
  fallback,
  last,
}: {
  agg: ModelAggregate | null;
  fallback?: string;
  last?: boolean;
}) {
  return (
    <div className={`p-4 ${last ? "" : "border-r border-zinc-200"}`}>
      <div className="text-xs uppercase opacity-70">Model</div>
      <div className="font-semibold text-zinc-900 text-sm truncate max-w-[160px]">
        {agg?.model || fallback || "—"}
      </div>
      <div className="text-xs opacity-60">
        {agg ? `${agg.fileCount} run${agg.fileCount === 1 ? "" : "s"}` : ""}
        {agg && agg.platforms.length > 0 ? ` · ${agg.platforms.join("/")}` : ""}
      </div>
    </div>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div className="grid grid-cols-1 border-t border-zinc-200">
      <div className="p-2 px-4 bg-zinc-100 text-xs uppercase tracking-wider font-bold text-zinc-600">
        {title}
      </div>
    </div>
  );
}

function MetaRow({
  label,
  values,
  gridStyle,
}: {
  label: string;
  values: (string | undefined)[];
  gridStyle: React.CSSProperties;
}) {
  const n = values.length;
  return (
    <div className="grid border-t border-zinc-100" style={gridStyle}>
      <div className="p-3 bg-zinc-50/50 text-sm text-zinc-600 border-r border-zinc-100">
        {label}
      </div>
      {values.map((v, idx) => (
        <div
          key={idx}
          className={`p-3 text-sm text-zinc-700 ${idx < n - 1 ? "border-r border-zinc-100" : ""}`}
        >
          {v || "—"}
        </div>
      ))}
    </div>
  );
}

function ModelSelect({
  label,
  models,
  value,
  onChange,
  loading,
}: {
  label: string;
  models: { model: string; count: number }[];
  value: string | undefined;
  onChange: (v: string) => void;
  loading: boolean;
}) {
  return (
    <div>
      <label className="text-sm font-medium text-zinc-700 mb-1 block">
        {label}
      </label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="bg-white border-zinc-200 text-zinc-800 w-48">
          <SelectValue placeholder={loading ? "Loading…" : "Select a model"} />
        </SelectTrigger>
        <SelectContent className="bg-white border-zinc-200 text-zinc-800">
          {models.map((m) => (
            <SelectItem key={m.model} value={m.model}>
              {m.model} ({m.count} run{m.count === 1 ? "" : "s"})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
