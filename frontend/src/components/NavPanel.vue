<template>
  <section class="panel nav-panel">
    <h2 class="panel-title">🗺️ 导航 & 环境</h2>

    <!-- 加载中 -->
    <div v-if="!envData" class="placeholder">
      <span class="loading-icon">⏳</span>
      <span>环境数据加载中...</span>
    </div>

    <div v-else class="env-content">
      <!-- 时间 + 日期 -->
      <div class="time-section">
        <div class="env-time">{{ currentTime }}</div>
        <div class="env-date">{{ currentDate }}</div>
      </div>

      <div class="env-divider"></div>

      <!-- 地图（Leaflet + 高德瓦片）-->
      <div class="map-wrapper">
        <div ref="mapEl" class="map-container"></div>
        <div class="map-tip">点击地图任意位置 = 设置为当前位置 → 天气自动更新</div>
      </div>

      <div class="env-divider"></div>

      <!-- 当前位置信息 -->
      <div class="location-info">
        <div class="location-row">
          <span class="loc-icon">📍</span>
          <span class="loc-text">{{ envData.city || '--' }}</span>
          <span class="loc-coord">{{ currentLat.toFixed(4) }}, {{ currentLon.toFixed(4) }}</span>
        </div>
        <div class="location-row" v-if="routeInfo">
          <span class="loc-icon">🚗</span>
          <span class="loc-text">→ {{ routeInfo.destination }}</span>
          <span class="loc-coord">{{ routeInfo.distance }}km / {{ routeInfo.duration }}min</span>
        </div>
      </div>

      <!-- 实时定位控制 -->
      <div class="gps-controls">
        <button class="gps-btn gps-btn-once" @click="getMyLocationOnce" :disabled="locating">
          {{ locating ? '定位中...' : '📍 定位一次' }}
        </button>
        <button class="gps-btn" :class="tracking ? 'gps-btn-stop' : 'gps-btn-track'" @click="toggleTracking">
          {{ tracking ? '⏸ 停止追踪' : '🛰️ 实时追踪' }}
        </button>
      </div>
      <div class="gps-status" v-if="gpsStatus">
        <span :class="['gps-dot', gpsStatusType]"></span>
        <span>{{ gpsStatus }}</span>
      </div>

      <div class="env-divider"></div>

      <!-- 路径规划 -->
      <div class="route-input">
        <input v-model="destination" type="text" class="route-field" placeholder="目的地（如 北京天安门）" @keyup.enter="planRoute" />
        <button class="route-btn" @click="planRoute" :disabled="!destination.trim() || planning">
          {{ planning ? '...' : '导航' }}
        </button>
      </div>

      <div class="env-divider"></div>

      <!-- 天气卡片（基于当前 GPS 位置）-->
      <div class="weather-card" :class="'weather-' + (envData.weather_icon || 'unknown')">
        <div class="weather-main">
          <span class="weather-emoji">{{ envData.weather_emoji || weatherEmoji }}</span>
          <span class="weather-temp">{{ tempDisplay }}</span>
        </div>
        <div class="weather-detail">
          <span class="weather-desc">{{ weatherLabel }}</span>
          <span class="weather-city">实时跟随 GPS</span>
        </div>
      </div>

      <!-- 详细环境数据 -->
      <div class="env-details">
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
          <span class="env-label">⚠️ 风险</span>
          <span class="env-value" :class="riskClass">{{ riskDisplay }}</span>
        </div>
      </div>

      <div class="env-divider"></div>

      <!-- 驾驶建议 -->
      <div class="env-context" :class="contextClass">
        <span class="context-icon">🚗</span>
        <span>{{ envData.driving_context || '路况正常' }}</span>
      </div>

      <!-- 预警列表 -->
      <div class="alerts-section" v-if="envData.alerts && envData.alerts.length > 0">
        <TransitionGroup name="alert">
          <div class="env-alert" v-for="(alert, i) in envData.alerts" :key="i"
               :class="'alert-' + (alert.level || 'info')">
            <span class="alert-icon">{{ alert.icon || (alert.level === 'warning' ? '⚠️' : 'ℹ️') }}</span>
            <span class="alert-text">{{ alert.text }}</span>
          </div>
        </TransitionGroup>
      </div>

      <!-- 状态指示 -->
      <div class="env-divider"></div>
      <div class="status-row">
        <span :class="['status-dot', envData.weather ? 'ok' : 'warn']"></span>
        <span class="status-text">{{ statusText }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

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
const currentLat = ref(39.9042)
const currentLon = ref(116.4074)
const destination = ref('')
const planning = ref(false)
const routeInfo = ref(null)

// ── 实时定位 ──
const locating = ref(false)
const tracking = ref(false)
const gpsStatus = ref('')
const gpsStatusType = ref('ok')   // ok / warn / error
let watchId = null

function getMyLocationOnce() {
  if (!('geolocation' in navigator)) {
    gpsStatus.value = '❌ 浏览器不支持 GPS 定位'
    gpsStatusType.value = 'error'
    return
  }
  locating.value = true
  gpsStatus.value = '正在获取 GPS...'
  gpsStatusType.value = 'warn'
  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      const { latitude: lat, longitude: lon, accuracy } = pos.coords
      gpsStatus.value = `定位成功（精度约 ${Math.round(accuracy)}m）`
      gpsStatusType.value = 'ok'
      await updateLocation(lat, lon, true)
      locating.value = false
    },
    (err) => {
      gpsStatus.value = `定位失败：${err.message || '用户拒绝或设备无 GPS'}`
      gpsStatusType.value = 'error'
      locating.value = false
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
  )
}

