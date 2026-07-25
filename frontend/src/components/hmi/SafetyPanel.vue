<template>
  <div class="flex h-full flex-col gap-4 overflow-y-auto p-4">
    <h2 class="text-sm font-semibold text-muted-foreground">安全监控</h2>

    <!-- Attention ring -->
    <div class="flex flex-col items-center rounded-2xl bg-card p-4">
      <AttentionRing :value="telemetry.attention" :level="telemetry.level" />
    </div>

    <!-- Metric cards -->
    <div class="grid grid-cols-2 gap-3">
      <div class="flex flex-col gap-1 rounded-xl bg-secondary/50 p-3">
        <div class="flex items-center gap-1.5 text-muted-foreground">
          <Activity class="h-3.5 w-3.5" />
          <span class="text-[11px]">疲劳程度</span>
        </div>
        <div class="font-mono text-xl font-semibold tabular-nums">
          {{ telemetry.fatigue }}<span class="ml-0.5 text-xs font-normal text-muted-foreground">%</span>
        </div>
      </div>
      <div class="flex flex-col gap-1 rounded-xl bg-secondary/50 p-3">
        <div class="flex items-center gap-1.5 text-muted-foreground">
          <Eye class="h-3.5 w-3.5" />
          <span class="text-[11px]">视线在路</span>
        </div>
        <div class="font-mono text-xl font-semibold tabular-nums">
          {{ telemetry.gazeOnRoad }}<span class="ml-0.5 text-xs font-normal text-muted-foreground">%</span>
        </div>
      </div>
    </div>

    <!-- Alert list -->
    <div class="flex flex-col gap-2">
      <h3 class="text-xs font-medium text-muted-foreground">实时告警</h3>
      <div
        v-for="a in alerts"
        :key="a.id"
        :class="cn(
          'flex items-start gap-3 rounded-xl p-3',
          levelBg[a.level],
          a.level === 'dangerous' && 'animate-hmi-pulse',
        )"
      >
        <CircleCheck v-if="a.level === 'safe'" class="mt-0.5 h-5 w-5 shrink-0 text-safe" />
        <CircleAlert v-else-if="a.level === 'warn'" class="mt-0.5 h-5 w-5 shrink-0 text-warn" />
        <AlertTriangle v-else class="mt-0.5 h-5 w-5 shrink-0 text-danger" />
        <div class="min-w-0 flex-1">
          <div class="flex items-center justify-between gap-2">
            <span :class="cn('text-sm font-medium', levelText[a.level])">{{ a.title }}</span>
            <span class="shrink-0 text-[10px] text-muted-foreground">{{ a.time }}</span>
          </div>
          <p class="mt-0.5 text-xs text-muted-foreground">{{ a.detail }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { AlertTriangle, CircleCheck, CircleAlert, Eye, Activity } from '@lucide/vue'
import { cn } from '@/lib/utils'
import AttentionRing from './AttentionRing.vue'
import type { SafetyAlert, SafetyLevel, Telemetry } from '@/lib/edgeguard'

defineProps<{
  telemetry: Telemetry
  alerts: SafetyAlert[]
}>()

const levelBg: Record<SafetyLevel, string> = {
  normal: 'bg-safe/12',
  attn_declining: 'bg-warn/12',
  distracted: 'bg-warn/12',
  dangerous: 'bg-danger/15',
}
const levelText: Record<SafetyLevel, string> = {
  normal: 'text-safe',
  attn_declining: 'text-warn',
  distracted: 'text-warn',
  dangerous: 'text-danger',
}
</script>
