<template>
  <section class="panel voice-panel">
    <h2>语音交互</h2>

    <!-- 对话历史 -->
    <div class="voice-history" ref="historyEl">
      <div v-if="messages.length === 0" class="placeholder">点击下方麦克风开始语音交互</div>
      <div v-for="(msg, i) in messages" :key="i" class="voice-msg" :class="msg.role">
        <span class="msg-role">{{ msg.role === 'user' ? '🧑 你' : '🤖 AI' }}</span>
        <span class="msg-text">{{ msg.text }}</span>
      </div>
    </div>

    <!-- 输入栏 -->
    <div class="voice-input-row">
      <input
        v-model="inputText"
        class="voice-input"
        placeholder="输入文字或点麦克风语音..."
        @keyup.enter="sendText"
      />
      <button class="voice-btn mic" @click="startListen" :disabled="listening" title="语音输入">
        {{ listening ? '🎙️' : '🎤' }}
      </button>
      <button class="voice-btn send" @click="sendText" :disabled="!inputText.trim()" title="发送">
        ➤
      </button>
    </div>

    <!-- 状态提示 -->
    <div v-if="errorMsg" class="voice-error">{{ errorMsg }}</div>
  </section>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const props = defineProps({ data: Object })
const emit = defineEmits(['ac-command', 'music-command', 'orchestrator-actions', 'agent-start'])

// ═════════════════════════════════════════════════════════════
//  Channel 1: 快速路由 — 简单指令直通 (<100ms，不经 LLM)
//  替代旧版 detectAcCommand() 150 行正则
// ═════════════════════════════════════════════════════════════

const QUICK_PATTERNS = [
  // 空调 — 开关
  { pattern: /打开空调|开空调|空调打开/, type: 'ac', command: 'TurnOnAC', label: '已开启空调' },
  { pattern: /关闭空调|关掉空调|关空调/, type: 'ac', command: 'TurnOffAC', label: '已关闭空调' },
  // 空调 — 温度快速设定
  { pattern: /太热了|好热|外面好热/, type: 'ac', command: 'set', params: { temperature: 22 }, label: '已调低温度至22度' },
  { pattern: /太冷了|好冷/, type: 'ac', command: 'set', params: { temperature: 26 }, label: '已调高温度至26度' },
  { pattern: /温度调高|调高温度|升高温度/, type: 'ac', command: 'temp_up', label: '温度已调高' },
  { pattern: /温度调低|调低温度|降低温度/, type: 'ac', command: 'temp_down', label: '温度已调低' },
  // 音乐 — 纯控制指令（不涉及搜索）
  { pattern: /暂停|停止播放|停止音乐|关闭音乐/, type: 'music', command: 'StopMusic', label: '已暂停播放' },
  { pattern: /下一首|换一首|切歌|跳过/, type: 'music', command: 'next_track', label: '切换下一首' },
  { pattern: /上一首|上一曲|前一首/, type: 'music', command: 'previous_track', label: '切换上一首' },
  { pattern: /音量.*大|大声|声音大/, type: 'music', command: 'volume_up', label: '音量已调大' },
  { pattern: /音量.*小|小声|声音小/, type: 'music', command: 'volume_down', label: '音量已调小' },
]

function quickRoute(text) {
  // 复合指令检测：含连词或多个控制意图时，不走快速路由，交给 Agent 统一处理
  const COMPOSITE_MARKERS = ['并', '同时', '还有', '然后', '顺便', '再加上', '以及']
  const isComposite = COMPOSITE_MARKERS.some(m => text.includes(m))
  if (isComposite) {
    return null  // 交给 Agent 处理复合指令
  }

  for (const p of QUICK_PATTERNS) {
    if (p.pattern.test(text)) {
      return { type: p.type, command: p.command, params: p.params || {}, label: p.label }
    }
  }
  // 音乐搜索（播放XXX的歌 / 来一首XXX）— 直通搜索 API，不经 LLM
  const music = detectMusicCommand(text)
  if (music && music.command === '_music_search') {
    return { type: 'music_search', keyword: music.keyword, label: music.label }
  }
  return null
}

