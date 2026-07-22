<template>
  <section class="panel gesture-panel">
    <div class="panel-header">
      <h2 class="panel-title">Gesture Control</h2>
      <span class="status-badge" :class="{ active: currentAction }">{{ currentAction ? 'DETECTED' : 'STANDBY' }}</span>
    </div>

    <div v-if="!gestures.length" class="placeholder">
      <div class="loading-spinner"></div>
      <span>Loading gestures...</span>
    </div>

    <div v-else class="gesture-content">
      <!-- 当前识别到的手势 - 大展示区 -->
      <div class="current-card" :class="{ detected: currentAction }">
        <div class="current-visual">
          <div class="gesture-emoji">{{ getEmoji(currentAction?.gesture) }}</div>
          <div class="pulse-ring" v-if="currentAction"></div>
        </div>
        <div class="current-detail">
          <span class="current-label">{{ currentAction ? getDisplayName(currentAction.gesture) : 'Waiting for gesture' }}</span>
          <span class="current-action">{{ currentAction ? currentAction.action_code : '--' }}</span>
        </div>
      </div>

      <!-- 手势网格 -->
      <div class="section-label">Supported Gestures ({{ gestures.length }})</div>
      <div class="gesture-grid">
        <div v-for="g in gestures" :key="g.gesture" class="gesture-item"
          :class="{ active: currentAction && currentAction.gesture === g.gesture }"
          :title="g.label">
          <span class="gi-emoji">{{ getEmoji(g.gesture) }}</span>
          <div class="gi-text">
            <span class="gi-name">{{ getDisplayName(g.gesture) }}</span>
            <span class="gi-code">{{ g.action_code }}</span>
          </div>
        </div>
      </div>

      <!-- 历史记录 -->
      <div v-if="history.length" class="history-section">
        <div class="section-label">Recent Activity</div>
        <div class="history-list">
          <div v-for="(h, i) in history.slice(0, 5)" :key="i" class="history-item">
            <span class="hi-emoji">{{ getEmoji(h.gesture) }}</span>
            <span class="hi-name">{{ getDisplayName(h.gesture) }}</span>
            <span class="hi-arrow">&rsaquo;</span>
            <span class="hi-action">{{ h.action_code }}</span>
            <span class="hi-time">{{ timeAgo(h.ts) }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

defineProps({ data: Object })

const gestures = ref([])
const currentAction = ref(null)
const history = ref([])

const gestureEmojiMap = {
  open_palm: '🖐️', fist: '✊', thumbs_up: '👍', thumbs_down: '👎',
  index_point: '👆', peace: '✌️', ok_sign: '👌', three_fingers: '🤟',
  four_fingers: '🖖', pinch: '🤏', swipe_left: '👈', swipe_right: '👉',
  palm_up: '🫳', palm_down: '🫱', call_me: '🤙', rock_on: '🤘'
}

const gestureNameMap = {
  open_palm: 'Open Palm', fist: 'Fist', thumbs_up: 'Thumbs Up', thumbs_down: 'Thumbs Down',
  index_point: 'Point', peace: 'Peace', ok_sign: 'OK Sign', three_fingers: 'Three',
  four_fingers: 'Four', pinch: 'Pinch', swipe_left: 'Swipe Left', swipe_right: 'Swipe Right',
  palm_up: 'Palm Up', palm_down: 'Palm Down', call_me: 'Call Me', rock_on: 'Rock On'
}

function getEmoji(gesture) {
  return gestureEmojiMap[gesture] || '❓'
}

function getDisplayName(gesture) {
  return gestureNameMap[gesture] || gesture || '--'
}

// 手势空调指令映射（与 gesture_classifier.py 的 action_code 保持一致）
const AC_GESTURE_MAP = {
  'open_ac': 'TurnOnAC',
  'close_ac': 'TurnOffAC',
  'confirm_ac': 'TurnOnAC',    // ok_sign 确认设定
}

const emit = defineEmits(['ac-command', 'music-command'])

// 手势音乐指令映射（与 gesture_classifier.py 的 action_code 一致）
const MUSIC_GESTURE_MAP = {
  'prev_track': 'previous_track',
  'next_track': 'next_track',
  'volume_up': 'volume_up',
  'volume_down': 'volume_down',
  'zoom_in': 'PlayMusic',    // pinch → play
  'thumbs_up': 'PlayMusic',  // thumbs_up → play
  'thumbs_down': 'StopMusic', // thumbs_down → stop
}

async function loadGestures() {
  try {
    const r = await fetch('http://localhost:8000/api/gesture/available')
    if (r.ok) gestures.value = (await r.json()).gestures || []
  } catch (e) {}
}

let pollTimer = null

async function pollGesture() {
  try {
    const r = await fetch('http://localhost:8000/api/camera/frame')
    if (!r.ok) return
    const gname = r.headers.get('X-Gesture')
    const gaction = r.headers.get('X-GestureAction')
    if (gname) {
      const action = { gesture: gname, action_code: gaction || '', label: gname, icon: gname, ts: Date.now() / 1000 }
      currentAction.value = action
      // 添加到历史（去重，只保留最近5条）
      if (!history.value.length || history.value[0].gesture !== gname) {
        history.value.unshift(action)
        if (history.value.length > 5) history.value.pop()
      }
      // 空调手势指令拦截（用 action_code 匹配）
      const acCmd = AC_GESTURE_MAP[gaction]
      if (acCmd) {
        emit('ac-command', acCmd)
      }
      // 音乐手势指令拦截
      const musicCmd = MUSIC_GESTURE_MAP[gaction]
      if (musicCmd) {
        emit('music-command', musicCmd)
      }
    } else {
      currentAction.value = null
    }
  } catch (e) {}
}

function timeAgo(ts) {
  const s = Math.floor(Date.now() / 1000 - ts)
  if (s < 3) return 'now'
  if (s < 60) return s + 's'
  return Math.floor(s / 60) + 'm'
}

onMounted(() => {
  loadGestures()
  pollTimer = setInterval(pollGesture, 500)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.gesture-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #94a3b8;
  letter-spacing: 0.02em;
}

.status-badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(100, 116, 139, 0.15);
  color: #64748b;
  border: 1px solid rgba(100, 116, 139, 0.2);
  transition: all 0.3s ease;
}

.status-badge.active {
  background: rgba(34, 197, 94, 0.12);
  color: #22c55e;
  border-color: rgba(34, 197, 94, 0.3);
  animation: badge-pulse 2s ease-in-out infinite;
}

@keyframes badge-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #4b5563;
  font-size: 13px;
  padding: 30px 0;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(100, 116, 139, 0.2);
  border-top-color: #22c55e;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.gesture-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
  min-height: 0;
}

