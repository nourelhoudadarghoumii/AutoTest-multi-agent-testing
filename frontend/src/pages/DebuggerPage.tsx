import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Bot, CheckCircle2, XCircle, Search, Wrench, RotateCcw, Gauge, ShieldQuestion,
} from 'lucide-react';
import { projectService, runService, apiErrorMessage } from '../services/api';
import type { DebugHistoryEntry, FinalReport, Project, RunStatus } from '../types';
import RunHeader from '../components/RunHeader';
import { MetricCard, StatBlock } from '../components/Metric';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';

const CONFIDENCE_STYLES: Record<string, string> = {
  high: 'badge-success',
  medium: 'badge-warning',
  low: 'badge-danger',
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: 'confiance : élevée',
  medium: 'confiance : moyenne',
  low: 'confiance : faible',
};

/** One debugger iteration, rendered as an engineering log entry. */
function DebugEntry({ entry }: { entry: DebugHistoryEntry }) {
  return (
    <div className="relative pl-10 pb-7">
      {/* connector */}
      <div className="absolute left-[15px] top-8 bottom-0 w-px bg-slate2-200" />

      {/* iteration marker */}
      <div
        className={`absolute left-0 top-0 w-8 h-8 rounded-full flex items-center justify-center border ${
          entry.applied
            ? 'bg-success-50 border-success-200'
            : 'bg-white border-slate2-200'
        }`}
      >
        {entry.applied ? (
          <Wrench size={14} className="text-success-600" />
        ) : (
          <XCircle size={14} className="text-slate2-400" />
        )}
      </div>

      <div className="card p-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="font-mono text-sm font-semibold text-slate2-900">{entry.test_name}</span>
              <span className="badge badge-neutral text-[10px] font-mono">{entry.error_type || 'Inconnu'}</span>
              <span className={`badge ${CONFIDENCE_STYLES[entry.confidence] ?? 'badge-neutral'} text-[10px]`}>
                {CONFIDENCE_LABELS[entry.confidence] ?? `confiance : ${entry.confidence}`}
              </span>
            </div>
            <p className="text-[11px] font-mono text-slate2-400 mt-1">itération {entry.iteration}</p>
          </div>
          <span className={`badge ${entry.applied ? 'badge-success' : 'badge-danger'} text-[11px]`}>
            {entry.applied ? 'correctif appliqué' : 'non réparé'}
          </span>
        </div>

        <div className="mt-3 space-y-2.5">
          <div className="flex items-start gap-2.5">
            <Search size={13} className="text-cap-500 mt-0.5 shrink-0" />
            <div>
              <p className="text-[11px] font-semibold text-slate2-500 uppercase tracking-wider">Cause racine</p>
              <p className="text-sm text-slate2-700 leading-relaxed mt-0.5">{entry.root_cause || '—'}</p>
            </div>
          </div>
          {entry.fix_description && (
            <div className="flex items-start gap-2.5">
              <Wrench size={13} className="text-success-600 mt-0.5 shrink-0" />
              <div>
                <p className="text-[11px] font-semibold text-slate2-500 uppercase tracking-wider">Correctif</p>
                <p className="text-sm text-slate2-700 leading-relaxed mt-0.5">{entry.fix_description}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DebuggerPage() {
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
      setError(apiErrorMessage(err, 'Impossible de charger les données de débogage.'));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingSpinner message="Chargement de l'historique de débogage" />;

  if (error) return <ErrorState title="Données de débogage indisponibles" message={error} onRetry={load} />;

  const history = report?.debug_history ?? [];

  return (
    <div>
      <RunHeader runId={runId!} projectId={run?.project_id ?? ''} projectName={project?.name} status={run?.status} activeTab="/debugger" />

      {run?.status !== 'completed' ? (
        <EmptyState
          icon={RotateCcw}
          title="Les données apparaîtront à la fin de la session"
          description="Le débogueur intervient entre les cycles d'exécution. Une fois le pipeline terminé, chaque diagnostic et réparation sera répertorié ici."
        />
      ) : history.length === 0 ? (
        <div className="card py-10 text-center animate-fade-up">
          <div className="w-14 h-14 bg-success-50 border border-success-200 rounded-lg flex items-center justify-center mx-auto mb-4">
            <CheckCircle2 size={26} className="text-success-600" />
          </div>
          <h3 className="text-base font-semibold text-slate2-900">Aucun débogage requis</h3>
          <p className="text-sm text-slate2-500 mt-1.5 max-w-md mx-auto leading-relaxed">
            Tous les tests générés ont réussi dès le premier essai. Le débogueur s'active uniquement en cas d'échec.
          </p>
        </div>
      ) : (
        <div className="animate-fade-up space-y-6">
          {/* Iteration summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard icon={Bot} label="Itérations Utilisées" value={`${report!.debug_iterations} / 3`} sub="plafond strict du pipeline" tone="dark" />
            <MetricCard icon={ShieldQuestion} label="Échecs Traités" value={history.length} />
            <MetricCard
              icon={Wrench}
              label="Correctifs Appliqués"
              value={history.filter((d) => d.applied).length}
              tone={history.some((d) => d.applied) ? 'success' : 'default'}
            />
            <MetricCard
              icon={Gauge}
              label="Résultat Final"
              value={report!.failed === 0 ? 'RÉSOLU' : 'NON RÉSOLU'}
              tone={report!.failed === 0 ? 'success' : 'danger'}
              sub={report!.failed === 0 ? 'tous les tests passent' : `${report!.failed} encore en échec`}
            />
          </div>

          {/* Timeline */}
          <div>
            <h3 className="text-sm font-bold text-slate2-900 uppercase tracking-wider mb-5 flex items-center gap-2">
              <Bot size={15} className="text-cap-500" />
              Chronologie du Débogage Autonome
            </h3>
            <div>
              {history
                .slice()
                .sort((a, b) => a.iteration - b.iteration)
                .map((entry, idx) => (
                  <DebugEntry key={`${entry.test_name}-${idx}`} entry={entry} />
                ))}
            </div>
          </div>

          {/* How it works */}
          <div className="card">
            <h4 className="text-xs font-bold text-slate2-600 uppercase tracking-wider mb-3">Fonctionnement du débogueur autonome</h4>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs text-slate2-600">
              {[
                ['1 · Détection', 'Les échecs pytest sont extraits avec type d\'erreur, message et trace'],
                ['2 · Diagnostic', 'Le modèle de débogage confronte le test défaillant au code source réel'],
                ['3 · Réparation', 'Un patch exclusif au test est proposé — le code de production n\'est jamais altéré'],
                ['4 · Validation', 'Le patch doit valider l\'AST et réussir pytest avant d\'être intégré'],
              ].map(([title, body]) => (
                <div key={title} className="bg-slate2-50 border border-slate2-200 rounded-md p-3">
                  <p className="font-mono font-semibold text-cap-700 mb-1">{title}</p>
                  <p className="leading-relaxed">{body}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Aggregated debug report */}
          {report!.generation && (
            <div className="card p-0 overflow-hidden">
              <div className="px-5 py-3.5 border-b border-slate2-200 bg-slate2-50">
                <h4 className="text-xs font-bold text-slate2-700 uppercase tracking-wider">Bilan Global du Débogage</h4>
              </div>
              <div className="px-5 py-4 grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatBlock label="Causes Racines Identifiées" value={history.filter((h) => h.root_cause).length} />
                <StatBlock label="Correctifs Haute Confiance" value={history.filter((h) => h.confidence === 'high' && h.applied).length} />
                <StatBlock label="Générations Échouées" value={report!.generation.functions_failed.length} />
                <StatBlock label="Triviales Ignorées" value={report!.generation.functions_skipped.length} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
