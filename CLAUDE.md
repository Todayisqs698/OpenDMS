# CLAUDE.md — EdgeGuard AI 会话上下文

## 项目
EdgeGuard — 边缘智能驾驶安全多模态交互系统。车载中控大屏 HMI + 多模态 AI Agent。

## 技术栈
- **后端**: Python 3.10+ / FastAPI 0.115+ / uvicorn 0.38+ (port 8000)
- **前端**: Vue 3.4+ / Vite 5.4+ / Tailwind CSS 4 / Element Plus 2.7+ (port 8005)
- **AI**: DeepSeek API (deepseek-v4-flash) via OpenAI SDK / LangGraph 0.6+ / FAISS
- **视觉**: OpenCV 4.11+ / MediaPipe 0.10.35 (Face 468pt + Hand 21pt)
- **语音**: Whisper (openai-whisper 20240930) / edge-tts 6.1+ / WebRTC VAD
- **数据库**: SQLite (data/edgeguard.db) — 3 表: drive_sessions, alerts, interactions
- **地图**: Leaflet 1.9.4 / OSRM (免费路线) / Nominatim (地理编码)

## 目录结构
```
backend/           # FastAPI — main.py (50+端点) + camera.py + ws/manager.py + core/database.py
modules/ai/        # Agent系统 — agent_core, agent_graph, orchestrator, 6个子Agent
modules/vision/    # 视觉 — face_tracker, hand_gesture, gesture_classifier
modules/audio/     # 语音 — speech_recognizer, audio_pipeline, recorder
frontend/src/      # Vue 3 — views/ + components/hmi/ (14组件) + composables/ + lib/
specs/             # 规范文档 — PRD, APP_FLOW, TECH_STACK, FRONTEND_GUIDELINES, BACKEND_STRUCTURE, IMPLEMENTATION_PLAN
app.py             # 独立摄像头AI引擎 (python app.py --dry-run)
```

## 文件命名约定
- Python: `snake_case` (agent_core.py, deepseek_client.py)
- Vue 组件: `PascalCase` (SafetyPanel.vue, AiPanel.vue)
- TypeScript 类型: `PascalCase` (Telemetry, AgentTraceStep)
- API 端点: `/api/模块/动作` (GET /api/ac/state, POST /api/agent/chat)
- 数据库表: `snake_case` 复数 (drive_sessions, alerts, interactions)

## 组件模式
- Vue SFC: `<script setup lang="ts">` → `<template>` → `<style scoped>`
- Composable: `useXxx` (useTelemetry, useAgentWS) — 管理响应式状态
- 全局单例: Python 模块级变量 (ws_manager, deepseek_client, _ac_state)
- 降级模式: 所有 AI 模块都有离线/异常降级路径 (langgraph未安装→手动循环, API超时→fallback, TTS→pyttsx3)
- API 调用: 类型集中在 `frontend/src/lib/edgeguard.ts` (ENDPOINTS + types + mocks)

## 设计令牌 (Tailwind CSS4 OKLCH)
- 字体: Geist Sans (正文) / Geist Mono (数据)
- 主色调: `oklch(0.5 0.15 230)` 蓝 (light) / `oklch(0.82 0.13 195)` 亮蓝 (dark)
- 安全: `oklch(0.55 0.17 165)` 绿 / 警告: `oklch(0.6 0.15 80)` 黄 / 危险: `oklch(0.55 0.2 25)` 红
- 圆角基准: `--radius: 1rem` (16px)
- 暗色主题默认 (.dark class)

## 允许的操作
- ✓ 新增 .vue 组件到 `frontend/src/components/hmi/`
- ✓ 新增 API 端点: `@app.get/post` 在 `backend/main.py`，同时更新 `frontend/src/lib/edgeguard.ts` 的 ENDPOINTS
- ✓ 新增 AI 模块到 `modules/ai/`
- ✓ 修改 prompt 模板: `modules/ai/prompts/*.py`，使用 `render(template_id, **vars)`
- ✓ 新增数据库表: `database.py` 的 `init_db()` + 对应的 CRUD 函数
- ✓ 新增手势: `hand_gesture.py` 的 labels + `edgeguard.ts` 的 gestureCommands

## 禁止的操作
- ✗ 不在 frontend 中直接硬编码 API URL（使用 ENDPOINTS 常量）
- ✗ 不在 components 中直接调用 fetch（通过 composables 封装）
- ✗ 不限流调用 LLM API（安全门控 + 离线降级必须保留）
- ✗ 不对 .env 文件做 git add（已加入 .gitignore）
- ✗ 不删除 modules/ 中的降级分支（每个 try/except fallback 都有存在理由）
- ✗ 不在生产环境使用 `allow_origins=["*"]`

## 关键命令
```bash
# 后端
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
# 前端
cd frontend && npm run dev
# 摄像头引擎
python app.py --dry-run    # 干跑
python app.py              # 正常模式
# 数据库初始化
python -c "from backend.app.core.database import init_db; init_db()"
```
