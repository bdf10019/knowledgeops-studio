import {
  Activity,
  ArrowRight,
  BarChart3,
  BookOpen,
  Bot,
  Check,
  ChevronRight,
  CircleGauge,
  Clock3,
  Database,
  FileCheck2,
  FlaskConical,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  RefreshCw,
  ScrollText,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { ApiError, api } from './api'
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

type View = 'dashboard' | 'ask' | 'knowledge' | 'prompts' | 'evaluations' | 'audit'

const navigation: Array<{ id: View; label: string; icon: typeof Activity }> = [
  { id: 'dashboard', label: '營運總覽', icon: LayoutDashboard },
  { id: 'ask', label: '知識任務', icon: MessageSquareText },
  { id: 'knowledge', label: '知識庫', icon: Database },
  { id: 'prompts', label: 'Prompt 版本', icon: Settings2 },
  { id: 'evaluations', label: '品質評測', icon: FlaskConical },
  { id: 'audit', label: '稽核軌跡', icon: ScrollText },
]

const roleLabels: Record<Role, string> = {
  admin: '系統管理員',
  editor: '知識編輯者',
  reviewer: '品質審核者',
  viewer: '一般使用者',
}

const emptyDashboard: Dashboard = {
  total_requests: 0,
  completed_requests: 0,
  review_queue: 0,
  document_count: 0,
  prompt_versions: 0,
  evaluation_runs: 0,
  median_latency_ms: 0,
  citation_rate: 0,
  provider_counts: {},
}

const formatDate = (value: string) =>
  new Intl.DateTimeFormat('zh-TW', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(
    new Date(value),
  )

const percent = (value: number) => `${Math.round(value * 100)}%`

function StatusPill({ status }: { status: string }) {
  const tone = ['completed', 'released', 'passed', 'active'].includes(status)
    ? 'success'
    : ['review_required', 'draft', 'running'].includes(status)
      ? 'warning'
      : 'neutral'
  const labels: Record<string, string> = {
    completed: '已完成',
    review_required: '待人工確認',
    released: '正式版',
    draft: '草稿',
    passed: '通過',
    running: '執行中',
    rejected: '已退回',
  }
  return <span className={`status-pill ${tone}`}>{labels[status] ?? status}</span>
}

function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  accent,
}: {
  label: string
  value: string | number
  hint: string
  icon: typeof Activity
  accent: string
}) {
  return (
    <article className="metric-card">
      <div className="metric-icon" style={{ background: accent }}><Icon size={20} /></div>
      <div className="metric-copy"><span>{label}</span><strong>{value}</strong><small>{hint}</small></div>
    </article>
  )
}

