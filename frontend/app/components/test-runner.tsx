import { useState, useEffect } from "react";
import { Play, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { Progress } from "@/app/components/ui/progress";
import { Checkbox } from "@/app/components/ui/checkbox";
import { api } from "@/app/services/api";

interface TestItem {
  id: string;
  name: string;
  status: "pending" | "running" | "passed" | "failed";
  duration?: number;
  selected: boolean;
}

interface TestRunnerProps {
  model: string;
  technology: string;
}

export function TestRunner({ model, technology }: TestRunnerProps) {
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [tests, setTests] = useState<TestItem[]>([]);

  // Fetch tests from backend on mount
  useEffect(() => {
    api
      .getTests()
      .then((backendTests) => {
        setTests(backendTests.map((t) => ({ ...t, selected: false })));
      })
      .catch(() => {
        // Fallback to hardcoded list if backend unavailable
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

  const toggleTest = (id: string) => {
    setTests((prev) =>
      prev.map((t) => (t.id === id ? { ...t, selected: !t.selected } : t)),
    );
  };

  const runTests = async () => {
    const selectedTests = tests.filter((t) => t.selected);
    if (selectedTests.length === 0) return;

    setIsRunning(true);
    setProgress(0);

    for (let i = 0; i < selectedTests.length; i++) {
      const testId = selectedTests[i].id;

      // Update test to running
      setTests((prev) =>
        prev.map((t) =>
          t.id === testId ? { ...t, status: "running" as const } : t,
        ),
      );

      // Call backend API to run the test
      let passed = false;
      let duration = 0;
      try {
        const results = await api.runTests([testId], model, technology);
        passed = results?.[0]?.status === "passed";
        duration = results?.[0]?.duration || 0;
      } catch {
        passed = false;
      }
      setTests((prev) =>
        prev.map((t) =>
          t.id === testId
            ? {
                ...t,
                status: passed ? ("passed" as const) : ("failed" as const),
                duration,
              }
            : t,
        ),
      );

      setProgress(((i + 1) / selectedTests.length) * 100);
    }

    setIsRunning(false);
  };

  const resetTests = () => {
    setTests(
      tests.map((t) => ({
        ...t,
        status: "pending" as const,
        duration: undefined,
      })),
    );
    setProgress(0);
  };

  const getIcon = (status: TestItem["status"]) => {
    switch (status) {
      case "running":
        return <Loader2 className="w-4 h-4 animate-spin text-black" />;
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

  const selectedCount = tests.filter((t) => t.selected).length;

  return (
    <div className="border rounded-lg p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-medium">Test Suite ({tests.length} tests)</h3>
        <div className="flex gap-2">
          <Button
            onClick={runTests}
            disabled={isRunning || selectedCount === 0}
            variant="outline"
            size="sm"
          >
            <Play className="w-4 h-4 mr-2" />
            Run Tests ({selectedCount})
          </Button>
          {progress > 0 && (
            <Button
              onClick={resetTests}
              disabled={isRunning}
              variant="outline"
              size="sm"
            >
              Reset
            </Button>
          )}
        </div>
      </div>

      {progress > 0 && (
        <div>
          <Progress value={progress} className="h-2" />
          <p className="text-xs text-gray-500 mt-1">
            {Math.round(progress)}% Complete
          </p>
        </div>
      )}

      <div className="space-y-2 max-h-96 overflow-y-auto">
        {tests.map((test) => (
          <div
            key={test.id}
            className="flex items-center justify-between p-3 bg-gray-50 rounded"
          >
            <div className="flex items-center gap-3">
              <Checkbox
                checked={test.selected}
                onCheckedChange={() => toggleTest(test.id)}
                disabled={isRunning}
              />
              {getIcon(test.status)}
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
    </div>
  );
}