async function executeQuickAction(action) {
  if (action.type === 'ac') {
    try {
      const body = Object.keys(action.params).length > 0
        ? JSON.stringify({ command: action.command, ...action.params })
        : JSON.stringify({ command: action.command })
      const r = await fetch('/api/ac/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body
      })
      if (r.ok) {
        const data = await r.json()
        messages.value.push({ role: 'ai', text: data.status === 'ok' ? action.label : '指令执行失败' })
      }
    } catch (e) {
      messages.value.push({ role: 'ai', text: '网络错误: ' + e.message })
    }
    emit('ac-command', { command: action.command, params: action.params })
  } else if (action.type === 'music') {
    emit('music-command', action.command)
    messages.value.push({ role: 'ai', text: action.label })
  } else if (action.type === 'music_search') {
    // 直通音乐搜索 API (<200ms)，不经 LLM
    try {
      const r = await fetch('/api/music/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: action.keyword })
      })
      if (r.ok) {
        const data = await r.json()
        const songs = data.songs || []
        if (songs.length > 0) {
          await fetch('/api/music/play', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ song_id: songs[0].id })
          })
          messages.value.push({ role: 'ai', text: `正在播放: ${songs[0].name} - ${songs[0].artist}` })
        } else {
          messages.value.push({ role: 'ai', text: `未搜索到"${action.keyword}"相关歌曲` })
        }
      }
    } catch (e) {
      messages.value.push({ role: 'ai', text: '网络错误: ' + e.message })
    }
  }
  scrollBottom()
}

// ═════════════════════════════════════════════════════════════
//  诊断关键词 — 走 Orchestrator 编排（保留旧路径给诊断/分析类）
// ═════════════════════════════════════════════════════════════

const DIAGNOSIS_KEYWORDS = ['诊断', '分析', '报告', '检查车况', '车辆状态', '油耗', '故障']

function isDiagnosis(text) {
  return DIAGNOSIS_KEYWORDS.some(kw => text.includes(kw))
}

// ═════════════════════════════════════════════════════════════
//  Channel 2: ReAct Agent (复杂指令) / Orchestrator (诊断类)
// ═════════════════════════════════════════════════════════════

// WebSocket 监听：Agent 最终回复通过 WS 先于 HTTP 到达时缓存
let _wsFinalReply = ''
let _wsFinalReady = false
let _ws = null

function connectAgentWS() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const host = location.host || 'localhost:8000'
  try {
    _ws = new WebSocket(`${protocol}://${host}/ws/agent_panel`)
    _ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'agent_final') {
          _wsFinalReply = msg.data?.text || ''
          _wsFinalReady = true
        } else if (msg.type === 'agent_error') {
          _wsFinalReady = true
          _wsFinalReply = ''
        }
      } catch {}
    }
    _ws.onclose = () => { setTimeout(connectAgentWS, 5000) }
    _ws.onerror = () => { _ws?.close() }
  } catch { setTimeout(connectAgentWS, 5000) }
}
connectAgentWS()

async function callAgentChat(text) {
  emit('agent-start')
  _wsFinalReply = ''
  _wsFinalReady = false

  // 超时 60s（行程规划等复杂多工具查询可能需要 30-50s）
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 60000)
  try {
    const resp = await fetch('/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, driver_state: props.data || {} }),
      signal: controller.signal
    })
    clearTimeout(timeoutId)
    const data = await resp.json()
    if (data.status === 'ok') {
      const result = data.result || {}
      messages.value.push({ role: 'ai', text: result.reply_text || '（未收到回复）' })
      scrollBottom()
      return true
    }
    return false
  } catch (e) {
    clearTimeout(timeoutId)
    if (e.name === 'AbortError') {
      // 超时后检查 WebSocket 是否已收到最终回复
      if (_wsFinalReady && _wsFinalReply) {
        console.log('HTTP 超时但 WebSocket 已收到回复，使用 WS 结果')
        messages.value.push({ role: 'ai', text: _wsFinalReply })
        scrollBottom()
        return true
      }
      // WS 也没有结果，等待 5s 再检查一次（Agent 可能刚好完成）
      await new Promise(r => setTimeout(r, 5000))
      if (_wsFinalReady && _wsFinalReply) {
        messages.value.push({ role: 'ai', text: _wsFinalReply })
        scrollBottom()
        return true
      }
      // 超时但面板可能已有部分结果（景点/行程已推送），不显示"抱歉"
      console.warn('Agent 超时 (60s)，检查面板是否已有结果')
      messages.value.push({ role: 'ai', text: '正在处理中，结果请查看右侧面板...' })
      scrollBottom()
      return true  // 不降级到 fallbackLocal，避免覆盖面板已有结果
    }
    return false
  }
}

