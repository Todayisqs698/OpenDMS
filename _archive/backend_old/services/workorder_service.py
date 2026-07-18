"""
工单业务逻辑层 — 串联 AI Agent 和数据库
"""
from sqlalchemy.orm import Session
from app.models import WorkOrder, AuditLog
from app.agents.speech_agent import classify
from app.agents.urgency_agent import evaluate_urgency, suggest_dispatch
from app.agents.audit_agent import audit, callback
from app.core.state_machine import WorkOrderStatus, can_transition
from app.ws.manager import ws_manager


async def process_new_order(db: Session, original_text: str, input_type: str, address: str = "") -> WorkOrder:
    """
    处理新工单全流程：
    1. AI 分类 + 实体提取
    2. AI 紧急度评估
    3. 存入数据库
    4. WebSocket 推送坐席员
    """
    # Step 1: AI 分类
    ai_result = classify(original_text)

    # Step 2: 紧急度评估
    urgency = evaluate_urgency(
        category=f"{ai_result.get('category_l1', '')}/{ai_result.get('category_l2', '')}",
        emotion_score=ai_result.get("emotion_score", 0),
    )

    # Step 3: 创建工单
    order = WorkOrder(
        order_no=f"WO{__import__('datetime').datetime.now().strftime('%Y%m%d%H%M%S')}",
        status=WorkOrderStatus.PENDING.value,
        priority=urgency["priority"],
        input_type=input_type,
        original_text=original_text,
        emotion_score=ai_result.get("emotion_score"),
        address=address,
        category_l1=ai_result.get("category_l1"),
        category_l2=ai_result.get("category_l2"),
        keywords=ai_result.get("keywords", []),
        entities=ai_result.get("entities", []),
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # Step 4: 推送
    await ws_manager.broadcast_new_order({"id": order.id, "order_no": order.order_no, "category": order.category_l2, "priority": order.priority})

    return order
