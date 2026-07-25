<template>
  <nav
    :class="cn(
      'flex shrink-0 flex-col items-stretch gap-2 border-r border-border bg-card/60 py-3 transition-all duration-300',
      collapsed ? 'w-14 px-1.5' : 'w-16 px-2',
    )"
    aria-label="主导航"
  >
    <!-- Brand logo -->
    <div class="mb-2 flex items-center justify-center">
      <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/30">
        <Shield class="h-5 w-5 text-primary" />
      </div>
    </div>

    <!-- Nav items -->
    <div class="flex flex-1 flex-col gap-2">
      <button
        v-for="{ key, label, icon } in navItems"
        :key="key"
        type="button"
        :aria-label="label"
        :aria-current="active === key ? 'page' : undefined"
        :class="cn(
          'group relative flex h-14 flex-col items-center justify-center gap-1 rounded-xl transition-colors',
          active === key
            ? 'bg-primary/12 text-primary'
            : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
        )"
        @click="$emit('select', key)"
      >
        <!-- Active indicator bar -->
        <span
          v-if="active === key"
          class="absolute left-0 top-1/2 h-7 w-1 -translate-y-1/2 rounded-r-full bg-primary"
        />
        <component :is="icon" class="h-5 w-5" />
        <span class="text-[10px] leading-none">{{ label }}</span>
      </button>
    </div>

    <!-- Collapse toggle -->
    <button
      type="button"
      :aria-label="collapsed ? '展开侧栏' : '收起侧栏'"
      class="flex h-11 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      @click="$emit('toggle')"
    >
      <ChevronRight v-if="collapsed" class="h-5 w-5" />
      <ChevronLeft v-else class="h-5 w-5" />
    </button>
  </nav>
</template>

<script setup lang="ts">
import { Settings, Shield, ChartBar, ChevronLeft, ChevronRight, Map } from '@lucide/vue'
import { cn } from '@/lib/utils'

export type PanelKey = 'safety' | 'stats' | 'trip' | 'settings'

const navItems: { key: PanelKey; label: string; icon: typeof Shield }[] = [
  { key: 'safety', label: '安全监控', icon: Shield },
  { key: 'trip', label: '行程结果', icon: Map },
  { key: 'stats', label: '驾驶统计', icon: ChartBar },
  { key: 'settings', label: '设置', icon: Settings },
]

defineProps<{
  active: PanelKey
  collapsed: boolean
}>()

defineEmits<{
  select: [key: PanelKey]
  toggle: []
}>()
</script>
