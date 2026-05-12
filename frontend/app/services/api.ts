const API_BASE = '/api';

export interface Model {
  value: string;
  label: string;
  installed?: boolean;
}

export interface Technology {
  value: string;
  label: string;
}

export interface DeploymentState {
  status: 'idle' | 'pulling' | 'running' | 'stopped';
  technology: string | null;
  model: string | null;
  cpu: number;
  memory: number;
  latency: number;
  message?: string;
}

export interface TestResult {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'passed' | 'failed';
  duration?: number;
}

export interface MetricsDataPoint {
  time: string;
  container: { cpu: number; memory: number; latency: number };
  vm: { cpu: number; memory: number; latency: number };
}

// Benchmark types
export interface BenchmarkCategory {
  value: string;
  label: string;
  prompts: number;
}

/**
 * Status string from `functionality.md` vocabulary. Used both per-run
 * (in saved JSON) and live in `benchmark_state.status` reported by
 * `/api/benchmarks/status`. The legacy values `running`/`completed`/
 * `error`/`stopped`/`skipped` are kept here for backward compatibility
 * with files saved before the spec-conformance update.
 */
export type RunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'not_enough_resources'
  | 'cancelled'
  // Legacy values still emitted by older files / live state
  | 'error'
  | 'stopped'
  | 'skipped'
  | 'idle'
  | 'warming_up'
  | string;

export interface BenchmarkStatus {
  running: boolean;
  progress: number;
  status: RunStatus;
  message: string;
}

/** Human-friendly label for a `RunStatus` value. */
export function runStatusLabel(status?: RunStatus | null): string {
  switch (status) {
    case 'completed':
      return 'Completed';
    case 'failed':
    case 'error':
      return 'Failed';
    case 'not_enough_resources':
      return 'Not enough resources';
    case 'cancelled':
    case 'stopped':
      return 'Cancelled';
    case 'skipped':
      return 'Skipped';
    case 'running':
      return 'Running';
    case 'warming_up':
      return 'Warming up';
    case 'pending':
      return 'Pending';
    case 'idle':
      return 'Idle';
    default:
      return status ? String(status) : '—';
  }
}

/** Tailwind classes for a small status pill. */
export function runStatusClass(status?: RunStatus | null): string {
  switch (status) {
    case 'completed':
      return 'bg-green-100 text-green-800 border-green-300';
    case 'failed':
    case 'error':
      return 'bg-red-100 text-red-800 border-red-300';
    case 'not_enough_resources':
      return 'bg-amber-100 text-amber-800 border-amber-300';
    case 'cancelled':
    case 'stopped':
    case 'skipped':
      return 'bg-zinc-100 text-zinc-700 border-zinc-300';
    case 'running':
    case 'warming_up':
    case 'pending':
      return 'bg-blue-100 text-blue-800 border-blue-300';
    default:
      return 'bg-zinc-100 text-zinc-700 border-zinc-300';
  }
}

export interface OllamaStatus {
  connected: boolean;
  models: string[];
}

export interface BenchmarkInference {
  first_token_latency_ms: number;
  total_duration_ms: number;
  tokens_generated: number;
  tokens_per_second: number;
  prompt_tokens: number;
  model_load_time_ms?: number;
}

export interface BenchmarkResources {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  memory_peak_mb: number;
}

export interface BenchmarkResultItem {
  category: string;
  run: number;
  prompt: string;
  response: string;
  inference: BenchmarkInference;
  resources: BenchmarkResources;
  success: boolean;
  error?: string;
}

export interface TestScriptResult {
  name: string;
  status: 'passed' | 'failed' | 'timeout' | 'error';
  duration: number;
  stdout?: string;
  stderr?: string;
  details?: Array<{
    prompt: string;
    response: string;
  }>;
}

/**
 * Set on a result file when the backend refused to even run a config
 * because the requested RAM was below the model's empirical minimum
 * (e.g. qwen2.5-coder:7b at 1 GB). The frontend uses this to push such
 * variants to the bottom of the leaderboard with a clear reason instead
 * of treating them as real "0-score" measurements.
 */
export interface InfeasibleInfo {
  reason: string;
  required_ram_gb: number;
  skipped?: boolean;
}

