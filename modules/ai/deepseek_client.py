#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek API客户端模块

集成DeepSeek API进行多模态数据融合和智能决策
"""

import json
import os
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from openai import OpenAI

# 加载 .env 文件
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'))


@dataclass
class MultimodalInput:
    """多模态输入数据"""
    gaze_data: Dict[str, Any]
    gesture_data: Dict[str, Any]
    speech_data: Dict[str, Any]
    timestamp: float
    duration: float  # 数据收集持续时间
    context: Dict[str, Any] = None  # 上下文信息，如分心恢复等


@dataclass
class AIResponse:
    """AI响应结果"""
    action_code: str
    recommendation_text: str
    confidence: float
    reasoning: str
    timestamp: float


class DeepSeekClient:
    """DeepSeek API客户端"""

    def __init__(self, api_key: str = None):
        if api_key is None:
            api_key = os.getenv('DEEPSEEK_API_KEY', '')
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        self.conversation_history = []

    def create_multimodal_prompt(self, multimodal_input: MultimodalInput) -> str:
        """创建多模态融合的提示词。优先从 Prompt 模板库获取，失败用内嵌兜底。"""

        # 构建上下文信息部分
        context_section = ""
        if multimodal_input.context:
            context_type = multimodal_input.context.get('type', '')
            if context_type == "attention_restored":
                context_section = f"""## 特殊上下文
- 类型: 注意力恢复
- 确认方式: {multimodal_input.context.get('confirmed_by', '未知')}
- 说明: 驾驶员之前处于分心状态，现已通过{multimodal_input.context.get('confirmed_by', '未知')}确认恢复注意力"""
            elif context_type == "distraction_detected":
                context_section = """## 特殊上下文
- 类型: 分心检测
- 说明: 系统检测到驾驶员视线长时间偏离道路，可能存在分心驾驶风险"""

        # 尝试从模板库渲染
        try:
            from modules.ai.prompts import render
            return render(
                "agent.multimodal_analysis",
                context_section=context_section,
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(multimodal_input.timestamp)),
                duration=f"{multimodal_input.duration:.1f}",
                gaze_state=multimodal_input.gaze_data.get('state', '未知'),
                gaze_duration=f"{multimodal_input.gaze_data.get('duration', 0):.1f}",
                gaze_deviation=multimodal_input.gaze_data.get('deviation', '正常'),
                gesture_type=multimodal_input.gesture_data.get('gesture', '无'),
                gesture_confidence=f"{multimodal_input.gesture_data.get('confidence', 0):.2f}",
                gesture_intent=multimodal_input.gesture_data.get('intent', '未知'),
                speech_text=multimodal_input.speech_data.get('text', '无语音输入'),
                speech_intent=multimodal_input.speech_data.get('intent', '未分类'),
                speech_emotion=multimodal_input.speech_data.get('emotion', '中性'),
            )
        except Exception:
            pass

        # 内嵌兜底（模板库不可用时使用）
        return f"""
你是一个车载智能助手，需要分析多模态输入数据并提供驾驶建议和操作指令。
{context_section}
## 输入数据分析
**时间戳**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(multimodal_input.timestamp))}
**数据收集时长**: {multimodal_input.duration:.1f}秒

### 1. 眼动数据
- 视线状态: {multimodal_input.gaze_data.get('state', '未知')}
- 持续时间: {multimodal_input.gaze_data.get('duration', 0):.1f}秒
- 偏离程度: {multimodal_input.gaze_data.get('deviation', '正常')}

### 2. 手势数据
- 检测到的手势: {multimodal_input.gesture_data.get('gesture', '无')}
- 手势置信度: {multimodal_input.gesture_data.get('confidence', 0):.2f}
- 手势意图: {multimodal_input.gesture_data.get('intent', '未知')}

### 3. 语音数据
- 识别文本: "{multimodal_input.speech_data.get('text', '无语音输入')}"
- 语音意图: {multimodal_input.speech_data.get('intent', '未分类')}
- 情感倾向: {multimodal_input.speech_data.get('emotion', '中性')}

## 任务要求
请基于以上多模态数据，进行综合分析并提供：

1. **驱动指令代码** (action_code): 
   - 格式: JSON字符串
   - 包含具体的系统操作指令

2. **操作推荐文本** (recommendation_text):
   - 自然语言描述
   - 适合语音播报
   - 简洁明了，易于理解

3. **置信度评分** (confidence):
   - 0.0-1.0之间的数值
   - 表示决策的可靠程度

4. **推理过程** (reasoning):
   - 简要说明决策依据
   - 解释多模态数据如何影响决策

## 响应格式
请严格按照以下JSON格式回复：

```json
{{
    "action_code": "具体的操作指令JSON字符串",
    "recommendation_text": "推荐操作的自然语言描述",
    "confidence": 0.85,
    "reasoning": "基于多模态数据的决策推理过程"
}}
```

我给你规定一个action_code库，如果识别结果比较符合，请务必从该库中取指令返回，如果没有对应的，你再自行定义action_code：
打开空调相关的："TurnOnAC"
关闭空调相关的："TurnOffAC"
播放音乐相关的："PlayMusic"
关闭音乐相关的："StopMusic"
司机分心了相关的："distract"
司机已经注意道路了相关的："NoticeRoad"

## 安全优先原则
- 驾驶安全始终是第一优先级
- 如果检测到分心驾驶，优先提醒注意道路
- 如果驾驶员刚从分心状态恢复，给予正面鼓励
- 避免在驾驶过程中执行复杂操作
- 语音交互优于视觉交互

