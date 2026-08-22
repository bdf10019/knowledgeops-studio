# Contributing

1. 不提交 `.env`、Key、Token、私人文件、客戶資料、執行期資料庫或大於 1 MiB 的產物。
2. 新功能需補最小可重現測試；權限、引用、評測與 migration 變更需有 regression case。
3. 執行 `scripts/verify.ps1`，確認 Python、前端、runtime diagnostics 與 privacy scan 全部通過。
4. Prompt 或 model 預設值變更需附固定題集結果，不能只以單一範例宣稱改善。
5. 保持核心領域邏輯與特定供應商解耦；新 adapter 必須正規化錯誤並驗證結構化輸出。
