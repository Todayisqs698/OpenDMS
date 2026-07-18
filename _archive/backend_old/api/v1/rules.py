"""
可配置规则引擎接口（管理员）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import RuleConfig
from app.schemas import APIResponse

router = APIRouter(prefix="/rules", tags=["规则引擎"])

DEFAULTS = {
    "category_mapping": [
        {"key": "噪音扰民", "dept": "城管执法中队", "sla_hours": 24},
        {"key": "垃圾堆积", "dept": "环卫所", "sla_hours": 48},
        {"key": "电梯故障", "dept": "应急管理局", "sla_hours": 2},
        {"key": "消费纠纷", "dept": "市场监管局", "sla_hours": 72},
        {"key": "停水停电", "dept": "市政公司", "sla_hours": 4},
        {"key": "物业纠纷", "dept": "街道办", "sla_hours": 48},
    ],
    "sla": [
        {"key": "high", "hours": 2},
        {"key": "medium", "hours": 24},
        {"key": "low", "hours": 48},
    ],
    "callback": [
        {"key": "auto", "enabled": True, "retry": True, "skip_above": 4},
    ],
}


@router.get("/")
def list_rules(rule_type: str = "", db: Session = Depends(get_db)):
    """获取规则（数据库优先，否则返回默认值）"""
    q = db.query(RuleConfig)
    if rule_type:
        q = q.filter(RuleConfig.rule_type == rule_type)
    db_rules = q.all()

    if db_rules:
        return {"status": "ok", "data": {"rules": [{"id": r.id, "type": r.rule_type, "key": r.key, "value": r.value} for r in db_rules]}}

    # 返回默认规则
    rules = []
    if rule_type and rule_type in DEFAULTS:
        for item in DEFAULTS[rule_type]:
            rules.append({"id": 0, "type": rule_type, "key": item["key"], "value": item})
    elif not rule_type:
        for t, items in DEFAULTS.items():
            for item in items:
                rules.append({"id": 0, "type": t, "key": item["key"], "value": item})

    return {"status": "ok", "data": {"rules": rules}}


@router.post("/")
def create_rule(rule_type: str, key: str, value: dict, db: Session = Depends(get_db)):
    """新增规则"""
    exist = db.query(RuleConfig).filter_by(rule_type=rule_type, key=key).first()
    if exist:
        exist.value = value
    else:
        db.add(RuleConfig(rule_type=rule_type, key=key, value=value))
    db.commit()
    return {"status": "ok", "message": "规则已保存"}


@router.put("/{rule_id}")
def update_rule(rule_id: int, value: dict, db: Session = Depends(get_db)):
    """修改规则"""
    rule = db.query(RuleConfig).filter_by(id=rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    rule.value = value
    db.commit()
    return {"status": "ok", "message": "规则已更新"}


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    """删除规则"""
    db.query(RuleConfig).filter_by(id=rule_id).delete()
    db.commit()
    return {"status": "ok", "message": "规则已删除"}
