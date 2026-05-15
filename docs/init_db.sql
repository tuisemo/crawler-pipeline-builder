-- ============================================================================
-- Scraper Flow Studio — 数据库初始化 DDL
-- ============================================================================
--
-- 用途：供运维直接复制到 MySQL 客户端执行，无需通过脚本连接。
--
-- 说明：
--   - 使用 IF NOT EXISTS，可安全重复执行（幂等）
--   - 执行顺序：users → tasks → task_assets（外键依赖）
--   - 字符集：utf8mb4 + utf8mb4_unicode_ci
--   - 会话和 OAuth 状态存储在 Redis 中，不在此数据库内
--
-- 来源：backend/database/models.py + scripts/db_init.py
--       如表结构变更，请同步更新以上两处及本文件。
-- ============================================================================

-- ── 1. 创建数据库（可选，通常由 DBA 预先创建）──────────────────────────
-- CREATE DATABASE IF NOT EXISTS `crawler_workflow`
--   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- USE `crawler_workflow`;

-- ── 2. 用户表（用户中心身份本地镜像）────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    external_id     VARCHAR(128)    NOT NULL           COMMENT '用户中心 openId',
    display_name    VARCHAR(200)    NOT NULL DEFAULT '' COMMENT '显示名称',
    email           VARCHAR(320)    NULL               COMMENT '邮箱',
    avatar_url      VARCHAR(2048)   NULL               COMMENT '头像 URL',
    synced_at       DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '最近一次从用户中心同步的时间',
    created_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_external_id (external_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户表 — 用户中心身份本地镜像';

-- ── 3. 任务表（爬虫任务记录）────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id                  INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    owner_user_id       INT UNSIGNED    NOT NULL           COMMENT '任务所有者 user.id',
    name                VARCHAR(200)    NOT NULL           COMMENT '任务名称',
    description         TEXT            NULL               COMMENT '任务描述',
    target_url          VARCHAR(2048)   NULL               COMMENT '目标网站 URL',
    status              VARCHAR(20)     NOT NULL DEFAULT 'draft' COMMENT '任务状态: draft / running / completed / failed',
    updated_by_user_id  INT UNSIGNED    NULL               COMMENT '最近更新者 user.id',
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
  COMMENT='任务表 — 爬虫任务记录';

-- ── 4. 任务资产表（版本化资产）──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS task_assets (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    task_id     INT UNSIGNED    NOT NULL           COMMENT '所属任务 tasks.id',
    asset_type  VARCHAR(50)     NOT NULL           COMMENT '资产类型: schema/preview, script, config 等',
    content     LONGTEXT        NULL               COMMENT '资产内容 (JSON / 代码 / 配置)',
    version     INT UNSIGNED    NOT NULL DEFAULT 1 COMMENT '版本号，每次保存自增',
    created_at  DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    CONSTRAINT fk_task_assets_task_id
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    INDEX idx_task_assets_latest (task_id, asset_type, version DESC),
    UNIQUE KEY uq_task_assets_version (task_id, asset_type, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='任务资产表 — 版本化资产 (DSL schema, 生成脚本, 配置等)';
