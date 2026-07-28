"""
Memory System — 三层记忆管理
  - 短期记忆: 当前对话的消息列表（内存）
  - 工作记忆: 当前任务的上下文（如"正在导航到天津"）
  - 长期记忆: 用户偏好、高频指令统计（SQLite，跨会话持久化）
"""
import json
import logging
import os
import sqlite3
import time
import re
from typing import Any, Optional
from collections import deque

logger = logging.getLogger(__name__)


class WorkingMemory:
    """短期记忆 + 工作记忆"""

    def __init__(self, max_turns: int = 20):
        self.messages: deque = deque(maxlen=max_turns)  # {"role": "user"/"assistant"/"tool", "content": ..., "name": ...}
        self.current_task: str = ""      # 当前任务描述
        self.current_context: str = ""   # 当前任务上下文
        self.turn_count: int = 0
        # 最近一次行程规划的结构化参数，用于多轮对话中"重新规划"场景。
        # chat() 在 plan_trip 工具调用成功后写入；下一轮注入 system prompt。
        self.last_trip_params: dict = {}
        # 最近一轮各结构化工具的精简结果摘要，供后续轮次引用。
        # key = tool_name，value = 单行人类可读摘要（不含完整 JSON，避免 prompt 膨胀）。
        # 只保留最近一轮，避免历史堆积。
        self.last_tool_results: dict = {}

    def add_message(self, role: str, content: str, name: str = ""):
        """添加消息到短期记忆"""
        self.messages.append({
            "role": role,
            "content": content,
            "name": name,
            "timestamp": time.time(),
        })
        self.turn_count += 1

    def add_tool_result(self, tool_name: str, result: str):
        """添加工具调用结果"""
        self.messages.append({
            "role": "tool",
            "content": result,
            "name": tool_name,
            "timestamp": time.time(),
        })

    def set_last_trip_params(self, params: dict) -> None:
        """缓存最近一次 plan_trip 的结构化参数，供下一轮对话复用。

        只保留 LLM 在"重新规划"时需要的关键字段，避免存入巨大的行程
        JSON 导致 prompt 膨胀。budget 等细节由行程面板自行展示，无需
        进上下文。
        """
        if not isinstance(params, dict) or not params:
            return
        keep = ("city", "days", "preference", "origin", "waypoints",
                "forbidden_cities", "trip_type", "accommodation", "transportation")
        cleaned: dict = {}
        for k in keep:
            if k not in params:
                continue
            v = params[k]
            if v in (None, "", []):
                continue
            # preference/preferences may arrive as a list; collapse to a single
            # comma-joined string so downstream prompt rendering stays simple.
            if k == "preference" and isinstance(v, (list, tuple)):
                v = "、".join(str(x) for x in v if x)
                if not v:
                    continue
            cleaned[k] = v
        self.last_trip_params = cleaned

    def set_last_tool_result(self, tool_name: str, summary: str) -> None:
        """缓存最近一轮某工具的结构化结果摘要。

        summary 应为单行人类可读文本（如"找到3个景点：外滩、东方明珠、豫园"），
        而非完整 JSON —— 完整数据由专属面板展示，上下文只需让 LLM 知道
        "上轮推荐过哪些景点"即可。
        """
        if not tool_name or not summary:
            return
        self.last_tool_results[tool_name] = summary.strip()

    def get_tool_results_for_prompt(self) -> str:
        """渲染上轮工具结果摘要，供 LLM 在后续轮次引用。

        例如用户说"刚才推荐的那个景点在哪"时，LLM 能从上下文看到上次
        search_attractions 的结果，而不是失忆。
        """
        if not self.last_tool_results:
            return ""
        lines = []
        label_map = {
            "search_attractions": "上次推荐景点",
            "get_weather": "上次天气查询",
            "start_navigation": "上次导航",
            "plan_trip": "上次行程规划",
        }
        for tool, summary in self.last_tool_results.items():
            label = label_map.get(tool, f"上次{tool}")
            lines.append(f"- {label}：{summary}")
        return "上轮工具结果（用户引用时请基于此信息回答）：\n" + "\n".join(lines)

    def get_trip_context_for_prompt(self) -> str:
        """渲染上次行程参数为一段可直接注入 system prompt 的中文上下文。

        返回空字符串表示没有可复用的行程上下文（首轮或未触发过 plan_trip）。
        """
        p = self.last_trip_params
        if not p:
            return ""
        parts: list = []
        if p.get("origin") and p.get("city"):
            parts.append(f"上次行程：{p['origin']}→{p['city']}")
        elif p.get("city"):
            parts.append(f"上次行程：{p['city']}")
        if p.get("days"):
            parts.append(f"{p['days']}日游")
        if p.get("preference"):
            parts.append(f"偏好「{p['preference']}」")
        if p.get("waypoints"):
            parts.append(f"途经{'、'.join(p['waypoints'])}")
        if p.get("forbidden_cities"):
            parts.append(f"避开{'、'.join(p['forbidden_cities'])}")
        if not parts:
            return ""
        return "上次行程参数（用户要求调整时请在此基础上修改，不要从零重新询问）：" + "，".join(parts) + "。"

    def get_messages_for_llm(self) -> list:
        """获取供 LLM 使用的消息列表（去除元数据）"""
        return [{"role": m["role"], "content": m["content"], "name": m.get("name", "")}
                for m in self.messages if m["role"] in ("user", "assistant", "tool")]

    def get_recent_context(self, n: int = 3) -> str:
        """获取最近 N 轮的摘要"""
        recent = list(self.messages)[-n*2:]
        lines = []
        for m in recent:
            prefix = "用户" if m["role"] == "user" else "助手" if m["role"] == "assistant" else "工具"
            lines.append(f"{prefix}: {m['content'][:100]}")
        return "\n".join(lines)

    def set_task(self, task: str, context: str = ""):
        self.current_task = task
        self.current_context = context

    def clear(self):
        self.messages.clear()
        self.current_task = ""
        self.current_context = ""
        self.turn_count = 0
        self.last_trip_params = {}
        self.last_tool_results = {}


