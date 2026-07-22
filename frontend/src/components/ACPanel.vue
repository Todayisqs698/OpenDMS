<template>
  <section class="panel ac-panel">
    <div class="panel-header">
      <h2 class="panel-title">空调控制</h2>
      <span class="ac-power-badge" :class="{ on: acState.power }">
        {{ acState.power ? 'ON' : 'OFF' }}
      </span>
    </div>

    <div class="ac-body">
      <!-- 温度大显示 -->
      <div class="ac-temp-display" :class="{ on: acState.power }">
        <span class="ac-temp-value">{{ acState.temperature }}</span>
        <span class="ac-temp-unit">°C</span>
      </div>

      <!-- 模式与风速 -->
      <div class="ac-meta">
        <span class="ac-mode">{{ modeLabel }}</span>
        <span class="ac-fan">{{ fanLabel }}</span>
      </div>

      <!-- 控制按钮 -->
      <div class="ac-controls">
        <button class="ac-btn power" :class="{ on: acState.power }" @click="togglePower">
          <span class="ac-btn-icon">⏻</span>
          <span class="ac-btn-label">{{ acState.power ? '关闭' : '开启' }}</span>
        </button>
        <button class="ac-btn temp" @click="tempDown" :disabled="!acState.power">
          <span class="ac-btn-icon">−</span>
          <span class="ac-btn-label">降温</span>
        </button>
        <button class="ac-btn temp" @click="tempUp" :disabled="!acState.power">
          <span class="ac-btn-icon">+</span>
          <span class="ac-btn-label">升温</span>
        </button>
      </div>

      <!-- 快捷模式 -->
      <div class="ac-modes">
        <button v-for="m in modes" :key="m.key"
          class="ac-mode-btn"
          :class="{ active: acState.mode === m.key && acState.power }"
          @click="setMode(m.key)"
          :disabled="!acState.power">
          {{ m.icon }} {{ m.label }}
        </button>
      </div>

      <!-- 最近操作日志 -->
      <div v-if="logs.length" class="ac-logs">
        <div v-for="(log, i) in logs.slice(0, 3)" :key="i" class="ac-log-item">
          <span class="ac-log-time">{{ log.time }}</span>
          <span class="ac-log-text">{{ log.text }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const acState = ref({ power: false, temperature: 24, mode: 'auto', fanSpeed: 2 })
const logs = ref([])
let pollTimer = null

const modes = [
  { key: 'cool', label: '制冷', icon: '❄️' },
  { key: 'heat', label: '制热', icon: '🔥' },
  { key: 'auto', label: '自动', icon: '🔄' },
  { key: 'fan', label: '送风', icon: '💨' },
]

const modeLabel = computed(() => {
  const m = modes.find(x => x.key === acState.value.mode)
  return m ? m.label : '自动'
})

const fanLabel = computed(() => {
  const s = acState.value.fanSpeed
  return s <= 1 ? '低风' : s <= 2 ? '中风' : '高风'
})

function addLog(text) {
  const now = new Date()
  const time = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`
  logs.value.unshift({ time, text })
  if (logs.value.length > 5) logs.value.pop()
}

async function fetchState() {
  try {
    const r = await fetch('/api/ac/state')
    if (r.ok) {
      const data = await r.json()
      if (data.status === 'ok' && data.data) acState.value = data.data
    }
  } catch (e) {}
}

async function sendCommand(command, extra = {}) {
  try {
    const r = await fetch('/api/ac/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, ...extra })
    })
    if (r.ok) {
      const data = await r.json()
      if (data.status === 'ok' && data.data) {
        acState.value = data.data
        addLog(data.message || command)
      }
    }
  } catch (e) {}
}

function togglePower() { sendCommand(acState.value.power ? 'TurnOffAC' : 'TurnOnAC') }
function tempUp() { sendCommand('temp_up') }
function tempDown() { sendCommand('temp_down') }
function setMode(mode) { sendCommand('set', { mode }) }

// 暴露方法给父组件（DashboardView 手势/语音触发）
defineExpose({
  async onCommand(payload) {
    // payload 可能是字符串（如 'TurnOnAC'）或对象（如 {command:'set', params:{mode:'cool'}}）
    if (typeof payload === 'string') {
      await sendCommand(payload)
    } else if (payload && payload.command) {
      await sendCommand(payload.command, payload.params || {})
    }
  },
  getState() { return acState.value }
})

onMounted(() => {
  fetchState()
  pollTimer = setInterval(fetchState, 3000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.ac-panel { display: flex; flex-direction: column; gap: 8px; }
.panel-header { display: flex; align-items: center; justify-content: space-between; }
.panel-title { margin: 0; font-size: 14px; font-weight: 600; color: #94a3b8; letter-spacing: 0.02em; }

.ac-power-badge {
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
  padding: 2px 8px; border-radius: 4px;
  background: rgba(100,116,139,0.15); color: #64748b;
  border: 1px solid rgba(100,116,139,0.2);
  transition: all 0.3s;
}
.ac-power-badge.on {
  background: rgba(34,197,94,0.12); color: #22c55e;
  border-color: rgba(34,197,94,0.3);
}

.ac-body { display: flex; flex-direction: column; gap: 10px; }

.ac-temp-display {
  display: flex; align-items: baseline; justify-content: center; gap: 4px;
  padding: 16px 0;
  background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
  border-radius: 10px; border: 1px solid #1e293b;
  transition: all 0.3s;
}
.ac-temp-display.on {
  border-color: rgba(34,197,94,0.3);
  box-shadow: 0 0 16px rgba(34,197,94,0.06);
}
.ac-temp-value { font-size: 48px; font-weight: 700; color: #475569; line-height: 1; transition: color 0.3s; }
.ac-temp-display.on .ac-temp-value { color: #4ade80; }
.ac-temp-unit { font-size: 16px; color: #64748b; }

.ac-meta { display: flex; justify-content: center; gap: 16px; font-size: 11px; color: #64748b; }

.ac-controls { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
.ac-btn {
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 10px 4px; border-radius: 8px; border: 1px solid #1e293b;
  background: #0f172a; color: #94a3b8; cursor: pointer;
  transition: all 0.2s;
}
.ac-btn:hover:not(:disabled) { background: rgba(30,41,59,0.6); border-color: #334155; }
.ac-btn:disabled { opacity: 0.3; cursor: default; }
.ac-btn.power.on { background: rgba(34,197,94,0.1); border-color: rgba(34,197,94,0.3); color: #4ade80; }
.ac-btn-icon { font-size: 20px; }
.ac-btn-label { font-size: 10px; }

.ac-modes { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 4px; }
.ac-mode-btn {
  padding: 6px 2px; border-radius: 6px; border: 1px solid transparent;
  background: rgba(15,23,42,0.5); color: #64748b; font-size: 10px;
  cursor: pointer; transition: all 0.2s;
}
.ac-mode-btn:hover:not(:disabled) { background: rgba(30,41,59,0.6); }
.ac-mode-btn.active { background: rgba(34,197,94,0.08); border-color: rgba(34,197,94,0.25); color: #4ade80; }
.ac-mode-btn:disabled { opacity: 0.3; cursor: default; }

.ac-logs { border-top: 1px solid #1e293b; padding-top: 6px; }
.ac-log-item { display: flex; gap: 8px; font-size: 10px; color: #64748b; padding: 2px 0; }
.ac-log-time { color: #475569; font-family: monospace; }
.ac-log-text { color: #94a3b8; }
</style>