function DashboardView({ dashboard, providers, requests }: { dashboard: Dashboard; providers: Provider[]; requests: KnowledgeRequest[] }) {
  return (
    <>
      <div className="page-heading">
        <div><p className="eyebrow">Outcome command center</p><h1>營運總覽</h1><p>從知識問題到可稽核答案，掌握品質、速度與人工介入。</p></div>
        <div className="live-badge"><span /> 系統在線</div>
      </div>
      <section className="metrics-grid">
        <MetricCard label="完成任務" value={dashboard.completed_requests} hint={`共 ${dashboard.total_requests} 筆請求`} icon={Check} accent="#d8f7e8" />
        <MetricCard label="引用覆蓋率" value={percent(dashboard.citation_rate)} hint="回答具來源證據" icon={FileCheck2} accent="#dff2ff" />
        <MetricCard label="待審核" value={dashboard.review_queue} hint="低證據自動攔截" icon={ShieldCheck} accent="#fff0d5" />
        <MetricCard label="中位延遲" value={`${Math.round(dashboard.median_latency_ms)} ms`} hint="端到端處理時間" icon={Clock3} accent="#efe8ff" />
      </section>
      <section className="dashboard-grid">
        <article className="panel outcome-panel">
          <div className="panel-title"><div><span className="section-kicker">Business outcome</span><h2>成果漏斗</h2></div><CircleGauge size={22} /></div>
          <div className="funnel">
            <div><strong>{dashboard.total_requests}</strong><span>進入工作流</span></div><ChevronRight />
            <div><strong>{dashboard.completed_requests}</strong><span>可信回答</span></div><ChevronRight />
            <div><strong>{dashboard.review_queue}</strong><span>人工接手</span></div>
          </div>
          <div className="progress-row"><span>自動完成率</span><strong>{percent(dashboard.total_requests ? dashboard.completed_requests / dashboard.total_requests : 0)}</strong></div>
          <div className="progress-track"><i style={{ width: `${dashboard.total_requests ? (dashboard.completed_requests / dashboard.total_requests) * 100 : 0}%` }} /></div>
        </article>
        <article className="panel">
          <div className="panel-title"><div><span className="section-kicker">Model gateway</span><h2>模型連線</h2></div><Bot size={22} /></div>
          <div className="provider-list">
            {providers.map((provider) => <div className="provider-row" key={provider.name}><div className={`provider-mark ${provider.name}`}><Sparkles size={16} /></div><div><strong>{provider.name}</strong><span>{provider.model}</span></div><span className={provider.live_calls_enabled ? 'connection ready' : 'connection'}>{provider.live_calls_enabled ? 'Live' : provider.name === 'mock' ? 'Offline' : '未設定'}</span></div>)}
          </div>
        </article>
        <article className="panel span-two">
          <div className="panel-title"><div><span className="section-kicker">Recent workflow</span><h2>最近知識任務</h2></div><Activity size={22} /></div>
          <div className="table-wrap"><table><thead><tr><th>問題</th><th>模型</th><th>證據</th><th>耗時</th><th>狀態</th></tr></thead><tbody>
            {requests.slice(0, 5).map((item) => <tr key={item.id}><td><strong>{item.question}</strong><small>{formatDate(item.created_at)}</small></td><td>{item.provider}<small>{item.model}</small></td><td>{percent(item.evidence_score)}</td><td>{Math.round(item.latency_ms)} ms</td><td><StatusPill status={item.status} /></td></tr>)}
            {!requests.length && <tr><td colSpan={5} className="empty-cell">送出第一個問題後，工作流結果會出現在這裡。</td></tr>}
          </tbody></table></div>
        </article>
      </section>
    </>
  )
}

