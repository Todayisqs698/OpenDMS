<template>
  <section class="panel ai-decision-panel">
    <!-- 标题栏 -->
    <h2>
      AI 决策链路
      <span class="status-badge" :class="wsConnected ? 'connected' : 'disconnected'">
        {{ wsConnected ? '实时' : '离线' }}
      </span>
    </h2>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-block">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>AI 引擎处理中...</span>
    </div>

    <!-- 报错提示 -->
    <div v-if="errorMsg" class="error-block">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ errorMsg }}</span>
      <button class="retry-btn" @click="clearError">关闭</button>
    </div>

    <!-- ── 当前决策摘要 ── -->
    <div v-if="lastResult" class="decision-card">
      <div class="card-header">
        <span class="card-label">当前决策</span>
        <el-tag
          :type="intentTagType"
          size="small"
          effect="dark"
        >
          {{ intentLabel }}
        </el-tag>
      </div>

      <!-- 意图可视化 -->
      <div class="intent-row">
        <div class="intent-item">
          <span class="intent-key">意图类型</span>
          <span class="intent-value">{{ intentTypeText }}</span>
        </div>
        <div class="intent-item">
          <span class="intent-key">驾驶员状态</span>
          <el-tag :type="riskTagType" size="small">{{ driverRiskText }}</el-tag>
        </div>
        <div class="intent-item">
          <span class="intent-key">执行许可</span>
          <el-tag
            :type="lastResult.allow_execute ? 'success' : 'danger'"
            size="small"
          >
            {{ lastResult.allow_execute ? '允许' : '禁止' }}
          </el-tag>
        </div>
      </div>

      <!-- 动作码 & 回复文本 -->
      <div class="action-row">
        <span class="intent-key">动作码</span>
        <code class="action-code">{{ lastResult.action_code }}</code>
      </div>
      <div v-if="lastResult.reply_text" class="reply-text">
        <el-icon><ChatDotRound /></el-icon>
        <span>{{ lastResult.reply_text }}</span>
      </div>

      <!-- 安全告警 -->
      <div v-if="!lastResult.allow_execute && lastResult.warning_msg" class="safety-alert">
        <el-icon><Warning /></el-icon>
        <div>
          <strong>安全拦截</strong>
          <p>{{ lastResult.warning_msg }}</p>
        </div>
      </div>
    </div>

    <!-- ── RAG 知识库引用 ── -->
    <div v-if="knowledgeDocs.length > 0" class="knowledge-section">
      <h3>
        <el-icon><Document /></el-icon>
        知识库引用
      </h3>
      <div
        v-for="(doc, i) in knowledgeDocs"
        :key="i"
        class="knowledge-item"
      >
        <div class="knowledge-header">
          <el-tag size="small" type="info">{{ doc.source }}</el-tag>
          <span class="knowledge-score">
            相似度 {{ (doc.score * 100).toFixed(0) }}%
          </span>
        </div>
        <p class="knowledge-content">{{ truncateText(doc.content, 200) }}</p>
      </div>
    </div>

    <!-- ── 历史交互记录 ── -->
    <div v-if="history.length > 0" class="history-section">
      <h3>
        <el-icon><Clock /></el-icon>
        交互历史
        <span class="history-count">{{ history.length }} 条</span>
      </h3>
      <div class="history-list">
        <div
          v-for="(item, i) in history"
          :key="i"
          class="history-item"
          :class="{ blocked: !item.allow_execute }"
        >
          <div class="history-header">
            <el-tag
              :type="getIntentTagType(item.intent_type)"
              size="small"
            >
              {{ getIntentLabel(item.intent_type) }}
            </el-tag>
            <span class="history-source">{{ item.source || '' }}</span>
            <span class="history-time">{{ item.time || '' }}</span>
          </div>
          <div class="history-body">
            <span class="history-query">{{ item.query || item.reply_text }}</span>
            <code class="history-action">{{ item.action_code }}</code>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!lastResult && !loading && !errorMsg && history.length === 0" class="empty-state">
      <el-icon :size="40"><Cpu /></el-icon>
      <p>等待语音或手势输入...</p>
      <p class="sub-text">点击下方麦克风按钮开始交互</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import {
  Loading, WarningFilled, Warning, ChatDotRound,
  Document, Clock, Cpu,
} from '@element-plus/icons-vue'

