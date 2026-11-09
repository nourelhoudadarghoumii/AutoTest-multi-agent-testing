import { AlertTriangle, RefreshCcw } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message: string;
  hint?: string;
  onRetry?: () => void;
}

export default function ErrorState({ title = 'Une erreur est survenue', message, hint, onRetry }: ErrorStateProps) {
  return (
    <div className="border border-danger-200 bg-danger-50 rounded-lg p-6">
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 bg-white border border-danger-200 rounded-lg flex items-center justify-center shrink-0">
          <AlertTriangle className="text-danger-500" size={20} />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-danger-700">{title}</h3>
          <p className="text-sm text-danger-600 mt-1 leading-relaxed break-words">{message}</p>
          {hint && <p className="text-xs text-danger-500/80 mt-2 leading-relaxed">{hint}</p>}
          {onRetry && (
            <button onClick={onRetry} className="btn-secondary mt-4 text-xs py-1.5 inline-flex items-center gap-2">
              <RefreshCcw size={13} />
              Réessayer
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
