"""
工单状态机 — 定义工单全生命周期状态流转
"""
from enum import Enum


class WorkOrderStatus(str, Enum):
    PENDING = "pending"           # 待审核（AI 已预处理，等坐席员确认）
    DISPATCHED = "dispatched"     # 已派单（网格员待接单）
    IN_PROGRESS = "in_progress"   # 处理中（网格员已接单）
    COMPLETED = "completed"       # 已办结（网格员提交，待质检）
    REVIEW_PASSED = "review_passed"   # 质检通过
    REVIEW_FAILED = "review_failed"   # 质检驳回（退回网格员）
    CALLBACK_PENDING = "callback_pending"  # 待回访
    DONE = "done"                 # 已完成（回访通过，归档）
    CANCELLED = "cancelled"       # 已撤销（重复工单/无效诉求）


# 允许的状态流转
ALLOWED_TRANSITIONS = {
    WorkOrderStatus.PENDING: [WorkOrderStatus.DISPATCHED, WorkOrderStatus.CANCELLED],
    WorkOrderStatus.DISPATCHED: [WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.CANCELLED],
    WorkOrderStatus.IN_PROGRESS: [WorkOrderStatus.COMPLETED],
    WorkOrderStatus.COMPLETED: [WorkOrderStatus.REVIEW_PASSED, WorkOrderStatus.REVIEW_FAILED],
    WorkOrderStatus.REVIEW_PASSED: [WorkOrderStatus.CALLBACK_PENDING, WorkOrderStatus.DONE],
    WorkOrderStatus.REVIEW_FAILED: [WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.COMPLETED],  # 退回重办或直接重新提交
    WorkOrderStatus.CALLBACK_PENDING: [WorkOrderStatus.DONE],
    WorkOrderStatus.DONE: [],  # 终态
    WorkOrderStatus.CANCELLED: [],  # 终态
}


def can_transition(current: WorkOrderStatus, target: WorkOrderStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, [])


class Priority(str, Enum):
    HIGH = "high"       # 🔴 紧急（2h）
    MEDIUM = "medium"   # 🟡 中等（24h）
    LOW = "low"         # 🟢 普通（48h）
