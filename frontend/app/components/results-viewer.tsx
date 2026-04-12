import { useState, useEffect, useMemo } from 'react';
import { Download, RefreshCw, MoreHorizontal } from 'lucide-react';
import { api, BenchmarkResultFile, BenchmarkSummary, BenchmarkStatus } from '@/app/services/api';
import { Button } from '@/app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/app/components/ui/dialog';

type ParsedQAPair = {
  prompt: string;
  response: string;
};

function extractPromptResponsePairs(stdout?: string): ParsedQAPair[] {
  if (!stdout) return [];

  const lines = stdout.split(/\r?\n/);
  const pairs: ParsedQAPair[] = [];
  let currentPrompt: string | null = null;
  let currentResponse: string | null = null;

  const flushCurrentPair = () => {
    if (!currentPrompt) return;
    pairs.push({
      prompt: currentPrompt,
      response: currentResponse || '(no response captured in output)',
    });
    currentPrompt = null;
    currentResponse = null;
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;

    if (line.startsWith('Prompt:')) {
      flushCurrentPair();
      currentPrompt = line.replace('Prompt:', '').trim();
      continue;
    }

    if (line.startsWith('Response:')) {
      currentResponse = line.replace('Response:', '').trim();
      continue;
    }

    if (line.startsWith('Score:') || line.startsWith('Time:') || line.startsWith('Error:')) {
      flushCurrentPair();
      continue;
    }

    if (currentResponse) {
      currentResponse = `${currentResponse} ${line}`.trim();
    }
  }

  flushCurrentPair();
  return pairs;
}

function formatDuration(duration: number): string {
  return duration >= 1000
    ? `${(duration / 1000).toFixed(1)}s`
    : `${duration.toFixed(0)}ms`;
}

function statusBadgeClass(status: string): string {
  if (status === 'passed') return 'bg-green-100 text-green-900 border-green-300';
  if (status === 'timeout') return 'bg-amber-100 text-amber-900 border-amber-300';
  return 'bg-red-100 text-red-900 border-red-300';
}

function getPreviewText(text: string, maxChars: number): { text: string; truncated: boolean } {
  if (text.length <= maxChars) {
    return { text, truncated: false };
  }
  return {
    text: text.slice(0, maxChars).trimEnd(),
    truncated: true,
  };
}

