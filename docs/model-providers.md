# 模型供應商介面

## 統一契約

所有 adapter 接收相同的 `GenerationRequest`：問題、系統指令、已授權證據、model、輸出 token 上限與
不可逆 safety id；回傳 `GenerationResult`：answer、chunk citations、needs_review、usage、latency 與
供應商 response id。

供應商原始 response 不直接回到前端。伺服器先正規化 JSON，再驗證 citation chunk id 是否真的出現在
本次 selected contexts。

## API 對應

| Provider | Endpoint / 格式 | v1 的資料控制 |
|---|---|---|
| OpenAI | Responses API `POST /v1/responses` + JSON Schema | `store=false`、hashed `safety_identifier` |
| Anthropic | Messages API `POST /v1/messages` + `output_config.format` | 不傳姓名/信箱，只傳被授權 context |
| Gemini | `models/{model}:generateContent` + JSON response schema | Key 只在 Header，不寫 URL、DB 或 log |
| Mock | process-local deterministic adapter | 完全離線、零費用、適合 CI |

官方參考：

- [OpenAI Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- [Claude Messages API](https://platform.claude.com/docs/en/api/messages/create)
- [Gemini GenerateContent API](https://ai.google.dev/api/generate-content)

## Model 與參數策略

預設 model 可由環境變數覆寫：`OPENAI_MODEL`、`ANTHROPIC_MODEL`、`GEMINI_MODEL`。v1 預設採穩定文字模型，
但 model lifecycle 會變動，正式環境必須由設定管理與評測 gate 控制升級。

不同模型對 sampling 的支援不同：GPT-5 系列與 Claude 5 不強制傳入 temperature；Gemini 3.7 adapter
也不傳已棄用的 sampling 參數。Prompt 版本仍保存 temperature，供支援該參數的模型與離線比較使用。

## 錯誤與 fallback

- 未設定 Key：不做外部 HTTP request，工作流留下原因後回退 mock。
- HTTP 4xx/5xx：只保存 status code，不把可能含敏感內容的 response body寫入 error。
- timeout 或無效 JSON：任務 failed 且需要人工介入。
- 引用 ID 不合法：丟棄引用並進入 review_required。

## 付費與隱私提醒

填入 Key 並選擇 live provider 會把本次問題與通過 ACL/相關性 gate 的文件片段傳給該供應商，且可能產生
費用。部署者必須先確認資料處理條款、地區、保留政策、ZDR/enterprise 設定與內部資料分類；本專案不會
代替這些組織層決策。
