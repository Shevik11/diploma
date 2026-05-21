import { useEffect, useMemo, useState } from "react";
import { Loader2, Trophy, Medal } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import {
  api,
  BenchmarkResultFile,
  BenchmarkSummary,
  InfeasibleInfo,
  isInfeasible,
  variantId,
  variantLabel,
} from "@/app/services/api";
import {
  aggregateModel,
  BAR_METRICS,
  ModelAggregate,
  normalizeValues,
  paletteColor,
} from "@/app/components/model-dashboard";

// ─── Helpers ─────────────────────────────────────────────────────────────────

interface RankedModel {
  rank: number;
  agg: ModelAggregate;
  score: number;
  perMetric: Record<string, number>; // metricId → 0..100 normalized score
  color: string;
  /**
   * If set, this entry was never actually benchmarked because the backend
   * judged the (model, RAM, CPU) config infeasible (model couldn't load
   * within the RAM cap). Such entries are pinned to the bottom of the
   * leaderboard and excluded from the composite normalization so they
   * don't drag everyone else's normalized score to 0.
   */
  infeasible?: InfeasibleInfo;
}

function rankColor(rank: number): string {
  switch (rank) {
    case 1:
      return "bg-yellow-100 text-yellow-800 border-yellow-300";
    case 2:
      return "bg-zinc-100 text-zinc-700 border-zinc-300";
    case 3:
      return "bg-orange-100 text-orange-800 border-orange-300";
    default:
      return "bg-white text-zinc-600 border-zinc-200";
  }
}

// ─── Component ───────────────────────────────────────────────────────────────

