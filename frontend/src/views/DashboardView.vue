<template>
  <main class="flex h-dvh w-full overflow-hidden bg-background text-foreground">
    <!-- ① 左侧垂直导航栏 -->
    <AppSidebar
      :active="panel"
      :collapsed="sidebarCollapsed"
      @select="panel = $event"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
    />

    <!-- ② 主体区域 -->
    <div class="flex min-w-0 flex-1 flex-col">
      <!-- 顶栏 -->
      <TopBar :offline="isOffline" :weather="weatherText" />

      <!-- ③ 中间三区 -->
      <div class="flex min-h-0 flex-1">
        <!-- 左侧内容面板：随导航切换 -->
        <section v-if="panel !== 'trip'" class="w-[300px] shrink-0 border-r border-border">
          <SafetyPanel v-if="panel === 'safety'" :telemetry="telemetry" :alerts="alertHistory" />
          <StatsPanel v-if="panel === 'stats'" :stats="drivingStats" :severe="stats.severe" :loading="reportLoading" :report-text="reportText" @gen-report="genReport" />
          <SettingsPanel v-if="panel === 'settings'" :landmarks-on="showLandmarks" :light-mode="lightMode" @toggle-landmarks="onLandmarkToggle" @toggle-theme="toggleTheme" />
        </section>

        <!-- ④ 中央地图区 -->
        <section v-show="panel === 'trip'" class="min-w-0 flex-1 p-3">
          <TripPlanView :trip-plan="liveTripPlan" @navigate="onTripNavigate" />
        </section>
        <section v-show="panel !== 'trip'" class="min-w-0 flex-1 p-3">
          <MapArea :nav="navDisplay" :camera-ready="cameraReady" :visible="panel !== 'trip'" />
        </section>

        <!-- ⑤ 右侧 AI 面板（可折叠） -->
        <AiPanel
          v-if="aiOpen"
          :messages="chatMessages"
          :agent-steps="agentSteps"
          :agent-results="agentResults"
          :agent-running="agentRunning"
          @send="handleSend"
          @speak-reply="speakReply"
          @close="aiOpen = false"
        />
      </div>

      <!-- ⑥ 底部快捷栏 -->
      <BottomBar :ai-open="aiOpen" :gesture-name="gestureDisplay" :headers="headers" @open-ai="aiOpen = true" />
    </div>

    <!-- Toast overlays -->
    <div v-if="insightMsg" class="insight-toast">AI: {{ insightMsg }}</div>
    <div v-if="encourage" class="encourage-toast">{{ encourage }}</div>

  </main>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import type { PanelKey } from '@/components/hmi/AppSidebar.vue'
import AppSidebar from '@/components/hmi/AppSidebar.vue'
import TopBar from '@/components/hmi/TopBar.vue'
import SafetyPanel from '@/components/hmi/SafetyPanel.vue'
import StatsPanel from '@/components/hmi/StatsPanel.vue'
import MapArea from '@/components/hmi/MapArea.vue'
import AiPanel from '@/components/hmi/AiPanel.vue'
import BottomBar from '@/components/hmi/BottomBar.vue'
import SettingsPanel from '@/components/hmi/SettingsPanel.vue'
import TripPlanView from '@/components/hmi/TripPlanView.vue'
import { useTelemetry } from '@/composables/useTelemetry'
import { useAgentWS } from '@/composables/useAgentWS'
import {
  initialAlerts,
  initialChat,
  initialStats,
  mockNav,
  type ChatMessage,
  type SafetyAlert,
  type DrivingStats,
  type NavInfo,
  type AgentStep,
  type AgentResult,
} from '@/lib/edgeguard'

// ── Real-time data sources ──
const { telemetry, cameraReady, onAlert, headers, showLandmarks } = useTelemetry()
const {
  steps: liveSteps,
  results: liveResults,
  finalReply,
  navInfo: wsNavInfo,
  tripPlan: liveTripPlan,
  connected: wsConnected,
} = useAgentWS()

// ── Layout state ──
const panel = ref<PanelKey>('safety')
const sidebarCollapsed = ref(false)
const aiOpen = ref(true)

// ── Data state ──
const alertHistory = ref<SafetyAlert[]>([...initialAlerts])
const chatMessages = ref<ChatMessage[]>([...initialChat])
const drivingStats = ref<DrivingStats>({ ...initialStats })
const navDisplay = ref<NavInfo>({ ...mockNav })

// ── Gesture display ──
const gestureDisplay = computed(() => {
  const h = headers.value
  return h.gestureHint || (h.gesture && h.gesture !== '--' ? h.gesture : '') || ''
})

