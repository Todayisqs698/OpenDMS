"""
SQLite 数据库连接 + 会话管理
组员直接用：from app.core.database import get_db
"""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

# 确保数据库文件所在目录存在
db_path = settings.DATABASE_URL.replace("sqlite:///", "")
if db_path and not db_path.startswith(":memory:"):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    """启动时建表"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI 依赖注入：每个请求一个数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