async function callOrchestrator(text) {
  emit('agent-start')
  _wsFinalReply = ''
  _wsFinalReady = false

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 45000)
  try {
    const resp = await fetch('/api/agent/orchestrate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, driver_state: props.data || {} }),
      signal: controller.signal
    })
    clearTimeout(timeoutId)
    const data = await resp.json()
    if (data.status === 'ok') {
      const result = data.result || {}
      if (result.actions && result.actions.length > 0) {
        emit('orchestrator-actions', result.actions)
      }
      messages.value.push({ role: 'ai', text: result.reply_text || '（未收到回复）' })
      scrollBottom()
      return true
    }
    return false
  } catch (e) {
    clearTimeout(timeoutId)
    if (e.name === 'AbortError') {
      // 超时后检查 WebSocket 是否已收到最终回复
      if (_wsFinalReady && _wsFinalReply) {
        messages.value.push({ role: 'ai', text: _wsFinalReply })
        scrollBottom()
        return true
      }
      await new Promise(r => setTimeout(r, 3000))
      if (_wsFinalReady && _wsFinalReply) {
        messages.value.push({ role: 'ai', text: _wsFinalReply })
        scrollBottom()
        return true
      }
      console.warn('Orchestrator 超时 (45s)，降级到本地规则')
    }
    return false
  }
}

// ═════════════════════════════════════════════════════════════
//  音乐指令检测 — fallbackLocal 降级使用
// ═════════════════════════════════════════════════════════════

function detectMusicCommand(text) {
  let normalized = text
    .replace(/一两|一二/g, '2').replace(/两/g, '2').replace(/二/g, '2')
    .replace(/三/g, '3').replace(/四/g, '4').replace(/五/g, '5')
    .replace(/六/g, '6').replace(/七/g, '7').replace(/八/g, '8')
    .replace(/九/g, '9').replace(/十(\d?)/g, (_, d) => (d ? '1' + d : '10'))

  if (/停止播放|暂停播放|暂停|停播|不要播|关闭音乐|停止音乐/.test(normalized))
    return { command: '_music_stop', label: '已停止播放' }

  const searchMatch = normalized.match(/(?:播放|放|来|听)\s*(?:一首|一个)?\s*(.+?)(?:的|的?歌|的?曲|$)/)
  if (searchMatch) {
    const keyword = searchMatch[1].trim()
    if (keyword && !/^(音乐|歌|歌曲|一下|吧|呢|啊|)$/.test(keyword)) {
      return { command: '_music_search', keyword, label: `搜索: ${keyword}` }
    }
  }

  if (/播放|放歌|来首|放首|听歌/.test(normalized))
    return { command: '_music_play', label: '开始播放音乐' }
  if (/下一首|换一首|切歌|跳过/.test(normalized))
    return { command: '_music_next', label: '切换下一首' }
  if (/上一首|上一曲|前一首/.test(normalized))
    return { command: '_music_prev', label: '切换上一首' }
  if (/音量.*大|大声|声音大/.test(normalized))
    return { command: '_music_vol_up', label: '音量已调大' }
  if (/音量.*小|小声|声音小/.test(normalized))
    return { command: '_music_vol_down', label: '音量已调小' }

  if (/(?:歌|唱|曲|音乐)/.test(normalized))
    return { command: '_music_search', keyword: text, label: `搜索: ${text}` }

  return null
}

// ═════════════════════════════════════════════════════════════
//  主入口 — 三通道路由
//  1. QUICK_PATTERNS → 直通执行 (<100ms)
//  2. /api/agent/chat (ReAct Agent) 或 /api/agent/orchestrate (诊断)
//  3. fallbackLocal (Agent 不可用时降级)
// ═════════════════════════════════════════════════════════════

const messages = ref([])
const inputText = ref('')
const listening = ref(false)
const errorMsg = ref('')
const historyEl = ref(null)

function scrollBottom() {
  nextTick(() => { if (historyEl.value) historyEl.value.scrollTop = historyEl.value.scrollHeight })
}

async function sendText() {
  const text = inputText.value.trim()
  if (!text) return
  inputText.value = ''

  messages.value.push({ role: 'user', text })
  errorMsg.value = ''
  scrollBottom()

  // ── Channel 1: 快速路由 (<100ms，不经 LLM) ──
  const quick = quickRoute(text)
  if (quick) {
    await executeQuickAction(quick)
    return
  }

  // ── Channel 2: ReAct Agent / Orchestrator ──
  try {
    if (isDiagnosis(text)) {
      if (await callOrchestrator(text)) return
    } else {
      if (await callAgentChat(text)) return
    }
  } catch (e) {
    console.warn('Agent 调用失败，降级到本地规则:', e)
  }

  // ── Channel 3: 降级到本地规则 (Agent 不可用时兜底) ──
  await fallbackLocal(text)
  scrollBottom()
}