// ── Gesture → AC/Music command routing (via X-Action from decide_locally) ──
let lastAction = ''
let actionCooldown = 0
watch(() => headers.value.action, (action) => {
  console.log('[Dashboard] X-Action:', action, 'last:', lastAction)
  if (!action || action === 'normal') { lastAction = ''; return }
  if (action === lastAction) return
  // 2秒冷却防重复触发
  const now = Date.now()
  if (now - actionCooldown < 2000) { console.log('[Dashboard] cooldown skip'); return }
  actionCooldown = now
  lastAction = action
  console.log('[Dashboard] >>> EXEC:', action)
  const acCommands = ['TurnOnAC', 'TurnOffAC', 'temp_up', 'temp_down']
  const musicMap: Record<string, [string, string | undefined]> = {
    PlayMusic: ['/api/music/play', undefined],
    StopMusic: ['/api/music/pause', undefined],
    previous_track: ['/api/music/prev', undefined],
    next_track: ['/api/music/next', undefined],
    volume_up: ['/api/music/volume', JSON.stringify({ volume: 90 })],
    volume_down: ['/api/music/volume', JSON.stringify({ volume: 50 })],
  }
  if (acCommands.includes(action)) {
    fetch('/api/ac/command', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: action }) }).catch(() => {})
  } else if (action in musicMap) {
    const [url, body] = musicMap[action]
    fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body }).catch(() => {})
  }
})

// ── Agent state (from WebSocket) ──
const agentSteps = ref<AgentStep[]>([])
const agentResults = ref<AgentResult[]>([])
const agentRunning = ref(false)

// Watch WebSocket data → sync to display refs
watch(liveSteps, (s) => { agentSteps.value = [...s] }, { deep: true })
watch(liveResults, (r) => { agentResults.value = [...r] }, { deep: true })
watch(finalReply, (text) => {
  if (text) {
    chatMessages.value = [
      ...chatMessages.value,
      { id: `a${Date.now()}`, role: 'assistant', text },
    ]
    agentRunning.value = false
  }
})
watch(wsNavInfo, (nav) => {
  if (nav.destination) {
    navDisplay.value = { ...navDisplay.value, ...nav }
  }
})

// ── 行程规划联动出行面板 ──
// TripPlanView 切换天数时 emit navigate 事件，
// 这里调用后端 /api/navigation/route 规划从当前位置到目的地的完整驾车路线，
// 地图上会显示起点→终点的蓝色路线和标记，而非仅一个终点。
async function onTripNavigate(payload: { destination: string; day: number }) {
  // 不提前设置 destination，避免触发 MapArea 的 geocode 降级逻辑，
  // 导致单点标记覆盖完整路线。等路线数据返回后一次性设置全部字段。
  navDisplay.value = {
    ...navDisplay.value,
    nextTurn: `Day ${payload.day} 正在规划路线…`,
  }

  try {
    const r = await fetch('/api/navigation/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ destination: payload.destination }),
    })
    const data = await r.json()
    if (data.success) {
      navDisplay.value = {
        ...navDisplay.value,
        destination: data.destination || payload.destination,
        destinationCoords: data.destination_coords || null,
        originCoords: data.origin_coords || null,
        geometry: data.geometry || [],
        etaMin: Math.round(data.duration_min || 0),
        distanceKm: data.distance_km || 0,
        nextTurn: data.route_summary || `Day ${payload.day} 行程目的地`,
        steps: data.steps || [],
        routeSource: data.source || '',
        coordinateSystem: data.coordinate_system || '',
        originSource: data.origin_source || '',
      }
    } else {
      // 路线规划失败时才设置 destination，降级为单点显示
      navDisplay.value = {
        ...navDisplay.value,
        destination: payload.destination,
        nextTurn: data.route_summary || `Day ${payload.day} 行程目的地`,
      }
    }
  } catch {
    navDisplay.value = {
      ...navDisplay.value,
      destination: payload.destination,
      nextTurn: `Day ${payload.day} 行程目的地`,
    }
  }
}

