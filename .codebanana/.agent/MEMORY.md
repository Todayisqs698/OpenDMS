# MEMORY.md — EdgeGuard 项目记忆

## 关键架构决策
- **疲劳预测接口**: `fatigue_predictor.py` 提供 `batch_predict(eye_frames)` 无状态函数 + `FatiguePredictor` 有状态类。safety_agent 调用 `batch_predict`，期望返回 `{"fatigue_score", "level"}`
- **天气 GPS 定位**: `environment_agent.analyze()` 现在支持三种输入: `{"city": "x"}`, `{"lat": x, "lon": y}`, `{}`(默认城市)。内部有 `_reverse_geocode(lat, lon)` 反查城市名
- **语音实时转写**: `app.py` 新增 `_speech_thread` 后台线程，从 `Recorder.record_stream()` 获取 WAV bytes → `speech_recognizer.transcribe()` → 存 `self._speech_text`，主循环读取后清空

## 文件路径
- 疲劳预测: `modules/ai/fatigue_predictor.py`
- 安全 Agent: `modules/ai/agents/safety_agent.py`
- 环境 Agent: `modules/ai/agents/environment_agent.py`
- 仪表盘组件: `frontend/src/components/GaugePanel.vue`
- 告警组件: `frontend/src/components/AlertPanel.vue`
- 主应用: `app.py`
- 移动端工程: `mobile/` (uni-app Vue3)
- 迁移方案: `docs/迁移方案.md`
- 开发规划: `docs/开发规划.md`

## 已知问题
- DeepSeek API Key 过期 (401 Unauthorized) — RAG 向量化失败，不影响本地决策链路
- safety_agent 的 distracted 工况测试用例 EAR 值 (0.26) 恰好不小于阈值 0.26，PERCLOS=0，导致分级结果不符合预期 — 属于 A 岗测试用例设计问题
- 兰(yin102570) 权限为 view，无法直接提交代码

## 后续待办
- A 岗: 修正 safety_agent 测试用例 EAR 值
- 配置 AMAP_KEY (高德 API) 用于 GPS 反查城市
- 兰: 用 HBuilderX 打开 mobile/ 目录，编译 APK 验证
- 兰: 在 settings 页配置后端 IP 地址