function AskView({ role, collections, prompts, providers, requests, onChanged }: { role: Role; collections: Collection[]; prompts: Prompt[]; providers: Provider[]; requests: KnowledgeRequest[]; onChanged: () => Promise<void> }) {
  const [question, setQuestion] = useState('Prompt 版本發布前需要通過哪些品質檢查？')
  const [collectionId, setCollectionId] = useState(collections[0]?.id ?? '')
  const [promptId, setPromptId] = useState(prompts.find((item) => item.status === 'released')?.id ?? prompts[0]?.id ?? '')
  const [provider, setProvider] = useState('mock')
  const [result, setResult] = useState<KnowledgeRequest | null>(requests[0] ?? null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { if (!collectionId && collections[0]) setCollectionId(collections[0].id) }, [collectionId, collections])
  useEffect(() => { if (!promptId && prompts[0]) setPromptId(prompts[0].id) }, [promptId, prompts])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      const answer = await api.ask(role, { question, collection_id: collectionId, prompt_id: promptId || null, provider, process_now: true })
      setResult(answer); await onChanged()
    } catch (caught) { setError(caught instanceof Error ? caught.message : '送出失敗') } finally { setBusy(false) }
  }

  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">Grounded answer workflow</p><h1>知識任務</h1><p>選擇知識範圍與模型，輸出附帶引用、證據分數及處理軌跡。</p></div></div>
      <section className="ask-layout">
        <form className="panel ask-form" onSubmit={submit}>
          <div className="panel-title"><div><span className="section-kicker">Input</span><h2>建立任務</h2></div><MessageSquareText size={22} /></div>
          <label>你的問題<textarea value={question} onChange={(event) => setQuestion(event.target.value)} rows={5} minLength={5} required /></label>
          <div className="form-grid">
            <label>知識庫<select value={collectionId} onChange={(event) => setCollectionId(event.target.value)} required>{collections.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
            <label>模型供應商<select value={provider} onChange={(event) => setProvider(event.target.value)}>{providers.map((item) => <option value={item.name} key={item.name}>{item.name}{!item.live_calls_enabled && item.name !== 'mock' ? '（模擬回退）' : ''}</option>)}</select></label>
          </div>
          <label>Prompt 版本<select value={promptId} onChange={(event) => setPromptId(event.target.value)}>{prompts.map((item) => <option value={item.id} key={item.id}>{item.name} v{item.version} · {item.status}</option>)}</select></label>
          {error && <div className="error-banner">{error}</div>}
          <button className="primary-button" disabled={busy || !collectionId || !question.trim()}>{busy ? <RefreshCw className="spin" size={18} /> : <Send size={18} />}{busy ? '處理中…' : '執行知識工作流'}</button>
          <p className="form-note"><ShieldCheck size={15} /> 證據不足時不猜測，轉入人工審核佇列。</p>
        </form>
        <article className="panel answer-panel">
          <div className="panel-title"><div><span className="section-kicker">Outcome</span><h2>可信回答</h2></div>{result && <StatusPill status={result.status} />}</div>
          {result ? <>
            <div className="answer-meta"><span><Bot size={15} /> {result.provider} / {result.model}</span><span><Clock3 size={15} /> {Math.round(result.latency_ms)} ms</span><span><FileCheck2 size={15} /> 證據 {percent(result.evidence_score)}</span></div>
            <div className="answer-copy">{result.answer}</div>
            <h3>來源引用</h3><div className="citations">{result.citations_json.map((citation, index) => <details key={citation.chunk_id}><summary><span>{index + 1}</span>{citation.filename}<small>{percent(citation.score)}</small></summary><p>{citation.quote}</p></details>)}{!result.citations_json.length && <div className="empty-state"><ShieldCheck /><p>目前沒有足夠證據，答案已交由人工確認。</p></div>}</div>
            <details className="trace"><summary>檢視處理軌跡</summary><pre>{JSON.stringify(result.trace_json, null, 2)}</pre></details>
          </> : <div className="empty-state tall"><Sparkles /><h3>等待第一個任務</h3><p>回答、引用與品質指標會集中顯示在這裡。</p></div>}
        </article>
      </section>
    </>
  )
}

function KnowledgeView({ role, collections }: { role: Role; collections: Collection[] }) {
  const [activeId, setActiveId] = useState(collections[0]?.id ?? '')
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [sourceLabel, setSourceLabel] = useState('內部公開範例')
  const [message, setMessage] = useState('')
  const active = collections.find((item) => item.id === activeId)

  const load = useCallback(async () => { if (activeId) setDocuments(await api.documents(role, activeId)) }, [activeId, role])
  useEffect(() => { if (!activeId && collections[0]) setActiveId(collections[0].id) }, [activeId, collections])
  useEffect(() => { void load() }, [load])

  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file || !activeId) return
    try { await api.upload(role, activeId, file, sourceLabel); setMessage(`${file.name} 已完成解析、切塊與索引`); await load() }
    catch (caught) { setMessage(caught instanceof Error ? caught.message : '上傳失敗') }
    event.target.value = ''
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">Controlled knowledge</p><h1>知識庫</h1><p>文件版本、雜湊去重、切塊索引與集合 ACL 在同一條治理鏈上。</p></div>{active?.can_write && <label className="upload-button"><UploadCloud size={17} /> 上傳文件<input type="file" accept=".txt,.md,.csv,.json,.pdf" onChange={upload} /></label>}</div>
    {message && <div className="notice-banner"><Check size={16} /> {message}<button onClick={() => setMessage('')} aria-label="關閉"><X size={15} /></button></div>}
    <section className="knowledge-layout"><aside className="panel collection-list"><span className="section-kicker">Collections</span>{collections.map((item) => <button className={item.id === activeId ? 'active' : ''} onClick={() => setActiveId(item.id)} key={item.id}><BookOpen size={18} /><span><strong>{item.name}</strong><small>{item.document_count} 份文件</small></span><ChevronRight size={16} /></button>)}</aside>
      <article className="panel"><div className="panel-title"><div><span className="section-kicker">Documents</span><h2>{active?.name ?? '知識文件'}</h2><p>{active?.description}</p></div><Database size={22} /></div>
        {active?.can_write && <div className="source-control"><label>本次來源標籤<input value={sourceLabel} onChange={(event) => setSourceLabel(event.target.value)} /></label><small>僅儲存標籤與文件內容；不會把本機路徑寫入資料庫。</small></div>}
        <div className="document-list">{documents.map((doc) => <div className="document-card" key={doc.id}><div className="file-icon"><FileCheck2 /></div><div><strong>{doc.filename}</strong><span>v{doc.version} · {doc.chunk_count} 個知識片段 · {doc.source_label || '未標記來源'}</span><small>SHA-256 {doc.sha256.slice(0, 16)}… · {formatDate(doc.created_at)}</small></div><StatusPill status={doc.status} /></div>)}{!documents.length && <div className="empty-state tall"><Database /><p>這個集合尚無文件。</p></div>}</div>
      </article></section>
  </>
}