export function ResultsViewer() {
  const [results, setResults] = useState<BenchmarkResultFile[]>([]);
  const [selectedResult, setSelectedResult] = useState<BenchmarkSummary | null>(null);
  const [benchmarkStatus, setBenchmarkStatus] = useState<BenchmarkStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedTestDetailIndex, setSelectedTestDetailIndex] = useState<number | null>(null);
  const [expandedQAText, setExpandedQAText] = useState<Record<string, boolean>>({});

  const selectedTestDetail = useMemo(() => {
    if (selectedResult === null || selectedTestDetailIndex === null) {
      return null;
    }
    return selectedResult.test_results?.[selectedTestDetailIndex] || null;
  }, [selectedResult, selectedTestDetailIndex]);

  const parsedQAPairs = useMemo(() => {
    if (selectedTestDetail?.details && selectedTestDetail.details.length > 0) {
      return selectedTestDetail.details.map((item) => ({
        prompt: item.prompt,
        response: item.response,
      }));
    }

    return extractPromptResponsePairs(selectedTestDetail?.stdout);
  }, [selectedTestDetail]);

  useEffect(() => {
    fetchResults();
    fetchBenchmarkStatus();

    // Auto-refresh when benchmarks/tests complete
    const onComplete = () => {
      fetchResults();
      fetchBenchmarkStatus();
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
      fetchBenchmarkStatus();
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

  const fetchBenchmarkStatus = async () => {
    try {
      const status = await api.getBenchmarkStatus();
      setBenchmarkStatus(status);
    } catch {
      // Status unavailable
    }
  };

  const viewResult = async (filename: string) => {
    try {
      const result = await api.getBenchmarkResult(filename);
      setSelectedResult(result);
      setExpandedQAText({});
    } catch {
      // Failed to load
    }
  };

  const toggleExpandedQAText = (key: string) => {
    setExpandedQAText((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
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
                      {result.test_results.filter((t: { status: string }) => t.status === 'passed').length}/{result.test_results.length} passed
                    </span>
                  )}
                  {(!result.test_results || result.test_results.length === 0) && (
                    <span className="text-xs font-mono px-2 py-1 rounded bg-gray-200 text-gray-700">
                      benchmark-only
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
                    <div className="flex items-center gap-1">
                      <span className="text-xs font-mono text-gray-500">
                        {formatDuration(t.duration)}
                      </span>
                      <Button
                        variant="outline"
                        size="icon"
                        className="h-7 w-7"
                        aria-label={`Open details for ${t.name}`}
                        onClick={() => setSelectedTestDetailIndex(i)}
                      >
                        <MoreHorizontal className="w-4 h-4" />
                      </Button>
                    </div>
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
              {benchmarkStatus?.running ? (
                <>
                  <p className="text-gray-700 text-sm font-medium">Test scripts are still running in background.</p>
                  <p className="text-gray-500 text-xs mt-1">
                    {benchmarkStatus.message || 'Running...'} ({Math.round(benchmarkStatus.progress)}%)
                  </p>
                </>
              ) : (
                <>
                  <p className="text-gray-500 text-sm">No test script results in this file.</p>
                  <p className="text-gray-400 text-xs mt-1">This record is benchmark-only (not a full run-all tests + metrics execution).</p>
                </>
              )}
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

      <Dialog
        open={selectedTestDetail !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedTestDetailIndex(null);
            setExpandedQAText({});
          }
        }}
      >
        <DialogContent className="sm:max-w-5xl max-h-[88vh] overflow-y-auto border-2 border-slate-900 bg-white">
          {selectedTestDetail && (
            <>
              <DialogHeader className="pb-3 border-b border-slate-200">
                <DialogTitle className="text-xl text-slate-900">{selectedTestDetail.name} Details</DialogTitle>
                <DialogDescription className="flex flex-wrap items-center gap-2 pt-1 text-slate-700">
                  <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold ${statusBadgeClass(selectedTestDetail.status)}`}>
                    {selectedTestDetail.status.toUpperCase()}
                  </span>
                  <span className="text-xs font-medium">Duration: {formatDuration(selectedTestDetail.duration)}</span>
                </DialogDescription>
              </DialogHeader>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="rounded-md border-2 border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-600">Status</p>
                  <p className="text-sm font-semibold mt-1 text-slate-900">{selectedTestDetail.status}</p>
                </div>
                <div className="rounded-md border-2 border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-600">Duration</p>
                  <p className="text-sm font-semibold mt-1 text-slate-900">{formatDuration(selectedTestDetail.duration)}</p>
                </div>
                <div className="rounded-md border-2 border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-600">Captured Logs</p>
                  <p className="text-sm font-semibold mt-1 text-slate-900">
                    {(selectedTestDetail.stdout?.length || 0).toLocaleString()} chars
                  </p>
                </div>
              </div>

              {parsedQAPairs.length > 0 && (
                <div className="space-y-2 rounded-md border-2 border-slate-200 bg-slate-50 p-3">
                  <h5 className="text-sm font-semibold text-slate-900">Detected Test Questions and Answers</h5>
                  <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                    {parsedQAPairs.map((pair, idx) => {
                      const questionKey = `qa-${idx}-question`;
                      const answerKey = `qa-${idx}-answer`;
                      const questionExpanded = expandedQAText[questionKey] ?? false;
                      const answerExpanded = expandedQAText[answerKey] ?? false;
                      const questionPreview = getPreviewText(pair.prompt, 140);
                      const answerPreview = getPreviewText(pair.response, 220);

                      return (
                        <div key={idx} className="rounded-md border border-slate-300 p-3 bg-white shadow-sm">
                          <p className="text-xs font-semibold text-slate-600 uppercase mb-1 tracking-wide">
                            Question {idx + 1}
                          </p>
                          <p className="text-sm text-slate-900 mb-2 whitespace-pre-wrap break-words overflow-visible text-clip">
                            {questionExpanded || !questionPreview.truncated ? pair.prompt : questionPreview.text}
                            {questionPreview.truncated && !questionExpanded && (
                              <button
                                type="button"
                                onClick={() => toggleExpandedQAText(questionKey)}
                                className="ml-1 inline text-blue-700 hover:text-blue-900 font-semibold"
                                aria-label={`Show full question ${idx + 1}`}
                              >
                                ...
                              </button>
                            )}
                            {questionPreview.truncated && questionExpanded && (
                              <button
                                type="button"
                                onClick={() => toggleExpandedQAText(questionKey)}
                                className="ml-2 inline text-xs text-slate-600 hover:text-slate-900 underline"
                                aria-label={`Show compact question ${idx + 1}`}
                              >
                                show less
                              </button>
                            )}
                          </p>

                          <p className="text-xs font-semibold text-slate-600 uppercase mb-1 tracking-wide">Answer</p>
                          <p className="text-sm text-slate-800 whitespace-pre-wrap break-words overflow-visible text-clip">
                            {answerExpanded || !answerPreview.truncated ? pair.response : answerPreview.text}
                            {answerPreview.truncated && !answerExpanded && (
                              <button
                                type="button"
                                onClick={() => toggleExpandedQAText(answerKey)}
                                className="ml-1 inline text-blue-700 hover:text-blue-900 font-semibold"
                                aria-label={`Show full answer ${idx + 1}`}
                              >
                                ...
                              </button>
                            )}
                            {answerPreview.truncated && answerExpanded && (
                              <button
                                type="button"
                                onClick={() => toggleExpandedQAText(answerKey)}
                                className="ml-2 inline text-xs text-slate-600 hover:text-slate-900 underline"
                                aria-label={`Show compact answer ${idx + 1}`}
                              >
                                show less
                              </button>
                            )}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="space-y-3">
                <details open>
                  <summary className="text-sm font-semibold cursor-pointer text-slate-900">Raw stdout</summary>
                  <pre className="mt-2 text-xs bg-slate-950 text-slate-100 border border-slate-800 rounded p-3 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                    {selectedTestDetail.stdout?.trim() || 'No stdout output.'}
                  </pre>
                </details>
                <details open={Boolean(selectedTestDetail.stderr)}>
                  <summary className="text-sm font-semibold cursor-pointer text-slate-900">Raw stderr</summary>
                  <pre className="mt-2 text-xs bg-red-950 text-red-100 border border-red-700 rounded p-3 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                    {selectedTestDetail.stderr?.trim() || 'No stderr output.'}
                  </pre>
                </details>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
