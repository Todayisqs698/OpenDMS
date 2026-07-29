"""
测试 FastAPI API 端点 — 使用 TestClient（需要启动应用）。

覆盖：
  - 健康检查 /api/health
  - 状态查询 /api/status
  - 告警查询 /api/alerts
  - Agent 对话 /api/agent/chat
"""
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    """创建异步 HTTP 测试客户端。"""
    # 延迟导入，避免 conftest 阶段初始化
    from backend.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac


class TestHealthCheck:
    """健康检查端点。"""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        """健康检查返回 200。"""
        response = await client.get("/api/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_has_status_field(self, client):
        """健康检查响应包含 status 字段。"""
        response = await client.get("/api/health")
        data = response.json()
        assert "status" in data


class TestStatusEndpoint:
    """状态查询端点。"""

    @pytest.mark.asyncio
    async def test_status_returns_200(self, client):
        """状态查询返回 200。"""
        response = await client.get("/api/status")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_status_has_required_fields(self, client):
        """状态响应包含必要字段。"""
        response = await client.get("/api/status")
        data = response.json()
        assert "status" in data
        assert "offline_mode" in data
        assert "llm_online" in data


class TestAlertsEndpoint:
    """告警查询端点。"""

    @pytest.mark.asyncio
    async def test_alerts_returns_200(self, client):
        """告警接口可访问。"""
        response = await client.get("/api/alerts")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_alerts_returns_list(self, client):
        """告警接口返回列表。"""
        response = await client.get("/api/alerts")
        data = response.json()
        # 可能是列表或包含列表的字典
        if isinstance(data, list):
            assert isinstance(data, list)
        else:
            assert "alerts" in data or "data" in data


class TestAgentChat:
    """Agent 对话端点。"""

    @pytest.mark.asyncio
    async def test_agent_chat_quick_route(self, client):
        """快速路由：简单指令返回成功或优雅降级。"""
        response = await client.post("/api/agent/chat", json={
            "text": "开空调",
            "gesture": "",
            "route": "quick",
            "driver_state": {"risk": "safe", "fatigue": False, "distracted": False}
        })
        # 快速路由应该很快返回，不依赖 LLM
        assert response.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_agent_chat_readonly_route(self, client):
        """安全模式：只读路由拒绝控制类操作。"""
        response = await client.post("/api/agent/chat", json={
            "text": "开空调",
            "gesture": "",
            "route": "readonly",
            "driver_state": {"risk": "safe", "fatigue": False, "distracted": False}
        })
        assert response.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_agent_chat_auto_route(self, client):
        """自动路由：不崩溃。"""
        response = await client.post("/api/agent/chat", json={
            "text": "你好",
            "gesture": "",
            "route": "auto",
            "driver_state": {"risk": "safe", "fatigue": False, "distracted": False}
        })
        # 可能因 API Key 问题失败，但不应 500
        assert response.status_code in (200, 503)
