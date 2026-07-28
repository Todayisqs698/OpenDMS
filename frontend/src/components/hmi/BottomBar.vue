<template>
  <div class="relative z-[1100] shrink-0">
    <!-- 抽屉覆盖层 -->
    <template v-if="drawer">
      <div class="animate-slide-in-bottom absolute inset-x-3 bottom-full mb-2 max-h-[72vh] overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
        <div class="flex h-12 items-center justify-between border-b border-border px-4">
          <div class="flex items-center gap-2">
            <Wind v-if="drawer === 'climate'" class="h-4 w-4 text-primary" />
            <Music v-else-if="drawer === 'music'" class="h-4 w-4 text-primary" />
            <Hand v-else class="h-4 w-4 text-primary" />
            <span class="text-sm font-semibold">{{ drawer === 'climate' ? '车辆温控' : drawer === 'music' ? '媒体中心' : 'EdgeGuard 手势指令' }}</span>
            <span class="text-xs text-muted-foreground">控制变更将发送至车辆接口</span>
          </div>
          <button type="button" aria-label="关闭控制抽屉" class="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground" @click="drawer = null"><X class="h-4 w-4" /></button>
        </div>
        <div :class="cn('overflow-y-auto p-4', drawer === 'gesture' ? 'max-h-[60vh]' : 'max-h-[calc(72vh-48px)]')">
          <ClimateControl v-if="drawer === 'climate'" />
          <GestureControl v-if="drawer === 'gesture'" :headers="headers" />
          <!-- 音乐面板 -->
          <div v-if="drawer === 'music'" class="space-y-4">
            <!-- 搜索 -->
            <div class="flex gap-2">
              <input v-model="musicSearch" placeholder="搜索歌曲…" class="h-9 flex-1 rounded-lg bg-secondary px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-primary/40" @keydown.enter="doMusicSearch" />
              <button type="button" class="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15 text-primary hover:bg-primary/25" @click="doMusicSearch"><Search class="h-4 w-4" /></button>
            </div>
            <!-- 当前播放 -->
            <div class="flex items-center gap-5 rounded-2xl bg-secondary/60 p-5">
              <img v-if="musicState.current_song?.cover" :src="musicState.current_song.cover" class="h-20 w-20 rounded-2xl object-cover" alt="封面" />
              <div v-else class="flex h-20 w-20 items-center justify-center rounded-2xl bg-primary/15"><Music class="h-8 w-8 text-primary" /></div>
              <div class="min-w-0 flex-1">
                <div class="text-lg font-semibold">{{ musicState.current_song?.name || '未在播放' }}</div>
                <div class="mt-1 text-sm text-muted-foreground">{{ musicState.current_song?.artist || '' }}</div>
                <div v-if="musicError" class="mt-2 text-xs text-danger">{{ musicError }}</div>
                <div class="mt-4 h-1.5 overflow-hidden rounded-full bg-card"><div class="h-full w-2/5 bg-primary" /></div>
              </div>
            </div>
            <!-- 控件 -->
            <div class="flex items-center justify-center gap-4">
              <button type="button" aria-label="上一首" class="flex h-11 w-11 items-center justify-center rounded-full bg-card text-muted-foreground hover:bg-accent hover:text-foreground" @click="musicPrev"><SkipBack class="h-5 w-5" /></button>
              <button type="button" :aria-label="musicState.playing ? '暂停' : '播放'" class="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground hover:opacity-90" @click="musicTogglePlay">
                <Pause v-if="musicState.playing" class="h-5 w-5" /><Play v-else class="h-5 w-5" />
              </button>
              <button type="button" aria-label="下一首" class="flex h-11 w-11 items-center justify-center rounded-full bg-card text-muted-foreground hover:bg-accent hover:text-foreground" @click="musicNext"><SkipForward class="h-5 w-5" /></button>
            </div>
            <!-- 音量 -->
            <div class="flex items-center gap-2">
              <Volume1 class="h-4 w-4 shrink-0 text-muted-foreground" />
              <input type="range" min="0" max="100" :value="musicState.volume" @input="setVolume" class="h-1 flex-1 accent-primary" />
              <span class="w-8 text-right text-[11px] tabular-nums text-muted-foreground">{{ musicState.volume }}</span>
            </div>
            <!-- 搜索结果 -->
            <div v-if="searchResults.length > 0" class="max-h-40 space-y-1 overflow-y-auto">
              <div v-for="song in searchResults" :key="song.id" class="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-secondary" @click="playSong(song.id)">
                <div class="min-w-0 flex-1"><div class="truncate text-xs font-medium">{{ song.name }}</div><div class="truncate text-[10px] text-muted-foreground">{{ song.artist }}</div></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 底部快捷栏 -->
    <div class="flex h-16 items-center gap-2 border-t border-border bg-card/95 px-3 backdrop-blur-xl">
      <button type="button"
        :class="cn('flex h-11 min-w-0 items-center gap-2 rounded-xl px-3 transition-colors',
          drawer === 'climate' ? 'bg-primary/15 text-primary ring-1 ring-primary/30' : 'bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground')"
        @click="toggle('climate')">
        <Wind class="h-5 w-5 shrink-0" />
        <span class="min-w-0 text-left"><span class="block text-[10px] leading-none text-muted-foreground">双区空调</span><span class="mt-1 block truncate text-xs font-medium">{{ hvacSummary }}</span></span>
      </button>
      <button type="button"
        :class="cn('flex h-11 min-w-0 items-center gap-2 rounded-xl px-3 transition-colors',
          drawer === 'music' ? 'bg-primary/15 text-primary ring-1 ring-primary/30' : 'bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground')"
        @click="toggle('music')">
        <Music class="h-5 w-5 shrink-0" />
        <span class="min-w-0 text-left"><span class="block text-[10px] leading-none text-muted-foreground">媒体</span><span class="mt-1 block truncate text-xs font-medium">{{ musicState.playing ? (musicState.current_song?.name || '播放中') : '已暂停' }}</span></span>
      </button>
      <button type="button"
        :class="cn('flex h-11 min-w-0 items-center gap-2 rounded-xl px-3 transition-colors',
          drawer === 'gesture' ? 'bg-primary/15 text-primary ring-1 ring-primary/30' : 'bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground')"
        @click="toggle('gesture')">
        <Hand class="h-5 w-5 shrink-0" />
        <span class="min-w-0 text-left"><span class="block text-[10px] leading-none text-muted-foreground">手势</span><span class="mt-1 block truncate text-xs font-medium">{{ gestureName || '监测中' }}</span></span>
      </button>
      <div class="ml-auto">
        <button v-if="!aiOpen" type="button" class="flex h-11 items-center gap-2 rounded-xl bg-primary/15 px-4 text-primary hover:bg-primary/25" @click="$emit('openAi')">
          <Sparkles class="h-5 w-5" /><span class="text-sm font-medium">AI 副驾</span>
        </button>
      </div>
    </div>
  </div>

  <!-- 音频播放器（隐藏） -->
  <audio ref="audioRef" autoplay crossorigin="anonymous" class="hidden" />
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import type { CameraHeaders } from '@/composables/useTelemetry'
import { Hand, Music, Pause, Play, Search, SkipBack, SkipForward, Sparkles, Volume1, Wind, X } from '@lucide/vue'
import { cn } from '@/lib/utils'
import ClimateControl from './ClimateControl.vue'
import GestureControl from './GestureControl.vue'
import type { MusicState, SongInfo } from '@/lib/edgeguard'

