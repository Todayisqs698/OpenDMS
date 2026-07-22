<template>
  <section class="panel agent-panel">
    <div class="panel-header">
      <h2 class="panel-title">Agent Thinking</h2>
      <span class="agent-badge" :class="status">{{ status }}</span>
    </div>

    <div class="agent-body">
      <!-- 思维链 -->
      <div v-if="steps.length" class="agent-steps">
        <div v-for="(step, i) in steps" :key="i" class="agent-step" :class="step.type">
          <div class="step-header">
            <span class="step-icon">{{ stepIcon(step.type) }}</span>
            <span class="step-label">{{ stepLabel(step.type) }}</span>
            <span class="step-time">{{ step.time }}</span>
          </div>
          <div class="step-content">
            <template v-if="step.type === 'think'">{{ step.thought }}</template>
            <template v-if="step.type === 'tool_call'">
              <span class="tool-name">{{ step.tool }}</span>
              <span class="tool-args">{{ formatArgs(step.args) }}</span>
            </template>
            <template v-if="step.type === 'tool_result'">
              <span class="tool-name">{{ step.tool }}</span>
              <span class="tool-result" :class="{ truncated: !isExpanded(i) && step.result.length > 80 }">
                {{ isExpanded(i) ? step.result : truncate(step.result, 80) }}
              </span>
              <button v-if="step.result.length > 80" class="expand-btn" @click="toggleExpand(i)">
                {{ isExpanded(i) ? '收起' : '展开' }}
              </button>
            </template>
            <template v-if="step.type === 'final'">{{ step.text }}</template>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else class="agent-empty">Agent 等待指令...</div>

      <!-- 安全等级指示 -->
      <div v-if="safetyLevel && safetyLevel !== 'normal'" class="safety-indicator" :class="safetyLevel">
        <span class="safety-icon">{{ safetyLevel === 'dangerous' ? '🚨' : '⚠️' }}</span>
        <span class="safety-text">{{ safetyText }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const steps = ref([])
const safetyLevel = ref('normal')
const status = ref('idle')  // idle / thinking / acting / done / error
const expandedSteps = ref(new Set())  // 折叠状态：已展开的 step index
let ws = null
let reconnectTimer = null

const statusText = computed(() => {
  const map = { idle: 'IDLE', thinking: 'THINKING', acting: 'ACTING', done: 'DONE', error: 'ERROR' }
  return map[status.value] || 'IDLE'
})

const safetyText = computed(() => {
  const map = {
    normal: '',
    attn_declining: '注意力下降',
    distracted: '分心状态 - 部分功能受限',
    dangerous: '危险状态 - 仅安全功能可用',
  }
  return map[safetyLevel.value] || ''
})

function stepIcon(type) {
  const map = { think: '💭', tool_call: '🔧', tool_result: '📋', final: '✅', error: '❌' }
  return map[type] || '💬'
}

function stepLabel(type) {
  const map = { think: '思考', tool_call: '调用工具', tool_result: '工具返回', final: '最终回复', error: '错误' }
  return map[type] || type
}

function formatArgs(args) {
  try {
    return typeof args === 'string' ? args : JSON.stringify(args)
  } catch { return String(args) }
}

function truncate(text, maxLen) {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

function isExpanded(index) {
  return expandedSteps.value.has(index)
}

function toggleExpand(index) {
  const next = new Set(expandedSteps.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  expandedSteps.value = next
}

function addStep(step) {
  step.time = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  steps.value.push(step)
  // 限制最多显示 20 步
  if (steps.value.length > 20) steps.value.shift()
}

function clearSteps() {
  steps.value = []
  expandedSteps.value = new Set()
  status.value = 'idle'
}

function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const host = location.host || 'localhost:8000'
  try {
    ws = new WebSocket(`${protocol}://${host}/ws/agent_panel`)
    ws.onopen = () => { console.log('Agent WS connected') }
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'agent_think') {
          status.value = 'thinking'
          addStep({ type: 'think', thought: msg.data.thought })
        } else if (msg.type === 'agent_tool_call') {
          status.value = 'acting'
          addStep({ type: 'tool_call', tool: msg.data.tool, args: msg.data.args })
        } else if (msg.type === 'agent_tool_result') {
          addStep({ type: 'tool_result', tool: msg.data.tool, result: msg.data.result })
        } else if (msg.type === 'agent_final') {
          status.value = 'done'
          addStep({ type: 'final', text: msg.data.text })
        } else if (msg.type === 'agent_error') {
          status.value = 'error'
          addStep({ type: 'error', text: msg.data.message })
        }
      } catch (err) {}
    }
    ws.onclose = () => {
      reconnectTimer = setTimeout(connectWS, 5000)
    }
    ws.onerror = () => { ws.close() }
  } catch (e) {
    reconnectTimer = setTimeout(connectWS, 5000)
  }
}

