import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Download, FileCode2, Package, Copy, Check } from 'lucide-react';
import { projectService, runService, apiErrorMessage } from '../services/api';
import type { Project, RunStatus, TestFileContent, TestFileMeta } from '../types';
import RunHeader from '../components/RunHeader';
import PythonCode from '../components/PythonCode';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';

/** Counts test functions in generated code. */
function countTests(code: string): number {
  const matches = code.match(/^\s*def\s+test_\w+|^\s*async\s+def\s+test_\w+/gm);
  return matches ? matches.length : 0;
}

/** Counts assert statements (a rough assertion-density indicator). */
function countAsserts(code: string): number {
  const matches = code.match(/\bassert\b/g);
  return matches ? matches.length : 0;
}

export default function GeneratedTestsPage() {
  const { runId } = useParams<{ runId: string }>();

  const [files, setFiles] = useState<TestFileMeta[]>([]);
  const [selected, setSelected] = useState<TestFileContent | null>(null);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const runData = await runService.getRun(runId);
      setRun(runData);
      projectService.getProject(runData.project_id).then(setProject).catch(() => {});
      const fileMetas = await runService.getTestFiles(runId);
      setFiles(fileMetas);
      if (fileMetas.length > 0) {
        setSelected(await runService.getTestFile(runId, fileMetas[0].filename));
      }
    } catch (err) {
      setError(apiErrorMessage(err, 'Impossible de charger les tests générés.'));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCopy = () => {
    if (!selected) return;
    navigator.clipboard.writeText(selected.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) return <LoadingSpinner message="Chargement des tests générés" />;

  if (error) return <ErrorState title="Impossible de charger les tests" message={error} onRetry={load} />;

  return (
    <div>
      <RunHeader runId={runId!} projectId={run?.project_id ?? ''} projectName={project?.name} status={run?.status} activeTab="/tests" />

      {files.length === 0 ? (
        <EmptyState
          icon={FileCode2}
          title="Aucun fichier de test généré"
          description="Cette session n'a généré aucun fichier de test. Vérifiez l'onglet d'exécution — le pipeline a peut-être échoué avant la fin de la génération."
        />
      ) : (
        <div className="animate-fade-up">
          {/* Toolbar */}
          <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
            <div className="flex items-center gap-4 text-xs font-mono text-slate2-500">
              <span>{files.length} fichier(s)</span>
              {selected && (
                <>
                  <span className="text-slate2-300">|</span>
                  <span>{countTests(selected.content)} fonctions de test</span>
                  <span className="text-slate2-300">|</span>
                  <span>{countAsserts(selected.content)} assertions</span>
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => runService.download(runId!, 'tests')} className="btn-secondary text-xs py-1.5 flex items-center gap-1.5">
                <Download size={13} />
                Télécharger les tests (.zip)
              </button>
              <button onClick={() => runService.download(runId!, 'package')} className="btn-primary text-xs py-1.5 flex items-center gap-1.5">
                <Package size={13} />
                Archive complète
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-4">
            {/* File tree */}
            <div className="card p-2 self-start">
              <p className="label-mono px-3 py-2">tests_generes/</p>
              <div className="space-y-0.5">
                {files.map((f) => (
                  <button
                    key={f.path}
                    onClick={async () => {
                      setSelected(await runService.getTestFile(runId!, f.filename));
                      setCopied(false);
                    }}
                    className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-left text-xs font-mono transition-colors ${
                      selected?.filename === f.filename
                        ? 'bg-cap-50 text-cap-700 font-semibold border border-cap-200'
                        : 'text-slate2-600 hover:bg-slate2-50 border border-transparent'
                    }`}
                  >
                    <FileCode2 size={13} className={selected?.filename === f.filename ? 'text-cap-500' : 'text-slate2-400'} />
                    <span className="truncate">{f.filename}</span>
                    <span className="ml-auto text-[10px] text-slate2-400 shrink-0">
                      {(f.size / 1024).toFixed(1)}k
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Code viewer */}
            <div className="min-w-0">
              {selected ? (
                <>
                  <div className="panel-header rounded-t-lg border-b-0 flex items-center justify-between">
                    <span className="text-cap-300 normal-case tracking-normal font-mono">{selected.filename}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-slate2-400 text-xs font-mono">{countTests(selected.content)} tests</span>
                      <button
                        onClick={handleCopy}
                        className="btn-secondary text-[11px] py-1 px-2.5 flex items-center gap-1.5 text-slate2-300 hover:text-white"
                        title="Copier le code dans le presse-papier"
                      >
                        {copied ? <Check size={12} className="text-success-400" /> : <Copy size={12} />}
                        <span>{copied ? 'Copié !' : 'Copier'}</span>
                      </button>
                    </div>
                  </div>
                  <PythonCode code={selected.content} maxHeight="68vh" />
                </>
              ) : (
                <LoadingSpinner message="Chargement du fichier" />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
