<template>
  <div class="dashboard">
    <header class="top-bar">
      <span class="top-left">EdgeGuard v1.0</span>
      <span class="top-center">
        <span>{{ currentTime }}</span>
      </span>
      <span class="top-right">
        <span class="attention-score">注意力 {{ attentionScore }}%</span>
        <span class="online-dot" :class="{ offline: isOffline }"></span>
        {{ isOffline ? '离线' : '在线' }}
      </span>
    </header>

    <main class="main-grid">
      <GaugePanel :data="driverState" />
      <AlertPanel :decision="lastDecision" />
      <AiPanel :decision="lastDecision" :driverState="driverState" />
      <VoicePanel :data="driverState" />
      <NavPanel :data="driverState" />
    </main>

    <!-- 摄像头实时画面浮窗（可拖拽可缩放） -->
    <div
      v-show="!minimized"
      class="camera-float"
      :style="{ left: camX + 'px', top: camY + 'px', width: camW + 'px', height: camH + 'px' }"
      @mousedown="startCamDrag"
    >
      <canvas ref="cameraCanvas" class="camera-feed" width="640" height="480" style="pointer-events:none"></canvas>
      <div class="camera-label">{{ camSize }}</div>
      <button class="minimize-btn" @mousedown.stop @click.stop="minimized = true" title="最小化">_</button>
      <div class="resize-handle" @mousedown.stop="startResize"></div>
    </div>

    <!-- AI 主动播报 -->
    <div v-if="insightMsg" class="insight-toast">AI: {{ insightMsg }}</div>

    <!-- 驾驶鼓励提示 -->
    <div v-if="encourage" class="encourage-toast">{{ encourage }}</div>

    <!-- 统计侧栏 -->
    <div class="stats-sidebar" :class="{ open: showStats }">
      <div class="stats-toggle" @click="showStats = !showStats">
        {{ showStats ? '▶' : '◀' }}
      </div>
      <div v-if="showStats" class="stats-content">
        <h3>驾驶统计</h3>
        <div class="stat-row"><span>驾驶时长</span><span>{{ statsDuration }}</span></div>
        <div class="stat-row"><span>分心次数</span><span>{{ stats.distractions }}</span></div>
        <div class="stat-row"><span>严重分心</span><span>{{ stats.severe }}</span></div>
        <div class="stat-divider"></div>
        <button class="report-btn" @click="genReport" :disabled="reportLoading">
          {{ reportLoading ? '生成中...' : '生成驾驶报告' }}
        </button>
        <div v-if="reportText" class="report-text">{{ reportText }}</div>
        <div class="stat-divider"></div>
        <div class="stat-row toggle-row">
          <span>面部标记</span>
          <label class="toggle-switch">
            <input type="checkbox" v-model="showLandmarks" @change="onLandmarkToggle">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="stat-row toggle-row">
          <span>浅色模式</span>
          <label class="toggle-switch">
            <input type="checkbox" v-model="lightMode" @change="toggleTheme">
            <span class="toggle-slider"></span>
          </label>
        </div>
      </div>
    </div>

    <!-- 最小化气泡 -->
    <div
      v-show="minimized"
      class="camera-bubble"
      :style="{ left: camX + 'px', top: camY + 'px' }"
      @mousedown="startBubbleDrag"
    >
      CAM
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import GaugePanel from '../components/GaugePanel.vue'
import AlertPanel from '../components/AlertPanel.vue'
import AiPanel from '../components/AiPanel.vue'
import VoicePanel from '../components/VoicePanel.vue'
import NavPanel from '../components/NavPanel.vue'

const currentTime = ref('')
const cameraStatus = ref('连接中...')
const driverState = ref({ gaze: '--', gesture: '--', speech: '', route: 'camera', perclos: null, blink_rate: null, fatigue_score: null, fatigue_level: null })
const lastDecision = ref({ action_code: 'normal' })
const cameraCanvas = ref(null)
const insightMsg = ref('')
const isOffline = ref(false)
setInterval(async () => {
  try {
    const r = await fetch('http://localhost:8000/api/status')
    isOffline.value = (await r.json()).offline_mode
  } catch(e) { isOffline.value = true }
}, 10000)

