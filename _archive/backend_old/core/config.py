"""
EdgeGuard 配置
"""
import os
from pathlib import Path


class Settings:
    # LLM
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "deepseek")

    # 路径
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"


settings = Settings()
