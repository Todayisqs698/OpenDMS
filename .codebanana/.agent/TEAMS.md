# TEAMS.md — EdgeGuard 团队分工

## 项目概况
- **项目名称:** EdgeGuard — 边缘智能驾驶安全多模态交互系统
- **背景:** 大模型应用开发实训，第5组
- **当前形态:** Python(感知/AI/后端) + Vue3(前端) 网页版
- **目标形态:** 迁移为 Android 移动端原生应用（HBuilder/uni-app）

## 成员与分工

* **Clouberri（组长 / 项目 Owner）:** 统筹协调。负责核心架构：LangGraph 编排器、边缘-云端路由器、面部追踪、FastAPI+WebSocket 后端、Vue3 大屏骨架、app.py 主流程串联。掌握 master 分支合并权。

* **yin102570（兰）:** 前端/移动端方向。负责 AI 助手项目的开发与推进，需将 Vue 网页版迁移到 HBuilder 安卓原生项目；负责答辩材料准备。下周一/二需向团队同步进度和下周计划。

* **qs song:** 团队成员（C 岗 / 环境导航方向，待补充细节）。

## 分工矩阵（按岗位）

| 岗位 | 负责人 | 模块 |
|------|--------|------|
| 组长 | Clouberri | 编排器+路由器+面部追踪+后端+大屏骨架+主流程 |
| A 岗（安全）| （待确认）| safety_agent / fatigue_predictor / AlertPanel / GaugePanel |
| B 岗（交互）| （待确认）| interaction_agent / RAG知识库 / AiDecisionPanel / VoiceInteractionBar |
| C 岗（环境）| qs song | environment_agent / NavPanel |
| 移动端迁移 | yin102570(兰) | Vue → HBuilder Android 迁移 / 答辩材料 |

## 关键备注
- 兰(yin102570) 当前权限为 view，是项目 presenter，非代码提交者
- 天气功能目前使用固定城市 `DEFAULT_CITY = "Beijing"`，需改为 GPS 自动定位
- 代码中无 deep agents / HBuilder / uni-app 相关实现，均为待开发
