type Status =
  | 'completed' | 'success' | 'passed' | 'low'
  | 'running' | 'in_progress' | 'queued' | 'analyzing' | 'generating' | 'executing' | 'debugging' | 'info'
  | 'warning' | 'medium'
  | 'failed' | 'error' | 'high' | 'critical';

interface StatusBadgeProps {
  status: Status | string;
  label?: string;
  size?: 'sm' | 'md';
  showDot?: boolean;
}

const FRENCH_STATUS_LABELS: Record<string, string> = {
  completed: 'Terminé',
  success: 'Succès',
  passed: 'Réussi',
  low: 'Faible',
  running: 'En cours',
  in_progress: 'En cours',
  queued: 'En attente',
  analyzing: 'Analyse',
  generating: 'Génération',
  executing: 'Exécution',
  debugging: 'Débogage',
  info: 'Info',
  warning: 'Attention',
  medium: 'Moyen',
  failed: 'Échoué',
  error: 'Erreur',
  high: 'Élevé',
  critical: 'Critique',
  active: 'Actif',
};

export default function StatusBadge({ status, label, size = 'md', showDot = true }: StatusBadgeProps) {
  const normalized = String(status).toLowerCase();

  const config =
    ['completed', 'success', 'passed', 'low'].includes(normalized)
      ? { cls: 'badge-success', dot: 'bg-success-500' }
      : ['running', 'in_progress', 'queued', 'analyzing', 'generating', 'executing', 'debugging', 'info'].includes(normalized)
      ? { cls: 'badge-info', dot: 'bg-accent-500 animate-pulse' }
      : ['warning', 'medium'].includes(normalized)
      ? { cls: 'badge-warning', dot: 'bg-warning-500' }
      : ['failed', 'error', 'high', 'critical'].includes(normalized)
      ? { cls: 'badge-danger', dot: 'bg-danger-500' }
      : { cls: 'badge-neutral', dot: 'bg-slate2-400' };

  const displayLabel =
    label || FRENCH_STATUS_LABELS[normalized] || String(status).replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());

  const sizeClasses = size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-xs';
  const dotSize = size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2';

  return (
    <span className={`badge ${config.cls} ${sizeClasses} rounded-full`}>
      {showDot && <span className={`${dotSize} ${config.dot} rounded-full`} />}
      {displayLabel}
    </span>
  );
}
