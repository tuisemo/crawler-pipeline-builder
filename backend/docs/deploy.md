# Scraper Flow Studio — 部署指南

## 1. 环境概览

| 环境 | 域名 | 部署路径 |
|---|---|---|
| 本地开发 | `http://127.0.0.1:3101` | `/` |
| 测试 | `https://test.zhongshu.tech` | `/crawler-studio/` |
| 预生产 | `https://demo.zhongshu.tech` | `/crawler-studio/` |
| 生产 | `https://ai.zhongshu.tech` | `/crawler-studio/` |

### URL 结构（测试 / 预生产 / 生产一致）

```
{domain}/crawler-studio/              → 前端 SPA (React)
{domain}/crawler-studio/api/          → 后端 API (FastAPI)
{domain}/crawler-studio/static/       → 后端静态资源
```

---

## 2. 核心设计：一次构建，任意路径部署

前端采用**相对路径**策略，不将任何部署路径写死到构建产物中：

- **Vite `base: "./"`** — 所有静态资源引用（JS/CSS/图片）使用相对路径，浏览器根据当前 URL 自动解析
- **`apiFetch()` 使用 `window.location.pathname` 推导基础路径** — API 请求自动适配当前部署目录
- **`login()` / `logout()` 使用 `./api/auth/...` 相对路径** — 全页面跳转自动适配
- **Logo 等静态资源通过 `import` 引用** — Vite 构建时自动处理路径

**前提条件：** 项目使用 `HashRouter`，`window.location.pathname` 始终稳定在部署目录（如 `/crawler-studio/`），hash 部分不影响路径解析。

### 路径解析示例

```
浏览器位于 https://test.zhongshu.tech/crawler-studio/
window.location.pathname = "/crawler-studio/"

相对路径解析:
  ./api/auth/login     → /crawler-studio/api/auth/login     ✓
  ./api/tasks          → /crawler-studio/api/tasks           ✓
  ./assets/app.js      → /crawler-studio/assets/app.js       ✓
  ./logo_128.webp      → /crawler-studio/logo_128.webp       ✓

浏览器位于 http://127.0.0.1:3101/  (本地开发)
window.location.pathname = "/"

相对路径解析:
  ./api/auth/login     → /api/auth/login                     ✓
  ./api/tasks          → /api/tasks                          ✓
  ./assets/app.js      → /assets/app.js                      ✓
```

---

## 3. Nginx 配置

三个环境的 Nginx 配置**完全相同**，仅 `server_name` 和 SSL 证书路径不同：

```nginx
server {
    listen 443 ssl;
    server_name {域名};    # test.zhongshu.tech / demo.zhongshu.tech / ai.zhongshu.tech

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # ── 确保目录有尾部斜杠（SPA 入口需要） ──
    location = /crawler-studio {
        return 308 /crawler-studio/;
    }

    # ── 后端 API ──
    # /crawler-studio/api/... → http://127.0.0.1:8000/api/...
    location /crawler-studio/api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 重写后端 Set-Cookie 的 path，否则浏览器不会回传 cookie
        proxy_cookie_path /api /crawler-studio/api;
    }

    # ── 后端静态资源 ──
    # /crawler-studio/static/... → http://127.0.0.1:8000/static/...
    location /crawler-studio/static/ {
        proxy_pass http://127.0.0.1:8000/static/;
    }

    # ── 前端 SPA ──
    location /crawler-studio/ {
        alias /path/to/deploy/frontend/dist/;
        index index.html;
        try_files $uri $uri/ /crawler-studio/index.html;
    }
}
```

### 各环境差异

| 配置项 | 测试 | 预生产 | 生产 |
|---|---|---|---|
| `server_name` | `test.zhongshu.tech` | `demo.zhongshu.tech` | `ai.zhongshu.tech` |
| SSL 证书 | 测试环境证书 | 预生产证书 | 生产证书 |
| `alias` 路径 | 测试机器的 dist 目录 | 预生产机器的 dist 目录 | 生产机器的 dist 目录 |

### 验证 Nginx 配置

```bash
nginx -t && nginx -s reload
```

---

## 4. 前端构建

### 4.1 构建命令