function PromptsView({ role, prompts, onChanged }: { role: Role; prompts: Prompt[]; onChanged: () => Promise<void> }) {
  const [selected, setSelected] = useState<Prompt | null>(prompts[0] ?? null)
  useEffect(() => { if (!selected && prompts[0]) setSelected(prompts[0]) }, [prompts, selected])
  async function release(id: string) { await api.releasePrompt(role, id); await onChanged() }
  return <>
    <div className="page-heading"><div><p className="eyebrow">Prompt operations</p><h1>Prompt 版本</h1><p>每次調校都有不可變版本、設定雜湊與明確發布狀態。</p></div></div>
    <section className="prompt-layout"><div className="panel prompt-list"><div className="panel-title"><div><span className="section-kicker">Registry</span><h2>版本紀錄</h2></div><Settings2 size={22} /></div>{prompts.map((prompt) => <button className={selected?.id === prompt.id ? 'active' : ''} onClick={() => setSelected(prompt)} key={prompt.id}><div><strong>{prompt.name} <b>v{prompt.version}</b></strong><span>{prompt.provider} · {prompt.model}</span></div><StatusPill status={prompt.status} /></button>)}</div>
      <article className="panel prompt-detail">{selected ? <><div className="panel-title"><div><span className="section-kicker">Configuration</span><h2>{selected.name} v{selected.version}</h2></div>{role === 'admin' && selected.status !== 'released' && <button className="secondary-button" onClick={() => void release(selected.id)}><Check size={16} /> 發布此版本</button>}</div>
        <div className="config-grid"><div><span>Provider</span><strong>{selected.provider}</strong></div><div><span>Temperature</span><strong>{selected.temperature}</strong></div><div><span>Retrieval K</span><strong>{selected.retrieval_k}</strong></div><div><span>最低證據</span><strong>{percent(selected.min_evidence_score)}</strong></div></div>
        <h3>系統指令</h3><pre className="prompt-copy">{selected.system_prompt}</pre><h3>使用者模板</h3><pre className="prompt-copy">{selected.user_template}</pre><div className="hash-row"><ShieldCheck size={16} /> 設定雜湊 <code>{selected.sha256}</code></div></> : null}</article></section>
  </>
}

