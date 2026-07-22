"""
驾驶分析 Agent — 驾驶行为数据分析与洞察生成
================================================

接收驾驶数据（时长、分心次数、注意力评分等），
生成结构化的驾驶分析报告和改进建议。

接口规范：
  输入: {"duration_min": 60, "distractions": 3, "severe_distractions": 1,
         "attention_score": 85, "avg_gaze": "center", "fatigue_level": "normal"}
  输出: {
    "success": true,
    "summary": "本次驾驶表现良好，注意力集中...",
    "score": 85,
    "grade": "B",
    "highlights": ["注意力评分85分", "严重分心仅1次"],
    "improvements": ["建议减少左侧视线偏离时长"],
    "safety_tips": ["长途驾驶每2小时休息一次"]
  }
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class AnalyzeAgent:
    """驾驶分析智能体"""

    def __init__(self):
        self._llm_client = None

    @property
    def llm(self):
        if self._llm_client is None:
            from modules.ai.deepseek_client import deepseek_client
            self._llm_client = deepseek_client
        return self._llm_client

    def analyze(self, data: dict) -> dict:
        """
        执行驾驶行为分析。

        Args:
            data: 驾驶数据 dict

        Returns:
            分析报告 dict
        """
        duration = data.get("duration_min", 0)
        distractions = data.get("distractions", 0)
        severe = data.get("severe_distractions", 0)
        attention = data.get("attention_score", 100)
        avg_gaze = data.get("avg_gaze", "center")
        fatigue = data.get("fatigue_level", "normal")

        # Step 1: 评分计算
        score = self._calculate_score(duration, distractions, severe, attention, fatigue)
        grade = self._score_to_grade(score)

        # Step 2: 亮点和改进点
        highlights = self._find_highlights(duration, distractions, severe, attention, fatigue)
        improvements = self._find_improvements(duration, distractions, severe, attention, avg_gaze, fatigue, score)

        # Step 3: LLM 生成总结
        try:
            summary = self._generate_summary(duration, distractions, severe,
                                             attention, avg_gaze, fatigue, score, grade)
        except Exception as e:
            logger.warning(f"分析总结生成失败: {e}，使用模板总结")
            summary = f"本次驾驶时长 {duration:.0f} 分钟，综合评分 {score} 分（{grade}级）。"

        # Step 4: 安全贴士
        tips = self._generate_safety_tips(duration, fatigue, score)

        return {
            "success": True,
            "summary": summary,
            "score": score,
            "grade": grade,
            "highlights": highlights,
            "improvements": improvements,
            "safety_tips": tips,
        }

    def _calculate_score(self, duration, distractions, severe, attention, fatigue) -> int:
        """计算综合驾驶评分（0-100）。"""
        score = 100

        # 分心扣分
        score -= distractions * 3
        score -= severe * 8

        # 注意力加分/减分
        if attention >= 90:
            score += 5
        elif attention < 70:
            score -= 10

        # 疲劳扣分
        if fatigue == "warning":
            score -= 10
        elif fatigue == "dangerous":
            score -= 20

        # 时长调整（短行程参考意义小）
        if duration < 5:
            score = min(score, 95)  # 太短不给满分

        return max(0, min(100, int(score)))

    def _score_to_grade(self, score: int) -> str:
        """分数转等级。"""
        if score >= 90:
            return "S"
        elif score >= 80:
            return "A"
        elif score >= 70:
            return "B"
        elif score >= 60:
            return "C"
        else:
            return "D"

    def _find_highlights(self, duration, distractions, severe, attention, fatigue) -> List[str]:
        """找出驾驶亮点。"""
        highlights = []

        if attention >= 90:
            highlights.append(f"注意力评分 {attention} 分，表现优秀")
        if severe == 0 and duration >= 10:
            highlights.append("全程无严重分心")
        if distractions <= 1 and duration >= 10:
            highlights.append("分心次数极少，驾驶专注")
        if fatigue == "normal" and duration >= 20:
            highlights.append("长时间驾驶状态良好")
        if not highlights:
            highlights.append("驾驶数据正常")

        return highlights[:3]

    def _find_improvements(self, duration, distractions, severe, attention, avg_gaze, fatigue, score) -> List[str]:
        """找出改进方向。"""
        improvements = []

        if severe > 0:
            improvements.append("减少严重分心，驾驶时请集中注意力")
        if distractions > 3:
            improvements.append(f"分心 {distractions} 次偏多，建议减少视线偏离")
        if attention < 80:
            improvements.append(f"注意力评分 {attention} 分偏低，建议保持专注")
        if fatigue != "normal":
            improvements.append("出现疲劳迹象，建议适时休息")
        if avg_gaze != "center" and distractions > 2:
            improvements.append(f"视线常偏向 {avg_gaze}，注意前方道路")

        if not improvements and score < 95:
            improvements.append("保持良好驾驶习惯，继续加油")

        return improvements[:3]

    def _generate_summary(self, duration, distractions, severe, attention,
                          avg_gaze, fatigue, score, grade) -> str:
        """用 LLM 生成自然语言总结。"""
        prompt = f"""你是驾驶行为分析师。根据以下数据生成一句简洁的驾驶总结（50字内）：

驾驶时长: {duration:.0f}分钟
分心次数: {distractions}次（严重{severe}次）
注意力评分: {attention}分
综合评分: {score}分（{grade}级）
疲劳状态: {fatigue}
主要视线: {avg_gaze}

语气亲切，像朋友一样。"""

        response = self.llm.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是专业的驾驶行为分析师，回答简洁亲切。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=100,
            temperature=0.7,
        )

        return response.choices[0].message.content.strip()

    def _generate_safety_tips(self, duration, fatigue, score) -> List[str]:
        """生成安全贴士。"""
        tips = []

        if duration >= 60:
            tips.append("长途驾驶每2小时建议休息15分钟")
        if fatigue != "normal":
            tips.append("感到疲劳时请尽快找安全地点休息")
        if score < 80:
            tips.append("建议减少驾驶时的其他操作，集中注意力")
        if not tips:
            tips.append("保持良好的驾驶习惯，安全第一")

        return tips[:3]
