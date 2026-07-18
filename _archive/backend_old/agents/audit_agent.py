"""
🅲 成员C：质量审核 + AI 回访 + 规则引擎

接口规范：
  质检:   input={"resolution": "...", "history_count": 0, "has_media": False, "hours_spent": 0}
          output={"review_result": "passed/failed", "review_comment": "...", "recurrence_risk": "low/medium/high", "issues": [...]}
  回访:   input={"phone": "...", "order_summary": "...", "resolution": "..."}
          output={"rating": 1-5, "feedback": "...", "auto_retry": false, "script": "..."}
"""
from app.core.llm_factory import get_llm_json_mode
from app.core.config import settings
import json
import logging

logger = logging.getLogger(__name__)

AUDIT_PROMPT = """你是12345热线质检员。请审核以下工单处理结果，输出JSON（不要输出其他内容）：

{
    "review_result": "passed或failed",
    "review_comment": "审核意见（50字以内）",
    "recurrence_risk": "low或medium或high",
    "issues": ["发现的问题1", "发现的问题2"]
}

审核维度：
1. 处理结果是否完整？（有实质内容，不是"已处理"三个字）
2. 是否解决了根因而非表面？
3. 是否有复发风险？（重复投诉地址要特别注意）
4. 是否超时？

工单信息："""

CALLBACK_PROMPT = """你是12345热线回访员。请根据以下工单信息生成回访结果，输出JSON（不要输出其他内容）：

{
    "rating": 4,
    "feedback": "回访反馈（50字以内）",
    "auto_retry": false,
    "script": "回访话术（模拟电话回访对话）"
}

评分标准：
- 5分：问题彻底解决，市民非常满意
- 4分：问题基本解决，市民满意
- 3分：部分解决，市民觉得还行
- 2分：未解决，市民不满意
- 1分：完全没解决，市民非常不满

工单信息："""


def _is_llm_available() -> bool:
    """检查 LLM 是否可用（API Key 已配置）"""
    provider = settings.LLM_PROVIDER
    if provider == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    elif provider == "openai":
        return bool(settings.OPENAI_API_KEY)
    else:
        return bool(settings.DEEPSEEK_API_KEY)


def audit(resolution: str, history_count: int = 0, has_media: bool = False, hours_spent: float = 0) -> dict:
    """
    AI 自动质检：
    - 形式审查（填写完整、有照片、未超时）
    - 内容审查（匹配度、根因分析、复发风险）
    - 正常情况下调用 LLM 做 AI 质检
    - LLM 不可用时返回规则兜底结果，绝不抛异常
    """
    issues: list[str] = []
    rule_failed = False

    # ── 规则引擎：形式审查 ──

    # 1. 处置结果为空或太短
    if not resolution or len(resolution.strip()) < 5:
        return {
            "review_result": "failed",
            "review_comment": "处置结果为空或过于简单，未通过形式审查",
            "recurrence_risk": "low",
            "issues": ["处置结果为空或内容过短（少于5个字）"],
        }

    # 2. 处置结果太敷衍
    perfunctory_phrases = ["已处理", "已解决", "处理了", "解决了", "已办结", "ok", "好了", "完成"]
    if resolution.strip() in perfunctory_phrases:
        rule_failed = True
        issues.append("处置结果过于敷衍，仅填写了「{}」".format(resolution.strip()))

    # 3. 没有现场材料
    if not has_media:
        issues.append("未上传现场照片或录音材料，建议补充")

    # 4. 历史投诉次数过高 → 复发风险提升
    recurrence_risk = "low"
    if history_count >= 3:
        recurrence_risk = "high"
        issues.append(f"该地址已有 {history_count} 次投诉记录，复发风险高")

    # 5. 处理超时
    if hours_spent > 48:
        issues.append(f"处理耗时 {hours_spent:.1f} 小时，超过48小时时限")

    # 如果规则已判定失败，直接返回
    if rule_failed:
        return {
            "review_result": "failed",
            "review_comment": "处置结果过于敷衍，未通过形式审查",
            "recurrence_risk": recurrence_risk,
            "issues": issues,
        }

    # ── AI 质检 ──
    if not _is_llm_available():
        logger.warning("LLM API Key 未配置，使用规则兜底结果")
        # 规则兜底：没有硬伤就算通过
        if not issues:
            return {
                "review_result": "passed",
                "review_comment": "自动审核完成（规则引擎）",
                "recurrence_risk": recurrence_risk,
                "issues": [],
            }
        else:
            return {
                "review_result": "failed",
                "review_comment": "存在以下问题：{}".format("；".join(issues)),
                "recurrence_risk": recurrence_risk,
                "issues": issues,
            }

    try:
        context = (
            f"处置结果：{resolution}\n"
            f"历史投诉次数：{history_count}\n"
            f"有现场照片/录音：{has_media}\n"
            f"处理耗时：{hours_spent:.1f}小时"
        )
        llm = get_llm_json_mode()
        response = llm.invoke(AUDIT_PROMPT + context)

        # 尝试解析 LLM 返回的 JSON
        content = response.content.strip()
        # 处理可能的 markdown 代码块包裹
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        result = json.loads(content)

        # 确保返回结构完整
        result.setdefault("review_result", "passed")
        result.setdefault("review_comment", "自动审核完成")
        result.setdefault("recurrence_risk", recurrence_risk)
        result.setdefault("issues", [])

        # 合并规则引擎发现的问题
        for issue in issues:
            if issue not in result["issues"]:
                result["issues"].append(issue)

        # 如果规则引擎判定风险更高，以规则为准
        risk_order = {"low": 0, "medium": 1, "high": 2}
        if risk_order.get(recurrence_risk, 0) > risk_order.get(result["recurrence_risk"], 0):
            result["recurrence_risk"] = recurrence_risk

        # 校验 review_result 字段值
        if result["review_result"] not in ("passed", "failed"):
            result["review_result"] = "passed"

        return result

    except json.JSONDecodeError as e:
        logger.warning(f"LLM 返回的 JSON 解析失败: {e}，使用规则兜底")
        # 兜底：根据规则引擎的判断返回
        return {
            "review_result": "failed" if issues else "passed",
            "review_comment": "AI 质检异常，使用规则引擎兜底判断",
            "recurrence_risk": recurrence_risk,
            "issues": issues,
        }

    except Exception as e:
        logger.error(f"AI 质检调用失败: {e}，使用规则兜底")
        return {
            "review_result": "failed" if issues else "passed",
            "review_comment": f"AI 质检服务异常（{str(e)[:50]}），使用规则引擎兜底",
            "recurrence_risk": recurrence_risk,
            "issues": issues,
        }


