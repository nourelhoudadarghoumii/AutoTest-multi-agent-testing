import { useEffect, useState } from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { FlaskConical, FolderOpen, Home, ShieldCheck, ShieldAlert } from 'lucide-react';
import { systemService } from '../services/api';
import type { Health } from '../types';

const NAV_ITEMS = [
  { path: '/', icon: Home, label: 'Espace de Travail', hint: 'Vue globale & accueil' },
  { path: '/projects', icon: FolderOpen, label: 'Projets', hint: 'Code & sessions de tests' },
];

export default function Layout() {
  const location = useLocation();
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    systemService.getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  const isActive = (path: string) =>
    path === '/' ? location.pathname === '/' : location.pathname.startsWith(path);

  return (
    <div className="min-h-screen flex bg-slate2-50">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 h-full w-60 bg-cap-950 dark-grid border-r border-cap-900 z-40 flex flex-col">
        {/* Brand */}
        <Link to="/" className="block p-5 border-b border-cap-900 group">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-cap-900 border border-cap-700 rounded-md flex items-center justify-center shadow-inner group-hover:border-cap-500 transition-colors">
              <FlaskConical className="text-cap-300" size={22} />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight leading-none">AutoTest</h1>
              <p className="text-[10px] text-cap-400/80 font-mono tracking-widest uppercase mt-1">
                Tests & Audit Qualité
              </p>
            </div>
          </div>
        </Link>

        {/* Navigation */}
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto dark-scrollbar">
          <p className="text-[10px] font-mono text-cap-500/80 mb-2 px-3 uppercase tracking-widest">
            Ingénierie
          </p>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md transition-all text-sm ${
                  active
                    ? 'bg-cap-800/80 text-white font-medium border border-cap-700/60'
                    : 'text-slate2-400 hover:bg-cap-900/70 hover:text-slate2-200 border border-transparent'
                }`}
              >
                <Icon size={17} className={active ? 'text-cap-300' : 'text-slate2-500'} />
                <div>
                  <div>{item.label}</div>
                  <div className={`text-[10px] font-mono ${active ? 'text-cap-400/80' : 'text-slate2-600'}`}>
                    {item.hint}
                  </div>
                </div>
              </Link>
            );
          })}
        </nav>

        {/* System status */}
        <div className="p-4 border-t border-cap-900">
          {health ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                {health.llm_configured ? (
                  <ShieldCheck size={14} className="text-success-400" />
                ) : (
                  <ShieldAlert size={14} className="text-warning-400" />
                )}
                <span className="text-[11px] font-mono text-slate2-400">
                  {health.llm_configured ? 'Service IA Actif' : 'Configuration requise'}
                </span>
              </div>
              <div className="text-[10px] font-mono text-slate2-600">
                Serveur v{health.version}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-danger-500 animate-pulse" />
              <span className="text-[11px] font-mono text-slate2-500">serveur hors ligne</span>
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 ml-60 min-h-screen flex flex-col">
        <div className="flex-1 p-8 max-w-7xl w-full mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
