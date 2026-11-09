import { CheckCircle2, CircleDashed, FileCode2, FlaskConical, Loader2, Radar, Activity, Wrench, FileCheck2 } from 'lucide-react';

/**
 * Structured engineering workflow stages.
 * Used on the Workspace (full map) and RunProgress (live tracker).
 */

export const PIPELINE_STAGES = [
  { id: 'project',    label: 'Source du Projet',          desc: 'Fichiers Python chargés dans l\'espace de travail' },
  { id: 'analysis',   label: 'Analyse Statique (AST)',    desc: 'Structure AST, complexité et dépendances' },
  { id: 'generation', label: 'Génération de la Suite',    desc: 'Synthèse des cas de test pytest' },
  { id: 'validation', label: 'Vérification Syntaxique',   desc: 'Validation AST et conformité syntaxique' },
  { id: 'execution',  label: 'Exécution des Tests',       desc: 'Lancement de pytest et mesure de couverture' },
  { id: 'detection',  label: 'Diagnostic des Échecs',     desc: 'Capture des assertions et traces d\'erreurs' },
  { id: 'debugger',   label: 'Réparation Automatisée',    desc: 'Génération de correctifs ciblés' },
  { id: 'reval',      label: 'Vérification des Tests',    desc: 'Validation de la suite réparée' },
  { id: 'quality',    label: 'Évaluation Qualité',        desc: 'Évaluation de la couverture et santé du code' },
  { id: 'report',     label: 'Rapport Décisionnel',       desc: 'Rapport technique avec recommandations' },
] as const;

/** Map a backend run status/agent to the active pipeline stage id. */
export function stageForStatus(status: string | undefined, agent?: string): string {
  if (status === 'completed') return 'report';
  if (status === 'failed') return 'detection';
  switch (agent) {
    case 'analyser': return 'analysis';
    case 'test_writer': return 'generation';
    case 'executor': return 'execution';
    case 'debugger': return 'debugger';
    case 'completed': return 'report';
    default: return 'analysis';
  }
}

interface PipelineFlowProps {
  /** Stage ids marked done. */
  doneStages?: string[];
  /** Currently active stage id. */
  activeStage?: string | null;
  failed?: boolean;
  compact?: boolean;
}

export default function PipelineFlow({ doneStages = [], activeStage, failed = false, compact = false }: PipelineFlowProps) {
  return (
    <ol className="relative space-y-0">
      {PIPELINE_STAGES.map((stage, idx) => {
        const isDone = doneStages.includes(stage.id);
        const isActive = activeStage === stage.id && !failed;
        const isLast = idx === PIPELINE_STAGES.length - 1;

        const icon = isDone ? (
          <CheckCircle2 size={18} className="text-success-500" />
        ) : isActive ? (
          <Loader2 size={18} className="text-accent-500 animate-spin" />
        ) : failed && activeStage === stage.id ? (
          <Radar size={18} className="text-danger-500" />
        ) : (
          <CircleDashed size={18} className="text-slate2-300" />
        );

        return (
          <li key={stage.id} className="relative flex gap-4">
            {/* connector */}
            {!isLast && (
              <div
                className={`absolute left-[13px] top-8 bottom-0 w-px ${
                  isDone ? 'bg-success-300' : isActive ? 'bg-accent-400' : 'bg-slate2-200'
                }`}
              />
            )}
            <div className="relative z-10 py-2 pl-2 pr-1 bg-inherit">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center ${
                isDone ? 'bg-success-50' : isActive ? 'bg-accent-50' : 'bg-white'
              }`}>
                {icon}
              </div>
            </div>
            <div className={`pb-6 pt-2.5 ${compact ? '' : ''}`}>
              <p className={`text-sm font-semibold tracking-tight ${
                isActive ? 'text-cap-700' : isDone ? 'text-slate2-800' : 'text-slate2-400'
              }`}>
                {stage.label}
              </p>
              <p className="text-xs text-slate2-500 mt-0.5">{stage.desc}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Horizontal strip of workflow capability chips */
export function PipelineChips() {
  const chips = [
    { icon: Activity, label: 'Analyse Statique AST' },
    { icon: FileCode2, label: 'Génération Pytest' },
    { icon: FlaskConical, label: 'Exécution & Couverture' },
    { icon: Wrench, label: 'Diagnostic des Échecs' },
    { icon: FileCheck2, label: 'Rapport Décisionnel' },
  ];
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {chips.map((c) => {
        const Icon = c.icon;
        return (
          <div
            key={c.label}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-cap-900/60 border border-cap-700/60 text-slate2-200 text-xs font-mono"
          >
            <Icon size={13} className="text-cap-300" />
            <span>{c.label}</span>
          </div>
        );
      })}
    </div>
  );
}
