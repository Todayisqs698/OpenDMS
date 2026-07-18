<template>
  <div class="voice-interaction-bar" :class="{ offline: !online }">
    <!-- 离线提示 -->
    <div v-if="!online" class="offline-banner">
      <el-icon><WarningFilled /></el-icon>
      <span>网络不可用，语音交互已暂停</span>
    </div>

    <!-- 语音识别文本展示区 -->
    <div class="speech-display" :class="{ active: isListening }">
      <div v-if="isListening" class="listening-indicator">
        <span class="pulse-dot"></span>
        <span>正在聆听...</span>
      </div>
      <div v-if="transcript" class="transcript-text">
        <el-icon><Microphone /></el-icon>
        <span>{{ transcript }}</span>
      </div>
      <div v-if="!transcript && !isListening" class="placeholder-text">
        点击麦克风按钮开始语音交互
      </div>
    </div>

    <!-- AI 回复展示区 -->
    <div v-if="aiReply" class="ai-reply-area" :class="{ warning: replyWarning }">
      <div class="reply-header">
        <el-icon><Cpu /></el-icon>
        <span>AI 回复</span>
        <button
          v-if="canSpeak"
          class="speak-btn"
          :class="{ speaking: isSpeaking }"
          @click="toggleSpeech"
          :title="isSpeaking ? '停止播报' : '语音播报'"
        >
          <el-icon><component :is="isSpeaking ? Mute : Microphone" /></el-icon>
        </button>
      </div>
      <p class="reply-content">{{ aiReply }}</p>
    </div>

    <!-- ── 操作区域 ── -->
    <div class="action-area">
      <!-- 麦克风按钮 -->
      <button
        class="mic-btn"
        :class="{ recording: isListening, disabled: !online }"
        :disabled="!online"
        @click="toggleRecording"
        :title="isListening ? '停止录音' : '开始录音'"
      >
        <el-icon :size="22">
          <component :is="isListening ? Mute : Microphone" />
        </el-icon>
      </button>

      <!-- 输入框 -->
      <el-input
        v-model="textInput"
        placeholder="输入文字指令..."
        :disabled="!online"
        class="text-input"
        @keyup.enter="sendText"
      >
        <template #suffix>
          <el-icon v-if="textInput" class="clear-icon" @click="textInput = ''">
            <CircleClose />
          </el-icon>
        </template>
      </el-input>

      <!-- 发送按钮 -->
      <button
        class="send-btn"
        :disabled="!textInput.trim() || !online || sending"
        @click="sendText"
      >
        <el-icon><Promotion /></el-icon>
      </button>
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMsg" class="error-toast">
      <span>{{ errorMsg }}</span>
      <el-icon class="close-toast" @click="errorMsg = ''"><Close /></el-icon>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted, watch } from 'vue'
import {
  Microphone, Mute, Promotion, WarningFilled, Cpu, CircleClose, Close,
} from '@element-plus/icons-vue'

// ── Emits ──
const emit = defineEmits<{
  (e: 'result', data: Record<string, any>): void
  (e: 'loading', val: boolean): void
  (e: 'error', msg: string): void
}>()

// ── 状态 ──
const online = ref(navigator.onLine)
const isListening = ref(false)
const transcript = ref('')
const textInput = ref('')
const aiReply = ref('')
const replyWarning = ref(false)
const errorMsg = ref('')
const sending = ref(false)
const isSpeaking = ref(false)
const canSpeak = ref('speechSynthesis' in window)

// Web Speech API 实例
let recognition: any = null
let speechUtterance: SpeechSynthesisUtterance | null = null

// ── 网络状态监听 ──
window.addEventListener('online', () => { online.value = true })
window.addEventListener('offline', () => {
  online.value = false
  if (isListening.value) stopRecording()
})

// ── 语音识别 ──

function toggleRecording() {
  if (!online.value) {
    errorMsg.value = '网络不可用，无法使用语音识别'
    return
  }
  if (isListening.value) {
    stopRecording()
  } else {
    startRecording()
  }
}