function toggleTracking() {
  if (tracking.value) {
    if (watchId != null) {
      navigator.geolocation.clearWatch(watchId)
      watchId = null
    }
    tracking.value = false
    gpsStatus.value = '⏸ 追踪已停止'
    gpsStatusType.value = 'warn'
  } else {
    if (!('geolocation' in navigator)) {
      gpsStatus.value = '❌ 浏览器不支持 GPS 定位'
      gpsStatusType.value = 'error'
      return
    }
    tracking.value = true
    gpsStatus.value = '🛰️ 实时追踪中...'
    gpsStatusType.value = 'ok'
    watchId = navigator.geolocation.watchPosition(
      async (pos) => {
        const { latitude: lat, longitude: lon, accuracy } = pos.coords
        // 只在位置变化 > 50m 时更新（避免抖动 + 节省 API 调用）
        if (calcDistance(lat, lon, currentLat.value, currentLon.value) > 0.05) {
          gpsStatus.value = `🛰️ 实时追踪中（精度 ${Math.round(accuracy)}m）`
          await updateLocation(lat, lon, false)
        }
      },
      (err) => {
        gpsStatus.value = `追踪失败：${err.message || 'GPS 不可用'}`
        gpsStatusType.value = 'error'
        tracking.value = false
      },
      { enableHighAccuracy: true, timeout: 30000, maximumAge: 5000 }
    )
  }
}

function calcDistance(lat1, lon1, lat2, lon2) {
  // 简易 Haversine 距离（km）
  const R = 6371
  const toRad = (x) => x * Math.PI / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

function handleEnvMessage(msg) {
  if (msg.type === 'environment' && msg.data) {
    envData.value = msg.data
    // 同步地图当前位置
    if (msg.data.lat != null && msg.data.lon != null) {
      currentLat.value = msg.data.lat
      currentLon.value = msg.data.lon
      if (map) {
        map.setView([msg.data.lat, msg.data.lon], map.getZoom())
        if (marker) marker.setLatLng([msg.data.lat, msg.data.lon])
      }
    }
  }
}

// ── 地图（Leaflet + 高德瓦片）──
let map = null
let marker = null
let routeLine = null
const mapEl = ref(null)

function initMap() {
  if (!window.L || !mapEl.value) return
  map = window.L.map(mapEl.value, {
    center: [currentLat.value, currentLon.value],
    zoom: 12,
    zoomControl: false,  // 隐藏默认的 +/- 按钮，自定义
    attributionControl: false,
  })
  // 高德瓦片（不需要 Key，中文标注好）
  window.L.tileLayer(
    'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    { subdomains: ['1', '2', '3', '4'], maxZoom: 18, minZoom: 4 }
  ).addTo(map)
  // 当前位置 marker
  marker = window.L.marker([currentLat.value, currentLon.value], { draggable: true }).addTo(map)
  // 拖拽 marker 也能更新位置
  marker.on('dragend', async (e) => {
    const { lat, lng } = e.target.getLatLng()
    await updateLocation(lat, lng)
  })
  // 点击地图设置位置
  map.on('click', async (e) => {
    const { lat, lng } = e.latlng
    marker.setLatLng([lat, lng])
    await updateLocation(lat, lng)
  })
}

async function updateLocation(lat, lon, updateMap = true) {
  currentLat.value = lat
  currentLon.value = lon
  if (updateMap && map) {
    map.setView([lat, lon], map.getZoom())
    if (marker) marker.setLatLng([lat, lon])
  }
  try {
    // 1. 写 location_store
    await fetch('/api/location', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon }),
    })
    // 2. 立即拉一次环境（不等 15s 周期）
    const r = await fetch('/api/environment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon }),
    })
    const d = await r.json()
    if (d.data) {
      envData.value = d.data
    }
  } catch (e) {
    console.log('[NavPanel] updateLocation 失败:', e.message)
  }
}

