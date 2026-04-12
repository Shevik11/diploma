import { useState } from 'react';
import { Play, Square, Server, Container } from 'lucide-react';
import { Badge } from '@/app/components/ui/badge';
import { DeploymentState } from '@/app/services/api';

interface DeploymentCardProps {
  type: 'container' | 'vm';
  modelName: string;
  state?: DeploymentState;
  onStart?: () => Promise<void>;
  onStop?: () => Promise<void>;
}

export function DeploymentCard({ type, modelName, state, onStart, onStop }: DeploymentCardProps) {
  const [isLoading, setIsLoading] = useState(false);

  const status = state?.status || 'idle';
  const metrics = {
    cpu: state?.cpu || 0,
    memory: state?.memory || 0,
    latency: state?.latency || 0,
  };

  const handleStart = async () => {
    if (!onStart) return;
    setIsLoading(true);
    try {
      await onStart();
    } finally {
      setIsLoading(false);
    }
  };

  const handleStop = async () => {
    if (!onStop) return;
    setIsLoading(true);
    try {
      await onStop();
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusVariant = () => {
    if (status === 'running') return 'default';
    return 'outline';
  };

  const isPulling = status === 'pulling';

  return (
    <div className="bg-white border rounded-lg p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {type === 'container' ? (
            <div className="p-2 bg-blue-100 rounded-lg">
              <Container className="w-5 h-5 text-blue-600" />
            </div>
          ) : (
            <div className="p-2 bg-purple-100 rounded-lg">
              <Server className="w-5 h-5 text-purple-600" />
            </div>
          )}
          <div>
            <h3 className="font-medium">{type === 'container' ? 'Container' : 'Virtual Machine'}</h3>
            <p className="text-sm text-gray-500">{modelName}</p>
          </div>
        </div>
        <Badge
          variant={getStatusVariant()}
          className={status === 'running' ? 'bg-green-500' : isPulling ? 'bg-amber-100 text-amber-800' : ''}
        >
          {status}
        </Badge>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-500 uppercase">CPU</p>
          <p className="text-lg font-mono font-semibold">{metrics.cpu.toFixed(1)}%</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-500 uppercase">Memory</p>
          <p className="text-lg font-mono font-semibold">{metrics.memory.toFixed(1)}%</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-500 uppercase">Latency</p>
          <p className="text-lg font-mono font-semibold">{metrics.latency.toFixed(0)}ms</p>
        </div>
      </div>

      <div className="flex gap-3">
        <button
          onClick={handleStart}
          disabled={status === 'running' || isPulling || isLoading}
          className="flex-1 px-4 py-2 text-sm font-bold text-black bg-white border-2 border-black rounded-lg shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] hover:translate-x-[2px] hover:translate-y-[2px] active:shadow-none active:translate-x-[3px] active:translate-y-[3px] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] disabled:hover:translate-x-0 disabled:hover:translate-y-0 transition-all duration-100 flex items-center justify-center gap-2"
        >
          <Play className="w-3 h-3" />
          {isPulling ? 'Pulling...' : isLoading && status !== 'running' ? 'Starting...' : 'Start'}
        </button>
        <button
          onClick={handleStop}
          disabled={status !== 'running' || isLoading}
          className="flex-1 px-4 py-2 text-sm font-bold text-black bg-white border-2 border-black rounded-lg shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] hover:shadow-[1px_1px_0px_0px_rgba(0,0,0,1)] hover:translate-x-[2px] hover:translate-y-[2px] active:shadow-none active:translate-x-[3px] active:translate-y-[3px] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] disabled:hover:translate-x-0 disabled:hover:translate-y-0 transition-all duration-100 flex items-center justify-center gap-2"
        >
          <Square className="w-3 h-3" />
          {isLoading && status === 'running' ? 'Stopping...' : 'Stop'}
        </button>
      </div>
    </div>
  );
}