const props = defineProps<{ aiOpen: boolean; gestureName?: string; headers?: CameraHeaders }>()
defineEmits<{ openAi: [] }>()

type Drawer = 'climate' | 'music' | 'gesture' | null
const drawer = ref<Drawer>(null)

function toggle(d: Drawer) { drawer.value = drawer.value === d ? null : d }

// AC 摘要（与 ClimateControl 共享状态，此处简化读取）
const acTemp = ref(24)
const acPower = ref(false)
const hvacSummary = computed(() => acPower.value ? `${acTemp}°` : '空调关')

// Music 状态（真实后端 API）
const musicState = ref<MusicState>({ playing: false, current_song: { id: 0, name: '', artist: '', album: '', url: '', cover: '', duration: 0 }, playlist: [], playlist_index: -1, volume: 80 })

// ── 音频播放器 ──
const audioRef = ref<HTMLAudioElement | null>(null)
const musicError = ref('')

async function playCurrentAudio() {
  const audio = audioRef.value
  const url = musicState.value.current_song?.url
  if (!audio || !url) {
    musicError.value = musicState.value.message || '无可播放的音频源'
    return
  }
  const absoluteUrl = new URL(url, window.location.origin).href
  if (audio.src !== absoluteUrl) {
    audio.src = url
    audio.load()
  }
  audio.volume = musicState.value.volume / 100
  try {
    await audio.play()
    musicError.value = ''
  } catch (err) {
    // 浏览器自动播放策略阻止 → 回退 playing 状态，提示用户手动点击播放
    const msg = err instanceof Error ? err.message : ''
    if (msg.includes('NotAllowed') || msg.includes('not allowed')) {
      musicState.value = { ...musicState.value, playing: false }
      musicError.value = '浏览器阻止自动播放，请点击下方播放按钮'
    } else {
      musicError.value = msg || '音频播放失败'
    }
  }
}

