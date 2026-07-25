import sqlite3
from pathlib import Path
from datetime import datetime

# 数据库文件路径：项目根目录 /data/edgeguard.db
DB_FILE = Path(__file__).parent.parent.parent.parent / "data" / "edgeguard.db"
# 确保data文件夹存在
DB_FILE.parent.mkdir(exist_ok=True)

# ── 全局当前会话 ID（由 main.py lifespan 设置，camera.py 读取）──
_current_session_id: int = 0


def set_current_session_id(sid: int):
    """设置当前驾驶会话 ID（供 main.py lifespan 调用）"""
    global _current_session_id
    _current_session_id = sid


def get_current_session_id() -> int:
    """获取当前驾驶会话 ID（供 camera.py / handler 读取）"""
    return _current_session_id


def get_db_connection():
    """获取SQLite数据库连接，启用行字典返回"""
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    初始化数据库，创建三张表：drive_sessions、alerts、interactions
    执行命令：python -c "from backend.app.core.database import init_db; init_db(); print('OK')"
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 驾驶会话表 drive_sessions
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS drive_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        start_time TEXT NOT NULL,
        end_time TEXT,
        avg_fatigue_score REAL,
        remark TEXT
    )
    ''')

    # 2. 告警记录表 alerts（安全Agent风险告警存入此处）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        risk_level TEXT NOT NULL,
        alert_msg TEXT,
        perclos REAL,
        blink_rate REAL,
        fatigue_score REAL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES drive_sessions(id)
    )
    ''')

    # 3. 语音交互记录表 interactions
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS interactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        user_query TEXT,
        ai_response TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES drive_sessions(id)
    )
    ''')

    conn.commit()
    conn.close()
    print("Database tables initialized: drive_sessions, alerts, interactions")


# ===================== 业务操作函数（供main.py调用） =====================
def create_drive_session() -> int:
    """新建一条驾驶会话，返回session_id"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO drive_sessions(start_time) VALUES (?)",
        (now,)
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def finish_drive_session(session_id: int, avg_fatigue_score: float = None):
    """结束驾驶会话，填充结束时间与平均疲劳分数"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        UPDATE drive_sessions
        SET end_time = ?, avg_fatigue_score = ?
        WHERE id = ?
    ''', (now, avg_fatigue_score, session_id))
    conn.commit()
    conn.close()


def insert_alert_record(
    session_id: int,
    risk_level: str,
    alert_msg: str,
    perclos: float,
    blink_rate: float,
    fatigue_score: float
):
    """
    写入告警记录
    【main.py 告警逻辑处调用此函数】
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO alerts
        (session_id, risk_level, alert_msg, perclos, blink_rate, fatigue_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, risk_level, alert_msg, perclos, blink_rate, fatigue_score, now))
    conn.commit()
    conn.close()


def insert_interaction_record(session_id: int, user_query: str, ai_response: str):
    """写入语音交互记录（供B岗语音模块调用）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO interactions
        (session_id, user_query, ai_response, created_at)
        VALUES (?, ?, ?, ?)
    ''', (session_id, user_query, ai_response, now))
    conn.commit()
    conn.close()


# ── 查询函数（供 API 端点使用）──

def query_alerts(session_id: int = 0, limit: int = 50):
    """获取指定会话的告警记录（0=当前会话）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    sid = session_id if session_id > 0 else get_current_session_id()
    cursor.execute(
        "SELECT * FROM alerts WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
        (sid, limit),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_session_summary(session_id: int = 0):
    """获取驾驶会话摘要（时长、告警数、平均疲劳分）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    sid = session_id if session_id > 0 else get_current_session_id()
    # 会话基本信息
    cursor.execute("SELECT * FROM drive_sessions WHERE id = ?", (sid,))
    session = cursor.fetchone()
    if not session:
        conn.close()
        return None
    # 告警统计
    cursor.execute(
        "SELECT risk_level, COUNT(*) as cnt, AVG(perclos) as avg_perclos, AVG(fatigue_score) as avg_fatigue FROM alerts WHERE session_id = ? GROUP BY risk_level",
        (sid,),
    )
    level_stats = [dict(r) for r in cursor.fetchall()]
    total_alerts = sum(r["cnt"] for r in level_stats)
    avg_fatigue = session["avg_fatigue_score"] or 0.0
    start_time = session["start_time"]
    end_time = session["end_time"]
    conn.close()
    return {
        "session_id": sid,
        "start_time": start_time,
        "end_time": end_time,
        "total_alerts": total_alerts,
        "avg_fatigue_score": round(avg_fatigue, 1),
        "level_breakdown": {r["risk_level"]: r["cnt"] for r in level_stats},
    }


def query_interactions(session_id: int = 0, limit: int = 100):
    """获取指定会话的交互记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    sid = session_id if session_id > 0 else get_current_session_id()
    cursor.execute(
        "SELECT * FROM interactions WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
        (sid, limit),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# 自测入口
if __name__ == "__main__":
    init_db()