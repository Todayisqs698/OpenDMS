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

defineProps({ data: Object })

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

  try {
    const resp = await fetch('http://localhost:8000/api/interaction/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, driver_risk: 'safe', driver_fatigue: false, driver_distracted: false })
    })
    const data = await resp.json()
    const result = data.result || {}
    const reply = result.reply_text || '（未收到回复）'
    messages.value.push({ role: 'ai', text: reply })
  } catch (e) {
    errorMsg.value = '请求失败: ' + e.message
  }
  scrollBottom()
}

// 浏览器语音识别
let recognition = null
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
      const text = e.results[0][0].transcript
      inputText.value = text
      listening.value = false
      sendText()
    }
    recognition.onerror = (e) => {
      errorMsg.value = '语音识别失败: ' + e.error
      listening.value = false
    }
    recognition.onend = () => { listening.value = false }
  }
  listening.value = true
  errorMsg.value = ''
  recognition.start()
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