// ── Alert callback from camera ──
let lastDistractionTime = 0
let goodDrivingFrames = 0
onAlert((h) => {
  const now = Date.now()
  if (now - lastDistractionTime > 3000) {
    stats.value.distractions++
    lastDistractionTime = now
  }
  if (h.severity === 'severe') {
    stats.value.severe++
  }
  // 驾驶鼓励：每专注 5 分钟弹一次（200ms 轮询, 5min = 1500 帧）
  if (!h.alertFlag && h.gaze === 'center') {
    goodDrivingFrames++
    if (goodDrivingFrames >= 1500) {
      encourage.value = '驾驶状态良好，请保持'
      setTimeout(() => { encourage.value = '' }, 4000)
      goodDrivingFrames = 0
    }
  } else if (h.alertFlag) {
    goodDrivingFrames = 0
    encourage.value = ''
  }
  // 构建中文告警标题
  const catLabel = h.alertLabel || h.alertCategory || '分心事件'
  const level = h.severity === 'severe' ? 'dangerous' : h.severity === 'moderate' ? 'distracted' : 'normal'
  alertHistory.value = [
    {
      id: `a${now}`,
      level: level as SafetyAlert['level'],
      title: level === 'dangerous' ? `严重${catLabel}` : level === 'distracted' ? `${catLabel}` : `${catLabel}`,
      detail: `视线: ${h.gaze || '未知'} · 疲劳: ${Math.round(h.fatigueScore)}%`,
      time: '刚刚',
    },
    ...alertHistory.value.slice(0, 19), // 保留最近 20 条
  ]
  // 同步更新驾驶统计
  drivingStats.value = {
    ...drivingStats.value,
    distractionCount: stats.value.distractions,
  }
})

// ── AI chat handler — 全部走 ReAct Agent，Agent 自己判断调什么工具 ──
async function handleSend(text: string) {
  const userMsg: ChatMessage = { id: `u${Date.now()}`, role: 'user', text }
  chatMessages.value = [...chatMessages.value, userMsg]

  agentRunning.value = true
  agentSteps.value = []
  agentResults.value = []

  try {
    const r = await fetch('/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        gesture: '',
        driver_state: {
          risk: telemetry.value.level === 'dangerous' ? 'high' : telemetry.value.level === 'distracted' ? 'medium' : 'safe',
          fatigue: telemetry.value.fatigue > 50,
          distracted: telemetry.value.gazeOnRoad < 70,
        },
      }),
    })
    const d = await r.json()
    if (d.status === 'ok' && d.result?.reply_text) {
      if (!wsConnected.value) {
        chatMessages.value = [
          ...chatMessages.value,
          { id: `a${Date.now()}`, role: 'assistant', text: d.result.reply_text },
        ]
        agentRunning.value = false
      }
    } else {
      chatMessages.value = [
        ...chatMessages.value,
        { id: `a${Date.now()}`, role: 'assistant', text: d.result?.reply_text || '抱歉，处理请求时遇到了问题。' },
      ]
      agentRunning.value = false
    }
  } catch {
    chatMessages.value = [
      ...chatMessages.value,
      { id: `a${Date.now()}`, role: 'assistant', text: '网络连接失败，请检查后端服务是否启动。' },
    ]
    agentRunning.value = false
  }
}

// ── TTS 语音播报 ──
function pickVoice(): SpeechSynthesisVoice | null {
  const voices = speechSynthesis.getVoices()
  return voices.find(v => v.name.includes('Xiaoxiao') && v.lang.startsWith('zh'))
      || voices.find(v => v.name.includes('Yunyang') && v.lang.startsWith('zh'))
      || voices.find(v => v.name.includes('Yunxia') && v.lang.startsWith('zh'))
      || voices.find(v => v.lang.startsWith('zh') && v.localService)
      || voices.find(v => v.lang.startsWith('zh'))
      || null
}

function doSpeak(text: string, voice: SpeechSynthesisVoice | null) {
  const u = new SpeechSynthesisUtterance(text)
  u.lang = 'zh-CN'; u.rate = 1.0; u.pitch = 1.0
  if (voice) u.voice = voice
  speechSynthesis.speak(u)
}

let _voicesReady = false
let _lastSpoken = ''
speechSynthesis.onvoiceschanged = () => { _voicesReady = true }

function speakReply(text: string) {
  if (!text) return
  // 3秒内相同内容去重
  if (text === _lastSpoken) return
  _lastSpoken = text
  setTimeout(() => { if (_lastSpoken === text) _lastSpoken = '' }, 3000)
  if (!('speechSynthesis' in window)) {
    new Audio(`/api/tts?text=${encodeURIComponent(text)}`).play().catch(() => {})
    return
  }
  speechSynthesis.cancel()
  if (_voicesReady || speechSynthesis.getVoices().length > 0) {
    _voicesReady = true
    doSpeak(text, pickVoice())
  } else {
    const handler = () => { _voicesReady = true; speechSynthesis.onvoiceschanged = null; doSpeak(text, pickVoice()) }
    speechSynthesis.onvoiceschanged = handler
  }
}

// ── 遗留统计功能 ──
const attentionScore = computed(() => telemetry.value.attention)
const insightMsg = ref('')
const encourage = ref('')
const isOffline = ref(false)

const stats = ref({ distractions: 0, severe: 0, startTime: Date.now() })
const reportLoading = ref(false)
const reportText = ref('')
function onLandmarkToggle() {
  showLandmarks.value = !showLandmarks.value
}