// 本地规则匹配 — Agent 不可用时的降级方案
async function fallbackLocal(text) {
  const music = detectMusicCommand(text)
  if (music) {
    try {
      if (music.command === '_music_search') {
        const r = await fetch('/api/music/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ keyword: music.keyword })
        })
        if (r.ok) {
          const data = await r.json()
          const songs = data.songs || []
          if (songs.length > 0) {
            const pr = await fetch('/api/music/play', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ song_id: songs[0].id })
            })
            if (pr.ok) {
              messages.value.push({ role: 'ai', text: `正在播放: ${songs[0].name} - ${songs[0].artist}` })
            } else {
              messages.value.push({ role: 'ai', text: '播放失败' })
            }
          } else {
            messages.value.push({ role: 'ai', text: `未搜索到"${music.keyword}"相关歌曲` })
          }
        }
      } else {
        const cmdMap = { '_music_play': 'PlayMusic', '_music_stop': 'StopMusic', '_music_next': 'next_track', '_music_prev': 'previous_track', '_music_vol_up': 'volume_up', '_music_vol_down': 'volume_down' }
        const cmd = cmdMap[music.command]
        if (cmd) emit('music-command', cmd)
        messages.value.push({ role: 'ai', text: music.label })
      }
    } catch (e) {
      messages.value.push({ role: 'ai', text: '网络错误: ' + e.message })
    }
    return
  }

  messages.value.push({ role: 'ai', text: '抱歉，语音服务暂时不可用，请稍后再试。' })
}

// 浏览器语音识别
let recognition = null
let _asrRetryCount = 0
const _ASR_MAX_RETRY = 2

function startListen() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SpeechRecognition) {
    errorMsg.value = '浏览器不支持语音识别，请用文字输入'
    return
  }
  if (!recognition) {
    recognition = new SpeechRecognition()
    recognition.lang = 'zh-CN'
    recognition.interimResults = false
    recognition.continuous = false
    recognition.onresult = (e) => {
      _asrRetryCount = 0
      const text = e.results[0][0].transcript
      inputText.value = text
      listening.value = false
      sendText()
    }
    recognition.onerror = (e) => {
      listening.value = false
      // network 错误：可能是短暂网络波动，自动重试
      if (e.error === 'network' && _asrRetryCount < _ASR_MAX_RETRY) {
        _asrRetryCount++
        errorMsg.value = `语音网络异常，正在重试 (${_asrRetryCount}/${_ASR_MAX_RETRY})...`
        setTimeout(() => {
          try { recognition.start() } catch {}
        }, 1000)
        return
      }
      // no-speech：用户没说话，静默处理
      if (e.error === 'no-speech') {
        errorMsg.value = ''
        return
      }
      // not-allowed：麦克风权限被拒
      if (e.error === 'not-allowed') {
        errorMsg.value = '请允许麦克风权限后重试'
        return
      }
      // 其他错误：友好提示
      const errorMap = {
        'network': '语音识别网络异常，请检查网络后重试',
        'audio-capture': '未检测到麦克风设备',
        'service-not-allowed': '语音服务不可用，请用文字输入',
      }
      errorMsg.value = errorMap[e.error] || `语音识别失败: ${e.error}`
      _asrRetryCount = 0
    }
    recognition.onend = () => { listening.value = false }
  }
  _asrRetryCount = 0
  listening.value = true
  errorMsg.value = ''
  try {
    recognition.start()
  } catch (e) {
    // start() 在已运行时调用会抛异常，静默处理
    listening.value = false
  }
}
</script>

<style scoped>
.voice-panel { display: flex; flex-direction: column; height: 100%; }
.voice-history { flex: 1; overflow-y: auto; padding: 8px; margin-bottom: 8px; min-height: 120px; max-height: 200px; background: #0f172a; border-radius: 6px; }
.placeholder { color: #64748b; font-size: 13px; text-align: center; padding: 20px 0; }
.voice-msg { margin-bottom: 8px; display: flex; gap: 6px; align-items: flex-start; }
.voice-msg.user .msg-role { color: #60a5fa; }
.voice-msg.ai .msg-role { color: #34d399; }
.msg-role { font-size: 12px; white-space: nowrap; min-width: 48px; }
.msg-text { font-size: 13px; color: #cbd5e1; line-height: 1.4; }
.voice-input-row { display: flex; gap: 6px; }
.voice-input { flex: 1; padding: 8px 10px; background: #1e293b; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0; font-size: 13px; outline: none; }
.voice-input:focus { border-color: #3b82f6; }
.voice-btn { padding: 8px 10px; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; background: #1e293b; color: #94a3b8; }
.voice-btn:disabled { opacity: 0.4; cursor: default; }
.voice-btn.send { color: #3b82f6; font-size: 18px; }
.voice-btn.mic:hover { color: #60a5fa; }
.voice-error { margin-top: 6px; font-size: 12px; color: #f87171; }
</style>
