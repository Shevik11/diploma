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

export interface BenchmarkStatus {
  running: boolean;
  progress: number;
  status: string;
  message: string;
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

export interface BenchmarkSummary {
  model: string;
  platform: string;
  technology: string;
  timestamp: string;
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
}

export interface BenchmarkResultFile {
  filename: string;
  filepath: string;
  model: string;
  platform: string;
  timestamp: string;
  summary: BenchmarkSummary['summary'];
  test_results?: TestScriptResult[];
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

  async startContainer(model: string, technology: string): Promise<DeploymentState> {
    const data = await this.request<{ state: DeploymentState }>('/container/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, technology }),
    });
    return data.state;
  }

  async stopContainer(): Promise<DeploymentState> {
    const data = await this.request<{ state: DeploymentState }>('/container/stop', {
      method: 'POST',
    });
    return data.state;
  }

  async startVM(model: string, technology: string): Promise<DeploymentState> {
    const data = await this.request<{ state: DeploymentState }>('/vm/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, technology }),
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
    technology: string
  ): Promise<{ success: boolean; filepath: string; summary: BenchmarkSummary }> {
    return this.request<{ success: boolean; filepath: string; summary: BenchmarkSummary }>('/benchmarks/run-all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, platform, technology }),
    });
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
    let heartbeatInterval: ReturnType<typeof setInterval> | undefined;

    ws.onopen = () => {
      heartbeatInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping');
        }
      }, 2000);
    };

    ws.onclose = () => {
      clearInterval(heartbeatInterval);
    };

    ws.onerror = () => {
      clearInterval(heartbeatInterval);
    };

    return ws;
  }
}

export const api = new ApiService();
