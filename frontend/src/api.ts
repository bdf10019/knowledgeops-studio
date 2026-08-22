import type {
  AuditLog,
  Collection,
  Dashboard,
  DocumentRecord,
  EvaluationCase,
  EvaluationRun,
  KnowledgeRequest,
  Prompt,
  Provider,
  Role,
  User,
} from './types'

const API_ROOT = import.meta.env.VITE_API_ROOT ?? ''

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, role: Role, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('X-Demo-User', role)
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_ROOT}${path}`, { ...init, headers })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = (await response.json()) as { detail?: string }
      detail = body.detail ?? detail
    } catch {
      // Keep the status message when a proxy returns a non-JSON error page.
    }
    throw new ApiError(detail, response.status)
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const api = {
  me: (role: Role) => request<User>('/api/v1/me', role),
  dashboard: (role: Role) => request<Dashboard>('/api/v1/dashboard', role),
  providers: (role: Role) => request<Provider[]>('/api/v1/providers', role),
  collections: (role: Role) => request<Collection[]>('/api/v1/collections', role),
  documents: (role: Role, collectionId: string) =>
    request<DocumentRecord[]>(`/api/v1/collections/${collectionId}/documents`, role),
  prompts: (role: Role) => request<Prompt[]>('/api/v1/prompts', role),
  requests: (role: Role) => request<KnowledgeRequest[]>('/api/v1/requests', role),
  evaluationRuns: (role: Role) => request<EvaluationRun[]>('/api/v1/evaluations/runs', role),
  evaluationCases: (role: Role) => request<EvaluationCase[]>('/api/v1/evaluations/cases', role),
  audit: (role: Role) => request<AuditLog[]>('/api/v1/audit', role),
  ask: (role: Role, payload: object) =>
    request<KnowledgeRequest>('/api/v1/requests', role, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  review: (role: Role, requestId: string, answer: string, approve: boolean) =>
    request<KnowledgeRequest>(`/api/v1/requests/${requestId}/review`, role, {
      method: 'POST',
      body: JSON.stringify({ answer, approve, note: 'Reviewed in KnowledgeOps Studio' }),
    }),
  upload: (role: Role, collectionId: string, file: File, sourceLabel: string) => {
    const body = new FormData()
    body.append('file', file)
    body.append('source_label', sourceLabel)
    return request<DocumentRecord>(`/api/v1/collections/${collectionId}/documents`, role, {
      method: 'POST',
      body,
    })
  },
  releasePrompt: (role: Role, promptId: string) =>
    request<Prompt>(`/api/v1/prompts/${promptId}/release`, role, { method: 'POST' }),
  runEvaluation: (role: Role, promptId: string, provider?: string) =>
    request<EvaluationRun>('/api/v1/evaluations/runs', role, {
      method: 'POST',
      body: JSON.stringify({ prompt_id: promptId, provider: provider || null }),
    }),
}