const lightMode = ref(false)
function toggleTheme() {
  lightMode.value = !lightMode.value
  document.documentElement.classList.toggle('dark', !lightMode.value)
  localStorage.setItem('edgeguard-theme', lightMode.value ? 'light' : 'dark')
}
;(() => {
  const t = localStorage.getItem('edgeguard-theme')
  if (t === 'light') { lightMode.value = true; document.documentElement.classList.remove('dark') }
})()

async function genReport() {
  reportLoading.value = true
  try {
    const mins = Math.round((Date.now() - stats.value.startTime) / 60000)
    const r = await fetch('/api/drive/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        duration_min: mins,
        distractions: stats.value.distractions,
        severe: stats.value.severe,
        attention_score: attentionScore.value,
        avg_gaze: 'center',
      }),
    })
    const d = await r.json()
    if (d.status === 'ok') {
      reportText.value = d.summary + '\n' + d.advice
    } else {
      reportText.value = d.message || '生成失败'
    }
  } catch {
    reportText.value = '生成失败，请重试'
  }
  reportLoading.value = false
}

// ── Weather ──
const weatherText = ref('')

async function fetchWeather() {
  try {
    const r = await fetch('/api/environment')
    const d = await r.json()
    if (d.status === 'ok' && d.data) {
      const w = d.data
      const temp = w.temperature != null ? `${Math.round(w.temperature)}°C` : ''
      const desc = w.weather_desc || ''
      weatherText.value = [temp, desc].filter(Boolean).join(' ') || '--°C'
    }
  } catch { /* ignore */ }
}

// ── 疲劳趋势采样（每 30 秒记录一次，保留最近 12 段）──
const fatigueSamples = ref<number[]>([])

// ── Periodic tasks ──
let statsTimer: ReturnType<typeof setInterval> | undefined
let statusTimer: ReturnType<typeof setInterval> | undefined
let weatherTimer: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  statsTimer = setInterval(() => {
    const mins = Math.floor((Date.now() - stats.value.startTime) / 60000)
    const durationStr = mins < 1 ? '<1分钟' : `${mins}分钟`
    // 疲劳采样
    const f = telemetry.value.fatigue
    fatigueSamples.value = [...fatigueSamples.value.slice(-11), f]
    // PERCLOS 累计平均
    const perclosRunning = (drivingStats.value.perclosAvg * (fatigueSamples.value.length - 1) + headers.value.perclos) / Math.max(1, fatigueSamples.value.length)
    drivingStats.value = {
      durationMin: mins,
      distractionCount: stats.value.distractions,
      perclosAvg: Math.round(perclosRunning * 1000) / 1000,
      fatigueTrend: [...fatigueSamples.value],
      score: Math.max(0, 100 - stats.value.distractions * 2 - stats.value.severe * 5),
    }
  }, 10000)

  statusTimer = setInterval(async () => {
    try {
      const r = await fetch('/api/status')
      isOffline.value = (await r.json()).offline_mode
    } catch { isOffline.value = true }
  }, 10000)

  fetchWeather()
  weatherTimer = setInterval(fetchWeather, 60000) // 每分钟刷新天气
})

onUnmounted(() => {
  if (statsTimer) clearInterval(statsTimer)
  if (statusTimer) clearInterval(statusTimer)
  if (weatherTimer) clearInterval(weatherTimer)
})

onUnmounted(() => {
  if (statsTimer) clearInterval(statsTimer)
  if (statusTimer) clearInterval(statusTimer)
})
</script>

<style>
/* Override old dashboard styles */
.dashboard { all: unset; }
.main-grid { all: unset; }
</style>

<style scoped>
/* Toast overlays */
.insight-toast {
  position: fixed;
  bottom: 120px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(59,130,246,0.15);
  border: 1px solid #3b82f6;
  color: #93c5fd;
  padding: 8px 20px;
  border-radius: 20px;
  font-size: 14px;
  z-index: 99;
  animation: fadeInOut 6s ease forwards;
  pointer-events: none;
}
.encourage-toast {
  position: fixed;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(34,197,94,0.15);
  border: 1px solid #22c55e;
  color: #86efac;
  padding: 8px 20px;
  border-radius: 20px;
  font-size: 14px;
  z-index: 99;
  animation: fadeInOut 4s ease forwards;
  pointer-events: none;
}
@keyframes fadeInOut {
  0% { opacity: 0; transform: translateX(-50%) translateY(10px); }
  15% { opacity: 1; transform: translateX(-50%) translateY(0); }
  85% { opacity: 1; }
  100% { opacity: 0; }
}
</style>
}