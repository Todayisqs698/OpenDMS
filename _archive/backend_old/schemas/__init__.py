"""
Pydantic 请求/响应模型 — 组员按这些 Schema 定义接口输入输出
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── 工单 ──
class WorkOrderCreate(BaseModel):
    """市民提交诉求"""
    input_type: str = Field(default="text", description="voice / text / image")
    original_text: str = Field(..., description="诉求文本（语音则填转写结果）")
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    citizen_name: Optional[str] = None
    citizen_phone: Optional[str] = None


class WorkOrderAIResult(BaseModel):
    """AI 处理结果 — 各 Agent 输出的统一格式"""
    category_l1: str = ""
    category_l2: str = ""
    keywords: list[str] = []
    entities: list[dict] = []
    priority: str = "medium"
    priority_score: float = 0.0
    emotion_score: float = 0.0
    suggested_dept: str = ""
    suggested_worker_id: Optional[int] = None
    suggestion: str = ""


class WorkOrderDispatch(BaseModel):
    """坐席员派单"""
    assigned_dept: str
    assigned_to: Optional[int] = None
    priority: str


class WorkOrderResolve(BaseModel):
    """网格员提交处理结果"""
    resolution: str
    media_urls: list[str] = []


class WorkOrderReview(BaseModel):
    """质检审核"""
    review_result: str  # passed / failed
    review_comment: str = ""


class WorkOrderResponse(BaseModel):
    """工单详情（返回给前端）"""
    id: int
    order_no: str
    status: str
    priority: str
    input_type: str
    original_text: str
    emotion_score: Optional[float] = None
    address: Optional[str] = None
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
    keywords: Optional[list] = None
    assigned_dept: Optional[str] = None
    resolution: Optional[str] = None
    review_result: Optional[str] = None
    callback_rating: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── 用户 ──
class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    role: str
    display_name: str


# ── 通用 ──
class APIResponse(BaseModel):
    status: str = "ok"
    message: str = ""
    data: Optional[dict | list] = None