// 暴露方法给父组件（VoicePanel 发送 Agent 请求时调用）
defineExpose({
  setSafetyLevel(level) { safetyLevel.value = level },
  clearSteps,
  setThinking() { status.value = 'thinking' },
  setDone() { status.value = 'done' },
})

onMounted(() => { connectWS() })
onUnmounted(() => {
  if (ws) ws.close()
  if (reconnectTimer) clearTimeout(reconnectTimer)
})
</script>

<style scoped>
.agent-panel { display: flex; flex-direction: column; gap: 8px; }
.panel-header { display: flex; align-items: center; justify-content: space-between; }
.panel-title { margin: 0; font-size: 14px; font-weight: 600; color: #94a3b8; letter-spacing: 0.02em; }

.agent-badge {
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
  padding: 2px 8px; border-radius: 4px;
  background: rgba(100,116,139,0.15); color: #64748b;
  border: 1px solid rgba(100,116,139,0.2); transition: all 0.3s;
}
.agent-badge.thinking { background: rgba(251,191,36,0.12); color: #fbbf24; border-color: rgba(251,191,36,0.3); }
.agent-badge.acting { background: rgba(96,165,250,0.12); color: #60a5fa; border-color: rgba(96,165,250,0.3); }
.agent-badge.done { background: rgba(34,197,94,0.12); color: #22c55e; border-color: rgba(34,197,94,0.3); }
.agent-badge.error { background: rgba(239,68,68,0.12); color: #ef4444; border-color: rgba(239,68,68,0.3); }

.agent-body { display: flex; flex-direction: column; gap: 8px; }
.agent-steps { max-height: 300px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #1e293b transparent; }

.agent-step {
  padding: 8px 10px; border-radius: 6px; border-left: 3px solid #334155;
  background: #0f172a; margin-bottom: 4px;
  animation: stepIn 0.2s ease-out;
}
@keyframes stepIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }

.agent-step.think { border-left-color: #fbbf24; }
.agent-step.tool_call { border-left-color: #60a5fa; }
.agent-step.tool_result { border-left-color: #34d399; }
.agent-step.final { border-left-color: #22c55e; background: rgba(34,197,94,0.04); }
.agent-step.error { border-left-color: #ef4444; }

.step-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.step-icon { font-size: 14px; }
.step-label { font-size: 11px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
.step-time { font-size: 10px; color: #475569; margin-left: auto; font-family: monospace; }
.step-content { font-size: 12px; color: #cbd5e1; line-height: 1.5; padding-left: 22px; word-break: break-word; }
.tool-name { color: #60a5fa; font-weight: 600; }
.tool-args { color: #64748b; }
.tool-result { color: #34d399; }
.tool-result.truncated { color: #64748b; }
.expand-btn {
  margin-left: 6px; padding: 0 4px; font-size: 10px; font-weight: 600;
  color: #60a5fa; background: none; border: 1px solid rgba(96,165,250,0.3);
  border-radius: 3px; cursor: pointer; transition: all 0.2s;
}
.expand-btn:hover { background: rgba(96,165,250,0.1); }

.agent-empty { color: #475569; font-size: 13px; text-align: center; padding: 30px 0; }

.safety-indicator {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  border-radius: 6px; font-size: 12px;
}
.safety-indicator.attn_declining { background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.2); color: #fbbf24; }
.safety-indicator.distracted { background: rgba(249,115,22,0.08); border: 1px solid rgba(249,115,22,0.2); color: #f97316; }
.safety-indicator.dangerous { background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.2); color: #ef4444; }
.safety-icon { font-size: 16px; }
.safety-text { font-weight: 600; }
</style>