// ── Props ──
const props = defineProps<{
  decision?: Record<string, any> | null
}>()

// ── 内部状态 ──
const wsConnected = ref(false)
const loading = ref(false)
const errorMsg = ref('')
const lastResult = ref<Record<string, any> | null>(null)
const knowledgeDocs = ref<any[]>([])
const history = ref<any[]>([])

let ws: WebSocket | null = null
let reconnectTimer: number | null = null
let loadingTimer: number | null = null

// ── 计算属性 ──

const intentTypeText = computed(() => {
  const types: Record<string, string> = {
    fault: '故障咨询', control: '功能控制', entertain: '影音娱乐', unknown: '未识别'
  }
  return types[lastResult.value?.intent_type] || '未知'
})

const intentLabel = computed(() => intentTypeText.value)

const intentTagType = computed(() => {
  const types: Record<string, string> = {
    fault: 'warning', control: 'primary', entertain: 'success', unknown: 'info'
  }
  return types[lastResult.value?.intent_type] || 'info'
})

const driverRiskText = computed(() => {
  const texts: Record<string, string> = {
    safe: '安全', distract: '分心', fatigue: '疲劳'
  }
  return texts[lastResult.value?.driver_risk] || '未知'
})

const riskTagType = computed(() => {
  const types: Record<string, string> = {
    safe: 'success', distract: 'warning', fatigue: 'danger'
  }
  return types[lastResult.value?.driver_risk] || 'info'
})

// ── 方法 ──

function truncateText(text: string, maxLen: number): string {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

function getIntentLabel(type: string): string {
  const labels: Record<string, string> = {
    fault: '故障咨询', control: '功能控制', entertain: '影音娱乐', unknown: '未识别'
  }
  return labels[type] || type
}

function getIntentTagType(type: string): string {
  const types: Record<string, string> = {
    fault: 'warning', control: '', entertain: 'success', unknown: 'info'
  }
  return types[type] || 'info'
}

function clearError() {
  errorMsg.value = ''
}

function addToHistory(result: Record<string, any>) {
  const now = new Date().toLocaleTimeString('zh-CN')
  history.value.unshift({
    ...result,
    time: now,
    source: result.source || 'speech',
  })
  // 最多保存 50 条
  if (history.value.length > 50) {
    history.value.pop()
  }
}

function handleInteractionResult(data: Record<string, any>) {
  loading.value = false
  if (loadingTimer) {
    clearTimeout(loadingTimer)
    loadingTimer = null
  }
  lastResult.value = data
  knowledgeDocs.value = data.knowledge_ref || []
  addToHistory(data)
}

// ── WebSocket 连接 ──

function connectWS() {
  if (ws && ws.readyState === WebSocket.OPEN) return

  try {
    ws = new WebSocket('ws://localhost:8000/ws/driver_interact')

    ws.onopen = () => {
      wsConnected.value = true
      errorMsg.value = ''
    }

    ws.onclose = () => {
      wsConnected.value = false
      scheduleReconnect()
    }

    ws.onerror = () => {
      wsConnected.value = false
      errorMsg.value = 'WebSocket 连接异常，AI 决策数据可能延迟'
    }

    ws.onmessage = (e: MessageEvent) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'interaction_result') {
          handleInteractionResult(msg.data)
        } else if (msg.type === 'knowledge_result') {
          knowledgeDocs.value = msg.data?.docs || []
        } else if (msg.type === 'driver_state') {
          // 同步驾驶员状态
        } else if (msg.type === 'ai_decision') {
          // 全局 AI 决策
        } else if (msg.type === 'error') {
          errorMsg.value = msg.message || '系统异常'
        }
      } catch {
        // 忽略解析错误
      }
    }
  } catch {
    scheduleReconnect()
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    connectWS()
  }, 3000)
}

// ── 监听 props.decision 变化（兼容旧 DashboardView 传参）──

