<template>
  <header class="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
    <!-- Left: Brand + status -->
    <div class="flex items-center gap-3">
      <span class="text-sm font-semibold tracking-wide">
        Edge<span class="text-primary">Guard</span>
      </span>
      <span
        :class="cn(
          'rounded-full px-2 py-0.5 text-[11px] font-medium',
          offline ? 'bg-danger/15 text-danger' : 'bg-safe/15 text-safe',
        )"
      >
        {{ offline ? '离线' : '监测中' }}
      </span>
    </div>

    <!-- Center: Clock -->
    <div class="flex items-center gap-2 font-mono text-lg font-medium tabular-nums">
      <span>{{ timeStr }}</span>
      <span class="text-xs font-sans font-normal text-muted-foreground">{{ dateStr }}</span>
    </div>

    <!-- Right: Weather + Wi-Fi + Settings -->
    <div class="flex items-center gap-4 text-sm text-muted-foreground">
      <div class="flex items-center gap-1.5">
        <Cloud class="h-4 w-4" />
        <span>{{ weather || '--°C' }}</span>
      </div>
      <div class="flex items-center gap-1.5" :class="offline ? 'text-muted-foreground' : 'text-safe'">
        <Wifi class="h-4 w-4" />
        <span class="text-xs">{{ offline ? '离线' : '在线' }}</span>
      </div>
      <button
        type="button"
        aria-label="设置"
        class="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      >
        <SettingsIcon class="h-4 w-4" />
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Cloud, Wifi, Settings as SettingsIcon } from '@lucide/vue'
import { cn } from '@/lib/utils'

defineProps<{
  offline?: boolean
  weather?: string
}>()

const now = ref<Date>(new Date())
let timer: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  timer = setInterval(() => { now.value = new Date() }, 30000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const timeStr = computed(() =>
  now.value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
)

const dateStr = computed(() =>
  now.value.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })
)
</script>
