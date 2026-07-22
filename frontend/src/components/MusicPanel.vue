<template>
  <section class="panel music-panel">
    <div class="panel-header">
      <h2 class="panel-title">Music Player</h2>
      <span class="music-badge" :class="{ playing: music.playing }">{{ music.playing ? 'PLAYING' : 'STOPPED' }}</span>
    </div>

    <div class="music-body">
      <!-- 搜索 -->
      <div class="music-search">
        <input v-model="keyword" class="music-input" placeholder="搜索歌曲/歌手..."
          @keyup.enter="search" />
        <button class="music-btn search" @click="search" :disabled="!keyword.trim()">🔍</button>
      </div>

      <!-- 搜索结果 -->
      <div v-if="results.length" class="music-results">
        <div v-for="s in results" :key="s.id" class="music-result-item"
          :class="{ active: music.current_song.id === s.id }"
          @click="playSong(s)">
          <span class="mr-name">{{ s.name }}</span>
          <span class="mr-artist">{{ s.artist }}</span>
        </div>
      </div>

      <!-- 当前播放 -->
      <div v-if="music.current_song.id" class="music-now">
        <div class="mn-info">
          <span class="mn-name">{{ music.current_song.name }}</span>
          <span class="mn-artist">{{ music.current_song.artist }}</span>
        </div>
        <!-- 音频播放器 -->
        <audio v-if="music.current_song.url" ref="audioRef"
          :src="music.current_song.url" @play="onPlay" @pause="onPause" @ended="onEnded" autoplay></audio>
        <!-- 进度条 -->
        <div class="mn-progress" @click="seek($event)">
          <div class="mn-progress-fill" :style="{ width: progressPercent + '%' }"></div>
        </div>
        <div class="mn-time">{{ currentTimeStr }} / {{ durationStr }}</div>
      </div>

      <!-- 播放控制 -->
      <div class="music-controls">
        <button class="mc-btn" @click="prevSong" title="上一首">⏮</button>
        <button class="mc-btn play" @click="togglePlay" :class="{ on: music.playing }">
          {{ music.playing ? '⏸' : '▶' }}
        </button>
        <button class="mc-btn" @click="nextSong" title="下一首">⏭</button>
      </div>

      <!-- 音量 -->
      <div class="music-volume">
        <span class="mv-label">🔊</span>
        <input type="range" class="mv-slider" min="0" max="100" v-model.number="volume" @input="setVolume" />
        <span class="mv-val">{{ volume }}%</span>
      </div>

      <!-- 播放列表 -->
      <div v-if="music.playlist.length" class="music-playlist">
        <div class="section-label">Playlist ({{ music.playlist.length }})</div>
        <div v-for="(s, i) in music.playlist" :key="s.id" class="pl-item"
          :class="{ active: i === music.playlist_index }" @click="playAtIndex(i)">
          <span class="pl-idx">{{ i + 1 }}</span>
          <span class="pl-name">{{ s.name }}</span>
          <span class="pl-artist">{{ s.artist }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

const music = ref({
  playing: false,
  current_song: { id: 0, name: '', artist: '', album: '', url: '', cover: '', duration: 0 },
  playlist: [],
  playlist_index: -1,
  volume: 80,
})

const keyword = ref('')
const results = ref([])
const audioRef = ref(null)
const currentTime = ref(0)
const duration = ref(0)
let pollTimer = null
let timeTimer = null

const currentTimeStr = computed(() => formatTime(currentTime.value))
const durationStr = computed(() => formatTime(duration.value))
const progressPercent = computed(() => duration.value ? (currentTime.value / duration.value * 100) : 0)

function formatTime(s) {
  if (!s || isNaN(s)) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

async function fetchState() {
  try {
    const r = await fetch('/api/music/state')
    if (r.ok) {
      const data = await r.json()
      if (data.status === 'ok' && data.data) music.value = { ...music.value, ...data.data }
    }
  } catch (e) {}
}

async function search() {
  const kw = keyword.value.trim()
  if (!kw) return
  results.value = []
  try {
    const r = await fetch('/api/music/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword: kw })
    })
    if (r.ok) {
      const data = await r.json()
      results.value = data.songs || []
    }
  } catch (e) {}
}

async function playSong(song) {
  try {
    const r = await fetch('/api/music/play', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ song_id: song.id, add_to_playlist: true })
    })
    if (r.ok) {
      const data = await r.json()
      if (data.status === 'ok' && data.data) {
        music.value = { ...music.value, ...data.data }
      }
    }
  } catch (e) {}
}

