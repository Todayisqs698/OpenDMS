<template>
  <div class="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card">
    <!-- 头部 -->
    <div class="flex shrink-0 items-center justify-between border-b border-border px-5 py-3">
      <div class="flex items-center gap-2.5">
        <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/15">
          <Map class="h-4 w-4 text-primary" />
        </div>
        <span class="text-sm font-semibold">行程规划</span>
        <span v-if="tripPlan" class="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
          {{ tripPlan.city }} · {{ tripPlan.days || 1 }}日游
        </span>
      </div>
      <button v-if="hasResults"
        type="button" aria-label="清空结果"
        class="flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
        @click="clearAll">✕</button>
    </div>

    <!-- 空状态 -->
    <div v-if="!hasResults && !loading" class="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
      <span class="text-4xl">🤖</span>
      <p class="text-sm text-muted-foreground">Agent 行程结果将显示在这里</p>
      <div class="mt-2 flex flex-wrap justify-center gap-2">
        <span v-for="h in hints" :key="h" class="rounded-full bg-secondary/60 px-3 py-1 text-[11px] text-muted-foreground">{{ h }}</span>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading && !hasResults" class="flex flex-1 flex-col items-center justify-center gap-3">
      <div class="h-7 w-7 animate-spin rounded-full border-[3px] border-secondary border-t-primary" />
      <span class="text-xs text-muted-foreground">Agent 思考中…</span>
    </div>

    <!-- 结果区 -->
    <div v-if="hasResults" class="flex min-h-0 flex-1 flex-col px-4 py-4">
      <!-- 行程概览卡片 -->
      <div v-if="tripPlan" class="shrink-0 rounded-2xl bg-gradient-to-br from-primary/10 to-primary/5 p-4 ring-1 ring-primary/20">
        <div class="mb-1 text-[11px] font-medium text-muted-foreground">
          {{ tripTitle }} · {{ tripPlan.date || '今日' }} · {{ tripPlan.days || 1 }}天
        </div>
        <div v-if="tripPlan.summary" class="mb-3 text-xs text-muted-foreground leading-relaxed">{{ tripPlan.summary }}</div>
        <div v-if="tripPlan.budget" class="flex items-end gap-4">
          <div>
            <div class="text-[10px] text-muted-foreground">预计总费用</div>
            <div class="text-2xl font-bold tabular-nums text-primary">¥{{ tripPlan.budget.total }}</div>
          </div>
          <div class="flex flex-wrap gap-2 text-[11px]">
            <span v-if="tripPlan.budget.tickets" class="rounded-full bg-primary/10 px-2 py-0.5">🎫 ¥{{ tripPlan.budget.tickets }}</span>
            <span v-if="tripPlan.budget.meals" class="rounded-full bg-primary/10 px-2 py-0.5">🍽️ ¥{{ tripPlan.budget.meals }}</span>
            <span v-if="tripPlan.budget.transport" class="rounded-full bg-primary/10 px-2 py-0.5">🚗 ¥{{ tripPlan.budget.transport }}</span>
          </div>
        </div>
      </div>

      <!-- 天气卡片 -->
      <div v-if="weather" class="mt-4 shrink-0 rounded-xl bg-secondary/40 p-3">
        <div class="flex items-center gap-3">
          <span class="text-3xl">{{ weather.weather_emoji || '🌤️' }}</span>
          <div>
            <div class="text-sm font-medium">{{ weather.city || '--' }} {{ weather.temperature != null ? weather.temperature + '°C' : '' }}</div>
            <div class="text-[11px] text-muted-foreground">{{ weather.weather_desc || '' }}</div>
          </div>
          <div class="ml-auto text-right text-[11px] text-muted-foreground">
            <div v-if="weather.humidity != null">💧 {{ weather.humidity }}%</div>
            <div v-if="weather.wind_speed != null">💨 {{ weather.wind_speed }} km/h</div>
          </div>
        </div>
        <div v-if="weather.driving_context" class="mt-2 text-[11px] text-primary/80">{{ weather.driving_context }}</div>
      </div>

      <!-- 导航卡片 -->
      <div v-if="navRoute" class="mt-4 shrink-0 rounded-xl bg-gradient-to-r from-blue-950/60 to-blue-900/30 p-3 ring-1 ring-blue-500/30">
        <div class="flex items-center gap-2 text-sm">
          <span class="text-muted-foreground">📍 {{ navRoute.origin || '当前位置' }}</span>
          <span class="text-primary">→</span>
          <span class="font-semibold">🎯 {{ navRoute.destination }}</span>
        </div>
        <div class="mt-2 flex gap-3">
          <span class="rounded-lg bg-blue-500/15 px-2.5 py-1 text-xs font-semibold text-blue-400">📏 {{ navRoute.distance_km }} km</span>
          <span class="rounded-lg bg-blue-500/15 px-2.5 py-1 text-xs font-semibold text-blue-400">⏱️ {{ navRoute.duration_min }} 分钟</span>
        </div>
        <div v-if="navRoute.route_summary" class="mt-2 text-[11px] text-muted-foreground">{{ navRoute.route_summary }}</div>
      </div>

      <!-- Day 快速切换 -->
      <div v-if="days.length > 1" class="mt-4 shrink-0 overflow-x-auto pb-1">
        <div class="flex min-w-max gap-2">
          <button
            v-for="day in days"
            :key="day.day"
            type="button"
            :class="[
              'flex h-12 min-w-24 flex-col items-center justify-center rounded-lg border px-3 text-left transition-colors',
              activeDay === day.day
                ? 'border-primary bg-primary/15 text-primary'
                : 'border-border bg-secondary/35 text-muted-foreground hover:bg-secondary hover:text-foreground'
            ]"
            @click="activeDay = day.day"
          >
            <span class="text-xs font-bold">Day {{ day.day }}</span>
            <span class="mt-0.5 max-w-20 truncate text-[10px]">{{ day.date }}</span>
          </button>
        </div>
      </div>

      <!-- 日行程时间线 -->
      <div v-if="activeDayPlan" class="mt-4 min-h-0 flex-1 overflow-y-auto pr-1">
        <div class="space-y-3">
        <div class="flex items-center gap-2">
          <span class="rounded-md bg-primary/15 px-2 py-0.5 text-[11px] font-bold text-primary">Day {{ activeDayPlan.day }}</span>
          <span class="text-[11px] text-muted-foreground">{{ activeDayPlan.date }}</span>
          <span v-if="days.length > 1" class="ml-auto text-[10px] text-muted-foreground">
            {{ activeDay }} / {{ days.length }}
          </span>
        </div>
        <div v-if="activeDayPlan.hotel" class="rounded-xl bg-secondary/30 p-3">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="text-sm font-medium">{{ activeDayPlan.hotel.name }}</div>
              <div class="mt-0.5 text-[11px] text-muted-foreground">{{ activeDayPlan.hotel.address }}</div>
            </div>
            <span v-if="activeDayPlan.hotel.source === 'estimated'" class="shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-400">参考</span>
          </div>
          <div class="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
            <span v-if="activeDayPlan.hotel.price_range">价格 {{ activeDayPlan.hotel.price_range }}</span>
            <span v-if="activeDayPlan.hotel.rating">评分 {{ activeDayPlan.hotel.rating }}</span>
            <span v-if="activeDayPlan.hotel.distance">{{ activeDayPlan.hotel.distance }}</span>
          </div>
        </div>
        <div class="relative ml-1 space-y-0">
          <div v-for="(slot, i) in (activeDayPlan.slots || [])" :key="i" class="relative flex gap-3 pb-4">
            <!-- 时间线竖线 -->
            <div class="flex flex-col items-center">
              <div class="text-[10px] tabular-nums text-muted-foreground w-10 text-right shrink-0">{{ slot.time }}</div>
              <div class="relative mt-1 flex h-full flex-col items-center">
                <div :class="['h-2.5 w-2.5 rounded-full shrink-0', dotColor(slot.type)]" />
                <div v-if="i < (activeDayPlan.slots?.length || 0) - 1" class="w-0.5 flex-1 bg-border" />
              </div>
            </div>
            <!-- 内容卡片 -->
            <div class="min-w-0 flex-1 rounded-xl bg-secondary/40 p-3">
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="text-sm font-medium">{{ slot.title }}</div>
                  <div v-if="slot.desc" class="mt-0.5 text-[11px] text-muted-foreground leading-relaxed">{{ slot.desc }}</div>
                </div>
                <span v-if="slot.cost > 0" class="shrink-0 text-xs font-semibold text-amber-400">¥{{ slot.cost }}</span>
              </div>
              <div v-if="slot.photo_url" class="mt-3 h-40 w-full overflow-hidden rounded-lg bg-secondary sm:h-52 xl:h-60">
                <img :src="slot.photo_url" class="h-full w-full object-cover"
                  @error="($event.target as HTMLImageElement).style.display='none'" />
              </div>
              <div v-if="slot.rating > 0" class="mt-1.5 flex gap-2 text-[10px] text-muted-foreground">
                <span>⭐ {{ slot.rating.toFixed(1) }}</span>
                <span v-if="slot.ticket_price > 0">🎫 ¥{{ slot.ticket_price }}</span>
                <span v-else>🎫 免费</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Map } from '@lucide/vue'