function startRecording() {
  // 检查浏览器支持
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SpeechRecognition) {
    errorMsg.value = '您的浏览器不支持语音识别，请使用 Chrome 浏览器'
    return
  }

  recognition = new SpeechRecognition()
  recognition.continuous = false         // 单次识别
  recognition.interimResults = true      // 实时中间结果
  recognition.lang = 'zh-CN'             // 中文识别

  recognition.onstart = () => {
    isListening.value = true
    transcript.value = ''
    aiReply.value = ''
    replyWarning.value = false
  }

  recognition.onresult = (event: any) => {
    let interim = ''
    let final = ''
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i]
      if (result.isFinal) {
        final += result[0].transcript
      } else {
        interim += result[0].transcript
      }
    }
    transcript.value = final || interim

    // 最终结果自动发送
    if (final) {
      sendToBackend(final.trim())
    }
  }

  recognition.onerror = (event: any) => {
    isListening.value = false
    if (event.error === 'not-allowed') {
      errorMsg.value = '麦克风权限被拒绝，请在浏览器设置中允许麦克风访问'
    } else if (event.error === 'no-speech') {
      // 无声，正常情况，不做提示
    } else {
      errorMsg.value = `语音识别失败: ${event.error}`
    }
  }

  recognition.onend = () => {
    isListening.value = false
    // 如果还有未发送的中间结果
    if (transcript.value && transcript.value.trim()) {
      sendToBackend(transcript.value.trim())
    }
  }

  try {
    recognition.start()
  } catch {
    errorMsg.value = '语音识别启动失败，请刷新页面重试'
    isListening.value = false
  }
}

function stopRecording() {
  if (recognition) {
    try {
      recognition.stop()
    } catch {
      // 忽略
    }
  }
  isListening.value = false
}

// ── 文字发送 ──

async function sendText() {
  const text = textInput.value.trim()
  if (!text || !online.value || sending.value) return

  sendToBackend(text)
  textInput.value = ''
}

async function sendToBackend(text: string) {
  if (!text || sending.value) return

  sending.value = true
  emit('loading', true)
  errorMsg.value = ''

  try {
    const resp = await fetch('http://localhost:8000/api/interaction/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text,
        gesture: '',
        gesture_confidence: 0,
        driver_risk: 'safe',
        driver_fatigue: false,
        driver_distracted: false,
      }),
    })

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}))
      throw new Error(errData.detail || `服务器错误 (${resp.status})`)
    }

    const data = await resp.json()
    const result = data.result || {}

    aiReply.value = result.reply_text || ''
    replyWarning.value = !result.allow_execute

    if (!result.allow_execute && result.warning_msg) {
      aiReply.value = result.warning_msg
    }

    // 向父组件发射结果
    emit('result', result)

    // 自动语音播报（仅在安全状态时）
    if (result.allow_execute && result.reply_text) {
      autoSpeak(result.reply_text)
    } else if (!result.allow_execute && result.warning_msg) {
      autoSpeak(result.warning_msg)
    }

  } catch (e: any) {
    const msg = e.message || '网络请求失败'
    errorMsg.value = msg
    emit('error', msg)
    aiReply.value = ''

    // 离线降级：用本地规则
    handleOfflineFallback(text)
  } finally {
    sending.value = false
    emit('loading', false)
  }
}

// ── 离线降级 ──

function handleOfflineFallback(text: string) {
  // 本地关键词匹配
  const rules: Record<string, string> = {
    '空调': '空调控制：请说「打开空调」启动',
    '音乐': '影音娱乐：请说「播放音乐」',
    '导航': '导航：请说「导航到 + 目的地」',
    '胎压': '胎压标准：前轮2.3-2.5 bar，后轮2.2-2.4 bar',
    '故障': '故障查询需联网，请查阅车辆说明书',
  }
  for (const [kw, reply] of Object.entries(rules)) {
    if (text.includes(kw)) {
      aiReply.value = `[离线] ${reply}`
      return
    }
  }
  aiReply.value = '[离线] 当前无网络连接，部分功能不可用'
}

// ── 语音播报 (TTS) ──

function toggleSpeech() {
  if (isSpeaking.value) {
    stopSpeech()
  } else if (aiReply.value) {
    speakText(aiReply.value)
  }
}