export interface BenchmarkSummary {
  model: string;
  platform: string;
  technology: string;
  timestamp: string;
  /** ISO timestamp of the moment the run started (backend ≥ spec update). */
  started_at?: string | null;
  /** ISO timestamp of the moment the run finished or was decided. */
  finished_at?: string | null;
  /** Spec status string. May be missing for legacy files. */
  status?: RunStatus | null;
  ram_gb?: number | null;
  cpu_cores?: number | null;
  system_info: Record<string, unknown>;
  results: BenchmarkResultItem[];
  test_results?: TestScriptResult[];
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
  infeasible?: InfeasibleInfo | null;
}

export interface BenchmarkResultFile {
  filename: string;
  filepath: string;
  model: string;
  platform: string;
  technology?: string;
  ram_gb?: number | null;
  cpu_cores?: number | null;
  timestamp: string;
  /** ISO timestamp the run started (backend ≥ spec update; falls back to `timestamp` for legacy files). */
  started_at?: string | null;
  /** ISO timestamp the run finished (backend ≥ spec update; falls back to `timestamp` for legacy files). */
  finished_at?: string | null;
  /** Spec status string; backend derives it from `infeasible` / `summary.successful` for legacy files. */
  status?: RunStatus | null;
  summary: BenchmarkSummary['summary'];
  test_results?: TestScriptResult[];
  infeasible?: InfeasibleInfo | null;
}

/**
 * A run is considered infeasible when the backend never executed it because
 * the requested RAM was below the model's empirical minimum. Newer files
 * carry `status === 'not_enough_resources'`; older files only have the
 * `infeasible` block, so we accept either.
 */
export function isInfeasible(
  f: Pick<BenchmarkResultFile, 'status' | 'infeasible'>,
): boolean {
  return f.status === 'not_enough_resources' || Boolean(f.infeasible);
}

/**
 * Build a stable key identifying a benchmark variant: same model run with
 * different parameters (CPU/RAM/platform/technology) yields different ids,
 * so they show up as separate items in dashboards.
 */
export function variantId(
  f: Pick<BenchmarkResultFile, 'model' | 'platform' | 'technology' | 'ram_gb' | 'cpu_cores'>,
): string {
  const ram = f.ram_gb ? `${f.ram_gb}GB` : 'noRAM';
  const cpu = f.cpu_cores ? `${f.cpu_cores}c` : 'noCPU';
  const tech = f.technology || 'tech?';
  const plat = f.platform || 'plat?';
  return `${f.model}__${ram}__${cpu}__${tech}__${plat}`;
}

/** Human-readable label for a variant, e.g. `qwen:1.5b · 4GB · 2c · ollama/docker`. */
export function variantLabel(
  f: Pick<BenchmarkResultFile, 'model' | 'platform' | 'technology' | 'ram_gb' | 'cpu_cores'>,
): string {
  const parts: string[] = [f.model];
  const cfg: string[] = [];
  cfg.push(f.ram_gb ? `${f.ram_gb}GB` : 'no-RAM-cap');
  cfg.push(f.cpu_cores ? `${f.cpu_cores}c` : 'no-CPU-cap');
  const stack = [f.technology, f.platform].filter(Boolean).join('/');
  if (stack) cfg.push(stack);
  parts.push(`(${cfg.join(' · ')})`);
  return parts.join(' ');
}