interface Budget { total: number; tickets: number; meals: number; transport: number }
interface Slot { time: string; type: string; title: string; desc: string; cost: number; photo_url: string; rating: number; ticket_price: number }
interface Hotel { name: string; address: string; price_range?: string; rating?: string; distance?: string; source?: string }
interface DayPlan { day: number; date: string; hotel?: Hotel; slots: Slot[] }
interface TripPlan {
  city: string
  origin?: string
  waypoints?: string[]
  route_summary?: string
  days: number
  date: string
  summary: string
  budget: Budget
  itinerary: DayPlan[]
}

const props = defineProps<{ tripPlan: TripPlan | null }>()
const emit = defineEmits<{
  (e: 'navigate', payload: { destination: string; day: number }): void
}>()

const tripPlan = ref<TripPlan | null>(null)
const weather = ref<any>(null)
const navRoute = ref<any>(null)
const attractions = ref<any[]>([])
const loading = ref(false)
const activeDay = ref(1)

// 同步 prop → 本地状态
watch(() => props.tripPlan, (val) => {
  if (val) {
    tripPlan.value = val
    activeDay.value = val.itinerary?.[0]?.day || 1
    loading.value = false
  }
}, { immediate: true })

const hints = ['📋 "计划上海一日游"', '🌤️ "今天天气怎么样"', '🧭 "导航去外滩"', '🗺️ "推荐附近景点"']

