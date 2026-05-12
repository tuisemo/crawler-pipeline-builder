"""MySQL DDL definitions for crawler workflow database."""

from __future__ import annotations

# ── Schema version tracking ──────────────────────────────────────────────

SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INT UNSIGNED    NOT NULL,
    applied_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

# ── Users (local mirror of user-center identity) ────────────────────────

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

# ── Sessions (server-side session storage, token hash) ──────────────────

SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    user_id         INT UNSIGNED    NOT NULL,
    token_hash      CHAR(64)        NOT NULL,
    created_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    expires_at      DATETIME(3)     NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_sessions_token_hash (token_hash),
    INDEX idx_sessions_expires (expires_at),
    CONSTRAINT fk_sessions_user_id
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

# ── Tasks (v2: includes owner_user_id and updated_by_user_id) ──────────

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

# ── Full DDL for fresh installs ─────────────────────────────────────────
# Order matters: users before tasks (FK dependency), sessions after users.
# On fresh install, tasks is created with owner_user_id / updated_by_user_id
# already included in the CREATE TABLE, so no ALTER TABLE is needed.

ALL_DDL = [
    SCHEMA_VERSION_DDL,
    USERS_DDL,
    SESSIONS_DDL,
    TASKS_DDL,
    TASK_ASSETS_DDL,
]

SCHEMA_VERSION = 2
