"""
Mock 数据初始化脚本
运行: python seed_data.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.core.database import init_db, SessionLocal
from app.core.security import hash_password
from app.models import User, WorkOrder, RuleConfig, AuditLog
from app.core.state_machine import WorkOrderStatus, Priority
from datetime import datetime, timedelta
import random

db = SessionLocal()
init_db()

# ── 清空旧数据 ──
for t in [AuditLog, WorkOrder, RuleConfig, User]:
    db.query(t).delete()
db.commit()

# ── 创建用户 ──
users = [
    User(username="admin", password_hash=hash_password("123456"), role="admin", display_name="张主任"),
    User(username="operator1", password_hash=hash_password("123456"), role="operator", display_name="王坐席"),
    User(username="operator2", password_hash=hash_password("123456"), role="operator", display_name="刘坐席"),
    User(username="worker1", password_hash=hash_password("123456"), role="gridworker", display_name="李建国", grid_area="第7网格"),
    User(username="worker2", password_hash=hash_password("123456"), role="gridworker", display_name="陈大民", grid_area="第3网格"),
    User(username="worker3", password_hash=hash_password("123456"), role="gridworker", display_name="赵小红", grid_area="第5网格"),
    User(username="citizen1", password_hash=hash_password("123456"), role="citizen", display_name="市民张三", phone="13800001111"),
]
db.add_all(users)
db.commit()

# ── 创建工单 ──
MOCK_ORDERS = [
    {"text": "楼下老王烧烤店每天晚上营业到凌晨两三点，食客大声喧哗，油烟直接飘到楼上，窗户都不敢开。已经是这个月第三次了！",
     "cat_l1": "城市管理", "cat_l2": "噪音扰民", "addr": "XX路15号", "pri": "high", "status": "pending"},
    {"text": "我们小区3栋2单元的电梯坏了三天了，物业说在修但一直没动静，老人小孩爬楼梯太危险了",
     "cat_l1": "公共安全", "cat_l2": "电梯故障", "addr": "YY小区3栋", "pri": "high", "status": "dispatched"},
    {"text": "ZZ路和AA路交叉口的路灯不亮一个礼拜了，晚上黑漆漆的，骑车经过很危险",
     "cat_l1": "城市管理", "cat_l2": "路灯报修", "addr": "ZZ路与AA路交叉口", "pri": "medium", "status": "completed"},
    {"text": "BB小区门口垃圾堆了三天没人清理，夏天到了臭气熏天，蚊虫乱飞",
     "cat_l1": "城市管理", "cat_l2": "垃圾堆积", "addr": "BB小区南门", "pri": "medium", "status": "in_progress"},
    {"text": "CC健身房突然关门跑路了，我还有两年会员卡没用完，二千多块钱呢！好多人都被骗了",
     "cat_l1": "市场监管", "cat_l2": "消费纠纷", "addr": "CC大厦3楼", "pri": "medium", "status": "pending"},
    {"text": "DD路有个井盖不见了，昨天差点骑车掉进去，太吓人了",
     "cat_l1": "公共安全", "cat_l2": "井盖丢失", "addr": "DD路中段", "pri": "high", "status": "review_passed"},
    {"text": "楼下KTV隔音太差，每天晚上咚咚咚的低音炮震得人睡不着。我家有老人有心脏病！",
     "cat_l1": "城市管理", "cat_l2": "噪音扰民", "addr": "EE路8号", "pri": "high", "status": "pending"},
    {"text": "小区旁边的工地早上六点就开始施工，噪音巨大，严重影响休息",
     "cat_l1": "城市管理", "cat_l2": "施工噪音", "addr": "FF小区东侧", "pri": "medium", "status": "dispatched"},
    {"text": "我们这条街的共享单车乱停乱放，把人行道都堵死了，老人过路都要绕到马路上",
     "cat_l1": "城市管理", "cat_l2": "占道经营", "addr": "GG路步行街", "pri": "medium", "status": "in_progress"},
    {"text": "HH农贸市场有人卖注水猪肉，买回家一炒全是水，希望市场监管部门查一下",
     "cat_l1": "市场监管", "cat_l2": "食品安全", "addr": "HH农贸市场", "pri": "medium", "status": "pending"},
    {"text": "我们单元楼上漏水到我家天花板，找物业说不管，找楼上业主联系不上，怎么办？",
     "cat_l1": "民生服务", "cat_l2": "物业纠纷", "addr": "II小区5栋402", "pri": "medium", "status": "completed"},
    {"text": "JJ路口每天早上堵车堵到疯，红绿灯时间太短了，建议调整",
     "cat_l1": "交通出行", "cat_l2": "交通拥堵", "addr": "JJ路与KK路交叉口", "pri": "low", "status": "done"},
]

depts = ["城管执法中队", "环卫所", "市场监管局", "街道办", "应急管理局", "市政公司"]
worker_ids = [4, 5, 6]  # worker1/2/3

# 🅲 确保 worker1 (id=4) 在各个状态都有工单用于演示
worker1_statuses = {
    0: "dispatched",    # 待接单
    1: "in_progress",   # 处理中
    2: "completed",     # 已提交待质检
    3: "review_passed", # 质检通过待回访
    4: "review_failed", # 质检驳回
    5: "done",          # 已完成
}

for i, m in enumerate(MOCK_ORDERS):
    # 🅲 前几个工单固定分配给 worker1，保证演示流程完整
    if i in worker1_statuses:
        assigned_to = 4
        status = worker1_statuses[i]
    else:
        assigned_to = random.choice(worker_ids) if m["status"] in ("dispatched", "in_progress", "completed", "review_passed", "review_failed", "done") else None
        status = m["status"]

    # 🅲 为非 pending 状态补充处置结果
    resolution = None
    if status in ("completed", "review_passed", "review_failed", "done"):
        resolution = "网格员已到现场核查，责令相关责任方限期整改，现场拍照取证，后续将持续跟进复查。"
    elif status == "in_progress":
        resolution = None  # 处理中尚未提交

    order = WorkOrder(
        order_no=f"WO20260713{i+1000:04d}",
        status=status,
        priority=m["pri"],
        input_type="text",
        original_text=m["text"],
        emotion_score=random.randint(40, 95),
        address=m["addr"],
        citizen_phone=f"1380000{i+1000:04d}"[:11],  # 🅲 补充市民电话用于回访
        category_l1=m["cat_l1"],
        category_l2=m["cat_l2"],
        keywords=m["text"][:3].split("，"),
        assigned_dept=random.choice(depts) if status not in ("pending",) else None,
        assigned_to=assigned_to,
        resolution=resolution,
        media_urls=["现场照片1.jpg", "整改后照片2.jpg"] if status in ("completed", "review_passed", "review_failed", "done") else None,
        review_result="passed" if status in ("review_passed", "done") else ("failed" if status == "review_failed" else None),
        review_comment="处理规范，材料齐全" if status in ("review_passed", "done") else ("处置结果不够详细，请补充" if status == "review_failed" else None),
        callback_rating=random.randint(4, 5) if status == "done" else None,
        callback_feedback="市民表示满意" if status == "done" else None,
        created_at=datetime.utcnow() - timedelta(hours=random.randint(1, 72)),
        updated_at=datetime.utcnow() - timedelta(minutes=random.randint(1, 120)),
    )
    db.add(order)
db.commit()

# ── 默认规则 ──
rules = [
    RuleConfig(rule_type="category_mapping", key="噪音扰民", value={"dept": "城管执法中队", "sla_hours": 24}),
    RuleConfig(rule_type="category_mapping", key="垃圾堆积", value={"dept": "环卫所", "sla_hours": 48}),
    RuleConfig(rule_type="category_mapping", key="电梯故障", value={"dept": "应急管理局", "sla_hours": 2}),
    RuleConfig(rule_type="category_mapping", key="消费纠纷", value={"dept": "市场监管局", "sla_hours": 72}),
    RuleConfig(rule_type="sla", key="high", value={"hours": 2}),
    RuleConfig(rule_type="sla", key="medium", value={"hours": 24}),
    RuleConfig(rule_type="sla", key="low", value={"hours": 48}),
    RuleConfig(rule_type="callback", key="auto", value={"enabled": True, "retry_on_dissatisfied": True, "skip_if_rating_above": 4}),
]
db.add_all(rules)
db.commit()

print(f"Seed OK: {len(users)} users, {len(MOCK_ORDERS)} orders, {len(rules)} rules")
db.close()
