import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  FileCode2, AlertCircle, FolderOpen, Clock, Play, Trash2, Archive,
  Edit2, Check, X,
} from 'lucide-react';
import { projectService, apiErrorMessage } from '../services/api';
import type { Project } from '../types';
import EmptyState from '../components/EmptyState';
import LoadingSpinner from '../components/LoadingSpinner';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const pyInputRef = useRef<HTMLInputElement>(null);
  const archiveInputRef = useRef<HTMLInputElement>(null);

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Rename state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState<string>('');
  const [savingRename, setSavingRename] = useState(false);

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setProjects(await projectService.getProjects());
    } catch (error) {
      setLoadError(apiErrorMessage(error, 'Impossible de charger les projets.'));
    } finally {
      setLoading(false);
    }
  };

  const upload = async (transport: () => Promise<{ project_id: string }>) => {
    setUploading(true);
    setUploadError(null);
    try {
      const result = await transport();
      navigate(`/projects/${result.project_id}`);
    } catch (error) {
      setUploadError(apiErrorMessage(error, 'Échec du téléversement.'));
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const list = Array.from(files);
    if (list.every((f) => f.name.endsWith('.py'))) {
      upload(() => projectService.uploadFiles(files));
    } else if (list.length === 1 && /\.(zip|tar\.gz|tgz)$/.test(list[0].name)) {
      upload(() => projectService.uploadArchive(list[0]));
    } else {
      setUploadError('Formats acceptés : une archive .zip/.tar.gz ou un ou plusieurs fichiers .py.');
    }
  };

  const handleDelete = async (projectId: string) => {
    if (!window.confirm('Êtes-vous sûr de vouloir supprimer ce projet et toutes ses sessions ?')) return;
    setDeleting(projectId);
    try {
      await projectService.deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
    } catch (error) {
      setUploadError(apiErrorMessage(error, 'Échec de la suppression.'));
    } finally {
      setDeleting(null);
    }
  };

  const startRename = (project: Project) => {
    setEditingId(project.id);
    setEditingName(project.name);
  };

  const cancelRename = () => {
    setEditingId(null);
    setEditingName('');
  };

  const handleSaveRename = async (projectId: string) => {
    const trimmed = editingName.trim();
    if (!trimmed) return;
    setSavingRename(true);
    try {
      await projectService.renameProject(projectId, trimmed);
      setProjects((prev) =>
        prev.map((p) => (p.id === projectId ? { ...p, name: trimmed } : p))
      );
      setEditingId(null);
    } catch (error) {
      setUploadError(apiErrorMessage(error, 'Impossible de renommer le projet.'));
    } finally {
      setSavingRename(false);
    }
  };

  if (loading) return <LoadingSpinner message="Chargement des projets" />;

  return (
    <div className="space-y-6 animate-fade-up">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate2-900">Projets</h1>
          <p className="text-slate2-500 mt-1.5 text-sm">
            Gérez vos espaces de travail Python et leurs suites de tests.
          </p>
        </div>
      </div>

      {/* Upload zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); handleDrop(e.dataTransfer.files); }}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-all ${
          dragOver ? 'border-accent-400 bg-cap-50' : 'border-slate2-300 bg-white hover:border-cap-400'
        }`}
      >
        <input
          ref={pyInputRef}
          type="file"
          className="hidden"
          multiple
          accept=".py"
          onChange={(e) => {
            if (e.target.files) upload(() => projectService.uploadFiles(e.target.files!));
          }}
        />
        <input
          ref={archiveInputRef}
          type="file"
          className="hidden"
          accept=".zip,.tar.gz,.tgz"
          onChange={(e) => {
            if (e.target.files?.[0]) {
              const file = e.target.files[0];
              upload(() => projectService.uploadArchive(file));
            }
          }}
        />

        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-[3px] border-cap-200 border-t-cap-500 rounded-full animate-spin" />
            <p className="text-sm font-medium text-slate2-700">Téléversement et validation du projet en cours…</p>
          </div>
        ) : (
          <>
            <div className="w-12 h-12 bg-cap-50 border border-cap-200 rounded-full flex items-center justify-center mx-auto mb-3">
              <FolderOpen size={20} className="text-cap-600" />
            </div>
            <p className="text-sm font-medium text-slate2-800">
              Glissez-déposez vos fichiers Python ou votre archive ici
            </p>
            <p className="text-xs text-slate2-500 mt-1">ou sélectionnez un format de fichier :</p>
            <div className="flex items-center justify-center gap-3 mt-4">
              <button className="btn-primary text-sm" onClick={() => pyInputRef.current?.click()}>
                <FileCode2 size={15} />
                Fichiers .py
              </button>
              <button className="btn-secondary text-sm" onClick={() => archiveInputRef.current?.click()}>
                <Archive size={15} />
                Archive .zip / .tar.gz
              </button>
            </div>
            <p className="text-[11px] text-slate2-400 mt-3 font-mono">
              max 100 Mo par archive · doit contenir des sources Python
            </p>
          </>
        )}

        {uploadError && (
          <div className="mt-4 flex items-start gap-2 text-sm text-danger-600 bg-danger-50 border border-danger-200 rounded-md px-3 py-2 text-left max-w-lg mx-auto">
            <AlertCircle size={15} className="shrink-0 mt-0.5" />
            {uploadError}
          </div>
        )}
      </div>

      {loadError && (
        <div className="flex items-start gap-2 text-sm text-danger-600 bg-danger-50 border border-danger-200 rounded-md px-4 py-3">
          <AlertCircle size={16} className="shrink-0 mt-0.5" />
          {loadError}
        </div>
      )}

      {/* Project list */}
      {projects.length === 0 && !loadError ? (
        <EmptyState
          icon={FolderOpen}
          title="Aucun projet pour le moment"
          description="Téléversez des fichiers .py ou une archive ZIP ci-dessus. AutoTest analysera le code et générera les tests automatiquement."
        />
      ) : (
        <div className="card p-0 overflow-hidden">
          <table className="w-full">
            <thead className="bg-slate2-50 border-b border-slate2-200">
              <tr>
                <th className="th-cell">Nom du Projet</th>
                <th className="th-cell">Fichiers</th>
                <th className="th-cell">Sessions</th>
                <th className="th-cell">Date d'Ajout</th>
                <th className="th-cell text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate2-100">
              {projects.map((project) => {
                const isEditing = editingId === project.id;
                return (
                  <tr key={project.id} className="hover:bg-cap-50/40 transition-colors group">
                    <td className="td-cell">
                      {isEditing ? (
                        <div className="flex items-center gap-2 max-w-md">
                          <input
                            type="text"
                            value={editingName}
                            onChange={(e) => setEditingName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleSaveRename(project.id);
                              if (e.key === 'Escape') cancelRename();
                            }}
                            autoFocus
                            disabled={savingRename}
                            className="input-field text-xs py-1 px-2 font-medium"
                          />
                          <button
                            onClick={() => handleSaveRename(project.id)}
                            disabled={savingRename || !editingName.trim()}
                            className="p-1.5 rounded-md bg-success-50 text-success-700 hover:bg-success-100 border border-success-200"
                            title="Enregistrer"
                          >
                            <Check size={13} />
                          </button>
                          <button
                            onClick={cancelRename}
                            disabled={savingRename}
                            className="p-1.5 rounded-md bg-slate2-100 text-slate2-600 hover:bg-slate2-200 border border-slate2-200"
                            title="Annuler"
                          >
                            <X size={13} />
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-3">
                          <Link to={`/projects/${project.id}`} className="flex items-center gap-3 group/link">
                            <div className="w-8 h-8 bg-cap-50 border border-cap-200 rounded-md flex items-center justify-center shrink-0">
                              <FolderOpen size={15} className="text-cap-500" />
                            </div>
                            <span className="font-medium text-slate2-900 group-hover/link:text-cap-700 transition-colors">
                              {project.name}
                            </span>
                          </Link>
                          <button
                            onClick={() => startRename(project)}
                            className="opacity-0 group-hover:opacity-100 p-1 text-slate2-400 hover:text-cap-600 rounded transition-all"
                            title="Renommer le projet"
                          >
                            <Edit2 size={12} />
                          </button>
                        </div>
                      )}
                    </td>
                    <td className="td-cell font-mono">{project.files_count}</td>
                    <td className="td-cell font-mono">{project.runs_count}</td>
                    <td className="td-cell text-slate2-500 text-xs">
                      <span className="inline-flex items-center gap-1.5">
                        <Clock size={11} />
                        {new Date(project.uploaded_at).toLocaleString()}
                      </span>
                    </td>
                    <td className="td-cell">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => startRename(project)}
                          className="btn-secondary text-xs py-1.5 px-2.5 inline-flex items-center gap-1 text-slate2-600"
                          title="Renommer"
                        >
                          <Edit2 size={12} />
                          Renommer
                        </button>
                        <Link
                          to={`/projects/${project.id}`}
                          className="btn-primary text-xs py-1.5 px-3 inline-flex items-center gap-1.5"
                        >
                          <Play size={12} />
                          Ouvrir
                        </Link>
                        <button
                          onClick={() => handleDelete(project.id)}
                          disabled={deleting === project.id}
                          className="p-1.5 rounded-md text-slate2-400 hover:text-danger-600 hover:bg-danger-50 transition-colors disabled:opacity-50"
                          title="Supprimer le projet"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
