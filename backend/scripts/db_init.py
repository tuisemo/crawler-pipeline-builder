#!/usr/bin/env python3
"""
db_init.py — Crawler Workflow 数据库初始化脚本
===============================================

用途：在全新环境中创建数据库（可选）及所有业务表，供运维在部署时使用。

使用方式
--------
# 1. 从项目 .env 文件读取配置（默认）
    uv run python scripts/db_init.py

# 2. 通过环境变量覆盖（CI/CD 场景）
    DB_HOST=10.0.0.1 DB_USER=app DB_PASSWORD=xxx DB_NAME=crawler_workflow \\
        uv run python scripts/db_init.py

# 3. 通过命令行参数完整指定（不读取 .env）
    python scripts/db_init.py \\
        --host 10.0.0.1 --port 3306 \\
        --user app --password xxx \\
        --db crawler_workflow

# 4. 仅输出 DDL SQL，不执行（dry-run 模式）
    python scripts/db_init.py --dry-run

可选参数
--------
--create-db     若数据库不存在则自动创建（默认不自动创建）
--drop-all      ⚠️  危险：先删除所有业务表再重建（仅用于测试环境）
--dry-run       打印 SQL 而不执行
--env-file      指定 .env 文件路径（默认 .env）
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

# ── 支持直接运行（不在包内部）──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pymysql
from pymysql.cursors import DictCursor


# ──────────────────────────────────────────────────────────────────────────────
# DDL — 与 backend/database/models.py 保持同步
# ──────────────────────────────────────────────────────────────────────────────

USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    external_id     VARCHAR(128)    NOT NULL,
    display_name    VARCHAR(200)    NOT NULL DEFAULT '',
    email           VARCHAR(320)    NULL,
    avatar_url      VARCHAR(2048)   NULL,
    synced_at       DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    created_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_external_id (external_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

TASKS_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id                  INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    owner_user_id       INT UNSIGNED    NOT NULL,
    name                VARCHAR(200)    NOT NULL,
    description         TEXT            NULL,
    target_url          VARCHAR(2048)   NULL,
    status              VARCHAR(20)     NOT NULL DEFAULT 'draft',
    updated_by_user_id  INT UNSIGNED    NULL,
    created_at          DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at          DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                            ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    INDEX idx_tasks_list (status, created_at DESC),
    INDEX idx_tasks_owner_list (owner_user_id, status, created_at DESC),
    CONSTRAINT fk_tasks_owner
        FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_tasks_updated_by
        FOREIGN KEY (updated_by_user_id) REFERENCES users(id) ON DELETE SET NULL
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

# 执行顺序：先 users，再 tasks（FK 依赖），最后 task_assets
ALL_DDL: list[tuple[str, str]] = [
    ("users",       USERS_DDL),
    ("tasks",       TASKS_DDL),
    ("task_assets", TASK_ASSETS_DDL),
]

# 删除顺序（反向，外键约束安全）
DROP_STATEMENTS: list[str] = [
    "DROP TABLE IF EXISTS task_assets",
    "DROP TABLE IF EXISTS tasks",
    "DROP TABLE IF EXISTS users",
]

CREATE_DB_SQL = "CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"


# ──────────────────────────────────────────────────────────────────────────────
# 配置加载（复用项目 .env 解析逻辑，独立实现，无需导入 backend 包）
# ──────────────────────────────────────────────────────────────────────────────

def _load_env_file(env_path: Path) -> dict[str, str]:
    config: dict[str, str] = {}
    if not env_path.exists():
        return config
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        config[k.strip()] = v.strip()
    return config


def _resolve(config: dict[str, str], key: str, default: str) -> str:
    return os.environ.get(key) or config.get(key) or default


def build_config(args: argparse.Namespace) -> dict:
    env_path = Path(args.env_file) if args.env_file else PROJECT_ROOT / ".env"
    env = _load_env_file(env_path)

    return {
        "host":     args.host     or _resolve(env, "DB_HOST",     "127.0.0.1"),
        "port":     int(args.port or _resolve(env, "DB_PORT",     "3306")),
        "user":     args.user     or _resolve(env, "DB_USER",     "root"),
        "password": args.password or _resolve(env, "DB_PASSWORD", ""),
        "db":       args.db       or _resolve(env, "DB_NAME",     "crawler_workflow"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Core logic
# ──────────────────────────────────────────────────────────────────────────────

ANSI_GREEN  = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RED    = "\033[91m"
ANSI_RESET  = "\033[0m"
ANSI_BOLD   = "\033[1m"
ANSI_DIM    = "\033[2m"


def _ok(msg: str)   -> None: print(f"  {ANSI_GREEN}✔{ANSI_RESET}  {msg}")
def _warn(msg: str) -> None: print(f"  {ANSI_YELLOW}⚠{ANSI_RESET}  {msg}")
def _err(msg: str)  -> None: print(f"  {ANSI_RED}✘{ANSI_RESET}  {msg}")
def _info(msg: str) -> None: print(f"  {ANSI_DIM}·{ANSI_RESET}  {msg}")


def connect_no_db(cfg: dict) -> pymysql.Connection:
    return pymysql.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        charset="utf8mb4", cursorclass=DictCursor,
        connect_timeout=10,
    )


def connect_db(cfg: dict) -> pymysql.Connection:
    return pymysql.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        database=cfg["db"],
        charset="utf8mb4", cursorclass=DictCursor,
        connect_timeout=10,
    )


def run_init(cfg: dict, create_db: bool, drop_all: bool, dry_run: bool) -> int:
    """Run the full initialization sequence. Returns 0 on success, 1 on error."""

    print()
    print(f"{ANSI_BOLD}=== Crawler Workflow — 数据库初始化 ==={ANSI_RESET}")
    print()
    print(f"  目标主机  : {cfg['host']}:{cfg['port']}")
    print(f"  数据库    : {cfg['db']}")
    print(f"  账号      : {cfg['user']}")
    print(f"  运行模式  : {'[DRY-RUN] 仅打印 SQL，不执行' if dry_run else '实际执行'}")
    print()

    # ── Step 1: 创建数据库（可选）────────────────────────────────────
    if create_db:
        sql = CREATE_DB_SQL.format(db=cfg["db"])
        if dry_run:
            print(f"-- [create-db]\n{sql};\n")
        else:
            print(f"{ANSI_BOLD}[1/3] 确认数据库存在{ANSI_RESET}")
            try:
                conn = connect_no_db(cfg)
                with conn.cursor() as cur:
                    cur.execute(sql)
                conn.commit()
                conn.close()
                _ok(f"数据库 `{cfg['db']}` 已就绪")
            except Exception as exc:
                _err(f"创建数据库失败: {exc}")
                return 1
    else:
        if not dry_run:
            _info("跳过自动建库（未指定 --create-db）")

    # ── Step 2: 连接到目标数据库（验证连通性）────────────────────────
    if not dry_run:
        print()
        print(f"{ANSI_BOLD}[2/3] 验证数据库连通性{ANSI_RESET}")
        try:
            conn = connect_db(cfg)
            conn.close()
            _ok(f"成功连接到 `{cfg['db']}`")
        except Exception as exc:
            _err(f"连接失败: {exc}")
            _warn("请检查 DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME 配置")
            return 1

    # ── Step 3: DROP（可选）──────────────────────────────────────────
    if drop_all:
        if dry_run:
            print("-- [drop-all]")
            for stmt in DROP_STATEMENTS:
                print(f"{stmt};\n")
        else:
            print()
            _warn("⚠️  执行 --drop-all：将删除所有业务表！")
            conn = connect_db(cfg)
            try:
                with conn.cursor() as cur:
                    # 临时禁用外键约束，确保 DROP 顺利
                    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
                    for stmt in DROP_STATEMENTS:
                        cur.execute(stmt)
                        tbl = stmt.split()[-1]
                        _ok(f"已删除表 {tbl}")
                    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
                conn.commit()
            except Exception as exc:
                conn.rollback()
                _err(f"DROP 失败: {exc}")
                conn.close()
                return 1
            conn.close()

    # ── Step 4: 创建业务表 ────────────────────────────────────────────
    if dry_run:
        print(f"-- [create tables]")
        for name, ddl in ALL_DDL:
            print(f"-- table: {name}")
            print(f"{ddl.strip()};\n")
        print("-- 完成")
        return 0

    print()
    print(f"{ANSI_BOLD}[3/3] 创建业务表{ANSI_RESET}")
    conn = connect_db(cfg)
    try:
        with conn.cursor() as cur:
            for name, ddl in ALL_DDL:
                cur.execute(ddl)
                _ok(f"表 {ANSI_BOLD}{name}{ANSI_RESET} 已就绪")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        _err(f"建表失败: {exc}")
        conn.close()
        return 1
    conn.close()

    print()
    print(f"{ANSI_GREEN}{ANSI_BOLD}✔ 数据库初始化完成！{ANSI_RESET}")
    print()
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawler Workflow 数据库初始化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              uv run python scripts/db_init.py
              uv run python scripts/db_init.py --create-db
              uv run python scripts/db_init.py --dry-run
              uv run python scripts/db_init.py --drop-all --create-db \\
                  --host 10.0.0.1 --user app --password s3cr3t --db crawler_workflow
        """),
    )
    parser.add_argument("--host",      default=None, help="MySQL 主机地址 (覆盖 .env DB_HOST)")
    parser.add_argument("--port",      default=None, help="MySQL 端口 (覆盖 .env DB_PORT，默认 3306)")
    parser.add_argument("--user",      default=None, help="MySQL 用户名 (覆盖 .env DB_USER)")
    parser.add_argument("--password",  default=None, help="MySQL 密码 (覆盖 .env DB_PASSWORD)")
    parser.add_argument("--db",        default=None, help="数据库名称 (覆盖 .env DB_NAME)")
    parser.add_argument("--env-file",  default=None, metavar="PATH", help="指定 .env 文件路径（默认: 项目根目录 .env）")
    parser.add_argument("--create-db", action="store_true", help="若数据库不存在则自动 CREATE DATABASE")
    parser.add_argument("--drop-all",  action="store_true", help="⚠️  先删除所有业务表再重建（测试环境专用）")
    parser.add_argument("--dry-run",   action="store_true", help="打印 SQL 而不实际执行")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.drop_all and not args.dry_run:
        print()
        _warn("你正在使用 --drop-all，这将删除所有业务数据！")
        confirm = input("  请输入 YES 确认: ").strip()
        if confirm != "YES":
            print("  已取消。")
            sys.exit(0)

    cfg = build_config(args)
    rc = run_init(
        cfg=cfg,
        create_db=args.create_db,
        drop_all=args.drop_all,
        dry_run=args.dry_run,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
