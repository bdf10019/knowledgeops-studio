export type Role = 'admin' | 'editor' | 'reviewer' | 'viewer'

export interface User {
  id: string
  username: string
  display_name: string
  role: Role
}

export interface Dashboard {
  total_requests: number
  completed_requests: number
  review_queue: number
  document_count: number
  prompt_versions: number
  evaluation_runs: number
  median_latency_ms: number
  citation_rate: number
  provider_counts: Record<string, number>
}

export interface Provider {
  name: string
  configured: boolean
  model: string
  supports_structured_output: boolean
  live_calls_enabled: boolean
}

export interface Collection {
  id: string
  name: string
  description: string
  document_count: number
  can_write: boolean
  created_at: string
}

export interface DocumentRecord {
  id: string
  filename: string
  content_type: string
  sha256: string
  version: number
  status: string
  source_label: string
  chunk_count: number
  created_at: string
}

export interface Prompt {
  id: string
  name: string
  version: number
  status: string
  provider: string
  model: string
  temperature: number
  retrieval_k: number
  min_evidence_score: number
  sha256: string
  system_prompt: string
  user_template: string
  created_at: string
}

export interface Citation {
  chunk_id: string
  document_id: string
  filename: string
  quote: string
  score: number
}

export interface KnowledgeRequest {
  id: string
  question: string
  collection_id: string
  prompt_id: string
  provider: string
  model: string
  status: string
  answer: string
  citations_json: Citation[]
  evidence_score: number
  needs_review: boolean
  latency_ms: number
  input_tokens: number
  output_tokens: number
  estimated_cost: number
  error: string
  trace_json: Record<string, unknown>
  created_at: string
}

export interface EvaluationRun {
  id: string
  prompt_id: string
  provider: string
  model: string
  status: string
  case_count: number
  pass_rate: number
  citation_rate: number
  refusal_accuracy: number
  median_latency_ms: number
  total_estimated_cost: number
  created_at: string
}

export interface EvaluationCase {
  id: string
  name: string
  question: string
  expected_terms: string[]
  should_answer: boolean
}

export interface AuditLog {
  id: string
  actor_id: string
  action: string
  resource_type: string
  resource_id: string
  detail_json: Record<string, unknown>
  created_at: string
}
