# Scraper Flow Studio

`scraper-flow-studio` 是一个基于 DSL 的浏览器爬虫工作流系统。它将 FastAPI 后端、React 可视化工作台与本地 Browser Bridge 扩展组合在一起，用于完成工作流编排、AI 辅助分析，以及列表/详情采集脚本生成。

## 当前范围

- 工作流 DSL 校验与图编辑
- Prompt 预览、骨架脚本生成、完整爬虫脚本生成
- 通过前端直连浏览器扩展完成的选择器检测、字段推断前置取证、分页分析前置取证
- 前端工作台中的脚本与提示词编辑工作区
- 任务管理（CRUD、状态跟踪、资产版本化）
- 用户中心 OAuth2 登录授权（BFF 模式 + Redis 会话）
- 独立的详情页页面采集工具 `page-extractor`（供批处理脚本或手工 CLI 调用）

## 快速开始

### 前置条件

- Python 3.13+
- Node.js 18+（前端构建）
- MySQL 8.0+
- Redis 6.0+
- 用户中心 OAuth2 服务（登录授权）

### 环境配置

复制 `.env` 文件并填写必要配置：

```bash
# 必填：用户中心 OAuth2
USER_CENTER_BASE_URI=https://your-user-center.example.com/pbc/usercenter
USER_CENTER_CLIENT_ID=your-client-id
USER_CENTER_CLIENT_SECRET=your-client-secret
USER_CENTER_REDIRECT_URI=http://127.0.0.1:3101/auth/callback

# 必填：MySQL
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your-password
DB_NAME=crawler_workflow

# 必填：Redis
REDIS_URL=redis://127.0.0.1:6379/0

# 必填：LLM
LLM_PROVIDER=openai        # openai | vllm
API_BASE_URL=
API_TOKEN=
MODEL_NAME=gpt-4
```

### 数据库初始化

```bash
# 自动建表（应用启动时也会自动执行，此脚本用于部署初始化）
uv run python scripts/db_init.py

# 可选：创建数据库 + 建表
uv run python scripts/db_init.py --create-db

# 可选：仅输出 DDL，不执行
uv run python scripts/db_init.py --dry-run
```

### Python 后端

```bash
uv sync
python main.py
```

后端默认地址：`http://127.0.0.1:8000`

### React 工作台

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3101
```

前端默认地址：`http://127.0.0.1:3101`

## 常用命令

```bash
# 后端测试
uv run python -m pytest tests -v

# 详情页 CLI 帮助
page-extractor collect --help

# 前端测试
cd frontend
npm run test

# 前端构建
cd frontend
npm run build

# 前端代码检查
cd frontend
npm run lint

# 数据库初始化
uv run python scripts/db_init.py

# 数据库初始化（含自动建库）
uv run python scripts/db_init.py --create-db
```

## 项目结构

```text
scraper-flow-studio/
├── main.py                    # 应用启动入口（支持 --port 参数）
├── backend/                   # 后端实现
│   ├── app.py                 # FastAPI 应用入口（lifespan / 异常处理 / 路由注册）
│   ├── api/                   # FastAPI 路由层
│   │   ├── auth_routes.py     # OAuth2 登录/回调/登出
│   │   ├── task_routes.py     # 任务 CRUD + 资产管理
│   │   ├── workflow_routes.py # 工作流 DSL 端点
│   │   └── assist_routes.py   # AI 辅助分析端点
│   ├── assist/                # assist 任务编排、JSON 协议、分页恢复
│   ├── auth/                  # OAuth2 BFF + Redis 会话 + 用户中心客户端
│   ├── core/                  # settings / logging / api_response 统一响应封装
│   ├── database/              # MySQL 连接池、DDL 定义、schema 自举
│   │   ├── db.py              # 连接池管理
│   │   └── models.py          # users / tasks / task_assets 表定义
│   ├── llm/                   # LLM client 实现（OpenAI / vLLM）
│   ├── prompts/               # prompt 共享规则、契约、任务与组装器
│   ├── tasks/                 # 任务 schemas 与 services
│   └── workflow/              # workflow schema、编译、脚本生成、沙箱执行
├── packages/
│   ├── page-extractor/        # 独立详情页采集工具与 CLI 运行时
│   └── browser-bridge-extension/ # Chrome 浏览器扩展（选择器检测、字段取证）
├── scripts/
│   └── db_init.py             # 数据库初始化脚本（支持 --create-db / --drop-all / --dry-run）
├── frontend/                  # React 工作台
│   └── src/
│       ├── app/               # 页面组件（首页/工作台/任务列表/任务详情）
│       ├── auth/              # AuthProvider / RequireAuth / AuthCallbackPage
│       ├── features/          # workflow / assist / results / runtime / prompt-workspace
│       ├── services/          # API client + auth API + task API + workflow API
│       ├── components/        # 共享 UI 组件
│       ├── theme/             # 主题配置
│       └── shared/            # 共享资源
├── docs/                      # 项目文档
├── tests/                     # 后端测试
├── output/                    # 运行时输出与日志
└── static/                    # 静态文件服务目录
```