async function playAtIndex(index) {
  try {
    const r = await fetch('/api/music/play_index', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index })
    })
    if (r.ok) {
      const data = await r.json()
      if (data.status === 'ok' && data.data) {
        music.value = { ...music.value, ...data.data }
      }
    }
  } catch (e) {}
}

async function togglePlay() {
  try {
    const r = await fetch('/api/music/pause', { method: 'POST' })
    if (r.ok) {
      const data = await r.json()
      if (data.status === 'ok' && data.data) {
        const newPlaying = data.data.playing
        music.value = { ...music.value, ...data.data }
        // 控制 HTML5 audio 实际播放/暂停
        if (audioRef.value) {
          if (newPlaying) {
            audioRef.value.play().catch(() => {})
          } else {
            audioRef.value.pause()
          }
        }
      }
    }
  } catch (e) {}
}

async function nextSong() {
  try {
    const r = await fetch('/api/music/next', { method: 'POST' })
    if (r.ok) {
      const data = await r.json()
      if (data.status === 'ok' && data.data) music.value = { ...music.value, ...data.data }
    }
  } catch (e) {}
}

async function prevSong() {
  try {
    const r = await fetch('/api/music/prev', { method: 'POST' })
    if (r.ok) {
      const data = await r.json()
      if (data.status === 'ok' && data.data) music.value = { ...music.value, ...data.data }
    }
  } catch (e) {}
}

async function setVolume() {
  try {
    await fetch('/api/music/volume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume: volume.value })
    })
  } catch (e) {}
}

const volume = computed({ get: () => music.value.volume, set: (v) => { music.value.volume = v } })

function onPlay() { music.value.playing = true; startTimer() }
function onPause() { music.value.playing = false; stopTimer() }
function onEnded() { nextSong() }

function seek(e) {
  if (!audioRef.value || !duration.value) return
  const rect = e.currentTarget.getBoundingClientRect()
  const pct = (e.clientX - rect.left) / rect.width
  audioRef.value.currentTime = pct * duration.value
}

function startTimer() {
  stopTimer()
  timeTimer = setInterval(() => {
    if (audioRef.value) currentTime.value = audioRef.value.currentTime || 0
  }, 500)
}
function stopTimer() {
  if (timeTimer) { clearInterval(timeTimer); timeTimer = null }
}

// 暴露方法给父组件（手势/语音触发）
defineExpose({
  async onCommand(command) {
    if (command === 'PlayMusic') { togglePlay() }
    else if (command === 'StopMusic') { if (music.value.playing) togglePlay() }
    else if (command === 'next_track') { nextSong() }
    else if (command === 'previous_track') { prevSong() }
    else if (command === 'volume_up') { volume.value = Math.min(100, volume.value + 10); setVolume() }
    else if (command === 'volume_down') { volume.value = Math.max(0, volume.value - 10); setVolume() }
  },
  async searchAndPlay(text) { keyword.value = text; await search() }
})

onMounted(() => { fetchState(); pollTimer = setInterval(fetchState, 5000) })
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer); stopTimer() })
</script>

