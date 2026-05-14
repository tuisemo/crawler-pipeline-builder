# MySQL 持久化存储升级方案

> **状态**: 终版，可落地执行  
> **日期**: 2026-05-12  
> **适用场景**: 全新工程，无 SQLite 历史数据迁移  

---

## 一、方案评审

### 1.1 核心业务访问模式

基于 `backend/tasks/services.py` 的实际 SQL，梳理出以下高频查询：

| 访问模式 | SQL 特征 | 频率 | 索引需求 |
|----------|----------|------|----------|
| 任务列表分页 | `WHERE status != 'archived' ORDER BY created_at DESC LIMIT N OFFSET M` | 高 | 复合索引 `(status, created_at DESC)` |
| 任务详情 | `WHERE id = %s` | 高 | 主键 |
| 某任务的所有资产 | `WHERE task_id = %s ORDER BY created_at DESC` | 中 | 索引 `(task_id)` |
| 获取最新版本资产 | `WHERE task_id = %s AND asset_type = %s ORDER BY version DESC LIMIT 1` | 高 | 复合索引 `(task_id, asset_type, version DESC)` |
| 计算当前最大版本号 | 同上，取 `MAX(version)` | 高 | 同上 |

### 1.2 审查发现及修正

| 问题 | 严重度 | 修正措施 |
|------|--------|----------|
| `status` 和 `asset_type` 使用 `ENUM` | **高** — 新增状态/资产类型需 `ALTER TABLE`，线上变更有锁表风险 | 改为 `VARCHAR`，由应用层 `frozenset` 校验 |
| `save_assets` 存在并发竞态条件 | **高** — 两个并发请求可能读到相同的 `MAX(version)`，导致重复插入 | 加 `SELECT ... FOR UPDATE` 行锁 |
| `content` 使用 `MEDIUMTEXT`（16MB 上限） | **中** — 生成的脚本和 JSON 配置可能超过 16MB | 改为 `LONGTEXT`（4GB），与原 SQLite `TEXT` 等价 |
| `task_assets` 设置了 `updated_at` | **中** — 追加式版本化模型下每行写入后不再修改，此字段无意义 | 移除 |
| `task_assets` 缺少版本唯一约束 | **中** — 并发写入可导致同一版本号重复 | 添加 `UNIQUE KEY (task_id, asset_type, version)` |
| 缺少数据库 schema 版本追踪 | **中** — 无法判断当前数据库结构是否与代码匹配 | 新增 `schema_version` 表 |
| 索引/外键命名不规范 | **低** | 统一采用 `fk_{表名}_{列名}` / `idx_{表名}_{用途}` 命名规范 |

---

## 二、数据库初始化

### 2.1 建库

```sql
CREATE DATABASE IF NOT EXISTS crawler_workflow
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;
```

### 2.2 建表

```sql
-- ========================================================================
-- schema_version: 记录已执行的 schema 版本，用于后续增量迁移
-- ========================================================================
CREATE TABLE IF NOT EXISTS schema_version (
    version     INT UNSIGNED    NOT NULL,
    applied_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================================================
-- tasks: 任务主表
-- ========================================================================
CREATE TABLE IF NOT EXISTS tasks (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    name        VARCHAR(200)    NOT NULL,
    description TEXT            NULL,
    target_url  VARCHAR(2048)   NULL,
    status      VARCHAR(20)     NOT NULL DEFAULT 'draft',
    created_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                        ON UPDATE CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),

    -- 任务列表分页：WHERE status != 'archived' ORDER BY created_at DESC
    INDEX idx_tasks_list (status, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================================================
-- task_assets: 任务资产版本化存储（追加式，每行不可变）
-- ========================================================================
CREATE TABLE IF NOT EXISTS task_assets (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    task_id     INT UNSIGNED    NOT NULL,
    asset_type  VARCHAR(50)     NOT NULL,
    content     LONGTEXT        NULL,
    version     INT UNSIGNED    NOT NULL DEFAULT 1,
    created_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (id),

    -- 外键：任务删除时级联删除所有资产版本
    CONSTRAINT fk_task_assets_task_id
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,

    -- 高频查询：获取某任务某类型资产的最新版本
    -- 覆盖 WHERE task_id = ? AND asset_type = ? ORDER BY version DESC LIMIT 1
    INDEX idx_task_assets_latest (task_id, asset_type, version DESC),

    -- 唯一约束：防止并发写入导致同版本号重复
    UNIQUE KEY uq_task_assets_version (task_id, asset_type, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.3 应用用户（可选，推荐生产环境使用）

```sql
CREATE USER IF NOT EXISTS 'crawler_app'@'%'
    IDENTIFIED BY '<生产环境强密码>';

