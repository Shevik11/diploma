import { useEffect, useMemo, useState } from "react";
import { Loader2, LayoutDashboard, Trophy } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ScatterChart,
  Scatter,
  ZAxis,
  ComposedChart,
  Line,
  LineChart,
  Legend,
  RadialBarChart,
  RadialBar,
} from "recharts";
import { Checkbox } from "@/app/components/ui/checkbox";
import {
  api,
  BenchmarkResultFile,
  BenchmarkSummary,
  TestScriptResult,
  isInfeasible,
  variantId,
  variantLabel,
} from "@/app/services/api";

/**
 * A benchmark result file is considered "with results" for the dashboard
 * if the backend actually executed at least one prompt or one test script
 * for it. Infeasible runs (refused for lack of RAM) and empty placeholders
 * are excluded so the graphs don't show models that have nothing to plot.
 */
function hasAnyResult(f: BenchmarkResultFile): boolean {
  if (isInfeasible(f)) return false;
  const s = f.summary;
  const ranPrompts = !!s && ((s.successful || 0) > 0 || (s.total_prompts || 0) > 0);
  const ranTests = (f.test_results?.length ?? 0) > 0;
  return ranPrompts || ranTests;
}

/** Same idea, but at the loaded-summary level (used after the JSON fetch). */
function summaryHasAnyResult(s: BenchmarkSummary | undefined | null): boolean {
  if (!s) return false;
  if (s.infeasible) return false;
  const ranPrompts =
    !!s.summary &&
    ((s.summary.successful || 0) > 0 || (s.summary.total_prompts || 0) > 0);
  const ranTests = (s.test_results?.length ?? 0) > 0 || (s.results?.length ?? 0) > 0;
  return ranPrompts || ranTests;
}

// ─── Aggregate types & helpers ───────────────────────────────────────────────

export interface ModelAggregate {
  model: string;
  fileCount: number;
  summary: {
    total_prompts: number;
    successful: number;
    failed: number;
    success_rate: number;
    avg_tokens_per_second: number;
    avg_latency_ms: number;
    avg_first_token_latency_ms: number;
    total_tokens_generated: number;
    avg_cpu_percent: number;
    avg_memory_percent: number;
  };
  testPassRate: number;
  // Extra metrics derived from raw per-prompt `results` across all JSON files.
  p95LatencyMs: number;
  peakMemoryMb: number;
  avgPromptTokens: number;
  errorRate: number; // share of items with `error` set
  testsRun: number;
}

function avg(nums: number[]): number {
  const vals = nums.filter((n) => typeof n === "number" && !Number.isNaN(n));
  if (!vals.length) return 0;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}
function sum(nums: number[]): number {
  return nums
    .filter((n) => typeof n === "number" && !Number.isNaN(n))
    .reduce((a, b) => a + b, 0);
}

export function aggregateModel(
  model: string,
  summaries: BenchmarkSummary[],
): ModelAggregate {
  const s = summaries.map((x) => x.summary).filter(Boolean);
  const aggSummary = {
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
  let passed = 0,
    total = 0;
  summaries.forEach((sm) =>
    (sm.test_results || []).forEach((t: TestScriptResult) => {
      total++;
      if (t.status === "passed") passed++;
    }),
  );

  // Pull per-prompt raw stats so the leaderboard can use ALL JSON data.
  const allItems = summaries.flatMap((sm) => sm.results || []);
  const latencies = allItems
    .map((it) => it.inference?.total_duration_ms)
    .filter((v): v is number => typeof v === "number" && !Number.isNaN(v))
    .sort((a, b) => a - b);
  const p95 =
    latencies.length > 0
      ? latencies[Math.min(latencies.length - 1, Math.floor(latencies.length * 0.95))]
      : 0;
  const peakMem = allItems.reduce(
    (mx, it) => Math.max(mx, it.resources?.memory_peak_mb || 0),
    0,
  );
  const promptTokenList = allItems
    .map((it) => it.inference?.prompt_tokens || 0)
    .filter((v) => v > 0);
  const errors = allItems.filter((it) => !!it.error).length;

  return {
    model,
    fileCount: summaries.length,
    summary: aggSummary,
    testPassRate: total > 0 ? passed / total : 0,
    p95LatencyMs: Math.round(p95),
    peakMemoryMb: Math.round(peakMem),
    avgPromptTokens: avg(promptTokenList),
    errorRate: allItems.length > 0 ? errors / allItems.length : 0,
    testsRun: total,
  };
}

// ─── Color palette ────────────────────────────────────────────────────────────

const PALETTE = [
  "#18181b",
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#06b6d4",
  "#f97316",
  "#ec4899",
  "#84cc16",
  "#14b8a6",
  "#a855f7",
];
export function paletteColor(idx: number) {
  return PALETTE[idx % PALETTE.length];
}

// ─── Normalization ────────────────────────────────────────────────────────────

/** Normalize a set of values to [0, 100]. higherBetter: true → high raw = high score */
export function normalizeValues(values: number[], higherBetter: boolean): number[] {
  const valid = values.filter((v) => !Number.isNaN(v));
  if (!valid.length) return values.map(() => 0);
  const mn = Math.min(...valid);
  const mx = Math.max(...valid);
  if (mn === mx) return values.map(() => 50);
  return values.map((v) => {
    const n = (v - mn) / (mx - mn); // 0..1
    return Math.round((higherBetter ? n : 1 - n) * 100);
  });
}

/** Score color: 0 = red, 100 = green */
function scoreColor(score: number): string {
  const h = Math.round((score / 100) * 120); // 0→red, 120→green
  return `hsl(${h}, 65%, 48%)`;
}

// ─── Leaderboard helpers ──────────────────────────────────────────────────────

/**
 * Compute a unified composite score (0-100) per aggregate using all BAR_METRICS.
 * Each metric is normalized across the provided aggregates respecting higherBetter,
 * and the per-model average yields the composite score.
 */
export function computeCompositeScores(
  aggregates: ModelAggregate[],
): Map<string, number> {
  const matrix = BAR_METRICS.map((m) =>
    normalizeValues(
      aggregates.map((a) => m.getValue(a)),
      m.higherBetter,
    ),
  );
  const out = new Map<string, number>();
  aggregates.forEach((a, i) => {
    const colVals = matrix.map((col) => col[i]);
    const score = colVals.length
      ? Math.round(colVals.reduce((s, v) => s + v, 0) / colVals.length)
      : 0;
    out.set(a.model, score);
  });
  return out;
}

/** Sort by composite leaderboard score (best first). Pure — returns a new array. */
export function sortByComposite(
  aggregates: ModelAggregate[],
): ModelAggregate[] {
  const scores = computeCompositeScores(aggregates);
  return [...aggregates].sort(
    (a, b) => (scores.get(b.model) ?? 0) - (scores.get(a.model) ?? 0),
  );
}

/** Sort by a single metric (best first), respecting higherBetter. */
export function sortByMetric(
  aggregates: ModelAggregate[],
  metric: BarMetric,
): ModelAggregate[] {
  return [...aggregates].sort((a, b) => {
    const va = metric.getValue(a);
    const vb = metric.getValue(b);
    return metric.higherBetter ? vb - va : va - vb;
  });
}

// ─── Widget registry ──────────────────────────────────────────────────────────

export interface BarMetric {
  id: string;
  label: string;
  unit: string;
  hint: string;
  higherBetter: boolean;
  getValue: (a: ModelAggregate) => number;
}

export const BAR_METRICS: BarMetric[] = [
  {
    id: "avg_tokens_per_second",
    label: "Tokens / second",
    unit: " tok/s",
    hint: "Higher is better",
    higherBetter: true,
    getValue: (a) =>
      Math.round((a.summary.avg_tokens_per_second || 0) * 100) / 100,
  },
  {
    id: "avg_latency_ms",
    label: "Avg latency",
    unit: " ms",
    hint: "Lower is better",
    higherBetter: false,
    getValue: (a) => Math.round(a.summary.avg_latency_ms || 0),
  },
  {
    id: "avg_first_token_latency_ms",
    label: "First token latency",
    unit: " ms",
    hint: "Lower is better",
    higherBetter: false,
    getValue: (a) => Math.round(a.summary.avg_first_token_latency_ms || 0),
  },
  {
    id: "success_rate",
    label: "Success rate",
    unit: "%",
    hint: "Higher is better",
    higherBetter: true,
    getValue: (a) => Math.round((a.summary.success_rate || 0) * 100) / 100,
  },
  {
    id: "avg_cpu_percent",
    label: "CPU usage",
    unit: "%",
    hint: "Lower is better",
    higherBetter: false,
    getValue: (a) => Math.round((a.summary.avg_cpu_percent || 0) * 100) / 100,
  },
  {
    id: "avg_memory_percent",
    label: "Memory usage",
    unit: "%",
    hint: "Lower is better",
    higherBetter: false,
    getValue: (a) =>
      Math.round((a.summary.avg_memory_percent || 0) * 100) / 100,
  },
  {
    id: "total_tokens_generated",
    label: "Total tokens generated",
    unit: "",
    hint: "Higher is better",
    higherBetter: true,
    getValue: (a) => a.summary.total_tokens_generated || 0,
  },
  {
    id: "test_pass_rate",
    label: "Test pass rate",
    unit: "%",
    hint: "Higher is better",
    higherBetter: true,
    getValue: (a) => Math.round(a.testPassRate * 100 * 100) / 100,
  },
];

interface WidgetDef {
  id: string;
  label: string;
  description: string;
  group: "analysis" | "metrics";
}

const ANALYSIS_WIDGETS: WidgetDef[] = [
  {
    id: "scatter",
    label: "Efficiency scatter",
    description: "Latency vs throughput bubble chart",
    group: "analysis",
  },
  {
    id: "reliability",
    label: "Reliability",
    description: "Passed vs failed prompts (stacked bar)",
    group: "analysis",
  },
  {
    id: "composed",
    label: "Speed & Quality",
    description: "Throughput bars + success rate line",
    group: "analysis",
  },
  {
    id: "radialScore",
    label: "Overall score",
    description: "Composite score radial bar chart",
    group: "analysis",
  },
  {
    id: "throughputByDeployment",
    label: "Throughput by model (4c + opt RAM)",
    description: "Model ranking by TPS at 4 CPU cores and best RAM per model",
    group: "analysis",
  },
  {
    id: "enormHeatmap",
    label: "E_norm heatmap",
    description: "Normalized efficiency in CPU cores × RAM GB space",
    group: "analysis",
  },
  {
    id: "oomHeatmap",
    label: "OOM failure heatmap",
    description: "OOM-failure share in RAM × Model space",
    group: "analysis",
  },
  {
    id: "tpsTcoPareto",
    label: "TPS-TCO Pareto",
    description: "Scatter of all configs with Pareto-optimal frontier",
    group: "analysis",
  },
  {
    id: "ramImpact",
    label: "RAM impact",
    description: "How throughput changes with RAM per model",
    group: "analysis",
  },
  {
    id: "cpuImpact",
    label: "CPU impact",
    description: "How throughput changes with CPU cores per model",
    group: "analysis",
  },
];

const BAR_WIDGETS: WidgetDef[] = BAR_METRICS.map((m) => ({
  id: `bar_${m.id}`,
  label: m.label,
  description: m.hint,
  group: "metrics" as const,
}));

const ALL_WIDGETS: WidgetDef[] = [...ANALYSIS_WIDGETS, ...BAR_WIDGETS];

// ─── Tooltip helper ───────────────────────────────────────────────────────────

function TT({
  active,
  payload,
  label,
  unit = "",
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color?: string }>;
  label?: string;
  unit?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-zinc-200 rounded-lg px-3 py-2 shadow-sm text-xs space-y-1">
      {label && <div className="font-semibold text-zinc-800 mb-1">{label}</div>}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          {p.color && (
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: p.color }}
            />
          )}
          <span className="text-zinc-600">{p.name}:</span>
          <span className="font-medium text-zinc-800">
            {p.value}
            {unit}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─── 2. Scatter chart ─────────────────────────────────────────────────────────

