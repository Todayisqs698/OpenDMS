# TECH_STACK — EdgeGuard 技术栈文档

> **版本**: 1.0.0 | **最后更新**: 2026-07-26

---

## 1. 技术选型总览

| 层级 | 选型 | 说明 |
|------|------|------|
| 运行时 | Python 3.10+ / Node.js 18+ | 后端 Python，前端 Node |
| 视觉感知 | OpenCV 4.8+ + MediaPipe 0.10.30+ | 面部 468 点 + 手势 21 关键点 |
| 语音 | Whisper (openai-whisper) + edge-tts + WebRTC VAD | 本地转写 + 云端 TTS 降级本地 |
| AI 编排 | LangGraph 0.2+ StateGraph | ReAct Agent 循环 |
| 大模型 | DeepSeek Chat API (deepseek-v4-flash) | 主 LLM，兼容 OpenAI/Anthropic |
| 向量检索 | FAISS 1.10+ + sentence-transformers 3.0+ | RAG 车辆知识库 |
| 后端框架 | FastAPI 0.110+ + uvicorn 0.29+ | 异步 REST + WebSocket |
| 前端框架 | Vue 3.4 + Vite 5.4 | 中控大屏 HMI |
| UI 库 | Element Plus 2.7 + Tailwind CSS 4 | 组件库 + 原子化样式 |
| 图表 | ECharts 5.5 | 驾驶统计可视化 |
| 地图 | Leaflet 1.9.4 | 开源地图展示 |
| 数据库 | SQLite (内置) | 告警/交互/会话持久化 |
| 导航 | OSRM + Nominatim (免费, 无需 Key) | 路线规划 + 地理编码 |

---

## 2. Python 依赖 (requirements.txt)

### 2.1 视觉与感知

| 包名 | 版本约束 | 锁定版本 | 用途 |
|------|---------|---------|------|
| `opencv-python` | `>=4.8.0` | `4.11.0.86` | 摄像头采集、图像处理、HUD 绘制 |
| `mediapipe` | `>=0.10.30` | `0.10.35` | Face Landmarker (468 点), Hand Landmarker (21 点) |
| `numpy` | `>=1.24.0` | `2.2.6` | 数值计算、特征点坐标变换 |

### 2.2 语音

| 包名 | 版本约束 | 锁定版本 | 用途 |
|------|---------|---------|------|
| `sounddevice` | `>=0.5.2` | `0.5.2` | 麦克风音频采集 |
| `webrtcvad` | `>=2.0.7` | `2.0.10` | 语音活动检测 (VAD) |
| `openai-whisper` | `>=20240930` | `20240930` | 语音转文字 (本地推理) |
| `noisereduce` | `>=3.0.0` | `3.0.3` | 音频降噪 |
| `edge-tts` | `>=6.1.0` | `6.1.17` | 微软神经网络 TTS (zh-CN-XiaoxiaoNeural) |

### 2.3 LLM & AI

| 包名 | 版本约束 | 锁定版本 | 用途 |
|------|---------|---------|------|
| `openai` | `>=1.30.0` | `1.109.1` | DeepSeek API 客户端 (兼容 OpenAI SDK) |
| `langchain` | `>=0.3.0` | `0.3.27` | LLM 链式调用、Prompt 模板 |
| `langgraph` | `>=0.2.0` | `0.6.11` | StateGraph ReAct Agent 循环 |

### 2.4 向量检索 & Embeddings

| 包名 | 版本约束 | 锁定版本 | 用途 |
|------|---------|---------|------|
| `faiss-cpu` | `>=1.10.0` | `1.10.0` | Facebook AI 向量相似度检索 |
| `sentence-transformers` | `>=3.0.0` | `3.4.1` | 文本向量化 (中文语义匹配) |

### 2.5 后端

| 包名 | 版本约束 | 锁定版本 | 用途 |
|------|---------|---------|------|
| `fastapi` | `>=0.110.0` | `0.115.12` | REST API + WebSocket 框架 |
| `uvicorn[standard]` | `>=0.29.0` | `0.38.0` | ASGI 服务器 (uvloop + httptools) |
| `websockets` | `>=12.0` | `12.0` | WebSocket 协议支持 |
| `httpx` | `>=0.28.0` | `0.28.1` | 异步 HTTP 客户端 (网易云 API 等) |

