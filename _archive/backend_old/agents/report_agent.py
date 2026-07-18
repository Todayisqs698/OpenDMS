"""
组长：周报生成 + 趋势分析
"""
from app.core.llm_factory import get_llm


def generate_weekly_report(start_date: str, end_date: str, stats: dict) -> str:
    """
    基于统计数据生成结构化周报，大屏"导出周报"按钮调用
    """
    llm = get_llm(temperature=0.4)

    prompt = f"""你是一位政务数据分析师，请根据以下 12345 热线数据生成一份专业的周报。

时间范围：{start_date} ~ {end_date}
统计数据：{stats}

请严格按照以下格式输出（Markdown）：

## 本周总体概况
- 工单总量与环比变化
- 办结率与市民满意度
- 平均处理时长

## TOP5 诉求类型
（按数量从高到低，含占比）

## 部门处理效能
（按办结率和处理速度排行，标注需要关注的部门）

## 趋势发现
- 相比上周有什么显著变化（上升/下降）
- 是否有新出现的高频问题

## 预警提示
- 哪些区域或类型有爆发趋势
- 哪些工单超时风险较高

## 下周重点关注
- 建议提前部署的巡查方向
- 需要协调的跨部门事项

要求：数据驱动、简洁专业、每条不超过两行。"""
    response = llm.invoke(prompt)
    return response.content
