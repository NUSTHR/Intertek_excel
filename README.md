# Excel Workspace

Excel Workspace is a standalone Excel knowledge-base and Q&A product area. It
combines versioned workbook management, deterministic Excel preprocessing,
persisted document summaries, and multi-turn chat with row-level evidence.

The module remains intentionally isolated from the legacy `D_ass` frontend and
`ragflow_integration_service` backend so it can evolve independently or be
split into its own repository later.

## Applications

- `backend/`: FastAPI service, default port `8090`
- `frontend/`: Vue 3 + Vite app, default port `5174`
- `contracts/`: API contract notes and future OpenAPI exports
- `docs/`: architecture and processing documentation
- `storage/`: runtime artifacts and SQLite data, ignored by Git

## 本地启动

这一节按“零基础、直接复制命令”的标准写。只要你的电脑里已经装好
Python 和 Node.js，就可以一步一步照着执行。

### 启动结果

成功后你会得到：

- 前端页面：`http://127.0.0.1:5174`
- 后端接口：`http://127.0.0.1:8090`
- 健康检查：`http://127.0.0.1:8090/health`

### 启动前准备

先确认你已经安装：

- Python `3.11` 或更高版本
- Node.js `18+` 和 npm

如果你只想把服务跑起来并打开页面，后端可以在没有 API Key 的情况下启动。
但如果你要真正使用“文档摘要”和“聊天问答”，还需要在 `backend/.env`
里配置真实的 LLM API Key。

### Windows 启动步骤

假设你当前已经在项目根目录：

```text
c:\Users\96934\Desktop\Intertek_project\Documentation Assistant\Intertek_excel
```

#### 第 1 步：打开第一个 PowerShell，启动后端

把下面整段命令完整复制进去：

```powershell
Set-Location "c:\Users\96934\Desktop\Intertek_project\Documentation Assistant\Intertek_excel\backend"
Copy-Item .env.example .env -Force
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
```

看到类似下面的输出，就表示后端启动成功：

```text
Uvicorn running on http://127.0.0.1:8090
Application startup complete.
```

#### 第 2 步：打开第二个 PowerShell，启动前端

把下面整段命令完整复制进去：

```powershell
Set-Location "c:\Users\96934\Desktop\Intertek_project\Documentation Assistant\Intertek_excel\frontend"
Copy-Item .env.example .env -Force
npm install
npx vite --host 127.0.0.1 --port 5174
```

看到类似下面的输出，就表示前端启动成功：

```text
VITE ready
Local: http://127.0.0.1:5174/
```

#### 第 3 步：打开浏览器

在浏览器地址栏里输入：

```text
http://127.0.0.1:5174
```

#### 第 4 步：检查后端是否真的可用

如果你想确认后端没有假启动，再打开一个 PowerShell，执行：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8090/health | Select-Object -ExpandProperty Content
```

如果返回：

```json
{"status":"ok"}
```

就说明后端健康检查正常。

### macOS / Linux 启动步骤

#### 第 1 步：启动后端

```bash
cd /path/to/Intertek_excel/backend
cp .env.example .env
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
```

#### 第 2 步：启动前端

另开一个终端：

```bash
cd /path/to/Intertek_excel/frontend
cp .env.example .env
npm install
npx vite --host 127.0.0.1 --port 5174
```

#### 第 3 步：打开页面

```text
http://127.0.0.1:5174
```

### 本地启动时最常见的问题

#### 1. 后端启动时报 `No module named uvicorn`

说明依赖还没装好。回到 `backend` 目录重新执行：

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

macOS / Linux：

```bash
./.venv/bin/python -m pip install -e '.[dev]'
```

#### 2. 前端提示端口被占用

这个项目把前端端口固定为 `5174`。如果该端口已被占用，请先关闭占用它的程序，
再重新执行启动命令。

#### 3. 页面能打开，但摘要/聊天报错

通常是 `backend/.env` 里没有配置 API Key。后端默认支持两组提供方配置：

- SiliconFlow
- DeepSeek Official

`backend/.env.example` 中的关键项如下：

```text
LLM_API_BASE_URL=https://api.siliconflow.cn/v1
LLM_API_KEY=
DEEPSEEK_API_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=
LLM_SUMMARY_PROVIDER=deepseek
LLM_ROUTER_PROVIDER=siliconflow
LLM_ANSWER_PROVIDER=deepseek
```

### 前端开发服务器说明

Vite dev server 当前固定配置如下：

- host: `0.0.0.0`
- port: `5174`
- `strictPort: true`
- proxy: `/api` and `/health` -> `http://127.0.0.1:8090`

