import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Target, AlertTriangle, Wrench, Layers, ArrowUpRight, CheckCircle2,
} from 'lucide-react';
import { projectService, runService, apiErrorMessage } from '../services/api';
import type { FinalReport, Project, RunStatus } from '../types';
import RunHeader from '../components/RunHeader';
import { MetricBar } from '../components/Metric';
import StatusBadge from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';

const URGENCY_BADGE: Record<string, string> = {
  IMMEDIATE: 'badge-danger',
  HIGH: 'badge-warning',
  MEDIUM: 'badge-info',
};

const URGENCY_LABELS: Record<string, string> = {
  IMMEDIATE: 'IMMÉDIAT',
  HIGH: 'ÉLEVÉ',
  MEDIUM: 'MOYEN',
};

export default function QualityPage() {
  const { runId } = useParams<{ runId: string }>();

  const [report, setReport] = useState<FinalReport | null>(null);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const runData = await runService.getRun(runId);
      setRun(runData);
      projectService.getProject(runData.project_id).then(setProject).catch(() => {});
      if (runData.status === 'completed') {
        setReport(await runService.getReport(runId));
      }
    } catch (err) {
      setError(apiErrorMessage(err, 'Impossible de charger les données d\'analyse du code.'));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingSpinner message="Chargement de l'analyse du code et des risques" />;

  if (error) return <ErrorState title="Analyse indisponible" message={error} onRetry={load} />;

  if (run?.status !== 'completed' || !report) {
    return (
      <div>
        <RunHeader runId={runId!} projectId={run?.project_id ?? ''} projectName={project?.name} status={run?.status} activeTab="/quality" />
        <EmptyState
          icon={Target}
          title="Les données d'analyse apparaîtront à la fin de la session"
          description="Les métriques statiques, les points chauds de complexité et les priorités s'afficheront ici."
        />
      </div>
    );
  }

  const effectiveness = report.ml_test_effectiveness;
  const hotspots = report.ml_defect_hotspots ?? [];
  const priorities = report.ml_refactoring_priorities ?? [];
  const analysis = report.analysis;

  return (
    <div>
      <RunHeader runId={runId!} projectId={run.project_id} projectName={project?.name} status={run.status} activeTab="/quality" />

      <div className="animate-fade-up space-y-6">
        {/* Test Suite Health */}
        {effectiveness && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="card lg:col-span-2 space-y-5">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate2-900 uppercase tracking-wider flex items-center gap-2">
                  <Target size={15} className="text-cap-600" />
                  Couverture & Santé des Tests
                </h3>
                <StatusBadge
                  status={
                    effectiveness.rating === 'EXCELLENT' ? 'passed'
                    : effectiveness.rating === 'GOOD' ? 'info'
                    : effectiveness.rating === 'ADEQUATE' ? 'warning' : 'failed'
                  }
                  label={
                    effectiveness.rating === 'EXCELLENT' ? 'EXCELLENT'
                    : effectiveness.rating === 'GOOD' ? 'BON'
                    : effectiveness.rating === 'ADEQUATE' ? 'ADÉQUAT' : 'INSUFFISANT'
                  }
                />
              </div>

              <MetricBar label="Taux de réussite" value={effectiveness.metrics.pass_rate} threshold={100} />
              <MetricBar label="Couverture de code" value={effectiveness.metrics.coverage} threshold={80} />
              <MetricBar
                label="Densité des tests"
                value={Math.round(Math.min(100, (effectiveness.metrics.test_ratio / 3) * 100))}
                suffix=""
                threshold={100}
              />
              <p className="text-xs text-slate2-500 font-mono">
                {effectiveness.metrics.test_ratio} test(s) généré(s) par fonction analysée.
              </p>
            </div>

            <div className="card panel flex flex-col justify-between">
              <div>
                <p className="label-mono text-cap-300">Indice de Qualité des Tests</p>
                <p className="text-5xl font-extrabold font-mono text-white mt-2">
                  {effectiveness.effectiveness_score}
                  <span className="text-lg text-slate2-500 font-bold"> /100</span>
                </p>
                <p className="text-xs text-cap-300/80 mt-3 leading-relaxed">
                  Calculé à partir du taux de réussite, de la couverture des instructions et de la densité des tests.
                </p>
              </div>
              <div className="mt-5 space-y-1.5 border-t border-cap-900 pt-3">
                <p className="text-[10px] uppercase font-mono text-cap-400 font-semibold mb-1">Prochaines étapes recommandées :</p>
                {effectiveness.next_actions.slice(0, 3).map((action) => (
                  <p key={action} className="text-[11px] text-slate2-300 font-mono leading-relaxed flex items-start gap-1.5">
                    <ArrowUpRight size={11} className="text-accent-400 shrink-0 mt-0.5" />
                    <span>{action}</span>
                  </p>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* High-Complexity Functions & Refactoring Priorities */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="card p-0 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-slate2-200 bg-slate2-50 flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate2-800 uppercase tracking-wider flex items-center gap-2">
                <AlertTriangle size={15} className="text-warning-600" />
                Fonctions Critiques (Complexité &gt; Seuil)
              </h3>
              <span className="text-[10px] text-slate2-400 font-mono">Analyse Statique AST</span>
            </div>
            {hotspots.length === 0 ? (
              <div className="p-6 flex items-center gap-3">
                <CheckCircle2 size={18} className="text-success-600" />
                <p className="text-sm text-slate2-600">
                  Aucune fonction à haut risque détectée. La complexité cyclomatique et la taille des fonctions sont dans les seuils sécurisés.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-slate2-100">
                {hotspots.map((h) => (
                  <div key={h.function} className="px-5 py-3.5 hover:bg-slate2-50/70 transition-colors">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <span className="font-mono text-sm font-semibold text-slate2-900">{h.function}</span>
                        <div className="flex items-center gap-3 mt-1 text-[11px] font-mono text-slate2-500">
                          <span className="font-bold text-slate2-700">CC {h.contributing_factors.complexity}</span>
                          <span>{h.contributing_factors.lines} lignes</span>
                          {h.contributing_factors.failed_tests && <span className="text-danger-600 font-semibold">tests en échec</span>}
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <StatusBadge
                          status={h.risk_level === 'CRITICAL' ? 'failed' : 'warning'}
                          label={h.risk_level === 'CRITICAL' ? 'CRITIQUE' : h.risk_level === 'HIGH' ? 'ÉLEVÉ' : 'MOYEN'}
                          size="sm"
                        />
                      </div>
                    </div>
                    <p className="text-xs text-slate2-600 mt-2 leading-relaxed">{h.recommendation}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Refactoring priorities */}
          <div className="card p-0 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-slate2-200 bg-slate2-50 flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate2-800 uppercase tracking-wider flex items-center gap-2">
                <Wrench size={15} className="text-cap-600" />
                Priorités de Refactoring
              </h3>
              <span className="text-[10px] text-slate2-400 font-mono">Classées par Risque</span>
            </div>
            {priorities.length === 0 ? (
              <div className="p-6 flex items-center gap-3">
                <CheckCircle2 size={18} className="text-success-600" />
                <p className="text-sm text-slate2-600">Aucun refactoring immédiat requis — la structure du code est maintenable.</p>
              </div>
            ) : (
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate2-100 bg-slate2-50 text-slate2-600 uppercase font-mono text-[10px]">
                  <tr>
                    <th className="py-2.5 px-4">Composant</th>
                    <th className="py-2.5 px-4">Risque Défaut</th>
                    <th className="py-2.5 px-4">Urgence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate2-100">
                  {priorities.map((p) => (
                    <tr key={p.item} className="hover:bg-slate2-50/70 transition-colors">
                      <td className="py-2.5 px-4 font-mono font-medium text-slate2-900">{p.item}</td>
                      <td className="py-2.5 px-4 font-mono text-slate2-700">{p.defect_risk}</td>
                      <td className="py-2.5 px-4">
                        <span className={`badge ${URGENCY_BADGE[p.urgency] ?? 'badge-neutral'} text-[10px] font-mono uppercase`}>
                          {URGENCY_LABELS[p.urgency] ?? p.urgency}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Code analysis snapshot */}
        {analysis && analysis.files.length > 0 && (
          <div className="card p-0 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-slate2-200 bg-slate2-50 flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate2-800 uppercase tracking-wider flex items-center gap-2">
                <Layers size={15} className="text-cap-600" />
                Structure du Code & Métriques
              </h3>
              <div className="flex items-center gap-4 text-xs font-mono text-slate2-500">
                <span>{analysis.total_files} fichiers</span>
                <span>{analysis.total_functions} fonctions</span>
                <span>{analysis.total_classes} classes</span>
                <span className={analysis.total_risk_zones > 0 ? 'text-warning-600' : 'text-success-600'}>
                  {analysis.total_risk_zones} zone(s) de risque
                </span>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate2-100 bg-slate2-50 text-slate2-600 uppercase font-mono text-[10px]">
                  <tr>
                    <th className="py-2.5 px-4">Fichier</th>
                    <th className="py-2.5 px-4">LOC</th>
                    <th className="py-2.5 px-4">Fonctions</th>
                    <th className="py-2.5 px-4">Classes</th>
                    <th className="py-2.5 px-4">Complexité Moy.</th>
                    <th className="py-2.5 px-4">Zones de Risque</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate2-100">
                  {analysis.files.map((f) => (
                    <tr key={f.name} className="hover:bg-slate2-50/70 transition-colors">
                      <td className="py-2.5 px-4 font-mono font-medium text-slate2-800">{f.name}</td>
                      <td className="py-2.5 px-4 font-mono text-slate2-600">{f.loc}</td>
                      <td className="py-2.5 px-4 font-mono text-slate2-600">{f.functions}</td>
                      <td className="py-2.5 px-4 font-mono text-slate2-600">{f.classes}</td>
                      <td className="py-2.5 px-4 font-mono text-slate2-700 font-semibold">{f.avg_complexity}</td>
                      <td className="py-2.5 px-4">
                        <span className={`badge ${f.risk_zones > 0 ? 'badge-warning' : 'badge-success'} text-[10px] font-mono`}>
                          {f.risk_zones}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {analysis.external_imports.length > 0 && (
              <div className="px-5 py-3 border-t border-slate2-100 bg-slate2-50/50">
                <p className="label-mono mb-2">Dépendances & Modules Externes :</p>
                <div className="flex flex-wrap gap-1.5">
                  {analysis.external_imports.map((mod) => (
                    <span key={mod} className="badge badge-info text-[10px] font-mono">{mod}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
