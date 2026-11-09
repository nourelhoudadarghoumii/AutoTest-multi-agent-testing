import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Play, FileCode2, Clock, CheckCircle2, AlertCircle, ChevronRight, Folder,
  Loader2, Eye, Edit2, Check, X, Trash2,
} from 'lucide-react';
import { projectService, apiErrorMessage } from '../services/api';
import type { Project, RunSummary, SourceFile } from '../types';
import PythonCode from '../components/PythonCode';
import StatusBadge from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<(Project & { runs: RunSummary[] }) | null>(null);
  const [files, setFiles] = useState<SourceFile[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);

  // File selection for execution & deletion
  const [selectedFilesForRun, setSelectedFilesForRun] = useState<Set<string>>(new Set());
  const [deletingFile, setDeletingFile] = useState<string | null>(null);

  // Project renaming state
  const [isEditingName, setIsEditingName] = useState(false);
  const [nameInput, setNameInput] = useState('');
  const [savingName, setSavingName] = useState(false);

  useEffect(() => {
    if (projectId) loadProject();
  }, [projectId]);

  const loadProject = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [proj, fileData] = await Promise.all([
        projectService.getProject(projectId!),
        projectService.getSourceFiles(projectId!),
      ]);
      setProject(proj);
      setFiles(fileData);
      setSelectedFilesForRun(new Set(fileData.map((f) => f.path)));
      if (fileData.length > 0) selectFile(fileData[0].path);
    } catch (error) {
      setLoadError(apiErrorMessage(error, 'Impossible de charger ce projet.'));
    } finally {
      setLoading(false);
    }
  };

  const selectFile = async (path: string) => {
    setSelectedPath(path);
    setFileContent('');
    try {
      const data = await projectService.getSourceFile(projectId!, path);
      setFileContent(data.content);
    } catch {
      setFileContent('# Impossible de charger le contenu du fichier.');
    }
  };

  const toggleSelectForRun = (filePath: string) => {
    setSelectedFilesForRun((prev) => {
      const next = new Set(prev);
      if (next.has(filePath)) {
        next.delete(filePath);
      } else {
        next.add(filePath);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedFilesForRun.size === files.length) {
      setSelectedFilesForRun(new Set());
    } else {
      setSelectedFilesForRun(new Set(files.map((f) => f.path)));
    }
  };

  const handleDeleteFile = async (e: React.MouseEvent, filePath: string, fileName: string) => {
    e.stopPropagation();
    if (!window.confirm(`Voulez-vous vraiment supprimer définitivement « ${fileName} » du projet ?\n\nCe fichier sera retiré du disque et ne sera plus analysé.`)) {
      return;
    }

    setDeletingFile(filePath);
    setStartError(null);
    try {
      await projectService.deleteSourceFile(projectId!, filePath);
      const remaining = files.filter((f) => f.path !== filePath);
      setFiles(remaining);
      setSelectedFilesForRun((prev) => {
        const next = new Set(prev);
        next.delete(filePath);
        return next;
      });
      setProject((prev) => (prev ? { ...prev, files_count: remaining.length } : null));
      setFeedbackMessage(`Fichier « ${fileName} » supprimé avec succès.`);
      setTimeout(() => setFeedbackMessage(null), 4000);

      if (selectedPath === filePath) {
        if (remaining.length > 0) {
          selectFile(remaining[0].path);
        } else {
          setSelectedPath(null);
          setFileContent('');
        }
      }
    } catch (err) {
      setStartError(apiErrorMessage(err, 'Impossible de supprimer le fichier.'));
    } finally {
      setDeletingFile(null);
    }
  };

  const handleStartRun = async () => {
    if (!projectId) return;
    if (selectedFilesForRun.size === 0) {
      setStartError('Veuillez sélectionner au moins un fichier à inclure dans les tests.');
      return;
    }
    setStarting(true);
    setStartError(null);
    try {
      const chosenFiles = Array.from(selectedFilesForRun);
      const response = await projectService.analyzeProject(projectId, chosenFiles);
      navigate(`/runs/${response.run_id}/progress`);
    } catch (error) {
      setStartError(apiErrorMessage(error, 'Impossible de démarrer le pipeline.'));
      setStarting(false);
    }
  };

  const handleSaveName = async () => {
    const trimmed = nameInput.trim();
    if (!trimmed || !projectId) return;
    setSavingName(true);
    try {
      await projectService.renameProject(projectId, trimmed);
      setProject((prev) => (prev ? { ...prev, name: trimmed } : null));
      setIsEditingName(false);
    } catch (err) {
      setStartError(apiErrorMessage(err, 'Impossible de renommer le projet.'));
    } finally {
      setSavingName(false);
    }
  };

  if (loading) return <LoadingSpinner message="Chargement du projet" />;

  if (loadError || !project) {
    return <ErrorState title="Projet introuvable" message={loadError ?? "Ce projet n'existe pas."} onRetry={loadProject} />;
  }

  const runs = project.runs;

  return (
    <div className="space-y-6 animate-fade-up">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-1.5 text-xs text-slate2-500 font-mono mb-2">
            <Link to="/projects" className="hover:text-cap-600">Projets</Link>
            <ChevronRight size={12} />
            <span className="text-slate2-700">{project.name}</span>
          </div>

          {isEditingName ? (
            <div className="flex items-center gap-2 mt-1">
              <input
                type="text"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveName();
                  if (e.key === 'Escape') setIsEditingName(false);
                }}
                autoFocus
                disabled={savingName}
                className="input-field text-xl font-bold py-1 px-2.5 max-w-md"
              />
              <button
                onClick={handleSaveName}
                disabled={savingName || !nameInput.trim()}
                className="p-2 rounded-md bg-success-50 text-success-700 hover:bg-success-100 border border-success-200"
                title="Enregistrer le nom"
              >
                <Check size={16} />
              </button>
              <button
                onClick={() => setIsEditingName(false)}
                disabled={savingName}
                className="p-2 rounded-md bg-slate2-100 text-slate2-600 hover:bg-slate2-200 border border-slate2-200"
                title="Annuler"
              >
                <X size={16} />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight text-slate2-900">{project.name}</h1>
              <button
                onClick={() => {
                  setNameInput(project.name);
                  setIsEditingName(true);
                }}
                className="p-1 text-slate2-400 hover:text-cap-600 hover:bg-slate2-100 rounded-md transition-colors"
                title="Renommer le projet"
              >
                <Edit2 size={16} />
              </button>
            </div>
          )}

          <p className="text-slate2-500 text-sm mt-1">
            <span className="font-mono">{project.files_count}</span> fichier(s) Python · ajouté le{' '}
            {new Date(project.uploaded_at).toLocaleString()}
          </p>
        </div>

        <button
          onClick={handleStartRun}
          disabled={starting || selectedFilesForRun.size === 0}
          className="btn-primary"
          title={selectedFilesForRun.size === 0 ? 'Sélectionnez au moins un fichier à tester' : ''}
        >
          {starting ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          {starting
            ? 'Démarrage du pipeline…'
            : `Lancer les Tests (${selectedFilesForRun.size} fichier${selectedFilesForRun.size > 1 ? 's' : ''})`}
        </button>
      </div>

      {feedbackMessage && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-md text-sm flex items-center justify-between">
          <span className="flex items-center gap-2">
            <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
            {feedbackMessage}
          </span>
          <button onClick={() => setFeedbackMessage(null)} className="text-emerald-600 hover:text-emerald-800">
            <X size={14} />
          </button>
        </div>
      )}

      {startError && <ErrorState title="Notification" message={startError} />}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Source browser */}
        <div className="lg:col-span-2 flex flex-col">
          <div className="card p-0 overflow-hidden flex flex-col" style={{ minHeight: '480px' }}>
            <div className="px-5 py-3 border-b border-slate2-200 bg-slate2-50 flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <Folder size={14} className="text-cap-500" />
                <h3 className="text-xs font-bold text-slate2-600 uppercase tracking-wider">
                  Fichiers Sources
                </h3>
                <span className="text-xs font-mono text-slate2-500">
                  ({selectedFilesForRun.size}/{files.length} sélectionnés pour test)
                </span>
              </div>
              {files.length > 0 && (
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={toggleSelectAll}
                    className="text-xs font-medium text-cap-600 hover:text-cap-700 underline"
                  >
                    {selectedFilesForRun.size === files.length ? 'Tout désélectionner' : 'Tout sélectionner'}
                  </button>
                </div>
              )}
            </div>

            {files.length === 0 ? (
              <div className="flex-1 p-8">
                <EmptyState
                  icon={FileCode2}
                  title="Aucun fichier Python trouvé"
                  description="Ce projet ne contient aucun fichier .py — téléversez un projet avec du code Python pour exécuter les tests."
                  to="/projects"
                  actionLabel="Téléverser un autre projet"
                />
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] flex-1 min-h-0">
                {/* file list */}
                <div className="border-r border-slate2-200 overflow-y-auto custom-scrollbar max-h-[60vh] divide-y divide-slate2-100">
                  {files.map((f) => (
                    <div
                      key={f.path}
                      onClick={() => selectFile(f.path)}
                      className={`group w-full flex items-center gap-2 px-3 py-2.5 text-left text-sm transition-colors border-l-2 cursor-pointer ${
                        selectedPath === f.path
                          ? 'bg-cap-50 border-cap-500 text-cap-700 font-medium'
                          : 'border-transparent text-slate2-600 hover:bg-slate2-50'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedFilesForRun.has(f.path)}
                        onChange={(e) => {
                          e.stopPropagation();
                          toggleSelectForRun(f.path);
                        }}
                        className="w-3.5 h-3.5 rounded border-slate2-300 text-cap-600 focus:ring-cap-500 cursor-pointer shrink-0"
                        title={selectedFilesForRun.has(f.path) ? "Inclus dans l'analyse" : "Exclu de l'analyse"}
                      />
                      <FileCode2 size={13} className={selectedPath === f.path ? 'text-cap-500 shrink-0' : 'text-slate2-400 shrink-0'} />
                      <span className="truncate font-mono text-xs flex-1" title={f.path}>{f.name}</span>
                      <span className="text-[10px] text-slate2-400 font-mono shrink-0">
                        {(f.size / 1024).toFixed(1)}k
                      </span>
                      <button
                        type="button"
                        onClick={(e) => handleDeleteFile(e, f.path, f.name)}
                        disabled={deletingFile === f.path}
                        className="p-1 text-slate2-400 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors opacity-70 group-hover:opacity-100 shrink-0"
                        title="Supprimer définitivement ce fichier du projet"
                      >
                        {deletingFile === f.path ? (
                          <Loader2 size={13} className="animate-spin text-rose-500" />
                        ) : (
                          <Trash2 size={13} />
                        )}
                      </button>
                    </div>
                  ))}
                </div>

                {/* code view */}
                <div className="flex flex-col min-w-0">
                  {selectedPath ? (
                    <>
                      <div className="px-4 py-2 border-b border-cap-900/50 bg-cap-900 text-cap-300 text-xs font-mono flex items-center justify-between">
                        <span className="flex items-center gap-2">
                          <Eye size={12} />
                          {selectedPath}
                        </span>
                        <span className="text-[11px] text-cap-400 font-sans">
                          {selectedFilesForRun.has(selectedPath) ? 'Inclus dans le test' : 'Exclu du test'}
                        </span>
                      </div>
                      <PythonCode code={fileContent || '// chargement…'} maxHeight="56vh" />
                    </>
                  ) : (
                    <div className="flex-1 flex items-center justify-center text-slate2-400 text-sm">
                      Sélectionnez un fichier pour l'examiner
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Run history */}
        <div className="flex flex-col">
          <div className="card p-0 overflow-hidden flex flex-col h-full">
            <div className="px-5 py-3 border-b border-slate2-200 bg-slate2-50">
              <h3 className="text-xs font-bold text-slate2-600 uppercase tracking-wider">Historique des Sessions</h3>
            </div>

            {runs.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
                <Play size={28} className="text-slate2-300 mb-3" />
                <p className="text-sm font-medium text-slate2-700">Aucune session pour le moment</p>
                <p className="text-xs text-slate2-500 mt-1 leading-relaxed">
                  Cliquez sur <span className="font-semibold text-cap-600">Lancer les Tests</span> pour démarrer
                  la génération, l'exécution et l'audit de qualité.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-slate2-100">
                {runs.map((run) => (
                  <Link
                    key={run.id}
                    to={run.status === 'completed' || run.status === 'failed' ? `/runs/${run.id}/results` : `/runs/${run.id}/progress`}
                    className="block px-5 py-3.5 hover:bg-cap-50/50 transition-colors group"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          {run.status === 'completed' ? (
                            <CheckCircle2 size={14} className="text-success-500 shrink-0" />
                          ) : run.status === 'failed' ? (
                            <AlertCircle size={14} className="text-danger-500 shrink-0" />
                          ) : (
                            <div className="w-3.5 h-3.5 border-2 border-cap-300 border-t-accent-500 rounded-full animate-spin shrink-0" />
                          )}
                          <span className="font-mono text-xs font-semibold text-slate2-900 group-hover:text-cap-700">
                            session {run.id.substring(0, 8)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-[11px] text-slate2-400 mt-1 font-mono">
                          <Clock size={10} />
                          {new Date(run.started_at).toLocaleTimeString()}
                          {run.tests_passed != null && run.tests_total != null && run.tests_total > 0 && (
                            <span>· {run.tests_passed}/{run.tests_total} réussis</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {run.quality_score != null && (
                          <span className="font-mono text-xs font-bold text-cap-700">{run.quality_score}/100</span>
                        )}
                        <StatusBadge status={run.status} size="sm" />
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
