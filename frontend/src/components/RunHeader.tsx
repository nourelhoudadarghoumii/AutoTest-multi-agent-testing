import { Link, NavLink } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import StatusBadge from './StatusBadge';

const RUN_TABS = [
  { path: '', label: 'Exécution des Tests', end: true },
  { path: '/tests', label: 'Tests Générés' },
  { path: '/debugger', label: 'Débogage & Correctifs' },
  { path: '/quality', label: 'Qualité & Risques' },
  { path: '/report', label: 'Rapport Décisionnel' },
];

interface RunHeaderProps {
  runId: string;
  projectId: string;
  projectName?: string;
  status?: string;
  activeTab: string;
}

export default function RunHeader({ runId, projectId, projectName, status, activeTab }: RunHeaderProps) {
  return (
    <div className="mb-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 text-xs text-slate2-500 font-mono mb-3">
        <Link to="/projects" className="hover:text-cap-600">Projets</Link>
        <ChevronRight size={12} />
        {projectName ? (
          <Link to={`/projects/${projectId}`} className="hover:text-cap-600 truncate max-w-[220px]">
            {projectName}
          </Link>
        ) : (
          <Link to={`/projects/${projectId}`} className="hover:text-cap-600 font-mono">
            {projectId.substring(0, 8)}
          </Link>
        )}
        <ChevronRight size={12} />
        <span className="text-slate2-700">session {runId.substring(0, 8)}</span>
      </div>

      {/* Title row */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate2-900">
            {RUN_TABS.find((t) => t.path === activeTab)?.label ?? 'Session'}
          </h1>
          <div className="flex items-center gap-3 mt-2">
            {status && <StatusBadge status={status} />}
            <span className="text-xs font-mono text-slate2-400">{runId}</span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mt-5 border-b border-slate2-200 -mb-px overflow-x-auto">
        {RUN_TABS.map((tab) => {
          const to = tab.path === '' ? `/runs/${runId}/results` : `/runs/${runId}${tab.path}`;
          const active = tab.path === activeTab || (tab.path === '' && activeTab === '');
          return (
            <NavLink
              key={tab.path}
              to={to}
              end={tab.end}
              className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                active
                  ? 'border-cap-500 text-cap-700'
                  : 'border-transparent text-slate2-500 hover:text-slate2-800 hover:border-slate2-300'
              }`}
            >
              {tab.label}
            </NavLink>
          );
        })}
      </div>
    </div>
  );
}
