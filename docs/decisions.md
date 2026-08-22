# 架構決策與技術債

## 已做決策

### ADR-001：核心功能不依賴付費模型

採 deterministic mock 與 hashing embedding，讓 CI、面試展示與程式審查可以完整重現。代價是 baseline
不代表語意模型品質，因此文件明確區分「流程正確性」與「模型效果」。

### ADR-002：供應商 adapter 不使用大型 agent framework

HTTP adapter 保持薄且透明，方便檢查 payload、隱私與錯誤。LangChain 只用在成熟的文件切塊，不讓核心
領域邏輯綁死特定框架。

### ADR-003：先做 ACL，再做 retrieval

檢索函式必須接收單一已授權 collection id，禁止先跨範圍搜尋再過濾，避免 trace、cache 或 exception
洩漏不該出現的資料。

### ADR-004：模型引用是非信任輸入

模型回傳的 chunk id 必須和本次 selected contexts 比對。若引用為空或無效，即使答案文字看似合理也需
人工審核。

### ADR-005：SQLite 是離線 adapter，PostgreSQL 是部署目標

同一 SQLAlchemy model 在 SQLite 用 JSON 儲存 embedding，在 PostgreSQL 用 pgvector。這讓新使用者不用
Docker 也能展示；Alembic migration 與 Compose 則驗證生產型 schema 路徑。

## 技術債優先序

1. P0：OIDC/JWT、tenant isolation、rate limit、正式 secret manager。
2. P0：外部文件解析 sandbox 與惡意內容掃描。
3. P1：pgvector HNSW 參數調校、正式 embedding service 與學習型 reranker（v1 已做 index 與 SQL cosine top-k）。
4. P1：queue retry、idempotency key、dead-letter、worker heartbeat。
5. P1：供應商實際成本表、circuit breaker、distributed tracing 與 metrics。
6. P2：Prompt diff/rollback UI、評測結果 drill-down、審核 SLA 通知。
7. P2：AWS/GCP IaC、managed database、KMS 與區域化資料邊界。
