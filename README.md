# Crawler Workflow

`crawler-workflow` 是一个基于 DSL 的浏览器爬虫工作流系统。它将 FastAPI 后端、React 可视化工作台与本地 Browser Bridge 扩展组合在一起，用于完成工作流编排、AI 辅助分析，以及列表/详情采集脚本生成。

## 当前范围

- 工作流 DSL 校验与图编辑
- Prompt 预览、骨架脚本生成、完整爬虫脚本生成
- 通过前端直连浏览器扩展完成的选择器检测、字段推断前置取证、分页分析前置取证
- 前端工作台中的脚本与提示词编辑工作区
- 独立的详情页页面采集工具 `page-extractor`（供批处理脚本或手工 CLI 调用）

## 快速开始

### Python 后端

```bash
uv sync
python server.py
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
.venv\Scripts\python.exe -m pytest tests -v

# 详情页 CLI 帮助
page-extractor collect --help

# 前端测试
cd frontend
npm run test

# 前端构建
cd frontend
npm run build
```

## 项目结构

```text
crawler-workflow/
├── server.py                  # 根目录兼容启动入口
├── backend/                   # 后端真实实现
│   ├── api/                   # FastAPI 路由层
│   ├── assist/                # assist 任务编排与 JSON 协议
│   ├── auth/                  # 登录授权（OAuth2 BFF + Redis 会话）
│   ├── core/                  # settings / logging / api_response
│   ├── extraction/            # 纯算法/规则层的 DOM 检测与 HTML 处理工具
│   ├── llm/                   # LLM client 实现
│   ├── prompts/               # prompt 共享规则、契约、任务与组装器
│   ├── runtime/               # 脚本输出与 legacy 隔离模块
│   └── workflow/              # workflow schema、编译、脚本生成
├── page_extractor/            # 独立详情页采集工具与 CLI 运行时
├── frontend/                  # React 工作台
│   └── src/
│       ├── app/               # 应用壳层与布局编排
│       ├── auth/              # AuthProvider / RequireAuth / AuthCallbackPage
│       ├── features/          # workflow / assist / results / prompt-workspace
│       ├── services/          # API client + auth API
│       └── shared/            # 共享资源
├── docs/                      # 当前有效文档、专项分析与归档文档
└── tests/                     # 后端测试
```

## 文档入口

- [docs/README.md](docs/README.md)
- [docs/documentation-audit.md](docs/documentation-audit.md)
- [docs/product-guide.md](docs/product-guide.md)
- [docs/technical-guide.md](docs/technical-guide.md)
- [docs/engineering-diagnosis-and-optimization-plan.md](docs/engineering-diagnosis-and-optimization-plan.md)
- [docs/optimization-implementation-plan.md](docs/optimization-implementation-plan.md)
- [docs/developer-checklist.md](docs/developer-checklist.md)
- [docs/analysis/guide.md](docs/analysis/guide.md)
- [page_extractor/README.md](page_extractor/README.md)
- [docs/page-extractor-cli-guide.md](docs/page-extractor-cli-guide.md)
- [docs/page-extractor-publish-and-install.md](docs/page-extractor-publish-and-install.md)
- [DESIGN.md](DESIGN.md)

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

### 环境变量配置

在项目根目录 `.env` 文件中配置以下变量：