watch(() => props.decision, (val) => {
  if (val && val.action_code) {
    handleInteractionResult({
      intent_type: val.intent_type || 'unknown',
      driver_risk: val.risk_level || 'safe',
      allow_execute: true,
      action_code: val.action_code,
      reply_text: val.recommendation_text || '',
      knowledge_ref: val.knowledge_ref || [],
      warning_msg: val.warning_msg || '',
      source: val.source || '',
    })
  }
}, { immediate: true })

// ── 生命周期 ──

onMounted(() => {
  connectWS()
})

onUnmounted(() => {
  if (ws) ws.close()
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (loadingTimer) clearTimeout(loadingTimer)
})

// ── 暴露方法供父组件调用 ──

defineExpose({
  setLoading(val: boolean) {
    loading.value = val
    if (val) {
      loadingTimer = window.setTimeout(() => {
        loading.value = false
      }, 10000)
    }
  },
  showError(msg: string) {
    errorMsg.value = msg
  },
})
</script>

<style scoped>
.ai-decision-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  max-height: 100%;
}

h2 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 16px;
  margin: 0 0 4px;
  color: #94a3b8;
  flex-shrink: 0;
}

h3 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #94a3b8;
  margin: 0 0 8px;
}

.status-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: normal;
}
.status-badge.connected { background: #14532d; color: #86efac; }
.status-badge.disconnected { background: #7f1d1d; color: #fca5a5; }

/* 加载/报错 */
.loading-block, .error-block {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
  flex-shrink: 0;
}
.loading-block { background: #1e293b; color: #94a3b8; }
.error-block { background: #7f1d1d; color: #fca5a5; }
.retry-btn { margin-left: auto; background: transparent; border: 1px solid #fca5a5; color: #fca5a5; padding: 2px 8px; border-radius: 4px; cursor: pointer; font-size: 12px; }

/* 决策卡片 */
.decision-card {
  background: #1a2332;
  border: 1px solid #1e3a5f;
  border-radius: 8px;
  padding: 12px;
  flex-shrink: 0;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.card-label { font-size: 13px; color: #64748b; }

.intent-row {
  display: flex;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.intent-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 80px;
}
.intent-key { font-size: 11px; color: #64748b; }
.intent-value { font-size: 13px; color: #e2e8f0; font-weight: 500; }

.action-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.action-code {
  background: #0f172a;
  color: #38bdf8;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 13px;
}

.reply-text {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px;
  background: #0f172a;
  border-radius: 6px;
  font-size: 13px;
  color: #cbd5e1;
  line-height: 1.5;
}

/* 安全告警 */
.safety-alert {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  padding: 10px;
  background: #7f1d1d;
  border: 1px solid #ef4444;
  border-radius: 6px;
  color: #fca5a5;
  font-size: 13px;
  animation: pulse 2s infinite;
}
.safety-alert strong { display: block; margin-bottom: 4px; }
.safety-alert p { margin: 0; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.85; }
}

/* 知识库引用 */
.knowledge-section {
  flex-shrink: 0;
}
.knowledge-item {
  background: #1a2332;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 6px;
}
.knowledge-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.knowledge-score { font-size: 11px; color: #64748b; }
.knowledge-content {
  font-size: 12px;
  color: #94a3b8;
  margin: 0;
  line-height: 1.5;
}

/* 历史记录 */
.history-section {
  flex: 1;
  min-height: 0;
}
.history-count { font-size: 11px; color: #64748b; font-weight: normal; }
.history-list {
  max-height: 240px;
  overflow-y: auto;
}
.history-item {
  padding: 6px 8px;
  border-bottom: 1px solid #1e293b;
  font-size: 12px;
}
.history-item.blocked {
  background: rgba(239, 68, 68, 0.1);
}
.history-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.history-source { color: #64748b; font-size: 11px; }
.history-time { color: #475569; font-size: 11px; margin-left: auto; }
.history-body {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.history-query { color: #cbd5e1; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-action {
  background: #0f172a;
  color: #38bdf8;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  flex-shrink: 0;
  margin-left: 8px;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #4b5563;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.empty-state p { margin: 0; font-size: 14px; }
.empty-state .sub-text { font-size: 12px; color: #374151; }

/* 滚动条 */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 2px; }
</style>
