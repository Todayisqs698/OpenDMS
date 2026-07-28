"""Runtime settings API routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from modules.ai.runtime_config import (
    get_runtime_settings_masked,
    update_runtime_settings,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    """Runtime configuration update payload."""
    DEEPSEEK_API_KEY: Optional[str] = None
    AMAP_API_KEY: Optional[str] = None
    OPENWEATHER_API_KEY: Optional[str] = None
    XHS_COOKIE: Optional[str] = None
    LLM_PROVIDER: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    HF_ENDPOINT: Optional[str] = None


@router.get("")
def get_settings():
    return {
        "success": True,
        "settings": get_runtime_settings_masked(),
    }


@router.post("")
def update_settings(req: SettingsUpdate):
    updates = {}
    for key, value in req.model_dump().items():
        if value is None:
            continue
        if value == "***已配置***":
            continue
        updates[key] = value

    if not updates:
        return {"success": True, "message": "无更新", "settings": get_runtime_settings_masked()}

    update_runtime_settings(updates)
    return {
        "success": True,
        "message": "配置已更新并立即生效",
        "settings": get_runtime_settings_masked(),
    }