请开始分析并给出建议：
"""


    def analyze_multimodal_data(self, multimodal_input: MultimodalInput) -> AIResponse:
        """分析多模态数据并获取AI建议"""

        try:
            # 创建提示词
            prompt = self.create_multimodal_prompt(multimodal_input)

            # 调用DeepSeek API
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的车载智能助手，擅长分析多模态数据并提供安全、实用的驾驶建议。请始终以JSON格式回复。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=1000,
                stream=False
            )

            # 解析响应
            content = response.choices[0].message.content

            # 尝试提取JSON部分
            try:
                # 查找JSON代码块
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    json_content = content[json_start:json_end].strip()
                else:
                    # 尝试直接解析整个内容
                    json_content = content.strip()

                # 解析JSON
                result = json.loads(json_content)

                return AIResponse(
                    action_code=result.get("action_code", "{}"),
                    recommendation_text=result.get("recommendation_text", "系统正在处理您的请求"),
                    confidence=float(result.get("confidence", 0.5)),
                    reasoning=result.get("reasoning", "基于多模态数据分析"),
                    timestamp=time.time()
                )

            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")
                print(f"原始响应: {content}")

                # 返回默认响应
                return AIResponse(
                    action_code='{"action": "error", "message": "解析失败"}',
                    recommendation_text="抱歉，系统暂时无法处理您的请求，请稍后再试",
                    confidence=0.1,
                    reasoning="API响应解析失败",
                    timestamp=time.time()
                )

        except Exception as e:
            print(f"DeepSeek API调用错误: {e}")

            # 返回错误响应
            return AIResponse(
                action_code='{"action": "error", "message": "API调用失败"}',
                recommendation_text="系统连接异常，请检查网络连接",
                confidence=0.0,
                reasoning=f"API调用异常: {str(e)}",
                timestamp=time.time()
            )

    def get_contextual_response(self, multimodal_input: MultimodalInput,
                                context: str = "") -> AIResponse:
        """获取带上下文的响应"""

        # 添加上下文信息到提示词
        enhanced_prompt = f"""
## 上下文信息
{context}

## 当前多模态输入
{self.create_multimodal_prompt(multimodal_input)}
"""

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个车载智能助手，能够理解上下文并提供连贯的交互体验。"
                    },
                    {
                        "role": "user",
                        "content": enhanced_prompt
                    }
                ],
                temperature=0.7,
                max_tokens=1000
            )

            content = response.choices[0].message.content

            # 解析响应（同上面的逻辑）
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_content = content[json_start:json_end].strip()
            else:
                json_content = content.strip()

            result = json.loads(json_content)

            return AIResponse(
                action_code=result.get("action_code", "{}"),
                recommendation_text=result.get("recommendation_text", "系统正在处理您的请求"),
                confidence=float(result.get("confidence", 0.5)),
                reasoning=result.get("reasoning", "基于上下文和多模态数据分析"),
                timestamp=time.time()
            )

        except Exception as e:
            print(f"上下文响应生成错误: {e}")
            return self.analyze_multimodal_data(multimodal_input)

    def add_to_conversation_history(self, multimodal_input: MultimodalInput,
                                    ai_response: AIResponse):
        """添加到对话历史"""
        self.conversation_history.append({
            "timestamp": multimodal_input.timestamp,
            "input": {
                "gaze": multimodal_input.gaze_data,
                "gesture": multimodal_input.gesture_data,
                "speech": multimodal_input.speech_data
            },
            "output": {
                "action_code": ai_response.action_code,
                "recommendation": ai_response.recommendation_text,
                "confidence": ai_response.confidence
            }
        })

        # 保持历史记录大小
        if len(self.conversation_history) > 10:
            self.conversation_history.pop(0)

    def get_conversation_context(self) -> str:
        """获取对话上下文"""
        if not self.conversation_history:
            return "这是新的对话开始。"

        recent_interactions = self.conversation_history[-3:]  # 最近3次交互
        context_parts = []

        for i, interaction in enumerate(recent_interactions, 1):
            context_parts.append(f"""
交互 {i} (时间: {time.strftime('%H:%M:%S', time.localtime(interaction['timestamp']))}):
- 用户输入: {interaction['input']['speech'].get('text', '无语音')}
- 系统建议: {interaction['output']['recommendation']}
- 执行操作: {interaction['output']['action_code']}
""")

        return "最近的交互历史:\n" + "\n".join(context_parts)

    def chat_with_tools(self, messages: list, tools: list = None,
                        tool_choice: str = "auto", temperature: float = 0.7,
                        max_tokens: int = 2000) -> dict:
        """
        支持 function calling 的对话接口。
        DeepSeek API 完全兼容 OpenAI 的 tools 格式。

        Args:
            messages: [{"role": "system/user/assistant/tool", "content": ..., "name": ..., "tool_calls": [...]}]
            tools: OpenAI function calling 格式的工具列表
            tool_choice: "auto" / "none" / "required" / {"type": "function", "function": {"name": "..."}}
            temperature: 生成温度
            max_tokens: 最大 token 数

        Returns:
            {
                "content": str or None,        # 文本回复
                "tool_calls": list or None,    # 工具调用请求 [{"id": ..., "type": "function", "function": {"name": ..., "arguments": "{...}"}}]
                "raw_message": Message,        # 原始返回
            }
        """
        kwargs = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        result = {
            "content": msg.content,
            "tool_calls": None,
            "raw_message": msg,
        }
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in msg.tool_calls
            ]

        return result


# 全局DeepSeek客户端实例
deepseek_client = DeepSeekClient()