// AI 主动观察（事件触发 + 最长间隔兜底）
let lastInsightTime = 0
let insightCooldown = 0
async function triggerInsight(reason) {
  // 不同事件不同冷却：手势5秒，严重分心无冷却，其他8秒
  const cooldown = reason.startsWith('手势') ? 5000 :
                   reason === '严重分心' ? 0 : 8000
  if (Date.now() - lastInsightTime < cooldown) return
  lastInsightTime = Date.now()
  try {
    const ad = lastDecision.value
    let context = `注意力${attentionScore.value}分`
    if (cameraStatus.value !== 'center') context += `，视线偏离${cameraStatus.value}`
    const g = (driverState.value.gesture || '') === '--' ? '' : driverState.value.gesture
    if (g) context += `，手势${g}`
    if (ad && ad.severity === 'severe') context += '，严重分心'
    context += `。触发原因: ${reason}`

    const r = await fetch('http://localhost:8000/api/drive/insight', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gaze_pattern: context,
        gesture: g,
        duration_sec: 0,
        attention: attentionScore.value
      })
    })
    const d = await r.json()
    if (d.speak && d.text) {
      insightMsg.value = d.text
      lastBeepTime = Date.now() + 5000  // 抑制计时器嘟声5秒
      try { speak(d.text) } catch(e) {}
      setTimeout(() => { insightMsg.value = '' }, 6000)
    }
  } catch(e) {}
}

// 摄像头浮窗拖拽+缩放
const camX = ref(window.innerWidth - 260)
const camY = ref(window.innerHeight - 220)
const camW = ref(240)
const camH = ref(180)
const camSize = ref('240x180')
const minimized = ref(false)
const attentionScore = ref(100)
let goodFrames = 0, badFrames = 0
let lastAlertState = '0'
let lastSeverity = 'normal'
let lastGaze = 'center'
let sustainedGazeFrames = 0
let lastGestureObserved = ''
let pendingGesture = ''
let gestureStableFrames = 0

// 告警提示音（Web Audio API）
let audioCtx = null
function beep(freq, duration, type = 'square') {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)()
    const osc = audioCtx.createOscillator()
    const gain = audioCtx.createGain()
    osc.type = type; osc.frequency.value = freq
    gain.gain.value = 0.08
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration)
    osc.connect(gain); gain.connect(audioCtx.destination)
    osc.start(); osc.stop(audioCtx.currentTime + duration)
  } catch(e) {}
}
function playAlertSound(severity) {
  if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume()
  if (severity === 'severe') {
    beep(880, 0.25); setTimeout(() => beep(660, 0.25), 250); setTimeout(() => beep(880, 0.25), 500)
  } else {
    beep(660, 0.15)
  }
}
// TTS 语音告警
// 选最自然的语音
let bestVoice = null
function pickVoice() {
  const voices = speechSynthesis.getVoices()
  // 优先选中文自然语音
  bestVoice = voices.find(v => v.name.includes('Xiaoxiao')) ||
              voices.find(v => v.lang === 'zh-CN' && v.localService) ||
              voices.find(v => v.lang === 'zh-CN') ||
              voices[0]
}
speechSynthesis.onvoiceschanged = pickVoice
pickVoice()

let audioEl = null
function speak(text) {
  // 检查 TTS 全局开关（AlertPanel 的"语音播报告警"勾选框同步到此）
  if (window.__edgeguard_tts === false) return
  if (!text) return
  try {
    if (!audioEl) { audioEl = new Audio(); audioEl.volume = 0.8 }
    audioEl.src = `http://localhost:8000/api/tts?text=${encodeURIComponent(text)}`
    audioEl.play().catch(() => {})
  } catch(e) {}
}

let lastTtsTime = 0
function speakAlert(text) {
  if (window.__edgeguard_tts === false) return
  const now = Date.now()
  if (now - lastTtsTime < 5000) return
  lastTtsTime = now
  speak(text)
}

// 驾驶统计
const stats = ref({ distractions: 0, severe: 0, startTime: Date.now() })
const showStats = ref(false)
const encourage = ref('')
let goodDrivingSince = 0
let lastBeepTime = 0
let lastDistractionTime = 0
const showLandmarks = ref(true)
let landmarksEnabled = true

const lightMode = ref(false)
function onLandmarkToggle() {
  landmarksEnabled = showLandmarks.value
}
const reportLoading = ref(false)
const reportText = ref('')

