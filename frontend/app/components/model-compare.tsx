import { useEffect, useMemo, useState } from "react";
import { GitCompare, Plus, X } from "lucide-react";
import {
  api,
  BenchmarkResultFile,
  BenchmarkSummary,
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
    label: "Tokens / sec",
    better: "higher",
    unit: " tok/s",
    get: (s) => s.avg_tokens_per_second,
  },
  {
    key: "avg_latency_ms",
    label: "Latency",
    better: "lower",
    unit: " ms",
    get: (s) => s.avg_latency_ms,
  },
  {
    key: "avg_first_token_latency_ms",
    label: "First-token latency",
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
    label: "CPU usage",
    better: "lower",
    unit: "%",
    get: (s) => s.avg_cpu_percent,
  },
  {
    key: "avg_memory_percent",
    label: "Memory usage",
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
  return isBest ? "bg-green-100 text-green-900 font-bold" : "text-zinc-900";
}

function shortTimestamp(ts?: string): string {
  if (!ts) return "—";
  // Backend stores something like "20260501-072400"
  const m = ts.match(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$/);
  if (m) return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}`;
  return ts;
}

export function ModelCompare() {
  const [files, setFiles] = useState<BenchmarkResultFile[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [errorList, setErrorList] = useState<string | null>(null);

  // Each slot holds a filename of a benchmark run, or undefined.
  const [selectedFiles, setSelectedFiles] = useState<(string | undefined)[]>([
    undefined,
    undefined,
  ]);

  useEffect(() => {
    setLoadingList(true);
    api
      .getBenchmarkResults()
      .then((r) => {
        // newest first
        const sorted = [...r].sort((a, b) =>
          (b.timestamp || "").localeCompare(a.timestamp || ""),
        );
        setFiles(sorted);
        setErrorList(null);
      })
      .catch((e) =>
        setErrorList(e.message || "Failed to load benchmark results"),
      )
      .finally(() => setLoadingList(false));
  }, []);

  const fileByName = useMemo(() => {
    const m = new Map<string, BenchmarkResultFile>();
    files.forEach((f) => m.set(f.filename, f));
    return m;
  }, [files]);

  // Auto-pick distinct defaults when files arrive
  useEffect(() => {
    if (files.length === 0) return;
    setSelectedFiles((prev) => {
      const used = new Set(prev.filter((x): x is string => !!x));
      const next = prev.map((v) => {
        if (v !== undefined) return v;
        const candidate = files.find((f) => !used.has(f.filename));
        if (candidate) {
          used.add(candidate.filename);
          return candidate.filename;
        }
        return v;
      });
      return next;
    });
  }, [files]);

  const addSlot = () => setSelectedFiles((prev) => [...prev, undefined]);
  const removeSlot = (idx: number) =>
    setSelectedFiles((prev) => prev.filter((_, i) => i !== idx));
  const setSlot = (idx: number, value: string) =>
    setSelectedFiles((prev) => prev.map((v, i) => (i === idx ? value : v)));

  const n = selectedFiles.length;
  const allSlotsFilled =
    files.length > 0 &&
    selectedFiles.filter((x): x is string => !!x).length >= files.length;

  const gridStyle = {
    gridTemplateColumns: `minmax(220px,1.2fr) repeat(${n}, minmax(160px,1fr))`,
  };

  // The benchmarks the user picked (in slot order), with empty slots removed for table use.
  const slotFiles: (BenchmarkResultFile | null)[] = selectedFiles.map((fn) =>
    fn ? fileByName.get(fn) || null : null,
  );

  // Collect every test-script name across the picked runs
  const testRows = useMemo(() => {
    const names = new Set<string>();
    slotFiles.forEach((f) => {
      (f?.test_results || []).forEach((t) => names.add(t.name));
    });
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [slotFiles]);

  return (
    <div className="bg-white border-2 border-black rounded-lg p-8 shadow-[3px_3px_0px_0px_rgba(0,0,0,1)]">
      <div className="flex items-center gap-3 mb-2">
        <GitCompare className="w-6 h-6" />
        <h2 className="text-2xl font-bold">
          Compare Benchmark Runs
        </h2>
      </div>
      <p className="text-sm text-zinc-600 mb-8">
        Pick individual benchmark runs (model + CPU/RAM parameters) and compare their metrics side-by-side.
      </p>

      {errorList && (
        <div className="mb-6 bg-red-50 border-2 border-red-300 rounded-lg p-4 text-sm font-medium text-red-800">
          ⚠️ {errorList}
        </div>
      )}

      {/* Selectors */}
      <div className="flex flex-wrap gap-3 items-stretch mb-6">
        {selectedFiles.map((fn, idx) => {
          const takenByOthers = new Set(
            selectedFiles
              .filter((v, i) => i !== idx && !!v)
              .map((v) => v as string),
          );
          const availableFiles = files.filter(
            (f) => !takenByOthers.has(f.filename) || f.filename === fn,
          );
          const file = fn ? fileByName.get(fn) || null : null;
          return (
            <RunSlot
              key={idx}
              index={idx}
              file={file}
              files={availableFiles}
              value={fn}
              onChange={(v) => setSlot(idx, v)}
              onRemove={n > 2 ? () => removeSlot(idx) : undefined}
              loading={loadingList}
            />
          );
        })}
        <button
          type="button"
          onClick={addSlot}
          disabled={allSlotsFilled}
          className="min-w-[220px] max-w-[280px] flex flex-col items-center justify-center gap-2 px-4 py-8 rounded-lg border-2 border-dashed border-zinc-300 text-zinc-400 hover:border-black hover:text-black hover:bg-zinc-50 text-sm font-bold transition-all duration-100 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-zinc-300 disabled:hover:text-zinc-400 disabled:hover:bg-transparent mt-7"
          title={
            allSlotsFilled
              ? "All available runs are already selected"
              : "Add another run to compare"
          }
        >
          <Plus className="w-6 h-6" />
          <span>Add run</span>
        </button>
      </div>

      {/* Comparison table */}
      <div className="border-2 border-black rounded-lg overflow-hidden bg-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
        {/* Header */}
        <div
          className="grid bg-zinc-50 border-b-2 border-black"
          style={gridStyle}
        >
          <div className="p-4 border-r-2 border-black font-bold uppercase text-xs tracking-wider">
            Metric
          </div>
          {slotFiles.map((f, idx) => (
            <RunHeader
              key={idx}
              slotLabel={`Run ${String.fromCharCode(65 + idx)}`}
              file={f}
              fallback={selectedFiles[idx]}
              last={idx === n - 1}
            />
          ))}
        </div>

        {/* Run info */}
        <SectionHeader title="Run info" />
        <MetaRow
          label="Platform"
          values={slotFiles.map((f) => f?.platform)}
          gridStyle={gridStyle}
        />
        <MetaRow
          label="Technology"
          values={slotFiles.map((f) => f?.technology)}
          gridStyle={gridStyle}
        />
        <MetaRow
          label="CPU cores"
          values={slotFiles.map((f) =>
            f ? (f.cpu_cores != null ? String(f.cpu_cores) : "no limit") : undefined,
          )}
          gridStyle={gridStyle}
        />
        <MetaRow
          label="RAM (GB)"
          values={slotFiles.map((f) =>
            f ? (f.ram_gb != null ? String(f.ram_gb) : "no limit") : undefined,
          )}
          gridStyle={gridStyle}
        />
        <MetaRow
          label="Run timestamp"
          values={slotFiles.map((f) => shortTimestamp(f?.timestamp))}
          gridStyle={gridStyle}
        />

        {/* Summary metrics (per-run, no averaging across runs) */}
        <SectionHeader title="Benchmark metrics (per run)" />
        {SUMMARY_METRICS.map((row) => {
          const values = slotFiles.map((f) =>
            f && f.summary ? row.get(f.summary) : undefined,
          );
          const best = bestIndices(values, row.better);
          return (
            <div
              key={row.key}
              className="grid border-t border-zinc-200"
              style={gridStyle}
            >
              <div className="p-3 bg-zinc-50 text-sm font-medium text-zinc-700 border-r-2 border-black">
                {row.label}
              </div>
              {values.map((v, idx) => (
                <div
                  key={idx}
                  className={`p-3 text-sm font-mono ${idx < n - 1 ? "border-r-2 border-black" : ""} ${cellClass(best.has(idx))}`}
                >
                  {fmtNumber(v, row.unit)}
                </div>
              ))}
            </div>
          );
        })}

        {/* Test scripts (per-run status, no aggregation) */}
        {testRows.length > 0 && (
          <>
            <SectionHeader title="Test scripts (per run)" />
            {testRows.map((name) => {
              const entries = slotFiles.map(
                (f) => (f?.test_results || []).find((t) => t.name === name) || null,
              );
              return (
                <div
                  key={name}
                  className="grid border-t border-zinc-200"
                  style={gridStyle}
                >
                  <div className="p-3 bg-zinc-50 text-sm font-medium text-zinc-700 border-r-2 border-black">
                    {name}
                  </div>
                  {entries.map((t, idx) => (
                    <div
                      key={idx}
                      className={`p-3 text-sm ${idx < n - 1 ? "border-r-2 border-black" : ""}`}
                    >
                      {t ? (
                        <span
                          className={
                            t.status === "passed"
                              ? "text-green-700 font-bold"
                              : "text-red-700 font-bold"
                          }
                        >
                          {t.status}
                          {typeof t.duration === "number"
                            ? ` · ${t.duration.toFixed(1)}s`
                            : ""}
                        </span>
                      ) : (
                        <span className="text-zinc-400">—</span>
                      )}
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

function RunHeader({
  slotLabel,
  file,
  fallback,
  last,
}: {
  slotLabel: string;
  file: BenchmarkResultFile | null;
  fallback?: string;
  last?: boolean;
}) {
  return (
    <div className={`p-4 ${last ? "" : "border-r-2 border-black"}`}>
      <div className="text-[10px] uppercase font-bold tracking-wider text-zinc-500 mb-2">
        {slotLabel}
      </div>
      <div className="font-bold text-zinc-900 leading-tight mb-2">
        {file?.model || fallback || "—"}
      </div>
      {file && (
        <>
          <div className="flex gap-1.5 mb-2">
            <span className="px-2 py-0.5 bg-blue-50 border border-blue-200 rounded text-[10px] font-semibold text-blue-700">
              {file.cpu_cores != null ? `${file.cpu_cores}c` : "∞"}
            </span>
            <span className="px-2 py-0.5 bg-purple-50 border border-purple-200 rounded text-[10px] font-semibold text-purple-700">
              {file.ram_gb != null ? `${file.ram_gb}GB` : "∞"}
            </span>
          </div>
          <div className="text-[10px] text-zinc-400 truncate">
            {file.technology}
          </div>
        </>
      )}
    </div>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div className="grid grid-cols-1 border-t-2 border-black">
      <div className="p-3 px-4 bg-zinc-100 text-xs uppercase tracking-wider font-bold text-black">
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
    <div className="grid border-t border-zinc-200" style={gridStyle}>
      <div className="p-3 bg-zinc-50 text-sm font-medium text-zinc-700 border-r-2 border-black">
        {label}
      </div>
      {values.map((v, idx) => (
        <div
          key={idx}
          className={`p-3 text-sm text-zinc-900 font-mono ${idx < n - 1 ? "border-r-2 border-black" : ""}`}
        >
          {v || "—"}
        </div>
      ))}
    </div>
  );
}

function RunSlot({
  index,
  file,
  files,
  value,
  onChange,
  onRemove,
  loading,
}: {
  index: number;
  file: BenchmarkResultFile | null;
  files: BenchmarkResultFile[];
  value: string | undefined;
  onChange: (v: string) => void;
  onRemove?: () => void;
  loading: boolean;
}) {
  const slotLabel = `Run ${String.fromCharCode(65 + index)}`;
  return (
    <div className="flex flex-col gap-2 min-w-[240px] max-w-[320px]">
      <div className="flex items-center justify-between px-1">
        <label className="text-xs font-bold uppercase tracking-wider text-zinc-500">
          {slotLabel}
        </label>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            className="h-5 w-5 rounded text-zinc-400 hover:text-red-600 hover:bg-red-50 flex items-center justify-center transition-colors"
            title="Remove this run"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger
          className="bg-white border-2 border-black rounded-lg !h-auto min-h-[72px] p-0 text-left shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] hover:translate-x-[1px] hover:translate-y-[1px] transition-all duration-100 whitespace-normal"
          iconClassName="size-5 opacity-60"
        >
          <SelectValue asChild>
            {file ? (
                <div className="!flex !flex-col !items-start !gap-2 !line-clamp-none p-3 w-full">
                  <div className="font-bold text-sm text-zinc-900 leading-tight break-words">
                  {file.model}
                </div>
                  <div className="flex flex-wrap gap-2">
                  <div className="flex items-center gap-1.5 px-2 py-1 bg-blue-50 border border-blue-200 rounded text-xs font-semibold text-blue-700">
                    <span className="opacity-60">CPU</span>
                    <span>{file.cpu_cores != null ? `${file.cpu_cores}c` : "∞"}</span>
                  </div>
                  <div className="flex items-center gap-1.5 px-2 py-1 bg-purple-50 border border-purple-200 rounded text-xs font-semibold text-purple-700">
                    <span className="opacity-60">RAM</span>
                    <span>{file.ram_gb != null ? `${file.ram_gb}GB` : "∞"}</span>
                  </div>
                </div>
                <div className="text-[10px] text-zinc-400 font-mono">
                  {shortTimestamp(file.timestamp)}
                </div>
              </div>
            ) : (
              <div className="p-3 text-sm text-zinc-500">
                {loading ? "Loading…" : "Select a run…"}
              </div>
            )}
          </SelectValue>
        </SelectTrigger>
        <SelectContent className="bg-white border-2 border-black shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] text-zinc-800 max-h-[420px]">
          {files.map((f) => (
            <SelectItem key={f.filename} value={f.filename} className="cursor-pointer">
              <div className="flex flex-col gap-1.5 py-1">
                <div className="font-semibold text-sm truncate max-w-[280px]">
                  {f.model}
                </div>
                <div className="flex gap-2">
                  <span className="px-1.5 py-0.5 bg-blue-50 border border-blue-200 rounded text-[10px] font-semibold text-blue-700">
                    {f.cpu_cores != null ? `${f.cpu_cores} CPU` : "No CPU limit"}
                  </span>
                  <span className="px-1.5 py-0.5 bg-purple-50 border border-purple-200 rounded text-[10px] font-semibold text-purple-700">
                    {f.ram_gb != null ? `${f.ram_gb}GB` : "No RAM limit"}
                  </span>
                </div>
                <div className="text-[10px] text-zinc-400 font-mono">
                  {f.platform} · {f.technology} · {shortTimestamp(f.timestamp)}
                </div>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