GRANT SELECT, INSERT, UPDATE, DELETE
    ON crawler_workflow.*
    TO 'crawler_app'@'%';

FLUSH PRIVILEGES;
```

---

## 三、代码改造

### 3.1 改造文件清单

| 文件 | 操作 | 改动说明 |
|------|------|----------|
| `pyproject.toml` | 修改 | 新增 `pymysql`、`DBUtils` 依赖 |
| `.env` | 追加 | MySQL 连接配置 |
| `backend/core/settings.py` | 修改 | 新增 `db_*` 配置字段 |
| `backend/database/db.py` | 重写 | MySQL 连接池管理 |
| `backend/database/models.py` | 重写 | MySQL DDL 定义 |
| `backend/database/migrations.py` | 重写 | 建表 + schema 版本记录 |
| `backend/database/__init__.py` | 修改 | 更新导出接口 |
| `backend/tasks/services.py` | 修改 | 占位符 `%s`、`DictCursor` 行访问、`save_assets` 行锁 |

### 3.2 `pyproject.toml`

```toml
dependencies = [
    # ... 现有依赖保持不变 ...
    "pymysql>=1.1.0",
    "DBUtils>=3.1.0",
]
```

### 3.3 `.env`

```env
# ── MySQL ──
DB_HOST=localhost
DB_PORT=3306
DB_USER=crawler_app
DB_PASSWORD=your_password_here
DB_NAME=crawler_workflow
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
```

### 3.4 `backend/core/settings.py`

在 `CrawlerWorkflowSettings` dataclass 中新增字段：

```python
@dataclass(frozen=True)
class CrawlerWorkflowSettings:
    # ... 现有字段保持不变 ...

    # ── 数据库 ──
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "crawler_workflow"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    @classmethod
    def from_env(cls) -> "CrawlerWorkflowSettings":
        config = load_env_config()
        # ... 现有逻辑 ...
        return cls(
            # ... 现有字段 ...
            db_host=_read_value(config, "DB_HOST", "127.0.0.1"),
            db_port=_read_int(config, "DB_PORT", 3306),
            db_user=_read_value(config, "DB_USER", "root"),
            db_password=_read_value(config, "DB_PASSWORD", ""),
            db_name=_read_value(config, "DB_NAME", "crawler_workflow"),
            db_pool_size=_read_int(config, "DB_POOL_SIZE", 10),
            db_max_overflow=_read_int(config, "DB_MAX_OVERFLOW", 20),
        )
```

### 3.5 `backend/database/db.py`

```python
"""MySQL connection pool management."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

import pymysql
from dbutils.pooled_db import PooledDB
from pymysql.cursors import DictCursor

from backend.core.settings import get_settings

_pool: PooledDB | None = None


def _get_pool() -> PooledDB:
    """Lazy-init MySQL connection pool."""
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = PooledDB(
            creator=pymysql,
            maxconnections=s.db_pool_size,
            maxshared=0,
            blocking=True,
            host=s.db_host,
            port=int(s.db_port),
            user=s.db_user,
            password=s.db_password,
            database=s.db_name,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
            cursorclass=DictCursor,
            autocommit=False,
        )
    return _pool


@contextmanager
def get_cursor() -> Generator[DictCursor, None, None]:
    """Context-managed cursor with automatic commit/rollback."""
    pool = _get_pool()
    conn = pool.connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_connection() -> Any:
    """Get a raw connection (for migrations)."""
    return _get_pool().connection()


def close_connection() -> None:
    """Shutdown hook: close the entire pool."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
```

### 3.6 `backend/database/models.py`

```python
"""MySQL DDL definitions."""

from __future__ import annotations