def callback(phone: str, order_summary: str, resolution: str) -> dict:
    """
    AI 自动回访：
    1. 生成回访话术（模拟电话回访）
    2. 评估满意度
    3. 不满意自动标记 auto_retry=True
    - 不真正发送短信或打电话，只做模拟回访
    - LLM 不可用时返回规则兜底结果，绝不抛异常
    """
    # ── 规则引擎：预判 ──

    # 处置结果太短 → 可能没真正解决
    resolution_short = not resolution or len(resolution.strip()) < 10

    # 生成模拟回访话术
    if resolution_short:
        base_rating = 2
        base_feedback = "市民反映问题未真正解决，处置结果过于简单"
        auto_retry = True
    else:
        base_rating = 4
        base_feedback = "市民对处理结果表示满意"
        auto_retry = False

    # ── AI 回访 ──
    if not _is_llm_available():
        logger.warning("LLM API Key 未配置，使用规则兜底回访结果")
        return {
            "rating": base_rating,
            "feedback": base_feedback,
            "auto_retry": auto_retry,
            "script": (
                f"【模拟回访话术】\n"
                f"回访员：您好，我是12345热线回访员。关于您之前反映的「{order_summary[:30]}」问题，"
                f"我们想了解一下处理情况。\n"
                f"市民：{'已经解决了，谢谢你们' if not resolution_short else '感觉没怎么处理啊，还是老样子'}\n"
                f"回访员：{'感谢您的反馈，祝您生活愉快！' if not resolution_short else '非常抱歉，我们会重新跟进处理。'}"
            ),
        }

    try:
        context = (
            f"市民电话：{phone}\n"
            f"诉求摘要：{order_summary}\n"
            f"处置结果：{resolution}"
        )
        llm = get_llm_json_mode()
        response = llm.invoke(CALLBACK_PROMPT + context)

        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        result = json.loads(content)

        # 确保返回结构完整
        result.setdefault("rating", base_rating)
        result.setdefault("feedback", base_feedback)
        result.setdefault("auto_retry", auto_retry)
        result.setdefault("script", "回访完成")

        # 校验字段
        if not isinstance(result["rating"], int) or not (1 <= result["rating"] <= 5):
            result["rating"] = base_rating
        if not isinstance(result["auto_retry"], bool):
            result["auto_retry"] = auto_retry

        # 如果规则引擎判定更差，以规则为准
        if resolution_short and result["rating"] > 2:
            result["rating"] = 2
            result["auto_retry"] = True

        return result

    except json.JSONDecodeError as e:
        logger.warning(f"LLM 回访 JSON 解析失败: {e}，使用规则兜底")
        return {
            "rating": base_rating,
            "feedback": base_feedback,
            "auto_retry": auto_retry,
            "script": "【模拟回访话术】\n回访员：您好，我是12345热线回访员，想了解一下您对问题处理的满意度。\n市民：还行吧，基本解决了。\n回访员：好的，感谢您的反馈！",
        }

    except Exception as e:
        logger.error(f"AI 回访调用失败: {e}，使用规则兜底")
        return {
            "rating": base_rating,
            "feedback": base_feedback,
            "auto_retry": auto_retry,
            "script": f"【模拟回访话术 - 服务异常】\n回访员：您好，关于您反映的问题，我们会持续跟进。",
        }