```bash
# ── 必填：用户中心 OAuth2 对接 ──

# 用户中心基础地址（如 https://dev.zhongshu.tech/pbc/usercenter）
USER_CENTER_BASE_URI=

# 用户中心分配的 OAuth2 client_id
USER_CENTER_CLIENT_ID=

# 用户中心分配的 OAuth2 client_secret
USER_CENTER_CLIENT_SECRET=

# OAuth2 scope（默认 basic）
USER_CENTER_SCOPE=basic

# 用户中心回调地址，必须指向前端的 /auth/callback 路由
# 格式：{前端部署地址}/auth/callback
# 示例：http://127.0.0.1:3101/auth/callback
USER_CENTER_REDIRECT_URI=

# ── 可选：登录与退出 ──

# 退出登录后重定向的目标地址（默认 /）
USER_CENTER_LOGOUT_REDIRECT_URI=/

# 退出登录的渠道标识（默认 default，需与用户中心管理后台配置一致）
USER_CENTER_LOGOUT_CHANNEL=default

# ── 可选：会话与安全 ──

# Redis 连接地址
REDIS_URL=redis://127.0.0.1:6379/0

# Redis key 前缀（默认 crawler_workflow）
REDIS_KEY_PREFIX=crawler_workflow

# 应用会话有效期，单位小时（默认 24）
SESSION_TTL_HOURS=24

# OAuth state 有效期，单位秒（默认 600）
OAUTH_STATE_TTL_SECONDS=600
```

### API 端点

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/api/auth/login?next=/tasks` | 无 | 生成 OAuth state，设置绑定 Cookie，302 到用户中心授权页 |
| `POST` | `/api/auth/callback` | Cookie 绑定 | 请求体 `{code, state}`：换取 token、获取用户信息、创建应用会话，返回 `{sessionId, user, nextPath}` |
| `GET` | `/api/auth/me` | Bearer | 返回当前登录用户信息 |
| `POST` | `/api/auth/logout` | Bearer | 销毁应用会话，返回用户中心退出跳转地址 |

### 前端路由

| 路径 | 认证 | 说明 |
|------|------|------|
| `/` | 公开 | 首页，未登录时显示登录入口 |
| `/auth/callback` | 公开 | OAuth 回调页，自动用 URL 中的 `code`/`state` 换取会话 |
| `/tasks/**` | 需登录 | 工作台页面，由 `RequireAuth` 守卫 |

### 安全机制

- **OAuth state 绑定**：`/api/auth/login` 在重定向前设置 HttpOnly + SameSite=Lax 的 Cookie，`/api/auth/callback` 校验 Cookie 与请求中的 `state` 匹配，防止登录 CSRF / 会话替换攻击
- **一次性 state**：OAuth state 存储在 Redis 中，回调时通过 `GETDEL` 原子消费，不可重放
- **Bearer 认证**：所有受保护 API 通过 `Authorization: Bearer <sessionId>` 请求头认证，sessionId 为 256 位随机令牌
- **会话存储**：前端使用 `sessionStorage` 存储 sessionId，浏览器标签页关闭后自动清除
- **路径白名单**：`/api/auth/login` 的 `next` 参数仅接受同源相对路径，拒绝外部域名和协议跳转

### Redis 数据模型

| Key 格式 | 用途 | TTL |
|----------|------|-----|
| `crawler_workflow:auth:state:{state}` | OAuth 一次性状态，含 `next_path` 和 `code_verifier` | `OAUTH_STATE_TTL_SECONDS`（默认 600s） |
| `crawler_workflow:auth:session:{sessionId}` | 应用会话，含用户快照和上游 token | `SESSION_TTL_HOURS`（默认 24h） |

### 本地开发配置示例

```bash
# .env

# 用户中心
USER_CENTER_BASE_URI=https://dev.zhongshu.tech/pbc/usercenter
USER_CENTER_CLIENT_ID=your-client-id
USER_CENTER_CLIENT_SECRET=your-client-secret
USER_CENTER_SCOPE=basic
USER_CENTER_REDIRECT_URI=http://127.0.0.1:3101/auth/callback

# Redis
REDIS_URL=redis://127.0.0.1:6379/0

# MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your-db-password
DB_NAME=crawler_workflow
```

> **注意**：`USER_CENTER_REDIRECT_URI` 必须与前端实际部署地址一致，且路径为 `/auth/callback`。用户中心管理后台需要将此地址加入授权回调白名单。

## 备注

- `GET /` 当前返回简单的 API 说明信息，主要的编排界面在 React 工作台中。
- 工作台阶段已不再依赖后端浏览器会话中介；浏览器取证由前端直连本地扩展完成。
- 临时截图、调试输出、一次性规划笔记不应保留在仓库根目录。
