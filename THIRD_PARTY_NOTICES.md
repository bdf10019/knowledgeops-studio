# Third-party notices

現行原創程式授權狀態與歷史範例權利見 [授權說明](LICENSE_INFORMATION.md)。以下是直接相依或選配執行元件的授權摘要；
實際使用時仍以各上游套件隨附的 license 為準。

| 元件 | 用途 | 上游授權/條款 |
|---|---|---|
| FastAPI、SQLAlchemy、Alembic、Pydantic、HTTPX、Uvicorn | Python API 與資料層 | MIT |
| psycopg | PostgreSQL driver | LGPL-3.0（binary package 依上游條款） |
| pgvector-python | Vector type adapter | MIT |
| pypdf | PDF 文字解析 | BSD-3-Clause |
| LangChain text splitters | 文件切塊 | MIT |
| React、Vite、Vitest、Testing Library | Web UI 與測試 | MIT |
| Lucide | UI icons | ISC |
| PostgreSQL、Redis、Nginx | 選配容器 | 各上游授權 |
| n8n | 選配自架 workflow runtime | Sustainable Use License / Enterprise License |

本專案不重新散布 GPT、Claude、Gemini 模型或權重。啟用外部 API 時，使用者必須另外遵守供應商條款、
資料處理政策與費率。Docker image 會在使用者執行 Compose 時由上游 registry 下載，並未提交到 Git。
