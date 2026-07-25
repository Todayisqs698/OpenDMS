<template>
  <div class="flex h-full w-[360px] shrink-0 flex-col border-l border-border bg-card/70">
    <!-- header -->
    <div class="flex items-center justify-between px-3 pt-3">
      <div class="flex items-center gap-2">
        <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/15"><Sparkles class="h-4 w-4 text-primary" /></div>
        <span class="text-sm font-semibold">AI 副驾</span>
      </div>
      <div class="flex items-center gap-1">
        <button type="button"
          :class="cn('rounded-lg px-2 py-1 text-xs font-medium transition-colors', advanced ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-secondary')"
          @click="advanced = !advanced">{{ advanced ? '高级' : '普通' }}</button>
        <button type="button" aria-label="收起 AI 面板" class="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground" @click="$emit('close')"><X class="h-4 w-4" /></button>
      </div>
    </div>

    <!-- 状态指示器：长按进入高级 -->
    <button type="button"
      @pointerdown="startPress" @pointerup="endPress" @pointerleave="endPress" @contextmenu.prevent
      :class="cn('mx-3 mt-3 flex items-center gap-3 rounded-xl bg-secondary/60 px-3 py-2.5 text-left transition-all',
        pressing && 'ring-2 ring-primary/50 scale-[0.98]', 'hover:bg-secondary')">
      <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/15">
        <span class="h-3 w-3 animate-hmi-breathe rounded-full bg-primary" />
      </span>
      <span class="min-w-0 flex-1">
        <span class="block text-xs text-muted-foreground">{{ route === 'auto' ? '系统自动选择最优 Agent' : '当前路由' }}</span>
        <span class="block truncate text-sm font-medium text-foreground">{{ activeRoute.label }}</span>
      </span>
      <span :class="cn('flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium', gate.style)">
        <component :is="gate.icon" class="h-3 w-3" />{{ gate.label }}
      </span>
    </button>

    <div v-if="!advanced" class="px-3 pt-1.5">
      <p class="text-[10px] text-muted-foreground">长按上方状态可进入高级模式</p>
      <p v-if="gate.label !== '全工具'" class="text-[10px] text-warn">
        受限工具：{{ safetyGateMap[safetyLevel].blockedTools.slice(0, 4).join('、') }}{{ safetyGateMap[safetyLevel].blockedTools.length > 4 ? '…' : '' }}
      </p>
    </div>

    <!-- 高级模式 -->
    <div v-if="advanced" class="mx-3 mt-2 flex flex-col gap-2">
      <!-- 路由选择 -->
      <div class="relative">
        <button type="button" class="flex w-full items-center justify-between rounded-lg bg-secondary px-3 py-2 text-sm" @click="routeOpen = !routeOpen">
          <span>路由：<span class="font-medium text-primary">{{ activeRoute.label }}</span></span>
          <ChevronDown :class="cn('h-4 w-4 transition-transform', routeOpen && 'rotate-180')" />
        </button>
        <div v-if="routeOpen" class="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-border bg-popover shadow-xl">
          <button v-for="r in agentRoutes" :key="r.id" type="button"
            :class="cn('flex w-full flex-col gap-0.5 px-3 py-2 text-left transition-colors hover:bg-accent', route === r.id && 'bg-primary/10')"
            @click="route = r.id; routeOpen = false">
            <span class="text-sm font-medium">{{ r.label }}</span><span class="text-xs text-muted-foreground">{{ r.description }}</span>
          </button>
        </div>
      </div>

      <!-- 安全门控详情 -->
      <div class="rounded-lg bg-secondary/40 p-2.5 text-xs">
        <div class="flex items-center justify-between">
          <span class="text-muted-foreground">安全门控</span>
          <span :class="cn('rounded-md px-2 py-0.5 font-medium', gate.style)">
            <component :is="gate.icon" class="mr-1 inline h-3 w-3" />{{ gate.label }} · {{ safetyLevel }}
          </span>
        </div>
        <div class="mt-1.5 grid grid-cols-2 gap-1 text-[10px] text-muted-foreground">
          <span>可用：{{ safetyGateMap[safetyLevel].allowedTools.length }} 个</span>
          <span>禁用：{{ safetyGateMap[safetyLevel].blockedTools.length }} 个</span>
        </div>
      </div>

      <!-- 执行轨迹 -->
      <button type="button" class="flex items-center justify-between rounded-lg bg-secondary/60 px-3 py-2 text-xs text-muted-foreground" @click="traceOpen = !traceOpen">
        <span>执行轨迹（系统记录）</span>
        <ChevronDown :class="cn('h-4 w-4 transition-transform', traceOpen && 'rotate-180')" />
      </button>
      <div v-if="traceOpen" class="flex flex-col gap-1">
        <div v-for="(step, i) in traceSteps" :key="step.id" class="flex flex-col gap-1 rounded-lg bg-secondary/40 px-3 py-2">
          <div class="flex items-center gap-2.5">
            <CircleCheck v-if="step.status === 'done'" class="h-4 w-4 shrink-0 text-safe" />
            <XCircle v-else-if="step.status === 'failed'" class="h-4 w-4 shrink-0 text-danger" />
            <Slash v-else-if="step.status === 'cancelled'" class="h-4 w-4 shrink-0 text-muted-foreground" />
            <ArrowDown v-else-if="step.status === 'degraded'" class="h-4 w-4 shrink-0 text-warn" />
            <span v-else-if="step.status === 'running'" class="h-4 w-4 shrink-0 animate-hmi-breathe rounded-full bg-primary" />
            <span v-else class="h-4 w-4 shrink-0 rounded-full border border-muted-foreground/40" />
            <span class="w-14 shrink-0 font-mono text-[10px] text-muted-foreground">{{ i + 1 }}.{{ phaseLabel[step.phase] }}</span>
            <span :class="cn('min-w-0 flex-1 truncate text-xs', step.status === 'pending' ? 'text-muted-foreground' : 'text-foreground')">{{ step.detail }}</span>
            <span v-if="step.durationMs != null" class="shrink-0 font-mono text-[10px] text-muted-foreground">{{ step.durationMs }}ms</span>
          </div>
          <div v-if="step.toolName" class="ml-[4.5rem] flex flex-col gap-0.5 text-[10px]">
            <span class="text-muted-foreground">入参：<code class="rounded bg-secondary px-1 font-mono text-primary">{{ JSON.stringify(step.toolArgs) }}</code></span>
            <span v-if="step.toolResult" :class="step.status === 'failed' ? 'text-danger' : 'text-safe'">{{ step.toolResult }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 对话主体 -->
    <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
      <div v-if="lastAssistant" class="rounded-2xl bg-primary/10 p-3 ring-1 ring-primary/20">
        <div class="mb-1.5 flex items-center gap-2">
          <Sparkles class="h-4 w-4 text-primary" /><span class="text-xs font-medium text-primary">EdgeGuard</span>
          <button type="button" aria-label="朗读回复" class="ml-auto flex h-6 w-6 items-center justify-center rounded-md text-primary hover:bg-primary/15" title="朗读此回复" @click="lastAssistant && emit('speak-reply', lastAssistant.text)"><Volume2 class="h-3.5 w-3.5" /></button>
        </div>
        <p class="text-lg leading-relaxed text-pretty">{{ lastAssistant.text }}</p>
      </div>
      <div class="flex flex-col gap-2">
        <div v-for="m in messages" :key="m.id" :class="cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')">
          <div :class="cn('max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed', m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-secondary text-foreground')">{{ m.text }}</div>
        </div>
      </div>

      <!-- 结果卡片（高级模式） -->
      <div v-if="advanced" class="flex flex-col gap-2">
        <span class="text-xs font-medium text-muted-foreground">结果卡片</span>
        <button v-for="r in mockAgentResults" :key="r.id" type="button" class="flex items-center gap-3 rounded-xl bg-card p-3 text-left hover:bg-accent">
          <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/12">
            <MapPin v-if="r.type === 'poi'" class="h-4 w-4 text-primary" />
            <Cloud v-else-if="r.type === 'weather'" class="h-4 w-4 text-primary" />
            <Navigation v-else class="h-4 w-4 text-primary" />
          </span>
          <span class="min-w-0 flex-1"><span class="block truncate text-sm font-medium">{{ r.title }}</span><span class="block truncate text-xs text-muted-foreground">{{ r.subtitle }}</span></span>
          <span class="shrink-0 text-xs text-primary">{{ r.meta }}</span>
          <ChevronRight class="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>
      </div>
    </div>

    <!-- input dock -->
    <div class="border-t border-border p-3">
      <div class="mb-2 flex flex-wrap gap-1.5">
        <button v-for="q in quickReplies" :key="q" type="button" class="rounded-full bg-secondary px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground" @click="submit(q)">{{ q }}</button>
      </div>
      <div class="flex items-center gap-2">
        <button type="button" :aria-label="recording ? '停止录音' : '开始语音'"
          :class="cn('flex h-11 w-11 shrink-0 items-center justify-center rounded-xl transition-colors',
            recording ? 'animate-hmi-breathe bg-danger text-primary-foreground' : 'bg-primary/15 text-primary hover:bg-primary/25')"
          @click="toggleRecording"><Mic class="h-5 w-5" /></button>
        <input v-model="input" placeholder="输入或说出指令…"
          class="h-11 flex-1 rounded-xl bg-secondary px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-primary/40"
          @keydown.enter.prevent="submit(input)" />
        <button type="button" aria-label="发送" class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground hover:opacity-90" @click="submit(input)"><Send class="h-5 w-5" /></button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { AlertTriangle, ArrowDown, ChevronDown, ChevronRight, CircleCheck, Cloud, MapPin, Mic, Navigation, Send, Shield, Slash, Sparkles, Volume2, X, XCircle } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { agentRoutes, mockAgentResults, mockAgentTrace, quickReplies, safetyGateMap, type AgentRoute, type AgentTraceStep, type ChatMessage, type SafetyLevel } from '@/lib/edgeguard'