```bash
cd frontend
npm run build    # 产物 → frontend/dist/
```

**只有一个构建命令，不需要分环境构建。** 同一份 `dist/` 产物可直接部署到测试、预生产、生产。

### 4.2 产物内容

```
frontend/dist/
├── index.html                         # 入口，资源引用为相对路径 (./assets/...)
├── logo_128.webp                      # 从 public/ 复制的静态资源
├── monaco-editor/                     # Monaco 编辑器 worker 文件
├── assets/
│   ├── index-a1b2c3d4.js              # 业务代码
│   ├── vendor-xxxx.js                 # 第三方依赖
│   ├── index-e5f6g7h8.css             # 样式
│   └── logo_128-hash.webp             # 被 import 引用的图片（带 hash）
└── ...
```

### 4.3 路径解析机制

| 场景 | 资源 | 解析方式 | 部署路径变化时 |
|---|---|---|---|
| JS/CSS bundle | `./assets/app-xxx.js` | 浏览器相对 `index.html` 所在目录 | 自动适配，无需重建 |
| API 请求 | `getDeployBase() + '/api/...'` | 从 `window.location.pathname` 推导 | 自动适配，无需重建 |
| Auth 跳转 | `./api/auth/login` | 浏览器相对当前页面 URL | 自动适配，无需重建 |
| Logo 图片 | `import logoUrl from '...'` | Vite 编译为 `./assets/logo-hash.webp` | 自动适配，无需重建 |
| Favicon | `./logo_128.webp` | 浏览器相对 `index.html` 所在目录 | 自动适配，无需重建 |

---

## 5. 后端部署

### 5.1 安装依赖

```bash
cd /path/to/sea-data
pip install .
```

### 5.2 环境变量

后端通过项目根目录 `.env` 文件加载配置。以下是与部署路径相关的变量：

```env
# ── OAuth2 回调地址（按环境修改） ──

# 测试环境
USER_CENTER_REDIRECT_URI=https://test.zhongshu.tech/crawler-studio/api/auth/callback
USER_CENTER_FRONTEND_URL=https://test.zhongshu.tech/crawler-studio
USER_CENTER_BASE_URI=https://test.zhongshu.tech/pbc/usercenter

# 预生产环境
# USER_CENTER_REDIRECT_URI=https://demo.zhongshu.tech/crawler-studio/api/auth/callback
# USER_CENTER_FRONTEND_URL=https://demo.zhongshu.tech/crawler-studio
# USER_CENTER_BASE_URI=https://demo.zhongshu.tech/pbc/usercenter

# 生产环境
# USER_CENTER_REDIRECT_URI=https://ai.zhongshu.tech/crawler-studio/api/auth/callback
# USER_CENTER_FRONTEND_URL=https://ai.zhongshu.tech/crawler-studio
# USER_CENTER_BASE_URI=https://ai.zhongshu.tech/pbc/usercenter
```

> 其余变量（LLM、MySQL、Redis 等）根据各环境基础设施配置，与部署路径无关。

### 5.3 启动服务

```bash
python src/main.py -p 8000
```

后端监听 `127.0.0.1:8000`，只接受 Nginx 转发的本地请求。

---

## 6. 完整部署流程

### 6.1 测试 / 预生产 / 生产（流程完全相同）

```bash
# 1. 前端构建（一次构建，产物通用）
cd frontend
npm install
npm run build

# 2. 将产物复制到部署目录
#    frontend/dist/ → 部署机器的 /path/to/deploy/frontend/dist/

# 3. 后端：配置 .env
#    修改 USER_CENTER_REDIRECT_URI / USER_CENTER_FRONTEND_URL / USER_CENTER_BASE_URI
#    修改 LLM / DB / Redis 等基础设施配置

# 4. 后端：安装依赖并启动
pip install .
python src/main.py -p 8000

# 5. Nginx
#    确保 server_name / SSL / alias 路径正确
nginx -t && nginx -s reload
```

---

## 7. 验证清单

部署完成后，依次检查以下项目：

