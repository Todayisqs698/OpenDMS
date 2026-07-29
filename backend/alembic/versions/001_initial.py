"""initial: drive_sessions, alerts, interactions

Revision ID: 001
Revises:
Create Date: 2026-07-29 12:00:00

创建 EdgeGuard 主数据库的三张核心表：
  - drive_sessions  驾驶会话
  - alerts          告警记录
  - interactions    语音交互记录

与 backend/app/core/database.py 中 init_db() 的建表语句保持一致。
Alembic 管理版本化迁移后，init_db() 可逐步退役。
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 驾驶会话表
    op.execute("""
        CREATE TABLE IF NOT EXISTS drive_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL,
            end_time TEXT,
            avg_fatigue_score REAL,
            remark TEXT
        )
    """)

    # 2. 告警记录表
    op.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            risk_level TEXT NOT NULL,
            alert_msg TEXT,
            perclos REAL,
            blink_rate REAL,
            fatigue_score REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES drive_sessions(id)
        )
    """)

    # 3. 语音交互记录表
    op.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            user_query TEXT,
            ai_response TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES drive_sessions(id)
        )
    """)

    # 创建索引加速查询
    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_session ON alerts(session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_interactions_session ON interactions(session_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS interactions")
    op.execute("DROP TABLE IF EXISTS alerts")
    op.execute("DROP TABLE IF EXISTS drive_sessions")