/* 当前手势大展示卡片 */
.current-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
  border-radius: 10px;
  border: 1px solid #1e293b;
  transition: all 0.4s ease;
  position: relative;
  overflow: hidden;
}

.current-card.detected {
  border-color: rgba(34, 197, 94, 0.4);
  background: linear-gradient(135deg, #0f172a 0%, #0a1628 100%);
  box-shadow: 0 0 20px rgba(34, 197, 94, 0.08);
}

.current-card.detected::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, #22c55e, transparent);
  animation: scan-line 2s ease-in-out infinite;
}

@keyframes scan-line {
  0% { opacity: 0; transform: translateX(-100%); }
  50% { opacity: 1; }
  100% { opacity: 0; transform: translateX(100%); }
}

.current-visual {
  position: relative;
  flex-shrink: 0;
}

.gesture-emoji {
  font-size: 32px;
  line-height: 1;
  display: block;
  transition: transform 0.3s ease;
}

.current-card.detected .gesture-emoji {
  transform: scale(1.15);
}

.pulse-ring {
  position: absolute;
  inset: -6px;
  border: 2px solid rgba(34, 197, 94, 0.4);
  border-radius: 50%;
  animation: pulse 1.5s ease-out infinite;
}

@keyframes pulse {
  0% { transform: scale(0.8); opacity: 1; }
  100% { transform: scale(1.3); opacity: 0; }
}

.current-detail {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.current-label {
  font-size: 15px;
  font-weight: 700;
  color: #e2e8f0;
  transition: color 0.3s;
}

.current-card.detected .current-label {
  color: #4ade80;
}

.current-action {
  font-size: 11px;
  font-family: 'Consolas', 'Monaco', monospace;
  color: #64748b;
  padding: 1px 6px;
  background: rgba(100, 116, 139, 0.1);
  border-radius: 3px;
  width: fit-content;
}

/* 分区标签 */
.section-label {
  font-size: 10px;
  font-weight: 600;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding-top: 4px;
}

/* 手势网格 */
.gesture-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #1e293b transparent;
}

.gesture-grid::-webkit-scrollbar {
  width: 4px;
}

.gesture-grid::-webkit-scrollbar-thumb {
  background: #1e293b;
  border-radius: 2px;
}

.gesture-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid transparent;
  transition: all 0.2s ease;
  cursor: default;
}

.gesture-item:hover {
  background: rgba(30, 41, 59, 0.6);
}

.gesture-item.active {
  background: rgba(34, 197, 94, 0.08);
  border-color: rgba(34, 197, 94, 0.25);
}

.gi-emoji {
  font-size: 16px;
  flex-shrink: 0;
  width: 24px;
  text-align: center;
}

.gi-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.gi-name {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gesture-item.active .gi-name {
  color: #4ade80;
}

.gi-code {
  font-size: 9px;
  font-family: 'Consolas', 'Monaco', monospace;
  color: #475569;
}

/* 历史记录 */
.history-section {
  flex: 1;
  min-height: 0;
  border-top: 1px solid #1e293b;
  padding-top: 8px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 120px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 5px;
  background: rgba(15, 23, 42, 0.5);
  font-size: 11px;
  animation: fade-in 0.3s ease;
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.hi-emoji {
  font-size: 13px;
  flex-shrink: 0;
}

.hi-name {
  color: #cbd5e1;
  font-weight: 500;
}

.hi-arrow {
  color: #475569;
  font-size: 14px;
}

.hi-action {
  color: #22c55e;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 10px;
}

.hi-time {
  color: #475569;
  margin-left: auto;
  font-size: 10px;
}
</style>
