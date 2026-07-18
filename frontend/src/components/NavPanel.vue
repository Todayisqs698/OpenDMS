<template>
  <section class="panel nav-panel">
    <h2 class="panel-title">导航 & 环境</h2>

    <!-- 加载中 -->
    <div v-if="!envData" class="placeholder">
      <span class="loading-icon">⏳</span>
      <span>环境数据加载中...</span>
    </div>

    <!-- 数据就绪 -->
    <div v-else class="env-content">
      <!-- 时间 + 日期 -->
      <div class="env-section time-section">
        <div class="env-time">{{ currentTime }}</div>
        <div class="env-date">{{ currentDate }}</div>
      </div>

      <div class="env-divider"></div>

      <!-- 天气卡片（参考 QML weatherCard 设计）-->
      <div class="weather-card" :class="'weather-' + (envData.weather_icon || 'unknown')">
        <div class="weather-main">
          <span class="weather-emoji">{{ envData.weather_emoji || weatherEmoji }}</span>
          <span class="weather-temp">{{ tempDisplay }}</span>
        </div>
        <div class="weather-detail">
          <span class="weather-desc">{{ weatherLabel }}</span>
          <span class="weather-city">{{ envData.city || '--' }} <span class="loc-dot" :class="'loc-' + locationStatus" :title="locationHint">{{ locIcon }}</span></span>
        </div>
      </div>

      <div class="env-divider"></div>

      <!-- 详细环境数据 -->
      <div class="env-section env-details">
        <div class="env-row">
          <span class="env-label">💧 湿度</span>
          <span class="env-value">{{ envData.humidity != null ? envData.humidity + '%' : '--' }}</span>
        </div>
        <div class="env-row">
          <span class="env-label">💨 风速</span>
          <span class="env-value">{{ envData.wind_speed != null ? envData.wind_speed + ' km/h' : '--' }}</span>
        </div>
        <div class="env-row">
          <span class="env-label">👁️ 能见度</span>
          <span class="env-value">{{ envData.visibility != null ? envData.visibility + ' km' : '--' }}</span>
        </div>
        <div class="env-row" v-if="envData.risk_score != null">
          <span class="env-label">⚠️ 风险指数</span>
          <span class="env-value" :class="riskClass">{{ riskDisplay }}</span>
        </div>
      </div>

      <div class="env-divider"></div>

      <!-- 驾驶建议（参考 QML driverCard 设计）-->
      <div class="env-section">
        <div class="env-context" :class="contextClass">
          <span class="context-icon">🚗</span>
          <span>{{ envData.driving_context || '路况正常' }}</span>
        </div>
      </div>

      <!-- 预警列表（带动画）-->
      <div class="env-section alerts-section" v-if="envData.alerts && envData.alerts.length > 0">
        <TransitionGroup name="alert">
          <div class="env-alert" v-for="(alert, i) in envData.alerts" :key="i"
            :class="'alert-' + (alert.level || 'info')">
            <span class="alert-icon">{{ alert.icon || (alert.level === 'warning' ? '⚠️' : 'ℹ️') }}</span>
            <span class="alert-text">{{ alert.text }}</span>
          </div>
        </TransitionGroup>
      </div>

      <!-- 驾驶员状态指示器（新增，参考 QML driverState）-->
      <div class="env-divider"></div>
      <div class="driver-status" :class="'status-' + driverStatus">
        <span class="driver-icon">
          {{ driverStatus === 'dangerous' ? '⚠️' : driverStatus === 'distracted' ? '👀' : '✅' }}
        </span>
        <span class="driver-text">{{ driverStatusText }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

defineProps({ data: Object })

// ── 时间 ──
const currentTime = ref('')
const currentDate = ref('')
let timer = null

function updateClock() {
  const now = new Date()
  currentTime.value = now.toLocaleTimeString('zh-CN', { hour12: false })
  currentDate.value = now.toLocaleDateString('zh-CN', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
  })
}

// ── 环境数据 ──
const envData = ref(null)
const locationStatus = ref('idle')  // idle | locating | located | failed
const locIcon = computed(() => ({ idle: '📍', locating: '📡', located: '📍', failed: '⚠️' }[locationStatus.value]))
const locationHint = computed(() => ({ idle: '等待定位', locating: '定位中...', located: '已定位', failed: '定位失败，使用默认城市' }[locationStatus.value]))

// ── 浏览器 GPS 定位 ──
function getBrowserLocation() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      locationStatus.value = 'failed'
      resolve(null)
      return
    }
    locationStatus.value = 'locating'
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        locationStatus.value = 'located'
        resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude })
      },
      (err) => {
        console.log('[NavPanel] 定位失败:', err.message)
        locationStatus.value = 'failed'
        resolve(null)
      },
      { timeout: 8000, maximumAge: 300000 }
    )
  })
}

