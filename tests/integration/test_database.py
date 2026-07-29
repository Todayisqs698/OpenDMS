"""
测试数据库 CRUD — 需要 SQLite（使用临时数据库）。

覆盖：
  - 创建/结束驾驶会话
  - 插入/查询告警记录
  - 插入/查询交互记录
  - 会话摘要统计
"""
import pytest
from backend.app.core.database import (
    init_db,
    create_drive_session,
    finish_drive_session,
    insert_alert_record,
    insert_interaction_record,
    query_alerts,
    query_interactions,
    get_session_summary,
    set_current_session_id,
    get_current_session_id,
)


class TestDriveSession:
    """驾驶会话 CRUD。"""

    def test_create_session(self, test_db_path):
        """创建会话返回有效 ID。"""
        sid = create_drive_session()
        assert sid > 0

    def test_finish_session(self, test_db_path):
        """结束会话写入 end_time 和 avg_fatigue_score。"""
        sid = create_drive_session()
        finish_drive_session(sid, avg_fatigue_score=45.5)

        summary = get_session_summary(sid)
        assert summary is not None
        assert summary["avg_fatigue_score"] == 45.5
        assert summary["end_time"] is not None

    def test_session_summary_no_alerts(self, test_db_path):
        """无告警的会话摘要 total_alerts=0。"""
        sid = create_drive_session()
        set_current_session_id(sid)
        finish_drive_session(sid)

        summary = get_session_summary(sid)
        assert summary["total_alerts"] == 0

    def test_set_and_get_current_session(self, test_db_path):
        """设置和获取当前会话 ID。"""
        sid = create_drive_session()
        set_current_session_id(sid)
        assert get_current_session_id() == sid


class TestAlertRecords:
    """告警记录 CRUD。"""

    def test_insert_and_query_alerts(self, test_db_path):
        """插入告警后能查询到。"""
        sid = create_drive_session()
        set_current_session_id(sid)

        insert_alert_record(sid, "dangerous", "疲劳驾驶告警", 0.6, 25.0, 85.0)
        insert_alert_record(sid, "mild", "轻微分心", 0.2, 18.0, 35.0)

        alerts = query_alerts(sid)
        assert len(alerts) == 2
        # 按时间倒序，最新的在前
        assert alerts[0]["risk_level"] in ("dangerous", "mild")

    def test_alert_fields_complete(self, test_db_path):
        """告警记录包含所有字段。"""
        sid = create_drive_session()
        set_current_session_id(sid)

        insert_alert_record(sid, "moderate", "分心告警", 0.4, 22.0, 60.0)
        alerts = query_alerts(sid)

        alert = alerts[0]
        assert alert["session_id"] == sid
        assert alert["risk_level"] == "moderate"
        assert alert["alert_msg"] == "分心告警"
        assert alert["perclos"] == 0.4
        assert alert["blink_rate"] == 22.0
        assert alert["fatigue_score"] == 60.0
        assert alert["created_at"] is not None

    def test_query_alerts_empty(self, test_db_path):
        """无告警时返回空列表。"""
        sid = create_drive_session()
        set_current_session_id(sid)

        alerts = query_alerts(sid)
        assert alerts == []

    def test_alert_summary_breakdown(self, test_db_path):
        """会话摘要按风险级别分组。"""
        sid = create_drive_session()
        set_current_session_id(sid)

        insert_alert_record(sid, "dangerous", "严重", 0.6, 25.0, 85.0)
        insert_alert_record(sid, "mild", "轻微", 0.2, 18.0, 35.0)
        insert_alert_record(sid, "mild", "轻微2", 0.3, 19.0, 40.0)

        summary = get_session_summary(sid)
        assert summary["total_alerts"] == 3
        assert summary["level_breakdown"]["mild"] == 2
        assert summary["level_breakdown"]["dangerous"] == 1


class TestInteractionRecords:
    """交互记录 CRUD。"""

    def test_insert_and_query_interactions(self, test_db_path):
        """插入交互记录后能查询到。"""
        sid = create_drive_session()
        set_current_session_id(sid)

        insert_interaction_record(sid, "开空调", "空调已开启")
        insert_interaction_record(sid, "播放音乐", "正在播放音乐")

        interactions = query_interactions(sid)
        assert len(interactions) == 2

    def test_interaction_fields(self, test_db_path):
        """交互记录包含所有字段。"""
        sid = create_drive_session()
        set_current_session_id(sid)

        insert_interaction_record(sid, "今天天气怎么样", "天津今天晴，25度")
        interactions = query_interactions(sid)

        inter = interactions[0]
        assert inter["session_id"] == sid
        assert inter["user_query"] == "今天天气怎么样"
        assert inter["ai_response"] == "天津今天晴，25度"
        assert inter["created_at"] is not None

    def test_query_interactions_empty(self, test_db_path):
        """无交互时返回空列表。"""
        sid = create_drive_session()
        set_current_session_id(sid)

        interactions = query_interactions(sid)
        assert interactions == []
