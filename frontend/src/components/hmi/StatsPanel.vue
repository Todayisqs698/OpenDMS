<template>
  <div class="flex h-full flex-col gap-4 overflow-y-auto p-4">
    <h2 class="text-sm font-semibold text-muted-foreground">驾驶统计</h2>

    <!-- Score card -->
    <div class="flex flex-col items-center gap-1 rounded-2xl bg-card p-5">
      <span class="text-xs text-muted-foreground">本次驾驶评分</span>
      <span class="font-mono text-5xl font-semibold tabular-nums text-primary">
        {{ stats.score }}
      </span>
      <span class="text-xs text-safe">表现优秀 · 继续保持</span>
    </div>

    <!-- Stat cards -->
    <div class="grid grid-cols-3 gap-3">
      <div class="flex flex-col gap-1.5 rounded-xl bg-secondary/50 p-3">
        <div class="flex items-center gap-1.5 text-muted-foreground">
          <Clock class="h-3.5 w-3.5" />
          <span class="text-[11px]">驾驶时长</span>
        </div>
        <div class="font-mono text-2xl font-semibold tabular-nums">
          {{ stats.durationMin }}<span class="ml-1 text-xs font-normal text-muted-foreground">分</span>
        </div>
      </div>
      <div class="flex flex-col gap-1.5 rounded-xl bg-secondary/50 p-3">
        <div class="flex items-center gap-1.5 text-muted-foreground">
          <Eye class="h-3.5 w-3.5" />
          <span class="text-[11px]">分心次数</span>
        </div>
        <div class="font-mono text-2xl font-semibold tabular-nums">
          {{ stats.distractionCount }}<span class="ml-1 text-xs font-normal text-muted-foreground">次</span>
        </div>
      </div>
      <div class="flex flex-col gap-1.5 rounded-xl bg-secondary/50 p-3">
        <div class="flex items-center gap-1.5 text-muted-foreground">
          <Eye class="h-3.5 w-3.5" />
          <span class="text-[11px]">闭眼比例</span>
        </div>
        <div class="font-mono text-2xl font-semibold tabular-nums">
          {{ (stats.perclosAvg * 100).toFixed(1) }}<span class="ml-1 text-xs font-normal text-muted-foreground">%</span>
        </div>
      </div>
    </div>

    <!-- Fatigue trend chart -->
    <div class="flex flex-col gap-2 rounded-xl bg-card p-4">
      <span class="text-xs font-medium text-muted-foreground">疲劳趋势</span>
      <div class="flex h-24 items-end gap-1.5">
        <div
          v-for="(v, i) in stats.fatigueTrend"
          :key="i"
          class="flex-1 rounded-t-sm bg-primary/70 transition-all"
          :style="{ height: maxVal > 0 ? (v / maxVal) * 100 + '%' : '0%' }"
          :title="`${v}%`"
        />
      </div>
      <span class="text-[10px] text-muted-foreground">近 1 小时采样</span>
    </div>

    <!-- 严重分心 + 报告 -->
    <div class="flex flex-col gap-2">
      <div class="flex items-center justify-between rounded-xl bg-secondary/50 px-3 py-2">
        <span class="text-[11px] text-muted-foreground">严重分心</span>
        <span class="font-mono text-sm font-semibold text-danger">{{ severe }} 次</span>
      </div>
      <button class="w-full rounded-xl bg-primary/15 py-2.5 text-sm font-medium text-primary hover:bg-primary/25 transition-colors" :disabled="loading" @click="$emit('genReport')">
        {{ loading ? '生成中...' : '生成驾驶报告' }}
      </button>
      <div v-if="reportText" class="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">{{ reportText }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Clock, Eye } from '@lucide/vue'
import type { DrivingStats } from '@/lib/edgeguard'

const props = defineProps<{
  stats: DrivingStats
  severe: number
  loading: boolean
  reportText: string
}>()

defineEmits<{ genReport: [] }>()

const maxVal = computed(() => Math.max(...props.stats.fatigueTrend, 1))
</script>
