import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface MetricsChartProps {
  data: Array<{
    time: string;
    container: number;
    vm: number;
  }>;
  metric: string;
}

export function MetricsChart({ data, metric }: MetricsChartProps) {
  return (
    <div className="border rounded-lg p-6">
      <h3 className="font-medium mb-4">{metric}</h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="time" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip />
          <Legend />
          <Line
            type="monotone"
            dataKey="container"
            stroke="#000000"
            strokeWidth={2}
            name="Container"
          />
          <Line
            type="monotone"
            dataKey="vm"
            stroke="#9ca3af"
            strokeWidth={2}
            name="VM"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
