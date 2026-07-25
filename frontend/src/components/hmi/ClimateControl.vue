<template>
  <div class="flex flex-col gap-4" :class="{ 'opacity-60': !hvac.power }">
    <!-- 顶部：总开关 + SYNC -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="text-base font-semibold">双区空调</span>
        <span class="rounded-md bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
          {{ hvac.auto ? 'AUTO' : '手动' }} · {{ hvac.fanSpeed }} 档
        </span>
      </div>
      <button
        type="button" aria-label="空调总开关"
        :class="cn('flex h-10 w-10 items-center justify-center rounded-xl transition-colors',
          hvac.power ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground')"
        @click="togglePower"
      >
        <Power class="h-5 w-5" />
      </button>
    </div>

    <!-- 双区温度 -->
    <div class="grid grid-cols-[1fr_auto_1fr] items-stretch gap-3">
      <div class="flex flex-col items-center gap-2 rounded-2xl bg-secondary/50 p-3">
        <span class="text-xs text-muted-foreground">主驾</span>
        <div class="font-mono text-4xl font-semibold tabular-nums text-primary">{{ hvac.driverTemp.toFixed(1) }}°</div>
        <div class="flex w-full gap-1.5">
          <button type="button" aria-label="主驾降温" class="h-10 flex-1 rounded-lg bg-card text-lg font-medium hover:bg-accent" @click="stepTemp('driver', -0.5)">−</button>
          <button type="button" aria-label="主驾升温" class="h-10 flex-1 rounded-lg bg-card text-lg font-medium hover:bg-accent" @click="stepTemp('driver', 0.5)">+</button>
        </div>
      </div>
      <div class="flex flex-col items-center justify-center gap-2">
        <button
          type="button"
          :class="cn('flex flex-col items-center gap-1 rounded-xl px-3 py-2 text-xs font-medium transition-colors',
            hvac.sync ? 'bg-primary/15 text-primary' : 'bg-secondary text-muted-foreground')"
          @click="toggleSync"
        >
          <RotateCw class="h-4 w-4" /> SYNC
        </button>
      </div>
      <div class="flex flex-col items-center gap-2 rounded-2xl bg-secondary/50 p-3" :class="{ 'opacity-70': hvac.sync }">
        <span class="text-xs text-muted-foreground">副驾</span>
        <div class="font-mono text-4xl font-semibold tabular-nums text-primary">{{ hvac.passengerTemp.toFixed(1) }}°</div>
        <div class="flex w-full gap-1.5">
          <button type="button" aria-label="副驾降温" class="h-10 flex-1 rounded-lg bg-card text-lg font-medium hover:bg-accent" @click="stepTemp('passenger', -0.5)">−</button>
          <button type="button" aria-label="副驾升温" class="h-10 flex-1 rounded-lg bg-card text-lg font-medium hover:bg-accent" @click="stepTemp('passenger', 0.5)">+</button>
        </div>
      </div>
    </div>

    <!-- 风速 1-5 -->
    <div>
      <div class="mb-1.5 flex items-center gap-1.5 text-xs text-muted-foreground"><Wind class="h-3.5 w-3.5" /> 风速</div>
      <div class="flex gap-1.5">
        <button v-for="n in 5" :key="n" type="button"
          :class="cn('h-9 flex-1 rounded-lg text-sm font-medium tabular-nums transition-colors',
            hvac.fanSpeed >= n ? 'bg-primary/80 text-primary-foreground' : 'bg-secondary text-muted-foreground hover:bg-accent')"
          @click="setFan(n)">{{ n }}</button>
      </div>
    </div>

    <!-- 送风模式（3×2 网格） -->
    <div class="grid grid-cols-3 gap-1.5">
      <button v-for="m in modes" :key="m.id" type="button"
        :class="cn('flex h-10 items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-colors',
          hvac.mode === m.id ? 'bg-primary/15 text-primary ring-1 ring-primary/30' : 'bg-secondary text-muted-foreground hover:bg-accent')"
        @click="setMode(m.id)">
        <component :is="m.icon" class="h-3.5 w-3.5" /> {{ m.label }}
      </button>
    </div>

    <!-- 开关行 -->
    <div class="grid grid-cols-3 gap-1.5">
      <button type="button"
        :class="cn('flex h-10 items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors',
          hvac.auto ? 'bg-primary/15 text-primary ring-1 ring-primary/30' : 'bg-secondary text-muted-foreground hover:bg-accent')"
        @click="toggleAuto"><Zap class="h-4 w-4" />AUTO</button>
      <button type="button"
        :class="cn('flex h-10 items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors',
          hvac.ac ? 'bg-primary/15 text-primary ring-1 ring-primary/30' : 'bg-secondary text-muted-foreground hover:bg-accent')"
        @click="toggleAc"><Snowflake class="h-4 w-4" />A/C</button>
      <button type="button"
        :class="cn('flex h-10 items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors',
          hvac.circulation === 'inside' ? 'bg-primary/15 text-primary ring-1 ring-primary/30' : 'bg-secondary text-muted-foreground hover:bg-accent')"
        @click="toggleCirculation"><RotateCw class="h-4 w-4" />{{ hvac.circulation === 'inside' ? '内循环' : '外循环' }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Power, Snowflake, Wind, RotateCw, Zap } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { initialHvac, type HvacState, type HvacMode } from '@/lib/edgeguard'