function handleEnvMessage(msg) {
  console.log('[NavPanel] 收到消息:', msg.type, msg.data ? '有数据' : '无数据')
  if (msg.type === 'environment' && msg.data) {
    console.log('[NavPanel] 环境数据就绪:', msg.data.weather, msg.data.temperature)
    envData.value = msg.data
  }
  if (msg.type === 'driver_state' && msg.data) {
    if (msg.data.risk_level) driverStatus.value = msg.data.risk_level
  }
}

// ── 驾驶员状态 ──
const driverStatus = ref('normal')
const driverStatusText = computed(() => {
  const map = {
    normal: '驾驶员状态正常',
    attention_declining: '注意力下降，请保持专注',
    distracted: '检测到分心，请注视前方',
    dangerous: '危险！请立即注意道路',
  }
  return map[driverStatus.value] || '状态未知'
})

// ── HTTP 降级（WebSocket 不可用时的兜底）──
async function fetchEnvFallback() {
  try {
    // 先获取浏览器 GPS 定位
    const gps = await getBrowserLocation()
    let url = 'http://localhost:8000/api/environment'
    if (gps) {
      url += `?lat=${gps.lat}&lon=${gps.lon}`
    }
    console.log('[NavPanel] HTTP 请求环境数据:', url)
    const res = await fetch(url)
    console.log('[NavPanel] HTTP 响应:', res.status, res.ok)
    if (res.ok) {
      const json = await res.json()
      console.log('[NavPanel] HTTP 数据:', json.status, json.data ? '有数据' : '无', '城市:', json.data?.city)
      if (json.data) envData.value = json.data
    }
  } catch (e) { console.log('[NavPanel] HTTP 请求失败:', e.message) }
}

// ── WebSocket（增强版：心跳+重连）──
let ws = null
let fallbackTimer = null
let heartbeatTimer = null
let reconnectTimeout = null
let reconnectAttempts = 0
const MAX_RECONNECT_DELAY = 30000

function connectWS() {
  try {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = location.host || 'localhost:8000'
    ws = new WebSocket(`${protocol}//${host}/ws/navpanel`)

    ws.onopen = () => {
      reconnectAttempts = 0
      startHeartbeat()
    }

    ws.onclose = () => {
      stopHeartbeat()
      scheduleReconnect()
    }

    ws.onerror = () => {
      // 静默处理，onclose 会触发重连
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        // 心跳响应
        if (msg.type === 'pong') return
        handleEnvMessage(msg)
      } catch { /* 忽略 */ }
    }
  } catch {
    // WebSocket 不可用，依赖 HTTP 降级
  }
}

function startHeartbeat() {
  stopHeartbeat()
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }))
    }
  }, 30000)
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

function scheduleReconnect() {
  if (reconnectTimeout) return
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY)
  reconnectAttempts++
  reconnectTimeout = setTimeout(() => {
    reconnectTimeout = null
    connectWS()
  }, delay)
}

// ── 计算属性 ──
const tempDisplay = computed(() => {
  const t = envData.value?.temperature
  return t != null ? `${t}°C` : '--'
})

const weatherEmoji = computed(() => {
  const emojiMap = {
    sunny: '☀️', cloudy: '☁️', rainy: '🌧️',
    snowy: '❄️', foggy: '🌫️', unknown: '❓',
  }
  return emojiMap[envData.value?.weather] || '🌤️'
})

const weatherLabel = computed(() => {
  return envData.value?.weather_desc || '--'
})

const contextClass = computed(() => {
  const ctx = envData.value?.driving_context || ''
  if (ctx.includes('恶劣') || ctx.includes('减速') || ctx.includes('暴雨')) return 'context-warning'
  if (ctx.includes('高峰') || ctx.includes('夜间') || ctx.includes('雾')) return 'context-caution'
  return 'context-normal'
})

const riskDisplay = computed(() => {
  const r = envData.value?.risk_score
  if (r == null) return '--'
  if (r >= 0.6) return `🔴 ${r}`
  if (r >= 0.3) return `🟡 ${r}`
  return `🟢 ${r}`
})

const riskClass = computed(() => {
  const r = envData.value?.risk_score
  if (r == null) return ''
  if (r >= 0.6) return 'risk-high'
  if (r >= 0.3) return 'risk-medium'
  return 'risk-low'
})

// ── 生命周期 ──
onMounted(() => {
  updateClock()
  timer = setInterval(updateClock, 1000)
  connectWS()
  fetchEnvFallback()
  fallbackTimer = setInterval(fetchEnvFallback, 30000)
})

onUnmounted(() => {
  clearInterval(timer)
  clearInterval(fallbackTimer)
  stopHeartbeat()
  if (reconnectTimeout) clearTimeout(reconnectTimeout)
  if (ws) ws.close()
})
</script>