## 技术栈

### 后端

- **FastAPI** — 异步 Web 框架
- **MySQL** — 业务数据持久化（users / tasks / task_assets）
- **Redis** — OAuth state 存储 + 应用会话管理
- **Authlib** — OAuth2 客户端
- **PyMySQL + DBUtils** — 数据库连接池
- **OpenAI SDK** — LLM 调用（支持 OpenAI / vLLM）
- **Playwright** — 浏览器自动化
- **Pydantic** — 数据校验与序列化
- **Uvicorn** — ASGI 服务器

### 前端

- **React 19** + **TypeScript 6**
- **Ant Design 6** — UI 组件库
- **React Flow** (@xyflow/react) — 工作流图编辑器
- **Monaco Editor** — 代码编辑器
- **React Router 7** — 路由
- **Vite 8** — 构建工具
- **Vitest** — 单元测试

## API 端点概览

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/` | 无 | API 说明信息 |
| `GET` | `/api/auth/login?next=/tasks` | 无 | OAuth2 登录，302 重定向到用户中心 |
| `POST` | `/api/auth/callback` | Cookie | OAuth2 回调，换取会话 |
| `GET` | `/api/auth/me` | Bearer | 当前登录用户信息 |
| `POST` | `/api/auth/logout` | Bearer | 销毁会话并退出 |
| `GET/POST` | `/api/tasks/*` | Bearer | 任务 CRUD + 资产管理 |
| `GET/POST` | `/api/workflows/*` | Bearer | 工作流 DSL 端点 |
| `POST` | `/api/assist/*` | Bearer | AI 辅助分析 |

## 登录授权

### 架构概览

本系统采用 **BFF（Backend-For-Frontend）模式** 对接用户中心 OAuth2 授权：

1. 浏览器访问 `GET /api/auth/login` → 后端生成 OAuth `state` 存入 Redis，同时写入 HttpOnly 绑定 Cookie，然后 302 重定向到用户中心授权页
2. 用户在用户中心完成授权 → 用户中心将浏览器回调到前端 `/auth/callback?code=xxx&state=xxx`
3. 前端 `AuthCallbackPage` 读取 URL 中的 `code` 和 `state`，POST 到后端 `POST /api/auth/callback`
4. 后端校验 Cookie 绑定 + Redis 一次性 state → Authlib 换取 accessToken → 调用 `/user/get` 获取用户信息 → 本地 upsert 用户 → 创建 Redis 应用会话 → 返回 `sessionId` + 用户信息
5. 前端将 `sessionId` 存入 `sessionStorage`，后续所有 API 调用通过 `Authorization: Bearer <sessionId>` 请求头携带
6. 后端从请求头解析 `sessionId`，查询 Redis 校验会话有效性

```
浏览器 ──GET /api/auth/login──▶ 后端 ──302──▶ 用户中心授权页
  │                                         │
  │       用户中心回调 /auth/callback?code&state
  │                                         │
  └─────前端 AuthCallbackPage────────────────┘
            │
     POST /api/auth/callback {code, state}
            │
            ▼
    后端：校验 state cookie → 换 token → 取用户 → 创建 session
            │
     返回 {sessionId, user, nextPath}
            │
    前端存 sessionStorage，后续请求带 Bearer 头
```

### 安全机制

- **OAuth state 绑定**：`/api/auth/login` 在重定向前设置 HttpOnly + SameSite=Lax 的 Cookie，`/api/auth/callback` 校验 Cookie 与请求中的 `state` 匹配，防止登录 CSRF / 会话替换攻击
- **一次性 state**：OAuth state 存储在 Redis 中，回调时通过 `GETDEL` 原子消费，不可重放
- **Bearer 认证**：所有受保护 API 通过 `Authorization: Bearer <sessionId>` 请求头认证，sessionId 为 256 位随机令牌
- **会话存储**：前端使用 `sessionStorage` 存储 sessionId，浏览器标签页关闭后自动清除
- **路径白名单**：`/api/auth/login` 的 `next` 参数仅接受同源相对路径，拒绝外部域名和协议跳转

### 前端路由

| 路径 | 认证 | 说明 |
|------|------|------|
| `/` | 公开 | 首页，未登录时显示登录入口 |
| `/auth/callback` | 公开 | OAuth 回调页，自动用 URL 中的 `code`/`state` 换取会话 |
| `/tasks/**` | 需登录 | 任务列表与任务详情页面，由 `RequireAuth` 守卫 |
| `/workbench/**` | 需登录 | 工作台页面，由 `RequireAuth` 守卫 |

## 数据模型

### MySQL 表

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `users` | 用户中心身份本地镜像 | `id`, `external_id` (唯一), `display_name`, `email` |
| `tasks` | 爬虫任务记录 | `id`, `owner_user_id` (FK→users), `name`, `status`, `target_url` |
| `task_assets` | 任务资产版本化存储 | `id`, `task_id` (FK→tasks), `asset_type`, `content`, `version` |

### Redis Key

| Key 格式 | 用途 | TTL |
|----------|------|-----|
| `crawler_workflow:auth:state:{state}` | OAuth 一次性状态，含 `next_path` 和 `code_verifier` | `OAUTH_STATE_TTL_SECONDS`（默认 600s） |
| `crawler_workflow:auth:session:{sessionId}` | 应用会话，含用户快照和上游 token | `SESSION_TTL_HOURS`（默认 24h） |

## 环境变量完整参考

```bash
# ── 应用 ──
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
SECRET_KEY=change-me-in-production

# ── LLM ──
LLM_PROVIDER=openai           # openai | vllm
API_BASE_URL=
API_TOKEN=
MODEL_NAME=gpt-4
SCRIPT_GENERATION_MAX_TOKENS=
SCRIPT_REVIEW_MAX_TOKENS=

# ── 脚本沙箱 ──
SCRIPT_SANDBOX_ENABLED=true
SCRIPT_SANDBOX_TIMEOUT_SECONDS=60

# ── MySQL ──
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=crawler_workflow
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# ── Redis ──
REDIS_URL=redis://127.0.0.1:6379/0
REDIS_KEY_PREFIX=crawler_workflow
REDIS_PASSWORD=
REDIS_DB=0
REDIS_SENTINEL_NODES=          # 可选：Sentinel 模式
REDIS_SENTINEL_MASTER=mymaster
REDIS_SENTINEL_PASSWORD=

# ── 用户中心 OAuth2 ──
USER_CENTER_BASE_URI=
USER_CENTER_CLIENT_ID=
USER_CENTER_CLIENT_SECRET=
USER_CENTER_SCOPE=basic
USER_CENTER_REDIRECT_URI=
USER_CENTER_FRONTEND_URL=

# ── 会话 ──
SESSION_TTL_HOURS=24
OAUTH_STATE_TTL_SECONDS=600

# ── 浏览器 ──
BROWSER_HEADLESS=false
DEFAULT_MAX_PAGES=10
```

## 文档入口

- [docs/backend_tech_guide.md](docs/backend_tech_guide.md) — 后端技术指南
- [docs/technical-development-guide.md](docs/technical-development-guide.md) — 技术开发指南
- [docs/product-planning-guide.md](docs/product-planning-guide.md) — 产品规划
- [docs/full-product-planning-guide.md](docs/full-product-planning-guide.md) — 完整产品规划
- [docs/checklist.md](docs/checklist.md) — 开发检查清单
- [packages/page-extractor/README.md](packages/page-extractor/README.md) — 详情页采集工具
- [packages/browser-bridge-extension/README.md](packages/browser-bridge-extension/README.md) — 浏览器扩展
- [DESIGN.md](DESIGN.md) — 设计规范

## 备注

- `GET /` 当前返回简单的 API 说明信息，主要的编排界面在 React 工作台中。
- 工作台阶段已不再依赖后端浏览器会话中介；浏览器取证由前端直连本地扩展完成。
- 应用启动时自动执行 `ensure_schema()` 建表，也可通过 `scripts/db_init.py` 手动初始化。
- 临时截图、调试输出、一次性规划笔记不应保留在仓库根目录。