## 部署

推荐部署方式：

- 操作系统：Ubuntu 22.04 / 24.04
- 后端：`systemd` 托管 `uvicorn`
- 前端：`npm run build` 后交给 `nginx` 提供静态文件
- 反向代理：`nginx` 将 `/api` 和 `/health` 转发到后端 `8090`

下面给出一套从空白 Linux 服务器开始的单机部署步骤。

### 部署目标

部署完成后：

- 前端由 `nginx` 提供访问
- 后端常驻运行在 `127.0.0.1:8090`
- 浏览器访问 `http://你的服务器IP/` 即可打开页面
- `http://你的服务器IP/health` 和 `http://你的服务器IP/api/...` 由 `nginx` 转发到后端

### 第 1 步：安装系统依赖

在 Ubuntu 服务器执行：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx curl
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### 第 2 步：把项目放到服务器

下面示例统一使用这个目录：

```text
/opt/excel-workspace
```

如果你是通过压缩包上传项目，就先手动把整个 `Intertek_excel` 目录放到：

```text
/opt/excel-workspace
```

最终目录结构应该至少是：

```text
/opt/excel-workspace/backend
/opt/excel-workspace/frontend
```

### 第 3 步：配置后端环境

执行：

```bash
cd /opt/excel-workspace/backend
cp .env.example .env
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e '.[dev]'
```

然后编辑 `backend/.env`，至少保证下面这些项正确：

```text
APP_HOST=127.0.0.1
APP_PORT=8090
APP_CORS_ORIGINS=http://你的服务器IP
EXCEL_DATABASE_PATH=
EXCEL_STORAGE_ROOT=
LLM_API_KEY=你的SiliconFlow密钥
DEEPSEEK_API_KEY=你的DeepSeek密钥
```

如果你暂时只想验证部署链路，不立即使用真实模型，也可以先保留空密钥。
这样后端通常仍然能启动，但摘要和聊天功能不会正常工作。

### 第 4 步：测试后端能否独立启动

执行：

```bash
cd /opt/excel-workspace/backend
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
```

看到类似输出：

```text
Uvicorn running on http://127.0.0.1:8090
Application startup complete.
```

按 `Ctrl + C` 停掉，继续下一步。

### 第 5 步：把后端配置成 systemd 服务

创建服务文件：

```bash
sudo tee /etc/systemd/system/excel-workspace-backend.service > /dev/null <<'EOF'
[Unit]
Description=Excel Workspace Backend
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/excel-workspace/backend
ExecStart=/opt/excel-workspace/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable excel-workspace-backend
sudo systemctl start excel-workspace-backend
sudo systemctl status excel-workspace-backend --no-pager
```

检查健康接口：

```bash
curl http://127.0.0.1:8090/health
```

如果返回：

```json
{"status":"ok"}
```

说明后端部署成功。

### 第 6 步：构建前端

执行：

```bash
cd /opt/excel-workspace/frontend
cp .env.example .env
printf "VITE_EXCEL_WORKSPACE_API_BASE_URL=\nVITE_EXCEL_WORKSPACE_REQUEST_TIMEOUT_MS=30000\nVITE_EXCEL_WORKSPACE_CHAT_TIMEOUT_MS=300000\n" > .env
npm install
npm run build
```

构建完成后，静态文件会在：

```text
/opt/excel-workspace/frontend/dist
```

### 第 7 步：配置 nginx

创建站点配置：

```bash
sudo tee /etc/nginx/sites-available/excel-workspace > /dev/null <<'EOF'
server {
    listen 80;
    server_name _;

    root /opt/excel-workspace/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
```

启用站点并重启 nginx：

```bash
sudo ln -sf /etc/nginx/sites-available/excel-workspace /etc/nginx/sites-enabled/excel-workspace
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
```

### 第 8 步：验证部署结果

在服务器本机执行：

```bash
curl http://127.0.0.1/health
```

在浏览器中打开：

```text
http://你的服务器IP/
```

如果页面能正常打开，并且上传/预览可用，说明部署完成。

### 第 9 步：以后更新代码怎么做

如果你修改了后端代码：

```bash
cd /opt/excel-workspace/backend
./.venv/bin/python -m pip install -e '.[dev]'
sudo systemctl restart excel-workspace-backend
```

如果你修改了前端代码：

```bash
cd /opt/excel-workspace/frontend
npm install
npm run build
sudo systemctl restart nginx
```