| # | 检查项 | 预期结果 |
|---|---|---|
| 1 | 访问 `{domain}/crawler-studio/` | 看到 SPA 首页（Scraper Flow Studio） |
| 2 | 访问 `{domain}/crawler-studio`（无尾部斜杠） | 308 重定向到 `/crawler-studio/` |
| 3 | 浏览器 F12 Network，检查 JS/CSS 资源路径 | 全部以 `/crawler-studio/assets/` 开头 |
| 4 | 检查 favicon 加载 | `/crawler-studio/logo_128.webp` 返回 200 |
| 5 | 点击登录按钮 | 浏览器跳转到 `/crawler-studio/api/auth/login` |
| 6 | OAuth 回调完成后 | URL 变为 `{domain}/crawler-studio/#/auth/callback?sessionId=...` |
| 7 | F12 Application → Cookies | `crawler_workflow_oauth_state` 的 path 为 `/crawler-studio/api` |
| 8 | 登录成功后访问受保护页面 | 能正常加载任务列表 |
| 9 | 点击退出 | 跳转到 `/crawler-studio/api/auth/logout`，然后回到首页 |
| 10 | SPA 内页面切换（HashRouter） | URL hash 变化，页面不刷新 |

---

## 8. 回滚

前端产物是纯静态文件，回滚只需替换 `dist/` 目录：

```bash
# 保留上一个版本的产物
cp -r /path/to/deploy/frontend/dist /path/to/deploy/frontend/dist.bak

# 部署新版本后如需回滚
rm -rf /path/to/deploy/frontend/dist
mv /path/to/deploy/frontend/dist.bak /path/to/deploy/frontend/dist
```

后端回滚：

```bash
git checkout <上一个稳定版本>
pip install .
# 重启后端服务
```

---

## 9. 环境变量完整参考

### 前端

前端不需要任何环境变量。所有路径通过相对路径自动适配。

### 后端（运行时通过 .env 加载，各环境不同）

| 变量 | 说明 | 必须按环境修改 |
|---|---|---|
| `USER_CENTER_REDIRECT_URI` | OAuth 回调地址 | 是 |
| `USER_CENTER_FRONTEND_URL` | 前端基础 URL | 是 |
| `USER_CENTER_BASE_URI` | 用户中心地址 | 是 |
| `API_BASE_URL` | LLM 接口地址 | 是 |
| `API_TOKEN` | LLM Token | 是 |
| `MODEL_NAME` | 模型名称 | 视环境 |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | MySQL 连接 | 是 |
| `REDIS_SENTINEL_NODES` / `REDIS_PASSWORD` 等 | Redis 连接 | 是 |
| `USER_CENTER_CLIENT_ID` / `USER_CENTER_CLIENT_SECRET` | OAuth 凭据 | 是 |

---

## 10. 常见问题

### Q: 本地开发会受影响吗？

不会。`base: "./"` 在开发模式下同样有效，Vite dev server 从根路径提供文件，所有相对路径解析为 `/`。API 代理配置不受影响。

### Q: 如果未来想换一个部署路径（如 `/sfs/`），需要重新构建前端吗？

不需要。只改 Nginx 的 `location` 和 `alias` 配置即可，同一份 `dist/` 产物直接使用。

### Q: 为什么用 `HashRouter` 而不是 `BrowserRouter`？

当前项目本身就是 `HashRouter`。相对路径方案依赖 `window.location.pathname` 在 SPA 导航时保持不变（hash 变化不影响 pathname）。如果迁移到 `BrowserRouter`，需要改用方案 A（构建时绝对前缀）。

### Q: Cookie 为什么需要重写 path？

后端 `auth_routes.py` 设置 `Set-Cookie: path=/api/auth`，但浏览器访问的是 `/crawler-studio/api/auth`。如果不重写，浏览器的 Cookie path 匹配规则会拒绝回传该 Cookie。Nginx 的 `proxy_cookie_path /api /crawler-studio/api` 解决了这个问题。

### Q: `proxy_pass` 末尾的 `/` 有什么用？

`location /crawler-studio/api/` 配合 `proxy_pass http://127.0.0.1:8000/api/` 时，末尾的 `/` 让 Nginx 自动剥离 `/crawler-studio` 前缀。后端收到的请求路径与本地开发一致（`/api/...`），无需任何改动。