export function TopModels() {
  const [files, setFiles] = useState<BenchmarkResultFile[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [errorList, setErrorList] = useState<string | null>(null);
  const [summaryCache, setSummaryCache] = useState<
    Record<string, BenchmarkSummary>
  >({});
  const [loadingFiles, setLoadingFiles] = useState(false);
  // Filter the leaderboard by base model name (e.g. "qwen:1.5b") so the user
  // can focus on a single model's variants. Empty == show all models.
  const [modelFilter, setModelFilter] = useState<string>("");
  // Filter by hardware parameters (RAM in GB, CPU cores). Empty == any.
  const [ramFilter, setRamFilter] = useState<string>("");
  const [cpuFilter, setCpuFilter] = useState<string>("");

  // Unique sorted list of base model names across all loaded files —
  // populates the filter <select>. Built from the raw file list so the
  // options stay stable regardless of the currently active filter.
  const baseModelOptions = useMemo(() => {
    const s = new Set<string>();
    files.forEach((f) => {
      if (f.model) s.add(f.model);
    });
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [files]);

  // Unique RAM (GB) and CPU (cores) values across all loaded files, sorted
  // numerically ascending. Used to populate the parameter filter <select>s.
  const ramOptions = useMemo(() => {
    const s = new Set<number>();
    files.forEach((f) => {
      if (f.ram_gb != null) s.add(f.ram_gb);
    });
    return Array.from(s).sort((a, b) => a - b);
  }, [files]);
  const cpuOptions = useMemo(() => {
    const s = new Set<number>();
    files.forEach((f) => {
      if (f.cpu_cores != null) s.add(f.cpu_cores);
    });
    return Array.from(s).sort((a, b) => a - b);
  }, [files]);

  // Load file list
  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoadingList(true);
    api
      .getBenchmarkResults()
      .then((r) => {
        if (cancelled) return;
        setFiles(r);
        setErrorList(null);
      })
      .catch((e) => {
        if (!cancelled) setErrorList(e.message || "Failed to load results");
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load all summaries for global ranking
  useEffect(() => {
    if (files.length === 0) return;
    const missing = files.filter((f) => !summaryCache[f.filename]);
    if (missing.length === 0) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoadingFiles(true);
    Promise.all(
      missing.map((f) =>
        api
          .getBenchmarkResult(f.filename)
          .then((s) => [f.filename, s] as const)
          .catch(() => null),
      ),
    )
      .then((loaded) => {
        setSummaryCache((p) => {
          const next = { ...p };
          loaded.forEach((entry) => {
            if (entry) next[entry[0]] = entry[1];
          });
          return next;
        });
      })
      .finally(() => setLoadingFiles(false));
  }, [files, summaryCache]);

  // Group files by variant id (same model + RAM + CPU + tech + platform).
  // A variant is considered infeasible if every result file for it is
  // explicitly flagged as such by the backend (i.e., the backend refused
  // to run it due to insufficient RAM). Mixed groups — where at least one
  // run actually executed — are treated as feasible and the infeasible
  // stub files are simply ignored for ranking purposes.
  const { aggregates, infeasibleEntries } = useMemo(() => {
    const byVariant = new Map<
      string,
      {
        label: string;
        summaries: BenchmarkSummary[];
        files: BenchmarkResultFile[];
      }
    >();
    files.forEach((f) => {
      if (!f.model) return;
      if (modelFilter && f.model !== modelFilter) return;
      if (ramFilter && String(f.ram_gb ?? "") !== ramFilter) return;
      if (cpuFilter && String(f.cpu_cores ?? "") !== cpuFilter) return;
      const s = summaryCache[f.filename];
      if (!s) return;
      const id = variantId(f);
      const cur = byVariant.get(id);
      if (cur) {
        cur.summaries.push(s);
        cur.files.push(f);
      } else {
        byVariant.set(id, {
          label: variantLabel(f),
          summaries: [s],
          files: [f],
        });
      }
    });

    const feasible: ModelAggregate[] = [];
    const infeasible: { agg: ModelAggregate; info: InfeasibleInfo }[] = [];

    Array.from(byVariant.values()).forEach(({ label, summaries, files: vf }) => {
      // Treat both legacy `infeasible` block and the new spec status
      // `not_enough_resources` as "this config never actually ran".
      const allInfeasible = vf.every((f) => isInfeasible(f));
      if (allInfeasible) {
        // Synthesize a placeholder aggregate so the row can still render
        // model name + config; metric cells will display "—" because all
        // values are zero.
        const agg = aggregateModel(label, summaries);
        const info =
          vf.find((f) => f.infeasible)?.infeasible ??
          ({
            reason:
              vf.find((f) => f.status === "not_enough_resources")
                ? "Not enough resources to load model"
                : "Infeasible config",
            required_ram_gb: 0,
          } as InfeasibleInfo);
        infeasible.push({ agg, info });
        return;
      }
      // Feasible variant: build aggregate only from files that actually ran.
      const realSummaries = vf
        .filter((f) => !isInfeasible(f))
        .map((f) => summaryCache[f.filename])
        .filter(Boolean) as BenchmarkSummary[];
      if (realSummaries.length === 0) return;
      const agg = aggregateModel(label, realSummaries);
      if (agg.fileCount > 0) feasible.push(agg);
    });

    return { aggregates: feasible, infeasibleEntries: infeasible };
  }, [files, summaryCache, modelFilter, ramFilter, cpuFilter]);

  // Build ranking using a weighted composite over ALL JSON fields:
  //  - Existing 8 BAR_METRICS (summary + test pass rate)
  //  - p95 latency, peak memory, error rate (from raw per-prompt items)
  // Weights emphasize speed & reliability.
  const ranked: RankedModel[] = useMemo(() => {
    // Note: even when there are no feasible aggregates, infeasible variants
    // are still appended below so the user sees *why* the leaderboard is
    // empty (instead of a blank page).
    if (aggregates.length === 0 && infeasibleEntries.length === 0) return [];

    type Axis = {
      id: string;
      values: number[]; // normalized 0..100
      weight: number;
    };

    const axes: Axis[] = [];
    // 8 BAR_METRICS axes (weight = 1 each)
    BAR_METRICS.forEach((m) => {
      axes.push({
        id: m.id,
        values: normalizeValues(
          aggregates.map((a) => m.getValue(a)),
          m.higherBetter,
        ),
        weight: 1,
      });
    });
    // Extra raw-derived axes
    axes.push({
      id: "p95_latency_ms",
      values: normalizeValues(
        aggregates.map((a) => a.p95LatencyMs),
        false,
      ),
      weight: 1.2,
    });
    axes.push({
      id: "peak_memory_mb",
      values: normalizeValues(
        aggregates.map((a) => a.peakMemoryMb),
        false,
      ),
      weight: 0.8,
    });
    axes.push({
      id: "error_rate",
      values: normalizeValues(
        aggregates.map((a) => a.errorRate),
        false,
      ),
      weight: 1.5,
    });

    const totalWeight = axes.reduce((s, a) => s + a.weight, 0);

    const items: RankedModel[] = aggregates.map((a, i) => {
      const perMetric: Record<string, number> = {};
      axes.forEach((ax) => {
        perMetric[ax.id] = ax.values[i];
      });
      const weighted =
        axes.reduce((s, ax) => s + ax.values[i] * ax.weight, 0) / totalWeight;
      return {
        rank: 0,
        agg: a,
        score: Math.round(weighted),
        perMetric,
        color: paletteColor(i),
      };
    });
    items.sort((a, b) => b.score - a.score);
    items.forEach((m, idx) => (m.rank = idx + 1));

    // Append infeasible variants at the very bottom of the leaderboard,
    // *after* every feasible model regardless of score. They keep their
    // own continuing rank numbers so the table is still gap-free, but
    // their composite score is rendered as "—" (see the table cell)
    // because they were never actually measured.
    const baseRank = items.length;
    infeasibleEntries.forEach(({ agg, info }, i) => {
      items.push({
        rank: baseRank + i + 1,
        agg,
        score: 0,
        perMetric: {},
        color: "#a1a1aa", // zinc-400 (grayed-out)
        infeasible: info,
      });
    });
    return items;
  }, [aggregates, infeasibleEntries]);

  const totalRuns = aggregates.reduce((s, a) => s + a.fileCount, 0);
  const isLoading = loadingList || loadingFiles;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-zinc-200 rounded-lg p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-1">
          <Trophy className="w-5 h-5 text-amber-600" />
          <h2 className="text-xl font-semibold text-zinc-800">
            Top Models — Global Leaderboard
          </h2>
          {isLoading && (
            <Loader2 className="w-4 h-4 animate-spin text-zinc-400 ml-1" />
          )}
        </div>
        <p className="text-sm text-zinc-500">
          Unified ranking across <strong>all benchmark runs</strong> and all
          metrics. Each metric is normalized to 0–100 (lower-is-better metrics
          are inverted), then combined into a single composite score using a
          <em>weighted</em> average (see the formula at the bottom for the
          per-axis weights).
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-zinc-600">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-50 border border-zinc-200">
            <strong className="text-zinc-800">{aggregates.length}</strong>{" "}
            models
          </span>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-50 border border-zinc-200">
            <strong className="text-zinc-800">{totalRuns}</strong> result files
          </span>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-50 border border-zinc-200">
            <strong className="text-zinc-800">{BAR_METRICS.length + 3}</strong>{" "}
            metrics scored
          </span>
          <div className="inline-flex items-center gap-2 ml-auto">
            <span className="text-zinc-500">Filter:</span>
            <select
              value={modelFilter}
              onChange={(e) => setModelFilter(e.target.value)}
              className="border border-zinc-300 rounded-md px-2 py-1 text-xs bg-white text-zinc-700 hover:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
              title="Filter leaderboard by base model name"
            >
              <option value="">All models ({baseModelOptions.length})</option>
              {baseModelOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            {modelFilter && (
              <button
                type="button"
                onClick={() => setModelFilter("")}
                className="text-zinc-400 hover:text-zinc-700 underline"
                title="Clear model filter"
              >
                clear
              </button>
            )}
            <span className="text-zinc-500 ml-2">RAM:</span>
            <select
              value={ramFilter}
              onChange={(e) => setRamFilter(e.target.value)}
              className="border border-zinc-300 rounded-md px-2 py-1 text-xs bg-white text-zinc-700 hover:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
              title="Filter leaderboard by RAM cap (GB)"
            >
              <option value="">Any ({ramOptions.length})</option>
              {ramOptions.map((r) => (
                <option key={r} value={String(r)}>
                  {r} GB
                </option>
              ))}
            </select>
            {ramFilter && (
              <button
                type="button"
                onClick={() => setRamFilter("")}
                className="text-zinc-400 hover:text-zinc-700 underline"
                title="Clear RAM filter"
              >
                clear
              </button>
            )}
            <span className="text-zinc-500 ml-2">CPU:</span>
            <select
              value={cpuFilter}
              onChange={(e) => setCpuFilter(e.target.value)}
              className="border border-zinc-300 rounded-md px-2 py-1 text-xs bg-white text-zinc-700 hover:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
              title="Filter leaderboard by CPU cores"
            >
              <option value="">Any ({cpuOptions.length})</option>
              {cpuOptions.map((c) => (
                <option key={c} value={String(c)}>
                  {c} {c === 1 ? "core" : "cores"}
                </option>
              ))}
            </select>
            {cpuFilter && (
              <button
                type="button"
                onClick={() => setCpuFilter("")}
                className="text-zinc-400 hover:text-zinc-700 underline"
                title="Clear CPU filter"
              >
                clear
              </button>
            )}
          </div>
        </div>
      </div>

      {errorList && (
        <div className="bg-red-50 border border-red-100 rounded-lg p-4 text-sm text-red-700">
          {errorList}
        </div>
      )}

      {ranked.length === 0 ? (
        <div className="bg-white border border-zinc-200 rounded-lg p-16 text-center text-zinc-400 shadow-sm">
          {isLoading
            ? "Loading benchmark summaries…"
            : modelFilter || ramFilter || cpuFilter
              ? `No benchmark results match the selected filters${
                  modelFilter ? ` · model=${modelFilter}` : ""
                }${ramFilter ? ` · RAM=${ramFilter}GB` : ""}${
                  cpuFilter ? ` · CPU=${cpuFilter}` : ""
                }.`
              : "No benchmark results available — run some benchmarks first."}
        </div>
      ) : (
        <>
          {/* Bar chart of composite scores */}
          <div className="bg-white border border-zinc-200 rounded-lg p-5 shadow-sm">
            <div className="flex items-baseline justify-between mb-3">
              <h3 className="font-medium text-zinc-800">
                Composite score (0 – 100)
              </h3>
              <span className="text-[11px] text-zinc-400">
                Higher is better · weighted average across {BAR_METRICS.length + 3} metrics
              </span>
            </div>
            <div style={{ height: Math.max(220, ranked.length * 38 + 40) }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={ranked.map((r) => ({
                    name: `#${r.rank} ${r.agg.model}`,
                    score: r.score,
                    fill: r.color,
                  }))}
                  layout="vertical"
                  margin={{ top: 4, right: 60, bottom: 4, left: 4 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    horizontal={false}
                    stroke="#e4e4e7"
                  />
                  <XAxis
                    type="number"
                    domain={[0, 100]}
                    tick={{ fontSize: 11, fill: "#71717a" }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={180}
                    tick={{ fontSize: 11, fill: "#71717a" }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip
                    cursor={{ fill: "#f4f4f5" }}
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const p = payload[0].payload as {
                        name: string;
                        score: number;
                      };
                      return (
                        <div className="bg-white border border-zinc-200 rounded-lg px-3 py-2 shadow-sm text-xs">
                          <div className="font-semibold text-zinc-800">
                            {p.name}
                          </div>
                          <div className="text-zinc-600">
                            Score:{" "}
                            <span className="font-medium text-zinc-800">
                              {p.score} / 100
                            </span>
                          </div>
                        </div>
                      );
                    }}
                  />
                  <Bar
                    dataKey="score"
                    radius={[0, 4, 4, 0]}
                    maxBarSize={26}
                    label={{
                      position: "right",
                      fontSize: 10,
                      fill: "#52525b",
                      formatter: (v: number) => `${v}`,
                    }}
                  >
                    {ranked.map((r) => (
                      <Cell key={r.agg.model} fill={r.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Detailed leaderboard table */}
          <div className="bg-white border border-zinc-200 rounded-lg shadow-sm overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-100 text-zinc-700">
                <tr>
                  <th className="text-left p-3 font-semibold w-16">#</th>
                  <th className="text-left p-3 font-semibold">Model</th>
                  <th className="text-right p-3 font-semibold w-28">Runs</th>
                  <th className="text-right p-3 font-semibold w-32">
                    Composite
                  </th>
                  {BAR_METRICS.map((m) => (
                    <th
                      key={m.id}
                      className="text-right p-3 font-semibold whitespace-nowrap"
                      title={`${m.label} (${m.higherBetter ? "higher is better" : "lower is better"})`}
                    >
                      {m.label}
                      <span className="ml-1 text-zinc-400 text-[10px]">
                        {m.higherBetter ? "↑" : "↓"}
                      </span>
                    </th>
                  ))}
                  <th
                    className="text-right p-3 font-semibold whitespace-nowrap"
                    title="p95 latency across raw per-prompt items (lower is better)"
                  >
                    p95 latency
                    <span className="ml-1 text-zinc-400 text-[10px]">↓</span>
                  </th>
                  <th
                    className="text-right p-3 font-semibold whitespace-nowrap"
                    title="Peak memory used across raw per-prompt items (lower is better)"
                  >
                    Peak mem
                    <span className="ml-1 text-zinc-400 text-[10px]">↓</span>
                  </th>
                  <th
                    className="text-right p-3 font-semibold whitespace-nowrap"
                    title="Error rate across raw per-prompt items (lower is better)"
                  >
                    Error rate
                    <span className="ml-1 text-zinc-400 text-[10px]">↓</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {ranked.map((r) => {
                  // Total non-static columns to span when we render the
                  // single "Infeasible — reason" cell instead of metrics.
                  const metricColCount = BAR_METRICS.length + 3; // + p95/peak/err
                  if (r.infeasible) {
                    return (
                      <tr
                        key={r.agg.model}
                        className="border-t border-zinc-100 bg-zinc-50/40 text-zinc-500"
                        title={r.infeasible.reason}
                      >
                        <td className="p-3">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-semibold bg-zinc-100 text-zinc-500 border-zinc-200">
                            #{r.rank}
                          </span>
                        </td>
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <span
                              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                              style={{ backgroundColor: r.color }}
                            />
                            <span className="font-medium text-zinc-600 line-through decoration-zinc-300">
                              {r.agg.model}
                            </span>
                            <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide bg-amber-50 text-amber-700 border border-amber-200">
                              Infeasible
                            </span>
                          </div>
                        </td>
                        <td className="p-3 text-right">{r.agg.fileCount}</td>
                        <td className="p-3 text-right text-zinc-400">—</td>
                        <td
                          className="p-3 text-zinc-500 text-xs italic"
                          colSpan={metricColCount}
                        >
                          Skipped — {r.infeasible.reason}
                          {r.infeasible.required_ram_gb
                            ? ` (needs ≥ ${r.infeasible.required_ram_gb} GB)`
                            : ""}
                        </td>
                      </tr>
                    );
                  }
                  return (
                    <tr
                      key={r.agg.model}
                      className="border-t border-zinc-100 hover:bg-zinc-50/60"
                    >
                      <td className="p-3">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-semibold ${rankColor(r.rank)}`}
                        >
                          {r.rank <= 3 && <Medal className="w-3 h-3" />}#
                          {r.rank}
                        </span>
                      </td>
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <span
                            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                            style={{ backgroundColor: r.color }}
                          />
                          <span className="font-medium text-zinc-800">
                            {r.agg.model}
                          </span>
                        </div>
                      </td>
                      <td className="p-3 text-right text-zinc-600">
                        {r.agg.fileCount}
                      </td>
                      <td className="p-3 text-right">
                        <span
                          className="inline-block px-2 py-0.5 rounded font-semibold text-white"
                          style={{
                            backgroundColor: `hsl(${Math.round((r.score / 100) * 120)}, 65%, 45%)`,
                          }}
                        >
                          {r.score} / 100
                        </span>
                      </td>
                      {BAR_METRICS.map((m) => {
                        const raw = m.getValue(r.agg);
                        const norm = r.perMetric[m.id] ?? 0;
                        const display =
                          Math.abs(raw) >= 100
                            ? Math.round(raw)
                            : Math.round(raw * 100) / 100;
                        return (
                          <td
                            key={m.id}
                            className="p-3 text-right whitespace-nowrap"
                            title={`Normalized: ${norm}/100`}
                          >
                            <span className="text-zinc-800">
                              {display}
                              {m.unit}
                            </span>
                            <span className="ml-1.5 text-[10px] text-zinc-400">
                              ({norm})
                            </span>
                          </td>
                        );
                      })}
                      {(
                        [
                          {
                            id: "p95_latency_ms",
                            raw: r.agg.p95LatencyMs,
                            unit: " ms",
                          },
                          {
                            id: "peak_memory_mb",
                            raw: r.agg.peakMemoryMb,
                            unit: " MB",
                          },
                          {
                            id: "error_rate",
                            raw: Math.round(r.agg.errorRate * 1000) / 10,
                            unit: "%",
                          },
                        ] as const
                      ).map(({ id, raw, unit }) => {
                        const norm = r.perMetric[id] ?? 0;
                        return (
                          <td
                            key={id}
                            className="p-3 text-right whitespace-nowrap"
                            title={`Normalized: ${norm}/100`}
                          >
                            <span className="text-zinc-800">
                              {raw}
                              {unit}
                            </span>
                            <span className="ml-1.5 text-[10px] text-zinc-400">
                              ({norm})
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-zinc-500 leading-relaxed">
            <strong>Composite formula:</strong> each axis is min-max normalized
            to 0 – 100 across all models (inverted for &ldquo;lower is
            better&rdquo; axes), then a weighted average is taken. Axes used:{" "}
            {BAR_METRICS.length} <code>summary.*</code> metrics (incl. test
            pass rate), each at weight 1.0, plus three raw-derived axes
            computed from <code>results[*]</code> across all JSON files:{" "}
            <em>p95 latency</em> (weight 1.2), <em>peak memory</em>{" "}
            (weight 0.8) and <em>error rate</em> (weight 1.5) — total{" "}
            {BAR_METRICS.length + 3} axes. Numbers in parentheses next to each
            metric show its normalized score for that model.
          </p>
        </>
      )}
    </div>
  );
}
