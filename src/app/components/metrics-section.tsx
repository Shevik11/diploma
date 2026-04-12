import { Download } from 'lucide-react';
import { MetricsChart } from '@/app/components/metrics-chart';
import { Button } from '@/app/components/ui/button';

interface MetricsSectionProps {
  metricsData: Array<{
    time: string;
    cpu: number;
    memory: number;
  }>;
  platform: 'docker' | 'vm';
}

export function MetricsSection({ metricsData, platform }: MetricsSectionProps) {
  const downloadRawData = () => {
    const csvContent = [
      ['Time', 'CPU (%)', 'Memory (%)'].join(','),
      ...metricsData.map(d => [d.time, d.cpu.toFixed(2), d.memory.toFixed(2)].join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `metrics-${platform}-${new Date().toISOString()}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // Convert to the format MetricsChart expects
  const cpuData = metricsData.map(d => ({
    time: d.time,
    container: platform === 'docker' ? d.cpu : 0,
    vm: platform === 'vm' ? d.cpu : 0,
  }));

  const memoryData = metricsData.map(d => ({
    time: d.time,
    container: platform === 'docker' ? d.memory : 0,
    vm: platform === 'vm' ? d.memory : 0,
  }));

  const hasData = metricsData.length > 1;

  return (
    <div className="space-y-6">
      <div className="bg-white border rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-medium">Live Metrics — {platform === 'docker' ? 'Docker' : 'VM'}</h3>
          {hasData && (
            <Button onClick={downloadRawData} variant="outline" size="sm">
              <Download className="w-4 h-4 mr-2" />
              Download CSV
            </Button>
          )}
        </div>
      </div>

      {hasData ? (
        <div className="grid md:grid-cols-2 gap-6">
          <MetricsChart data={cpuData} metric="CPU Usage (%)" />
          <MetricsChart data={memoryData} metric="Memory Usage (%)" />
        </div>
      ) : (
        <div className="border rounded-lg p-12 text-center">
          <p className="text-gray-500">Start a model to see live metrics</p>
        </div>
      )}
    </div>
  );
}
