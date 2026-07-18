"""
安全 Agent — 眼动 + 头部姿态分析，输出安全评级

接口规范：
  输入: {"gaze": {"state": "left/right/center", "duration": 3.5, ...},
         "head_pose": {"pitch": 10, "yaw": -15, "roll": 2},
         "eye_frames": [{"ear":0.22, "mar":0.6, "pitch":35, "yaw":5}, ...]
  输出: {"risk_level": "normal/attn_declining/distracted/dangerous",
         "alert_msg": "请注视前方道路",
         "metrics": {"perclos": 0.12, "blink_rate": 18, "fatigue_score": 42, "fatigue_level": "warning"}}

TODO: 成员A 实现 analyze() 函数
      1. 从眼动数据计算 PERCLOS、眨眼频率
      2. 调用 fatigue_predictor 做趋势判断
      3. 结合头部姿态输出风险等级
"""
import sys
import json
from pathlib import Path
# 将项目根目录加入Python搜索路径
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

# 原有导入
from modules.ai.fatigue_predictor import batch_predict

class SafetyAgent:
    """安全 Agent — 驾驶员状态监控"""

    def __init__(self):
        self.state = "normal"
        self.consecutive_warnings = 0
        self.blink_count = 0
        self.last_ear_low = False

    def _calc_perclos_blink(self, eye_frames: list[dict]) -> tuple[float, int]:
        """
        TODO1：从眼动帧计算 PERCLOS、眨眼频率
        PERCLOS：闭眼时长占总时长比例（0~1）
        blink_rate：单位窗口内眨眼次数
        """
        if not eye_frames:
            return 0.0, 0
        EAR_THRESHOLD = 0.26
        total = len(eye_frames)
        close_count = 0
        blink_times = 0
        for frame in eye_frames:
            ear = frame.get("ear", 0.5)
            if ear < EAR_THRESHOLD:
                close_count += 1
                if not self.last_ear_low:
                    blink_times += 1
                    self.last_ear_low = True
            else:
                self.last_ear_low = False
        perclos = close_count / total
        return round(perclos, 2), blink_times

    def analyze(self, data: dict) -> dict:
        """
        TODO: 成员A 完整实现
        分析眼动、头部、时序眼动帧，输出安全评级
        修复：分层判定逻辑，4档分级无跳级、无断层
        """
        # 每次分析重置单帧状态，避免历史残留干扰工况切换
        self.last_ear_low = False

        # 1. 提取输入数据
        gaze = data.get("gaze", {})
        gaze_state = gaze.get("state", "center")
        gaze_duration = gaze.get("duration", 0)
        head_pose = data.get("head_pose", {})
        pitch = abs(head_pose.get("pitch", 0))
        yaw = abs(head_pose.get("yaw", 0))
        eye_frames = data.get("eye_frames", [])

        # TODO1：计算PERCLOS、眨眼频率
        perclos, blink_rate = self._calc_perclos_blink(eye_frames)

        # TODO2：调用疲劳预测模块获取疲劳分数与等级
        fatigue_result = batch_predict(eye_frames)
        fatigue_score = fatigue_result["fatigue_score"]
        fatigue_level = fatigue_result["level"]

        # 组装基础指标
        metrics = {
            "perclos": perclos,
            "blink_rate": blink_rate,
            "fatigue_score": fatigue_score,
            "fatigue_level": fatigue_level
        }

        # TODO3：多维度分层判定风险等级（分层修复核心）
        risk_level = "normal"
        alert_text = ""

        # 分层判定条件拆分
        is_fatigue_danger = (fatigue_level == "danger")
        is_fatigue_tired = (fatigue_level == "warning")

        # 视线/头部偏转分层：轻度偏移 / 重度偏移
        gaze_off = (gaze_state != "center")
        slight_gaze = gaze_off and (1.5 < gaze_duration <= 3.0)
        heavy_gaze = gaze_off and (gaze_duration > 3.0)

        slight_head = (12 < pitch <= 22) or (8 < yaw <= 16)
        heavy_head = (pitch > 22) or (yaw > 28)

        # ========== 分级判定顺序：从高风险到低风险 ==========
        # 1. 重度危险 dangerous：重度疲劳 或 重度分心+轻度疲劳叠加
        if is_fatigue_danger or (heavy_gaze and is_fatigue_tired) or (heavy_head and is_fatigue_tired):
            risk_level = "dangerous"
            if is_fatigue_danger:
                alert_text = "重度疲劳，建议立即靠边停车休息"
            else:
                alert_text = "疲劳+分心双重风险，请专注驾驶并及时休息"
            self.consecutive_warnings += 1

        # 2. 中度分心 distracted：单纯重度视线/头部偏移，无轻度疲劳
        elif (heavy_gaze or heavy_head) and not is_fatigue_tired:
            risk_level = "distracted"
            alert_text = f"视线/头部偏离道路 {gaze_duration:.0f} 秒，请注视前方道路"
            self.consecutive_warnings += 1

        # 3. 注意力下降 attn_declining：轻度疲劳 或 小幅视线/头部偏移（无重度偏移）
        elif is_fatigue_tired or slight_gaze or slight_head:
            risk_level = "attn_declining"
            alert_text = "轻度疲劳/注意力偏移，注意力下降，建议短暂休整"
            self.consecutive_warnings += 1

        # 4. 正常状态 normal：无疲劳、无视线/头部偏移
        else:
            risk_level = "normal"
            alert_text = ""
            self.consecutive_warnings = 0

        # 修改1：将alert改为alert_msg，匹配main.py读取字段
        return {
            "risk_level": risk_level,
            "alert_msg": alert_text,
            "metrics": metrics
        }

    # 新增兼容main.py调用的方法 calculate_risk，解决方法名不匹配报错
    def calculate_risk(self, gaze_state, gaze_duration, perclos, fatigue_score):
        """
        兼容backend/main.py调用接口，适配前端模拟简易工况
        仅模拟基础入参，内部调用完整analyze逻辑
        """
        mock_input = {
            "gaze": {"state": gaze_state, "duration": gaze_duration},
            "head_pose": {"pitch": 0, "yaw": 0, "roll": 0},
            "eye_frames": [{"ear": 0.3}] * 10
        }
        result = self.analyze(mock_input)
        # 额外提取疲劳等级，匹配main.py输出结构
        return {
            "risk_level": result["risk_level"],
            "alert_msg": result["alert_msg"],
            "fatigue_level": result["metrics"]["fatigue_level"]
        }