<style scoped>
.music-panel { display: flex; flex-direction: column; gap: 8px; }
.panel-header { display: flex; align-items: center; justify-content: space-between; }
.panel-title { margin: 0; font-size: 14px; font-weight: 600; color: #94a3b8; letter-spacing: 0.02em; }

.music-badge {
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
  padding: 2px 8px; border-radius: 4px;
  background: rgba(100,116,139,0.15); color: #64748b;
  border: 1px solid rgba(100,116,139,0.2); transition: all 0.3s;
}
.music-badge.playing {
  background: rgba(96,165,250,0.12); color: #60a5fa;
  border-color: rgba(96,165,250,0.3);
}

.music-body { display: flex; flex-direction: column; gap: 8px; }

.music-search { display: flex; gap: 4px; }
.music-input {
  flex: 1; padding: 7px 10px; background: #1e293b; border: 1px solid #334155;
  border-radius: 6px; color: #e2e8f0; font-size: 12px; outline: none;
}
.music-input:focus { border-color: #3b82f6; }
.music-btn { padding: 7px 10px; border: none; border-radius: 6px; cursor: pointer; background: #1e293b; color: #94a3b8; font-size: 14px; }
.music-btn:disabled { opacity: 0.4; }
.music-btn:hover:not(:disabled) { background: rgba(30,41,59,0.8); }

.music-results { max-height: 120px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #1e293b transparent; }
.music-result-item {
  display: flex; gap: 8px; padding: 5px 8px; border-radius: 5px; cursor: pointer; transition: background 0.2s;
}
.music-result-item:hover { background: rgba(30,41,59,0.6); }
.music-result-item.active { background: rgba(96,165,250,0.08); }
.mr-name { flex: 1; font-size: 11px; color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mr-artist { font-size: 10px; color: #64748b; white-space: nowrap; }

.music-now { display: flex; flex-direction: column; gap: 4px; padding: 10px; background: linear-gradient(135deg, #111827, #0f172a); border-radius: 8px; border: 1px solid #1e293b; }
.mn-info { display: flex; flex-direction: column; gap: 2px; }
.mn-name { font-size: 13px; font-weight: 600; color: #e2e8f0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mn-artist { font-size: 11px; color: #64748b; }
.mn-progress { height: 4px; background: #1e293b; border-radius: 2px; cursor: pointer; }
.mn-progress-fill { height: 100%; background: #3b82f6; border-radius: 2px; transition: width 0.3s; }
.mn-time { font-size: 10px; color: #475569; text-align: right; font-family: monospace; }

.music-controls { display: flex; justify-content: center; gap: 16px; }
.mc-btn {
  width: 36px; height: 36px; border: none; border-radius: 50%; cursor: pointer;
  background: #1e293b; color: #94a3b8; font-size: 16px;
  display: flex; align-items: center; justify-content: center; transition: all 0.2s;
}
.mc-btn:hover { background: #334155; }
.mc-btn.play { width: 42px; height: 42px; font-size: 18px; }
.mc-btn.play.on { background: rgba(96,165,250,0.15); color: #60a5fa; border: 1px solid rgba(96,165,250,0.3); }

.music-volume { display: flex; align-items: center; gap: 6px; padding: 0 4px; }
.mv-label { font-size: 14px; }
.mv-slider { flex: 1; height: 4px; -webkit-appearance: none; background: #1e293b; border-radius: 2px; outline: none; }
.mv-slider::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; border-radius: 50%; background: #60a5fa; cursor: pointer; }
.mv-val { font-size: 10px; color: #475569; min-width: 30px; text-align: right; }

.music-playlist { max-height: 100px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #1e293b transparent; }
.section-label { font-size: 10px; font-weight: 600; color: #475569; text-transform: uppercase; letter-spacing: 0.1em; padding: 4px 0; }
.pl-item { display: flex; gap: 6px; padding: 3px 8px; border-radius: 4px; cursor: pointer; transition: background 0.2s; }
.pl-item:hover { background: rgba(30,41,59,0.6); }
.pl-item.active { background: rgba(96,165,250,0.08); }
.pl-idx { font-size: 10px; color: #475569; min-width: 18px; }
.pl-name { flex: 1; font-size: 10px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pl-artist { font-size: 9px; color: #475569; white-space: nowrap; }
</style>
