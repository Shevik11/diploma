const API_BASE = '/api';

export interface Model {
  value: string;
  label: string;
}

export interface Technology {
  value: string;
  label: string;
}

export interface DeploymentState {
  status: 'idle' | 'running' | 'stopped';
  technology: string | null;
  model: string | null;
  cpu: number;
  memory: number;
  latency: number;
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
  async getModels(): Promise<Model[]> {
    const response = await fetch(`${API_BASE}/models`);
    const data = await response.json();
    return data.models;
  }

  async getTechnologies(): Promise<{ container: Technology[]; vm: Technology[] }> {
    const response = await fetch(`${API_BASE}/technologies`);
    return response.json();
  }

  async getStatus(): Promise<{ container: DeploymentState; vm: DeploymentState }> {
    const response = await fetch(`${API_BASE}/status`);
    return response.json();
  }

  async startContainer(model: string, technology: string): Promise<DeploymentState> {
    const response = await fetch(`${API_BASE}/container/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, technology }),
    });
    const data = await response.json();
    return data.state;
  }

  async stopContainer(): Promise<DeploymentState> {
    const response = await fetch(`${API_BASE}/container/stop`, {
      method: 'POST',
    });
    const data = await response.json();
    return data.state;
  }

  async startVM(model: string, technology: string): Promise<DeploymentState> {
    const response = await fetch(`${API_BASE}/vm/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, technology }),
    });
    const data = await response.json();
    return data.state;
  }

  async stopVM(): Promise<DeploymentState> {
    const response = await fetch(`${API_BASE}/vm/stop`, {
      method: 'POST',
    });
    const data = await response.json();
    return data.state;
  }

  async getMetrics(): Promise<MetricsDataPoint[]> {
    const response = await fetch(`${API_BASE}/metrics`);
    const data = await response.json();
    return data.data;
  }

  async getTests(): Promise<TestResult[]> {
    const response = await fetch(`${API_BASE}/tests`);
    const data = await response.json();
    return data.tests;
  }

  async runTests(testIds: string[], model?: string, technology?: string): Promise<TestResult[]> {
    const response = await fetch(`${API_BASE}/tests/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ test_ids: testIds, model, technology }),
    });
    const data = await response.json();
    return data.results;
  }

  async downloadMetrics(model: string, technology: string): Promise<{ filename: string; content: string }> {
    const response = await fetch(`${API_BASE}/metrics/download?model=${model}&technology=${technology}`);
    return response.json();
  }

  // Benchmark API methods
  async getOllamaStatus(): Promise<OllamaStatus> {
    const response = await fetch(`${API_BASE}/benchmarks/ollama/status`);
    return response.json();
  }

  async getBenchmarkStatus(): Promise<BenchmarkStatus> {
    const response = await fetch(`${API_BASE}/benchmarks/status`);
    return response.json();
  }

  async getBenchmarkCategories(): Promise<BenchmarkCategory[]> {
    const response = await fetch(`${API_BASE}/benchmarks/categories`);
    const data = await response.json();
    return data.categories;
  }

  async runBenchmark(
    model: string,
    categories?: string[],
    warmUp: boolean = true,
    runsPerPrompt: number = 1
  ): Promise<{ success: boolean; filepath: string; summary: BenchmarkSummary }> {
    const response = await fetch(`${API_BASE}/benchmarks/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        categories,
        warm_up: warmUp,
        runs_per_prompt: runsPerPrompt,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Benchmark failed');
    }
    return response.json();
  }

  async getBenchmarkResults(): Promise<BenchmarkResultFile[]> {
    const response = await fetch(`${API_BASE}/benchmarks/results`);
    const data = await response.json();
    return data.results;
  }

  async getBenchmarkResult(filename: string): Promise<BenchmarkSummary> {
    const response = await fetch(`${API_BASE}/benchmarks/results/${filename}`);
    return response.json();
  }

  async runAllTests(
    model: string,
    platform: string,
    technology: string
  ): Promise<{ success: boolean; filepath: string; summary: BenchmarkSummary }> {
    const response = await fetch(`${API_BASE}/benchmarks/run-all`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, platform, technology }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Run all tests failed');
    }
    return response.json();
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