class ApiService {
  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, init);
    const contentType = response.headers.get('content-type') || '';

    let payload: unknown = null;
    if (contentType.includes('application/json')) {
      payload = await response.json();
    } else {
      payload = await response.text();
    }

    if (!response.ok) {
      const detail =
        typeof payload === 'object' && payload !== null && 'detail' in payload
          ? String((payload as { detail?: unknown }).detail ?? '')
          : typeof payload === 'string'
            ? payload
            : '';
      throw new Error(detail || `Request failed (${response.status})`);
    }

    return payload as T;
  }

  async getModels(): Promise<Model[]> {
    const data = await this.request<{ models: Model[] }>('/models');
    return data.models;
  }

  async getTechnologies(): Promise<{ container: Technology[]; vm: Technology[] }> {
    return this.request<{ container: Technology[]; vm: Technology[] }>('/technologies');
  }

  async getStatus(): Promise<{ container: DeploymentState; vm: DeploymentState }> {
    return this.request<{ container: DeploymentState; vm: DeploymentState }>('/status');
  }

  async startContainer(model: string, technology: string, ramGb?: number, cpuCores?: number): Promise<DeploymentState> {
    const data = await this.request<{ state: DeploymentState }>('/container/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, technology, ram_gb: ramGb ?? null, cpu_cores: cpuCores ?? null }),
    });
    return data.state;
  }

  async stopContainer(): Promise<DeploymentState> {
    const data = await this.request<{ state: DeploymentState }>('/container/stop', {
      method: 'POST',
    });
    return data.state;
  }

  async startVM(model: string, technology: string, ramGb?: number, cpuCores?: number): Promise<DeploymentState> {
    const data = await this.request<{ state: DeploymentState }>('/vm/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, technology, ram_gb: ramGb ?? null, cpu_cores: cpuCores ?? null }),
    });
    return data.state;
  }

  async stopVM(): Promise<DeploymentState> {
    const data = await this.request<{ state: DeploymentState }>('/vm/stop', {
      method: 'POST',
    });
    return data.state;
  }

  async getMetrics(): Promise<MetricsDataPoint[]> {
    const data = await this.request<{ data: MetricsDataPoint[] }>('/metrics');
    return data.data;
  }

  async getTests(): Promise<TestResult[]> {
    const data = await this.request<{ tests: TestResult[] }>('/tests');
    return data.tests;
  }

  async runTests(testIds: string[], model?: string, technology?: string): Promise<TestResult[]> {
    const data = await this.request<{ results: TestResult[] }>('/tests/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ test_ids: testIds, model, technology }),
    });
    return data.results;
  }

  async downloadMetrics(model: string, technology: string): Promise<{ filename: string; content: string }> {
    const params = new URLSearchParams({ model, technology });
    return this.request<{ filename: string; content: string }>(`/metrics/download?${params.toString()}`);
  }

  // Benchmark API methods
  async getOllamaStatus(): Promise<OllamaStatus> {
    return this.request<OllamaStatus>('/benchmarks/ollama/status');
  }

  async getBenchmarkStatus(): Promise<BenchmarkStatus> {
    return this.request<BenchmarkStatus>('/benchmarks/status');
  }

  async getBenchmarkCategories(): Promise<BenchmarkCategory[]> {
    const data = await this.request<{ categories: BenchmarkCategory[] }>('/benchmarks/categories');
    return data.categories;
  }

  async runBenchmark(
    model: string,
    categories?: string[],
    warmUp: boolean = true,
    runsPerPrompt: number = 1
  ): Promise<{ success: boolean; filepath: string; summary: BenchmarkSummary }> {
    return this.request<{ success: boolean; filepath: string; summary: BenchmarkSummary }>('/benchmarks/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        categories,
        warm_up: warmUp,
        runs_per_prompt: runsPerPrompt,
      }),
    });
  }

  async getBenchmarkResults(): Promise<BenchmarkResultFile[]> {
    const data = await this.request<{ results: BenchmarkResultFile[] }>('/benchmarks/results');
    return data.results;
  }

  async getBenchmarkResult(filename: string): Promise<BenchmarkSummary> {
    return this.request<BenchmarkSummary>(`/benchmarks/results/${filename}`);
  }

  async runAllTests(
    model: string,
    platform: string,
    technology: string,
    ramGb?: number,
    cpuCores?: number,
    options?: {
      configs?: Array<{ ram_gb?: number | null; cpu_cores?: number | null }>;
      ramOptions?: number[];
      cpuOptions?: number[];
      runAllConfigs?: boolean;
    },
  ): Promise<{ success: boolean; message?: string; configs?: Array<{ ram_gb: number | null; cpu_cores: number | null }> }> {
    return this.request<{ success: boolean; message?: string; configs?: Array<{ ram_gb: number | null; cpu_cores: number | null }> }>('/benchmarks/run-all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        platform,
        technology,
        ram_gb: ramGb ?? null,
        cpu_cores: cpuCores ?? null,
        configs: options?.configs ?? null,
        ram_options: options?.ramOptions ?? null,
        cpu_options: options?.cpuOptions ?? null,
        run_all_configs: options?.runAllConfigs ?? false,
      }),
    });
  }

  async getResourceOptions(): Promise<{
    ram_options_gb: number[];
    cpu_options: number[];
    default_matrix: Array<{ ram_gb: number; cpu_cores: number }>;
  }> {
    return this.request('/benchmarks/resource-options');
  }

  // WebSocket connection for real-time metrics
  connectWebSocket(onMessage: (data: { container: DeploymentState; vm: DeploymentState }) => void): WebSocket {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/metrics`);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'metrics') {
        onMessage(data.data);
      }
    };

    // Send heartbeat to trigger metrics updates
    ws.onopen = () => {
      setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping');
        }
      }, 2000);
    };

    return ws;
  }
}

export const api = new ApiService();
