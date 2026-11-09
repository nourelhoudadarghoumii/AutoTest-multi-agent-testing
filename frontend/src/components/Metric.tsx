import type { LucideIcon } from 'lucide-react';

/** Compact labeled metric with an optional accent. */
export function MetricCard({
  icon: Icon,
  label,
  value,
  sub,
  tone = 'default',
}: {
  icon?: LucideIcon;
  label: string;
  value: string | number | null | undefined;
  sub?: string;
  tone?: 'default' | 'primary' | 'success' | 'danger' | 'warning' | 'dark';
}) {
  const toneClasses: Record<string, string> = {
    default: 'text-slate2-900',
    primary: 'text-cap-600',
    success: 'text-success-600',
    danger: 'text-danger-600',
    warning: 'text-warning-600',
    dark: 'text-cap-300',
  };

  return (
    <div className={`card p-5 ${tone === 'dark' ? 'panel border-cap-900' : ''}`}>
      <div className={`flex items-center gap-2 mb-2 ${tone === 'dark' ? 'text-slate2-400' : 'text-slate2-500'}`}>
        {Icon && (
          <Icon
            size={15}
            className={
              tone === 'dark' ? 'text-cap-400'
              : tone === 'success' ? 'text-success-500'
              : tone === 'danger' ? 'text-danger-500'
              : tone === 'warning' ? 'text-warning-500'
              : tone === 'primary' ? 'text-cap-500'
              : 'text-slate2-400'
            }
          />
        )}
        <span className="label-mono">{label}</span>
      </div>
      <p className={`text-3xl font-bold font-mono tracking-tight ${toneClasses[tone]}`}>
        {value ?? '—'}
      </p>
      {sub && (
        <p className={`text-xs mt-1 ${tone === 'dark' ? 'text-slate2-500' : 'text-slate2-500'}`}>{sub}</p>
      )}
    </div>
  );
}

/** Horizontal bar for 0-100 values. */
export function MetricBar({
  label,
  value,
  suffix = '%',
  threshold,
  invertColor = false,
}: {
  label: string;
  value: number | null | undefined;
  suffix?: string;
  /** Optional target marker (0-100). */
  threshold?: number;
  /** When true, lower values are shown green (e.g. complexity). */
  invertColor?: boolean;
}) {
  const pct = Math.max(0, Math.min(100, value ?? 0));
  const color =
    invertColor
      ? pct <= 60 ? 'bg-success-500' : pct <= 85 ? 'bg-warning-400' : 'bg-danger-500'
      : pct >= 80 ? 'bg-success-500' : pct >= 50 ? 'bg-warning-400' : 'bg-danger-500';

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-sm text-slate2-600">{label}</span>
        <span className="font-mono font-semibold text-slate2-900 text-sm">
          {value != null ? `${value}${suffix}` : '—'}
        </span>
      </div>
      <div className="h-2 bg-slate2-100 rounded-full overflow-hidden relative">
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${pct}%` }} />
        {threshold != null && threshold > 0 && threshold < 100 && (
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-slate2-700/50"
            style={{ left: `${threshold}%` }}
            title={`Target: ${threshold}${suffix}`}
          />
        )}
      </div>
    </div>
  );
}

/** A number with label, used in dense grids. */
export function StatBlock({ label, value, tone = 'text-slate2-900' }: { label: string; value: string | number; tone?: string }) {
  return (
    <div>
      <p className="label-mono mb-1">{label}</p>
      <p className={`text-xl font-bold font-mono ${tone}`}>{value}</p>
    </div>
  );
}