function syncMusicState(data: MusicState, status = 'ok', message = '') {
  musicState.value = { ...musicState.value, ...data }
  musicError.value = message || data.message || ''
  if (status === 'ok' && musicState.value.playing) void playCurrentAudio()
}

watch(() => musicState.value.current_song?.url, (url) => {
  if (!url || !audioRef.value) return
  audioRef.value.src = url
  audioRef.value.load()
  if (musicState.value.playing) {
    void playCurrentAudio()
  }
})

watch(() => musicState.value.playing, (playing) => {
  if (!audioRef.value) return
  if (playing) {
    if (audioRef.value.src && audioRef.value.paused) {
      void playCurrentAudio()
    }
  } else {
    audioRef.value.pause()
  }
})
const musicSearch = ref('')
const searchResults = ref<SongInfo[]>([])
let musicPollTimer: ReturnType<typeof setInterval> | undefined

async function fetchMusicState() {
  try {
    const r = await fetch('/api/music/state'); const d = await r.json()
    if (d.data) syncMusicState(d.data, d.status, d.message)
  } catch { /* ignore */ }
}
async function doMusicSearch() {
  const kw = musicSearch.value.trim(); if (!kw) return
  try {
    const r = await fetch('/api/music/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ keyword: kw }) })
    const d = await r.json()
    if (d.status === 'ok') searchResults.value = d.songs || []
  } catch { /* ignore */ }
}
async function playSong(id: number) {
  try {
    const r = await fetch('/api/music/play', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ song_id: id }) })
    const d = await r.json()
    if (d.data) { syncMusicState(d.data, d.status, d.message); searchResults.value = []; musicSearch.value = '' }
  } catch { /* ignore */ }
}
async function musicTogglePlay() {
  try {
    const r = await fetch('/api/music/pause', { method: 'POST' }); const d = await r.json()
    if (d.data) syncMusicState(d.data, d.status, d.message)
  } catch { /* ignore */ }
}
async function musicNext() {
  try {
    const r = await fetch('/api/music/next', { method: 'POST' }); const d = await r.json()
    if (d.data) syncMusicState(d.data, d.status, d.message)
  } catch { /* ignore */ }
}
async function musicPrev() {
  try {
    const r = await fetch('/api/music/prev', { method: 'POST' }); const d = await r.json()
    if (d.data) syncMusicState(d.data, d.status, d.message)
  } catch { /* ignore */ }
}

async function setVolume(e: Event) {
  const vol = parseInt((e.target as HTMLInputElement).value)
  musicState.value.volume = vol
  if (audioRef.value) audioRef.value.volume = vol / 100
  try {
    await fetch('/api/music/volume', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ volume: vol }) })
  } catch { /* ignore */ }
}

// 加载 AC 温度用于底栏摘要
async function fetchAcTemp() {
  try {
    const r = await fetch('/api/ac/state'); const d = await r.json()
    if (d.status === 'ok' && d.data) { acTemp.value = d.data.temperature ?? 24; acPower.value = d.data.power ?? false }
  } catch { /* ignore */ }
}

onMounted(() => { fetchAcTemp(); fetchMusicState(); musicPollTimer = setInterval(fetchMusicState, 2000) })
onUnmounted(() => { if (musicPollTimer) clearInterval(musicPollTimer) })
</script>
