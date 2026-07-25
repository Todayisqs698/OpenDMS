<template>
  <div class="relative h-full overflow-hidden rounded-2xl border border-border bg-card">
    <!-- Leaflet map container -->
    <div ref="mapContainer" class="absolute inset-0 h-full w-full" />

    <!-- Top nav info bar -->
    <div class="absolute inset-x-3 top-3 z-[1000] flex items-center justify-between gap-3 rounded-xl bg-card/85 px-4 py-2.5 backdrop-blur-md">
      <div class="flex items-center gap-3">
        <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15">
          <Navigation class="h-5 w-5 text-primary" />
        </div>
        <div>
          <div class="text-sm font-medium">{{ nav.nextTurn || '导航待命中' }}</div>
          <div class="text-xs text-muted-foreground">
            <template v-if="nav.destination">
              目的地 {{ nav.destination }}
            </template>
            <template v-else>
              说出"导航到..."开始规划路线
            </template>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-4 text-right">
        <div>
          <div class="font-mono text-lg font-semibold tabular-nums text-primary">
            {{ nav.etaMin || '--' }}<span class="ml-0.5 text-xs font-normal text-muted-foreground">分钟</span>
          </div>
          <div class="text-[11px] text-muted-foreground">{{ nav.distanceKm || '--' }} km</div>
        </div>
      </div>
    </div>

    <!-- Camera PiP (driver monitor) -->
    <button
      type="button"
      :aria-label="camLarge ? '缩小摄像头' : '放大摄像头'"
      :class="cn(
        'group absolute right-3 z-[1000] overflow-hidden rounded-xl border border-border bg-card shadow-lg transition-all duration-300',
        camLarge ? 'top-20 h-48 w-72' : 'top-20 h-40 w-56',
      )"
      @click="camLarge = !camLarge"
    >
      <canvas
        ref="cameraCanvas"
        width="640"
        height="480"
        class="h-full w-full object-cover"
      />
      <img
        v-if="!cameraReady"
        src="/images/driver-cam.png"
        alt="驾驶员监测摄像头画面"
        class="absolute inset-0 h-full w-full object-cover"
      />
      <div class="absolute left-2 top-2 flex items-center gap-1.5 rounded-full bg-background/70 px-2 py-0.5 backdrop-blur">
        <span :class="cn('h-1.5 w-1.5 rounded-full', cameraReady ? 'animate-hmi-breathe bg-danger' : 'bg-muted-foreground')" />
        <span class="text-[10px] font-medium">驾驶员监测</span>
      </div>
      <div class="absolute bottom-2 right-2 flex h-6 w-6 items-center justify-center rounded-md bg-background/70 opacity-0 backdrop-blur transition-opacity group-hover:opacity-100">
        <Maximize2 class="h-3.5 w-3.5" />
      </div>
    </button>

    <!-- Speed display -->
    <div class="absolute bottom-3 left-3 z-[1000] flex items-end gap-3 rounded-xl bg-card/85 px-4 py-2.5 backdrop-blur-md">
      <div class="text-center">
        <div class="font-mono text-3xl font-semibold leading-none tabular-nums">
          {{ nav.speed || '--' }}
        </div>
        <div class="mt-1 text-[10px] text-muted-foreground">km/h</div>
      </div>
      <div class="flex h-11 w-11 flex-col items-center justify-center rounded-full border-2 border-danger">
        <span class="font-mono text-sm font-semibold leading-none tabular-nums">
          {{ nav.speedLimit || '--' }}
        </span>
      </div>
    </div>

    <!-- Map controls -->
    <div class="absolute bottom-3 right-3 z-[1000] flex flex-col gap-2">
      <button
        type="button"
        aria-label="定位"
        class="flex h-10 w-10 items-center justify-center rounded-xl bg-card/85 text-primary backdrop-blur-md transition-colors hover:bg-card"
        @click="locateMe"
      >
        <MapPin class="h-5 w-5" />
      </button>
      <div class="flex flex-col overflow-hidden rounded-xl bg-card/85 backdrop-blur-md">
        <button
          type="button"
          aria-label="放大"
          class="flex h-10 w-10 items-center justify-center transition-colors hover:bg-secondary"
          @click="zoomIn"
        >
          <Plus class="h-5 w-5" />
        </button>
        <div class="h-px bg-border" />
        <button
          type="button"
          aria-label="缩小"
          class="flex h-10 w-10 items-center justify-center transition-colors hover:bg-secondary"
          @click="zoomOut"
        >
          <Minus class="h-5 w-5" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Navigation, Plus, Minus, MapPin, Maximize2 } from '@lucide/vue'