function EvaluationsView({ role, prompts, runs, cases, onChanged }: { role: Role; prompts: Prompt[]; runs: EvaluationRun[]; cases: EvaluationCase[]; onChanged: () => Promise<void> }) {
  const [promptId, setPromptId] = useState(prompts[0]?.id ?? '')
  const [busy, setBusy] = useState(false)
  async function run() { setBusy(true); try { await api.runEvaluation(role, promptId); await onChanged() } finally { setBusy(false) } }
  const latest = runs[0]
  return <>
    <div className="page-heading"><div><p className="eyebrow">Quality gate</p><h1>品質評測</h1><p>用固定案例比較 Prompt，避免靠主觀感受發布模型功能。</p></div><div className="inline-action"><select aria-label="評測 Prompt" value={promptId} onChange={(event) => setPromptId(event.target.value)}>{prompts.map((item) => <option value={item.id} key={item.id}>{item.name} v{item.version}</option>)}</select><button className="primary-button compact" disabled={busy || !promptId} onClick={() => void run()}>{busy ? <RefreshCw className="spin" size={17} /> : <FlaskConical size={17} />} 執行評測</button></div></div>
    {latest && <section className="metrics-grid evaluation-metrics"><MetricCard label="案例通過率" value={percent(latest.pass_rate)} hint={`${latest.case_count} 個固定案例`} icon={Check} accent="#d8f7e8" /><MetricCard label="引用率" value={percent(latest.citation_rate)} hint="回答附可追溯來源" icon={FileCheck2} accent="#dff2ff" /><MetricCard label="拒答準確率" value={percent(latest.refusal_accuracy)} hint="範圍外問題不臆測" icon={ShieldCheck} accent="#fff0d5" /><MetricCard label="中位延遲" value={`${Math.round(latest.median_latency_ms)} ms`} hint={`${latest.provider} / ${latest.model}`} icon={Clock3} accent="#efe8ff" /></section>}
    <section className="dashboard-grid"><article className="panel"><div className="panel-title"><div><span className="section-kicker">Test set</span><h2>固定評測案例</h2></div><span className="count-badge">{cases.length}</span></div><div className="case-list">{cases.map((item) => <div key={item.id}><span className={item.should_answer ? 'answerable' : 'refusal'}>{item.should_answer ? '應回答' : '應拒答'}</span><div><strong>{item.name}</strong><p>{item.question}</p><small>{item.expected_terms.join(' · ') || '無指定關鍵詞'}</small></div></div>)}</div></article>
      <article className="panel"><div className="panel-title"><div><span className="section-kicker">History</span><h2>評測紀錄</h2></div><BarChart3 size={22} /></div><div className="run-list">{runs.map((item) => <div key={item.id}><div className="score-ring" style={{ '--score': `${item.pass_rate * 360}deg` } as React.CSSProperties}><span>{percent(item.pass_rate)}</span></div><div><strong>{item.provider} / {item.model}</strong><span>{formatDate(item.created_at)} · {item.case_count} cases</span></div><StatusPill status={item.status} /></div>)}{!runs.length && <div className="empty-state tall"><FlaskConical /><p>尚未執行評測。</p></div>}</div></article></section>
  </>
}

function AuditView({ logs, allowed }: { logs: AuditLog[]; allowed: boolean }) {
  return <><div className="page-heading"><div><p className="eyebrow">Governance trail</p><h1>稽核軌跡</h1><p>保留誰在何時對知識、Prompt 與回答做了什麼變更。</p></div></div>
    <article className="panel">{allowed ? <div className="audit-timeline">{logs.map((log) => <div key={log.id}><span className="timeline-dot" /><time>{formatDate(log.created_at)}</time><div><strong>{log.action}</strong><p>{log.resource_type} · {log.resource_id}</p><code>{JSON.stringify(log.detail_json)}</code></div></div>)}{!logs.length && <div className="empty-state tall"><ScrollText /><p>尚無稽核事件。</p></div>}</div> : <div className="empty-state access-denied"><ShieldCheck /><h2>僅管理員可讀取稽核紀錄</h2><p>切換 Demo 身分可驗證角色權限與資料存取控管。</p></div>}</article>
  </>
}

