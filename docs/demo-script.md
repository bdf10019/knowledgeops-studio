# 展示腳本（約 8 分鐘）

1. **營運總覽**：先說明目標是可信成果，不是聊天介面；指出引用率、待審核與延遲。
2. **知識任務**：用預設 Prompt 發布問題，展示 answer、單一正確來源、證據分數與 trace。
3. **範圍外拒答**：詢問天氣或其他文件未涵蓋內容，展示 review_required。
4. **角色權限**：切到 viewer 看不到稽核；切回 admin 顯示所有高價值操作。
5. **文件治理**：說明 SHA-256 去重、版本與來源標籤；相同文件上傳不重複索引。
6. **PromptOps**：展示版本、設定雜湊、retrieval k 與證據門檻。
7. **品質評測**：執行固定 6 題，說明 refusal 與 citation 的發布意義。
8. **架構與誠實邊界**：指出 mock/SQLite 是零成本展示 adapter，正式路徑已有 pgvector、Redis、worker、
   Docker、Alembic 與 n8n，但 OIDC、雲端與 live provider 驗證仍列為待辦。
