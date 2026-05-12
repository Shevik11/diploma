import { useState, useEffect } from "react";
import { DeploymentCard } from "@/app/components/deployment-card";
import { MetricsSection } from "@/app/components/metrics-section";
import { ResultsViewer } from "@/app/components/results-viewer";
import { ModelCompare } from "@/app/components/model-compare";
import { ModelDashboard } from "@/app/components/model-dashboard";
import { TopModels } from "@/app/components/top-models";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/app/components/ui/select";
import {
  api,
  Model,
  DeploymentState,
  BenchmarkCategory,
} from "@/app/services/api";
import {
  Play,
  BarChart3,
  Loader2,
  CheckCircle,
  XCircle,
  LayoutDashboard,
  GitCompare,
  FlaskConical,
  Trophy,
} from "lucide-react";
import { Progress } from "@/app/components/ui/progress";
import { Checkbox } from "@/app/components/ui/checkbox";

interface TestItem {
  id: string;
  name: string;
  status: "pending" | "running" | "passed" | "failed";
  duration?: number;
  selected: boolean;
}

export default function App() {
  const [selectedModel, setSelectedModel] = useState("phi-3-mini");
  const [selectedEnvironment, setSelectedEnvironment] = useState<
    "docker" | "vm"
  >("docker");
  const [selectedTechnology, setSelectedTechnology] = useState("ollama");
  // Multi-select RAM (GB) and CPU (cores). Picking >1 of either runs a sweep.
  const RAM_OPTIONS = [1, 2, 4, 8, 16];
  const CPU_OPTIONS = [1, 2, 4, 8];
  const [selectedRamGbs, setSelectedRamGbs] = useState<number[]>([4]);
  const [selectedCpuCoresList, setSelectedCpuCoresList] = useState<number[]>([2]);
  // Single-value fallbacks (used for the deploy/start path which only takes one (ram, cpu)).
  const selectedRamGb = selectedRamGbs[0] ?? 4;
  const selectedCpuCores = selectedCpuCoresList[0] ?? 2;

  const toggleRam = (v: number) =>
    setSelectedRamGbs((prev) =>
      prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v].sort((a, b) => a - b),
    );
  const toggleCpu = (v: number) =>
    setSelectedCpuCoresList((prev) =>
      prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v].sort((a, b) => a - b),
    );
  const [models, setModels] = useState<Model[]>([
    { value: "phi-3-mini", label: "Phi-3 Mini (3.8B)" },
    { value: "llama-3.2-1b", label: "Llama 3.2 (1B)" },
    { value: "llama-3.2-3b", label: "Llama 3.2 (3B)" },
    { value: "gemma-2b", label: "Gemma 2B" },
    { value: "mistral-7b", label: "Mistral 7B" },
    { value: "qwen2.5:0.5b", label: "Qwen 2.5 (0.5B)" },
    { value: "qwen2.5:1.5b", label: "Qwen 2.5 (1.5B)" },
    { value: "qwen2.5:3b", label: "Qwen 2.5 (3B)" },
    { value: "qwen2.5:7b", label: "Qwen 2.5 (7B)" },
    { value: "qwen2.5-coder:1.5b", label: "Qwen 2.5 Coder (1.5B)" },
    { value: "qwen2.5-coder:7b", label: "Qwen 2.5 Coder (7B)" },
  ]);
  const [deploymentState, setDeploymentState] = useState<DeploymentState>({
    status: "idle",
    technology: null,
    model: null,
    cpu: 0,
    memory: 0,
    latency: 0,
  });
  const [metricsData, setMetricsData] = useState<
    Array<{ time: string; cpu: number; memory: number }>
  >([{ time: "0s", cpu: 0, memory: 0 }]);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [isRunningTests, setIsRunningTests] = useState(false);
  const [testProgress, setTestProgress] = useState(0);
  const [runStatusMessage, setRunStatusMessage] = useState("");
  const [showResults, setShowResults] = useState(false);
  const [activeView, setActiveView] = useState<
    "dashboard" | "tests" | "compare" | "top"
  >("dashboard");

  // Test suite state
  const [tests, setTests] = useState<TestItem[]>([]);
  const [benchmarkCategories, setBenchmarkCategories] = useState<
    BenchmarkCategory[]
  >([]);
  const [selectedBenchmarkCategories, setSelectedBenchmarkCategories] =
    useState<string[]>([]);

  // Fetch models on mount
  useEffect(() => {
    api
      .getModels()
      .then((m) => {
        setModels(m);
        setSelectedModel((current) =>
          m.length > 0 && m.some((model) => model.value === current)
            ? current
            : m[0]?.value || current,
        );
        setBackendError(null);
      })
      .catch((e) => {
        setBackendError(e.message || "Backend unavailable");
      });
  }, []);

  // Fetch tests on mount
  useEffect(() => {
    api
      .getTests()
      .then((backendTests) => {
        setTests(backendTests.map((t) => ({ ...t, selected: false })));
      })
      .catch(() => {
        setTests([
          {
            id: "quality",
            name: "Quality Test",
            status: "pending",
            selected: false,
          },
          {
            id: "advanced_quality",
            name: "Advanced Quality Test",
            status: "pending",
            selected: false,
          },
          {
            id: "performance",
            name: "Performance Test",
            status: "pending",
            selected: false,
          },
          {
            id: "safety_robustness",
            name: "Safety & Robustness Test",
            status: "pending",
            selected: false,
          },
          {
            id: "stress_consistency",
            name: "Stress & Consistency Test",
            status: "pending",
            selected: false,
          },
          {
            id: "hard_tests",
            name: "Hard Tests",
            status: "pending",
            selected: false,
          },
          {
            id: "multilingual",
            name: "Multilingual Test",
            status: "pending",
            selected: false,
          },
          {
            id: "summarization",
            name: "Summarization Test",
            status: "pending",
            selected: false,
          },
          {
            id: "context_window",
            name: "Context Window Test",
            status: "pending",
            selected: false,
          },
          {
            id: "cost_efficiency",
            name: "Cost Efficiency Test",
            status: "pending",
            selected: false,
          },
          {
            id: "benchmark_mmlu",
            name: "MMLU Benchmark",
            status: "pending",
            selected: false,
          },
          {
            id: "benchmark_reasoning",
            name: "Reasoning Benchmark (ARC / HellaSwag / Winogrande)",
            status: "pending",
            selected: false,
          },
          {
            id: "benchmark_gsm8k",
            name: "GSM8K Math Benchmark",
            status: "pending",
            selected: false,
          },
          {
            id: "benchmark_truthfulqa",
            name: "TruthfulQA Benchmark",
            status: "pending",
            selected: false,
          },
          {
            id: "benchmark_humaneval",
            name: "HumanEval Code Benchmark",
            status: "pending",
            selected: false,
          },
          {
            id: "compare_models",
            name: "Compare Models",
            status: "pending",
            selected: false,
          },
          {
            id: "run_all",
            name: "Run All Tests",
            status: "pending",
            selected: false,
          },
        ]);
      });
  }, []);

  // Fetch benchmark categories on mount
  useEffect(() => {
    api
      .getBenchmarkCategories()
      .then((cats) => setBenchmarkCategories(cats))
      .catch(() => {});
  }, []);

  // Connect to WebSocket for real-time metrics
  useEffect(() => {
    let ws: WebSocket | null = null;

    try {
      ws = api.connectWebSocket((data) => {
        const platformData =
          selectedEnvironment === "docker" ? data.container : data.vm;
        setDeploymentState(platformData);

        setMetricsData((prev) => {
          const newPoint = {
            time: `${prev.length * 2}s`,
            cpu: platformData.cpu,
            memory: platformData.memory,
          };
          return [...prev.slice(-29), newPoint];
        });
      });
    } catch {
      // WebSocket failed, will use polling
    }

    return () => {
      if (ws) ws.close();
    };
  }, [selectedEnvironment]);

  // Fallback: poll for status updates
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const status = await api.getStatus();
        const platformData =
          selectedEnvironment === "docker" ? status.container : status.vm;
        setDeploymentState(platformData);
        setBackendError(null);

        if (platformData.status === "running") {
          setMetricsData((prev) => {
            const newPoint = {
              time: `${prev.length * 5}s`,
              cpu: platformData.cpu,
              memory: platformData.memory,
            };
            return [...prev.slice(-29), newPoint];
          });
        }
      } catch {
        // API might not be available yet
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [selectedEnvironment]);

  const handleStart = async () => {
    try {
      setBackendError(null);
      const state =
        selectedEnvironment === "docker"
          ? await api.startContainer(
              selectedModel,
              selectedTechnology,
              selectedRamGb,
              selectedCpuCores,
            )
          : await api.startVM(
              selectedModel,
              selectedTechnology,
              selectedRamGb,
              selectedCpuCores,
            );
      setDeploymentState(state);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to start";
      setBackendError(msg);
    }
  };

  const handleStop = async () => {
    try {
      const state =
        selectedEnvironment === "docker"
          ? await api.stopContainer()
          : await api.stopVM();
      setDeploymentState(state);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to stop";
      setBackendError(msg);
    }
  };

  const toggleTest = (id: string) => {
    setTests((prev) =>
      prev.map((t) => (t.id === id ? { ...t, selected: !t.selected } : t)),
    );
  };

  const toggleBenchmarkCategory = (value: string) => {
    setSelectedBenchmarkCategories((prev) =>
      prev.includes(value) ? prev.filter((c) => c !== value) : [...prev, value],
    );
  };

  const selectAllTests = () => {
    const allSelected = tests.every((t) => t.selected);
    setTests((prev) => prev.map((t) => ({ ...t, selected: !allSelected })));
  };

  const selectAllBenchmarks = () => {
    if (selectedBenchmarkCategories.length === benchmarkCategories.length) {
      setSelectedBenchmarkCategories([]);
    } else {
      setSelectedBenchmarkCategories(benchmarkCategories.map((c) => c.value));
    }
  };

  const handleRunAllTests = async () => {
    if (deploymentState.status !== "running") return;
    setIsRunningTests(true);
    setTestProgress(0);
    setRunStatusMessage("Starting benchmarks and tests...");
    setShowResults(false);

    try {
      if (selectedRamGbs.length === 0 || selectedCpuCoresList.length === 0) {
        throw new Error("Pick at least one RAM value and one CPU value");
      }

      // Build cross-product of selected RAMs × CPUs. If exactly one of each, this is a single config.
      const configs = selectedRamGbs.flatMap((ram) =>
        selectedCpuCoresList.map((cpu) => ({ ram_gb: ram, cpu_cores: cpu })),
      );
      const isSweep = configs.length > 1;

      await api.runAllTests(
        selectedModel,
        selectedEnvironment,
        selectedTechnology,
        selectedRamGb,
        selectedCpuCores,
        isSweep ? { configs } : undefined,
      );

      // run-all endpoint returns immediately; poll backend status until completion
      const startedAt = Date.now();
      const maxWaitMs = 2 * 60 * 60 * 1000; // 2h safety cap for very long suites

      while (true) {
        if (Date.now() - startedAt > maxWaitMs) {
          throw new Error("Run timed out while waiting for completion");
        }

        await new Promise((resolve) => setTimeout(resolve, 2000));
        const status = await api.getBenchmarkStatus();

        setTestProgress(Math.max(1, Math.min(status.progress ?? 0, 100)));
        setRunStatusMessage(
          status.message || "Running benchmarks and tests...",
        );

        if (!status.running) {
          if (status.status === "error") {
            throw new Error(status.message || "Run failed");
          }
          break;
        }
      }

      setTestProgress(100);
      setRunStatusMessage("Completed");

      window.dispatchEvent(new Event("benchmark-completed"));

      setTimeout(() => {
        setShowResults(true);
        setIsRunningTests(false);
        setRunStatusMessage("");
      }, 500);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Tests failed";
      setBackendError(msg);
      setIsRunningTests(false);
      setRunStatusMessage("");
    }
  };

  const getTestIcon = (status: TestItem["status"]) => {
    switch (status) {
      case "running":
        return <Loader2 className="w-4 h-4 animate-spin text-blue-500" />;
      case "passed":
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case "failed":
        return <XCircle className="w-4 h-4 text-red-500" />;
      default:
        return (
          <div className="w-4 h-4 rounded-full border-2 border-gray-300" />
        );
    }
  };

  const selectedTestCount = tests.filter((t) => t.selected).length;
  const selectedModelMeta = models.find((m) => m.value === selectedModel);

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto p-8">
        {/* Header */}
        <div className="mb-8 flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl mb-2">SLM Deployment Control Panel</h1>
            <p className="text-gray-600">
              Benchmark small language models on Docker & VM
            </p>
          </div>
          <div className="flex gap-4 flex-wrap">
            {(
              [
                { id: "dashboard", label: "Dashboard", icon: <LayoutDashboard className="w-4 h-4" /> },
                { id: "tests",     label: "Tests",     icon: <FlaskConical className="w-4 h-4" /> },
                { id: "compare",   label: "Compare",   icon: <GitCompare className="w-4 h-4" /> },
                { id: "top",       label: "Top Models", icon: <Trophy className="w-4 h-4" /> },
              ] as const
            ).map(({ id, label, icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveView(id)}
                className={`px-6 py-2 text-sm font-bold border-2 border-black rounded-lg transition-all duration-100 flex items-center gap-2 ${
                  activeView === id
                    ? "bg-black text-white shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] translate-x-[2px] translate-y-[2px]"
                    : "bg-white text-black shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] hover:translate-x-[2px] hover:translate-y-[2px] active:shadow-none active:translate-x-[3px] active:translate-y-[3px]"
                }`}
              >
                {icon}
                {label}
              </button>
            ))}
          </div>
        </div>

        {activeView === "dashboard" && <ModelDashboard />}

        {activeView === "compare" && <ModelCompare />}

        {activeView === "top" && <TopModels />}

        {activeView === "tests" && (
          <>
            {/* Backend Error Banner */}
            {backendError && (
              <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-red-700 text-sm font-medium">
                  Warning: {backendError}
                </p>
                <p className="text-red-500 text-xs mt-1">
                  Make sure the backend is running:{" "}
                  <code>uvicorn backend.main:app --reload</code>
                </p>
              </div>
            )}

            {/* Top Control Bar: Environment / Model / Technology / Status */}
            <div className="mb-8 bg-white border rounded-lg p-6 flex items-center gap-6 flex-wrap">
              <div className="flex items-center gap-2">
                <label className="text-sm font-medium whitespace-nowrap">
                  Environment
                </label>
                <Select
                  value={selectedEnvironment}
                  onValueChange={(v) =>
                    setSelectedEnvironment(v as "docker" | "vm")
                  }
                >
                  <SelectTrigger className="w-36">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="docker">Docker</SelectItem>
                    <SelectItem value="vm">VM</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2">
                <label className="text-sm font-medium whitespace-nowrap">
                  Model
                </label>
                <Select value={selectedModel} onValueChange={setSelectedModel}>
                  <SelectTrigger className="w-52">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map((model) => (
                      <SelectItem key={model.value} value={model.value}>
                        {model.label}
                        {model.installed === false ? " (not pulled)" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2">
                <label className="text-sm font-medium whitespace-nowrap">
                  Technology
                </label>
                <Select
                  value={selectedTechnology}
                  onValueChange={setSelectedTechnology}
                >
                  <SelectTrigger className="w-44">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ollama">Ollama</SelectItem>
                    <SelectItem value="llama-cpp">llama.cpp</SelectItem>
                    <SelectItem value="vllm">vLLM</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2 ml-auto">
                <span className="text-sm font-medium">Status</span>
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                    deploymentState.status === "running"
                      ? "bg-green-100 text-green-800"
                      : deploymentState.status === "pulling"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {deploymentState.status === "running"
                    ? "Running"
                    : deploymentState.status === "pulling"
                      ? "Pulling"
                      : "Idle"}
                </span>
              </div>
            </div>

            {selectedModelMeta?.installed === false && (
              <p className="-mt-4 mb-6 text-sm text-amber-700">
                This model is not pulled yet. Press Start and it will be
                downloaded automatically.
              </p>
            )}

            {/* Deployment Card */}
            <div className="mb-8">
              <DeploymentCard
                type={selectedEnvironment === "docker" ? "container" : "vm"}
                modelName={
                  models.find((m) => m.value === selectedModel)?.label || ""
                }
                state={deploymentState}
                onStart={handleStart}
                onStop={handleStop}
              />
            </div>

            {/* Metrics Visualization */}
            <MetricsSection
              metricsData={metricsData}
              platform={selectedEnvironment}
            />

            {/* Tests & Benchmarks Selection — side by side */}
            <div className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Test Suites */}
              <div className="bg-white border rounded-lg p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-medium text-lg">Test Suites</h3>
                  <button
                    onClick={selectAllTests}
                    className="text-xs text-gray-500 hover:text-black underline"
                  >
                    {tests.every((t) => t.selected)
                      ? "Deselect All"
                      : "Select All"}
                  </button>
                </div>
                <div className="space-y-1 max-h-80 overflow-y-auto">
                  {tests.map((test) => (
                    <div
                      key={test.id}
                      className="flex items-center justify-between p-2.5 bg-gray-50 rounded"
                    >
                      <div className="flex items-center gap-3">
                        <Checkbox
                          checked={test.selected}
                          onCheckedChange={() => toggleTest(test.id)}
                          disabled={isRunningTests}
                        />
                        {getTestIcon(test.status)}
                        <span className="text-sm">{test.name}</span>
                      </div>
                      {test.duration !== undefined && test.duration > 0 && (
                        <span className="text-xs text-gray-500 font-mono">
                          {test.duration >= 1000
                            ? `${(test.duration / 1000).toFixed(1)}s`
                            : `${test.duration.toFixed(0)}ms`}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-400 mt-3">
                  {selectedTestCount} of {tests.length} selected
                </p>
              </div>

              {/* Benchmark Categories */}
              <div className="bg-white border rounded-lg p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-medium text-lg">Benchmark Categories</h3>
                  <button
                    onClick={selectAllBenchmarks}
                    className="text-xs text-gray-500 hover:text-black underline"
                  >
                    {selectedBenchmarkCategories.length ===
                      benchmarkCategories.length &&
                    benchmarkCategories.length > 0
                      ? "Deselect All"
                      : "Select All"}
                  </button>
                </div>
                {benchmarkCategories.length > 0 ? (
                  <div className="space-y-1 max-h-80 overflow-y-auto">
                    {benchmarkCategories.map((cat) => (
                      <div
                        key={cat.value}
                        className="flex items-center justify-between p-2.5 bg-gray-50 rounded"
                      >
                        <div className="flex items-center gap-3">
                          <Checkbox
                            checked={selectedBenchmarkCategories.includes(
                              cat.value,
                            )}
                            onCheckedChange={() =>
                              toggleBenchmarkCategory(cat.value)
                            }
                            disabled={isRunningTests}
                          />
                          <span className="text-sm">{cat.label}</span>
                        </div>
                        <span className="text-xs text-gray-400 font-mono">
                          {cat.prompts} prompts
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-400">
                    No benchmark categories available. Start the model first.
                  </p>
                )}
                <p className="text-xs text-gray-400 mt-3">
                  {selectedBenchmarkCategories.length} of{" "}
                  {benchmarkCategories.length} selected
                </p>
              </div>
            </div>

            {/* Resource configuration (RAM × CPU) — under Test Suites & Benchmark Categories */}
            <div className="mt-6 bg-white border rounded-lg p-6">
              <div className="mb-4">
                <h3 className="font-medium text-lg">Resource Configuration</h3>
                <p className="text-sm text-gray-500">
                  Pick one or more RAM and CPU values. The cross-product of
                  selections will be executed — one full benchmark + tests run
                  per (RAM × CPU) cell.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <div className="text-sm font-medium mb-2">RAM (GB)</div>
                  <div className="flex flex-wrap gap-3">
                    {RAM_OPTIONS.map((ram) => {
                      const id = `ram-${ram}`;
                      const checked = selectedRamGbs.includes(ram);
                      return (
                        <div key={ram} className="flex items-center gap-1.5">
                          <Checkbox
                            id={id}
                            checked={checked}
                            onCheckedChange={() => toggleRam(ram)}
                            disabled={isRunningTests}
                          />
                          <label htmlFor={id} className="text-sm cursor-pointer whitespace-nowrap">
                            {ram} GB
                          </label>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <div className="text-sm font-medium mb-2">CPU cores</div>
                  <div className="flex flex-wrap gap-3">
                    {CPU_OPTIONS.map((cpu) => {
                      const id = `cpu-${cpu}`;
                      const checked = selectedCpuCoresList.includes(cpu);
                      return (
                        <div key={cpu} className="flex items-center gap-1.5">
                          <Checkbox
                            id={id}
                            checked={checked}
                            onCheckedChange={() => toggleCpu(cpu)}
                            disabled={isRunningTests}
                          />
                          <label htmlFor={id} className="text-sm cursor-pointer whitespace-nowrap">
                            {cpu} {cpu === 1 ? "core" : "cores"}
                          </label>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {(selectedRamGbs.length > 0 && selectedCpuCoresList.length > 0) && (
                <p className="mt-4 text-xs text-gray-500">
                  {selectedRamGbs.length * selectedCpuCoresList.length === 1
                    ? `Will run 1 configuration: ${selectedRamGbs[0]} GB / ${selectedCpuCoresList[0]} core${selectedCpuCoresList[0] === 1 ? "" : "s"}.`
                    : `Sweep mode: will run ${selectedRamGbs.length * selectedCpuCoresList.length} configurations (${selectedRamGbs.length} RAM × ${selectedCpuCoresList.length} CPU), one benchmark + tests per cell.`}
                </p>
              )}
            </div>

            {/* Run Tests & Collect Metrics — below parameter blocks */}
            <div className="mt-6 bg-white border rounded-lg p-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium text-lg">
                    Run Tests & Collect Metrics
                  </h3>
                  <p className="text-sm text-gray-500">
                    Execute selected test suites and benchmarks, collect
                    metrics, save results
                  </p>
                </div>
                <button
                  onClick={handleRunAllTests}
                  disabled={
                    isRunningTests || deploymentState.status !== "running"
                  }
                  className="px-6 py-3 text-sm font-bold text-black bg-white border-2 border-black rounded-lg shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] hover:translate-x-[2px] hover:translate-y-[2px] active:shadow-none active:translate-x-[3px] active:translate-y-[3px] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] disabled:hover:translate-x-0 disabled:hover:translate-y-0 transition-all duration-100 flex items-center gap-2"
                >
                  {isRunningTests ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Running...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" />
                      Run Tests & Metrics
                    </>
                  )}
                </button>
              </div>

              {isRunningTests && (
                <div className="mt-4">
                  <Progress value={testProgress} className="h-2" />
                  <p className="text-xs text-gray-500 mt-1">
                    {Math.round(testProgress)}% Complete
                  </p>
                  {runStatusMessage && (
                    <p className="text-xs text-gray-500 mt-1">
                      {runStatusMessage}
                    </p>
                  )}
                </div>
              )}

              {deploymentState.status !== "running" && (
                <p className="text-xs text-amber-600 mt-2">
                  Start the model first before running tests
                </p>
              )}
            </div>

            {/* View Results Button */}
            <div className="mt-6 flex justify-center">
              <button
                onClick={() => setShowResults(!showResults)}
                className="px-6 py-3 text-sm font-bold text-black bg-white border-2 border-black rounded-lg shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] hover:translate-x-[2px] hover:translate-y-[2px] active:shadow-none active:translate-x-[3px] active:translate-y-[3px] transition-all duration-100 flex items-center gap-2"
              >
                <BarChart3 className="w-4 h-4" />
                {showResults ? "Hide Results" : "View Results"}
              </button>
            </div>

            {/* Results Viewer */}
            {showResults && (
              <div className="mt-6">
                <ResultsViewer />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