export default function App() {
  const [view, setView] = useState<View>('dashboard')
  const [role, setRole] = useState<Role>('admin')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [user, setUser] = useState<User | null>(null)
  const [dashboard, setDashboard] = useState<Dashboard>(emptyDashboard)
  const [providers, setProviders] = useState<Provider[]>([])
  const [collections, setCollections] = useState<Collection[]>([])
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [requests, setRequests] = useState<KnowledgeRequest[]>([])
  const [runs, setRuns] = useState<EvaluationRun[]>([])
  const [cases, setCases] = useState<EvaluationCase[]>([])
  const [logs, setLogs] = useState<AuditLog[]>([])

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    setError('')
    try {
      const [me, overview, modelProviders, knowledge, promptRows, requestRows, runRows, caseRows] = await Promise.all([
        api.me(role), api.dashboard(role), api.providers(role), api.collections(role), api.prompts(role), api.requests(role), api.evaluationRuns(role), api.evaluationCases(role),
      ])
      setUser(me); setDashboard(overview); setProviders(modelProviders); setCollections(knowledge); setPrompts(promptRows); setRequests(requestRows); setRuns(runRows); setCases(caseRows)
      setLogs(role === 'admin' ? await api.audit(role) : [])
    } catch (caught) {
      const message = caught instanceof ApiError && caught.status === 0 ? 'API 尚未啟動' : caught instanceof Error ? caught.message : '無法讀取資料'
      setError(message)
    } finally { setLoading(false) }
  }, [role])

  useEffect(() => { void load() }, [load])
  const activeLabel = useMemo(() => navigation.find((item) => item.id === view)?.label ?? '', [view])

  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
      <div className="brand"><div className="brand-mark"><Sparkles /></div><div><strong>KnowledgeOps</strong><span>STUDIO</span></div><button className="close-menu" onClick={() => setMobileOpen(false)} aria-label="關閉選單"><X /></button></div>
      <div className="workspace-label">工作空間</div><div className="workspace-card"><div>KS</div><span><strong>企業知識中樞</strong><small>Production demo</small></span></div>
      <nav aria-label="主選單">{navigation.map(({ id, label, icon: Icon }) => <button key={id} className={view === id ? 'active' : ''} onClick={() => { setView(id); setMobileOpen(false) }}><Icon size={19} /><span>{label}</span>{id === 'ask' && dashboard.review_queue > 0 && <b>{dashboard.review_queue}</b>}</button>)}</nav>
      <div className="sidebar-foot"><div className="privacy-card"><ShieldCheck size={19} /><div><strong>資料邊界已啟用</strong><span>ACL · Audit · No training</span></div></div><span>v1.0.1 · Offline ready</span></div>
    </aside>
    {mobileOpen && <button className="backdrop" onClick={() => setMobileOpen(false)} aria-label="關閉選單" />}
    <main>
      <header><button className="menu-button" onClick={() => setMobileOpen(true)} aria-label="開啟選單"><Menu /></button><div className="breadcrumb"><span>KnowledgeOps</span><ChevronRight size={14} /><strong>{activeLabel}</strong></div><div className="header-actions"><button className="icon-button" onClick={() => void load()} aria-label="重新整理"><RefreshCw size={18} /></button><label className="role-switcher"><div className="avatar">{role.slice(0, 1).toUpperCase()}</div><span><small>Demo 身分</small><strong>{user?.display_name ?? roleLabels[role]}</strong></span><select aria-label="切換 Demo 身分" value={role} onChange={(event) => setRole(event.target.value as Role)}><option value="admin">系統管理員</option><option value="editor">知識編輯者</option><option value="reviewer">品質審核者</option><option value="viewer">一般使用者</option></select></label></div></header>
      <div className="content">
        {error && <div className="error-banner global"><Bot size={18} /><div><strong>無法連線後端</strong><span>{error}。請先執行 README 的啟動指令。</span></div><button onClick={() => void load()}><RefreshCw size={16} />重試</button></div>}
        {loading ? <div className="loading-screen"><div className="loader" /><strong>載入工作空間</strong><span>同步知識、Prompt 與營運指標…</span></div> : <>
          {view === 'dashboard' && <DashboardView dashboard={dashboard} providers={providers} requests={requests} />}
          {view === 'ask' && <AskView role={role} collections={collections} prompts={prompts} providers={providers} requests={requests} onChanged={() => load(true)} />}
          {view === 'knowledge' && <KnowledgeView role={role} collections={collections} />}
          {view === 'prompts' && <PromptsView role={role} prompts={prompts} onChanged={() => load(true)} />}
          {view === 'evaluations' && <EvaluationsView role={role} prompts={prompts} runs={runs} cases={cases} onChanged={() => load(true)} />}
          {view === 'audit' && <AuditView logs={logs} allowed={role === 'admin'} />}
        </>}
      </div>
    </main>
  </div>
}
