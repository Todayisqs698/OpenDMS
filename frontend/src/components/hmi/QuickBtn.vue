<template>
  <button
    type="button"
    :class="cn(
      'flex h-11 items-center gap-2 rounded-xl px-4 transition-colors',
      active
        ? 'bg-primary/15 text-primary'
        : 'bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground',
    )"
  >
    <Wind v-if="icon === 'Wind'" class="h-5 w-5" />
    <Music v-else-if="icon === 'Music'" class="h-5 w-5" />
    <Hand v-else-if="icon === 'Hand'" class="h-5 w-5" />
    <span class="text-sm font-medium">{{ label }}</span>
  </button>
</template>

<script setup lang="ts">
import { Wind, Music, Hand } from '@lucide/vue'
import { cn } from '@/lib/utils'

defineProps<{
  icon: 'Wind' | 'Music' | 'Hand'
  label: string
  active?: boolean
}>()
</script>
