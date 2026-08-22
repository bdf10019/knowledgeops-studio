# Prompt 與 RAG 評測策略

## 目標

評測的作用不是替模型貼上一個總分，而是回答發布決策：新版是否在必要案例上更可靠、是否維持拒答、
是否仍有來源、速度與成本是否可接受。

## v1 指標

| 指標 | 計算方式 | 風險意義 |
|---|---|---|
| Term recall | 預期詞出現在答案的比例 | 核心步驟或限制是否遺漏 |
| Pass rate | 應答題 term recall ≥ 0.5，拒答題判斷正確 | 固定 regression gate |
| Citation rate | 有至少一個通過伺服器白名單的引用 | 是否能追溯來源 |
| Refusal accuracy | 應拒答與實際無引用拒答是否相同 | 防止範圍外臆測 |
| Median latency | 單案例端到端模型階段中位數 | 使用體驗與容量規劃 |
| Estimated cost | 供應商 usage × 版控價格表 | 目前欄位已保留，v1 live price 尚未設定 |

## Offline baseline

`examples/evals/cases.jsonl` 為原創合成資料，共 6 題。執行：

```powershell
knowledgeops evaluate
```

v1 mock baseline：通過率 100%、引用率 83.3%、拒答準確率 100%。引用率不是 100% 的原因是範圍外題
預期沒有引用。Mock 的延遲接近 0 ms，不能用來估計真實模型效能。

## 正式發布 gate 建議

- 必要案例通過率 100%。
- 拒答準確率不得低於目前 released 版本。
- 應答題引用率 100%，且來源必須屬於測試集合。
- P95 latency 與每任務成本不得超過該流程 SLO/budget。
- 安全與權限案例一票否決，不由其他高分抵銷。
- 同一 provider/model 至少重跑多次，以處理非 deterministic 輸出。

## 尚未完成

- 語意相似度、LLM-as-judge、引用 entailment 與人工盲評。
- 真實供應商的 rate-limit、成本與多次採樣報表。
- 資料漂移、文件更新前後的 retrieval recall@k 比較。
- 評測集的標註者一致性與正式簽核流程。
