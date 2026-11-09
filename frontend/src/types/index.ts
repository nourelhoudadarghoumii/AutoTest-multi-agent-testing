// ── Shared API types — mirror the real backend payloads ──────────────────

export interface Health {
  status: string;
  version: string;
  llm_models: {
    test_writer: string;
    debugger: string;
  };
  llm_configured: boolean;
  timestamp: string;
}

export interface Project {
  id: string;
  name: string;
  files_count: number;
  uploaded_at: string;
  runs_count: number;
  status: string;
}

export interface SourceFile {
  name: string;
  path: string;
  size: number;
}

export interface RunSummary {
  id: string;
  project_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  started_at: string;
  completed_at?: string;
  quality_score?: number | null;
  tests_passed?: number | null;
  tests_total?: number | null;
  coverage?: number | null;
  error?: string | null;
}

export interface RunStatus {
  run_id: string;
  project_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress: string;
  started_at: string;
  completed_at?: string;
  error?: string | null;
}

export interface SSEEvent {
  status?: RunStatus['status'];
  progress?: string;
  current_agent?: string;
  quality_score?: number;
  coverage?: number;
  tests_passed?: number;
  tests_total?: number;
  error?: string;
  timestamp?: string;
}

// ── Workspace statistics (computed server-side from real run metadata) ──

export interface WorkspaceStats {
  total_projects: number;
  completed_runs: number;
  failed_runs: number;
  total_tests_generated: number;
  average_quality: number | null;
  average_coverage: number | null;
}

// ── Final report (as produced by agents/reporter.py) ─────────────────────

export interface AnalysisFile {
  name: string;
  functions: number;
  classes: number;
  risk_zones: number;
  avg_complexity: number;
  loc: number;
}

export interface AnalysisSummary {
  files: AnalysisFile[];
  total_files: number;
  total_functions: number;
  total_classes: number;
  total_risk_zones: number;
  avg_complexity: number;
  top_risk_functions: Array<{ name: string; file: string; complexity: number }>;
  external_imports: string[];
}

export interface GenerationStats {
  tests_generated: number;
  llm_api_calls: number;
  llm_retries: number;
  llm_total_tokens: number;
  llm_success_rate: number;
  ast_validation_passed: boolean;
  pytest_validation_passed: boolean;
  functions_skipped: string[];
  functions_failed: string[];
  failed_tests: string[];
}

export interface DebugHistoryEntry {
  iteration: number;
  test_name: string;
  error_type: string;
  root_cause: string;
  fix_description: string;
  confidence: 'high' | 'medium' | 'low';
  applied: boolean;
}

export interface CodeSmell {
  type: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  location: string;
  description: string;
  suggestion: string;
  impact: string;
}

export interface TechnicalDebt {
  debt_hours: number;
  debt_cost: number;
  debt_level: 'critical' | 'high' | 'medium' | 'low';
  priority_fixes: CodeSmell[];
  breakdown: {
    code_smells: number;
    failed_tests: number;
    coverage_gap: number;
  };
}

export interface Benchmark {
  overall_percentile: number;
  summary: string;
  benchmarks: Array<{
    metric: string;
    value: number;
    category: string;
    percentile: number;
    industry_avg: number;
    comparison: string;
  }>;
}

export interface MaintenancePrediction {
  monthly_maintenance_hours: number;
  monthly_maintenance_cost: number;
  defect_probability_6mo: number;
  onboarding_days: number;
  refactoring_urgency: number;
  recommendation: string;
}

export interface Recommendation {
  priority: number;
  category: string;
  title: string;
  description: string;
  impact: {
    hours_saved: number;
    cost_saved: number;
    risk_reduction: string;
  };
  action_steps: string[];
  affected_functions?: string[];
}

export interface DefectHotspot {
  function: string;
  defect_probability: number;
  risk_level: 'CRITICAL' | 'HIGH' | 'MEDIUM';
  contributing_factors: {
    complexity: number;
    lines: number;
    has_docstring: boolean;
    failed_tests: boolean;
  };
  recommendation: string;
}

export interface TestEffectiveness {
  effectiveness_score: number;
  rating: string;
  confidence_level: string;
  bug_detection_capability: string;
  metrics: {
    coverage: number;
    test_ratio: number;
    pass_rate: number;
  };
  improvement_potential: string;
  next_actions: string[];
}

export interface VelocityImpact {
  current_velocity: string;
  velocity_loss: string;
  potential_gain: string;
  sprint_impact: {
    hours_lost_per_sprint: number;
    story_points_lost: number;
    features_delayed: string;
  };
  roi_of_fixes: {
    investment: string;
    payback_period: string;
    annual_savings: string;
  };
  manager_summary: string;
}

export interface FinalReport {
  project_id: string;
  summary: string;
  quality_score: number;
  coverage_percent: number;
  total_tests: number;
  passed: number;
  failed: number;
  skipped: number;
  complexity_avg: number;
  debug_iterations: number;
  risk_level: 'low' | 'medium' | 'high';

  analysis?: AnalysisSummary;
  generation?: GenerationStats;
  debug_history?: DebugHistoryEntry[];
  test_files?: string[];

  code_smells?: CodeSmell[];
  technical_debt?: TechnicalDebt;
  industry_benchmark?: Benchmark;
  maintenance_prediction?: MaintenancePrediction;
  recommendations?: Recommendation[];

  ml_defect_hotspots?: DefectHotspot[];
  ml_test_effectiveness?: TestEffectiveness;
  ml_velocity_impact?: VelocityImpact;
  ml_refactoring_priorities?: Array<{
    item: string;
    priority_score: number;
    defect_risk: string;
    effort_hours: number;
    expected_savings: string;
    roi_percentage: string;
    urgency: string;
    business_impact: string;
  }>;
}

export interface TestFileMeta {
  filename: string;
  path: string;
  size: number;
}

export interface TestFileContent {
  filename: string;
  content: string;
}