# 本地自测入口
if __name__ == "__main__":
    agent = SafetyAgent()
    # 工况4：dangerous 重度危险自测
    test_dangerous = {
        "gaze": {"state": "left", "duration": 4.2},
        "head_pose": {"pitch": 30, "yaw": 8, "roll": 2},
        "eye_frames": [{"ear":0.22, "mar":0.62, "pitch":35, "yaw":5}] * 25
    }
    print("=== dangerous 重度危险工况 ===")
    print(json.dumps(agent.analyze(test_dangerous), ensure_ascii=False, indent=2))

    # 工况3：distracted 中度分心自测
    test_distracted = {
        "gaze": {"state": "left", "duration": 3.0},
        "head_pose": {"pitch": 21, "yaw": 14, "roll": 3},
        "eye_frames": [{"ear":0.26, "mar":0.54, "pitch":22, "yaw":12}] * 25
    }
    print("\n=== distracted 中度分心情况 ===")
    print(json.dumps(agent.analyze(test_distracted), ensure_ascii=False, indent=2))

    # 工况2：attn_declining 轻度注意力下降自测
    test_attn = {
        "gaze": {"state": "right", "duration": 2.2},
        "head_pose": {"pitch": 14, "yaw": 9, "roll": 2},
        "eye_frames": [{"ear":0.32, "mar":0.49, "pitch":12, "yaw":7}] * 25
    }
    print("\n=== attn_declining 轻度注意力下降 ===")
    print(json.dumps(agent.analyze(test_attn), ensure_ascii=False, indent=2))

    # 工况1：normal 正常驾驶自测
    test_normal = {
        "gaze": {"state": "center", "duration": 0.8},
        "head_pose": {"pitch": 5, "yaw": 1, "roll": 0},
        "eye_frames": [{"ear":0.38, "mar":0.45, "pitch":6, "yaw":0}] * 25
    }
    print("\n=== normal 正常驾驶 ===")
    print(json.dumps(agent.analyze(test_normal), ensure_ascii=False, indent=2))