import type { LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  to?: string;
  actionLabel?: string;
}

export default function EmptyState({ icon: Icon, title, description, to, actionLabel }: EmptyStateProps) {
  return (
    <div className="text-center py-14 px-6 border border-dashed border-slate2-300 rounded-lg bg-slate2-50/60">
      <div className="w-14 h-14 bg-white border border-slate2-200 rounded-lg flex items-center justify-center mx-auto mb-4 shadow-card">
        <Icon className="text-slate2-400" size={26} />
      </div>
      <h3 className="text-base font-semibold text-slate2-900 mb-1.5">{title}</h3>
      <p className="text-sm text-slate2-500 mb-5 max-w-sm mx-auto leading-relaxed">{description}</p>
      {to && actionLabel && (
        <Link to={to} className="btn-primary text-sm">
          {actionLabel}
        </Link>
      )}
    </div>
  );
}
