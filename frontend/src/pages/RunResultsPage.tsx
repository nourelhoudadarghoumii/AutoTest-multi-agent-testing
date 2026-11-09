import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  CheckCircle2, XCircle, SkipForward, Gauge, FileCode2, AlertCircle,
  ShieldAlert, Bot,
} from 'lucide-react';
import { projectService, runService, apiErrorMessage } from '../services/api';
import type { FinalReport, Project, RunStatus } from '../types';
import RunHeader from '../components/RunHeader';
import { MetricCard, MetricBar, StatBlock } from '../components/Metric';
import StatusBadge from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';

export default function RunResultsPage() {
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
      try {
        const projData = await projectService.getProject(runData.project_id);
        setProject(projData);
      } catch {
        setProject(null);
      }
      if (runData.status === 'completed') {
        setReport(await runService.getReport(runId));
      } else {
        setReport(null);
      }
    } catch (err) {
      setError(apiErrorMessage(err, 'Impossible de charger cette session.'));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingSpinner message="Chargement des résultats de la session" />;

  if (error) return <ErrorState title="Session indisponible" message={error} onRetry={load} />;

  if (!run) return <EmptyState icon={AlertCircle} title="Session introuvable" description="Cette session n'existe pas ou a été supprimée." to="/projects" actionLabel="Retour aux projets" />;

  // Run not finished yet → point the engineer at the live view
  if (run.status !== 'completed' && !report) {
    const failedEarly = run.status === 'failed';
    return (
      <div>
        <RunHeader runId={runId!} projectId={run.project_id} projectName={project?.name} status={run.status} activeTab="" />
        <div className="card">
          {failedEarly ? (
            <>
              <h2 className="font-semibold text-danger-700 flex items-center gap-2">
                <ShieldAlert size={18} />
                Le pipeline a échoué avant de générer le rapport
              </h2>
              <p className="text-sm text-slate2-600 mt-3">Détail de l'erreur :</p>
              <pre className="panel dark-scrollbar mt-2 p-4 rounded-md text-xs font-mono text-danger-300 whitespace-pre-wrap max-h-72 overflow-auto">
                {run.error || 'Erreur inconnue.'}
              </pre>
            </>
          ) : (
            <>
              <h2 className="font-semibold text-slate2-900">Cette session est toujours en cours d'exécution</h2>
              <p className="text-sm text-slate2-500 mt-2 font-mono">{run.progress}</p>
            </>
          )}
          <a href={`/runs/${runId}/progress`} className="btn-primary mt-5 text-sm">Ouvrir le suivi en direct</a>
        </div>
      </div>
    );
  }

  const exec = {
    total: report!.total_tests,
    passed: report!.passed,
    failed: report!.failed,
    skipped: report!.skipped ?? 0,
    coverage: report!.coverage_percent,
    duration: null as number | null,
    failedNames: report!.generation?.failed_tests ?? [],
  };
  const errors = Math.max(0, exec.total - exec.passed - exec.failed - exec.skipped);

  return (
    <div>
      <RunHeader runId={runId!} projectId={run.project_id} projectName={project?.name} status={run.status} activeTab="" />

      <div className="space-y-6 animate-fade-up">
        {/* Headline metrics */}
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          <MetricCard icon={FileCode2} label="Tests Exécutés" value={exec.total} tone="dark" />
          <MetricCard icon={CheckCircle2} label="Réussis" value={exec.passed} tone="success" />
          <MetricCard icon={XCircle} label="Échoués" value={exec.failed} tone={exec.failed > 0 ? 'danger' : 'default'} />
          <MetricCard icon={AlertCircle} label="Erreurs" value={errors} tone={errors > 0 ? 'danger' : 'default'} />
          <MetricCard icon={SkipForward} label="Ignorés" value={exec.skipped} />
          <MetricCard icon={Gauge} label="Couverture" value={`${exec.coverage}%`} tone="primary" sub="cible 80%" />
        </div>

        {/* Pass rate + risk */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="card lg:col-span-2 space-y-5">
            <h3 className="text-sm font-bold text-slate2-900 uppercase tracking-wider">Résultat de la Suite</h3>
            <MetricBar label="Taux de réussite" value={exec.total > 0 ? Math.round((exec.passed / exec.total) * 100) : 0} threshold={100} />
            <MetricBar label="Couverture de code" value={exec.coverage} threshold={80} />
            <div className="grid grid-cols-3 gap-4 pt-2 border-t border-slate2-100">
              <StatBlock label="Itérations Débogueur" value={report!.debug_iterations} />
              <StatBlock label="Correctifs Appliqués" value={report!.debug_history?.filter((d) => d.applied).length ?? 0} />
              <StatBlock
                label="Niveau de Risque"
                value={
                  report!.risk_level === 'low' ? 'FAIBLE' :
                  report!.risk_level === 'medium' ? 'MOYEN' : 'ÉLEVÉ'
                }
                tone={report!.risk_level === 'low' ? 'text-success-600' : report!.risk_level === 'medium' ? 'text-warning-600' : 'text-danger-600'}
              />
            </div>
          </div>

          <div className="card panel">
            <h3 className="text-sm font-bold text-cap-300 uppercase tracking-wider mb-3">Débogage Automatisé</h3>
            <p className="text-slate2-300 text-sm leading-relaxed">
              {report!.debug_history && report!.debug_history.length > 0 ? (
                <>
                  Le débogueur a traité <span className="text-white font-semibold">{report!.debug_history.length}</span> échec(s)
                  sur {report!.debug_iterations} itération(s).
                </>
              ) : (
                <>Tous les tests générés ont réussi dès la première exécution — aucun débogage nécessaire.</>
              )}
            </p>
            <a href={`/runs/${runId}/debugger`} className="inline-flex items-center gap-1.5 text-xs text-cap-300 hover:text-accent-400 mt-4 font-medium">
              <Bot size={13} />
              Voir l'historique de débogage
            </a>
          </div>
        </div>

        {/* Failures detail */}
        <div className="card p-0 overflow-hidden">
          <div className="px-5 py-3.5 border-b border-slate2-200 bg-slate2-50 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate2-800 uppercase tracking-wider flex items-center gap-2">
              <XCircle size={15} className={exec.failed > 0 ? 'text-danger-500' : 'text-success-500'} />
              Échecs
            </h3>
            <span className="text-xs font-mono text-slate2-400">{exec.failedNames.length} test(s) en échec</span>
          </div>

          {exec.failedNames.length === 0 ? (
            <div className="px-5 py-6 flex items-center gap-3">
              <CheckCircle2 size={18} className="text-success-500" />
              <p className="text-sm text-slate2-600">Tous les tests générés ont réussi. Aucun échec à signaler.</p>
            </div>
          ) : (
            <div className="divide-y divide-slate2-100">
              {exec.failedNames.map((name) => (
                <div key={name} className="px-5 py-3 flex items-center justify-between hover:bg-danger-50/40">
                  <span className="font-mono text-sm text-slate2-800">{name}</span>
                  <StatusBadge status="failed" size="sm" />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Raw pytest output */}
        {report!.generation && (
          <details className="card p-0 overflow-hidden group">
            <summary className="px-5 py-3.5 cursor-pointer select-none text-sm font-bold text-slate2-800 uppercase tracking-wider hover:bg-slate2-50 flex items-center justify-between">
              <span>Détails de Génération & Validation</span>
              <span className="text-xs font-mono text-slate2-400 font-normal normal-case">
                {report!.generation.tests_generated} tests · {report!.generation.llm_api_calls} appels IA ·{' '}
                {report!.generation.llm_total_tokens.toLocaleString()} jetons
              </span>
            </summary>
            <div className="px-5 py-4 border-t border-slate2-100 grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatBlock label="Validation AST" value={report!.generation.ast_validation_passed ? 'VALIDÉ' : 'ÉCHOUÉ'} tone={report!.generation.ast_validation_passed ? 'text-success-600' : 'text-danger-600'} />
              <StatBlock label="Collecte Pytest" value={report!.generation.pytest_validation_passed ? 'VALIDÉ' : 'ÉCHOUÉ'} tone={report!.generation.pytest_validation_passed ? 'text-success-600' : 'text-danger-600'} />
              <StatBlock label="Taux Réussite IA" value={`${report!.generation.llm_success_rate.toFixed(0)}%`} />
              <StatBlock label="Tentatives IA" value={report!.generation.llm_retries} />
            </div>
            {report!.generation.functions_failed.length > 0 && (
              <div className="px-5 pb-4">
                <p className="label-mono mb-2">Fonctions dont la génération a échoué</p>
                <ul className="space-y-1">
                  {report!.generation.functions_failed.map((f) => (
                    <li key={f} className="text-xs font-mono text-warning-700 bg-warning-50 border border-warning-200 rounded px-2.5 py-1.5">
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </details>
        )}
      </div>
    </div>
  );
}
