<template>
  <div
    class="relative flex items-center justify-center"
    :style="{ width: size + 'px', height: size + 'px' }"
  >
    <svg :width="size" :height="size" class="-rotate-90">
      <!-- Background circle -->
      <circle
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        stroke="var(--secondary)"
        :stroke-width="stroke"
      />
      <!-- Progress arc -->
      <circle
        :cx="size / 2"
        :cy="size / 2"
        :r="radius"
        fill="none"
        :stroke="colorVar"
        :stroke-width="stroke"
        stroke-linecap="round"
        :stroke-dasharray="circumference"
        :stroke-dashoffset="offset"
        :style="{
          transition: 'stroke-dashoffset 0.8s ease, stroke 0.4s ease',
          filter: `drop-shadow(0 0 6px color-mix(in oklch, ${colorVar} 60%, transparent))`,
        }"
      />
    </svg>
    <!-- Center content -->
    <div class="absolute inset-0 flex flex-col items-center justify-center">
      <span
        class="font-mono text-5xl font-semibold tabular-nums leading-none"
        :style="{ color: colorVar }"
      >
        {{ Math.round(value) }}
      </span>
      <span class="mt-1 text-xs text-muted-foreground">注意力分数</span>
      <span
        class="mt-2 rounded-full px-2.5 py-0.5 text-xs font-medium"
        :style="{
          color: colorVar,
          backgroundColor: `color-mix(in oklch, ${colorVar} 18%, transparent)`,
        }"
      >
        {{ levelLabel[level] }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SafetyLevel } from '@/lib/edgeguard'

const props = withDefaults(defineProps<{
  value: number
  level: SafetyLevel
  size?: number
}>(), {
  size: 176,
})

const stroke = 12
const radius = computed(() => (props.size - stroke) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
const offset = computed(() => circumference.value - (props.value / 100) * circumference.value)

const levelColor: Record<SafetyLevel, string> = {
  safe: 'var(--safe)',
  warn: 'var(--warn)',
  danger: 'var(--danger)',
}

const levelLabel: Record<SafetyLevel, string> = {
  safe: '专注',
  warn: '注意',
  danger: '警告',
}

const colorVar = computed(() => levelColor[props.level])
</script>
