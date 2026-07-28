"""异步旅行规划任务管理器 — 移植自 TripStar 的异步任务模式。

提供:
- POST /api/trip/async → 立即返回 task_id，不阻塞请求
- GET /api/trip/status/{task_id} → HTTP 轮询兼容
- WebSocket /api/trip/ws/{task_id} → 实时推送进度

任务状态持久化到 JSON 文件，服务重启后能恢复。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import traceback
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 配置 ─────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_TASKS_DATA_DIR = _PROJECT_ROOT / "data" / "trip_tasks"

_FINAL_TASK_STATUS = {"completed", "failed"}

# 内存任务存储
_tasks: dict[str, dict[str, Any]] = {}


# ── 任务状态管理 ──────────────────────────────────────────────────────

def _create_task_state(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "processing",
        "stage": "submitted",
        "progress": 0,
        "message": "任务已提交，等待执行...",
        "result": None,
        "error": None,
        "subscribers": [],  # list[asyncio.Queue]
    }


def _task_file_path(task_id: str) -> Path:
    return _TASKS_DATA_DIR / f"{task_id}.json"


def _persist_task_state(task_id: str, task: dict[str, Any]) -> None:
    try:
        _TASKS_DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "task_id": task_id,
            "status": task.get("status", "processing"),
            "stage": task.get("stage", ""),
            "progress": task.get("progress", 0),
            "message": task.get("message", ""),
            "result": _serialize_result(task.get("result")),
            "error": task.get("error"),
        }
        target = _task_file_path(task_id)
        tmp = target.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(target)
    except Exception as e:
        logger.warning("持久化任务 %s 失败: %s", task_id, e)


def _serialize_result(result: Any) -> Any:
    if result is None:
        return None
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if isinstance(result, dict) and "trip_plan" in result:
        # EdgeGuard plan_from_text 返回的 dict
        # 浅拷贝，避免修改原始数据（原代码在 tp 无 model_dump 时会原地修改）
        result = dict(result)
        tp = result.get("trip_plan")
        if hasattr(tp, "model_dump"):
            result["trip_plan"] = tp.model_dump(mode="json")
        ts = result.get("trip_schema")
        if hasattr(ts, "model_dump"):
            result["trip_schema"] = ts.model_dump(mode="json")
        # trip_schema 保留（已是 model_dump 结果或 None），不置空
    return result


def _load_task_from_disk(task_id: str) -> dict[str, Any] | None:
    path = _task_file_path(task_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return None
        task = _create_task_state(task_id)
        task.update({
            "status": payload.get("status", "failed"),
            "stage": payload.get("stage", "failed"),
            "progress": payload.get("progress", 100),
            "message": payload.get("message", ""),
            "result": payload.get("result"),
            "error": payload.get("error"),
        })
        # 服务重启后处理中的任务无法恢复
        if task["status"] not in _FINAL_TASK_STATUS:
            task["status"] = "failed"
            task["error"] = "服务已重启，未完成的任务无法恢复，请重新生成。"
            task["message"] = task["error"]
        _tasks[task_id] = task
        return task
    except Exception as e:
        logger.warning("读取任务 %s 失败: %s", task_id, e)
        return None


def get_task(task_id: str) -> dict[str, Any] | None:
    return _tasks.get(task_id) or _load_task_from_disk(task_id)


def _build_task_event(task_id: str, task: dict[str, Any]) -> dict[str, Any]:
    event = {
        "task_id": task_id,
        "status": task.get("status", "processing"),
        "stage": task.get("stage", ""),
        "progress": task.get("progress", 0),
        "message": task.get("message", ""),
    }
    if task.get("error"):
        event["error"] = task["error"]
    if task.get("result") is not None:
        event["result"] = _serialize_result(task["result"])
    return event


def _broadcast_task_event(task_id: str, event: dict[str, Any]) -> None:
    task = _tasks.get(task_id)
    if not task:
        return
    dead_queues = []
    for queue in task.get("subscribers", []):
        try:
            queue.put_nowait(event)
        except Exception:
            dead_queues.append(queue)
    if dead_queues:
        task["subscribers"] = [q for q in task.get("subscribers", []) if q not in dead_queues]


async def update_task_state(
    task_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    result: Any = None,
    error: str | None = None,
) -> None:
    task = _tasks.get(task_id)
    if not task:
        return
    if status is not None:
        task["status"] = status
    if stage is not None:
        task["stage"] = stage
    if progress is not None:
        task["progress"] = progress
    if message is not None:
        task["message"] = message
    if result is not None:
        task["result"] = result
    if error is not None:
        task["error"] = error
    _persist_task_state(task_id, task)
    event = _build_task_event(task_id, task)
    _broadcast_task_event(task_id, event)


# ── 后台任务执行 ──────────────────────────────────────────────────────

async def run_trip_planning_async(
    task_id: str,
    city: str,
    days: int,
    preference: str | None = None,
    origin: str = "",
    waypoints: list[str] | None = None,
    forbidden_cities: list[str] | None = None,
) -> None:
    """后台执行旅行规划并推送进度。

    使用 asyncio.to_thread 包装同步的 trip planner 调用，
    在关键阶段之间推送进度更新。
    """
    try:
        await update_task_state(
            task_id, status="processing", stage="searching",
            progress=10, message="正在搜索景点数据...",
        )

        from modules.ai.trip_planner.agent import EdgeGuardTripPlanner
        planner = EdgeGuardTripPlanner()

        # 搜索景点（包含 XHS 增强）
        await update_task_state(
            task_id, progress=20, message=f"正在搜索{city}景点和小红书游记...",
        )

        # 在线程中执行同步规划（不阻塞事件循环）
        await update_task_state(
            task_id, progress=30, message="正在收集天气和酒店信息...",
        )

        result = await asyncio.to_thread(
            planner.plan_from_text,
            query=f"{city}{days}日游",
            city=city,
            days=days,
            preference=preference,
            origin=origin,
            waypoints=waypoints,
            forbidden_cities=forbidden_cities,
        )

        await update_task_state(
            task_id, progress=80, message="AI 正在规划行程...",
        )

        if result.get("success"):
            await update_task_state(
                task_id, status="completed", stage="completed",
                progress=100, message="旅行计划生成成功",
                result=result,
            )
            logger.info("异步任务 %s 完成", task_id)
        else:
            await update_task_state(
                task_id, status="failed", stage="failed",
                progress=100, message="规划失败",
                error=result.get("reply", "未知错误"),
            )
    except Exception as e:
        logger.error("异步任务 %s 失败: %s\n%s", task_id, e, traceback.format_exc())
        await update_task_state(
            task_id, status="failed", stage="failed",
            progress=100, message=str(e), error=str(e),
        )


# ── 公共 API ──────────────────────────────────────────────────────────

def create_trip_task(
    city: str,
    days: int,
    preference: str | None = None,
    origin: str = "",
    waypoints: list[str] | None = None,
    forbidden_cities: list[str] | None = None,
) -> str:
    """创建异步旅行规划任务，返回 task_id。"""
    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = _create_task_state(task_id)
    _persist_task_state(task_id, _tasks[task_id])

    # 启动后台任务
    asyncio.create_task(
        run_trip_planning_async(
            task_id, city, days, preference, origin, waypoints, forbidden_cities,
        )
    )
    logger.info("创建异步旅行任务: task_id=%s city=%s days=%s", task_id, city, days)
    return task_id


def subscribe_to_task(task_id: str) -> asyncio.Queue | None:
    """订阅任务状态更新，返回一个 asyncio.Queue。"""
    task = get_task(task_id)
    if not task:
        return None
    queue: asyncio.Queue = asyncio.Queue()
    task["subscribers"].append(queue)
    return queue


def unsubscribe_from_task(task_id: str, queue: asyncio.Queue) -> None:
    """取消订阅任务状态更新。"""
    task = _tasks.get(task_id)
    if task:
        task["subscribers"] = [q for q in task.get("subscribers", []) if q is not queue]


def get_task_status(task_id: str) -> dict[str, Any] | None:
    """获取任务状态（供 HTTP 轮询）。"""
    task = get_task(task_id)
    if not task:
        return None
    return _build_task_event(task_id, task)
