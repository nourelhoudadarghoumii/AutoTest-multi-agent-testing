import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  UploadCloud, FileCode2, ArrowRight, CheckCircle2, AlertCircle, Clock,
  FlaskConical, ScanSearch, ShieldCheck, CircleDot, FileCheck2,
} from 'lucide-react';
import { projectService, runService, systemService, apiErrorMessage } from '../services/api';
import type { Project, RunSummary, WorkspaceStats, Health } from '../types';
import PipelineFlow, { PipelineChips } from '../components/PipelineFlow';
import { MetricCard } from '../components/Metric';
import StatusBadge from '../components/StatusBadge';
import ErrorState from '../components/ErrorState';

export default function WorkspacePage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [projects, setProjects] = useState<Project[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [stats, setStats] = useState<WorkspaceStats | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    loadWorkspace();
  }, []);

  const loadWorkspace = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [healthData, statsData, runsData] = await Promise.all([
        systemService.getHealth().catch(() => null),
        systemService.getStats().catch(() => null),
        runService.getRuns().catch(() => []),
      ]);
      setHealth(healthData);
      setStats(statsData);
      setRuns(runsData);
      const projectData = await projectService.getProjects().catch(() => []);
      setProjects(projectData);
    } catch (error) {
      setLoadError(apiErrorMessage(error, 'Impossible de charger les données de l\'espace de travail.'));
    } finally {
      setLoading(false);
    }
  };

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setUploadError(null);
    try {
      const allPy = Array.from(files).every((f) => f.name.endsWith('.py'));
      if (allPy) {
        const result = await projectService.uploadFiles(files);
        navigate(`/projects/${result.project_id}`);
      } else if (files.length === 1 && /\.(zip|tar\.gz|tgz)$/.test(files[0].name)) {
        const result = await projectService.uploadArchive(files[0]);
        navigate(`/projects/${result.project_id}`);
      } else {
        setUploadError('Formats acceptés : une archive .zip/.tar.gz ou un ou plusieurs fichiers .py.');
      }
    } catch (error) {
      setUploadError(apiErrorMessage(error, 'Échec du téléversement.'));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const projectName = (id: string) => projects.find((p) => p.id === id)?.name;
  const recentRuns = runs.slice(0, 6);

  if (loading) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-[3px] border-cap-200 border-t-cap-500 rounded-full animate-spin" />
          <p className="text-slate2-500 font-mono text-xs uppercase tracking-widest">Chargement de l'espace de travail</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-10 animate-fade-up">
      {/* ── Hero: product identity + entry point ─────────────────────────── */}
      <section className="panel blueprint-grid rounded-xl px-8 py-10 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-cap-950/40 via-transparent to-cap-800/30 pointer-events-none" />
        <div className="relative max-w-3xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-cap-700 bg-cap-900/70 text-cap-300 text-[11px] font-mono uppercase tracking-widest mb-6">
            <CircleDot size={11} className="text-accent-400" />
            Ingénierie des Tests & Qualité Python
          </div>
          <h1 className="text-4xl font-extrabold tracking-tight text-white leading-tight">
            Suite de tests automatisée & audit de code
            <br />
            <span className="text-cap-300">conçus pour la prise de décision.</span>
          </h1>
          <p className="text-slate2-300/90 mt-4 leading-relaxed max-w-xl">
            Déposez votre projet Python. AutoTest analyse la complexité du code, génère des suites de tests pytest robustes, les exécute avec mesure de couverture, diagnostique et répare les assertions défaillantes, puis délivre un verdict d'ingénierie clair.
          </p>

          <div className="mt-8">
            <PipelineChips />
          </div>

          {/* Primary CTA: upload */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
            onClick={() => !uploading && fileInputRef.current?.click()}
            className={`mt-8 max-w-xl border-2 border-dashed rounded-lg px-6 py-6 flex items-center gap-4 cursor-pointer transition-all ${
              dragOver
                ? 'border-accent-400 bg-accent-500/10'
                : uploading
                ? 'border-cap-600 bg-cap-900/60'
                : 'border-cap-700 bg-cap-900/40 hover:border-cap-500 hover:bg-cap-900/70'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              multiple
              accept=".py,.zip,.tar.gz,.tgz"
              onChange={(e) => handleFiles(e.target.files)}
            />
            {uploading ? (
              <>
                <div className="w-9 h-9 border-2 border-cap-600 border-t-accent-400 rounded-full animate-spin shrink-0" />
                <div>
                  <p className="text-white font-medium text-sm">Téléversement du projet en cours…</p>
                  <p className="text-cap-300/70 text-xs font-mono mt-0.5">validation des fichiers sources</p>
                </div>
              </>
            ) : (
              <>
                <div className="w-10 h-10 bg-cap-800 border border-cap-700 rounded-lg flex items-center justify-center shrink-0">
                  <UploadCloud size={20} className="text-cap-300" />
                </div>
                <div className="min-w-0">
                  <p className="text-white font-medium text-sm">
                    Déposez un projet Python ici — <span className="text-cap-300 underline underline-offset-2">parcourir les fichiers</span>
                  </p>
                  <p className="text-slate2-400 text-xs mt-0.5 font-mono">
                    fichiers .py ou archives .zip / .tar.gz
                  </p>
                </div>
                <ArrowRight size={18} className="text-cap-400 ml-auto shrink-0" />
              </>
            )}
          </div>
          {uploadError && (
            <div className="mt-3 flex items-start gap-2 text-sm text-warning-300 bg-warning-500/10 border border-warning-500/30 rounded-md px-3 py-2 max-w-xl">
              <AlertCircle size={15} className="shrink-0 mt-0.5" />
              {uploadError}
            </div>
          )}
        </div>
      </section>

      {/* ── System status: real metrics only ─────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold text-slate2-900 uppercase tracking-wider">Vue d'Ensemble</h2>
          {health && (
            <span className="text-xs font-mono text-slate2-500">
              serveur v{health.version}
              {health.llm_configured
                ? <span className="text-success-600"> · Configuration valide</span>
                : <span className="text-warning-600"> · Configuration requise</span>}
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <MetricCard icon={FileCode2} label="Projets" value={stats?.total_projects ?? 0} tone="dark" />
          <MetricCard icon={FlaskConical} label="Sessions Terminées" value={stats?.completed_runs ?? 0} />
          <MetricCard icon={ScanSearch} label="Tests Générés" value={stats?.total_tests_generated ?? 0} />
          <MetricCard
            icon={CheckCircle2}
            label="Qualité Moyenne"
            value={stats?.average_quality != null ? `${stats.average_quality}` : '—'}
            sub={stats?.average_quality != null ? '/ 100' : 'aucun test'}
            tone="primary"
          />
          <MetricCard
            icon={ShieldCheck}
            label="Couverture Moyenne"
            value={stats?.average_coverage != null ? `${stats.average_coverage}%` : '—'}
            tone="success"
          />
        </div>
      </section>

      {/* ── Workflow map + recent activity ───────────────────────────────── */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card">
          <h3 className="font-bold text-slate2-900 text-sm uppercase tracking-wider mb-1">
            Flux de Vérification
          </h3>
          <p className="text-xs text-slate2-500 mb-5">
            Flux rigoureux en 10 étapes assurant validation syntaxique, exécution et mesure de couverture.
          </p>
          <PipelineFlow doneStages={PIPELINE_ALL_DONE} activeStage={null} compact />
        </div>

        <div className="lg:col-span-2">
          <div className="card h-full flex flex-col p-0 overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate2-100">
              <h3 className="font-bold text-slate2-900 text-sm uppercase tracking-wider">
                Sessions Récentes
              </h3>
              <Link to="/projects" className="text-xs text-cap-600 hover:text-cap-700 font-medium">
                Tous les projets →
              </Link>
            </div>

            {loadError ? (
              <div className="p-6">
                <ErrorState title="Serveur indisponible" message={loadError} onRetry={loadWorkspace} />
              </div>
            ) : recentRuns.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-10">
                <FileCheck2 size={36} className="text-slate2-300 mb-3" />
                <p className="text-slate2-700 font-medium">Aucune session pour le moment</p>
                <p className="text-sm text-slate2-500 mt-1 max-w-sm">
                  Téléversez un projet ci-dessus pour exécuter les tests et générer votre premier rapport technique.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-slate2-100 flex-1">
                {recentRuns.map((run) => (
                  <Link
                    key={run.id}
                    to={run.status === 'completed' || run.status === 'failed' ? `/runs/${run.id}/results` : `/runs/${run.id}/progress`}
                    className="flex items-center justify-between px-6 py-3.5 hover:bg-cap-50/60 transition-colors group"
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      <div className="shrink-0">
                        {run.status === 'completed' ? (
                          <CheckCircle2 size={18} className="text-success-500" />
                        ) : run.status === 'failed' ? (
                          <AlertCircle size={18} className="text-danger-500" />
                        ) : (
                          <div className="w-[18px] h-[18px] border-2 border-cap-200 border-t-accent-500 rounded-full animate-spin" />
                        )}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-slate2-900 truncate">
                            {projectName(run.project_id) ?? 'Projet'}
                          </p>
                          <span className="badge badge-neutral text-[10px] font-mono">{run.id.substring(0, 8)}</span>
                        </div>
                        <div className="flex items-center gap-3 text-xs text-slate2-500 mt-0.5">
                          <Clock size={11} />
                          {new Date(run.started_at).toLocaleString()}
                          {run.tests_total != null && run.tests_total > 0 && (
                            <span className="font-mono">
                              {run.tests_passed ?? 0}/{run.tests_total} tests
                              {run.coverage != null && ` · ${run.coverage}% couv.`}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      {run.quality_score != null && (
                        <span className="font-mono text-sm font-semibold text-cap-700">{run.quality_score}</span>
                      )}
                      <StatusBadge status={run.status} size="sm" />
                      <ArrowRight size={15} className="text-slate2-300 group-hover:text-cap-500 transition-colors" />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

const PIPELINE_ALL_DONE: string[] = [];
