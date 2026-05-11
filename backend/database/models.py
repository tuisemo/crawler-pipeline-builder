"""DDL definitions for crawler workflow database tables and indexes."""

#: tasks table schema
TASKS_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    target_url TEXT,
    status TEXT DEFAULT 'draft' NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

#: task_assets table schema
TASK_ASSETS_DDL = """
CREATE TABLE IF NOT EXISTS task_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    asset_type TEXT NOT NULL,
    content TEXT,
    version INTEGER DEFAULT 1 NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
)
"""

#: index on task_id for fast asset lookups
INDEX_TASK_ASSETS_TASK_ID = """
CREATE INDEX IF NOT EXISTS idx_task_assets_task_id ON task_assets(task_id)
"""

#: composite index on task_id + asset_type for unique asset lookups
INDEX_TASK_ASSETS_TASK_TYPE = """
CREATE INDEX IF NOT EXISTS idx_task_assets_task_type ON task_assets(task_id, asset_type)
"""

ALL_DDLStatements = [
    TASKS_DDL,
    TASK_ASSETS_DDL,
    INDEX_TASK_ASSETS_TASK_ID,
    INDEX_TASK_ASSETS_TASK_TYPE,
]
