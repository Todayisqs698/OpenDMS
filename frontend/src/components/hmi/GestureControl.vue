<template>
  <div class="relative flex h-full min-h-0 flex-col gap-3">
    <!-- emergency_stop 二次确认覆盖层 -->
    <div v-if="confirmStop" class="absolute inset-0 z-50 flex flex-col items-center justify-center gap-4 rounded-2xl bg-background/95 backdrop-blur-md animate-hmi-pulse">
      <AlertTriangle class="h-12 w-12 text-danger" />
      <div class="text-center">
        <p class="text-lg font-bold text-danger">确认紧急制动？</p>
        <p class="mt-1 text-sm text-muted-foreground">此操作将触发最高级别安全告警</p>
        <p class="mt-2 font-mono text-2xl font-semibold text-danger">{{ confirmTimer }}s 后自动取消</p>
      </div>
      <div class="flex gap-4">
        <button type="button" class="flex h-14 w-32 items-center justify-center rounded-2xl bg-secondary text-lg font-medium text-muted-foreground hover:bg-accent hover:text-foreground" @click="cancelStop">取消</button>
        <button type="button" class="flex h-14 w-32 items-center justify-center rounded-2xl bg-danger text-lg font-bold text-primary-foreground hover:opacity-90 animate-hmi-breathe" @click="confirmStopAction">确认制动</button>
      </div>
    </div>

    <!-- 摄像头状态 + 识别 -->
    <div class="grid grid-cols-[1fr_1.25fr] gap-3">
      <div class="relative flex min-h-28 flex-col justify-between overflow-hidden rounded-2xl bg-secondary/70 p-4 ring-1 ring-border">
        <Camera class="absolute right-3 top-3 h-16 w-16 text-primary/10" />
        <div class="flex items-center gap-2 text-xs text-muted-foreground">
          <span :class="cn('h-2 w-2 rounded-full', enabled ? 'animate-hmi-breathe bg-safe' : 'bg-muted-foreground')" />
          手势识别 {{ enabled ? '在线' : '已暂停' }}
        </div>
        <div>
          <div :class="cn('font-mono text-xl font-semibold', gestureName !== '—' ? 'text-primary' : 'text-muted-foreground')">{{ gestureName }}</div>
          <div class="mt-1 text-sm text-muted-foreground">{{ gestureName !== '—' ? meaning : '等待手势…' }}</div>
        </div>
      </div>
      <div class="flex flex-col justify-between rounded-2xl bg-primary/10 p-4 ring-1 ring-primary/20">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-primary">当前识别</span>
          <span v-if="confidence != null" :class="cn('font-mono text-xs', confidence >= 90 ? 'text-safe' : confidence >= 70 ? 'text-warn' : 'text-danger')">{{ confidence.toFixed(1) }}%</span>
        </div>
        <div class="h-2 overflow-hidden rounded-full bg-secondary">
          <div class="h-full rounded-full bg-primary transition-all duration-300" :style="{ width: confidence != null ? `${confidence.toFixed(0)}%` : '0%' }" />
        </div>
        <div class="flex items-center gap-2 text-sm">
          <template v-if="detStatus === '已执行'"><CircleCheck class="h-4 w-4 text-safe" />已执行 · 刚刚</template>
          <template v-else-if="detStatus === '待确认'"><AlertTriangle class="h-4 w-4 text-warn" />待确认</template>
          <template v-else-if="detStatus === '失败'"><XCircle class="h-4 w-4 text-danger" />识别失败</template>
          <template v-else><span class="h-2 w-2 animate-hmi-breathe rounded-full bg-primary" />识别中…</template>
        </div>
      </div>
    </div>

    <!-- 分类筛选 -->
    <div class="flex items-center gap-2 overflow-x-auto pb-1">
      <button v-for="item in categories" :key="item" type="button"
        :class="cn('h-8 shrink-0 rounded-lg px-3 text-xs font-medium transition-colors',
          category === item ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground hover:text-foreground')"
        @click="category = item">{{ item }}</button>
    </div>

    <!-- 手势映射表 -->
    <div class="min-h-0 flex-1 overflow-y-auto rounded-xl ring-1 ring-border">
      <div class="grid grid-cols-[1fr_.85fr_.65fr_.65fr] bg-secondary/70 px-3 py-2 text-xs text-muted-foreground">
        <span>手势 / action_code</span><span>含义</span><span>分类</span><span>端点</span>
      </div>
      <div v-for="cmd in filtered" :key="`${cmd.gesture}-${cmd.actionCode}`"
        :class="cn('grid min-h-12 grid-cols-[1fr_.85fr_.65fr_.65fr] items-center border-t border-border px-3 py-2', cmd.actionCode === 'emergency_stop' && 'bg-danger/10')">
        <div class="min-w-0">
          <div :class="cn('truncate font-mono text-xs font-medium', cmd.actionCode === 'emergency_stop' ? 'text-danger' : 'text-foreground')">{{ cmd.gesture }}</div>
          <div class="truncate font-mono text-[10px] text-muted-foreground">{{ cmd.actionCode }}</div>
        </div>
        <div class="flex items-center gap-1.5 text-sm">
          <AlertTriangle v-if="cmd.actionCode === 'emergency_stop'" class="h-4 w-4 text-danger" />
          {{ cmd.meaning }}
        </div>
        <span class="text-xs text-muted-foreground">{{ cmd.category }}</span>
        <code class="truncate rounded bg-secondary/60 px-1 py-0.5 font-mono text-[10px] text-muted-foreground">{{ getEndpoint(cmd.actionCode) }}</code>
      </div>
    </div>

    <!-- 底部状态栏 -->
    <div class="flex items-center justify-between rounded-xl bg-secondary/60 px-3 py-2.5">
      <div class="flex items-center gap-2 text-xs text-muted-foreground min-w-0">
        <Radio class="h-4 w-4 shrink-0" />
        <span class="truncate">{{ lastExecuted || '识别记录：等待手势输入' }}</span>
      </div>
      <button type="button"
        :class="cn('flex h-9 shrink-0 items-center gap-2 rounded-lg px-3 text-xs font-medium ml-2',
          enabled ? 'bg-primary/15 text-primary' : 'bg-secondary text-muted-foreground')"
        @click="enabled = !enabled">
        <Hand class="h-4 w-4" /> {{ enabled ? '手势已开启' : '启用手势' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { AlertTriangle, Camera, CircleCheck, Hand, Radio, XCircle } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { gestureCommands, type GestureCategory } from '@/lib/edgeguard'
import type { CameraHeaders } from '@/composables/useTelemetry'

const props = defineProps<{ headers?: CameraHeaders }>()

const categories = ['全部', '空调', '确认', '导航', '媒体'] as const
const category = ref<(typeof categories)[number]>('全部')

const enabled = computed(() => true) // 摄像头在线即启用
const filtered = computed(() =>
  category.value === '全部' ? gestureCommands : gestureCommands.filter(g => g.category === category.value)
)

// 实时数据 — 从摄像头 headers 取
const gestureName = computed(() => props.headers?.gestureHint || props.headers?.gesture || '—')
const confidence = computed(() => props.headers?.confidence != null ? Math.round(props.headers.confidence * 100) : null)
const actionCode = computed(() => props.headers?.action || '')
const detStatus = computed<'识别中' | '已执行' | '待确认' | '已取消' | '失败'>(() => {
  if (!props.headers?.gesture) return '识别中'
  const code = actionCode.value
  if (code === 'TurnOnAC' || code === 'TurnOffAC' || code.includes('track') || code.includes('volume')) return '已执行'
  if (code === 'confirm' || code === 'cancel') return code === 'confirm' ? '已执行' : '已取消'
  if (code && code !== 'normal') return '已执行'
  return '识别中'
})
const meaning = computed(() => {
  const g = gestureCommands.find(c => c.gesture === gestureName.value)
  return g?.label || (gestureName.value !== '—' ? gestureName.value : '')
})
const lastExecuted = ref<string | null>(null)

// emergency_stop 二次确认
const confirmStop = ref(false)
const confirmTimer = ref(5)
let timerInterval: ReturnType<typeof setInterval> | null = null

function triggerStopConfirm() {
  confirmStop.value = true
  confirmTimer.value = 5
  timerInterval = setInterval(() => {
    confirmTimer.value--
    if (confirmTimer.value <= 0) { cancelStop() }
  }, 1000)
}

function confirmStopAction() {
  confirmStop.value = false
  if (timerInterval) clearInterval(timerInterval)
  lastExecuted.value = 'stop → emergency_stop → 已触发'
}

function cancelStop() {
  confirmStop.value = false
  if (timerInterval) clearInterval(timerInterval)
  lastExecuted.value = 'stop → emergency_stop → 已取消'
}

// 模拟检测到 stop 手势时弹出确认
watch(gestureName, (val) => {
  if (val === 'stop') { triggerStopConfirm() }
})

onBeforeUnmount(() => { if (timerInterval) clearInterval(timerInterval) })

const endpointMap: Record<string, string> = {
  TurnOnAC: '/api/ac/command', TurnOffAC: '/api/ac/command',
  confirm: '/api/agent/chat', cancel: '/api/agent/chat',
  attention: '/api/agent/chat', mode_3: '/api/agent/chat', mode_4: '/api/agent/chat',
  zoom_in: '/api/agent/chat',
  previous_track: '/api/music/prev', next_track: '/api/music/next',
  volume_up: '/api/music/volume', volume_down: '/api/music/volume',
  call: '/api/agent/chat', mute: '/api/music/volume',
  emergency_stop: '/api/agent/chat',
}

function getEndpoint(code: string) { return endpointMap[code] || '/api/agent/chat' }
</script>