## Boundary Rules

- Do not import code from `D_ass`.
- Do not import code from `ragflow_integration_service`.
- Do not register Excel assets in RAGFlow.
- Treat this directory as a standalone product boundary.

## Current Product

Excel Workspace is no longer just an Excel viewer. The current product is a
runnable Excel knowledge-base Q&A MVP with deterministic preprocessing,
persisted workbook understanding, and backend-verified row-level citations.

Current scope:

- Upload Excel workbooks and preserve version history.
- Replace an existing workbook by creating a new version under the same file.
- Parse `.xls`, `.xlsx`, `.xlsm`, `.xltx`, and `.xltm` into deterministic raw artifacts.
- Export raw CSV artifacts, row mappings, and workbook profile JSON.
- Generate and persist document summaries from workbook profiles.
- Edit persisted document summaries after generation.
- Run session-based multi-turn chat with route and answer stages.
- Manage chat sessions with listing, renaming, pinning, and deletion.
- Verify cited row IDs in the backend and let the frontend jump to the source row.
- Hard-delete workbooks together with derived artifacts, summaries, and related chat attachments.

The chat and LLM workflow are now first-class product functionality rather than
temporary demo behavior.

## Architecture

The backend keeps a ports-and-adapters shape with an explicit dialogue workflow
layer:

```text
api/          HTTP routes, request DTOs, response DTOs, error mapping
domain/       pure dataclasses, no framework dependencies
application/  upload, summary, preview, lookup, deletion, chat services
ports/        repository, storage, workbook-reader, llm-client, chat-workflow protocols
adapters/     SQLite, filesystem, workbook reader, LLM, LangGraph dialogue workflow
core/         config, IDs, time, supported-model catalog, application errors
```

Current orchestration details:

- `ChatService` owns business behavior.
- `ports/chat_workflow.py` defines the route -> answer workflow contract.
- `adapters/dialogue/langgraph_chat_workflow.py` runs the production chat chain with LangGraph.
- Application services still depend on `ports/`, not concrete adapters.

## Current Features

- Upload and replacement confirmation:
  - duplicate display names can be checked before upload
  - duplicate uploads return `409` until replacement is explicitly confirmed
  - replacement creates a new version and only activates it after processing succeeds
- File and version management:
  - file list
  - single file lookup
  - file rename
  - active-version lookup
  - version list
  - manual version activation API
- Deterministic Excel processing:
  - stable sheet codes such as `S001`
  - stable row IDs such as `S001_R1`
  - raw CSV export per sheet
  - row-to-original provenance mapping
  - workbook profile JSON
- Sheet inspection:
  - sheet list by version
  - paged sheet preview
  - paged row listing with mappings
  - row lookup by `row_id`
- Document summaries:
  - generated from workbook profile only
  - persisted in SQLite
  - request-level provider/model override
  - manual PATCH editing after generation
- Chat:
  - direct `/chat` API
  - session-based `/messages` API
  - split `/route` and `/answer` APIs
  - selected document and newly attached document reporting
  - attached-document reuse tracking per session
  - stage timing output
  - row-level citations and source trace
  - insufficient-evidence and warning fields in responses
- Chat session management:
  - create
  - list
  - rename
  - pin/unpin
  - delete
- Frontend workspace:
  - file and chat views
  - file search
  - local file pinning
  - summary editing UI
  - schema inspection tab
  - preview CSV export
  - citation click-through and row highlight
  - resizable chat panel
  - resizable preview grid columns and rows

## Supported Models

The backend and frontend currently support these providers:

- `siliconflow`
- `deepseek`

Provider model catalogs:

- SiliconFlow:
  - `inclusionAI/Ling-flash-2.0`
  - `deepseek-ai/DeepSeek-V4-Pro`
  - `Pro/deepseek-ai/DeepSeek-V3.2`
  - `Qwen/Qwen3.6-27B`
  - `Qwen/Qwen3.6-35B-A3B`
- DeepSeek Official:
  - `deepseek-v4-pro`
  - `deepseek-v4-flash`

Default stage models:

- summary: DeepSeek Official `deepseek-v4-pro`
- router: SiliconFlow `Qwen/Qwen3.6-35B-A3B`
- answer: DeepSeek Official `deepseek-v4-pro`

Implementation notes:

- The backend validates model/provider combinations against the provider catalog.
- Summary, router, and answer stages each support independent provider/model selection.
- The backend only sends `enable_thinking=false` for known-compatible model families and avoids unsupported toggles for other models.
- `LLM_PROVIDER=fake` is still supported for local tests without external network calls.