const props = defineProps<{ messages: ChatMessage[] }>()
const emit = defineEmits<{ send: [text: string]; 'speak-reply': [text: string]; close: [] }>()

const input = ref('')
const recording = ref(false)
const advanced = ref(false)
const route = ref<AgentRoute>('auto')
const routeOpen = ref(false)
const traceOpen = ref(false)
const pressing = ref(false)
const safetyLevel = ref<SafetyLevel>('normal')
const traceSteps = ref<AgentTraceStep[]>(mockAgentTrace)

let pressTimer: ReturnType<typeof setTimeout> | null = null

const activeRoute = computed(() => agentRoutes.find(r => r.id === route.value)!)

const phaseLabel: Record<AgentTraceStep['phase'], string> = { perceive: '感知', safety_gate: '安全门控', agent: '决策', tool: '工具', result: '结果' }

const gate = computed(() => {
  const readOnly = route.value === 'readonly'
  const lvl = readOnly ? 'dangerous' : safetyLevel.value
  const g = safetyGateMap[lvl]
  const isFull = g.toolAvailability === 'full'
  const isReadonly = g.toolAvailability === 'readonly'
  return {
    label: g.label,
    style: isFull ? 'bg-safe/15 text-safe' : isReadonly ? 'bg-danger/15 text-danger' : 'bg-warn/15 text-warn',
    icon: isFull ? Shield : isReadonly ? AlertTriangle : Shield,
  }
})

