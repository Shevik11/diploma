import { useState, useEffect } from 'react';
import { Play, CheckCircle, XCircle, Loader2, Download, RefreshCw } from 'lucide-react';
import { Progress } from '@/app/components/ui/progress';
import { Checkbox } from '@/app/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/app/components/ui/select';
import {
  api,
  BenchmarkCategory,
  BenchmarkStatus,
  OllamaStatus,
  BenchmarkResultFile,
  BenchmarkSummary,
} from '@/app/services/api';

export function BenchmarkRunner() {
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus>({ connected: false, models: [] });
  const [categories, setCategories] = useState<BenchmarkCategory[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [benchmarkStatus, setBenchmarkStatus] = useState<BenchmarkStatus>({
    running: false,
    progress: 0,
    status: 'idle',
    message: '',
  });
  const [results, setResults] = useState<BenchmarkResultFile[]>([]);
  const [currentResult, setCurrentResult] = useState<BenchmarkSummary | null>(null);
  const [, setIsLoading] = useState(false);

  // Fetch initial data
  useEffect(() => {
    checkOllamaStatus();
    fetchCategories();
    fetchResults();
  }, []);

  // Poll benchmark status when running
  useEffect(() => {
    if (!benchmarkStatus.running) return;

    const interval = setInterval(async () => {
      const status = await api.getBenchmarkStatus();
      setBenchmarkStatus(status);

      if (!status.running) {
        clearInterval(interval);
        fetchResults();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [benchmarkStatus.running]);

  const checkOllamaStatus = async () => {
    try {
      const status = await api.getOllamaStatus();
      setOllamaStatus(status);
      if (status.models.length > 0 && !selectedModel) {
        setSelectedModel(status.models[0]);
      }
    } catch {
      setOllamaStatus({ connected: false, models: [] });
    }
  };

  const fetchCategories = async () => {
    try {
      const cats = await api.getBenchmarkCategories();
      setCategories(cats);
    } catch {
      // Categories unavailable
    }
  };

  const fetchResults = async () => {
    try {
      const res = await api.getBenchmarkResults();
      setResults(res);
    } catch {
      // Results unavailable
    }
  };

  const toggleCategory = (value: string) => {
    setSelectedCategories((prev) =>
      prev.includes(value) ? prev.filter((c) => c !== value) : [...prev, value]
    );
  };

  const runBenchmark = async () => {
    if (!selectedModel || selectedCategories.length === 0) return;

    setIsLoading(true);
    setBenchmarkStatus({
      running: true,
      progress: 0,
      status: 'starting',
      message: 'Starting benchmark...',
    });

    try {
      const result = await api.runBenchmark(
        selectedModel,
        selectedCategories,
        true,
        1
      );
      setCurrentResult(result.summary);
      fetchResults();
    } catch (e) {
      setBenchmarkStatus({
        running: false,
        progress: 0,
        status: 'error',
        message: e instanceof Error ? e.message : 'Benchmark failed',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const viewResult = async (filename: string) => {
    try {
      const result = await api.getBenchmarkResult(filename);
      setCurrentResult(result);
    } catch {
      // Failed to load result
    }
  };

  const downloadResult = (result: BenchmarkResultFile) => {
    const dataStr = JSON.stringify(result, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = result.filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Ollama Status */}
      <div className="bg-white border rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-medium text-lg">Docker Ollama Benchmark</h3>
          <button
            onClick={checkOllamaStatus}
            className="p-2 text-sm font-bold text-black bg-white border-2 border-black rounded-lg shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] hover:translate-x-[2px] hover:translate-y-[2px] active:shadow-none active:translate-x-[3px] active:translate-y-[3px] transition-all duration-100"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        <div className="flex items-center gap-2 mb-4">
          {ollamaStatus.connected ? (
            <>
              <CheckCircle className="w-5 h-5 text-green-500" />
              <span className="text-green-600 font-medium">Ollama Connected</span>
              <span className="text-gray-500 text-sm">({ollamaStatus.models.length} models available)</span>
            </>
          ) : (
            <>
              <XCircle className="w-5 h-5 text-red-500" />
              <span className="text-red-600 font-medium">Ollama Not Connected</span>
              <span className="text-gray-500 text-sm">(Start Ollama in Docker)</span>
            </>
          )}
        </div>

        {ollamaStatus.connected && (
          <>
            {/* Model Selection */}
            <div className="mb-4">
              <label className="block text-sm mb-2 text-gray-600">Select Model</label>
              <Select value={selectedModel} onValueChange={setSelectedModel}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select a model" />
                </SelectTrigger>
                <SelectContent>
                  {ollamaStatus.models.map((model) => (
                    <SelectItem key={model} value={model}>
                      {model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Categories Selection */}
            <div className="mb-4">
              <label className="block text-sm mb-2 text-gray-600">Benchmark Categories</label>
              <div className="grid grid-cols-2 gap-2">
                {categories.map((cat) => (
                  <div
                    key={cat.value}
                    className="flex items-center gap-2 p-2 bg-gray-50 rounded-lg"
                  >
                    <Checkbox
                      checked={selectedCategories.includes(cat.value)}
                      onCheckedChange={() => toggleCategory(cat.value)}
                      disabled={benchmarkStatus.running}
                    />
                    <span className="text-sm">{cat.label}</span>
                    <span className="text-xs text-gray-400">({cat.prompts})</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Run Button */}
            <button
              onClick={runBenchmark}
              disabled={benchmarkStatus.running || selectedCategories.length === 0 || !selectedModel}
              className="w-full px-4 py-3 text-sm font-bold text-black bg-white border-2 border-black rounded-lg shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] hover:translate-x-[2px] hover:translate-y-[2px] active:shadow-none active:translate-x-[3px] active:translate-y-[3px] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] disabled:hover:translate-x-0 disabled:hover:translate-y-0 transition-all duration-100 flex items-center justify-center gap-2"
            >
              {benchmarkStatus.running ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Running Benchmark...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  Run Benchmark ({selectedCategories.length} categories)
                </>
              )}
            </button>

            {/* Progress */}
            {benchmarkStatus.running && (
              <div className="mt-4">
                <Progress value={benchmarkStatus.progress} className="h-2" />
                <p className="text-xs text-gray-500 mt-1">
                  {benchmarkStatus.progress}% - {benchmarkStatus.message}
                </p>
              </div>
            )}
          </>
        )}
      </div>

      {/* Current Result Summary */}
      {currentResult && (
        <div className="bg-white border rounded-lg p-6">
          <h3 className="font-medium text-lg mb-4">Latest Result: {currentResult.model}</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">Tokens/sec</p>
              <p className="text-lg font-mono font-semibold">
                {currentResult.summary.avg_tokens_per_second.toFixed(1)}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">Avg Latency</p>
              <p className="text-lg font-mono font-semibold">
                {currentResult.summary.avg_latency_ms.toFixed(0)}ms
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">Success Rate</p>
              <p className="text-lg font-mono font-semibold">
                {currentResult.summary.success_rate.toFixed(0)}%
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">Total Tokens</p>
              <p className="text-lg font-mono font-semibold">
                {currentResult.summary.total_tokens_generated}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Previous Results */}
      {results.length > 0 && (
        <div className="bg-white border rounded-lg p-6">
          <h3 className="font-medium text-lg mb-4">Previous Results</h3>
          <div className="space-y-2">
            {results.slice(0, 5).map((result) => (
              <div
                key={result.filename}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
              >
                <div>
                  <p className="font-medium text-sm">{result.model}</p>
                  <p className="text-xs text-gray-500">
                    {result.platform} • {new Date(result.timestamp).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono bg-gray-200 px-2 py-1 rounded">
                    {result.summary?.avg_tokens_per_second?.toFixed(1)} tok/s
                  </span>
                  <button
                    onClick={() => viewResult(result.filename)}
                    className="p-2 text-gray-600 hover:text-black"
                  >
                    View
                  </button>
                  <button
                    onClick={() => downloadResult(result)}
                    className="p-2 text-gray-600 hover:text-black"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