class LongTermMemory:
    """长期记忆 — SQLite 持久化"""

    def __init__(self, db_path: str = "data/user_memory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()
        self._cache: dict = {}  # 运行时缓存

    def _init_tables(self):
        c = self._conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                pref_type TEXT NOT NULL DEFAULT 'like',
                updated_at REAL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS command_history (
                command TEXT NOT NULL,
                success INTEGER NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS conversation_summary (
                session_id TEXT,
                summary TEXT,
                timestamp REAL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS saved_locations (
                label TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                lat REAL,
                lon REAL,
                updated_at REAL
            )
        """)
        self._conn.commit()
        self._migrate_preferences_schema()

    # ── 已保存地点（家/公司等语义地点）──

    def set_location(self, label: str, address: str, lat: float = None, lon: float = None):
        """保存或更新一个语义地点（如 home → "北京市朝阳区XX路XX号"）"""
        c = self._conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO saved_locations (label, address, lat, lon, updated_at) VALUES (?, ?, ?, ?, ?)",
            (label, address, lat, lon, time.time()),
        )
        self._conn.commit()
        logger.info("已保存地点: %s → %s", label, address)

    def get_location(self, label: str) -> Optional[dict]:
        """查询已保存的地点，返回 {label, address, lat, lon} 或 None"""
        c = self._conn.cursor()
        c.execute("SELECT label, address, lat, lon FROM saved_locations WHERE label = ?", (label,))
        row = c.fetchone()
        if row:
            return {"label": row["label"], "address": row["address"],
                    "lat": row["lat"], "lon": row["lon"]}
        return None

    def get_all_locations(self) -> list:
        """返回所有已保存的地点列表"""
        c = self._conn.cursor()
        c.execute("SELECT label, address, lat, lon FROM saved_locations ORDER BY updated_at DESC")
        return [{"label": row["label"], "address": row["address"],
                 "lat": row["lat"], "lon": row["lon"]} for row in c.fetchall()]

    def _migrate_preferences_schema(self):
        c = self._conn.cursor()
        try:
            c.execute("PRAGMA table_info(user_preferences)")
            cols = {row["name"] for row in c.fetchall()}
            if "pref_type" not in cols:
                c.execute("ALTER TABLE user_preferences ADD COLUMN pref_type TEXT NOT NULL DEFAULT 'like'")
            if "updated_at" not in cols:
                c.execute("ALTER TABLE user_preferences ADD COLUMN updated_at REAL")
            self._conn.commit()
        except Exception as e:
            logger.warning("user_preferences schema migration skipped: %s", e)

    def set_pref(self, key: str, value: Any, pref_type: str = "like"):
        c = self._conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO user_preferences (key, value, pref_type, updated_at) VALUES (?, ?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), pref_type or "like", time.time()),
        )
        self._conn.commit()
        self._cache[key] = {"value": value, "pref_type": pref_type or "like", "updated_at": time.time()}

    def set_like(self, key: str, value: Any):
        self.set_pref(key, value, pref_type="like")

    def set_dislike(self, key: str, value: Any):
        self.set_pref(key, value, pref_type="dislike")

    def get_pref(self, key: str, default: Any = None) -> Any:
        if key in self._cache:
            cached = self._cache[key]
            return cached["value"] if isinstance(cached, dict) and "value" in cached else cached
        c = self._conn.cursor()
        c.execute("SELECT value, pref_type, updated_at FROM user_preferences WHERE key = ?", (key,))
        row = c.fetchone()
        if row:
            val = json.loads(row["value"])
            self._cache[key] = {
                "value": val,
                "pref_type": row["pref_type"] or "like",
                "updated_at": row["updated_at"] or 0,
            }
            return val
        return default

    def get_pref_record(self, key: str, default: Any = None) -> dict:
        """Return the full preference record including pref_type and timestamp."""
        if key in self._cache and isinstance(self._cache[key], dict):
            return self._cache[key]
        c = self._conn.cursor()
        c.execute("SELECT value, pref_type, updated_at FROM user_preferences WHERE key = ?", (key,))
        row = c.fetchone()
        if row:
            record = {
                "value": json.loads(row["value"]),
                "pref_type": row["pref_type"] or "like",
                "updated_at": row["updated_at"] or 0,
            }
            self._cache[key] = record
            return record
        return {"value": default, "pref_type": "like", "updated_at": 0}

    def get_pref_with_decay(self, key: str, half_life_days: float = 30.0) -> tuple:
        """Return (value, weight) with exponential decay over time."""
        record = self.get_pref_record(key, default=None)
        value = record.get("value")
        updated_at = float(record.get("updated_at", 0) or 0)
        if not updated_at:
            return value, 0.5
        age_days = max(0.0, (time.time() - updated_at) / 86400.0)
        weight = 0.5 ** (age_days / half_life_days)
        return value, round(weight, 4)

    def get_all_preferences(self) -> dict:
        c = self._conn.cursor()
        c.execute("SELECT key, value, pref_type, updated_at FROM user_preferences")
        prefs = {}
        for row in c.fetchall():
            prefs[row["key"]] = {
                "value": json.loads(row["value"]),
                "pref_type": row["pref_type"] or "like",
                "updated_at": row["updated_at"] or 0,
            }
        return prefs

    def record_command(self, command: str, success: bool):
        c = self._conn.cursor()
        c.execute("INSERT INTO command_history (command, success, timestamp) VALUES (?, ?, ?)",
                  (command, 1 if success else 0, time.time()))
        self._conn.commit()

    def get_command_stats(self, command: str = "") -> dict:
        c = self._conn.cursor()
        if command:
            c.execute("SELECT COUNT(*) as total, SUM(success) as ok FROM command_history WHERE command = ?", (command,))
            row = c.fetchone()
            total = row["total"]
            ok = row["ok"] or 0
            return {"total": total, "success": ok, "fail": total - ok, "success_rate": ok / total if total > 0 else 0}
        else:
            c.execute("SELECT command, COUNT(*) as total, SUM(success) as ok FROM command_history GROUP BY command ORDER BY total DESC LIMIT 10")
            return {row["command"]: {"total": row["total"], "ok": row["ok"] or 0} for row in c.fetchall()}

    def save_conversation_summary(self, session_id: str, summary: str):
        c = self._conn.cursor()
        c.execute("INSERT INTO conversation_summary (session_id, summary, timestamp) VALUES (?, ?, ?)",
                  (session_id, summary, time.time()))
        self._conn.commit()

    def get_recent_summaries(self, n: int = 3) -> list:
        c = self._conn.cursor()
        c.execute("SELECT summary, timestamp FROM conversation_summary ORDER BY timestamp DESC LIMIT ?", (n,))
        return [{"summary": row["summary"], "time": row["timestamp"]} for row in c.fetchall()]

    def close(self):
        self._conn.close()


class AgentMemory:
    """三层记忆统一管理"""

    def __init__(self, db_path: str = "data/user_memory.db"):
        self.working = WorkingMemory()
        self.long_term = LongTermMemory(db_path)
        self.session_id = f"session_{int(time.time())}"

    def get_user_context_for_prompt(self) -> str:
        """生成用户上下文提示，注入到 LLM system prompt"""
        prefs = self.long_term.get_all_preferences()
        stats = self.long_term.get_command_stats()

        parts = []
        likes = []
        dislikes = []
        for key, record in prefs.items():
            value = record.get("value")
            pref_type = record.get("pref_type", "like")
            _, weight = self.long_term.get_pref_with_decay(key)
            if pref_type == "dislike":
                dislikes.append(f"  - {value}")
            else:
                likes.append(f"  - {key}: {value} (weight={weight:.2f})")

        if likes:
            parts.append("用户偏好:\n" + "\n".join(likes))
        if dislikes:
            parts.append("用户排斥:\n" + "\n".join(dislikes))
        if stats:
            top_cmds = list(stats.items())[:5]
            stat_lines = [f"  - {cmd}: {s['ok']}次成功/{s['total']}次总计" for cmd, s in top_cmds]
            parts.append("常用指令:\n" + "\n".join(stat_lines))

        summaries = self.long_term.get_recent_summaries(2)
        if summaries:
            # 最新的标"上次对话"，次新的标"更早对话"，避免 LLM 把多条
            # 摘要混为一谈。摘要本身已是结构化格式（见 _build_session_summary）。
            labels = ["上次对话摘要", "更早对话摘要"]
            for idx, s in enumerate(summaries):
                label = labels[idx] if idx < len(labels) else f"历史摘要{idx}"
                parts.append(f"{label}: {s['summary']}")

        return "\n".join(parts) if parts else ""

    def learn_preferences_from_text(self, text: str) -> list:
        """Extract simple likes/dislikes from user text and persist them."""
        if not text:
            return []

        compact = re.sub(r"\s+", "", text)
        updates = []

        def record(pref_type: str, value: str):
            value = value.strip(" 的了吧啊呀")
            if not value:
                return
            key = f"{pref_type}:{value}"
            if pref_type == "dislike":
                self.long_term.set_dislike(key, value)
            else:
                self.long_term.set_like(key, value)
            updates.append({"pref_type": pref_type, "value": value})

        dislike_patterns = [
            r"(?:以后|之后|不要再|不要|别再|别|不想|不喜欢|讨厌|拒绝)(?:推荐|提到|播放|听|展示)?(?P<value>[^，。！？、]{1,20})",
        ]
        like_patterns = [
            r"(?:我喜欢|喜欢|偏好|想要|常用)(?P<value>[^，。！？、]{1,20})",
        ]

        for pattern in dislike_patterns:
            m = re.search(pattern, compact)
            if m:
                record("dislike", m.group("value"))
                break

        for pattern in like_patterns:
            m = re.search(pattern, compact)
            if m:
                record("like", m.group("value"))
                break

        return updates

    def new_session(self):
        """开始新会话"""
        self.working.clear()
        self.session_id = f"session_{int(time.time())}"

    def end_session(self, summary: str = ""):
        """结束会话，持久化"""
        if summary:
            self.long_term.save_conversation_summary(self.session_id, summary)

    def close(self):
        self.long_term.close()