async function genReport() {
  reportLoading.value = true
  try {
    const mins = (Date.now() - stats.value.startTime) / 60000
    const r = await fetch('http://localhost:8000/api/drive/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        duration_min: Math.round(mins),
        distractions: stats.value.distractions,
        severe: stats.value.severe,
        attention_score: attentionScore.value,
        avg_gaze: driverState.value.gaze
      })
    })
    const d = await r.json()
    if (d.status === 'ok') {
      reportText.value = d.summary + '\n' + d.advice
      try {
        speak(d.summary + '。' + d.advice)
      } catch(e) {}
    } else {
      reportText.value = d.message
    }
  } catch(e) {
    reportText.value = '生成失败，请重试'
  }
  reportLoading.value = false
}

function toggleTheme() {
  document.body.classList.toggle('light-theme', lightMode.value)
}

const statsDuration = ref('<1分钟')
setInterval(() => {
  const mins = Math.floor((Date.now() - stats.value.startTime) / 60000)
  statsDuration.value = mins < 1 ? '<1分钟' : `${mins}分钟`
}, 10000)  // 每10秒更新
let dragStartX = 0, dragStartY = 0, startW = 0, startH = 0, startX = 0, startY = 0

let camDragStartX = 0, camDragStartY = 0, camStartX = 0, camStartY = 0
function startCamDrag(e) {
  if (e.target !== e.currentTarget) return  // 只在浮窗本体上拖
  camDragStartX = e.clientX; camDragStartY = e.clientY
  camStartX = camX.value; camStartY = camY.value
  document.addEventListener('mousemove', onCamDrag)
  document.addEventListener('mouseup', stopCamDrag)
}
function onCamDrag(e) {
  camX.value = camStartX + e.clientX - camDragStartX
  camY.value = camStartY + e.clientY - camDragStartY
}
function stopCamDrag() {
  document.removeEventListener('mousemove', onCamDrag)
  document.removeEventListener('mouseup', stopCamDrag)
}

function startResize(e) {
  camDragStartX = e.clientX; camDragStartY = e.clientY
  startW = camW.value; startH = camH.value
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
}
function onResize(e) {
  camW.value = Math.max(160, startW + e.clientX - camDragStartX)
  camH.value = Math.max(120, startH + e.clientY - camDragStartY)
  camSize.value = camW.value + 'x' + camH.value
}
function stopResize() {
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
}

let bubbleMoved = false
function startBubbleDrag(e) {
  bubbleMoved = false
  dragStartX = e.clientX; dragStartY = e.clientY
  startX = camX.value; startY = camY.value
  document.addEventListener('mousemove', onBubbleMove)
  document.addEventListener('mouseup', onBubbleUp)
}
function onBubbleMove(e) {
  if (Math.abs(e.clientX - dragStartX) > 3 || Math.abs(e.clientY - dragStartY) > 3) {
    bubbleMoved = true
  }
  camX.value = startX + e.clientX - dragStartX
  camY.value = startY + e.clientY - dragStartY
}
function onBubbleUp() {
  document.removeEventListener('mousemove', onBubbleMove)
  document.removeEventListener('mouseup', onBubbleUp)
  if (!bubbleMoved) minimized.value = false
}

let clockTimer = null
let cameraTimer = null