const hasResults = computed(() => tripPlan.value || weather.value || navRoute.value)
const days = computed(() => tripPlan.value?.itinerary || [])
const activeDayPlan = computed(() =>
  days.value.find(day => day.day === activeDay.value) || days.value[0] || null
)

// 当激活天数变化时，提取该天首个 visit 景点并 emit 给父组件，
// 驱动出行面板（MapArea）地图飞到对应目的地。
// 行程数据到达时 activeDay 会重置为第一天，此 watch 自动触发首次定位。
watch(activeDayPlan, (plan) => {
  if (!plan) return
  const slots = plan.slots || []
  const visit = slots.find(s => s.type === 'visit' && s.title)
  if (!visit) return
  const city = tripPlan.value?.city || ''
  const fullDest = city ? `${city}${visit.title}` : visit.title
  emit('navigate', { destination: fullDest, day: plan.day })
})

const tripTitle = computed(() => {
  const plan = tripPlan.value
  if (!plan) return ''
  if (plan.route_summary) return plan.route_summary
  const route = [plan.origin, ...(plan.waypoints || []), plan.city].filter(Boolean)
  return route.length > 1 ? route.join(' → ') : plan.city
})

function clearAll() {
  weather.value = null; navRoute.value = null
  attractions.value = []; loading.value = false; activeDay.value = 1
}

function dotColor(type: string) {
  switch (type) {
    case 'visit': return 'bg-emerald-400'
    case 'meal': return 'bg-amber-400'
    case 'transport': return 'bg-blue-400'
    case 'rest': return 'bg-purple-400'
    default: return 'bg-primary'
  }
}
</script>
