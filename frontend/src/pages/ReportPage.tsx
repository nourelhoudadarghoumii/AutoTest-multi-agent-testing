import { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  FileCheck2, Download, Package, ShieldCheck, AlertTriangle, Lightbulb,
  CheckCircle2, Gauge, Info, FileCode2, Terminal, ArrowRight, ShieldAlert,
} from 'lucide-react';
import { projectService, runService, apiErrorMessage } from '../services/api';
import type { FinalReport, Project, Recommendation, RunStatus } from '../types';
import RunHeader from '../components/RunHeader';
import { MetricBar } from '../components/Metric';
import StatusBadge from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';

function RecommendationCard({ rec }: { rec: Recommendation }) {
  return (
    <div className="border border-slate2-200 bg-white rounded-lg p-5 hover:border-cap-300 transition-colors shadow-sm">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3 min-w-0">
          <span className="w-8 h-8 rounded-md bg-cap-50 border border-cap-200 flex items-center justify-center font-mono text-xs font-bold text-cap-700 shrink-0">
            P{rec.priority}
          </span>
          <div>
            <h4 className="font-semibold text-slate2-900 text-sm">{rec.title}</h4>
            <p className="text-xs text-slate2-500 mt-0.5">
              {rec.category} · Niveau d'impact : <span className="text-cap-700 font-semibold">{rec.impact.risk_reduction}</span>
            </p>
          </div>
        </div>
      </div>
      <p className="text-sm text-slate2-600 leading-relaxed mt-3">{rec.description}</p>
      {rec.action_steps && rec.action_steps.length > 0 && (
        <div className="mt-3 bg-slate2-50 rounded-md p-3 border border-slate2-100">
          <p className="text-[11px] font-mono uppercase tracking-wider text-slate2-500 mb-1.5 font-semibold">Plan d'action recommandé :</p>
          <ol className="space-y-1">
            {rec.action_steps.map((step) => (
              <li key={step} className="text-xs text-slate2-700 font-mono flex items-start gap-2">
                <span className="text-cap-500 font-bold">▸</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

export default function ReportPage() {
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
      setError(apiErrorMessage(err, 'Impossible de charger le rapport.'));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingSpinner message="Chargement du rapport décisionnel" />;

  if (error) return <ErrorState title="Rapport indisponible" message={error} onRetry={load} />;

  if (run?.status !== 'completed' || !report) {
    return (
      <div>
        <RunHeader runId={runId!} projectId={run?.project_id ?? ''} projectName={project?.name} status={run?.status} activeTab="/report" />
        <EmptyState
          icon={FileCheck2}
          title="Le rapport est généré après l'exécution des tests"
          description="Une fois la suite exécutée, le verdict complet, les écarts de couverture, la complexité du code et les recommandations s'afficheront ici."
        />
      </div>
    );
  }

  const passRate = report.total_tests > 0 ? Math.round((report.passed / report.total_tests) * 100) : 0;
  const coverageGap = Math.max(0, 80 - Math.round(report.coverage_percent));

  // Realistic verdict based on factual outcomes
  const isFailed = report.failed > 0;
  const isCoverageLow = report.coverage_percent < 80;

  const verdictStatus = isFailed ? 'danger' : isCoverageLow ? 'warning' : 'success';
  const verdictTitle = isFailed
    ? 'Action Requise — Échecs de tests détectés'
    : isCoverageLow
    ? 'Écart de Couverture — Attention recommandée avant déploiement'
    : 'Prêt pour Validation — Tous les tests passent & bonne couverture';

  // Real risk functions from AST analysis
  const topRisks = report.analysis?.top_risk_functions ?? [];
  const defectHotspots = report.ml_defect_hotspots ?? [];

  return (
    <div>
      <RunHeader runId={runId!} projectId={run.project_id} projectName={project?.name} status={run.status} activeTab="/report" />

      <div className="animate-fade-up space-y-6">
        {/* Decision & Verdict Banner */}
        <div className={`rounded-xl border px-7 py-6 ${
          verdictStatus === 'success' ? 'bg-success-50 border-success-200'
          : verdictStatus === 'warning' ? 'bg-warning-50 border-warning-200'
          : 'bg-danger-50 border-danger-200'
        }`}>
          <div className="flex items-start justify-between gap-6 flex-wrap">
            <div className="max-w-3xl">
              <div className="flex items-center gap-2 mb-1">
                {verdictStatus === 'success' && <ShieldCheck className="text-success-600" size={18} />}
                {verdictStatus === 'warning' && <AlertTriangle className="text-warning-600" size={18} />}
                {verdictStatus === 'danger' && <ShieldAlert className="text-danger-600" size={18} />}
                <p className="label-mono uppercase tracking-wider text-slate2-600 font-bold">Verdict Technique</p>
              </div>
              <h2 className={`text-2xl font-extrabold tracking-tight ${
                verdictStatus === 'success' ? 'text-success-800'
                : verdictStatus === 'warning' ? 'text-warning-800' : 'text-danger-800'
              }`}>
                {verdictTitle}
              </h2>
              <p className="text-sm text-slate2-700 mt-2 leading-relaxed font-medium">
                {report.summary}
              </p>
            </div>
            <div className="text-right shrink-0 bg-white/70 backdrop-blur-sm p-4 rounded-xl border border-slate2-200 shadow-sm">
              <p className="text-5xl font-extrabold font-mono tracking-tight text-slate2-900">
                {report.quality_score}
                <span className="text-lg text-slate2-400 font-bold">/100</span>
              </p>
              <p className="text-[11px] font-mono text-slate2-500 uppercase tracking-wider mt-1">Indice de Qualité</p>
            </div>
          </div>

          {/* Factual Metrics Strip */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-6 pt-5 border-t border-slate2-200/80">
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-slate2-500">Tests Exécutés</p>
              <p className="text-lg font-bold font-mono text-slate2-900 mt-0.5">{report.total_tests}</p>
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-slate2-500">Taux de Réussite</p>
              <p className={`text-lg font-bold font-mono mt-0.5 ${report.failed === 0 ? 'text-success-700' : 'text-danger-700'}`}>
                {report.passed}/{report.total_tests} ({passRate}%)
              </p>
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-slate2-500">Couverture Lignes</p>
              <p className={`text-lg font-bold font-mono mt-0.5 ${report.coverage_percent >= 80 ? 'text-success-700' : 'text-warning-700'}`}>
                {report.coverage_percent}%
              </p>
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-slate2-500">Complexité Moy. (CC)</p>
              <p className="text-lg font-bold font-mono text-slate2-900 mt-0.5">{report.complexity_avg}</p>
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wider text-slate2-500">Anomalies Code</p>
              <p className="text-lg font-bold font-mono text-slate2-900 mt-0.5">{report.code_smells?.length ?? 0}</p>
            </div>
          </div>
        </div>

        {/* 2-Column Core View */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Quality & Coverage Health */}
          <div className="card lg:col-span-2 space-y-5">
            <h3 className="text-sm font-bold text-slate2-900 uppercase tracking-wider flex items-center gap-2">
              <Gauge size={16} className="text-cap-600" />
              Santé & Qualité Technique
            </h3>
            
            <MetricBar label="Taux de réussite des tests" value={passRate} threshold={100} />
            
            <div>
              <MetricBar label="Couverture de code" value={report.coverage_percent} threshold={80} />
              {coverageGap > 0 ? (
                <p className="text-xs text-warning-700 font-mono mt-1.5 flex items-center gap-1.5">
                  <AlertTriangle size={13} />
                  <span>Écart de couverture de {coverageGap}% pour atteindre le seuil standard (80%).</span>
                </p>
              ) : (
                <p className="text-xs text-success-700 font-mono mt-1.5 flex items-center gap-1.5">
                  <CheckCircle2 size={13} />
                  <span>La couverture atteint ou dépasse le seuil cible.</span>
                </p>
              )}
            </div>

            <MetricBar
              label="Indice de Maîtrise de la Complexité"
              value={Math.max(0, 100 - report.complexity_avg * 10)}
              suffix=""
              invertColor
            />

            <div className="grid grid-cols-3 gap-4 pt-3 border-t border-slate2-100">
              <div>
                <p className="label-mono mb-1">Fonctions Analysées</p>
                <p className="text-lg font-bold font-mono text-slate2-900">{report.analysis?.total_functions ?? 0}</p>
              </div>
              <div>
                <p className="label-mono mb-1">Triviales Ignorées</p>
                <p className="text-lg font-bold font-mono text-slate2-900">{report.skipped ?? 0}</p>
              </div>
              <div>
                <p className="label-mono mb-1">Fichiers de Test</p>
                <p className="text-lg font-bold font-mono text-slate2-900">{report.test_files?.length ?? 0}</p>
              </div>
            </div>
          </div>

          {/* Deliverables & Quick Actions Card */}
          <div className="card flex flex-col justify-between space-y-4">
            <div>
              <h3 className="text-sm font-bold text-slate2-900 uppercase tracking-wider flex items-center gap-2 mb-3">
                <FileCode2 size={16} className="text-cap-600" />
                Livrables & Intégration CI
              </h3>
              <p className="text-xs text-slate2-600 leading-relaxed">
                La suite de tests est compilée et validée avec pytest. Vous pouvez inspecter les fichiers générés ou les télécharger directement pour votre dépôt.
              </p>

              <div className="mt-4 space-y-2">
                <Link
                  to={`/runs/${runId}/tests`}
                  className="w-full flex items-center justify-between p-2.5 rounded-lg border border-slate2-200 hover:border-cap-400 hover:bg-slate2-50 transition-all text-xs font-medium text-slate2-800"
                >
                  <span className="flex items-center gap-2">
                    <FileCode2 size={15} className="text-cap-500" />
                    Examiner les tests générés
                  </span>
                  <ArrowRight size={13} className="text-slate2-400" />
                </Link>

                {report.debug_history && report.debug_history.length > 0 && (
                  <Link
                    to={`/runs/${runId}/debugger`}
                    className="w-full flex items-center justify-between p-2.5 rounded-lg border border-slate2-200 hover:border-cap-400 hover:bg-slate2-50 transition-all text-xs font-medium text-slate2-800"
                  >
                    <span className="flex items-center gap-2">
                      <ShieldCheck size={15} className="text-success-500" />
                      Voir les correctifs appliqués ({report.debug_history.length})
                    </span>
                    <ArrowRight size={13} className="text-slate2-400" />
                  </Link>
                )}
              </div>

              <div className="mt-4 p-3 bg-slate2-900 rounded-lg text-slate2-200 font-mono text-xs">
                <p className="text-slate2-400 text-[10px] uppercase tracking-wider mb-1 flex items-center gap-1.5">
                  <Terminal size={12} /> Exécuter en local :
                </p>
                <p className="text-cap-300">pytest -v tests/</p>
              </div>
            </div>

            <div className="space-y-2 pt-4 border-t border-slate2-100">
              <button
                onClick={() => runService.download(runId!, 'tests')}
                className="btn-primary w-full text-xs py-2 flex items-center justify-center gap-2"
              >
                <Package size={14} />
                Télécharger les tests (.zip)
              </button>
              <button
                onClick={() => runService.download(runId!, 'report-md')}
                className="btn-secondary w-full text-xs py-2 flex items-center justify-center gap-2"
              >
                <Download size={14} />
                Télécharger le rapport technique (.md)
              </button>
            </div>
          </div>
        </div>

        {/* Real Code Risks / High-Complexity Functions */}
        {(topRisks.length > 0 || defectHotspots.length > 0) && (
          <div className="card p-0 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-slate2-200 bg-slate2-50 flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate2-900 uppercase tracking-wider flex items-center gap-2">
                <AlertTriangle size={15} className="text-warning-600" />
                Zones Critiques & Complexité (Analyse AST)
              </h3>
              <span className="text-xs font-mono text-slate2-500">
                {topRisks.length || defectHotspots.length} fonction(s) évaluée(s)
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate2-200 bg-slate2-100/70 text-slate2-600 font-mono uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="py-2.5 px-4">Fonction</th>
                    <th className="py-2.5 px-4">Complexité Cyclomatique (CC)</th>
                    <th className="py-2.5 px-4">Niveau de Risque</th>
                    <th className="py-2.5 px-4">Action Ingénieur Recommandée</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate2-100">
                  {topRisks.map((fn) => {
                    const isHigh = fn.complexity >= 10;
                    return (
                      <tr key={fn.name} className="hover:bg-slate2-50/80 transition-colors">
                        <td className="py-3 px-4 font-mono font-medium text-slate2-900">
                          {fn.name}
                          <span className="block text-[11px] text-slate2-400 font-sans">{fn.file}</span>
                        </td>
                        <td className="py-3 px-4 font-mono font-bold text-slate2-800">
                          {fn.complexity}
                        </td>
                        <td className="py-3 px-4">
                          <StatusBadge
                            status={isHigh ? 'failed' : 'warning'}
                            label={isHigh ? 'Risque Élevé (CC ≥ 10)' : 'Modéré (CC < 10)'}
                            size="sm"
                          />
                        </td>
                        <td className="py-3 px-4 text-slate2-600 leading-relaxed font-sans">
                          {isHigh
                            ? 'Complexité de branchement élevée. Décomposer en sous-fonctions plus simples et tester les cas limites.'
                            : 'S\'assurer que les branches conditionnelles et exceptions disposent de tests unitaires dédiés.'}
                        </td>
                      </tr>
                    );
                  })}
                  {topRisks.length === 0 && defectHotspots.map((h) => (
                    <tr key={h.function} className="hover:bg-slate2-50/80 transition-colors">
                      <td className="py-3 px-4 font-mono font-medium text-slate2-900">{h.function}</td>
                      <td className="py-3 px-4 font-mono font-bold text-slate2-800">{h.contributing_factors.complexity}</td>
                      <td className="py-3 px-4">
                        <StatusBadge
                          status={h.risk_level === 'CRITICAL' ? 'failed' : 'warning'}
                          label={h.risk_level === 'CRITICAL' ? 'CRITIQUE' : 'ÉLEVÉ'}
                          size="sm"
                        />
                      </td>
                      <td className="py-3 px-4 text-slate2-600 leading-relaxed font-sans">{h.recommendation}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Concrete Code Smells */}
        {report.code_smells && report.code_smells.length > 0 && (
          <div className="card p-0 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-slate2-200 bg-slate2-50 flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate2-800 uppercase tracking-wider flex items-center gap-2">
                <AlertTriangle size={15} className="text-warning-500" />
                Anomalies de Code Détectées
              </h3>
              <span className="text-xs font-mono text-slate2-400">{report.code_smells.length} anomalie(s)</span>
            </div>
            <div className="divide-y divide-slate2-100">
              {report.code_smells.slice(0, 10).map((smell, idx) => (
                <div key={`${smell.location}-${idx}`} className="px-5 py-3.5 hover:bg-slate2-50/60 transition-colors">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span className={`badge ${smell.severity === 'critical' || smell.severity === 'high' ? 'badge-danger' : smell.severity === 'medium' ? 'badge-warning' : 'badge-neutral'} text-[10px] uppercase font-mono`}>
                        {smell.severity === 'critical' ? 'CRITIQUE' : smell.severity === 'high' ? 'ÉLEVÉ' : smell.severity === 'medium' ? 'MOYEN' : 'MINEUR'}
                      </span>
                      <span className="text-sm font-semibold text-slate2-800">{smell.type}</span>
                      <span className="font-mono text-xs text-cap-700 bg-cap-50 px-2 py-0.5 rounded border border-cap-200">
                        {smell.location}
                      </span>
                    </div>
                  </div>
                  <p className="text-xs text-slate2-600 mt-1.5 leading-relaxed">{smell.description}</p>
                  <p className="text-xs text-cap-700 mt-1 font-mono font-medium">→ Conseil de refactoring : {smell.suggestion}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Prioritized Engineering Recommendations */}
        <div>
          <h3 className="text-sm font-bold text-slate2-900 uppercase tracking-wider flex items-center gap-2 mb-4">
            <Lightbulb size={16} className="text-warning-500" />
            Plan d'Action Priorisé
          </h3>
          {(!report.recommendations || report.recommendations.length === 0) ? (
            <div className="card flex items-center gap-3">
              <CheckCircle2 size={18} className="text-success-500" />
              <p className="text-sm text-slate2-600">
                Aucune action bloquante requise — cette base de code répond à tous les critères de qualité.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {report.recommendations.map((rec) => (
                <RecommendationCard key={rec.priority} rec={rec} />
              ))}
            </div>
          )}
        </div>

        {/* Transparent Quality Composition Note */}
        <p className="flex items-start gap-2 text-[11px] text-slate2-400 pb-4">
          <Info size={12} className="shrink-0 mt-0.5" />
          L'Indice de Qualité est une mesure objective : 40% taux de réussite, 30% couverture pytest, 20% maîtrise de la complexité et 10% efficacité du débogage. Toutes les données proviennent de pytest et de l'analyse statique AST Python.
        </p>
      </div>
    </div>
  );
}