async function refreshCamera() {
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 2000)
    const resp = await fetch(`http://localhost:8000/api/camera/frame?t=${Date.now()}&landmarks=${landmarksEnabled ? '1' : '0'}`, {
      signal: controller.signal
    })
    clearTimeout(timeout)
    if (!resp.ok) return

    // 帧 → Canvas
    const blob = await resp.blob()
    const img = new Image()
    img.onload = () => {
      const canvas = cameraCanvas.value
      if (!canvas) return
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
    }
    img.src = URL.createObjectURL(blob)

    // 状态 → 大屏
    const gaze = resp.headers.get('X-Gaze')
    const gesture = resp.headers.get('X-Gesture')
    const action = resp.headers.get('X-Action')
    const alert = resp.headers.get('X-Alert')
    const severity = resp.headers.get('X-Severity')
    const confidence = parseFloat(resp.headers.get('X-Confidence')) || 0

    // 告警统计 + 离线备用提示音
    if (alert === '1') {
      const now = Date.now()
      if (lastAlertState === '0') {
        if (now - lastDistractionTime > 3000) {
          stats.value.distractions++; lastDistractionTime = now
        }
      }
      if (severity === 'severe' && lastSeverity !== 'severe') {
        stats.value.severe++
      }
      // 离线时用计时器嘟声兜底
      if (isOffline.value) {
        if (lastAlertState === '0') speakAlert('请注视前方')
        if (severity === 'severe' && now - lastBeepTime > 1600) {
          lastBeepTime = now; playAlertSound(severity)
        } else if (lastAlertState === '0') {
          lastBeepTime = now; playAlertSound(severity)
        }
      }
      goodDrivingSince = 0
    }
    // AI 事件触发（偏离需持续3秒以上，意外短暂瞥一眼不打扰）
    if (alert === '1' && lastAlertState === '0' && severity === 'severe') triggerInsight('严重分心')
    else if (gaze !== 'center' && lastGaze === 'center') {
      sustainedGazeFrames = 0
    } else if (gaze !== 'center' && gaze === lastGaze) {
      sustainedGazeFrames++
      if (sustainedGazeFrames === 15) triggerInsight('持续视线偏离')  // ~3秒
    }
    if (gesture && gesture !== '--') {
      if (gesture !== pendingGesture) {
        pendingGesture = gesture
        gestureStableFrames = 1
      } else {
        gestureStableFrames++
        if (gestureStableFrames === 5 && gesture !== lastGestureObserved) {  // 稳定1秒
          lastGestureObserved = gesture
          const gestureLabels = { 'Thumbs Up': '确认', 'Thumbs Down': '取消', 'Open': '张开手掌', 'Fist': '握拳', 'Point': '指向', 'Peace': '胜利', 'OK': 'OK' }
          triggerInsight('手势: 驾驶员做了' + (gestureLabels[gesture] || gesture) + '手势，请给简短反馈')
        }
      }
    } else {
      pendingGesture = ''
      gestureStableFrames = 0
    }

    lastAlertState = alert
    lastSeverity = severity || 'normal'
    lastGaze = gaze || 'center'

    // 注意力评分 + 冲突检测
    if (gaze === 'center') { goodFrames++; badFrames = Math.max(0, badFrames - 1) }
    else if (gaze === 'lost') { badFrames += 2 }
    else { badFrames++ }
    const total = goodFrames + badFrames
    attentionScore.value = total > 0 ? Math.round(goodFrames / total * 100) : 100
    // 驾驶鼓励：每专注 5 分钟提示一次
    if (alert === '0' && gaze === 'center') {
      goodDrivingSince++
      if (goodDrivingSince === 1500) {  // ~5分钟
        encourage.value = '驾驶状态良好，请保持'
        try { /* no cancel - let speeches queue */; speak('驾驶状态良好') } catch(e) {}
        setTimeout(() => { encourage.value = '' }, 4000)
        goodDrivingSince = 0
      }
    } else if (alert === '1') {
      goodDrivingSince = 0
      encourage.value = ''
    }


    cameraStatus.value = gaze || 'error'
    const perclos = parseFloat(resp.headers.get('X-Perclos')) || 0
    const blinkRate = parseFloat(resp.headers.get('X-BlinkRate')) || 0
    const fatigueScore = parseInt(resp.headers.get('X-FatigueScore')) || 0
    const fatigueLevel = resp.headers.get('X-FatigueLevel') || 'normal'
    driverState.value = {
      gaze: gaze || 'lost',
      gesture: gesture || '--',
      speech: '',
      route: 'camera',
      confidence: Math.round(confidence * 100),
      perclos: perclos,
      blink_rate: blinkRate,
      fatigue_score: fatigueScore,
      fatigue_level: fatigueLevel,
    }
    // 根据严重度和持续时间生成动态告警文字
    const dur = parseFloat(resp.headers.get('X-Duration')) || 0
    const alertLabels = {
      mild: `请保持视线在前方（${dur.toFixed(0)}秒）`,
      moderate: `视线偏离道路，请注意（${dur.toFixed(0)}秒）`,
      severe: `严重分心！请立即注视前方（${dur.toFixed(0)}秒）`,
    }
    lastDecision.value = {
      action_code: action || 'normal',
      recommendation_text: (alert === '1') ? (alertLabels[severity] || alertLabels.mild) : undefined,
      source: 'camera',
      severity: severity || 'normal',
      confidence: Math.round(confidence * 100)
    }
  } catch(e) {
    cameraStatus.value = '离线'
  }
}