<style scoped>
.panel-title {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.env-content { display: flex; flex-direction: column; gap: 6px; }
.env-section { margin-bottom: 2px; }

/* ── 时间 ── */
.time-section { text-align: center; }
.env-time {
  font-size: 28px; font-weight: bold; color: #f1f5f9;
  font-variant-numeric: tabular-nums;
}
.env-date { font-size: 13px; color: #94a3b8; margin-top: 2px; }

/* ── 天气卡片（参考 QML weatherCard）── */
.weather-card {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-radius: 10px;
  transition: background 0.3s;
}
.weather-sun     { background: linear-gradient(135deg, #1a3a2a, #0f2b1a); border: 1px solid #166534; }
.weather-cloud   { background: linear-gradient(135deg, #1e293b, #1a2332); border: 1px solid #334155; }
.weather-rain    { background: linear-gradient(135deg, #1a2744, #162033); border: 1px solid #1e3a5f; }
.weather-snow    { background: linear-gradient(135deg, #1e2a3a, #162233); border: 1px solid #2a3a4f; }
.weather-fog     { background: linear-gradient(135deg, #2a2a2a, #1e1e1e); border: 1px solid #444; }
.weather-unknown { background: #1e1e2d; border: 1px solid #333; }

.weather-main { display: flex; align-items: center; gap: 10px; }
.weather-emoji { font-size: 36px; }
.weather-temp { font-size: 28px; font-weight: bold; color: #f1f5f9; }
.weather-detail { text-align: right; }
.weather-desc { display: block; font-size: 14px; color: #e2e8f0; }
.weather-city { display: block; font-size: 11px; color: #64748b; margin-top: 2px; }
.loc-dot { font-size: 12px; cursor: help; }
.loc-locating { animation: loc-pulse 1.2s ease-in-out infinite; }
@keyframes loc-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.loc-failed { filter: grayscale(1); }

/* ── 详细数据 ── */
.env-details { padding: 0 4px; }
.env-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 3px 0; font-size: 13px;
}
.env-label { color: #64748b; }
.env-value { color: #e2e8f0; font-weight: 500; }

/* ── 驾驶建议（参考 QML driverStateMessage）── */
.env-context {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; padding: 10px 12px; border-radius: 8px; line-height: 1.5;
}
.context-icon { flex-shrink: 0; font-size: 18px; }
.context-warning {
  background: #7f1d1d; border: 1px solid #ef4444; color: #fca5a5;
}
.context-caution {
  background: #78350f; border: 1px solid #f59e0b; color: #fde68a;
}
.context-normal {
  background: #14532d; border: 1px solid #22c55e; color: #86efac;
}

/* ── 预警动画 ── */
.alerts-section { margin-top: 4px; }
.env-alert {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: 6px; margin-bottom: 4px; font-size: 12px;
}
.alert-warning { background: #7f1d1d; color: #fca5a5; border: 1px solid #991b1b; }
.alert-info    { background: #1e3a5f; color: #93c5fd; border: 1px solid #1e40af; }
.alert-icon { flex-shrink: 0; font-size: 14px; }
.alert-text { line-height: 1.4; }

/* Alert TransitionGroup */
.alert-enter-active { transition: all 0.4s ease-out; }
.alert-leave-active { transition: all 0.3s ease-in; }
.alert-enter-from { opacity: 0; transform: translateX(-20px); }
.alert-leave-to   { opacity: 0; transform: translateX(20px); }

/* ── 驾驶员状态（新增，参考 QML driverCard）── */
.driver-status {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; border-radius: 8px; font-size: 13px;
}
.status-normal {
  background: #14532d; border: 1px solid #22c55e; color: #86efac;
}
.status-attention_declining {
  background: #78350f; border: 1px solid #f59e0b; color: #fde68a;
}
.status-distracted {
  background: #7f1d1d; border: 1px solid #ef4444; color: #fca5a5;
  animation: pulse-warning 1.5s infinite;
}
.status-dangerous {
  background: #991b1b; border: 2px solid #ff0000; color: #fff;
  animation: pulse-danger 0.8s infinite;
}
.driver-icon { font-size: 20px; flex-shrink: 0; }
.driver-text { line-height: 1.4; }

@keyframes pulse-warning {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
@keyframes pulse-danger {
  0%, 100% { opacity: 1; border-color: #ff0000; }
  50% { opacity: 0.5; border-color: #ff6666; }
}

/* ── 风险指数 ── */
.risk-high   { color: #fca5a5 !important; font-weight: bold; }
.risk-medium { color: #fde68a !important; }
.risk-low    { color: #86efac !important; }

/* ── 加载状态 ── */
.placeholder {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  color: #4b5563; font-size: 14px; margin-top: 20px;
}
.loading-icon { font-size: 28px; animation: spin 2s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── 分割线 ── */
.env-divider { height: 1px; background: #1e293b; margin: 6px 0; }
</style>
