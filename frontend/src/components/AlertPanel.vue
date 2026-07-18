<template>
  <section class="panel alert-panel" :class="alertClass">
    <h2>安全告警</h2>

    <!-- 三级告警显示 -->
    <transition name="alert-fade" mode="out-in">
      <div v-if="shouldAlert" :key="alertKey" class="alert-content" :class="severityClass">
        <div class="alert-icon">{{ severityIcon }}</div>
        <div class="alert-text">{{ alertText }}</div>
        <div class="alert-pulse" v-if="severity === 'severe'"></div>
      </div>
      <div v-else-if="decision && decision.action_code !== 'normal'" :key="'ok'" class="alert-ok">
        <span class="ok-icon">✓</span>
        <span>{{ decision.recommendation_text || '状态正常' }}</span>
      </div>
      <div v-else-if="decision" :key="'normal'" class="alert-normal">
        <span class="ok-icon">✓</span>
        <span>驾驶状态正常</span>
      </div>
      <p v-else :key="'wait'" class="placeholder">等待数据...</p>
    </transition>

    <!-- 告警历史（最近3条） -->
    <div class="alert-history" v-if="alertHistory.length > 0">
      <div class="history-title">最近告警</div>
      <div v-for="(h, i) in alertHistory" :key="i" class="history-item" :class="'sev-' + h.severity">
        <span class="history-time">{{ h.time }}</span>
        <span class="history-text">{{ h.text }}</span>
      </div>
    </div>

    <!-- TTS 反馈开关 -->
    <div class="tts-toggle">
      <label>
        <input type="checkbox" v-model="ttsEnabled" @change="onTtsToggle" />
        <span>语音播报告警</span>
      </label>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({ decision: Object })

const ttsEnabled = ref(true)
const alertHistory = ref([])
const currentAlertText = ref('')

// 计算告警等级
const severity = computed(() => {
  if (!props.decision) return 'none'
  const action = props.decision.action_code
  if (action === 'normal' || !action) return 'none'
  return props.decision.severity || 'mild'
})

const shouldAlert = computed(() => {
  return severity.value !== 'none' && props.decision?.recommendation_text
})

const severityClass = computed(() => 'sev-' + severity.value)

const severityIcon = computed(() => {
  const icons = { mild: '⚠️', moderate: '🟠', severe: '🔴' }
  return icons[severity.value] || '⚠️'
})

const alertText = computed(() => props.decision?.recommendation_text || '检测到分心驾驶')

const alertClass = computed(() => ({
  'panel-alerted': shouldAlert.value,
  'panel-severe': severity.value === 'severe',
}))

const alertKey = computed(() => severity.value + ':' + alertText.value)

// TTS 语音播报
function speak(text) {
  if (!ttsEnabled.value) return
  if (!('speechSynthesis' in window)) return
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.lang = 'zh-CN'
  u.rate = severity.value === 'severe' ? 1.1 : 0.9
  window.speechSynthesis.speak(u)
}

// 监听告警变化 → TTS + 记录历史
watch(shouldAlert, (newVal, oldVal) => {
  if (newVal) {
    // 新告警触发
    speak(alertText.value)
    alertHistory.value.unshift({
      severity: severity.value,
      text: alertText.value,
      time: new Date().toLocaleTimeString('zh-CN'),
    })
    if (alertHistory.value.length > 3) {
      alertHistory.value = alertHistory.value.slice(0, 3)
    }
  }
})

// 监听告警文字变化（同等级但文字不同也重新播报）
watch(alertText, (newText) => {
  if (shouldAlert.value && newText !== currentAlertText.value) {
    currentAlertText.value = newText
    speak(newText)
  }
})

function onTtsToggle() {
  // 同步到全局，让 DashboardView 也能读取
  window.__edgeguard_tts = ttsEnabled.value
  if (!ttsEnabled.value && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel()
  }
}
// 初始化全局标志
window.__edgeguard_tts = ttsEnabled.value
</script>

<style scoped>
.alert-panel {
  position: relative;
  overflow: hidden;
  transition: background 0.3s ease;
}

.panel-alerted {
  background: rgba(250, 173, 20, 0.1);
}

.panel-severe {
  background: rgba(255, 77, 79, 0.15);
  animation: severe-flash 0.8s infinite alternate;
}

@keyframes severe-flash {
  from { background: rgba(255, 77, 79, 0.15); }
  to   { background: rgba(255, 77, 79, 0.3); }
}

.alert-content {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border-radius: 8px;
  position: relative;
}

.sev-mild {
  background: rgba(250, 173, 20, 0.15);
  border-left: 4px solid #faad14;
  animation: mild-blink 1.5s infinite alternate;
}

.sev-moderate {
  background: rgba(250, 140, 20, 0.2);
  border-left: 4px solid #fa8c16;
  animation: moderate-pulse 1s infinite alternate;
}

.sev-severe {
  background: rgba(255, 77, 79, 0.2);
  border-left: 4px solid #ff4d4f;
}

@keyframes mild-blink {
  from { opacity: 0.8; }
  to   { opacity: 1; }
}

@keyframes moderate-pulse {
  from { transform: scale(1); }
  to   { transform: scale(1.02); }
}

.alert-icon {
  font-size: 24px;
}

.alert-text {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.alert-pulse {
  position: absolute;
  inset: 0;
  border-radius: 8px;
  border: 2px solid #ff4d4f;
  animation: pulse-ring 1s infinite;
}

@keyframes pulse-ring {
  0%   { transform: scale(1); opacity: 1; }
  100% { transform: scale(1.1); opacity: 0; }
}

.alert-ok, .alert-normal {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  font-size: 14px;
  color: #52c41a;
}

.ok-icon {
  font-size: 18px;
  font-weight: bold;
}

.alert-fade-enter-active, .alert-fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.alert-fade-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.alert-fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

.alert-history {
  margin-top: 10px;
  border-top: 1px solid #eee;
  padding-top: 8px;
}

.history-title {
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}

.history-item {
  display: flex;
  gap: 8px;
  font-size: 12px;
  padding: 2px 0;
}

.history-time {
  color: #aaa;
  flex-shrink: 0;
}

.history-text {
  color: #666;
}

.sev-mild .history-text { color: #faad14; }
.sev-moderate .history-text { color: #fa8c16; }
.sev-severe .history-text { color: #ff4d4f; }

.tts-toggle {
  margin-top: 8px;
  font-size: 12px;
  color: #888;
}

.tts-toggle label {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.placeholder {
  color: #999;
  text-align: center;
  padding: 20px;
}
</style>