### 2.6 工具

| 包名 | 版本约束 | 锁定版本 | 用途 |
|------|---------|---------|------|
| `python-dotenv` | `>=1.0.0` | `1.1.1` | .env 环境变量加载 |
| `requests` | `>=2.31.0` | `2.32.3` | 同步 HTTP 请求 (摄像头推流等) |

---

## 3. 前端依赖 (frontend/package.json)

### 3.1 运行时依赖

| 包名 | 版本约束 | 锁定版本 | 用途 |
|------|---------|---------|------|
| `vue` | `^3.4.0` | `3.5.17` | 渐进式前端框架 |
| `vue-router` | `^4.3.0` | `4.5.1` | SPA 路由 |
| `element-plus` | `^2.7.0` | `2.11.4` | Vue 3 UI 组件库 (对话框、抽屉、按钮等) |
| `echarts` | `^5.5.0` | `5.6.0` | 数据可视化图表 |
| `leaflet` | `^1.9.4` | `1.9.4` | 开源地图库 |
| `tailwindcss` | `^4.3.3` | `4.3.3` | 原子化 CSS 框架 |
| `@tailwindcss/postcss` | `^4.3.3` | `4.3.3` | Tailwind PostCSS 插件 |
| `postcss` | `^8.5.22` | `8.5.22` | CSS 后处理器 |
| `@lucide/vue` | `^1.26.0` | `1.26.0` | Lucide 图标库 (Vue 3) |
| `clsx` | `^2.1.1` | `2.1.1` | 条件类名工具 |
| `tailwind-merge` | `^3.6.0` | `3.6.0` | Tailwind 类名合并 (避免冲突) |
| `tw-animate-css` | `^1.4.0` | `1.4.0` | Tailwind 动画扩展 |
| `@fontsource/geist-sans` | `^5.3.0` | `5.3.0` | Geist Sans 字体 |
| `@fontsource/geist-mono` | `^5.3.0` | `5.3.0` | Geist Mono 等宽字体 |

### 3.2 开发依赖

| 包名 | 版本约束 | 锁定版本 | 用途 |
|------|---------|---------|------|
| `vite` | `^5.4.0` | `5.4.19` | 前端构建工具 |
| `@vitejs/plugin-vue` | `^5.0.0` | `5.2.4` | Vite Vue 3 插件 |

---

## 4. 外部 API 与服务

### 4.1 LLM API

| API | Base URL | 模型 | 用途 | 必填 |
|-----|----------|------|------|------|
| DeepSeek Chat | `https://api.deepseek.com` | `deepseek-v4-flash` | 主 LLM — 对话/推理/报告生成 | ✅ |
| OpenAI (备用) | `https://api.openai.com` | 用户指定 | 备用 LLM 提供商 | ❌ |
| Anthropic (备用) | `https://api.anthropic.com` | 用户指定 | 备用 LLM 提供商 | ❌ |

### 4.2 地图与位置

| API | Base URL | 用途 | 必填 |
|-----|----------|------|------|
| Nominatim | `https://nominatim.openstreetmap.org` | 地理编码 (地址→坐标) | ❌ (免费) |
| OSRM | `https://router.project-osrm.org` | 路线规划 | ❌ (免费) |
| 高德地图 | `https://restapi.amap.com` | POI 检索 / 天气 / 逆地理编码 | ❌ |
| OpenWeatherMap | `https://api.openweathermap.org` | 天气数据 | ❌ |
| wttr.in | `https://wttr.in` | 天气数据 (免费降级) | ❌ (免费) |

### 4.3 本地服务

| 服务 | 地址 | 用途 | 必填 |
|------|------|------|------|
| 网易云音乐 API | `http://localhost:3000` | 音乐搜索/播放 | ❌ (降级演示) |
| HuggingFace 镜像 | `https://hf-mirror.com` | 模型下载加速 (国内) | ❌ |

---

## 5. 模型文件

