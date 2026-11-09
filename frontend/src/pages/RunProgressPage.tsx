import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { TerminalSquare, ArrowRight, AlertCircle, RefreshCcw } from 'lucide-react';
import { runService } from '../services/api';
import type { SSEEvent } from '../types';
import PipelineFlow, { stageForStatus } from '../components/PipelineFlow';
import StatusBadge from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';

export default function RunProgressPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const [run, setRun] = useState<{ status: string; progress: string; project_id?: string } | null>(null);
  const [events, setEvents] = useState<Array<{ time: string; text: string; kind: 'info' | 'done' | 'error' }>>([]);
  const [connectionLost, setConnectionLost] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!runId) return;
    let mounted = true;
    let seenDoneStages = new Set<string>();

    const pushEvent = (text: string, kind: 'info' | 'done' | 'error' = 'info') => {
      const time = new Date().toLocaleTimeString('fr-FR', { hour12: false });
      setEvents((prev) => [...prev, { time, text, kind }]);
    };

    pushEvent(`Connexion à la session ${runId.substring(0, 8)}`);

    runService
      .getRun(runId)
      .then((data) => {
        if (!mounted) return;
        setRun({ status: data.status, progress: data.progress, project_id: data.project_id });
        pushEvent(`Statut : ${data.status} — ${data.progress}`);
      })
      .catch(() => {
        if (mounted) pushEvent('Session introuvable — elle a peut-être été exécutée ailleurs.', 'error');
      });

    const cleanup = runService.streamProgress(
      runId,
      (data: SSEEvent) => {
        if (!mounted) return;
        setRun((prev) => ({
          status: data.status ?? prev?.status ?? 'running',
          progress: data.progress ?? prev?.progress ?? '',
          project_id: prev?.project_id,
        }));

        if (data.progress) pushEvent(data.progress, data.status === 'failed' ? 'error' : 'info');

        const stage = stageForStatus(data.status, data.current_agent);
        if (!seenDoneStages.has(stage)) {
          seenDoneStages.add(stage);
        }

        if (data.status === 'completed') {
          pushEvent(`Pipeline terminé avec succès — Qualité : ${data.quality_score ?? '—'}/100, Couverture : ${data.coverage ?? '—'}%`, 'done');
        }
        if (data.status === 'failed' && data.error) {
          pushEvent(`Échec du pipeline : ${data.error}`, 'error');
        }
      },
      () => {
        if (mounted) setConnectionLost(true);
      }
    );

    return () => {
      mounted = false;
      cleanup();
    };
  }, [runId]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  if (!run) return <LoadingSpinner message="Connexion au pipeline en cours" />;

  const isCompleted = run.status === 'completed';
  const isFailed = run.status === 'failed';

  const stageOrder = ['analysis', 'generation', 'execution', 'debugger', 'report'];
  const statusStage = stageForStatus(run.status);
  const doneStages = isCompleted
    ? stageOrder
    : isFailed
    ? stageOrder.slice(0, Math.max(0, stageOrder.indexOf(statusStage)))
    : statusStage !== 'analysis'
    ? stageOrder.slice(0, stageOrder.indexOf(statusStage))
    : [];

  const activeStage = isCompleted || isFailed ? null : statusStage;

  return (
    <div className="max-w-5xl mx-auto animate-fade-up">
      {/* Header */}
      <div className="panel dark-grid rounded-xl px-6 py-5 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-white tracking-tight">Exécution du Pipeline</h1>
            <StatusBadge status={run.status} label={undefined} />
          </div>
          <p className="text-xs font-mono text-slate2-400 mt-1.5">
            session {runId?.substring(0, 8)} · télémétrie en direct via SSE
          </p>
        </div>

        {(isCompleted || isFailed) && (
          <Link
            to={`/runs/${runId}/${isCompleted ? 'results' : 'results'}`}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-cap-500 hover:bg-cap-600 text-white text-sm font-medium transition-colors"
          >
            {isCompleted ? 'Voir les Résultats' : 'Voir les Détails de l\'Échec'}
            <ArrowRight size={15} />
          </Link>
        )}
      </div>

      {/* Running / failure banner */}
      {isFailed && run.progress && (
        <div className="mt-4 flex items-start gap-3 border border-danger-200 bg-danger-50 rounded-lg px-4 py-3">
          <AlertCircle size={17} className="text-danger-500 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-danger-700">Échec du pipeline</p>
            <p className="text-xs text-danger-600 mt-0.5 font-mono break-words">{run.progress}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 mt-6">
        {/* Stage tracker */}
        <div className="card py-4 px-2">
          <PipelineFlow doneStages={doneStages} activeStage={activeStage} failed={isFailed} />
        </div>

        {/* Live log */}
        <div className="flex flex-col">
          <div className="panel flex flex-col flex-1 min-h-[440px] rounded-lg overflow-hidden">
            <div className="panel-header">
              <div className="flex items-center gap-2">
                <TerminalSquare size={13} />
                Journal d'Exécution en Direct
              </div>
              <div className="flex items-center gap-2">
                {!isCompleted && !isFailed && !connectionLost && (
                  <span className="flex items-center gap-1.5 text-accent-400 normal-case">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent-400 animate-pulse" />
                    en direct
                  </span>
                )}
                {connectionLost && <span className="text-warning-400 normal-case">reconnexion…</span>}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto dark-scrollbar p-4 font-mono text-xs leading-relaxed">
              {events.length === 0 ? (
                <p className="text-slate2-600 italic">En attente de la télémétrie du pipeline…</p>
              ) : (
                events.map((event, idx) => (
                  <div key={idx} className="flex gap-3">
                    <span className="text-slate2-600 shrink-0">{event.time}</span>
                    <span
                      className={
                        event.kind === 'error'
                          ? 'text-danger-400'
                          : event.kind === 'done'
                          ? 'text-success-400'
                          : 'text-cap-300'
                      }
                    >
                      {event.text}
                    </span>
                  </div>
                ))
              )}
              {!isCompleted && !isFailed && (
                <span className="inline-block w-2 h-3.5 bg-cap-500 animate-pulse mt-1" />
              )}
              <div ref={logEndRef} />
            </div>
          </div>

          {connectionLost && !isCompleted && !isFailed && (
            <div className="mt-3 flex items-center justify-between border border-warning-200 bg-warning-50 rounded-md px-4 py-2.5">
              <p className="text-xs text-warning-700">Flux déconnecté — le pipeline continue peut-être de s'exécuter.</p>
              <button
                onClick={() => navigate(0)}
                className="text-xs font-medium text-warning-700 hover:text-warning-600 inline-flex items-center gap-1"
              >
                <RefreshCcw size={12} />
                Reconnexion
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
