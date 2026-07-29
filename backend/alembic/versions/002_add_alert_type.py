"""add alert_type column to alerts table

Revision ID: 002
Revises: 001
Create Date: 2026-07-29 12:01:00

给 alerts 表新增 alert_type 字段，用于区分告警类型
（fatigue / distraction / gaze / crowd / absence）。

SQLite 使用 batch 模式执行 ALTER TABLE（render_as_batch=True）。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('alerts') as batch_op:
        batch_op.add_column(sa.Column('alert_type', sa.Text(), nullable=True, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('alerts') as batch_op:
        batch_op.drop_column('alert_type')