onMounted(() => {
  clockTimer = setInterval(() => {
    currentTime.value = new Date().toLocaleTimeString('zh-CN')
  }, 1000)
  refreshCamera()
  cameraTimer = setInterval(refreshCamera, 200)
})

onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(cameraTimer)
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0a0e17; color: #e0e6ed; font-family: 'Microsoft YaHei', sans-serif; }

.dashboard { height: 100vh; display: flex; flex-direction: column; }

.top-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 20px; background: #111827; border-bottom: 1px solid #1e293b;
  font-size: 14px;
}
.top-left, .top-right { min-width: 160px; }
.top-right { text-align: right; display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
.online-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #22c55e; }
.online-dot.offline { background: #ef4444; }

.llm-test-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 20px; background: #0d1117; border-bottom: 1px solid #1e293b;
}
.llm-input {
  flex: 1; background: #1a2236; border: 1px solid #1e293b; color: #cbd5e1;
  padding: 6px 12px; border-radius: 6px; font-size: 13px; outline: none;
}
.llm-input:focus { border-color: #22c55e; }
.llm-btn {
  background: #22c55e; color: #000; border: none; padding: 6px 14px;
  border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: bold;
}
.llm-btn:hover { background: #4ade80; }
.llm-result { font-size: 12px; color: #94a3b8; }
.llm-result b { color: #22c55e; }
.top-center { display: flex; align-items: center; gap: 10px; }
.attention-score {
  font-size: 12px; color: #94a3b8;
  padding: 2px 8px; background: rgba(148,163,184,0.1); border-radius: 8px;
}
.gaze-indicator {
  display: inline-block;
  min-width: 80px;
  text-align: center;
  padding: 2px 10px;
  background: rgba(34,197,94,0.1);
  border: 1px solid rgba(34,197,94,0.3);
  border-radius: 12px;
  color: #4ade80;
  font-weight: bold;
  font-size: 13px;
}

.main-grid {
  flex: 1; display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 12px; padding: 12px;
}

.panel {
  background: #111827; border: 1px solid #1e293b; border-radius: 8px;
  padding: 16px; overflow: auto;
}
.panel h2 { font-size: 16px; margin-bottom: 10px; color: #94a3b8; }

.placeholder { color: #4b5563; font-size: 14px; margin-top: 20px; text-align: center; }

.gauge-panel { grid-row: 1; grid-column: 1; }
.alert-panel { grid-row: 1; grid-column: 2; }
.ai-panel { grid-row: 1 / 3; grid-column: 3; }
.voice-panel { grid-row: 2; grid-column: 1; }
.nav-panel { grid-row: 2; grid-column: 2; }

.metric { padding: 6px 0; font-size: 14px; border-bottom: 1px solid #1e293b; color: #cbd5e1; }

.alert-active { background: #7f1d1d; border: 1px solid #ef4444; border-radius: 6px; padding: 12px; color: #fca5a5; font-size: 14px; font-weight: bold; }
.alert-ok { background: #14532d; border: 1px solid #22c55e; border-radius: 6px; padding: 12px; color: #86efac; font-size: 14px; }

.decision-log { font-size: 13px; }
.log-item { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #1e293b; }
.log-item .label { color: #64748b; }
.log-item .value { color: #e2e8f0; font-family: monospace; }

.voice-active { background: #1e293b; border-radius: 6px; padding: 12px; color: #facc15; font-size: 18px; text-align: center; }

/* 摄像头浮窗 */
.camera-float {
  position: fixed;
  border: 2px solid #22c55e;
  border-radius: 8px;
  overflow: hidden;
  z-index: 100;
  background: #000;
  box-shadow: 0 0 20px rgba(34, 197, 94, 0.3);
  cursor: move;
  user-select: none;
}
.drag-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 18px;
  background: rgba(0,0,0,0.5);
  color: #64748b;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: move;
  z-index: 2;
  user-select: none;
}
.drag-bar:hover { color: #22c55e; }
.camera-feed {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.camera-label {
  position: absolute;
  top: 4px;
  left: 6px;
  font-size: 10px;
  color: #22c55e;
  font-weight: bold;
  background: rgba(0,0,0,0.6);
  padding: 1px 6px;
  border-radius: 3px;
  pointer-events: none;
}
.minimize-btn {
  position: absolute;
  top: 2px;
  right: 4px;
  width: 20px;
  height: 20px;
  background: rgba(0,0,0,0.6);
  border: 1px solid #22c55e;
  color: #22c55e;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.minimize-btn:hover { background: #22c55e; color: #000; }
.resize-handle {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  background: linear-gradient(135deg, transparent 50%, rgba(34,197,94,0.6) 50%);
}

/* 最小化气泡 */
.camera-bubble {
  position: fixed;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: #111827;
  border: 2px solid #22c55e;
  color: #22c55e;
  font-size: 11px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 100;
  box-shadow: 0 0 12px rgba(34,197,94,0.4);
  user-select: none;
}
.camera-bubble:hover {
  background: #1a2236;
  box-shadow: 0 0 20px rgba(34,197,94,0.6);
}

/* 驾驶鼓励提示 */
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

/* 统计侧栏 */
.stats-sidebar {
  position: fixed;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  z-index: 99;
  display: flex;
}
.stats-sidebar.open .stats-toggle {
  border-radius: 8px 0 0 8px;
}
.stats-toggle {
  width: 28px;
  height: 60px;
  background: #111827;
  border: 1px solid #1e293b;
  border-right: none;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  border-radius: 8px 0 0 8px;
  user-select: none;
}
.stats-toggle:hover { color: #22c55e; background: #1a2236; }
.stats-content {
  background: #111827;
  border: 1px solid #1e293b;
  border-radius: 8px 0 0 8px;
  padding: 16px;
  width: 180px;
}
.stats-content h3 {
  font-size: 14px;
  color: #94a3b8;
  margin-bottom: 10px;
}
.stat-row {
  display: flex;
  justify-content: space-between;
  padding: 5px 0;
  font-size: 13px;
  color: #cbd5e1;
  border-bottom: 1px solid #1e293b;
}
.stat-row span:last-child { color: #22c55e; font-weight: bold; }
.stat-divider { border-top: 1px solid #1e293b; margin: 8px 0; }
.report-btn {
  width: 100%; background: #1a2236; border: 1px solid #22c55e; color: #22c55e;
  padding: 6px; border-radius: 6px; cursor: pointer; font-size: 12px;
}
.report-btn:hover { background: #22c55e; color: #000; }
.report-btn:disabled { opacity: 0.5; cursor: wait; }
.report-text { font-size: 12px; color: #94a3b8; margin-top: 6px; line-height: 1.5; white-space: pre-line; }
.toggle-row { display: flex; justify-content: space-between; align-items: center; }
.toggle-switch { position: relative; display: inline-block; width: 36px; height: 20px; }
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.toggle-slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background: #334155; border-radius: 20px; transition: .2s; }
.toggle-slider::before { content: ''; position: absolute; height: 14px; width: 14px; left: 3px; bottom: 3px; background: #94a3b8; border-radius: 50%; transition: .2s; }
.toggle-switch input:checked + .toggle-slider { background: #22c55e; }
.toggle-switch input:checked + .toggle-slider::before { transform: translateX(16px); background: #fff; }

/* 浅色模式 */
body.light-theme { background: #f1f5f9; color: #1e293b; }
body.light-theme .dashboard { background: #f1f5f9; }
body.light-theme .top-bar { background: #fff; border-color: #e2e8f0; color: #334155; }
body.light-theme .panel { background: #fff; border-color: #e2e8f0; color: #334155; }
body.light-theme .panel h2 { color: #64748b; }
body.light-theme .metric { border-color: #e2e8f0; color: #475569; }
body.light-theme .alert-active { background: #fef2f2; border-color: #ef4444; color: #991b1b; }
body.light-theme .alert-ok { background: #f0fdf4; border-color: #22c55e; color: #166534; }
body.light-theme .placeholder { color: #94a3b8; }
body.light-theme .stats-sidebar .stats-content,
body.light-theme .stats-toggle { background: #fff; border-color: #e2e8f0; color: #334155; }
body.light-theme .stat-row { border-color: #e2e8f0; color: #475569; }
body.light-theme .stat-row span:last-child { color: #16a34a; }
body.light-theme .camera-float { border-color: #22c55e; }
body.light-theme .camera-bubble { background: #fff; }
body.light-theme .gaze-indicator { background: rgba(34,197,94,0.1); color: #16a34a; }
</style>
