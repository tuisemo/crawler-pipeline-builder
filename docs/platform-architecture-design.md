# 平台架构设计：采集任务管理 + 工作流工作台

> 状态：设计文档（2026-05-11）
> 目标：在现有爬虫工作流工作台基础上，扩展为"轻量任务管理 + 工作台编排"的采集平台，保持单体架构不变。

---

## 1. 产品架构总览

### 1.1 系统组件图

```
┌─────────────────────────────────────────────────────────────────────┐
│                          React SPA (port 3101)                      │
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ HomePage │  │ TaskListPage │  │TaskDetailPage│  │WorkbenchPage│  │
│  │  /       │  │  /tasks      │  │ /tasks/:id   │  │/tasks/:id/  │  │
│  │          │  │              │  │              │  │ workbench   │  │
│  └────┬─────┘  └──────┬───────┘  └──────┬───────┘  └──────┬─────┘  │
│       │               │                 │                  │        │
│       └───────────────┴────────┬────────┴──────────────────┘        │
│                                │                                    │
│                        taskApi.ts (services)                        │
│                        workflowApi.ts (services)                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTP (Vite proxy /api → :8000)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend (port 8000)                     │
│                                                                     │
│  ┌─────────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ /api/tasks/*        │  │ /api/workflows/* │  │ /api/assist/* │  │
│  │ (task_routes.py)    │  │ (workflow_routes)│  │(assist_routes)│  │
│  └────────┬────────────┘  └────────┬─────────┘  └───────┬───────┘  │
│           │                        │                     │          │
│  ┌────────▼────────────┐  ┌───────▼──────────┐  ┌───────▼───────┐  │
│  │ tasks/services.py   │  │ workflow/services │  │assist/services│  │
│  │ (CRUD + asset I/O)  │  │ (编译/生成/验证)  │  │ (AI 辅助)     │  │
│  └────────┬────────────┘  └──────────────────┘  └───────────────┘  │
│           │                                                         │
│  ┌────────▼────────────┐                                            │
│  │ database/db.py      │                                            │
│  │ (SQLite 连接管理)    │                                            │
│  │ data/crawler_workflow.db    │                                            │
│  └─────────────────────┘                                            │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 用户流程

```
首页 (/)  ──→  任务列表 (/tasks)  ──→  任务详情 (/tasks/:id)
                                           │
                                           ├──→ 进入编排 (/tasks/:id/workbench)
                                           │       │
                                           │       ├── 编排画布、配置、生成脚本
                                           │       └── 保存到任务 ← DSL + 脚本 + 提示词 + 编译计划 + 批处理配置
                                           │
                                           └──→ 编辑任务元信息、查看资产状态
```

**核心循环：**

1. 用户在首页了解产品，点击"进入任务管理"
2. 在任务列表页创建新任务（填写名称、描述、目标 URL）
3. 点击任务进入详情页，查看任务元信息与已保存资产
4. 点击"进入编排"进入工作台页面（当前 App.tsx 的功能完整保留）
5. 在工作台完成编排、生成脚本后，点击"保存到任务"
6. 工作台将当前 DSL 图、编译计划、脚本、提示词、批处理配置打包回传到任务
7. 返回任务详情页可查看已保存的全部资产

### 1.3 页面路由设计

| 路由 | 页面组件 | 说明 |
|------|----------|------|
| `/` | `HomePage` | 产品介绍 + 入口 |
| `/tasks` | `TaskListPage` | 任务列表，支持新建任务 |
| `/tasks/:taskId` | `TaskDetailPage` | 单任务详情、资产概览 |
| `/tasks/:taskId/workbench` | `WorkbenchPage` | 从 App.tsx 重构而来的工作台 |

所有页面共享 `Layout` 壳组件，包含左侧导航菜单与内容区。

---

## 2. 数据库设计

### 2.1 数据库位置

```
data/crawler_workflow.db    ← 项目根目录下的 data 文件夹，与现有数据目录一致
```

使用 Python 内置 `sqlite3` 模块，零依赖、零配置、文件级数据库。单体架构下无需引入 ORM。

### 2.2 表结构 DDL

```sql
-- 任务主表
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT,
    target_url  TEXT,
    status      TEXT    NOT NULL DEFAULT 'draft',  -- draft | active | archived
    created_at  TEXT    NOT NULL,                   -- ISO8601 UTC
    updated_at  TEXT    NOT NULL                    -- ISO8601 UTC
);

