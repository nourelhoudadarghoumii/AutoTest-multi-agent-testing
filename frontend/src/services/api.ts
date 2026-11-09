import axios from 'axios';
import type {
  Health,
  Project,
  RunStatus,
  RunSummary,
  SourceFile,
  SSEEvent,
  WorkspaceStats,
  FinalReport,
  TestFileMeta,
  TestFileContent,
} from '../types';

const api = axios.create({
  baseURL: '/',
  headers: { 'Content-Type': 'application/json' },
});

/** Extract a readable message from an axios/backend error. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (detail) return JSON.stringify(detail);
    if (error.response) return `Request failed with status ${error.response.status}.`;
    return 'Cannot reach the AutoTest backend. Is it running on port 8000?';
  }
  return fallback;
}

// ── System ───────────────────────────────────────────────────────────────

export const systemService = {
  getHealth: async (): Promise<Health> => {
    const response = await api.get<Health>('/health');
    return response.data;
  },
  getStats: async (): Promise<WorkspaceStats> => {
    const response = await api.get<WorkspaceStats>('/api/stats');
    return response.data;
  },
};

// ── Projects ─────────────────────────────────────────────────────────────

export const projectService = {
  uploadFiles: async (files: FileList): Promise<{ project_id: string; message: string; files_count: number }> => {
    const formData = new FormData();
    Array.from(files).forEach((file) => formData.append('files', file));
    const response = await api.post('/v1/projects/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  uploadArchive: async (file: File): Promise<{ project_id: string; message: string; files_count: number }> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/v1/projects/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  getProjects: async (): Promise<Project[]> => {
    const response = await api.get<Project[]>('/api/projects');
    return response.data;
  },

  getProject: async (projectId: string): Promise<Project & { runs: RunSummary[] }> => {
    const response = await api.get(`/api/projects/${projectId}`);
    return response.data;
  },

  deleteProject: async (projectId: string): Promise<void> => {
    await api.delete(`/api/projects/${projectId}`);
  },

  renameProject: async (projectId: string, name: string): Promise<{ project_id: string; name: string }> => {
    const response = await api.patch(`/api/projects/${projectId}`, { name });
    return response.data;
  },

  analyzeProject: async (projectId: string, sourceFiles?: string[]): Promise<{ run_id: string; status: string }> => {
    const payload = sourceFiles && sourceFiles.length > 0 ? { source_files: sourceFiles } : {};
    const response = await api.post(`/v1/projects/${projectId}/analyze`, payload);
    return response.data;
  },

  getSourceFiles: async (projectId: string): Promise<SourceFile[]> => {
    const response = await api.get<SourceFile[]>(`/api/projects/${projectId}/source`);
    return response.data;
  },

  getSourceFile: async (projectId: string, filePath: string): Promise<TestFileContent> => {
    const response = await api.get<TestFileContent>(`/api/projects/${projectId}/source/${filePath}`);
    return response.data;
  },

  deleteSourceFile: async (projectId: string, filePath: string): Promise<void> => {
    await api.delete(`/api/projects/${projectId}/source/${filePath}`);
  },

  deleteSourceFilesBatch: async (projectId: string, files: string[]): Promise<void> => {
    await api.post(`/api/projects/${projectId}/source/delete-batch`, { files });
  },
};

// ── Runs ─────────────────────────────────────────────────────────────────

export const runService = {
  getRun: async (runId: string): Promise<RunStatus> => {
    const response = await api.get<RunStatus>(`/v1/runs/${runId}`);
    return response.data;
  },

  getRuns: async (projectId?: string): Promise<RunSummary[]> => {
    const url = projectId ? `/api/runs?project_id=${projectId}` : '/api/runs';
    const response = await api.get<RunSummary[]>(url);
    return response.data;
  },

  getReport: async (runId: string): Promise<FinalReport> => {
    const response = await api.get<{ report: FinalReport }>(`/v1/runs/${runId}/report`);
    return response.data.report;
  },

  getTestFiles: async (runId: string): Promise<TestFileMeta[]> => {
    const response = await api.get<TestFileMeta[]>(`/v1/runs/${runId}/tests`);
    return response.data;
  },

  getTestFile: async (runId: string, filename: string): Promise<TestFileContent> => {
    const response = await api.get<TestFileContent>(`/v1/runs/${runId}/tests/${filename}`);
    return response.data;
  },

  /** Open a browser download for generated tests / package / markdown report. */
  download: (runId: string, kind: 'tests' | 'package' | 'report-md'): void => {
    const suffix = kind === 'tests' ? 'tests/download' : kind === 'package' ? 'package' : 'report?format=markdown';
    window.open(`/v1/runs/${runId}/${suffix}`, '_blank');
  },

  /** Subscribe to live progress via Server-Sent Events. Returns a cleanup fn. */
  streamProgress: (runId: string, onEvent: (data: SSEEvent) => void, onError?: (error: Error) => void): (() => void) => {
    const eventSource = new EventSource(`/v1/runs/${runId}/stream`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as SSEEvent;
        onEvent(data);
        if (data.status === 'completed' || data.status === 'failed') {
          eventSource.close();
        }
      } catch (err) {
        console.error('Failed to parse SSE payload:', err);
      }
    };

    eventSource.onerror = () => {
      if (onError) onError(new Error('Progress stream connection lost.'));
      eventSource.close();
    };

    return () => eventSource.close();
  },
};

export default api;
