# 安全、隱私與資料治理

## v1 已實作

- 集合層 ACL：每次文件讀寫與任務查詢都先驗證集合存取權。
- 角色分工：admin、editor、reviewer、viewer；發布、審核與稽核端點各自限制角色。
- 拒絕越權：未授權請求直接回 403，不洩漏文件是否存在或內容片段。
- 供應商 Key 僅從環境變數讀取；`.env`、資料庫、輸出與上傳目錄由 Git 忽略。
- 文件上傳限制大小與副檔名，PDF/Text 解析錯誤只保留非敏感摘要。
- OpenAI request 設定 `store=false`；`safety_identifier` 使用本機 user id 的 SHA-256 截斷值。
- 模型只能引用本次選出的 chunk id；伺服器會丟棄任何模型自行產生的其他引用。
- 文件採軟刪除並留下 actor、資源與時間的 audit log。
- `scripts/privacy-check.ps1` 掃描已追蹤檔案的 Key 特徵、私人路徑、敏感檔名與大檔案。

## Demo 模式的重要邊界

`X-Demo-User` 是可刻意切換角色的展示 adapter，沒有密碼也不是正式 Authentication。它讓作品可以
離線驗證 Authorization，但不得公開到不受信任網路。正式化時應：

1. 由反向代理或 API 驗證 OIDC/OAuth2 JWT 的 issuer、audience、signature、expiry。
2. 以不可變 subject 映射內部 user id，不信任 Client 傳入的角色。
3. 角色與集合群組由 IdP/SCIM 或受審核的管理流程同步。
4. 加入租戶 id，所有查詢與 unique constraint 都必須包含 tenant scope。

## 威脅與控制

| 威脅 | v1 控制 | 生產強化 |
|---|---|---|
| Prompt injection 文件 | 系統指令、授權集合、引用白名單、低證據 gate | 文件信任分級、內容掃描、指令分類器 |
| 跨集合資料洩漏 | 檢索 SQL 固定 collection id + ACL | tenant RLS 與資料庫 policy |
| Key 洩漏 | env-only、Git ignore、隱私掃描 | Secret Manager、短期憑證與輪替 |
| 模型輸出偽造引用 | 只接受 selected chunk id | 引用 entailment evaluator |
| 濫用與成本暴增 | timeout、token 上限、低證據先拒答 | rate limit、budget、circuit breaker |
| 惡意檔案 | 類型/大小/UTF-8 檢查 | 防毒、sandbox parser、OCR pipeline |
| 稽核遭竄改 | 應用層 append-only 習慣 | WORM sink、簽章與集中 SIEM |

## Git 前檢查

```powershell
git add -A
.\scripts\privacy-check.ps1
git diff --cached --check
```

掃描器是最後一道防線，不取代人工檢查。任何真實客戶文件、私人資料、執行期 DB、`.env`、Key、
Token、模型輸出與大型資料集都不應加入版本控制。