function ScatterWidget({
  aggregates,
  colorMap,
}: {
  aggregates: ModelAggregate[];
  colorMap: Map<string, string>;
}) {
  return (
    <WidgetCard
      title="Efficiency scatter"
      hint="Top-left = fast & low latency · bubble size = success rate"
    >
      <ResponsiveContainer width="100%" height={400}>
        <ScatterChart margin={{ top: 10, right: 20, bottom: 80, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
          <XAxis
            type="number"
            dataKey="x"
            name="Latency"
            unit=" ms"
            label={{
              value: "Avg latency (ms)",
              position: "insideBottom",
              offset: -20,
              fontSize: 11,
              fill: "#71717a",
            }}
            tick={{ fontSize: 11, fill: "#71717a" }}
            tickLine={false}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Tokens/sec"
            unit=" tok/s"
            label={{
              value: "Tokens / sec",
              angle: -90,
              position: "insideLeft",
              offset: 10,
              fontSize: 11,
              fill: "#71717a",
            }}
            tick={{ fontSize: 11, fill: "#71717a" }}
            tickLine={false}
          />
          <ZAxis
            type="number"
            dataKey="z"
            range={[60, 400]}
            name="Success rate"
            unit="%"
          />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            content={(props) => {
              if (!props.active || !props.payload?.length) return null;
              const p = props.payload[0].payload as {
                model: string;
                x: number;
                y: number;
                z: number;
              };
              return (
                <div className="bg-white border border-zinc-200 rounded-lg px-3 py-2 shadow-sm text-xs space-y-0.5">
                  <div className="font-semibold text-zinc-800 mb-1">
                    {p.model}
                  </div>
                  <div className="text-zinc-600">
                    Latency:{" "}
                    <span className="font-medium text-zinc-800">{p.x} ms</span>
                  </div>
                  <div className="text-zinc-600">
                    Tokens/s:{" "}
                    <span className="font-medium text-zinc-800">
                      {p.y} tok/s
                    </span>
                  </div>
                  <div className="text-zinc-600">
                    Success rate:{" "}
                    <span className="font-medium text-zinc-800">{p.z}%</span>
                  </div>
                </div>
              );
            }}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            verticalAlign="bottom"
            wrapperStyle={{
              paddingTop: "40px",
              fontSize: 11,
              color: "#52525b",
            }}
          />
          {aggregates.map((a) => (
            <Scatter
              key={a.model}
              name={a.model}
              data={[
                {
                  x: Math.round(a.summary.avg_latency_ms || 0),
                  y:
                    Math.round((a.summary.avg_tokens_per_second || 0) * 10) /
                    10,
                  z: Math.round((a.summary.success_rate || 0) * 10) / 10,
                  model: a.model,
                },
              ]}
              fill={colorMap.get(a.model) || "#18181b"}
              fillOpacity={0.85}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </WidgetCard>
  );
}

// ─── 3. Stacked reliability bar chart ─────────────────────────────────────────

function ReliabilityWidget({
  aggregates,
  colorMap,
}: {
  aggregates: ModelAggregate[];
  colorMap: Map<string, string>;
}) {
  const data = aggregates.map((a) => ({
    model: a.model,
    label: a.model.length > 14 ? `${a.model.slice(0, 13)}…` : a.model,
    Successful: a.summary.successful || 0,
    Failed: a.summary.failed || 0,
    color: colorMap.get(a.model) || "#18181b",
  }));
  const barH = Math.max(200, data.length * 44 + 40);

  return (
    <WidgetCard
      title="Reliability"
      hint="Successful vs failed prompts across all runs"
    >
      <div style={{ height: barH }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
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
              tick={{ fontSize: 11, fill: "#71717a" }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={130}
              tick={{ fontSize: 11, fill: "#71717a" }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              content={(props) => (
                <TT
                  active={props.active}
                  payload={props.payload?.map((p) => ({
                    name: String(p.dataKey),
                    value: Number(p.value),
                    color: String(p.fill),
                  }))}
                  label={props.label}
                />
              )}
            />
            <Legend
              iconType="square"
              iconSize={10}
              wrapperStyle={{ fontSize: 11, color: "#52525b" }}
            />
            <Bar dataKey="Successful" stackId="a" fill="#10b981" />
            <Bar
              dataKey="Failed"
              stackId="a"
              fill="#ef4444"
              radius={[0, 4, 4, 0]}
              label={{
                position: "right",
                fontSize: 10,
                fill: "#52525b",
                formatter: (v: number) => (v > 0 ? `${v} fail` : ""),
              }}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </WidgetCard>
  );
}

// ─── 4. Composed chart (throughput bars + success rate line) ──────────────────

function ComposedWidget({
  aggregates,
  colorMap,
}: {
  aggregates: ModelAggregate[];
  colorMap: Map<string, string>;
}) {
  const data = aggregates.map((a) => ({
    model: a.model.length > 12 ? `${a.model.slice(0, 11)}…` : a.model,
    fullModel: a.model,
    "Tokens/s": Math.round((a.summary.avg_tokens_per_second || 0) * 10) / 10,
    "Success %": Math.round((a.summary.success_rate || 0) * 10) / 10,
    color: colorMap.get(a.model) || "#18181b",
  }));

  return (
    <WidgetCard
      title="Speed & Quality"
      hint="Bars = tokens/sec (left axis) · line = success rate (right axis)"
    >
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart
          data={data}
          margin={{ top: 10, right: 48, bottom: 36, left: 10 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
          <XAxis
            dataKey="model"
            tick={{ fontSize: 10, fill: "#71717a" }}
            tickLine={false}
            angle={-35}
            textAnchor="end"
            height={60}
          />
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 11, fill: "#71717a" }}
            tickLine={false}
            axisLine={false}
            label={{
              value: "tok/s",
              angle: -90,
              position: "insideLeft",
              offset: 12,
              fontSize: 10,
              fill: "#71717a",
            }}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            domain={[0, 100]}
            tick={{ fontSize: 11, fill: "#71717a" }}
            tickLine={false}
            axisLine={false}
            label={{
              value: "%",
              angle: 90,
              position: "insideRight",
              offset: 12,
              fontSize: 10,
              fill: "#71717a",
            }}
          />
          <Tooltip
            content={(props) => (
              <TT
                active={props.active}
                payload={props.payload?.map((p) => ({
                  name: String(p.dataKey),
                  value: Number(p.value),
                  color: p.color,
                }))}
                label={props.payload?.[0]?.payload?.fullModel ?? props.label}
              />
            )}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 11, color: "#52525b" }}
          />
          <Bar
            yAxisId="left"
            dataKey="Tokens/s"
            radius={[4, 4, 0, 0]}
            maxBarSize={40}
          >
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Bar>
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="Success %"
            stroke="#6366f1"
            strokeWidth={2}
            dot={{ r: 4, fill: "#6366f1", strokeWidth: 0 }}
            activeDot={{ r: 6 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </WidgetCard>
  );
}

// ─── 5. Radial bar (overall composite score) ──────────────────────────────────

function RadialScoreWidget({
  aggregates,
  colorMap,
}: {
  aggregates: ModelAggregate[];
  colorMap: Map<string, string>;
}) {
  // Compute composite score: average of all normalized metric scores
  const metricsForScore = [
    {
      getValue: (a: ModelAggregate) => a.summary.avg_tokens_per_second || 0,
      higherBetter: true,
    },
    {
      getValue: (a: ModelAggregate) => a.summary.avg_latency_ms || 0,
      higherBetter: false,
    },
    {
      getValue: (a: ModelAggregate) => a.summary.success_rate || 0,
      higherBetter: true,
    },
    {
      getValue: (a: ModelAggregate) => a.summary.avg_cpu_percent || 0,
      higherBetter: false,
    },
    {
      getValue: (a: ModelAggregate) => a.summary.avg_memory_percent || 0,
      higherBetter: false,
    },
    {
      getValue: (a: ModelAggregate) => a.testPassRate * 100,
      higherBetter: true,
    },
  ];

  // For each metric, normalize across all aggregates, then avg per model
  const scoreMatrix = metricsForScore.map((m) => {
    const raw = aggregates.map(m.getValue);
    return normalizeValues(raw, m.higherBetter);
  });

  const compositeScores = aggregates.map((_a, idx) =>
    Math.round(avg(scoreMatrix.map((col) => col[idx]))),
  );

  const data = aggregates
    .map((a, i) => ({
      name: a.model.length > 16 ? `${a.model.slice(0, 15)}…` : a.model,
      fullName: a.model,
      score: compositeScores[i],
      fill: colorMap.get(a.model) || paletteColor(i),
    }))
    .sort((a, b) => b.score - a.score);

  return (
    <WidgetCard
      title="Overall score"
      hint="Composite of 6 normalized metrics (100 = best possible)"
    >
      <ResponsiveContainer
        width="100%"
        height={Math.max(240, data.length * 40 + 60)}
      >
        <RadialBarChart
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={30}
          outerRadius="85%"
          barSize={18}
          startAngle={180}
          endAngle={-180}
        >
          <RadialBar
            dataKey="score"
            background={{ fill: "#f4f4f5" }}
            cornerRadius={6}
            label={{
              position: "insideStart",
              fill: "#fff",
              fontSize: 10,
              fontWeight: 600,
            }}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            formatter={(value: string) => {
              const d = data.find((x) => x.name === value);
              return `${value} (${d?.score ?? "—"})`;
            }}
            wrapperStyle={{ fontSize: 11, color: "#52525b" }}
          />
          <Tooltip
            content={(props) => {
              if (!props.active || !props.payload?.length) return null;
              const p = props.payload[0].payload as {
                fullName: string;
                score: number;
              };
              return (
                <div className="bg-white border border-zinc-200 rounded-lg px-3 py-2 shadow-sm text-xs">
                  <div className="font-semibold text-zinc-800">
                    {p.fullName}
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
        </RadialBarChart>
      </ResponsiveContainer>
    </WidgetCard>
  );
}

// ─── 6. Heatmap ───────────────────────────────────────────────────────────────

const HEATMAP_COLS = [
  {
    key: "avg_tokens_per_second",
    label: "Tok/s",
    higherBetter: true,
    getValue: (a: ModelAggregate) => a.summary.avg_tokens_per_second || 0,
  },
  {
    key: "avg_latency_ms",
    label: "Latency",
    higherBetter: false,
    getValue: (a: ModelAggregate) => a.summary.avg_latency_ms || 0,
  },
  {
    key: "avg_first_token_latency_ms",
    label: "TTFT",
    higherBetter: false,
    getValue: (a: ModelAggregate) => a.summary.avg_first_token_latency_ms || 0,
  },
  {
    key: "success_rate",
    label: "Success%",
    higherBetter: true,
    getValue: (a: ModelAggregate) => a.summary.success_rate || 0,
  },
  {
    key: "avg_cpu_percent",
    label: "CPU%",
    higherBetter: false,
    getValue: (a: ModelAggregate) => a.summary.avg_cpu_percent || 0,
  },
  {
    key: "avg_memory_percent",
    label: "Mem%",
    higherBetter: false,
    getValue: (a: ModelAggregate) => a.summary.avg_memory_percent || 0,
  },
  {
    key: "test_pass_rate",
    label: "Tests%",
    higherBetter: true,
    getValue: (a: ModelAggregate) => a.testPassRate * 100,
  },
];

function fmt(v: number): string {
  if (v === 0) return "—";
  return Math.abs(v) >= 100
    ? String(Math.round(v))
    : String(Math.round(v * 10) / 10);
}

function HeatmapWidget({ aggregates }: { aggregates: ModelAggregate[] }) {
  // Per-column normalization
  const scoreGrid: number[][] = HEATMAP_COLS.map((col) => {
    const raw = aggregates.map(col.getValue);
    return normalizeValues(raw, col.higherBetter);
  });

  return (
    <WidgetCard
      title="Performance heatmap"
      hint="Green = best in column · red = worst · hover for raw value"
      fullWidth
    >
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr>
              <th className="text-left p-2 text-zinc-500 font-medium w-36">
                Model
              </th>
              {HEATMAP_COLS.map((col) => (
                <th
                  key={col.key}
                  className="p-2 text-center text-zinc-500 font-medium whitespace-nowrap"
                >
                  {col.label}
                  <span className="block text-[10px] font-normal text-zinc-400">
                    {col.higherBetter ? "▲ higher" : "▼ lower"}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {aggregates.map((a, ri) => (
              <tr key={a.model} className={ri % 2 === 0 ? "bg-zinc-50/50" : ""}>
                <td
                  className="p-2 text-zinc-700 font-medium truncate max-w-[144px]"
                  title={a.model}
                >
                  {a.model}
                </td>
                {HEATMAP_COLS.map((col, ci) => {
                  const score = scoreGrid[ci][ri];
                  const raw = col.getValue(a);
                  return (
                    <td key={col.key} className="p-1 text-center">
                      <div
                        title={`${a.model} · ${col.label}: ${fmt(raw)} (score: ${score})`}
                        className="rounded px-2 py-1.5 font-mono font-semibold text-white text-[11px]"
                        style={{ backgroundColor: scoreColor(score) }}
                      >
                        {fmt(raw)}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Color scale legend */}
      <div className="flex items-center gap-2 mt-3 text-[10px] text-zinc-400">
        <span>Worst</span>
        <div
          className="h-2 flex-1 rounded"
          style={{
            background:
              "linear-gradient(to right, hsl(0,65%,48%), hsl(60,65%,48%), hsl(120,65%,48%))",
          }}
        />
        <span>Best</span>
      </div>
    </WidgetCard>
  );
}

// ─── 7. Throughput by model (4 CPU cores + optimal RAM) ───────────────────────

function median(nums: number[]): number {
  const vals = nums
    .filter((n) => typeof n === "number" && !Number.isNaN(n))
    .sort((a, b) => a - b);
  if (!vals.length) return 0;
  const mid = Math.floor(vals.length / 2);
  return vals.length % 2 === 0
    ? (vals[mid - 1] + vals[mid]) / 2
    : vals[mid];
}

function ThroughputByDeploymentWidget({
  usableFiles,
  summaryCache,
  selectedModels,
}: {
  usableFiles: BenchmarkResultFile[];
  summaryCache: Record<string, BenchmarkSummary>;
  selectedModels: Set<string>;
}) {
  const isSingleModel = selectedModels.size === 1;

  const data = useMemo(() => {
    const byModelRam = new Map<string, { model: string; ram: number; values: number[] }>();
    usableFiles.forEach((f) => {
      if (!selectedModels.has(variantId(f))) return;
      const s = summaryCache[f.filename];
      if (!summaryHasAnyResult(s)) return;
      if (f.cpu_cores == null || Number(f.cpu_cores) !== 4) return;
      if (f.ram_gb == null) return;
      const tps = s.summary?.avg_tokens_per_second || 0;
      if (tps <= 0) return;
      const model = f.model || s.model || "unknown-model";
      const ram = Number(f.ram_gb);
      const key = `${model}__${ram}`;
      const prev = byModelRam.get(key) ?? { model, ram, values: [] };
      prev.values.push(tps);
      byModelRam.set(key, prev);
    });

    if (isSingleModel) {
      // Show all RAM variants for the single selected model
      return Array.from(byModelRam.values())
        .sort((a, b) => a.ram - b.ram)
        .map((entry, i) => ({
          model: entry.model,
          ram: entry.ram,
          medianTok: Math.round(median(entry.values) * 100) / 100,
          runs: entry.values.length,
          label: `${entry.ram} GB RAM`,
          color: paletteColor(i),
        }));
    }

    // Multi-model: pick optimal RAM per model at 4 cores: highest median TPS, tie -> lower RAM.
    const bestByModel = new Map<
      string,
      { model: string; ram: number; medianTok: number; runs: number }
    >();
    byModelRam.forEach((entry) => {
      const med = Math.round(median(entry.values) * 100) / 100;
      const candidate = {
        model: entry.model,
        ram: entry.ram,
        medianTok: med,
        runs: entry.values.length,
      };
      const prev = bestByModel.get(entry.model);
      if (
        !prev ||
        candidate.medianTok > prev.medianTok ||
        (candidate.medianTok === prev.medianTok && candidate.ram < prev.ram)
      ) {
        bestByModel.set(entry.model, candidate);
      }
    });

    return Array.from(bestByModel.values())
      .sort((a, b) => b.medianTok - a.medianTok)
      .map((v, i) => ({
        ...v,
        label: v.model,
        color: paletteColor(i),
      }));
  }, [usableFiles, summaryCache, selectedModels, isSingleModel]);

  const singleModelName = isSingleModel ? Array.from(selectedModels)[0] : null;

  if (!data.length) {
    return (
      <WidgetCard
        title={
          isSingleModel && singleModelName
            ? `Throughput by RAM — ${singleModelName} (4 cores)`
            : "Throughput by model (4 cores + optimal RAM)"
        }
        hint="Ranking unavailable: no runs with exactly 4 CPU cores in current selection"
        fullWidth
      >
        <p className="text-sm text-zinc-400 py-6 text-center">
          No model throughput data available for 4-core configuration.
        </p>
      </WidgetCard>
    );
  }

  const barH = Math.max(220, data.length * 48 + 36);
  return (
    <WidgetCard
      title={
        isSingleModel && singleModelName
          ? `Throughput by RAM — ${singleModelName} (4 cores)`
          : "Throughput by model (4 cores + optimal RAM)"
      }
      hint={
        isSingleModel
          ? "All RAM configurations for this model at exactly 4 CPU cores"
          : "Per model: pick RAM with highest median TPS at exactly 4 CPU cores"
      }
      fullWidth
    >
      <div style={{ height: barH }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 80, bottom: 4, left: 4 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              horizontal={false}
              stroke="#e4e4e7"
            />
            <XAxis
              type="number"
              tick={{ fontSize: 11, fill: "#71717a" }}
              tickLine={false}
              axisLine={false}
              unit=" tok/s"
            />
            <YAxis
              type="category"
              dataKey="label"
              width={190}
              tick={{ fontSize: 11, fill: "#71717a" }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              content={(props) => {
                if (!props.active || !props.payload?.length) return null;
                const p = props.payload[0].payload as {
                  model: string;
                  ram: number;
                  medianTok: number;
                  runs: number;
                };
                return (
                  <div className="bg-white border border-zinc-200 rounded-lg px-3 py-2 shadow-sm text-xs space-y-0.5">
                    <div className="font-semibold text-zinc-800">
                      {isSingleModel ? `${p.ram} GB RAM` : p.model}
                    </div>
                    {!isSingleModel && (
                      <div className="text-zinc-600">
                        Optimal RAM @4c:{" "}
                        <span className="font-medium text-zinc-800">
                          {p.ram} GB
                        </span>
                      </div>
                    )}
                    <div className="text-zinc-600">
                      Median TPS:{" "}
                      <span className="font-medium text-zinc-800">
                        {p.medianTok} tok/s
                      </span>
                    </div>
                    <div className="text-zinc-600">
                      Runs:{" "}
                      <span className="font-medium text-zinc-800">
                        {p.runs}
                      </span>
                    </div>
                  </div>
                );
              }}
            />
            <Bar
              dataKey="medianTok"
              radius={[0, 4, 4, 0]}
              maxBarSize={34}
              label={{
                position: "right",
                fontSize: 10,
                fill: "#52525b",
                formatter: (v: number, _n: string, row: { payload?: { ram?: number } }) =>
                  v > 0
                    ? `${v} tok/s${!isSingleModel && row?.payload?.ram ? ` (${row.payload.ram}GB)` : ""}`
                    : "",
              }}
            >
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </WidgetCard>
  );
}

// ─── 8. OOM failure heatmap (RAM_GB × Model) ─────────────────────────────────

function oomRateColor(ratePct: number): string {
  // 0% => green (120), 100% => red (0)
  const h = Math.round((1 - Math.max(0, Math.min(100, ratePct)) / 100) * 120);
  return `hsl(${h}, 65%, 48%)`;
}

function isOomLikeErrorType(v: unknown): boolean {
  const s = String(v || "").toLowerCase();
  return (
    s.includes("oom") ||
    s.includes("out of memory") ||
    s === "server_error" ||
    s === "http_500" ||
    s === "http_503"
  );
}

function extractOomFailureRate(summary: BenchmarkSummary): number | null {
  const tests = Array.isArray(summary.test_results) ? summary.test_results : [];
  const oomTest = tests.find((t) => t?.id === "oom_detection");
  const raw = (oomTest as { raw_data?: unknown } | undefined)?.raw_data as
    | {
        burst?: {
          error_types?: unknown[];
          runs?: Array<{ success?: boolean; error_type?: unknown }>;
        };
      }
    | undefined;
  const burst = raw?.burst;
  if (burst) {
    const errTypes = Array.isArray(burst.error_types) ? burst.error_types : [];
    if (errTypes.length > 0) {
      // Figure 4.4 definition: rate over repeated launches (use first 10 when available).
      const sample = errTypes.slice(0, 10);
      const oomCount = sample.filter(isOomLikeErrorType).length;
      return sample.length > 0 ? (oomCount / sample.length) * 100 : null;
    }
    const runs = Array.isArray(burst.runs) ? burst.runs : [];
    if (runs.length > 0) {
      const sample = runs.slice(0, 10);
      const oomCount = sample.filter(
        (r) => r.success === false && isOomLikeErrorType(r.error_type),
      ).length;
      return sample.length > 0 ? (oomCount / sample.length) * 100 : null;
    }
  }

  // Fallback for legacy files: infer from Phase-1 prompt-level failures.
  const rs = Array.isArray(summary.results) ? summary.results : [];
  if (!rs.length) return null;
  const sample = rs.slice(0, 10);
  const oomCount = sample.filter((r) => {
    if (r.success) return false;
    const err = String(r.error || "").toLowerCase();
    return (
      err.includes("oom") ||
      err.includes("out of memory") ||
      err.includes("http 500") ||
      err.includes("http 503") ||
      err.includes("terminated with exit code -1")
    );
  }).length;
  return sample.length > 0 ? (oomCount / sample.length) * 100 : null;
}

function OomHeatmapWidget({
  usableFiles,
  summaryCache,
  selectedModels,
}: {
  usableFiles: BenchmarkResultFile[];
  summaryCache: Record<string, BenchmarkSummary>;
  selectedModels: Set<string>;
}) {
  const { modelNames, ramValues, cellMap } = useMemo(() => {
    const modelSet = new Set<string>();
    const ramSet = new Set<number>();
    const acc = new Map<string, { sum: number; count: number }>();

    usableFiles.forEach((f) => {
      if (!selectedModels.has(variantId(f))) return;
      if (f.ram_gb == null) return;
      const summary = summaryCache[f.filename];
      if (!summary) return;
      const rate = extractOomFailureRate(summary);
      if (rate == null || Number.isNaN(rate)) return;
      const model = f.model || summary.model || "unknown-model";
      const ram = Number(f.ram_gb);
      modelSet.add(model);
      ramSet.add(ram);
      const key = `${model}__${ram}`;
      const prev = acc.get(key) ?? { sum: 0, count: 0 };
      acc.set(key, { sum: prev.sum + rate, count: prev.count + 1 });
    });

    const cell = new Map<string, { rate: number; runs: number }>();
    acc.forEach((v, k) => {
      cell.set(k, { rate: v.count > 0 ? v.sum / v.count : 0, runs: v.count });
    });

    return {
      modelNames: Array.from(modelSet).sort((a, b) => a.localeCompare(b)),
      ramValues: Array.from(ramSet).sort((a, b) => a - b),
      cellMap: cell,
    };
  }, [usableFiles, summaryCache, selectedModels]);

  if (!modelNames.length || !ramValues.length) {
    return (
      <WidgetCard
        title="OOM failure heatmap"
        hint="RAM × Model, 0% (green) → 100% (red)"
        fullWidth
      >
        <p className="text-sm text-zinc-400 py-6 text-center">
          No OOM data available yet. Run benchmarks with the OOM Detection test.
        </p>
      </WidgetCard>
    );
  }

  return (
    <WidgetCard
      title="OOM failure heatmap"
      hint="RAM × Model, OOM-failure share over repeated launches (up to first 10 repeats)"
      fullWidth
    >
      <div className="overflow-x-auto">
        <table className="text-xs border-collapse min-w-full">
          <thead>
            <tr>
              <th className="p-2 text-left text-zinc-400 font-medium whitespace-nowrap w-24">
                RAM \ Model
              </th>
              {modelNames.map((m) => (
                <th
                  key={m}
                  className="p-2 text-center text-zinc-500 font-medium whitespace-nowrap min-w-[110px]"
                  title={m}
                >
                  {m}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ramValues.map((ram) => (
              <tr key={ram}>
                <td className="p-2 text-zinc-600 font-medium whitespace-nowrap">
                  {ram} GB
                </td>
                {modelNames.map((m) => {
                  const key = `${m}__${ram}`;
                  const cell = cellMap.get(key);
                  if (!cell) {
                    return (
                      <td key={m} className="p-1 text-center">
                        <div className="rounded px-2 py-2.5 text-zinc-300 bg-zinc-100 text-[11px]">
                          —
                        </div>
                      </td>
                    );
                  }
                  const rate = Math.round(cell.rate * 10) / 10;
                  return (
                    <td key={m} className="p-1 text-center">
                      <div
                        title={`${m} @ ${ram} GB RAM\nOOM failure rate: ${rate}%\nRuns: ${cell.runs}`}
                        className="rounded px-2 py-2.5 font-mono font-semibold text-white text-[11px] cursor-default select-none"
                        style={{ backgroundColor: oomRateColor(rate) }}
                      >
                        {rate}%
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-2 mt-3 text-[10px] text-zinc-400">
        <span>0% OOM</span>
        <div
          className="h-2 flex-1 rounded"
          style={{
            background:
              "linear-gradient(to right, hsl(120,65%,48%), hsl(60,65%,48%), hsl(0,65%,48%))",
          }}
        />
        <span>100% OOM</span>
      </div>
    </WidgetCard>
  );
}

// ─── 9. TPS–TCO scatter with Pareto frontier ──────────────────────────────────

type InfraProfile = {
  id: string;
  cpu_cores: number;
  ram_gb: number;
  usd_per_hour: number;
};

const INFRA_PROFILES: InfraProfile[] = [
  { id: "edge-cpu-1c-1g", cpu_cores: 1, ram_gb: 1, usd_per_hour: 0.0061 },
  { id: "edge-cpu-2c-2g", cpu_cores: 2, ram_gb: 2, usd_per_hour: 0.0157 },
  { id: "server-cpu-4c-8g", cpu_cores: 4, ram_gb: 8, usd_per_hour: 0.084 },
  { id: "server-cpu-8c-16g", cpu_cores: 8, ram_gb: 16, usd_per_hour: 0.168 },
];

function pickHwProfile(ram: number, cpu: number): InfraProfile | null {
  const fit = INFRA_PROFILES.filter((p) => p.ram_gb >= ram && p.cpu_cores >= cpu);
  if (!fit.length) return null;
  return [...fit].sort((a, b) => a.usd_per_hour - b.usd_per_hour)[0];
}

function usdPerMillionTokens(usdPerHour: number, tokPerS: number): number | null {
  if (!tokPerS || tokPerS <= 0) return null;
  const tokensPerHour = tokPerS * 3600;
  if (tokensPerHour <= 0) return null;
  const hoursPerMillion = 1_000_000 / tokensPerHour;
  return usdPerHour * hoursPerMillion;
}

type TpsTcoPoint = {
  id: string;
  model: string;
  ram: number;
  cpu: number;
  technology: string;
  platform: string;
  tps: number;
  tco: number;
  hwProfile: string;
  pareto?: boolean;
};

function TpsTcoParetoWidget({
  usableFiles,
  summaryCache,
  selectedModels,
}: {
  usableFiles: BenchmarkResultFile[];
  summaryCache: Record<string, BenchmarkSummary>;
  selectedModels: Set<string>;
}) {
  const { points, pareto } = useMemo(() => {
    const pts: TpsTcoPoint[] = [];
    usableFiles.forEach((f) => {
      if (!selectedModels.has(variantId(f))) return;
      if (f.ram_gb == null || f.cpu_cores == null) return;
      const s = summaryCache[f.filename];
      if (!summaryHasAnyResult(s)) return;
      const tps = s.summary?.avg_tokens_per_second || 0;
      if (tps <= 0) return;
      const hw = pickHwProfile(Number(f.ram_gb), Number(f.cpu_cores));
      if (!hw) return;
      const tco = usdPerMillionTokens(hw.usd_per_hour, tps);
      if (tco == null || Number.isNaN(tco)) return;
      pts.push({
        id: f.filename,
        model: f.model || s.model || "unknown-model",
        ram: Number(f.ram_gb),
        cpu: Number(f.cpu_cores),
        technology: f.technology || s.technology || "unknown-tech",
        platform: f.platform || s.platform || "unknown-platform",
        tps: Math.round(tps * 100) / 100,
        tco: Math.round(tco * 1000) / 1000,
        hwProfile: hw.id,
      });
    });

    // Pareto front for: maximize TPS, minimize TCO.
    const byCostAsc = [...pts].sort((a, b) => a.tco - b.tco || b.tps - a.tps);
    const front: TpsTcoPoint[] = [];
    let bestTps = -Infinity;
    byCostAsc.forEach((p) => {
      if (p.tps > bestTps) {
        front.push({ ...p, pareto: true });
        bestTps = p.tps;
      }
    });
    const frontIds = new Set(front.map((p) => p.id));
    const all = pts.map((p) => ({ ...p, pareto: frontIds.has(p.id) }));
    return {
      points: all,
      pareto: [...front].sort((a, b) => a.tps - b.tps),
    };
  }, [usableFiles, summaryCache, selectedModels]);

  if (!points.length) {
    return (
      <WidgetCard
        title="TPS–TCO Pareto"
        hint="No feasible configurations with TPS + RAM/CPU metadata"
        fullWidth
      >
        <p className="text-sm text-zinc-400 py-6 text-center">
          No data to build TPS–TCO scatter. Run benchmarks on RAM/CPU configs first.
        </p>
      </WidgetCard>
    );
  }

  return (
    <WidgetCard
      title="TPS–TCO Pareto"
      hint={`All feasible configs: ${points.length} · Pareto-optimal: ${pareto.length}`}
      fullWidth
    >
      <ResponsiveContainer width="100%" height={420}>
        <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
          <XAxis
            type="number"
            dataKey="x"
            name="TCO"
            unit=" USD / 1M tok"
            tick={{ fontSize: 11, fill: "#71717a" }}
            tickLine={false}
            label={{
              value: "TCO (USD per 1M tokens)",
              position: "insideBottom",
              offset: -10,
              fontSize: 11,
              fill: "#71717a",
            }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="TPS"
            unit=" tok/s"
            tick={{ fontSize: 11, fill: "#71717a" }}
            tickLine={false}
            label={{
              value: "Throughput (tok/s)",
              angle: -90,
              position: "insideLeft",
              offset: 10,
              fontSize: 11,
              fill: "#71717a",
            }}
          />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            content={(props) => {
              if (!props.active || !props.payload?.length) return null;
              const p = props.payload[0].payload as {
                model: string;
                tco: number;
                tps: number;
                ram: number;
                cpu: number;
                technology: string;
                platform: string;
                pareto?: boolean;
              };
              return (
                <div className="bg-white border border-zinc-200 rounded-lg px-3 py-2 shadow-sm text-xs space-y-0.5">
                  <div className="font-semibold text-zinc-800">{p.model}</div>
                  <div className="text-zinc-600">
                    Config:{" "}
                    <span className="font-medium text-zinc-800">
                      {p.ram}GB / {p.cpu}c · {p.technology}/{p.platform}
                    </span>
                  </div>
                  <div className="text-zinc-600">
                    TPS: <span className="font-medium text-zinc-800">{p.tps}</span>
                  </div>
                  <div className="text-zinc-600">
                    TCO: <span className="font-medium text-zinc-800">{p.tco} USD / 1M</span>
                  </div>
                  {p.pareto && (
                    <div className="text-amber-700 font-medium">Pareto-optimal</div>
                  )}
                </div>
              );
            }}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            verticalAlign="top"
            wrapperStyle={{ fontSize: 11, color: "#52525b" }}
          />
          <Scatter
            name="All configurations"
            data={points.map((p) => ({ ...p, x: p.tco, y: p.tps }))}
            fill="#94a3b8"
            fillOpacity={0.65}
          />
          <Scatter
            name="Pareto frontier"
            data={pareto.map((p) => ({ ...p, x: p.tco, y: p.tps }))}
            fill="#f59e0b"
            fillOpacity={1}
          />
        </ScatterChart>
      </ResponsiveContainer>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr>
              <th className="text-left p-2 text-zinc-500 font-medium">#</th>
              <th className="text-left p-2 text-zinc-500 font-medium">Model</th>
              <th className="text-left p-2 text-zinc-500 font-medium">Config</th>
              <th className="text-right p-2 text-zinc-500 font-medium">TPS</th>
              <th className="text-right p-2 text-zinc-500 font-medium">TCO</th>
            </tr>
          </thead>
          <tbody>
            {pareto.map((p, i) => (
              <tr key={p.id} className={i % 2 === 0 ? "bg-zinc-50/50" : ""}>
                <td className="p-2 text-zinc-600">{i + 1}</td>
                <td className="p-2 text-zinc-700">{p.model}</td>
                <td className="p-2 text-zinc-600">
                  {p.ram}GB / {p.cpu}c · {p.technology}/{p.platform}
                </td>
                <td className="p-2 text-right font-mono text-zinc-800">{p.tps}</td>
                <td className="p-2 text-right font-mono text-zinc-800">
                  {p.tco}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </WidgetCard>
  );
}

// ─── 10. E_norm heatmap (CPU_cores × RAM_GB per model) ───────────────────────

/**
 * E_norm heatmap (CPU_cores x RAM_GB).
 *
 * E(m, p, c) = avg_tokens_per_second / sqrt((avg_cpu_percent/100) * (avg_memory_percent/100))
 *
 * E_norm(m, p, c) = E(m, p, c) / max_{(m', p', c') in O} E(m', p', c')
 *
 * O is the set of all measured configurations (all models, platforms, hardware settings).
 * E_norm in [0, 1]; the configuration with E_norm = 1 is the reference point.
 */

/** Build per-cell average E (and component metrics) for one base model. */
function buildModelCells(
  model: string,
  usableFiles: BenchmarkResultFile[],
  summaryCache: Record<string, BenchmarkSummary>,
): {
  cpuValues: number[];
  ramValues: number[];
  cells: Map<string, { e: number; tok: number; cpu: number; mem: number }>;
} {
  const acc = new Map<
    string,
    { eSum: number; count: number; tok: number; cpu: number; mem: number }
  >();
  usableFiles.forEach((f) => {
    if (f.model !== model || f.cpu_cores == null || f.ram_gb == null) return;
    const s = summaryCache[f.filename]?.summary;
    if (!s) return;
    const tok = s.avg_tokens_per_second || 0;
    const cpu = s.avg_cpu_percent || 0;
    const mem = s.avg_memory_percent || 0;
    const denom = Math.sqrt((cpu / 100) * (mem / 100));
    const e = denom > 0 ? tok / denom : 0;
    const key = `${f.cpu_cores}_${f.ram_gb}`;
    const prev = acc.get(key) ?? { eSum: 0, count: 0, tok: 0, cpu: 0, mem: 0 };
    acc.set(key, {
      eSum: prev.eSum + e,
      count: prev.count + 1,
      tok: prev.tok + tok,
      cpu: prev.cpu + cpu,
      mem: prev.mem + mem,
    });
  });

  const cells = new Map<
    string,
    { e: number; tok: number; cpu: number; mem: number }
  >();
  const cpuSet = new Set<number>();
  const ramSet = new Set<number>();
  acc.forEach((v, key) => {
    const [cpuStr, ramStr] = key.split("_");
    cpuSet.add(Number(cpuStr));
    ramSet.add(Number(ramStr));
    cells.set(key, {
      e: v.count > 0 ? v.eSum / v.count : 0,
      tok: v.count > 0 ? v.tok / v.count : 0,
      cpu: v.count > 0 ? v.cpu / v.count : 0,
      mem: v.count > 0 ? v.mem / v.count : 0,
    });
  });

  return {
    cpuValues: [...cpuSet].sort((a, b) => a - b),
    ramValues: [...ramSet].sort((a, b) => a - b),
    cells,
  };
}

/** Renders a single model's CPU×RAM E_norm grid. */
function ModelEGrid({
  model,
  cpuValues,
  ramValues,
  cells,
  globalMaxE,
}: {
  model: string;
  cpuValues: number[];
  ramValues: number[];
  cells: Map<string, { e: number; tok: number; cpu: number; mem: number }>;
  globalMaxE: number;
}) {
  const r = (v: number) => Math.round(v * 10) / 10;
  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-collapse w-full">
        <thead>
          <tr>
            <th className="p-1.5 text-left text-zinc-400 font-medium whitespace-nowrap w-20">
              RAM ↓ / CPU →
            </th>
            {cpuValues.map((cpu) => (
              <th
                key={cpu}
                className="p-1.5 text-center text-zinc-500 font-medium whitespace-nowrap min-w-[76px]"
              >
                {cpu}c
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ramValues.map((ram) => (
            <tr key={ram}>
              <td className="p-1.5 text-zinc-600 font-medium whitespace-nowrap">
                {ram} GB
              </td>
              {cpuValues.map((cpu) => {
                const key = `${cpu}_${ram}`;
                const cell = cells.get(key);
                if (!cell) {
                  return (
                    <td key={cpu} className="p-1 text-center">
                      <div className="rounded px-1.5 py-2.5 text-zinc-300 bg-zinc-100 text-[11px]">
                        —
                      </div>
                    </td>
                  );
                }
                const norm =
                  globalMaxE > 0 ? Math.min(1, cell.e / globalMaxE) : 0;
                const isRef = norm >= 0.999;
                return (
                  <td key={cpu} className="p-1 text-center">
                    <div
                      title={[
                        `${model} · ${cpu} cores, ${ram} GB RAM`,
                        `E_norm: ${norm.toFixed(3)}${isRef ? " ★ еталон" : ""}`,
                        `E: ${cell.e.toFixed(2)}`,
                        `Tok/s: ${r(cell.tok)}`,
                        `CPU: ${r(cell.cpu)}%`,
                        `Mem: ${r(cell.mem)}%`,
                      ].join("\n")}
                      className="rounded px-1.5 py-2.5 font-mono font-semibold text-white text-[11px] cursor-default select-none"
                      style={{
                        backgroundColor: scoreColor(Math.round(norm * 100)),
                      }}
                    >
                      {norm.toFixed(3)}
                      {isRef && (
                        <span className="block text-[9px] leading-none mt-0.5 opacity-90">
                          ★
                        </span>
                      )}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EfficHeatmapWidget({
  usableFiles,
  summaryCache,
}: {
  usableFiles: BenchmarkResultFile[];
  summaryCache: Record<string, BenchmarkSummary>;
}) {
  // All base model names that have at least one loaded summary with hw info.
  const baseModels = useMemo(() => {
    const s = new Set<string>();
    usableFiles.forEach((f) => {
      if (f.model && summaryCache[f.filename] && f.cpu_cores != null && f.ram_gb != null)
        s.add(f.model);
    });
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [usableFiles, summaryCache]);

  // "" = show all models; any other string = filter to that model.
  const [modelFilter, setModelFilter] = useState<string>("");

  // Global maximum E across entire Ω — shared colour scale.
  const globalMaxE = useMemo(() => {
    let max = 0;
    usableFiles.forEach((f) => {
      if (f.cpu_cores == null || f.ram_gb == null) return;
      const s = summaryCache[f.filename]?.summary;
      if (!s) return;
      const tok = s.avg_tokens_per_second || 0;
      const cpu = s.avg_cpu_percent || 0;
      const mem = s.avg_memory_percent || 0;
      const denom = Math.sqrt((cpu / 100) * (mem / 100));
      const e = denom > 0 ? tok / denom : 0;
      if (e > max) max = e;
    });
    return max;
  }, [usableFiles, summaryCache]);

  // Pre-build cell data for every base model once.
  const allModelData = useMemo(
    () =>
      baseModels.map((m) => ({
        model: m,
        ...buildModelCells(m, usableFiles, summaryCache),
      })),
    [baseModels, usableFiles, summaryCache],
  );

  const visibleData = modelFilter
    ? allModelData.filter((d) => d.model === modelFilter)
    : allModelData;

  if (baseModels.length === 0) {
    return (
      <WidgetCard
        title="E_norm heatmap"
        hint="CPU cores × RAM GB"
        fullWidth
      >
        <p className="text-sm text-zinc-400 py-6 text-center">
          No benchmark data available with cpu_cores + ram_gb fields.
        </p>
      </WidgetCard>
    );
  }

  return (
    <WidgetCard
      title="E_norm heatmap"
      hint="E_norm = E(m,p,c) / max E  ·  E = tok/s / sqrt(cpu% * mem%)  ·  1.000 = reference"
      fullWidth
    >
      {/* Controls row */}
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <label className="flex items-center gap-2 text-xs text-zinc-600">
          <span className="text-zinc-500">Model:</span>
          <select
            value={modelFilter}
            onChange={(e) => setModelFilter(e.target.value)}
            className="border border-zinc-300 rounded-md px-2 py-1 text-xs bg-white text-zinc-700 hover:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
          >
            <option value="">All models ({baseModels.length})</option>
            {baseModels.map((m) => (
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
            >
              reset
            </button>
          )}
        </label>
        <span className="text-[11px] text-zinc-400">
          max_Ω(E) = {globalMaxE > 0 ? globalMaxE.toFixed(2) : "—"}
        </span>
      </div>

      {/* One grid per model */}
      <div
        className={
          visibleData.length === 1
            ? ""
            : "grid grid-cols-1 xl:grid-cols-2 gap-6"
        }
      >
        {visibleData.map(({ model, cpuValues, ramValues, cells }) =>
          cpuValues.length === 0 ? null : (
            <div key={model}>
              {visibleData.length > 1 && (
                <p className="text-xs font-semibold text-zinc-700 mb-2 truncate">
                  {model}
                </p>
              )}
              <ModelEGrid
                model={model}
                cpuValues={cpuValues}
                ramValues={ramValues}
                cells={cells}
                globalMaxE={globalMaxE}
              />
            </div>
          ),
        )}
      </div>

      {/* Colour scale legend */}
      <div className="flex items-center gap-2 mt-4 text-[10px] text-zinc-400">
        <span>0 (worst)</span>
        <div
          className="h-2 flex-1 rounded"
          style={{
            background:
              "linear-gradient(to right, hsl(0,65%,48%), hsl(60,65%,48%), hsl(120,65%,48%))",
          }}
        />
        <span>1 (reference)</span>
      </div>
    </WidgetCard>
  );
}

// ─── 11. Resource impact line charts (RAM & CPU) ──────────────────────────────

function buildImpactData(
  usableFiles: BenchmarkResultFile[],
  summaryCache: Record<string, BenchmarkSummary>,
  selectedModels: Set<string>,
  axis: "ram" | "cpu",
): { models: string[]; xValues: number[]; series: Map<string, Map<number, number>> } {
  const series = new Map<string, Map<number, { sum: number; count: number }>>();

  usableFiles.forEach((f) => {
    if (!selectedModels.has(variantId(f))) return;
    const s = summaryCache[f.filename]?.summary;
    if (!s) return;
    const tps = s.avg_tokens_per_second || 0;
    if (tps <= 0) return;

    const xVal = axis === "ram" ? f.ram_gb : f.cpu_cores;
    if (xVal == null) return;
    const x = Number(xVal);

    const model = f.model || variantId(f);
    if (!series.has(model)) series.set(model, new Map());
    const modelMap = series.get(model)!;
    const prev = modelMap.get(x) ?? { sum: 0, count: 0 };
    modelMap.set(x, { sum: prev.sum + tps, count: prev.count + 1 });
  });

  const xSet = new Set<number>();
  const avgSeries = new Map<string, Map<number, number>>();
  series.forEach((modelMap, model) => {
    const avg = new Map<number, number>();
    modelMap.forEach((v, x) => {
      avg.set(x, v.sum / v.count);
      xSet.add(x);
    });
    avgSeries.set(model, avg);
  });

  return {
    models: Array.from(avgSeries.keys()).sort(),
    xValues: Array.from(xSet).sort((a, b) => a - b),
    series: avgSeries,
  };
}

function ResourceImpactWidget({
  usableFiles,
  summaryCache,
  selectedModels,
  axis,
  colorMap,
}: {
  usableFiles: BenchmarkResultFile[];
  summaryCache: Record<string, BenchmarkSummary>;
  selectedModels: Set<string>;
  axis: "ram" | "cpu";
  colorMap: Map<string, string>;
}) {
  const { models, xValues, series } = useMemo(
    () => buildImpactData(usableFiles, summaryCache, selectedModels, axis),
    [usableFiles, summaryCache, selectedModels, axis],
  );

  const xLabel = axis === "ram" ? "RAM (GB)" : "CPU cores";
  const title = axis === "ram" ? "RAM impact on throughput" : "CPU impact on throughput";
  const hint = axis === "ram"
    ? "Average tok/s at each RAM level per model"
    : "Average tok/s at each CPU core count per model";

  if (models.length === 0 || xValues.length < 2) {
    return (
      <WidgetCard title={title} hint={hint}>
        <p className="text-sm text-zinc-400 py-6 text-center">
          Not enough data (need at least 2 distinct {xLabel} values).
        </p>
      </WidgetCard>
    );
  }

  const chartData = xValues.map((x) => {
    const point: Record<string, number> = { x };
    models.forEach((m) => {
      const val = series.get(m)?.get(x);
      if (val != null) point[m] = Math.round(val * 100) / 100;
    });
    return point;
  });

  return (
    <WidgetCard title={title} hint={hint}>
      <div style={{ height: Math.max(260, 260) }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
            <XAxis
              dataKey="x"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={{ fontSize: 11, fill: "#71717a" }}
              tickLine={false}
              axisLine={false}
              label={{ value: xLabel, position: "insideBottomRight", offset: -4, fontSize: 11, fill: "#a1a1aa" }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#71717a" }}
              tickLine={false}
              axisLine={false}
              label={{ value: "tok/s", angle: -90, position: "insideLeft", offset: 10, fontSize: 11, fill: "#a1a1aa" }}
            />
            <Tooltip
              contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid #e4e4e7" }}
              labelFormatter={(v) => `${xLabel}: ${v}`}
            />
            <Legend
              wrapperStyle={{ fontSize: 11 }}
              iconType="circle"
              iconSize={8}
            />
            {models.map((m, i) => (
              <Line
                key={m}
                type="monotone"
                dataKey={m}
                name={m.length > 20 ? `${m.slice(0, 19)}...` : m}
                stroke={colorMap.get(m) || paletteColor(i)}
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </WidgetCard>
  );
}

// ─── 12. Horizontal bar chart (per metric) ────────────────────────────────────

function BarWidget({
  metric,
  aggregates,
  colorMap,
  leaderboardMode,
}: {
  metric: BarMetric;
  aggregates: ModelAggregate[];
  colorMap: Map<string, string>;
  leaderboardMode?: boolean;
}) {
  const data = aggregates.map((a, i) => {
    const base = a.model.length > 18 ? `${a.model.slice(0, 17)}…` : a.model;
    return {
      model: a.model,
      label: leaderboardMode ? `#${i + 1} ${base}` : base,
      value: metric.getValue(a),
      color: colorMap.get(a.model) || "#18181b",
    };
  });
  const barH = Math.max(180, data.length * 44 + 32);

  return (
    <WidgetCard
      title={metric.label}
      hint={
        leaderboardMode
          ? `Ranked best → worst (${metric.hint.toLowerCase()})`
          : metric.hint
      }
    >
      <div style={{ height: barH }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 2, right: 56, bottom: 2, left: 4 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              horizontal={false}
              stroke="#e4e4e7"
            />
            <XAxis
              type="number"
              tick={{ fontSize: 11, fill: "#71717a" }}
              tickLine={false}
              axisLine={false}
              unit={metric.unit}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={130}
              tick={{ fontSize: 11, fill: "#71717a" }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              content={(props) => (
                <TT
                  active={props.active}
                  payload={props.payload?.map((p) => ({
                    name: String(
                      props.payload?.[0]?.payload?.model ?? props.label ?? "",
                    ),
                    value: Number(p.value),
                    color: p.fill as string,
                  }))}
                  unit={metric.unit}
                />
              )}
            />
            <Bar
              dataKey="value"
              radius={[0, 4, 4, 0]}
              maxBarSize={30}
              label={{
                position: "right",
                fontSize: 10,
                fill: "#52525b",
                formatter: (v: number) => (v === 0 ? "" : `${v}${metric.unit}`),
              }}
            >
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </WidgetCard>
  );
}

// ─── Widget card wrapper ──────────────────────────────────────────────────────

function WidgetCard({
  title,
  hint,
  children,
  fullWidth,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
  fullWidth?: boolean;
}) {
  return (
    <div
      className={`bg-white border border-zinc-200 rounded-lg p-5 shadow-sm${fullWidth ? " xl:col-span-2" : ""}`}
    >
      <div className="flex items-baseline justify-between mb-3">
        <h4 className="font-medium text-zinc-800">{title}</h4>
        {hint && (
          <span className="text-[11px] text-zinc-400 ml-3 text-right">
            {hint}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function ModelDashboard() {
  const [files, setFiles] = useState<BenchmarkResultFile[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [errorList, setErrorList] = useState<string | null>(null);
  const [summaryCache, setSummaryCache] = useState<
    Record<string, BenchmarkSummary>
  >({});
  const [loadingSet, setLoadingSet] = useState<Set<string>>(new Set());
  const [selectedModels, setSelectedModels] = useState<Set<string>>(new Set());
  const [selectedWidgets, setSelectedWidgets] = useState<Set<string>>(
    new Set(ALL_WIDGETS.map((w) => w.id)),
  );
  // Filter the pill list by base model name (e.g. "qwen:1.5b") so the user
  // can focus the dashboard on one model's runs across its different
  // RAM/CPU/tech/platform configs. Empty == show all models.
  const [modelFilter, setModelFilter] = useState<string>("");
  const [cpuFilter, setCpuFilter] = useState<string>("");
  const [ramFilter, setRamFilter] = useState<string>("");

  // Each unique combination of model + RAM + CPU + tech + platform is shown
  // as a separate item ("variant"). `model` here holds the human-readable
  // variant label so existing widgets keep working unchanged. We also keep
  // the base `baseModel` name on each entry so the model-name filter can
  // narrow the pills to a single model's variants.
  // Only files that actually produced data should drive the dashboard's
  // graphs / pill list — infeasible runs and zero-prompt placeholders are
  // excluded so empty bars no longer pollute the charts.
  const usableFiles = useMemo(
    () => files.filter(hasAnyResult),
    [files],
  );

  const allModels = useMemo(() => {
    const map = new Map<
      string,
      { label: string; count: number; baseModel: string; cpu_cores: number | null; ram_gb: number | null }
    >();
    usableFiles.forEach((f) => {
      if (!f.model) return;
      const id = variantId(f);
      const cur = map.get(id);
      if (cur) cur.count += 1;
      else
        map.set(id, {
          label: variantLabel(f),
          count: 1,
          baseModel: f.model,
          cpu_cores: f.cpu_cores ?? null,
          ram_gb: f.ram_gb ?? null,
        });
    });
    return Array.from(map.entries())
      .map(([id, v]) => ({
        model: id,
        label: v.label,
        count: v.count,
        baseModel: v.baseModel,
        cpu_cores: v.cpu_cores,
        ram_gb: v.ram_gb,
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [usableFiles]);

  // Unique sorted list of base model names — populates the filter <select>.
  const baseModelOptions = useMemo(() => {
    const s = new Set<string>();
    allModels.forEach((m) => s.add(m.baseModel));
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [allModels]);

  const cpuOptions = useMemo(() => {
    const s = new Set<number>();
    allModels.forEach((m) => { if (m.cpu_cores != null) s.add(m.cpu_cores); });
    return Array.from(s).sort((a, b) => a - b);
  }, [allModels]);

  const ramOptions = useMemo(() => {
    const s = new Set<number>();
    allModels.forEach((m) => { if (m.ram_gb != null) s.add(m.ram_gb); });
    return Array.from(s).sort((a, b) => a - b);
  }, [allModels]);

  // Variants visible after applying all filters.
  const visibleModels = useMemo(() => {
    let result = allModels;
    if (modelFilter) result = result.filter((m) => m.baseModel === modelFilter);
    if (cpuFilter) result = result.filter((m) => m.cpu_cores != null && String(m.cpu_cores) === cpuFilter);
    if (ramFilter) result = result.filter((m) => m.ram_gb != null && String(m.ram_gb) === ramFilter);
    return result;
  }, [allModels, modelFilter, cpuFilter, ramFilter]);

  // When any filter changes, narrow the selection to the visible variants.
  // If all filters are cleared, restore "select all".
  useEffect(() => {
    if (!modelFilter && !cpuFilter && !ramFilter) {
      setSelectedModels(new Set(allModels.map((m) => m.model)));
      return;
    }
    setSelectedModels(new Set(visibleModels.map((m) => m.model)));
  }, [modelFilter, cpuFilter, ramFilter, allModels, visibleModels]);

  // Display label lookup keyed by variant id (== ModelAggregate.model).
  const labelMap = useMemo(() => {
    const m = new Map<string, string>();
    allModels.forEach((v) => m.set(v.model, v.label));
    return m;
  }, [allModels]);

  // Color map keyed by both variant id AND label so callers using either
  // (pill button uses id, widgets use label) all resolve correctly.
  const colorMap = useMemo(() => {
    const m = new Map<string, string>();
    allModels.forEach(({ model, label }, idx) => {
      const c = paletteColor(idx);
      m.set(model, c);
      m.set(label, c);
    });
    return m;
  }, [allModels]);

  useEffect(() => {
    setLoadingList(true);
    api
      .getBenchmarkResults()
      .then((r) => {
        setFiles(r);
        setErrorList(null);
      })
      .catch((e) => setErrorList(e.message || "Failed to load results"))
      .finally(() => setLoadingList(false));
  }, []);

  useEffect(() => {
    if (allModels.length > 0 && selectedModels.size === 0)
      setSelectedModels(new Set(allModels.map((m) => m.model)));
  }, [allModels]); // eslint-disable-line react-hooks/exhaustive-deps

  // When the model-name filter changes, narrow the current selection to
  // only the variants belonging to the chosen model so the charts react
  // immediately. If the filter is cleared, restore the "select all"
  // default to keep behavior consistent with the initial load.
  useEffect(() => {
    selectedModels.forEach((vid) => {
      // Only fetch summaries for files that have actual results — skip
      // infeasible / empty placeholders so we don't waste roundtrips.
      const missing = usableFiles.filter(
        (f) => variantId(f) === vid && !summaryCache[f.filename],
      );
      if (!missing.length) return;
      setLoadingSet((p) => new Set(p).add(vid));
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
            loaded.forEach((e) => {
              if (e) next[e[0]] = e[1];
            });
            return next;
          });
        })
        .finally(() => {
          setLoadingSet((p) => {
            const n = new Set(p);
            n.delete(vid);
            return n;
          });
        });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModels, usableFiles]);

  const aggregates = useMemo(
    () =>
      Array.from(selectedModels)
        .map((vid) => {
          // Restrict to files that have actual data (skip infeasible /
          // empty runs) AND to summaries that, once loaded, still contain
          // at least one executed prompt or test script.
          const summaries = usableFiles
            .filter((f) => variantId(f) === vid)
            .map((f) => summaryCache[f.filename])
            .filter((s): s is BenchmarkSummary => summaryHasAnyResult(s));
          if (!summaries.length) return null;
          // Use the human-readable variant label as the aggregate's `model`,
          // so that all charts/widgets render the variant correctly.
          const label = labelMap.get(vid) ?? vid;
          return aggregateModel(label, summaries);
        })
        .filter((a): a is ModelAggregate => a !== null),
    [selectedModels, summaryCache, usableFiles, labelMap],
  );

  const toggleModel = (model: string) =>
    setSelectedModels((p) => {
      const n = new Set(p);
      n.has(model) ? n.delete(model) : n.add(model);
      return n;
    });

  const toggleWidget = (id: string) =>
    setSelectedWidgets((p) => {
      const n = new Set(p);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const toggleGroup = (group: "analysis" | "metrics") => {
    const ids = ALL_WIDGETS.filter((w) => w.group === group).map((w) => w.id);
    const allOn = ids.every((id) => selectedWidgets.has(id));
    setSelectedWidgets((p) => {
      const n = new Set(p);
      ids.forEach((id) => (allOn ? n.delete(id) : n.add(id)));
      return n;
    });
  };

  const isLoading = loadingList || loadingSet.size > 0;
  const noData = aggregates.length === 0 && !isLoading;

  // Leaderboard mode — when ON, charts are reordered so the best-ranked
  // models appear first. Without this, `aggregatesByComposite` was just an
  // alias of `aggregates`, `leaderboardScores` was never passed to
  // `RadarWidget`, and `BarWidget` got the unsorted list with no
  // `leaderboardMode` flag, leaving the ranked titles / `#<rank>` labels as
  // dead code.
  const [leaderboardMode, setLeaderboardMode] = useState(false);

  const compositeScores = useMemo(
    () => computeCompositeScores(aggregates),
    [aggregates],
  );

  const aggregatesByComposite = useMemo(
    () => (leaderboardMode ? sortByComposite(aggregates) : aggregates),
    [aggregates, leaderboardMode],
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-zinc-200 rounded-lg p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <LayoutDashboard className="w-5 h-5 text-zinc-700" />
              <h2 className="text-xl font-semibold text-zinc-800">
                Analytics Dashboard
              </h2>
              {isLoading && (
                <Loader2 className="w-4 h-4 animate-spin text-zinc-400 ml-1" />
              )}
            </div>
            <p className="text-sm text-zinc-500">
              Visual overview of benchmark metrics — radar, scatter, heatmap,
              composed charts &amp; more.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setLeaderboardMode((v) => !v)}
            title={
              leaderboardMode
                ? "Charts ranked best → worst by composite score (lower-is-better metrics inverted). Click to switch back."
                : "Click to rank charts from best to worst by a composite score across all metrics."
            }
            className={`flex items-center gap-2 text-sm font-medium px-3 py-1.5 rounded-md border transition-colors ${
              leaderboardMode
                ? "bg-amber-100 border-amber-300 text-amber-800 hover:bg-amber-200"
                : "bg-white border-zinc-300 text-zinc-700 hover:bg-zinc-50"
            }`}
          >
            <Trophy className="w-4 h-4" />
            {leaderboardMode ? "Leaderboard: ON" : "Leaderboard"}
          </button>
        </div>
      </div>

      {errorList && (
        <div className="bg-red-50 border border-red-100 rounded-lg p-4 text-sm text-red-700">
          {errorList}
        </div>
      )}



      {/* Filters row */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-6">
        {/* Model pills */}
        <div className="bg-white border border-zinc-200 rounded-lg p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
            <div className="flex items-center gap-3 flex-wrap">
              <h3 className="font-medium text-zinc-800">Models</h3>
              {/* Filter by base model name so the user can pick a single
                  model and inspect only its different RAM/CPU/tech configs. */}
              <label className="inline-flex items-center gap-2 text-xs text-zinc-600">
                <span className="text-zinc-500">Model:</span>
                <select
                  value={modelFilter}
                  onChange={(e) => setModelFilter(e.target.value)}
                  className="border border-zinc-300 rounded-md px-2 py-1 text-xs bg-white text-zinc-700 hover:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
                >
                  <option value="">All ({baseModelOptions.length})</option>
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
                    ×
                  </button>
                )}
              </label>
              <label className="inline-flex items-center gap-2 text-xs text-zinc-600">
                <span className="text-zinc-500">CPU:</span>
                <select
                  value={cpuFilter}
                  onChange={(e) => setCpuFilter(e.target.value)}
                  className="border border-zinc-300 rounded-md px-2 py-1 text-xs bg-white text-zinc-700 hover:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
                >
                  <option value="">All</option>
                  {cpuOptions.map((c) => (
                    <option key={c} value={String(c)}>
                      {c} cores
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
                    ×
                  </button>
                )}
              </label>
              <label className="inline-flex items-center gap-2 text-xs text-zinc-600">
                <span className="text-zinc-500">RAM:</span>
                <select
                  value={ramFilter}
                  onChange={(e) => setRamFilter(e.target.value)}
                  className="border border-zinc-300 rounded-md px-2 py-1 text-xs bg-white text-zinc-700 hover:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
                >
                  <option value="">All</option>
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
                    ×
                  </button>
                )}
              </label>
            </div>
            <button
              onClick={() =>
                setSelectedModels(
                  selectedModels.size === visibleModels.length
                    ? new Set()
                    : new Set(visibleModels.map((m) => m.model)),
                )
              }
              className="text-xs text-zinc-500 hover:text-zinc-800 underline"
            >
              {selectedModels.size === visibleModels.length
                ? "Deselect All"
                : "Select All"}
            </button>
          </div>
          {loadingList ? (
            <div className="flex items-center gap-2 text-sm text-zinc-400">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </div>
          ) : visibleModels.length === 0 ? (
            <p className="text-sm text-zinc-400">
              {allModels.length === 0
                ? "No benchmark results found — run some benchmarks first."
                : "No variants match the selected filters."}
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {visibleModels.map(({ model, label, count }) => {
                const active = selectedModels.has(model);
                const color = colorMap.get(model) || "#18181b";
                return (
                  <button
                    key={model}
                    type="button"
                    onClick={() => toggleModel(model)}
                    title={label}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm transition-colors ${
                      active
                        ? "border-zinc-800 bg-zinc-800 text-white"
                        : "border-zinc-200 bg-zinc-50 text-zinc-600 hover:border-zinc-400"
                    }`}
                  >
                    <span
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: color }}
                    />
                    {label}
                    <span className="opacity-60 text-xs">({count})</span>
                  </button>
                );
              })}
            </div>
          )}
          <p className="text-xs text-zinc-400 mt-3">
            {selectedModels.size} of {visibleModels.length} selected
            {(modelFilter || cpuFilter || ramFilter) && (
              <span className="ml-2 text-zinc-500">
                (filtered
                {modelFilter && <> — model: <strong>{modelFilter}</strong></>}
                {cpuFilter && <> — CPU: <strong>{cpuFilter} cores</strong></>}
                {ramFilter && <> — RAM: <strong>{ramFilter} GB</strong></>}
                )
              </span>
            )}
          </p>
        </div>

        {/* Widget toggles */}
        <div className="bg-white border border-zinc-200 rounded-lg p-5 shadow-sm min-w-[260px]">
          <h3 className="font-medium text-zinc-800 mb-3">Visible charts</h3>
          <div className="space-y-3">
            {/* Analysis group */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
                  Analysis
                </span>
                <button
                  onClick={() => toggleGroup("analysis")}
                  className="text-[10px] text-zinc-400 hover:text-zinc-700 underline"
                >
                  {ANALYSIS_WIDGETS.every((w) => selectedWidgets.has(w.id))
                    ? "off"
                    : "on"}
                </button>
              </div>
              {ANALYSIS_WIDGETS.map((w) => (
                <label
                  key={w.id}
                  className="flex items-center gap-2 text-sm cursor-pointer py-1 hover:bg-zinc-50 rounded px-1"
                >
                  <Checkbox
                    checked={selectedWidgets.has(w.id)}
                    onCheckedChange={() => toggleWidget(w.id)}
                  />
                  <span className="text-zinc-700">{w.label}</span>
                </label>
              ))}
            </div>
            {/* Metrics group */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
                  Metric bars
                </span>
                <button
                  onClick={() => toggleGroup("metrics")}
                  className="text-[10px] text-zinc-400 hover:text-zinc-700 underline"
                >
                  {BAR_WIDGETS.every((w) => selectedWidgets.has(w.id))
                    ? "off"
                    : "on"}
                </button>
              </div>
              {BAR_WIDGETS.map((w) => (
                <label
                  key={w.id}
                  className="flex items-center gap-2 text-sm cursor-pointer py-1 hover:bg-zinc-50 rounded px-1"
                >
                  <Checkbox
                    checked={selectedWidgets.has(w.id)}
                    onCheckedChange={() => toggleWidget(w.id)}
                  />
                  <span className="text-zinc-700">{w.label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Chart grid */}
      {noData ? (
        <div className="bg-white border border-zinc-200 rounded-lg p-16 text-center text-zinc-400 shadow-sm">
          {selectedModels.size === 0
            ? "Select at least one model above to view charts."
            : "Summaries still loading — or run some benchmarks first."}
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {/* Analysis widgets — use composite-ranked order in leaderboard mode */}
          {selectedWidgets.has("scatter") && aggregatesByComposite.length >= 1 && (
            <ScatterWidget
              aggregates={aggregatesByComposite}
              colorMap={colorMap}
            />
          )}
          {selectedWidgets.has("reliability") &&
            aggregatesByComposite.length >= 1 && (
              <ReliabilityWidget
                aggregates={aggregatesByComposite}
                colorMap={colorMap}
              />
            )}
          {selectedWidgets.has("composed") &&
            aggregatesByComposite.length >= 1 && (
              <ComposedWidget
                aggregates={aggregatesByComposite}
                colorMap={colorMap}
              />
            )}
          {selectedWidgets.has("radialScore") &&
            aggregatesByComposite.length >= 1 && (
              <RadialScoreWidget
                aggregates={aggregatesByComposite}
                colorMap={colorMap}
              />
            )}
          {selectedWidgets.has("throughputByDeployment") &&
            usableFiles.length >= 1 && (
              <ThroughputByDeploymentWidget
                usableFiles={usableFiles}
                summaryCache={summaryCache}
                selectedModels={selectedModels}
              />
            )}
          {/* Heatmap — full width */}
          {selectedWidgets.has("heatmap") &&
            aggregatesByComposite.length >= 1 && (
              <div className="xl:col-span-2">
                <HeatmapWidget aggregates={aggregatesByComposite} />
              </div>
            )}
          {/* E_norm heatmap — full width */}
          {selectedWidgets.has("enormHeatmap") && usableFiles.length >= 1 && (
            <div className="xl:col-span-2">
              <EfficHeatmapWidget
                usableFiles={usableFiles}
                summaryCache={summaryCache}
              />
            </div>
          )}
          {/* OOM heatmap — full width */}
          {selectedWidgets.has("oomHeatmap") && usableFiles.length >= 1 && (
            <div className="xl:col-span-2">
              <OomHeatmapWidget
                usableFiles={usableFiles}
                summaryCache={summaryCache}
                selectedModels={selectedModels}
              />
            </div>
          )}
          {/* TPS–TCO Pareto scatter — full width */}
          {selectedWidgets.has("tpsTcoPareto") && usableFiles.length >= 1 && (
            <div className="xl:col-span-2">
              <TpsTcoParetoWidget
                usableFiles={usableFiles}
                summaryCache={summaryCache}
                selectedModels={selectedModels}
              />
            </div>
          )}
          {/* RAM impact */}
          {selectedWidgets.has("ramImpact") && usableFiles.length >= 1 && (
              <ResourceImpactWidget
                usableFiles={usableFiles}
                summaryCache={summaryCache}
                selectedModels={selectedModels}
                axis="ram"
                colorMap={colorMap}
              />
          )}
          {/* CPU impact */}
          {selectedWidgets.has("cpuImpact") && usableFiles.length >= 1 && (
              <ResourceImpactWidget
                usableFiles={usableFiles}
                summaryCache={summaryCache}
                selectedModels={selectedModels}
                axis="cpu"
                colorMap={colorMap}
              />
          )}
          {/* Per-metric bar charts — in leaderboard mode each is sorted by its own metric */}
          {BAR_METRICS.map((metric) =>
            selectedWidgets.has(`bar_${metric.id}`) &&
            aggregates.length >= 1 ? (
              <BarWidget
                key={metric.id}
                metric={metric}
                aggregates={
                  leaderboardMode ? sortByMetric(aggregates, metric) : aggregates
                }
                colorMap={colorMap}
                leaderboardMode={leaderboardMode}
              />
            ) : null,
          )}
        </div>
      )}
    </div>
  );
}
