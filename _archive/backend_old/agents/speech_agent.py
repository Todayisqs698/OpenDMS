"""
🅰 成员A：语音转写 + 情绪识别 + 意图分类 + 实体提取

接口规范：
  输入: {"text": "市民原始语音转写文本"}
  输出: {"category_l1": "城市管理", "category_l2": "噪音扰民", "keywords": [...], "entities": [...], "emotion_score": 0.0}

TODO: 实现 classify() 函数，用 LLM 完成意图分类 + 实体提取
"""
from app.core.llm_factory import get_llm_json_mode

CLASSIFY_PROMPT = """你是一个12345热线工单分类专家。请对以下市民诉求进行分类和信息提取，输出JSON：

{
    "category_l1": "城市管理/公共安全/环境保护/市场监管/民生服务/交通出行/其他",
    "category_l2": "二级分类（如：噪音扰民、电梯故障、垃圾堆积、消费纠纷）",
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "entities": [
        {"name": "实体名", "type": "地址/人物/机构/物品/事件"}
    ],
    "emotion_score": 0.0-100.0 (根据文本语气估计市民情绪强度),
    "summary": "一句话概括诉求"
}

市民诉求："""


def classify(text: str) -> dict:
    """
    TODO: 成员A 实现
    1. 调用 LLM 做意图分类
    2. 提取关键词和实体
    3. 评估情绪分数
    4. 返回结构化的分类结果
    """
    llm = get_llm_json_mode()
    response = llm.invoke(CLASSIFY_PROMPT + text)
    import json
    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        return {
            "category_l1": "其他",
            "category_l2": "未分类",
            "keywords": [],
            "entities": [],
            "emotion_score": 0.0,
            "summary": response.content[:200],
        }


# 如需语音转写，在此处接入 Whisper / 讯飞 API
def transcribe(audio_file_path: str) -> str:
    """
    TODO: 成员A 可选实现
    语音转文字（暂用 mock，后续接入 Whisper API）
    """
    # from openai import OpenAI
    # client = OpenAI(api_key=settings.SPEECH_API_KEY)
    # with open(audio_file_path, "rb") as f:
    #     return client.audio.transcriptions.create(model="whisper-1", file=f).text
    return "[语音转写结果]"