-- 任务资产表（每个 asset_type 存储该类型最新版本的 JSON 内容）
CREATE TABLE IF NOT EXISTS task_assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL,
    asset_type  TEXT    NOT NULL,
    content     TEXT,                               -- JSON 字符串
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL,                   -- ISO8601 UTC
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- 索引：按 task_id + asset_type 快速查找
CREATE INDEX IF NOT EXISTS idx_task_assets_task_id     ON task_assets(task_id);
CREATE INDEX IF NOT EXISTS idx_task_assets_task_type   ON task_assets(task_id, asset_type);
```

### 2.3 asset_type 取值说明

| asset_type | 对应内容 | 来源 |
|------------|----------|------|
| `workflow_graph` | DSL 图 JSON（nodes + edges） | 画布序列化 |
| `compile_plan` | 编译计划 JSON | `/api/workflows/compile-plan` 返回值 |
| `list_script` | 列表采集脚本源码 | `/api/workflows/generate-crawler` 返回值 |
| `prompt` | 提示词文本 | `/api/workflows/to-prompt` 或用户编辑版 |
| `detail_batch_config` | 详情批处理配置 JSON | 详情批处理参数 |
| `detail_batch_script` | 详情批处理脚本源码 | `/api/workflows/generate-detail-batch-runner` 返回值 |

### 2.4 设计决策

- **不使用版本历史**：每次保存直接覆盖 `content` 并递增 `version`，保留最新版本即可。如需历史回溯，可在后续迭代中增加 `task_asset_history` 表。
- **软删除**：`tasks.status = 'archived'` 实现软删除，`DELETE` 操作仅更新状态而非物理删除记录。
- **JSON 存储在 TEXT 列**：SQLite 原生支持 JSON 函数，TEXT 列足以满足查询和存储需求。

---

## 3. 后端 API 设计

### 3.1 路由前缀

```
/api/tasks
```

新增独立路由模块 `backend/api/task_routes.py`，挂载到 `backend/app.py`。

### 3.2 接口清单

#### GET /api/tasks — 获取任务列表

**查询参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码 |
| `page_size` | int | 20 | 每页条数 |
| `status` | string | — | 按状态过滤（可选） |

**响应 `data`：**

```json
{
  "items": [
    {
      "id": 1,
      "name": "商品列表采集",
      "description": "采集某电商首页商品列表数据",
      "target_url": "https://example.com/products",
      "status": "draft",
      "created_at": "2026-05-11T08:00:00Z",
      "updated_at": "2026-05-11T08:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

#### POST /api/tasks — 创建任务

**请求体：**

```json
{
  "name": "商品列表采集",
  "description": "采集某电商首页商品列表数据",
  "target_url": "https://example.com/products"
}
```

**响应 `data`：** 返回创建的完整任务对象（含 `id`）。

#### GET /api/tasks/{task_id} — 获取任务详情（含最新资产）

**响应 `data`：**

```json
{
  "task": {
    "id": 1,
    "name": "商品列表采集",
    "description": "采集某电商首页商品列表数据",
    "target_url": "https://example.com/products",
    "status": "draft",
    "created_at": "2026-05-11T08:00:00Z",
    "updated_at": "2026-05-11T08:00:00Z"
  },
  "assets": [
    {
      "asset_type": "workflow_graph",
      "version": 3,
      "updated_at": "2026-05-11T10:00:00Z"
    }
  ]
}
```

> 注意：资产列表仅返回元信息（类型、版本、更新时间），不返回 `content` 内容体，避免单次请求过大。

#### PUT /api/tasks/{task_id} — 更新任务元信息

**请求体：**

```json
{
  "name": "商品列表采集 v2",
  "description": "更新后的描述",
  "status": "active"
}
```

所有字段可选，仅传入需要更新的字段。

#### DELETE /api/tasks/{task_id} — 软删除任务

将 `status` 设为 `archived`，不物理删除记录。

**响应 `data`：**

```json
{
  "id": 1,
  "status": "archived"
}
```

#### POST /api/tasks/{task_id}/assets — 保存资产包

一次性保存工作台产出的全部资产类型。

**请求体：**

```json
{
  "assets": [
    {
      "asset_type": "workflow_graph",
      "content": { "nodes": [], "edges": [] }
    },
    {
      "asset_type": "compile_plan",
      "content": { "steps": [] }
    },
    {
      "asset_type": "list_script",
      "content": "import asyncio\n..."
    },
    {
      "asset_type": "prompt",
      "content": "请根据以下工作流定义生成采集脚本..."
    },
    {
      "asset_type": "detail_batch_config",
      "content": { "batch_size": 10 }
    },
    {
      "asset_type": "detail_batch_script",
      "content": "import sys\n..."
    }
  ]
}
```

> `content` 字段为 JSON 对象或字符串均可，后端统一 `json.dumps` 后存入 TEXT 列。

**响应 `data`：**

```json
{
  "saved_count": 6,
  "assets": [
    { "asset_type": "workflow_graph", "version": 4 },
    { "asset_type": "list_script", "version": 2 }
  ]
}
```

#### GET /api/tasks/{task_id}/assets/{asset_type} — 获取指定类型资产

**路径参数：**

| 参数 | 说明 |
|------|------|
| `task_id` | 任务 ID |
| `asset_type` | 资产类型，取值见 2.3 节 |

**响应 `data`：**

```json
{
  "task_id": 1,
  "asset_type": "workflow_graph",
  "content": { "nodes": [], "edges": [] },
  "version": 4,
  "created_at": "2026-05-11T10:00:00Z"
}
```

### 3.3 错误处理

与现有接口保持一致，使用 `api_response` 包装：

```python
# 任务不存在
api_response(status_code=404, success=False, error_code="task_not_found", error="任务不存在")

# 请求参数校验失败
api_response(status_code=422, success=False, error_code="request_validation_error", error="请求参数不合法")

# 资产类型不合法
api_response(status_code=400, success=False, error_code="invalid_asset_type", error="不支持的资产类型")
```

### 3.4 Pydantic 请求/响应模型

```python
# backend/tasks/schemas.py

from pydantic import BaseModel, Field
from typing import Any


class CreateTaskRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    target_url: str | None = None


class UpdateTaskRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    target_url: str | None = None
    status: str | None = None


class AssetItem(BaseModel):
    asset_type: str
    content: Any


class SaveAssetsRequest(BaseModel):
    assets: list[AssetItem]
```

---

## 4. 后端模块结构

### 4.1 新增文件清单

```
backend/
├── database/
│   ├── __init__.py
│   ├── db.py            # SQLite 连接管理
│   ├── models.py        # 表定义（DDL 语句）+ ensure_schema()
├── tasks/
│   ├── __init__.py
│   ├── schemas.py       # Pydantic 请求/响应模型
│   └── services.py      # 业务逻辑（CRUD + 资产读写）
└── api/
    ├── task_routes.py    # /api/tasks 路由（新增）
    ├── workflow_routes.py # 已有
    └── assist_routes.py   # 已有
```

### 4.2 database/db.py — 连接管理

```python
"""SQLite 连接管理，模块级单例连接。"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "crawler_workflow.db"

_connection: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """获取模块级 SQLite 连接（惰性初始化）。"""
    global _connection
    if _connection is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA foreign_keys=ON")
    return _connection


@contextmanager
def get_cursor():
    """上下文管理器：获取游标并在结束后自动 commit。"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def close_connection():
    """关闭连接（应用退出时调用）。"""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
```

### 4.3 database/models.py — DDL 定义

```python
"""数据库表结构定义。"""

TASKS_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT,
    target_url  TEXT,
    status      TEXT    NOT NULL DEFAULT 'draft',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
"""

TASK_ASSETS_DDL = """
CREATE TABLE IF NOT EXISTS task_assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL,
    asset_type  TEXT    NOT NULL,
    content     TEXT,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
"""

INDEX_DDLS = [
    "CREATE INDEX IF NOT EXISTS idx_task_assets_task_id   ON task_assets(task_id);",
    "CREATE INDEX IF NOT EXISTS idx_task_assets_task_type ON task_assets(task_id, asset_type);",
]

ALL_DDLS = [TASKS_DDL, TASK_ASSETS_DDL, *INDEX_DDLS]
```

### 4.4 database/models.py — Schema 启动

项目处于 v0.0.0 阶段，不使用版本号追踪或增量迁移。`ensure_schema()` 在每次应用启动时通过 `CREATE TABLE IF NOT EXISTS` 确保所有表存在：

```python
def ensure_schema() -> None:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for ddl in ALL_DDL:
            cursor.execute(ddl)
        conn.commit()
    finally:
        cursor.close()
        conn.close()
```

### 4.5 集成到 backend/app.py

```python
from backend.database.models import ensure_schema
from backend.database.db import close_connection
from backend.api.task_routes import router as task_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema()            # 启动时建表（幂等）
    yield
    close_connection()         # 退出时关闭连接

app = FastAPI(title="Scraper Flow Studio API", lifespan=lifespan)
# ... 已有路由 ...
app.include_router(task_router)  # 新增任务路由
```

### 4.6 tasks/services.py — 业务逻辑

```python
"""任务管理业务逻辑。"""

import json
from datetime import datetime, timezone
from backend.database.db import get_cursor

VALID_ASSET_TYPES = {
    "workflow_graph", "compile_plan", "list_script",
    "prompt", "detail_batch_config", "detail_batch_script",
}

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def create_task(name: str, description: str | None, target_url: str | None) -> dict:
    now = _now_iso()
    with get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO tasks (name, description, target_url, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'draft', ?, ?)",
            (name, description, target_url, now, now),
        )
        task_id = cursor.lastrowid
        return {"id": task_id, "name": name, "description": description,
                "target_url": target_url, "status": "draft",
                "created_at": now, "updated_at": now}

def list_tasks(page: int = 1, page_size: int = 20, status: str | None = None) -> dict:
    with get_cursor() as cursor:
        where = "WHERE status != 'archived'" if not status else "WHERE status = ?"
        params = [] if not status else [status]
        cursor.execute(f"SELECT COUNT(*) FROM tasks {where}", params)
        total = cursor.fetchone()[0]
        offset = (page - 1) * page_size
        cursor.execute(
            f"SELECT * FROM tasks {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        )
        items = [dict(row) for row in cursor.fetchall()]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

def get_task(task_id: int) -> dict | None:
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        task = dict(row)
        cursor.execute(
            "SELECT asset_type, version, created_at FROM task_assets "
            "WHERE task_id = ? ORDER BY asset_type",
            (task_id,),
        )
        assets = [dict(r) for r in cursor.fetchall()]
        return {"task": task, "assets": assets}

def update_task(task_id: int, **fields) -> dict | None:
    allowed = {"name", "description", "target_url", "status"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_task(task_id)
    updates["updated_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]
    with get_cursor() as cursor:
        cursor.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        return get_task(task_id)

def delete_task(task_id: int) -> dict | None:
    now = _now_iso()
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE tasks SET status = 'archived', updated_at = ? WHERE id = ?",
            (now, task_id),
        )
        if cursor.rowcount == 0:
            return None
        return {"id": task_id, "status": "archived"}

def save_assets(task_id: int, assets: list[dict]) -> dict:
    now = _now_iso()
    saved = []
    with get_cursor() as cursor:
        for asset in assets:
            atype = asset["asset_type"]
            if atype not in VALID_ASSET_TYPES:
                raise ValueError(f"不支持的资产类型: {atype}")
            content = asset["content"]
            content_str = json.dumps(content, ensure_ascii=False) if not isinstance(content, str) else content
            # 查询当前版本
            cursor.execute(
                "SELECT version FROM task_assets WHERE task_id = ? AND asset_type = ?",
                (task_id, atype),
            )
            existing = cursor.fetchone()
            new_version = (existing["version"] + 1) if existing else 1
            if existing:
                cursor.execute(
                    "UPDATE task_assets SET content = ?, version = ?, created_at = ? "
                    "WHERE task_id = ? AND asset_type = ?",
                    (content_str, new_version, now, task_id, atype),
                )
            else:
                cursor.execute(
                    "INSERT INTO task_assets (task_id, asset_type, content, version, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (task_id, atype, content_str, new_version, now),
                )
            saved.append({"asset_type": atype, "version": new_version})
        # 同步更新 task.updated_at
        cursor.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (now, task_id))
    return {"saved_count": len(saved), "assets": saved}

def get_asset(task_id: int, asset_type: str) -> dict | None:
    if asset_type not in VALID_ASSET_TYPES:
        return None
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM task_assets WHERE task_id = ? AND asset_type = ?",
            (task_id, asset_type),
        )
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        # 尝试 JSON 反序列化
        try:
            result["content"] = json.loads(result["content"])
        except (json.JSONDecodeError, TypeError):
            pass
        return result
```

---

## 5. 前端路由设计

### 5.1 依赖安装

```bash
npm install react-router-dom@^7
```

> 当前 `frontend/package.json` 中未安装 `react-router-dom`，需新增。

### 5.2 路由结构

```tsx
// frontend/src/main.tsx（改造后）

import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './app/Layout'
import HomePage from './pages/HomePage'
import TaskListPage from './pages/TaskListPage'
import TaskDetailPage from './pages/TaskDetailPage'
import WorkbenchPage from './pages/WorkbenchPage'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider locale={zhCN} theme={/* 保持不变 */}>
      <AntdApp>
        <BrowserRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<HomePage />} />
              <Route path="tasks" element={<TaskListPage />} />
              <Route path="tasks/:taskId" element={<TaskDetailPage />} />
              <Route path="tasks/:taskId/workbench" element={<WorkbenchPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  </StrictMode>,
)
```

### 5.3 Layout 组件

```tsx
// frontend/src/app/Layout.tsx

import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout as AntLayout, Menu } from 'antd'
import { HomeOutlined, UnorderedListOutlined } from '@ant-design/icons'

const { Sider, Content } = AntLayout

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const selectedKey = location.pathname === '/' ? 'home'
    : location.pathname.startsWith('/tasks') ? 'tasks'
    : 'home'

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider width={200} theme="light" style={{ borderRight: '1px solid #e8e8e8' }}>
        <div style={{ padding: '16px', fontWeight: 700, fontSize: 16 }}>
          Crawler Workflow
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={[
            { key: 'home', icon: <HomeOutlined />, label: '首页', onClick: () => navigate('/') },
            { key: 'tasks', icon: <UnorderedListOutlined />, label: '任务管理', onClick: () => navigate('/tasks') },
          ]}
        />
      </Sider>
      <Content>
        <Outlet />
      </Content>
    </AntLayout>
  )
}
```

### 5.4 App.tsx → WorkbenchPage 重构

**原则：100% 保留现有工作台功能，仅做以下最小改动：**

1. 将 `App.tsx` 的 `export default function App()` 重命名为 `export default function WorkbenchPage()`
2. 从 `useParams()` 获取 `taskId`，用于加载和保存资产
3. 顶部工具栏增加任务名称显示与"保存到任务"按钮
4. 新增 `useEffect`：进入页面时调用 `getTaskAsset(taskId, 'workflow_graph')` 加载已有图数据
5. 保存逻辑：收集当前 `nodes`/`edges` + `resultState` 中的脚本/提示词，调用 `saveTaskAssets`

```tsx
// 关键改动示例（伪代码）

import { useParams } from 'react-router-dom'
import { getTaskAsset, saveTaskAssets } from '../services/taskApi'

export default function WorkbenchPage() {
  const { taskId } = useParams<{ taskId: string }>()
  // ...所有现有 state 和 hooks 保持不变...

  // 加载已有资产
  useEffect(() => {
    if (!taskId) return
    getTaskAsset(Number(taskId), 'workflow_graph').then((asset) => {
      if (asset?.content) {
        const graph = asset.content
        setNodes(graph.nodes.map(/* 转换为 ReactFlow 格式 */))
        setEdges(graph.edges.map(/* 转换为 ReactFlow 格式 */))
      }
    })
  }, [taskId])

  // 保存到任务
  async function handleSaveToTask() {
    const assets = [
      { asset_type: 'workflow_graph', content: canonicalGraph },
      { asset_type: 'list_script', content: resultState.payload?.script ?? '' },
      { asset_type: 'prompt', content: resultState.payload?.prompt ?? '' },
      { asset_type: 'compile_plan', content: resultState.payload?.compilePlan ?? {} },
    ]
    await saveTaskAssets(Number(taskId), assets)
    message.success('已保存到任务')
  }

  return (
    <div className="console-root">
      {/* 顶部增加任务名和保存按钮 */}
      <div className="console-toolbar">
        {/* ...原有 WorkbenchToolbar... */}
        <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveToTask}>
          保存到任务
        </Button>
      </div>
      {/* ...其余 JSX 完全不变... */}
    </div>
  )
}
```

---

## 6. 前端页面设计

### 6.1 HomePage — 首页

**定位：** 产品介绍 + 快速入口，无需登录。

```
┌─────────────────────────────────────────────────┐
│  [左侧导航: 首页 | 任务管理]                      │
│                                                  │
│  ┌─────────────────────────────────────────────┐ │
│  │           Crawler Workflow Studio            │ │
│  │        浏览器采集工作流编排平台                  │ │
│  │                                              │ │
│  │  ● 可视化拖拽编排采集流程                      │ │
│  │  ● AI 辅助生成采集脚本                        │ │
│  │  ● 一键保存与管理采集任务                      │ │
│  │                                              │ │
│  │      [ 进入任务管理 → ]                        │ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

**实现要点：**

- 使用 Ant Design 的 `Typography.Title`、`Typography.Paragraph`、`Button`、`Card` 组件
- "进入任务管理" 按钮 `onClick={() => navigate('/tasks')}`
- 无需调用任何 API

### 6.2 TaskListPage — 任务列表

**定位：** 任务 CRUD 列表页。

```
┌──────────────────────────────────────────────────────┐
│  任务管理                               [+ 新建任务]  │
│                                                      │
│  ┌──────────────────────────────────────────────────┐│
│  │ 任务名称    │ 描述       │ 状态  │ 创建时间 │ 操作 ││
│  ├────────────┼───────────┼──────┼─────────┼──────┤│
│  │ 商品列表    │ 采集某电商  │ draft│ 05-11   │编辑 删除 进入│
│  │ 文章采集    │ 采集新闻    │active│ 05-10   │编辑 删除 进入│
│  └──────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────┘
```

**实现要点：**

- `Table` 组件展示任务列表，列：名称、描述（截断）、状态（`Tag` 颜色映射）、创建时间、操作按钮
- 操作按钮：编辑（打开 `Drawer`/`Modal`）、删除（`Popconfirm` 二次确认）、进入（`navigate('/tasks/:id')`）
- "新建任务"按钮打开 `Modal` 或 `Drawer`，内含表单（`Form` + `Input` + `Input.TextArea`）
- 调用 `listTasks()` 加载数据，`createTask()` 创建任务
- 状态 `Tag` 颜色：draft → default，active → green，archived → red

### 6.3 TaskDetailPage — 任务详情

**定位：** 查看任务元信息、资产概览、进入编排入口。

```
┌──────────────────────────────────────────────────────┐
│  ← 返回列表    任务详情                                │
│                                                      │
│  ┌────────────────────────────────────┐              │
│  │ 名称: 商品列表采集                   │              │
│  │ 描述: 采集某电商首页商品列表数据      │              │
│  │ 目标URL: https://example.com/...   │              │
│  │ 状态: [draft]                       │              │
│  │ 创建: 2026-05-11  更新: 2026-05-11  │              │
│  │                           [编辑信息] │              │
│  └────────────────────────────────────┘              │
│                                                      │
│  已保存资产                                            │
│  ┌────────────────────────────────────┐              │
│  │ 工作流图     ✓ v3  05-11 10:00     │              │
│  │ 编译计划     ✓ v2  05-11 10:00     │              │
│  │ 采集脚本     ✓ v2  05-11 10:00     │              │
│  │ 提示词       ✓ v2  05-11 10:00     │              │
│  │ 详情批处理   ✗ 未生成               │              │
│  └────────────────────────────────────┘              │
│                                                      │
│         [ 进入编排工作台 → ]                            │
└──────────────────────────────────────────────────────┘
```

**实现要点：**

- `Descriptions` 组件展示任务元信息
- 资产列表用 `List` 或自定义 `Card`，显示每个 asset_type 的状态（已保存/未生成）、版本号、最后更新时间
- "编辑信息" 按钮打开编辑 `Drawer`
- "进入编排工作台" 按钮：`navigate(`/tasks/${taskId}/workbench`)`
- 调用 `getTask(taskId)` 加载数据

### 6.4 WorkbenchPage — 工作台（从 App.tsx 重构）

**改造量最小化，核心工作台功能 100% 保留。**

顶部工具栏新增元素：

```
┌─────────────────────────────────────────────────────────────────┐
│  ← 返回任务    任务: 商品列表采集    [原有工具栏按钮...]  [保存到任务] │
└─────────────────────────────────────────────────────────────────┘
```

**实现要点：**

- 顶部增加返回按钮（`navigate(-1)` 或 `navigate(`/tasks/${taskId}`)）
- 显示当前任务名称（从路由参数或 API 获取）
- 增加"保存到任务"按钮，调用 `saveTaskAssets`
- 工作台的节点画布、属性面板、结果面板、DSL 编辑器全部保持原样

### 6.5 导航栏设计

使用 Ant Design `Layout.Sider` + `Menu` 组件：

| 菜单项 | 图标 | 路由 |
|--------|------|------|
| 首页 | `HomeOutlined` | `/` |
| 任务管理 | `UnorderedListOutlined` | `/tasks` |

工作台页面（`/tasks/:taskId/workbench`）隐藏左侧导航栏，提供全屏沉浸式编排体验。

---

## 7. 前端 API 客户端

### 7.1 文件位置

```
frontend/src/services/taskApi.ts
```

### 7.2 实现

```typescript
// frontend/src/services/taskApi.ts

import type { ApiEnvelope } from './workflowApi'

const API_BASE = '/api/tasks'

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isApiEnvelope(value: unknown): value is ApiEnvelope {
  if (!isRecord(value)) return false
  return typeof value.success === 'boolean' && Object.prototype.hasOwnProperty.call(value, 'data')
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const raw: unknown = await response.json()
  if (!isApiEnvelope(raw) || !raw.success) {
    const msg = isApiEnvelope(raw) ? raw.error : '请求失败'
    throw new Error(msg ?? '请求失败')
  }
  return raw.data as T
}

// ---- 任务 CRUD ----

export type Task = {
  id: number
  name: string
  description: string | null
  target_url: string | null
  status: 'draft' | 'active' | 'archived'
  created_at: string
  updated_at: string
}

export type TaskListResponse = {
  items: Task[]
  total: number
  page: number
  page_size: number
}

export type AssetMeta = {
  asset_type: string
  version: number
  created_at: string
}

export type TaskDetailResponse = {
  task: Task
  assets: AssetMeta[]
}

export type SaveAssetsResponse = {
  saved_count: number
  assets: { asset_type: string; version: number }[]
}

export async function listTasks(page = 1, pageSize = 20, status?: string): Promise<TaskListResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (status) params.set('status', status)
  return request<TaskListResponse>(`${API_BASE}?${params}`)
}

export async function createTask(data: { name: string; description?: string; target_url?: string }): Promise<Task> {
  return request<Task>(API_BASE, { method: 'POST', body: JSON.stringify(data) })
}

export async function getTask(taskId: number): Promise<TaskDetailResponse> {
  return request<TaskDetailResponse>(`${API_BASE}/${taskId}`)
}

export async function updateTask(taskId: number, data: Partial<{ name: string; description: string; status: string }>): Promise<TaskDetailResponse> {
  return request<TaskDetailResponse>(`${API_BASE}/${taskId}`, { method: 'PUT', body: JSON.stringify(data) })
}

export async function deleteTask(taskId: number): Promise<{ id: number; status: string }> {
  return request<{ id: number; status: string }>(`${API_BASE}/${taskId}`, { method: 'DELETE' })
}

// ---- 资产操作 ----

export type AssetItem = {
  asset_type: string
  content: unknown
}

export async function saveTaskAssets(taskId: number, assets: AssetItem[]): Promise<SaveAssetsResponse> {
  return request<SaveAssetsResponse>(`${API_BASE}/${taskId}/assets`, {
    method: 'POST',
    body: JSON.stringify({ assets }),
  })
}

export async function getTaskAsset(taskId: number, assetType: string): Promise<{
  task_id: number
  asset_type: string
  content: unknown
  version: number
  created_at: string
} | null> {
  try {
    return await request(`${API_BASE}/${taskId}/assets/${assetType}`)
  } catch {
    return null  // 资产不存在时返回 null
  }
}
```

### 7.3 与现有 workflowApi.ts 的关系

| 文件 | 职责 |
|------|------|
| `workflowApi.ts` | 工作流编译、生成、验证等无状态 API 调用 |
| `taskApi.ts` | 任务 CRUD 与资产持久化 API 调用 |

两者独立，不互相依赖。工作台页面同时使用两个文件。

---

## 8. 数据流设计

### 8.1 创建任务

```
TaskListPage                    taskApi.ts                   Backend
    │                               │                          │
    │  用户填写表单 → createTask()    │                          │
    │ ─────────────────────────────→ POST /api/tasks           │
    │                               │ ────────────────────────→│
    │                               │                          │ INSERT INTO tasks
    │                               │ ←─ { id, name, ... } ───│
    │ ←─ navigate('/tasks/:id') ────│                          │
    │                               │                          │
    │  TaskDetailPage 渲染           │                          │
```

### 8.2 进入工作台并加载已有资产

```
TaskDetailPage                  WorkbenchPage               taskApi.ts
    │                               │                          │
    │  点击"进入编排"                 │                          │
    │ ── navigate ─────────────────→│                          │
    │                               │  useEffect: getTaskAsset │
    │                               │ ────────────────────────→│
    │                               │                          │ GET /api/tasks/:id/assets/workflow_graph
    │                               │ ←─ { content: graph } ──│
    │                               │                          │
    │                               │  setNodes(graph.nodes)   │
    │                               │  setEdges(graph.edges)   │
    │                               │  → 画布渲染已有节点       │
```

**资产加载到画布的映射：**

```
task_assets.content (JSON)
  ↓ 反序列化
WorkflowGraph { nodes: CanonicalWorkflowNode[], edges: CanonicalWorkflowEdge[] }
  ↓ 转换为 ReactFlow 格式
WorkflowNode[] + WorkflowEdge[]
  ↓ setNodes / setEdges
画布渲染
```

### 8.3 保存工作台到任务

```
WorkbenchPage                   taskApi.ts                   Backend
    │                               │                          │
    │  点击"保存到任务"               │                          │
    │                               │                          │
    │  收集资产:                      │                          │
    │    workflow_graph = canonicalGraph (from nodes+edges)     │
    │    compile_plan = resultState.payload.compilePlan         │
    │    list_script = resultState.payload.script               │
    │    prompt = resultState.payload.prompt                    │
    │    detail_batch_config = ...                              │
    │    detail_batch_script = ...                              │
    │                               │                          │
    │ ── saveTaskAssets() ─────────→│                          │
    │                               │ POST /api/tasks/:id/assets
    │                               │ ────────────────────────→│
    │                               │                          │ UPSERT task_assets
    │                               │ ←─ { saved_count } ─────│
    │ ←─ message.success ───────────│                          │
```

**资产收集逻辑（在 WorkbenchPage 中）：**

```typescript
async function handleSaveToTask() {
  if (!taskId) return

  const assets: AssetItem[] = []

  // 工作流图（始终保存）
  assets.push({ asset_type: 'workflow_graph', content: canonicalGraph })

  // 编译计划（如果已生成）
  if (resultState.payload?.compilePlan) {
    assets.push({ asset_type: 'compile_plan', content: resultState.payload.compilePlan })
  }

  // 列表采集脚本（如果已生成）
  if (resultState.payload?.script) {
    assets.push({ asset_type: 'list_script', content: resultState.payload.script })
  }

  // 提示词（优先使用用户编辑版）
  const prompt = getPromptOverride(resultState.graphKey) ?? resultState.payload?.prompt
  if (prompt) {
    assets.push({ asset_type: 'prompt', content: prompt })
  }

  await saveTaskAssets(Number(taskId), assets)
  message.success('已保存到任务')
}
```

---

## 9. 关键技术决策

### 9.1 SQLite 同步访问

**决策：** 使用 Python 内置 `sqlite3` 模块，同步调用，不引入异步驱动。

**理由：**

- SQLite 是文件级数据库，无网络 I/O，同步调用足够快
- 本地工作站场景并发极低（单用户），无需连接池
- Python `sqlite3` 是标准库，零额外依赖
- FastAPI 的 `def` 路由（同步）天然与 `sqlite3` 兼容，无需 `run_in_executor`

**连接管理策略：**

- 模块级单例连接，惰性初始化
- 启动时建表（`lifespan` hook），退出时关闭连接
- 每次请求通过 `get_cursor()` 上下文管理器获取游标，自动 commit/rollback
- 启用 WAL 模式（`PRAGMA journal_mode=WAL`）提升并发读性能

### 9.2 前端任务上下文

**决策：** 通过 React Router 的 `useParams` 获取 `taskId`，配合自定义 Hook `useTaskContext` 管理任务状态。

```typescript
// frontend/src/app/useTaskContext.ts

import { useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getTask, type Task } from '../services/taskApi'

export function useTaskContext() {
  const { taskId } = useParams<{ taskId: string }>()
  const [task, setTask] = useState<Task | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!taskId) return
    setLoading(true)
    getTask(Number(taskId))
      .then((res) => setTask(res.task))
      .finally(() => setLoading(false))
  }, [taskId])

  return {
    taskId: taskId ? Number(taskId) : null,
    task,
    loading,
    refresh: () => {
      if (taskId) {
        getTask(Number(taskId)).then((res) => setTask(res.task))
      }
    },
  }
}
```

### 9.3 工作台保持 100% 兼容

**决策：** 工作台页面仅增加"保存/加载"层，不改动任何现有编排逻辑。

**具体做法：**

- `WorkbenchPage` 是 `App.tsx` 的直接重命名 + 扩展，所有 state、hooks、子组件不变
- 保存逻辑作为新增函数，不影响现有 `useWorkflowActions` 等 hooks
- 加载逻辑仅在页面初始化时执行一次，不影响后续画布操作
- 当无 `taskId` 路由参数时（如直接访问 `/`），工作台仍可独立运行（向后兼容）

### 9.4 路由过渡策略

**决策：** 采用渐进式迁移，保留原有入口。

- 重构 `App.tsx` 为 `WorkbenchPage.tsx`，移动到 `frontend/src/pages/WorkbenchPage.tsx`
- `main.tsx` 中用 `BrowserRouter` 替代直接渲染 `<App />`
- `/` 首页提供"进入任务管理"入口
- 后续可通过 `redirect` 将根路径重定向到 `/tasks`（如需）

---

## 10. 实施计划（建议顺序）

### 阶段一：后端数据库 + API

1. 创建 `backend/database/` 模块（db.py、models.py）
2. 创建 `backend/tasks/` 模块（schemas.py、services.py）
3. 创建 `backend/api/task_routes.py`
4. 修改 `backend/app.py` 集成新路由和生命周期 hook
5. 编写后端单元测试

### 阶段二：前端路由 + 页面

6. 安装 `react-router-dom`
7. 创建 `Layout` 组件
8. 创建 `HomePage`、`TaskListPage`、`TaskDetailPage` 页面
9. 创建 `taskApi.ts`
10. 重构 `App.tsx` → `WorkbenchPage.tsx`
11. 修改 `main.tsx` 接入路由

### 阶段三：数据流打通

12. 实现工作台资产加载逻辑
13. 实现工作台资产保存逻辑
14. 端到端测试：创建任务 → 进入编排 → 保存 → 返回查看

---

## 附录 A：完整目录结构变更

```
backend/
├── database/                    # [新增]
│   ├── __init__.py
│   ├── db.py
│   └── models.py
├── tasks/                       # [新增]
│   ├── __init__.py
│   ├── schemas.py
│   └── services.py
├── api/
│   ├── task_routes.py           # [新增]
│   ├── workflow_routes.py       # [不变]
│   └── assist_routes.py         # [不变]
├── app.py                       # [修改] 挂载 task_router + lifespan
└── ...

frontend/src/
├── app/
│   ├── Layout.tsx               # [新增] 带侧边导航的布局壳
│   ├── App.tsx                  # [重构] 移动到 pages/WorkbenchPage.tsx
│   └── ...
├── pages/                       # [新增目录]
│   ├── HomePage.tsx
│   ├── TaskListPage.tsx
│   ├── TaskDetailPage.tsx
│   └── WorkbenchPage.tsx        # [从 App.tsx 重构]
├── services/
│   ├── taskApi.ts               # [新增]
│   └── workflowApi.ts           # [不变]
├── main.tsx                     # [修改] 接入 BrowserRouter
└── ...

data/
└── crawler_workflow.db                  # [自动创建] SQLite 数据库文件
```

## 附录 B：环境依赖变更

**后端：** 无新增依赖，`sqlite3` 为 Python 标准库。

**前端：** 新增 `react-router-dom@^7`。
