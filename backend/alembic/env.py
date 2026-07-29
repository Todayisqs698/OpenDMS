"""
Alembic 迁移环境配置。

本项目使用原生 sqlite3（无 ORM），因此 Alembic 仅作为版本化 DDL 管理工具：
迁移脚本中用 op.execute() 写原始 SQL，不依赖 SQLAlchemy 模型。

SQLite 不支持完整的 ALTER TABLE，通过 render_as_batch=True 启用批量模式。
"""
import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context

# ── 将项目根目录加入 sys.path，使 import backend.* 可用 ──
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── 动态获取数据库路径 ──
try:
    from backend.app.core.database import DB_FILE
    db_path = str(DB_FILE)
except Exception:
    # 回退到默认路径
    db_path = str(PROJECT_ROOT / "data" / "edgeguard.db")

# Alembic 配置
config = context.config

# 设置数据库 URL（覆盖 alembic.ini 中的占位值）
config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

# 日志配置
if config.config_file_name is not None:
    fileConfig(config)

# 目标 metadata（本项目无 ORM，设为 None，用原始 SQL）
target_metadata = None


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而不连接数据库。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite 批量模式
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直接连接数据库执行迁移。"""
    from sqlalchemy import engine_from_config, pool

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite 批量模式
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