TASKS_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    name        VARCHAR(200)    NOT NULL,
    description TEXT            NULL,
    target_url  VARCHAR(2048)   NULL,
    status      VARCHAR(20)     NOT NULL DEFAULT 'draft',
    created_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                        ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    INDEX idx_tasks_list (status, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

TASK_ASSETS_DDL = """
CREATE TABLE IF NOT EXISTS task_assets (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    task_id     INT UNSIGNED    NOT NULL,
    asset_type  VARCHAR(50)     NOT NULL,
    content     LONGTEXT        NULL,
    version     INT UNSIGNED    NOT NULL DEFAULT 1,
    created_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    CONSTRAINT fk_task_assets_task_id
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    INDEX idx_task_assets_latest (task_id, asset_type, version DESC),
    UNIQUE KEY uq_task_assets_version (task_id, asset_type, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INT UNSIGNED    NOT NULL,
    applied_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

ALL_DDL = [SCHEMA_VERSION_DDL, TASKS_DDL, TASK_ASSETS_DDL]

SCHEMA_VERSION = 1
```

### 3.7 `backend/database/migrations.py`

```python
"""Database migration: create tables and record schema version."""

from backend.database.db import get_connection
from backend.database.models import ALL_DDL, SCHEMA_VERSION


def run_migrations() -> None:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for ddl in ALL_DDL:
            cursor.execute(ddl)

        cursor.execute(
            "SELECT 1 FROM schema_version WHERE version = %s",
            (SCHEMA_VERSION,),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO schema_version (version) VALUES (%s)",
                (SCHEMA_VERSION,),
            )

        conn.commit()
    finally:
        cursor.close()
        conn.close()
```

### 3.8 `backend/database/__init__.py`

```python
from backend.database.db import close_connection, get_connection, get_cursor
from backend.database.migrations import run_migrations

__all__ = [
    "close_connection",
    "get_connection",
    "get_cursor",
    "run_migrations",
]
```

### 3.9 `backend/tasks/services.py`

完整改造后的文件：

```python
"""Business logic for task CRUD operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.database.db import get_cursor
from backend.tasks.schemas import (
    VALID_ASSET_TYPES,
    CreateTaskRequest,
    SaveAssetResponse,
    TaskAssetResponse,
    TaskDetailResponse,
    TaskListResponse,
    TaskResponse,
    UpdateTaskRequest,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# -- Task CRUD ---------------------------------------------------------------


def create_task(request: CreateTaskRequest) -> TaskResponse:
    now = _now()
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO tasks (name, description, target_url, status, created_at, updated_at)
               VALUES (%s, %s, %s, 'draft', %s, %s)""",
            (request.name, request.description, request.target_url, now, now),
        )
        task_id = cursor.lastrowid
        cursor.execute(
            """SELECT id, name, description, target_url, status, created_at, updated_at
               FROM tasks WHERE id = %s""",
            (task_id,),
        )
        row = cursor.fetchone()
    return _row_to_task_response(row)


def list_tasks(
    page: int = 1,
    page_size: int = 20,
    include_archived: bool = False,
) -> TaskListResponse:
    offset = (page - 1) * page_size
    with get_cursor() as cursor:
        if include_archived:
            cursor.execute("SELECT COUNT(*) AS cnt FROM tasks")
        else:
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM tasks WHERE status != 'archived'"
            )
        total = cursor.fetchone()["cnt"]

        where = "" if include_archived else "WHERE status != 'archived' "
        cursor.execute(
            f"""SELECT id, name, description, target_url, status, created_at, updated_at
                FROM tasks {where}
                ORDER BY created_at DESC LIMIT %s OFFSET %s""",
            (page_size, offset),
        )
        rows = cursor.fetchall()

    items = [_row_to_task_response(r) for r in rows]
    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


def get_task(task_id: int) -> TaskDetailResponse:
    with get_cursor() as cursor:
        cursor.execute(
            """SELECT id, name, description, target_url, status, created_at, updated_at
               FROM tasks WHERE id = %s""",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Task {task_id} not found")

        cursor.execute(
            """SELECT asset_type, version, created_at
               FROM task_assets WHERE task_id = %s ORDER BY created_at DESC""",
            (task_id,),
        )
        asset_rows = cursor.fetchall()

    task = _row_to_task_response(row)
    assets = [
        TaskAssetResponse(
            asset_type=r["asset_type"],
            version=r["version"],
            created_at=str(r["created_at"]),
        )
        for r in asset_rows
    ]
    return TaskDetailResponse(task=task, assets=assets)


def update_task(task_id: int, request: UpdateTaskRequest) -> TaskResponse:
    updates: list[str] = []
    params: list[Any] = []

    if request.name is not None:
        updates.append("name = %s")
        params.append(request.name)
    if request.description is not None:
        updates.append("description = %s")
        params.append(request.description)
    if request.target_url is not None:
        updates.append("target_url = %s")
        params.append(request.target_url)
    if request.status is not None:
        updates.append("status = %s")
        params.append(request.status)

    if not updates:
        return get_task(task_id).task

    updates.append("updated_at = %s")
    params.append(_now())
    params.append(task_id)

    with get_cursor() as cursor:
        cursor.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE id = %s", params
        )
        cursor.execute(
            """SELECT id, name, description, target_url, status, created_at, updated_at
               FROM tasks WHERE id = %s""",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Task {task_id} not found")

    return _row_to_task_response(row)


def delete_task(task_id: int) -> TaskResponse:
    now = _now()
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE tasks SET status = 'archived', updated_at = %s WHERE id = %s",
            (now, task_id),
        )
        cursor.execute(
            """SELECT id, name, description, target_url, status, created_at, updated_at
               FROM tasks WHERE id = %s""",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Task {task_id} not found")

    return _row_to_task_response(row)


# -- Asset services ----------------------------------------------------------


def save_assets(task_id: int, assets: dict[str, Any]) -> SaveAssetResponse:
    for asset_type in assets.keys():
        if asset_type not in VALID_ASSET_TYPES:
            raise ValueError(
                f"Invalid asset type: {asset_type}. "
                f"Must be one of {sorted(VALID_ASSET_TYPES)}"
            )

    now = _now()
    versions: dict[str, int] = {}

    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Task {task_id} not found")

        for asset_type, content in assets.items():
            # FOR UPDATE locks the row, preventing concurrent duplicate versions
            cursor.execute(
                """SELECT MAX(version) AS max_ver
                   FROM task_assets
                   WHERE task_id = %s AND asset_type = %s
                   FOR UPDATE""",
                (task_id, asset_type),
            )
            row = cursor.fetchone()
            new_version = (row["max_ver"] or 0) + 1

            cursor.execute(
                """INSERT INTO task_assets
                   (task_id, asset_type, content, version, created_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (task_id, asset_type, content, new_version, now),
            )
            versions[asset_type] = new_version

    return SaveAssetResponse(saved_count=len(assets), versions=versions)


def get_asset(task_id: int, asset_type: str) -> dict[str, Any]:
    if asset_type not in VALID_ASSET_TYPES:
        raise ValueError(
            f"Invalid asset type: {asset_type}. "
            f"Must be one of {sorted(VALID_ASSET_TYPES)}"
        )

    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Task {task_id} not found")

        cursor.execute(
            """SELECT content, asset_type, version, created_at
               FROM task_assets
               WHERE task_id = %s AND asset_type = %s
               ORDER BY version DESC LIMIT 1""",
            (task_id, asset_type),
        )
        row = cursor.fetchone()

    if row is None:
        return {
            "content": None,
            "asset_type": asset_type,
            "version": 0,
            "created_at": None,
        }

    return {
        "content": row["content"],
        "asset_type": row["asset_type"],
        "version": row["version"],
        "created_at": str(row["created_at"]),
    }


# -- Helpers -----------------------------------------------------------------


def _row_to_task_response(row: dict) -> TaskResponse:
    return TaskResponse(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        target_url=row["target_url"],
        status=row["status"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
```

---

## 四、关键设计决策

### 4.1 VARCHAR vs ENUM

使用 `VARCHAR` 而非 `ENUM` 存储 `status` 和 `asset_type`。

| 维度 | ENUM | VARCHAR |
|------|------|---------|
| 新增值 | 需 `ALTER TABLE`（线上锁表） | 仅改应用代码 |
| 存储 | 1-2 字节（内部整数映射） | 实际字节长度 |
| 可读性 | SHOW CREATE TABLE 才能看到允许值 | 需查代码 |
| 本项目选择 | — | **VARCHAR** |

理由：`VALID_ASSET_TYPES` 由应用层 `frozenset` 校验，数据库只负责存储，不承担业务校验职责。

### 4.2 追加式版本化模型

`task_assets` 每次保存都 INSERT 新行，不 UPDATE 旧行。

- 每行写入后不可变，无需 `updated_at` 字段
- 通过 `version` 字段递增实现版本管理
- 历史版本可随时查询、比对、回滚
- 通过 `SELECT MAX(version) ... FOR UPDATE` + `UNIQUE KEY` 保证并发安全

### 4.3 LONGTEXT vs MEDIUMTEXT

使用 `LONGTEXT`（4GB）而非 `MEDIUMTEXT`（16MB）。

`task_assets.content` 存储的内容类型包括：Python 脚本（生成的爬虫代码）、JSON 配置（workflow_graph、compile_plan）、提示词模板（prompt）。原 SQLite 使用 `TEXT`（理论无上限），`LONGTEXT` 是最接近的等价选择，且不影响小数据的读写性能。

### 4.4 DATETIME(3) vs TIMESTAMP

| 维度 | DATETIME(3) | TIMESTAMP |
|------|------------|-----------|
| 范围 | 1000-01-01 ~ 9999-12-31 | 1970-01-01 ~ 2038-01-19 |
| 时区 | 不转换 | 存储时转 UTC，读取时转回 session 时区 |
| 存储 | 5 字节（含毫秒） | 4 字节 |
| 本项目选择 | **DATETIME(3)** | — |

理由：应用层统一使用 `datetime.now(timezone.utc)` 生成时间，MySQL 不需要做时区转换。`DATETIME(3)` 提供毫秒精度，足够区分快速连续操作。

---

## 五、MySQL 生产配置建议

### 5.1 `my.cnf`

```ini
[mysqld]
character-set-server       = utf8mb4
collation-server           = utf8mb4_unicode_ci
max_connections            = 200
wait_timeout               = 28800
interactive_timeout        = 28800
innodb_buffer_pool_size    = 2G
innodb_log_file_size       = 512M
innodb_flush_log_at_trx_commit = 1
innodb_flush_method        = O_DIRECT
innodb_file_per_table      = ON
```

### 5.2 连接池配置

| 配置项 | 开发 | 生产 | 说明 |
|--------|------|------|------|
| `DB_POOL_SIZE` | 5 | 10~20 | 常驻连接数 |
| `DB_MAX_OVERFLOW` | 10 | 20~40 | 突发流量额外连接 |

---

## 六、数据生命周期

`task_assets` 追加式存储会导致表持续增长。建议通过定时任务清理历史版本：

```sql
-- 每个 (task_id, asset_type) 保留最近 100 个版本
DELETE FROM task_assets
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY task_id, asset_type ORDER BY version DESC
               ) AS rn
        FROM task_assets
    ) ranked
    WHERE ranked.rn > 100
);

-- 物理删除 90 天前归档的任务（级联删除关联资产）
DELETE FROM tasks
WHERE status = 'archived'
  AND updated_at < NOW() - INTERVAL 90 DAY
LIMIT 1000;
```

---

## 七、实施步骤

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | MySQL 建库建表 | 执行本文档第二章 DDL |
| 2 | `pyproject.toml` | 添加 `pymysql`、`DBUtils` |
| 3 | `uv sync` | 安装新依赖 |
| 4 | `.env` | 配置 MySQL 连接信息 |
| 5 | `backend/core/settings.py` | 新增 `db_*` 字段 |
| 6 | `backend/database/db.py` | 重写为 MySQL 连接池 |
| 7 | `backend/database/models.py` | 重写为 MySQL DDL |
| 8 | `backend/database/migrations.py` | 重写建表逻辑 |
| 9 | `backend/database/__init__.py` | 更新导出 |
| 10 | `backend/tasks/services.py` | 占位符、行访问、行锁 |
| 11 | 启动验证 | 确认建表和 CRUD 正常 |
| 12 | 清理 | 删除 `data/crawler_workflow.db`，`data/` 加入 `.gitignore` |

---

## 八、验证清单

| 验证项 | 预期结果 |
|--------|----------|
| 应用启动 | `run_migrations()` 建表成功，`schema_version` 记录 v1 |
| `POST /api/tasks` | tasks 表新增记录，`created_at`/`updated_at` 自动填充 |
| `GET /api/tasks` | 返回分页列表，按 `created_at DESC` 排序 |
| `GET /api/tasks/{id}` | 返回任务详情 + 资产元数据列表 |
| `PUT /api/tasks/{id}` | 部分更新，`updated_at` 自动刷新 |
| `DELETE /api/tasks/{id}` | 软删除，`status` 变为 `archived` |
| `POST /api/tasks/{id}/assets` | 资产 version 递增存储 |
| `GET /api/tasks/{id}/assets/{type}` | 返回最新版本资产内容 |
| 并发 `save_assets` | 不出现重复 version，`FOR UPDATE` + `UNIQUE KEY` 双重保护 |
| 连接池压力测试 | 无 `Too many connections` 错误 |
| 中文内容存储 | 任务名、description、脚本内容存取不乱码 |