const lastAssistant = computed(() => [...props.messages].reverse().find(m => m.role === 'assistant'))

function submit(text: string) {
  const t = text.trim()
  if (!t) return
  emit('send', t)
  input.value = ''
  if (t.includes('疲劳') || t.includes('累了')) safetyLevel.value = 'attn_declining'
  else if (t.includes('分心')) safetyLevel.value = 'distracted'
  else if (t.includes('危险') || t.includes('紧急')) safetyLevel.value = 'dangerous'
  else safetyLevel.value = 'normal'
}

function startPress() { pressing.value = true; pressTimer = setTimeout(() => { advanced.value = true; pressing.value = false }, 600) }
function endPress() { pressing.value = false; if (pressTimer) clearTimeout(pressTimer) }

// ── 语音识别（Web Speech API，浏览器原生支持）──
let recognition: any = null

function toggleRecording() {
  if (recording.value) {
    stopRecording()
    return
  }
  startRecording()
}

function startRecording() {
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SpeechRecognition) {
    alert('您的浏览器不支持语音识别，请使用 Chrome 浏览器')
    return
  }

  recognition = new SpeechRecognition()
  recognition.continuous = false
  recognition.interimResults = false
  recognition.lang = 'zh-CN'

  recognition.onstart = () => {
    recording.value = true
  }

  recognition.onresult = (event: any) => {
    let transcript = ''
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        transcript += event.results[i][0].transcript
      }
    }
    if (transcript.trim()) {
      submit(transcript.trim())
    }
  }

  recognition.onerror = (event: any) => {
    recording.value = false
    if (event.error === 'not-allowed') {
      alert('麦克风权限被拒绝，请在浏览器设置中允许麦克风访问')
    } else if (event.error !== 'no-speech') {
      console.warn('语音识别:', event.error)
    }
  }

  recognition.onend = () => {
    recording.value = false
  }

  try {
    recognition.start()
  } catch {
    recording.value = false
  }
}

function stopRecording() {
  if (recognition) {
    try { recognition.stop() } catch { /* ignore */ }
  }
  recording.value = false
}
</script>