async function planRoute() {
  const dest = destination.value.trim()
  if (!dest) return
  planning.value = true
  try {
    const r = await fetch('/api/navigation/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ destination: dest, lat: currentLat.value, lon: currentLon.value }),
    })
    const d = await r.json()
    if (d.success && d.geometry && d.geometry.length > 0 && window.L) {
      // 清除旧路径
      if (routeLine) {
        map.removeLayer(routeLine)
        routeLine = null
      }
      // 画新路径
      routeLine = window.L.polyline(d.geometry, { color: '#22c55e', weight: 5, opacity: 0.8 }).addTo(map)
      // 终点 marker
      const lastPt = d.geometry[d.geometry.length - 1]
      window.L.marker(lastPt, { icon: window.L.divIcon({ className: 'dest-icon', html: '🏁', iconSize: [24, 24] }) }).addTo(map)
      // 缩放到路径范围
      map.fitBounds(routeLine.getBounds(), { padding: [20, 20] })
      routeInfo.value = {
        destination: d.destination,
        distance: d.distance_km,
        duration: d.duration_min,
      }
    } else {
      // 降级：直线
      routeInfo.value = {
        destination: dest,
        distance: d.distance_km || 0,
        duration: d.duration_min || 0,
      }
      alert(d.route_summary || '路径规划失败：' + (d.route_summary || '未知错误'))
    }
  } catch (e) {
    alert('导航请求失败：' + e.message)
  } finally {
    planning.value = false
  }
}

// ── HTTP 拉取环境数据 ──
async function fetchEnv() {
  try {
    // 用 GPS 坐标拉环境
    const r = await fetch('/api/environment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat: currentLat.value, lon: currentLon.value }),
    })
    if (r.ok) {
      const d = await r.json()
      if (d.data) {
        envData.value = d.data
        if (d.data.lat != null) currentLat.value = d.data.lat
        if (d.data.lon != null) currentLon.value = d.data.lon
      }
    }
  } catch (e) { /* ignore */ }
}

// ── WebSocket ──
let ws = null
let reconnectTimeout = null
let reconnectAttempts = 0
const MAX_RECONNECT_DELAY = 30000

function connectWS() {
  try {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = location.host || 'localhost:8000'
    ws = new WebSocket(`${protocol}//${host}/ws/navpanel`)
    ws.onopen = () => { reconnectAttempts = 0 }
    ws.onclose = () => { scheduleReconnect() }
    ws.onerror = () => { /* onclose will handle */ }
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'pong') return
        handleEnvMessage(msg)
      } catch { /* ignore */ }
    }
  } catch { /* ignore */ }
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

const weatherLabel = computed(() => envData.value?.weather_desc || '--')

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

const statusText = computed(() => {
  if (!envData.value) return '环境数据采集中...'
  return 'GPS 天气实时联动中'
})

// ── 生命周期 ──
onMounted(async () => {
  updateClock()
  timer = setInterval(updateClock, 1000)

  // 初始化地图（等 DOM ready）
  await nextTick()
  initMap()

  // 立即拉一次（不等 WS）
  await fetchEnv()
  // 每 30s 拉一次（兜底 + 跟随 GPS）
  setInterval(fetchEnv, 30000)

  connectWS()
})

