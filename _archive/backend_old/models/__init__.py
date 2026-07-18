"""
数据模型 — SQLAlchemy ORM 定义
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, JSON
from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False)  # citizen / operator / gridworker / admin
    display_name = Column(String(50))
    phone = Column(String(20))
    department = Column(String(100))  # 所属部门
    grid_area = Column(String(100))   # 负责网格区域（网格员）
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkOrder(Base):
    __tablename__ = "workorders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(30), unique=True, nullable=False)  # 工单号
    status = Column(String(30), nullable=False, default="pending")
    priority = Column(String(10), nullable=False, default="medium")

    # 诉求内容
    citizen_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    citizen_name = Column(String(50))
    citizen_phone = Column(String(20))
    input_type = Column(String(20))  # voice / text / image
    original_text = Column(Text)     # 原始诉求文本（语音转写后）
    emotion_score = Column(Float)    # 情绪评分 0-100
    address = Column(String(200))    # 事发地址
    latitude = Column(Float)         # 地理坐标
    longitude = Column(Float)

    # AI 分类结果
    category_l1 = Column(String(50))  # 一级分类
    category_l2 = Column(String(50))  # 二级分类
    keywords = Column(JSON)           # 关键词列表
    entities = Column(JSON)           # 实体列表

    # 派单
    assigned_dept = Column(String(100))
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)

    # 处置
    resolution = Column(Text)         # 处理结果
    media_urls = Column(JSON)         # 现场照片/录音
    completed_at = Column(DateTime)

    # 质检
    review_result = Column(String(20))  # passed / failed
    review_comment = Column(Text)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # 回访
    callback_rating = Column(Integer)   # 1-5 星
    callback_feedback = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeEntry(Base):
    __tablename__ = "knowledge"
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50))       # 问题类型
    title = Column(String(200))
    content = Column(Text)               # 处置方案
    laws = Column(JSON)                  # 适用法规
    tags = Column(JSON)                  # 标签
    source_order_id = Column(Integer)    # 来源工单
    use_count = Column(Integer, default=0)  # 被引用次数
    created_at = Column(DateTime, default=datetime.utcnow)


class RuleConfig(Base):
    __tablename__ = "rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_type = Column(String(30))       # category_mapping / sla / callback
    key = Column(String(100))            # 规则键
    value = Column(JSON)                 # 规则值
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("workorders.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(50))          # 操作类型
    detail = Column(Text)                # 操作详情
    created_at = Column(DateTime, default=datetime.utcnow)
