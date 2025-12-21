"""Peewee migrations -- 019_add_shared_file_fields.py.

添加共享文件空间字段：
- space_type: 文件空间类型（'personal' | 'shared'）
- space_id: 空间ID（个人文件为user_id，共享文件为'global'或group_id）

"""

from contextlib import suppress
import logging

import peewee as pw
from peewee_migrate import Migrator


with suppress(ImportError):
    import playhouse.postgres_ext as pw_pext

log = logging.getLogger(__name__)


def migrate(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your migrations here."""

    # 检查字段是否已存在（通过查询表结构）
    cursor = database.execute_sql("PRAGMA table_info(file)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    
    # 添加 space_type 字段（如果不存在）
    if "space_type" not in existing_columns:
        try:
            migrator.sql("ALTER TABLE file ADD COLUMN space_type VARCHAR(20) DEFAULT 'personal'")
            log.info("Added space_type column")
        except Exception as e:
            log.warning(f"Failed to add space_type column (may already exist): {e}")
    else:
        log.info("space_type column already exists, skipping")
    
    # 添加 space_id 字段（如果不存在）
    if "space_id" not in existing_columns:
        try:
            migrator.sql("ALTER TABLE file ADD COLUMN space_id VARCHAR(255)")
            log.info("Added space_id column")
        except Exception as e:
            log.warning(f"Failed to add space_id column (may already exist): {e}")
    else:
        log.info("space_id column already exists, skipping")
    
    # 删除可能已存在的索引（如果之前迁移失败）
    for index_name in ["file_space_id", "idx_file_space", "idx_file_user_space", "idx_file_group"]:
        try:
            migrator.sql(f"DROP INDEX IF EXISTS {index_name}")
        except Exception as e:
            log.debug(f"Could not drop index {index_name}: {e}")

    # 创建索引（使用 IF NOT EXISTS）
    try:
        migrator.sql("CREATE INDEX IF NOT EXISTS idx_file_space ON file(space_type, space_id)")
    except Exception as e:
        log.warning(f"Failed to create idx_file_space: {e}")
    
    try:
        migrator.sql("CREATE INDEX IF NOT EXISTS idx_file_user_space ON file(user_id, space_type)")
    except Exception as e:
        log.warning(f"Failed to create idx_file_user_space: {e}")
    
    try:
        migrator.sql("CREATE INDEX IF NOT EXISTS idx_file_group ON file(space_id)")
    except Exception as e:
        log.warning(f"Failed to create idx_file_group: {e}")


def rollback(migrator: Migrator, database: pw.Database, *, fake=False):
    """Write your rollback migrations here."""

    # 删除索引
    migrator.drop_index("file", "space_id")
    migrator.drop_index("file", "user_id", "space_type")
    migrator.drop_index("file", "space_type", "space_id")

    # 删除字段
    migrator.remove_fields("file", "space_id", "space_type")

