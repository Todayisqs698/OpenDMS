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
        self._conn.commit()

    def set_pref(self, key: str, value: Any):
        c = self._conn.cursor()
        c.execute("INSERT OR REPLACE INTO user_preferences (key, value, updated_at) VALUES (?, ?, ?)",
                  (key, json.dumps(value, ensure_ascii=False), time.time()))
        self._conn.commit()
        self._cache[key] = value

    def get_pref(self, key: str, default: Any = None) -> Any:
        if key in self._cache:
            return self._cache[key]
        c = self._conn.cursor()
        c.execute("SELECT value FROM user_preferences WHERE key = ?", (key,))
        row = c.fetchone()
        if row:
            val = json.loads(row["value"])
            self._cache[key] = val
            return val
        return default

    def get_all_preferences(self) -> dict:
        c = self._conn.cursor()
        c.execute("SELECT key, value FROM user_preferences")
        return {row["key"]: json.loads(row["value"]) for row in c.fetchall()}

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
        if prefs:
            pref_lines = [f"  - {k}: {v}" for k, v in prefs.items()]
            parts.append("用户偏好:\n" + "\n".join(pref_lines))
        if stats:
            top_cmds = list(stats.items())[:5]
            stat_lines = [f"  - {cmd}: {s['ok']}次成功/{s['total']}次总计" for cmd, s in top_cmds]
            parts.append("常用指令:\n" + "\n".join(stat_lines))

        summaries = self.long_term.get_recent_summaries(1)
        if summaries:
            parts.append(f"上次对话摘要: {summaries[0]['summary']}")

        return "\n".join(parts) if parts else ""

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