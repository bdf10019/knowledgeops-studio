import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const fixtures: Record<string, unknown> = {
  '/api/v1/me': { id: 'u1', username: 'admin', display_name: 'Demo Admin', role: 'admin' },
  '/api/v1/dashboard': { total_requests: 3, completed_requests: 2, review_queue: 1, document_count: 4, prompt_versions: 1, evaluation_runs: 1, median_latency_ms: 21, citation_rate: 1, provider_counts: { mock: 3 } },
  '/api/v1/providers': [{ name: 'mock', configured: true, model: 'mock-grounded-v1', supports_structured_output: true, live_calls_enabled: false }],
  '/api/v1/collections': [{ id: 'c1', name: '示範知識庫', description: 'Synthetic data', document_count: 4, can_write: true, created_at: '2026-01-01T00:00:00Z' }],
  '/api/v1/prompts': [{ id: 'p1', name: 'grounded-answer', version: 1, status: 'released', provider: 'mock', model: 'mock-grounded-v1', temperature: 0.1, retrieval_k: 4, min_evidence_score: 0.18, sha256: 'abc', system_prompt: 'Use only evidence and cite every claim.', user_template: '{{question}} {{context}}', created_at: '2026-01-01T00:00:00Z' }],
  '/api/v1/requests': [],
  '/api/v1/evaluations/runs': [],
  '/api/v1/evaluations/cases': [],
  '/api/v1/audit': [],
}

describe('KnowledgeOps Studio', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      const value = fixtures[url]
      return new Response(JSON.stringify(value ?? []), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows outcome metrics from the API', async () => {
    render(<App />)
    expect(await screen.findByRole('heading', { name: '營運總覽' })).toBeInTheDocument()
    expect(screen.getByText('引用覆蓋率')).toBeInTheDocument()
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByLabelText('切換 Demo 身分')).toHaveValue('admin')
  })

  it('navigates to the knowledge workflow', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: '營運總覽' })
    fireEvent.click(screen.getByRole('button', { name: /知識任務/ }))
    await waitFor(() => expect(screen.getByRole('heading', { name: '知識任務' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '執行知識工作流' })).toBeEnabled()
  })
})