| 模型 | 来源 | 大小 | 位置 | 自动下载 |
|------|------|------|------|---------|
| MediaPipe Face Landmarker | Google | ~5.5 MB | 自动缓存 | ✅ |
| MediaPipe Hand Landmarker | Google | ~16 MB | `modules/vision/hand_landmarker.task` | ❌ |
| Whisper (base) | OpenAI | ~142 MB | `~/.cache/whisper/` | ✅ |
| KeyPoint Classifier (TFLite) | 预训练 | ~100 KB | `modules/vision/gesture/models/avazahedi/` | ❌ |
| sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) | HuggingFace | ~420 MB | `~/.cache/huggingface/` | ✅ |
| FAISS Index | 本地构建 | ~10 KB | `data/knowledge/faiss_index/` | ❌ (手动构建) |

---

## 6. 数据库

| 数据库 | 版本 | 文件位置 | 用途 |
|--------|------|---------|------|
| SQLite | 3.x (Python 内置) | `data/edgeguard.db` | 主数据库 — 驾驶会话/告警/交互 |
| SQLite | 3.x (Python 内置) | `backend/data/user_memory.db` | 用户记忆 (Agent 偏好) |
| FAISS | 1.10+ | `data/knowledge/faiss_index/` | 车辆知识库向量索引 |

---

## 7. 环境变量 (.env)

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DEEPSEEK_API_KEY` | ✅ | — | DeepSeek API 密钥 |
| `LLM_PROVIDER` | ❌ | `deepseek` | LLM 提供商: deepseek / openai / anthropic |
| `OPENAI_API_KEY` | ❌ | — | OpenAI API 密钥 (备用) |
| `ANTHROPIC_API_KEY` | ❌ | — | Anthropic API 密钥 (备用) |
| `AMAP_API_KEY` | ❌ | — | 高德地图 API Key (POI/天气) |
| `OPENWEATHER_API_KEY` | ❌ | — | OpenWeatherMap API Key |
| `HF_ENDPOINT` | ❌ | `https://hf-mirror.com` | HuggingFace 镜像站 |
| `EMBEDDING_API_BASE` | ❌ | — | 远程 Embedding 服务地址 |
| `EMBEDDING_API_KEY` | ❌ | — | 远程 Embedding 服务密钥 |
| `EMBEDDING_MODEL` | ❌ | `text-embedding-3-small` | Embedding 模型名 |
| `CAMERA_ENABLED` | ❌ | `1` | 是否启用服务端摄像头引擎 |

---

## 8. 端口分配

| 服务 | 端口 | 协议 | 说明 |
|------|------|------|------|
| FastAPI 后端 | `8000` | HTTP + WS | REST API + WebSocket |
| Vite 前端开发 | `8005` | HTTP | 开发服务器 (代理 8000) |
| 网易云音乐 API | `3000` | HTTP | 可选本地代理 |
| 前端生产构建 | `8000` (通过 StaticFiles) | HTTP | 后端直接托管 dist |

---

## 9. 技术决策记录 (ADR)

### ADR-01: 为什么选 DeepSeek 而非 OpenAI?
- **成本**: DeepSeek 价格约为 OpenAI 的 1/10
- **中文能力**: DeepSeek 中文理解和生成质量优于 GPT-4o
- **API 兼容**: 使用 OpenAI SDK，切换成本为零
- **降级**: 离线时回退本地模板，不依赖任何云服务

### ADR-02: 为什么选 LangGraph 而非 AutoGen/CrewAI?
- **轻量**: 单一 StateGraph 文件即可定义 ReAct 循环
- **可控**: 显式节点+边，比 AutoGen 的对话式编排更可预测
- **降级**: LangGraph 未安装时自动切换手动 while 循环实现

### ADR-03: 为什么用手势几何规则 + TFLite 双引擎?
- **几何规则**: 零依赖，始终可用，延迟 < 1ms
- **TFLite**: 精度更高，作为辅助验证
- **互补**: 几何规则处理标准手势，TFLite 处理模糊手势

### ADR-04: 为什么选 SQLite 而非 PostgreSQL?
- **零配置**: Python 内置，无需安装数据库服务
- **单机部署**: 车载场景无需分布式
- **足够**: 告警/交互记录量级小 (< 10 万条/年)

### ADR-05: 为什么选 Element Plus + Tailwind CSS 组合?
- **Element Plus**: 提供开箱即用的车载 UI 组件 (对话框/抽屉/开关)
- **Tailwind CSS 4**: 原子化样式，暗色主题 OKLCH 颜色空间
- **职责分离**: Element Plus 负责交互组件，Tailwind 负责布局和主题
