"""
工单 API — CRUD + 状态流转
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.core.database import get_db
from app.core.state_machine import WorkOrderStatus, can_transition
from app.models import WorkOrder, AuditLog
from app.schemas import (
    WorkOrderCreate, WorkOrderDispatch, WorkOrderResolve,
    WorkOrderReview, WorkOrderResponse, APIResponse,
)
from datetime import datetime

router = APIRouter(prefix="/workorders", tags=["工单"])


def _order_to_response(order: WorkOrder) -> dict:
    return {
        "id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "priority": order.priority,
        "input_type": order.input_type,
        "original_text": order.original_text,
        "emotion_score": order.emotion_score,
        "address": order.address,
        "category_l1": order.category_l1,
        "category_l2": order.category_l2,
        "keywords": order.keywords or [],
        "assigned_dept": order.assigned_dept,
        "assigned_to": order.assigned_to,
        "resolution": order.resolution,
        "media_urls": order.media_urls or [],
        "review_result": order.review_result,
        "review_comment": order.review_comment,
        "callback_rating": order.callback_rating,
        "callback_feedback": order.callback_feedback,
        "created_at": str(order.created_at) if order.created_at else None,
        "updated_at": str(order.updated_at) if order.updated_at else None,
    }


@router.post("/", response_model=APIResponse)
def create_workorder(req: WorkOrderCreate, db: Session = Depends(get_db)):
    """市民提交诉求"""
    import asyncio
    from app.agents.speech_agent import classify
    from app.agents.urgency_agent import evaluate_urgency
    from app.ws.manager import ws_manager

    # AI 分类
    ai = classify(req.original_text)

    # AI 紧急度评分
    urg = evaluate_urgency(
        category=f"{ai.get('category_l1','')}/{ai.get('category_l2','')}",
        emotion_score=ai.get("emotion_score", 0),
    )

    # 创建工单
    order = WorkOrder(
        order_no=f"WO{datetime.now().strftime('%Y%m%d%H%M%S')}",
        status=WorkOrderStatus.PENDING.value,
        priority=urg["priority"],
        input_type=req.input_type,
        original_text=req.original_text,
        emotion_score=ai.get("emotion_score"),
        address=req.address,
        latitude=req.latitude,
        longitude=req.longitude,
        citizen_name=req.citizen_name,
        citizen_phone=req.citizen_phone,
        category_l1=ai.get("category_l1"),
        category_l2=ai.get("category_l2"),
        keywords=ai.get("keywords", []),
        entities=ai.get("entities", []),
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # WebSocket 推送
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(ws_manager.broadcast_new_order({
            "id": order.id,
            "order_no": order.order_no,
            "category": order.category_l2,
            "priority": order.priority,
            "text": order.original_text[:50],
        }))
    except Exception:
        pass

    return {"status": "ok", "data": _order_to_response(order)}


@router.get("/", response_model=APIResponse)
def list_workorders(
    status: str = Query(None),
    priority: str = Query(None),
    assigned_to: int = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """工单列表"""
    q = db.query(WorkOrder)
    if status:
        q = q.filter(WorkOrder.status == status)
    if priority:
        q = q.filter(WorkOrder.priority == priority)
    if assigned_to:
        q = q.filter(WorkOrder.assigned_to == assigned_to)
    total = q.count()
    orders = q.order_by(desc(WorkOrder.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "status": "ok",
        "data": {
            "items": [_order_to_response(o) for o in orders],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    }


@router.get("/{order_id}", response_model=APIResponse)
def get_workorder(order_id: int, db: Session = Depends(get_db)):
    """工单详情"""
    order = db.query(WorkOrder).filter(WorkOrder.id == order_id).first()
    if not order:
        return {"status": "error", "message": "工单不存在"}
    # 附带操作日志
    logs = db.query(AuditLog).filter(AuditLog.order_id == order_id).order_by(AuditLog.created_at).all()
    return {
        "status": "ok",
        "data": {
            "order": _order_to_response(order),
            "logs": [{"action": l.action, "detail": l.detail, "time": str(l.created_at)} for l in logs],
        }
    }


@router.put("/{order_id}/dispatch", response_model=APIResponse)
def dispatch_workorder(order_id: int, req: WorkOrderDispatch, db: Session = Depends(get_db)):
    """坐席员派单"""
    import asyncio
    from app.ws.manager import ws_manager

    order = db.query(WorkOrder).filter(WorkOrder.id == order_id).first()
    if not order:
        return {"status": "error", "message": "工单不存在"}
    if not can_transition(WorkOrderStatus(order.status), WorkOrderStatus.DISPATCHED):
        return {"status": "error", "message": f"当前状态 {order.status} 不可派单"}

    order.status = WorkOrderStatus.DISPATCHED.value
    order.priority = req.priority
    order.assigned_dept = req.assigned_dept
    order.assigned_to = req.assigned_to
    order.updated_at = datetime.utcnow()
    db.commit()

    # 推送网格员
    if req.assigned_to:
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(ws_manager.notify_gridworker(req.assigned_to, {
                "id": order.id, "order_no": order.order_no, "category": order.category_l2,
            }))
        except Exception:
            pass

    return {"status": "ok", "data": _order_to_response(order)}


@router.put("/{order_id}/resolve", response_model=APIResponse)
def resolve_workorder(order_id: int, req: WorkOrderResolve, db: Session = Depends(get_db)):
    """网格员提交处理结果"""
    order = db.query(WorkOrder).filter(WorkOrder.id == order_id).first()
    if not order:
        return {"status": "error", "message": "工单不存在"}
    if not can_transition(WorkOrderStatus(order.status), WorkOrderStatus.COMPLETED):
        return {"status": "error", "message": f"当前状态 {order.status} 不可提交"}

    order.status = WorkOrderStatus.COMPLETED.value
    order.resolution = req.resolution
    order.media_urls = req.media_urls
    order.completed_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()
    db.commit()

    # 写入操作日志
    log = AuditLog(order_id=order.id, action="resolve", detail=f"网格员提交处理结果")
    db.add(log)
    db.commit()

    return {"status": "ok", "data": _order_to_response(order)}


@router.put("/{order_id}/review", response_model=APIResponse)
def review_workorder(order_id: int, req: WorkOrderReview, db: Session = Depends(get_db)):
    """质检审核"""
    order = db.query(WorkOrder).filter(WorkOrder.id == order_id).first()
    if not order:
        return {"status": "error", "message": "工单不存在"}

    target = WorkOrderStatus.REVIEW_PASSED if req.review_result == "passed" else WorkOrderStatus.REVIEW_FAILED
    if not can_transition(WorkOrderStatus(order.status), target):
        return {"status": "error", "message": f"当前状态 {order.status} 不可审核"}

    order.status = target.value
    order.review_result = req.review_result
    order.review_comment = req.review_comment
    order.updated_at = datetime.utcnow()
    db.commit()

    return {"status": "ok", "data": _order_to_response(order)}


@router.put("/{order_id}/accept", response_model=APIResponse)
def accept_workorder(order_id: int, db: Session = Depends(get_db)):
    """🅲 网格员接单：dispatched → in_progress"""
    order = db.query(WorkOrder).filter(WorkOrder.id == order_id).first()
    if not order:
        return {"status": "error", "message": "工单不存在"}

    if not can_transition(WorkOrderStatus(order.status), WorkOrderStatus.IN_PROGRESS):
        return {"status": "error", "message": f"当前状态 {order.status} 不可接单，仅 dispatched 状态可接单"}

    order.status = WorkOrderStatus.IN_PROGRESS.value
    order.updated_at = datetime.utcnow()
    db.commit()

    # 写入操作日志
    log = AuditLog(order_id=order.id, action="accept", detail="网格员接单")
    db.add(log)
    db.commit()

    return {"status": "ok", "data": _order_to_response(order)}


@router.put("/{order_id}/auto-audit", response_model=APIResponse)
def auto_audit_workorder(order_id: int, db: Session = Depends(get_db)):
    """🅲 AI 自动质检：completed → review_passed / review_failed"""
    from app.agents.audit_agent import audit

    order = db.query(WorkOrder).filter(WorkOrder.id == order_id).first()
    if not order:
        return {"status": "error", "message": "工单不存在"}

    if not can_transition(WorkOrderStatus(order.status), WorkOrderStatus.REVIEW_PASSED):
        return {"status": "error", "message": f"当前状态 {order.status} 不可质检，仅 completed 状态可质检"}

    # 计算处理耗时
    hours_spent = 0.0
    if order.created_at:
        delta = datetime.utcnow() - order.created_at
        hours_spent = delta.total_seconds() / 3600

    # 检查是否有现场材料
    has_media = bool(order.media_urls)

    # 统计该地址历史投诉次数（简易实现）
    history_count = 0
    if order.address:
        history_count = db.query(WorkOrder).filter(
            WorkOrder.address == order.address,
            WorkOrder.id != order.id,
        ).count()

    # 调用 AI 质检
    audit_result = audit(
        resolution=order.resolution or "",
        history_count=history_count,
        has_media=has_media,
        hours_spent=hours_spent,
    )

    # 根据质检结果更新状态
    if audit_result["review_result"] == "passed":
        order.status = WorkOrderStatus.REVIEW_PASSED.value
    else:
        order.status = WorkOrderStatus.REVIEW_FAILED.value

    order.review_result = audit_result["review_result"]
    order.review_comment = audit_result["review_comment"]
    order.updated_at = datetime.utcnow()
    db.commit()

    # 写入操作日志
    log = AuditLog(
        order_id=order.id,
        action="auto_audit",
        detail=f"AI自动质检：{audit_result['review_result']} — {audit_result.get('review_comment', '')}",
    )
    db.add(log)
    db.commit()

    return {
        "status": "ok",
        "data": {
            "order": _order_to_response(order),
            "audit_result": audit_result,
        },
    }


@router.put("/{order_id}/callback", response_model=APIResponse)
def callback_workorder(order_id: int, db: Session = Depends(get_db)):
    """🅲 AI 自动回访：review_passed → done"""
    from app.agents.audit_agent import callback

    order = db.query(WorkOrder).filter(WorkOrder.id == order_id).first()
    if not order:
        return {"status": "error", "message": "工单不存在"}

    if not can_transition(WorkOrderStatus(order.status), WorkOrderStatus.DONE):
        return {"status": "error", "message": f"当前状态 {order.status} 不可回访，仅 review_passed 状态可回访"}

    # 调用 AI 回访
    callback_result = callback(
        phone=order.citizen_phone or "未知",
        order_summary=f"{order.category_l2}: {order.original_text[:80] if order.original_text else ''}",
        resolution=order.resolution or "",
    )

    # 更新状态
    order.status = WorkOrderStatus.DONE.value
    order.callback_rating = callback_result["rating"]
    order.callback_feedback = callback_result["feedback"]
    order.updated_at = datetime.utcnow()
    db.commit()

    # 写入操作日志
    retry_hint = "（建议创建二次工单）" if callback_result.get("auto_retry") else ""
    log = AuditLog(
        order_id=order.id,
        action="callback",
        detail=f"AI回访：评分{callback_result['rating']}分 — {callback_result.get('feedback', '')}{retry_hint}",
    )
    db.add(log)
    db.commit()

    return {
        "status": "ok",
        "data": {
            "order": _order_to_response(order),
            "callback_result": callback_result,
        },
    }


@router.get("/citizen/{phone}", response_model=APIResponse)
def track_by_phone(phone: str, db: Session = Depends(get_db)):
    """市民按手机号查询工单进度"""
    orders = db.query(WorkOrder).filter(WorkOrder.citizen_phone == phone).order_by(desc(WorkOrder.created_at)).limit(10).all()
    return {"status": "ok", "data": {"orders": [_order_to_response(o) for o in orders]}}
