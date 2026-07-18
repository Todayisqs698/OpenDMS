"""
可配置规则引擎 — 连接数据库规则表，与系统配置页联动
"""
from sqlalchemy.orm import Session
from app.models import RuleConfig

# 兜底默认值（数据库没配时用）
DEFAULTS = {
    "category_mapping": {
        "噪音扰民": {"dept": "城管执法中队", "sla_hours": 24},
        "垃圾堆积": {"dept": "环卫所", "sla_hours": 48},
        "电梯故障": {"dept": "应急管理局", "sla_hours": 2},
        "消费纠纷": {"dept": "市场监管局", "sla_hours": 72},
        "停水停电": {"dept": "市政公司", "sla_hours": 4},
        "物业纠纷": {"dept": "街道办", "sla_hours": 48},
        "施工噪音": {"dept": "城管执法中队", "sla_hours": 24},
        "井盖丢失": {"dept": "市政公司", "sla_hours": 2},
        "食品安全": {"dept": "市场监管局", "sla_hours": 24},
        "交通拥堵": {"dept": "公安局", "sla_hours": 72},
    },
    "sla": {
        "high": {"hours": 2},
        "medium": {"hours": 24},
        "low": {"hours": 48},
    },
    "callback": {
        "auto": {"enabled": True, "retry": True, "skip_above": 4},
    },
}


def get_category_dept(db: Session, category: str) -> str:
    """根据分类获取负责部门：数据库 > 默认值"""
    rule = db.query(RuleConfig).filter_by(rule_type="category_mapping", key=category).first()
    if rule and isinstance(rule.value, dict) and "dept" in rule.value:
        return rule.value["dept"]
    return DEFAULTS["category_mapping"].get(category, {}).get("dept", "街道办")


def get_sla_hours(db: Session, priority: str) -> int:
    """获取 SLA 响应时限（小时）：数据库 > 默认值"""
    rule = db.query(RuleConfig).filter_by(rule_type="sla", key=priority).first()
    if rule and isinstance(rule.value, dict) and "hours" in rule.value:
        return rule.value["hours"]
    return DEFAULTS["sla"].get(priority, {}).get("hours", 48)


def get_callback_config(db: Session) -> dict:
    """获取回访策略配置"""
    rule = db.query(RuleConfig).filter_by(rule_type="callback", key="auto").first()
    if rule and isinstance(rule.value, dict):
        return rule.value
    return DEFAULTS["callback"]["auto"]