const hvac = ref<HvacState>({ ...initialHvac })

const modes: { id: HvacMode; label: string; icon: any }[] = [
  { id: 'face', label: '吹脸', icon: Wind },
  { id: 'face-feet', label: '吹脸+脚', icon: Wind },
  { id: 'feet', label: '吹脚', icon: Wind },
  { id: 'front-defrost', label: '前挡除雾', icon: Wind },
  { id: 'rear-defrost', label: '后挡除雾', icon: Wind },
]

async function fetchState() {
  try {
    const r = await fetch('/api/ac/state')
    const d = await r.json()
    if (d.status === 'ok' && d.data) {
      const s = d.data
      hvac.value.power = s.power ?? hvac.value.power
      hvac.value.driverTemp = s.temperature ?? hvac.value.driverTemp
      hvac.value.passengerTemp = s.temperature ?? hvac.value.passengerTemp
      hvac.value.fanSpeed = s.fanSpeed ?? hvac.value.fanSpeed
      if (s.mode) hvac.value.mode = s.mode
    }
  } catch { /* 后端不可用 */ }
}

async function sendCmd(cmd: string, extra?: Record<string, unknown>) {
  try {
    const r = await fetch('/api/ac/command', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd, ...extra }),
    })
    const d = await r.json()
    if (d.status === 'ok' && d.data) {
      const s = d.data
      hvac.value.power = s.power ?? hvac.value.power
      hvac.value.driverTemp = s.temperature ?? hvac.value.driverTemp
      if (hvac.value.sync) hvac.value.passengerTemp = hvac.value.driverTemp
      hvac.value.fanSpeed = s.fanSpeed ?? hvac.value.fanSpeed
      if (s.mode) hvac.value.mode = s.mode
    }
  } catch { /* ignore */ }
}

function togglePower() { sendCmd(hvac.value.power ? 'TurnOffAC' : 'TurnOnAC') }
function stepTemp(zone: 'driver' | 'passenger', delta: number) {
  const clamp = (v: number) => Math.min(30, Math.max(16, Math.round(v * 2) / 2))
  if (hvac.value.sync) {
    const t = clamp(hvac.value.driverTemp + delta)
    hvac.value.driverTemp = t; hvac.value.passengerTemp = t
  } else if (zone === 'driver') {
    hvac.value.driverTemp = clamp(hvac.value.driverTemp + delta)
  } else {
    hvac.value.passengerTemp = clamp(hvac.value.passengerTemp + delta)
  }
  sendCmd('set', { temperature: hvac.value.driverTemp })
}
function toggleSync() { hvac.value.sync = !hvac.value.sync; if (hvac.value.sync) hvac.value.passengerTemp = hvac.value.driverTemp }
function setFan(n: number) { hvac.value.fanSpeed = n as HvacState['fanSpeed']; hvac.value.auto = false; sendCmd('set', { fanSpeed: n }) }
function setMode(m: HvacMode) { hvac.value.mode = m; sendCmd('set', { mode: m }) }
function toggleAuto() { hvac.value.auto = !hvac.value.auto }
function toggleAc() { hvac.value.ac = !hvac.value.ac }
function toggleCirculation() { hvac.value.circulation = hvac.value.circulation === 'inside' ? 'outside' : 'inside' }

onMounted(() => { fetchState() })
</script>