import { cn } from '@/lib/utils'
import type { NavInfo } from '@/lib/edgeguard'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const props = defineProps<{
  nav: NavInfo
  cameraReady: boolean
}>()

const camLarge = ref(false)
const cameraCanvas = ref<HTMLCanvasElement | null>(null)
const mapContainer = ref<HTMLDivElement | null>(null)
let mapInstance: L.Map | null = null
let currentMarker: L.Marker | null = null

// ── Leaflet map init ──
function initMap() {
  if (!mapContainer.value || mapInstance) return

  mapInstance = L.map(mapContainer.value, {
    center: [31.2304, 121.4737],  // Shanghai default
    zoom: 14,
    zoomControl: false,
    attributionControl: false,
  })

  // Light tile layer (OpenStreetMap — free, no key)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(mapInstance)
}

// ── Navigation functions ──
function locateMe() {
  if (!mapInstance) return
  if ('geolocation' in navigator) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords
        mapInstance!.setView([latitude, longitude], 16)
        if (currentMarker) currentMarker.remove()
        currentMarker = L.marker([latitude, longitude])
          .addTo(mapInstance!)
          .bindPopup('当前位置')
          .openPopup()
      },
      () => {
        // Fallback to Shanghai
        mapInstance!.setView([31.2304, 121.4737], 14)
      },
      { enableHighAccuracy: true, timeout: 5000 },
    )
  }
}

function zoomIn() { mapInstance?.zoomIn() }
function zoomOut() { mapInstance?.zoomOut() }

// Watch nav destination changes to fly to location
watch(() => props.nav.destination, async (dest) => {
  if (!dest || !mapInstance) return
  // Geocode destination with Nominatim
  try {
    const resp = await fetch(
      `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(dest)}&limit=1`
    )
    const data = await resp.json()
    if (data[0]) {
      const { lat, lon } = data[0]
      mapInstance!.setView([parseFloat(lat), parseFloat(lon)], 14)
      if (currentMarker) currentMarker.remove()
      currentMarker = L.marker([parseFloat(lat), parseFloat(lon)])
        .addTo(mapInstance!)
        .bindPopup(dest)
        .openPopup()
    }
  } catch { /* geocode failed */ }
})

// ── Camera frame rendering ──
let camTimer: ReturnType<typeof setInterval> | undefined
let camCtx: CanvasRenderingContext2D | null = null

async function renderCameraFrame() {
  if (!cameraCanvas.value) return
  if (!camCtx) {
    camCtx = cameraCanvas.value.getContext('2d')
    if (!camCtx) return
  }

  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 2000)
    const resp = await fetch(`/api/camera/frame?t=${Date.now()}`, {
      signal: controller.signal,
    })
    clearTimeout(timeout)
    if (!resp.ok) return

    const blob = await resp.blob()
    const img = new Image()
    const url = URL.createObjectURL(blob)

    await new Promise<void>((resolve, reject) => {
      img.onload = () => { URL.revokeObjectURL(url); resolve() }
      img.onerror = () => { URL.revokeObjectURL(url); reject() }
      img.src = url
    })

    const canvas = cameraCanvas.value!
    camCtx!.drawImage(img, 0, 0, canvas.width, canvas.height)
  } catch { /* ignore */ }
}

onMounted(async () => {
  await nextTick()
  initMap()
  locateMe()
  renderCameraFrame()
  camTimer = setInterval(renderCameraFrame, 200)
})

onUnmounted(() => {
  if (camTimer) clearInterval(camTimer)
  if (mapInstance) { mapInstance.remove(); mapInstance = null }
})
</script>