## Public APIs

Health:

```text
GET    /health
```

Excel assets:

```text
POST   /api/excel/files/check-name
POST   /api/excel/files
GET    /api/excel/files
GET    /api/excel/files/{file_id}
PATCH  /api/excel/files/{file_id}
DELETE /api/excel/files/{file_id}
GET    /api/excel/files/{file_id}/active
GET    /api/excel/files/{file_id}/versions
POST   /api/excel/files/{file_id}/versions/{version_id}/activate

GET    /api/excel/versions/{version_id}/sheets
GET    /api/excel/versions/{version_id}/profile
GET    /api/excel/versions/{version_id}/artifacts

GET    /api/excel/sheets/{sheet_id}/preview
GET    /api/excel/sheets/{sheet_id}/rows
GET    /api/excel/sheets/{sheet_id}/rows/{row_id}
```

Document summaries:

```text
POST   /api/excel/versions/{version_id}/summary/generate
GET    /api/excel/versions/{version_id}/summary
PATCH  /api/excel/versions/{version_id}/summary
```

Chat and LLM:

```text
GET    /api/excel/llm/options
POST   /api/excel/chat

POST   /api/excel/chat/sessions
GET    /api/excel/chat/sessions
GET    /api/excel/chat/sessions/{session_id}
PATCH  /api/excel/chat/sessions/{session_id}
DELETE /api/excel/chat/sessions/{session_id}
PATCH  /api/excel/chat/sessions/{session_id}/pin

POST   /api/excel/chat/sessions/{session_id}/messages
POST   /api/excel/chat/sessions/{session_id}/route
POST   /api/excel/chat/sessions/{session_id}/answer
```

## Storage And Data Rules

Runtime data lives under `storage/` unless overridden by environment variables.

Default derived paths:

```text
storage/excel-workspace.sqlite3
storage/
```

Important invariants:

- `file_id` stays stable across replacements.
- `version_id` changes on every new upload version.
- `sheet_id` is per-version/per-sheet.
- `row_id` is deterministic within each sheet.
- failed processing must not replace the previously active version.
- citations are accepted only after backend row-ID verification.

Generated artifacts currently include:

- original uploaded workbook
- raw sheet CSV files
- row mapping records
- workbook profile JSON
- SQLite summary and chat state

## Current Risks

- Chat scope:
  - router still considers active summaries across the knowledge base
  - there is still no explicit per-chat file scope in the API
- Context size:
  - answer stage still sends full selected-document rows
  - large selections can increase latency or exceed provider token limits
- Confirmed model limit:
  - `Pro/deepseek-ai/DeepSeek-V3.2` can fail with provider `400` at answer time when prompt tokens exceed that model's limit
- Citation semantics:
  - backend verifies row IDs exist
  - it does not yet prove semantic claim support beyond existence and attachment scope
- Frontend layout:
  - long chat sessions can still crowd the right-side evidence/chat area
- Frontend/backend upload mismatch:
  - the frontend upload picker currently allows `.csv`
  - the backend upload API only accepts Excel extensions

## Current Priorities

- Add explicit chat file scope.
- Add answer-stage context and token guardrails.
- Improve long-session chat and citation layout.
- Improve chat-stage observability and error diagnostics.
- Extend session inspection beyond metadata-only responses.

## Verification Status

Available local checks in the repository:

```text
backend: ruff check app tests
backend: pytest
frontend: npm run typecheck
frontend: npm run build
```

Latest recorded local status already documented in the repository:

```text
pytest: 22 passed
npm run build: passed
```

## Operational Notes

- `storage/` is ignored by Git and may contain user data.
- Do not delete runtime storage during normal development unless explicitly resetting local state.
- Keep frontend TypeScript types and backend schemas synchronized.
- Keep changes inside this project boundary unless a task explicitly requires integration work elsewhere.
- Backend `.env` supports both SiliconFlow and DeepSeek Official credentials plus per-stage default providers/models.
- Frontend `.env` supports:

```text
VITE_EXCEL_WORKSPACE_API_BASE_URL
VITE_EXCEL_WORKSPACE_REQUEST_TIMEOUT_MS
VITE_EXCEL_WORKSPACE_CHAT_TIMEOUT_MS
```

- For deeper implementation context, read `project_inspection.md`, `docs/architecture.md`, and `docs/processing-pipeline.md`.