function autoSpeak(text: string) {
  if (!canSpeak.value) return
  // 短文本自动播报
  if (text.length <= 100) {
    speakText(text)
  }
}

function speakText(text: string) {
  if (!canSpeak.value || !text) return

  // 停止当前播报
  stopSpeech()

  speechUtterance = new SpeechSynthesisUtterance(text)
  speechUtterance.lang = 'zh-CN'
  speechUtterance.rate = 1.0
  speechUtterance.pitch = 1.0

  speechUtterance.onstart = () => { isSpeaking.value = true }
  speechUtterance.onend = () => { isSpeaking.value = false }
  speechUtterance.onerror = () => { isSpeaking.value = false }

  window.speechSynthesis.speak(speechUtterance)
}

function stopSpeech() {
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel()
  }
  isSpeaking.value = false
}

// ── 生命周期 ──

onUnmounted(() => {
  stopRecording()
  stopSpeech()
})
</script>

<style scoped>
.voice-interaction-bar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  background: #111827;
  border: 1px solid #1e293b;
  border-radius: 8px;
}
.voice-interaction-bar.offline {
  opacity: 0.8;
}

/* 离线横幅 */
.offline-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #7f1d1d;
  border-radius: 6px;
  color: #fca5a5;
  font-size: 13px;
}

/* 语音展示区 */
.speech-display {
  padding: 12px;
  background: #1a2332;
  border-radius: 6px;
  min-height: 48px;
  display: flex;
  align-items: center;
}
.speech-display.active {
  border: 1px solid #facc15;
}
.listening-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #facc15;
  font-size: 14px;
}
.pulse-dot {
  width: 8px;
  height: 8px;
  background: #ef4444;
  border-radius: 50%;
  animation: pulse-anim 1.2s infinite;
}
@keyframes pulse-anim {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.3); }
}
.transcript-text {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #e2e8f0;
  font-size: 15px;
}
.placeholder-text {
  color: #4b5563;
  font-size: 13px;
}

/* AI 回复区 */
.ai-reply-area {
  padding: 10px 12px;
  background: #0f172a;
  border-radius: 6px;
  border: 1px solid #1e3a5f;
}
.ai-reply-area.warning {
  border-color: #ef4444;
  background: rgba(127, 29, 29, 0.3);
}
.reply-header {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #64748b;
  font-size: 12px;
  margin-bottom: 6px;
}
.speak-btn {
  margin-left: auto;
  background: transparent;
  border: 1px solid #1e3a5f;
  color: #38bdf8;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  padding: 0;
}
.speak-btn.speaking {
  background: #38bdf8;
  color: #0f172a;
}
.speak-btn:hover { border-color: #38bdf8; }
.reply-content {
  margin: 0;
  font-size: 13px;
  color: #cbd5e1;
  line-height: 1.5;
}

/* 操作区域 */
.action-area {
  display: flex;
  align-items: center;
  gap: 10px;
}
.mic-btn {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 2px solid #1e3a5f;
  background: #1a2332;
  color: #38bdf8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}
.mic-btn:hover { border-color: #38bdf8; background: #1e3a5f; }
.mic-btn.recording {
  background: #ef4444;
  border-color: #ef4444;
  color: #fff;
  animation: mic-pulse 1.2s infinite;
}
.mic-btn.disabled { opacity: 0.4; cursor: not-allowed; }
@keyframes mic-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
}

.text-input {
  flex: 1;
}
.text-input :deep(.el-input__wrapper) {
  background: #1a2332;
  border-color: #1e3a5f;
  box-shadow: none;
}
.text-input :deep(.el-input__inner) {
  color: #e2e8f0;
}
.text-input :deep(.el-input__inner::placeholder) {
  color: #4b5563;
}
.clear-icon { color: #64748b; cursor: pointer; }

.send-btn {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  border: none;
  background: #2563eb;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.2s;
}
.send-btn:hover { background: #1d4ed8; }
.send-btn:disabled { background: #1e3a5f; color: #4b5563; cursor: not-allowed; }

/* 错误提示 */
.error-toast {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #7f1d1d;
  border-radius: 6px;
  color: #fca5a5;
  font-size: 12px;
}
.close-toast { cursor: pointer; }
</style>