onUnmounted(() => {
  clearInterval(timer)
  if (reconnectTimeout) clearTimeout(reconnectTimeout)
  if (watchId != null) {
    navigator.geolocation.clearWatch(watchId)
    watchId = null
  }
  if (ws) ws.close()
  if (map) {
    map.remove()
    map = null
  }
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

/* ── 时间 ── */
.time-section { text-align: center; }
.env-time {
  font-size: 28px; font-weight: bold; color: #f1f5f9;
  font-variant-numeric: tabular-nums;
}
.env-date { font-size: 13px; color: #94a3b8; margin-top: 2px; }

/* ── 地图 ── */
.map-wrapper { display: flex; flex-direction: column; gap: 4px; }
.map-container {
  width: 100%;
  height: 200px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #1e293b;
  background: #1a2236;
}
.map-tip {
  font-size: 10px;
  color: #64748b;
  text-align: center;
}
:deep(.dest-icon) {
  font-size: 18px;
  text-align: center;
  line-height: 24px;
}
:deep(.leaflet-container) { background: #1a2236; }

/* ── 位置信息 ── */
.location-info { padding: 0 4px; }
.location-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  padding: 3px 0;
}
.loc-icon { font-size: 14px; flex-shrink: 0; }
.loc-text { color: #e2e8f0; font-weight: 500; flex: 1; }
.loc-coord { color: #64748b; font-size: 11px; font-family: monospace; }

/* ── 路径输入 ── */
.route-input { display: flex; gap: 4px; }
.route-field {
  flex: 1;
  background: #1a2236;
  border: 1px solid #1e293b;
  color: #cbd5e1;
  padding: 5px 10px;
  border-radius: 5px;
  font-size: 12px;
  outline: none;
}
.route-field:focus { border-color: #22c55e; }
.route-btn {
  background: #22c55e;
  color: #000;
  border: none;
  padding: 5px 12px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 12px;
  font-weight: bold;
}
.route-btn:hover { background: #4ade80; }
.route-btn:disabled { background: #334155; color: #94a3b8; cursor: not-allowed; }

/* ── GPS 实时定位控件 ── */
.gps-controls {
  display: flex;
  gap: 4px;
}
.gps-btn {
  flex: 1;
  background: #1a2236;
  color: #cbd5e1;
  border: 1px solid #1e293b;
  padding: 6px 10px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 500;
}
.gps-btn:hover:not(:disabled) {
  background: #22c55e;
  color: #000;
  border-color: #22c55e;
}
.gps-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.gps-btn-track {
  background: #1e3a5f;
  border-color: #3b82f6;
  color: #93c5fd;
}
.gps-btn-stop {
  background: #7f1d1d;
  border-color: #ef4444;
  color: #fca5a5;
  animation: gps-pulse 1.5s infinite;
}
@keyframes gps-pulse {
  50% { opacity: 0.7; }
}
.gps-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
  padding: 4px 6px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
}
.gps-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.gps-dot.ok { background: #22c55e; box-shadow: 0 0 4px #22c55e; }
.gps-dot.warn { background: #fbbf24; }
.gps-dot.error { background: #ef4444; }

/* ── 天气卡片 ── */
.weather-card {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-radius: 10px;
  transition: background 0.3s;
}
.weather-sun     { background: linear-gradient(135deg, #1a3a2a, #0f2b1a); border: 1px solid #166534; }
.weather-cloud   { background: linear-gradient(135deg, #1e293b, #1e2332); border: 1px solid #334155; }
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

/* ── 详细数据 ── */
.env-details { padding: 0 4px; }
.env-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 3px 0; font-size: 13px;
}
.env-label { color: #64748b; }
.env-value { color: #e2e8f0; font-weight: 500; }

/* ── 驾驶建议 ── */
.env-context {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; padding: 10px 12px; border-radius: 8px; line-height: 1.5;
}
.context-icon { flex-shrink: 0; font-size: 18px; }
.context-warning { background: #7f1d1d; border: 1px solid #ef4444; color: #fca5a5; }
.context-caution { background: #78350f; border: 1px solid #f59e0b; color: #fde68a; }
.context-normal  { background: #14532d; border: 1px solid #22c55e; color: #86efac; }

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

.alert-enter-active { transition: all 0.4s ease-out; }
.alert-leave-active { transition: all 0.3s ease-in; }
.alert-enter-from { opacity: 0; transform: translateX(-20px); }
.alert-leave-to   { opacity: 0; transform: translateX(20px); }

/* ── 状态指示 ── */
.status-row {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: #64748b;
}
.status-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #22c55e;
}
.status-dot.warn { background: #f59e0b; }
.status-text { font-family: monospace; }

/* ── 风险指数 ── */
.risk-high   { color: #fca5a5 !important; font-weight: bold; }
.risk-medium { color: #fde68a !important; }
.risk-low    { color: #86efac !important; }

/* ── 分割线 ── */
.env-divider { height: 1px; background: #1e293b; margin: 6px 0; }

/* ── 加载状态 ── */
.placeholder {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  color: #4b5563; font-size: 14px; margin-top: 20px;
}
.loading-icon { font-size: 28px; animation: spin 2s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
