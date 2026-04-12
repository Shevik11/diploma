import { useState, useEffect } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import { api, BenchmarkResultFile, BenchmarkSummary } from '@/app/services/api';

export function ResultsViewer() {
  const [results, setResults] = useState<BenchmarkResultFile[]>([]);
  const [selectedResult, setSelectedResult] = useState<BenchmarkSummary | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchResults();

    // Auto-refresh when benchmarks/tests complete
    const onComplete = () => {
      fetchResults();
      // Re-fetch the latest results list and auto-select the newest
      api.getBenchmarkResults().then(res => {
        if (res.length > 0) {
          viewResult(res[0].filename);
        }
      }).catch(() => {});
    };
    window.addEventListener('benchmark-completed', onComplete);

    // Poll for updates every 10s while tests may be running
    // This ensures test_results appear as they complete
    const pollInterval = setInterval(() => {
      fetchResults();
    }, 10000);

    return () => {
      window.removeEventListener('benchmark-completed', onComplete);
      clearInterval(pollInterval);
    };
  }, []);

  const fetchResults = async () => {
    setLoading(true);
    try {
      const res = await api.getBenchmarkResults();
      setResults(res);
    } catch {
      // Results unavailable
    } finally {
      setLoading(false);
    }
  };

  const viewResult = async (filename: string) => {
    try {
      const result = await api.getBenchmarkResult(filename);
      setSelectedResult(result);
    } catch {
      // Failed to load
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
      {/* Results List */}
      <div className="bg-white border rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-medium text-lg">Saved Test Results</h3>
          <button
            onClick={fetchResults}
            disabled={loading}
            className="p-2 text-sm font-bold text-black bg-white border-2 border-black rounded-lg shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] hover:translate-x-[2px] hover:translate-y-[2px] active:shadow-none active:translate-x-[3px] active:translate-y-[3px] transition-all duration-100"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {results.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No test results yet. Run tests to see results here.</p>
        ) : (
          <div className="space-y-2">
            {results.map((result) => (
              <div
                key={result.filename}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <div>
                  <p className="font-medium text-sm">{result.model}</p>
                  <p className="text-xs text-gray-500">
                    {result.platform} • {new Date(result.timestamp).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {result.test_results && result.test_results.length > 0 && (
                    <span className={`text-sm font-mono px-2 py-1 rounded ${
                      result.test_results.every((t: { status: string }) => t.status === 'passed') ? 'bg-green-100 text-green-700' :
                      result.test_results.some((t: { status: string }) => t.status === 'passed') ? 'bg-yellow-100 text-yellow-700' :
                      'bg-red-100 text-red-700'
                    }`}>
                      {result.test_results.filter((t: { status: string }) => t.status === 'passed').length}/{result.test_results.length} tests
                    </span>
                  )}
                  {result.summary && (
                    <span className="text-sm font-mono bg-gray-200 px-2 py-1 rounded">
                      {result.summary.avg_tokens_per_second?.toFixed(1)} tok/s
                    </span>
                  )}
                  <button
                    onClick={() => viewResult(result.filename)}
                    className="px-3 py-1 text-xs font-bold text-black bg-white border-2 border-black rounded shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:shadow-none hover:translate-x-[2px] hover:translate-y-[2px] transition-all duration-100"
                  >
                    View
                  </button>
                  <button
                    onClick={() => downloadResult(result)}
                    className="p-1 text-gray-600 hover:text-black"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Detailed Result View */}
      {selectedResult && (
        <div className="bg-white border rounded-lg p-6">
          <h3 className="font-medium text-lg mb-4">
            Result: {selectedResult.model} — {selectedResult.platform}
          </h3>

          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">Tokens/sec</p>
              <p className="text-lg font-mono font-semibold">
                {selectedResult.summary.avg_tokens_per_second.toFixed(1)}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">Avg Latency</p>
              <p className="text-lg font-mono font-semibold">
                {selectedResult.summary.avg_latency_ms.toFixed(0)}ms
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">Success Rate</p>
              <p className="text-lg font-mono font-semibold">
                {selectedResult.summary.success_rate.toFixed(0)}%
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">Total Tokens</p>
              <p className="text-lg font-mono font-semibold">
                {selectedResult.summary.total_tokens_generated}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">First Token Latency</p>
              <p className="text-lg font-mono font-semibold">
                {selectedResult.summary.avg_first_token_latency_ms.toFixed(0)}ms
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">Avg CPU</p>
              <p className="text-lg font-mono font-semibold">
                {selectedResult.summary.avg_cpu_percent.toFixed(1)}%
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">Avg Memory</p>
              <p className="text-lg font-mono font-semibold">
                {selectedResult.summary.avg_memory_percent.toFixed(1)}%
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 uppercase">Prompts</p>
              <p className="text-lg font-mono font-semibold">
                {selectedResult.summary.successful}/{selectedResult.summary.total_prompts}
              </p>
            </div>
          </div>

          {/* Test Script Results */}
          {selectedResult.test_results && selectedResult.test_results.length > 0 ? (
            <div className="mb-6">
              <h4 className="font-medium text-sm mb-2">Test Suite Results</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {selectedResult.test_results.map((t, i) => (
                  <div
                    key={i}
                    className={`flex items-center justify-between p-3 rounded-lg border ${
                      t.status === 'passed' ? 'bg-green-50 border-green-200' :
                      t.status === 'timeout' ? 'bg-yellow-50 border-yellow-200' :
                      'bg-red-50 border-red-200'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-lg">
                        {t.status === 'passed' ? '✅' : t.status === 'timeout' ? '⏱️' : '❌'}
                      </span>
                      <span className="text-sm font-medium">{t.name}</span>
                      {t.status !== 'passed' && t.status !== 'failed' && (
                        <span className="text-xs text-gray-400">({t.status})</span>
                      )}
                    </div>
                    <span className="text-xs font-mono text-gray-500">
                      {(t.duration / 1000).toFixed(1)}s
                    </span>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex items-center gap-4 text-sm">
                <span className="font-medium">
                  Score: {selectedResult.test_results.filter(t => t.status === 'passed').length}/{selectedResult.test_results.length}
                  {' '}({(selectedResult.test_results.filter(t => t.status === 'passed').length / selectedResult.test_results.length * 100).toFixed(0)}%)
                </span>
                <span className="text-gray-500">
                  Total time: {(selectedResult.test_results.reduce((sum, t) => sum + t.duration, 0) / 1000).toFixed(1)}s
                </span>
              </div>
            </div>
          ) : (
            <div className="mb-6 bg-gray-50 border border-gray-200 rounded-lg p-4 text-center">
              <p className="text-gray-500 text-sm">No test script results available for this run.</p>
              <p className="text-gray-400 text-xs mt-1">Test scripts run after benchmarks. If tests are still running, click View again to refresh.</p>
            </div>
          )}

          {/* Individual Benchmark Results Table */}
          {selectedResult.results && selectedResult.results.length > 0 && (
            <div>
              <h4 className="font-medium text-sm mb-2">Individual Benchmark Results</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2 px-2">Category</th>
                      <th className="text-left py-2 px-2">Prompt</th>
                      <th className="text-right py-2 px-2">Tokens/s</th>
                      <th className="text-right py-2 px-2">Latency</th>
                      <th className="text-right py-2 px-2">CPU %</th>
                      <th className="text-center py-2 px-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedResult.results.map((r, i) => (
                      <tr key={i} className="border-b hover:bg-gray-50">
                        <td className="py-2 px-2 font-mono text-xs">{r.category}</td>
                        <td className="py-2 px-2 text-xs max-w-[200px] truncate">{r.prompt}</td>
                        <td className="py-2 px-2 text-right font-mono">{r.inference.tokens_per_second.toFixed(1)}</td>
                        <td className="py-2 px-2 text-right font-mono">{r.inference.total_duration_ms.toFixed(0)}ms</td>
                        <td className="py-2 px-2 text-right font-mono">{r.resources.cpu_percent.toFixed(1)}%</td>
                        <td className="py-2 px-2 text-center">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${r.success ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                            {r.success ? 'OK' : 'FAIL'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
