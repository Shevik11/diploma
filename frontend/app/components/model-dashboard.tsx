import { useEffect, useMemo, useState } from "react";
import { Loader2, LayoutDashboard } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ScatterChart,
  Scatter,
  ZAxis,
  ComposedChart,
  Line,
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
  variantId,
  variantLabel,
} from "@/app/services/api";

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
  // Raw-derived axes used by the leaderboard composite. Default to 0
  // when not computed by the caller so all consumers can read them safely.
  p95LatencyMs: number;
  peakMemoryMb: number;
  errorRate: number;
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
  return {
    model,
    fileCount: summaries.length,
    summary: aggSummary,
    testPassRate: total > 0 ? passed / total : 0,
    // Defaults — top-models recomputes these from raw per-prompt items.
    p95LatencyMs: 0,
    peakMemoryMb: 0,
    errorRate: 0,
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

// ─── Widget registry ──────────────────────────────────────────────────────────

interface BarMetric {
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
    id: "radar",
    label: "Radar overview",
    description: "Multi-metric fingerprint per model",
    group: "analysis",
  },
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

// ─── 1. Radar chart ───────────────────────────────────────────────────────────

const RADAR_AXES = [
  {
    key: "avg_tokens_per_second",
    label: "Tok/s",
    higherBetter: true,
    getValue: (a: ModelAggregate) => a.summary.avg_tokens_per_second || 0,
  },
  {
    key: "avg_latency_ms",
    label: "Latency↓",
    higherBetter: false,
    getValue: (a: ModelAggregate) => a.summary.avg_latency_ms || 0,
  },
  {
    key: "avg_first_token_ms",
    label: "TTFT↓",
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
    label: "CPU↓",
    higherBetter: false,
    getValue: (a: ModelAggregate) => a.summary.avg_cpu_percent || 0,
  },
  {
    key: "avg_memory_percent",
    label: "Memory↓",
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

function RadarWidget({
  aggregates,
  colorMap,
}: {
  aggregates: ModelAggregate[];
  colorMap: Map<string, string>;
}) {
  // Normalize each axis across all aggregates
  const radarData = RADAR_AXES.map((axis) => {
    const raw = aggregates.map((a) => axis.getValue(a));
    const scores = normalizeValues(raw, axis.higherBetter);
    const row: Record<string, number | string> = { metric: axis.label };
    aggregates.forEach((a, i) => {
      row[a.model] = scores[i];
    });
    return row;
  });

  return (
    <WidgetCard
      title="Radar overview"
      hint="All metrics normalized 0–100 · ↓ = lower is better"
    >
      <ResponsiveContainer width="100%" height={320}>
        <RadarChart
          data={radarData}
          margin={{ top: 10, right: 30, bottom: 10, left: 30 }}
        >
          <PolarGrid stroke="#e4e4e7" />
          <PolarAngleAxis
            dataKey="metric"
            tick={{ fontSize: 11, fill: "#71717a" }}
          />
          <PolarRadiusAxis
            angle={30}
            domain={[0, 100]}
            tick={{ fontSize: 9, fill: "#a1a1aa" }}
          />
          {aggregates.map((a) => (
            <Radar
              key={a.model}
              name={a.model}
              dataKey={a.model}
              stroke={colorMap.get(a.model) || "#18181b"}
              fill={colorMap.get(a.model) || "#18181b"}
              fillOpacity={0.12}
              strokeWidth={2}
              dot={{ r: 3 }}
            />
          ))}
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 11, color: "#52525b" }}
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
                label={String(props.label ?? "")}
                unit=" pts"
              />
            )}
          />
        </RadarChart>
      </ResponsiveContainer>
    </WidgetCard>
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

// ─── 7. Horizontal bar chart (per metric) ─────────────────────────────────────

function BarWidget({
  metric,
  aggregates,
  colorMap,
}: {
  metric: BarMetric;
  aggregates: ModelAggregate[];
  colorMap: Map<string, string>;
}) {
  const data = aggregates.map((a) => ({
    model: a.model,
    label: a.model.length > 18 ? `${a.model.slice(0, 17)}…` : a.model,
    value: metric.getValue(a),
    color: colorMap.get(a.model) || "#18181b",
  }));
  const barH = Math.max(180, data.length * 44 + 32);

  return (
    <WidgetCard title={metric.label} hint={metric.hint}>
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

  // Each unique combination of model + RAM + CPU + tech + platform is shown
  // as a separate item ("variant"). `model` here holds the human-readable
  // variant label so existing widgets keep working unchanged. We also keep
  // the base `baseModel` name on each entry so the model-name filter can
  // narrow the pills to a single model's variants.
  const allModels = useMemo(() => {
    const map = new Map<
      string,
      { label: string; count: number; baseModel: string }
    >();
    files.forEach((f) => {
      if (!f.model) return;
      const id = variantId(f);
      const cur = map.get(id);
      if (cur) cur.count += 1;
      else
        map.set(id, {
          label: variantLabel(f),
          count: 1,
          baseModel: f.model,
        });
    });
    return Array.from(map.entries())
      .map(([id, v]) => ({
        model: id,
        label: v.label,
        count: v.count,
        baseModel: v.baseModel,
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [files]);

  // Unique sorted list of base model names — populates the filter <select>.
  const baseModelOptions = useMemo(() => {
    const s = new Set<string>();
    allModels.forEach((m) => s.add(m.baseModel));
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [allModels]);

  // Variants visible after applying the base-model filter. All pill-list,
  // Select-All, and counts use this filtered view so the dashboard only
  // shows the user-selected model when the filter is active.
  const visibleModels = useMemo(
    () =>
      modelFilter
        ? allModels.filter((m) => m.baseModel === modelFilter)
        : allModels,
    [allModels, modelFilter],
  );


  // Color map keyed by both variant id AND label so callers using either
  // (pill button uses id, widgets use label) all resolve correctly.
  const colorMap = useMemo(() => {
    const m = new Map<string, string>();
    allModels.forEach(({ model }, idx) => m.set(model, paletteColor(idx)));
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
    if (!modelFilter) {
      setSelectedModels(new Set(allModels.map((m) => m.model)));
      return;
    }
    setSelectedModels(new Set(visibleModels.map((m) => m.model)));
  }, [modelFilter, allModels, visibleModels]);

  useEffect(() => {
    selectedModels.forEach((model) => {
      const missing = files.filter(
        (f) => f.model === model && !summaryCache[f.filename],
      );
      if (!missing.length) return;
      setLoadingSet((p) => new Set(p).add(model));
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
            n.delete(model);
            return n;
          });
        });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedModels, files]);

  const aggregates = useMemo(
    () =>
      Array.from(selectedModels)
        .map((model) => {
          const summaries = files
            .filter((f) => f.model === model)
            .map((f) => summaryCache[f.filename])
            .filter((s): s is BenchmarkSummary => !!s);
          return summaries.length ? aggregateModel(model, summaries) : null;
        })
        .filter((a): a is ModelAggregate => a !== null),
    [selectedModels, summaryCache, files],
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-zinc-200 rounded-lg p-6 shadow-sm">
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
                <span className="text-zinc-500">Filter:</span>
                <select
                  value={modelFilter}
                  onChange={(e) => setModelFilter(e.target.value)}
                  className="border border-zinc-300 rounded-md px-2 py-1 text-xs bg-white text-zinc-700 hover:border-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-400"
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
                : `No variants for model "${modelFilter}".`}
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
            {modelFilter && (
              <span className="ml-2 text-zinc-500">
                (filtered to <strong>{modelFilter}</strong>)
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
          {/* Analysis widgets */}
          {selectedWidgets.has("radar") && aggregates.length >= 1 && (
            <RadarWidget aggregates={aggregates} colorMap={colorMap} />
          )}
          {selectedWidgets.has("scatter") && aggregates.length >= 1 && (
            <ScatterWidget aggregates={aggregates} colorMap={colorMap} />
          )}
          {selectedWidgets.has("reliability") && aggregates.length >= 1 && (
            <ReliabilityWidget aggregates={aggregates} colorMap={colorMap} />
          )}
          {selectedWidgets.has("composed") && aggregates.length >= 1 && (
            <ComposedWidget aggregates={aggregates} colorMap={colorMap} />
          )}
          {selectedWidgets.has("radialScore") && aggregates.length >= 1 && (
            <RadialScoreWidget aggregates={aggregates} colorMap={colorMap} />
          )}
          {/* Heatmap — full width */}
          {selectedWidgets.has("heatmap") && aggregates.length >= 1 && (
            <div className="xl:col-span-2">
              <HeatmapWidget aggregates={aggregates} />
            </div>
          )}
          {/* Per-metric bar charts */}
          {BAR_METRICS.map((metric) =>
            selectedWidgets.has(`bar_${metric.id}`) &&
            aggregates.length >= 1 ? (
              <BarWidget
                key={metric.id}
                metric={metric}
                aggregates={aggregates}
                colorMap={colorMap}
              />
            ) : null,
          )}
        </div>
      )}
    </div>
  );
}
