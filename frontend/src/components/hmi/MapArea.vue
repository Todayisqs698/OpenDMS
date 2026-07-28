<template>
  <div class="relative h-full min-h-[300px] overflow-hidden rounded-2xl border border-border bg-card">
    <!-- Leaflet map container -->
    <div ref="mapContainer" class="absolute inset-0 h-full w-full" style="z-index:0" />

    <!-- Top nav info bar -->
    <div class="absolute inset-x-3 top-3 z-[1000] flex items-center justify-between gap-3 rounded-xl bg-card/85 px-4 py-2.5 backdrop-blur-md">
      <div class="flex items-center gap-3">
        <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15">
          <Navigation class="h-5 w-5 text-primary" />
        </div>
        <div class="min-w-0">
          <div class="truncate text-sm font-medium">{{ nav.nextTurn || '导航待命中' }}</div>
          <div class="text-xs text-muted-foreground">
            <template v-if="nav.destination">
              目的地 {{ nav.destination }}
            </template>
            <template v-else>
              说出"导航到..."开始规划路线
            </template>
          </div>
          <div v-if="nav.destination" class="mt-0.5 text-[10px]" :class="originStatusClass">
            {{ originStatusText }}
            <span v-if="nav.routeSource" class="ml-1 text-muted-foreground/70">· {{ nav.routeSource === 'amap' ? '高德路线' : nav.routeSource === 'osrm' ? 'OSRM路线' : '估算' }}</span>
          </div>
        </div>
      </div>
      <div class="flex shrink-0 items-center gap-4 text-right">
        <div>
          <div class="font-mono text-lg font-semibold tabular-nums text-primary">
            {{ nav.etaMin || '--' }}<span class="ml-0.5 text-xs font-normal text-muted-foreground">分钟</span>
          </div>
          <div class="text-[11px] text-muted-foreground">{{ nav.distanceKm || '--' }} km</div>
        </div>
      </div>
    </div>

    <!-- Route steps panel (when navigation steps available) -->
    <div v-if="nav.steps && nav.steps.length > 0" class="absolute left-3 top-20 z-[1000] w-64 max-h-[45%] overflow-y-auto rounded-xl bg-card/90 p-3 backdrop-blur-md shadow-lg">
      <div class="mb-2 flex items-center gap-1.5">
        <Route class="h-3.5 w-3.5 text-primary" />
        <span class="text-xs font-semibold">路线指引</span>
        <span class="ml-auto text-[10px] text-muted-foreground">{{ nav.steps.length }} 步</span>
      </div>
      <div class="flex flex-col gap-1.5">
        <div v-for="(step, i) in nav.steps" :key="i" class="flex items-start gap-2 text-xs">
          <span class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/15 font-mono text-[9px] text-primary">{{ i + 1 }}</span>
          <span class="text-foreground/80">{{ step }}</span>
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
import { computed, ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Navigation, Plus, Minus, MapPin, Maximize2, Route } from '@lucide/vue'
import { cn } from '@/lib/utils'
import type { NavInfo } from '@/lib/edgeguard'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const props = defineProps<{
  nav: NavInfo
  cameraReady: boolean
  visible: boolean
}>()

const camLarge = ref(false)

// v-show 隐藏再显示时 Leaflet 需要重新计算容器尺寸
watch(() => props.visible, (v) => {
  if (v && mapInstance) {
    nextTick(() => mapInstance!.invalidateSize())
  }
})
const cameraCanvas = ref<HTMLCanvasElement | null>(null)
const mapContainer = ref<HTMLDivElement | null>(null)
let mapInstance: L.Map | null = null
let currentMarker: L.Marker | null = null
let routeLayer: L.Polyline | null = null
let originMarker: L.Marker | null = null
let destinationMarker: L.Marker | null = null
let geocodeRequestSeq = 0

const originStatusText = computed(() => {
  if (props.nav.originSource === 'fallback_shanghai') return '起点：默认上海市中心（未获取真实定位）'
  if (props.nav.originSource) return '起点：真实定位'
  return props.nav.originCoords ? '起点：已定位' : '起点：等待定位'
})

const originStatusClass = computed(() =>
  props.nav.originSource === 'fallback_shanghai' ? 'text-amber-400' : 'text-emerald-400',
)

// ── Leaflet map init ──
function initMap() {
  if (!mapContainer.value || mapInstance) return

  mapInstance = L.map(mapContainer.value, {
    center: [31.2304, 121.4737],  // Shanghai default
    zoom: 14,
    zoomControl: false,
    attributionControl: false,
  })

  // 高德地图瓦片（国内可访问，无需翻墙）
  L.tileLayer(
    'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    {
      subdomains: ['1', '2', '3', '4'],
      maxZoom: 19,
      attribution: '&copy; 高德地图',
    },
  ).addTo(mapInstance)
}

// ── Navigation functions ──
function flyTo(lat: number, lng: number, zoom = 16, label = '当前位置') {
  if (!mapInstance) return
  clearRoute()
  mapInstance.setView([lat, lng], zoom)
  if (currentMarker) currentMarker.remove()
  currentMarker = L.marker([lat, lng]).addTo(mapInstance).bindPopup(label).openPopup()
}

function reportLocation(lat: number, lng: number) {
  const body = JSON.stringify({ lat, lon: lng })
  fetch('/api/location', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  }).catch(() => {})

  const params = new URLSearchParams({ lat: String(lat), lon: String(lng) })
  fetch(`/api/gps/update?${params.toString()}`, { method: 'POST' }).catch(() => {})
}

function clearRoute() {
  routeLayer?.remove()
  originMarker?.remove()
  destinationMarker?.remove()
  routeLayer = null
  originMarker = null
  destinationMarker = null
}

function setRouteMarker(coords: [number, number], label: string, role: 'origin' | 'destination') {
  if (!mapInstance) return null
  // 高德风格标记：圆形带字母 A(起点/绿色) 或 B(终点/红色)
  const color = role === 'origin' ? '#22c55e' : '#ef4444'
  const letter = role === 'origin' ? 'A' : 'B'
  const icon = L.divIcon({
    className: 'nav-route-marker',
    html: `<div style="
      display:flex;align-items:center;justify-content:center;
      width:28px;height:28px;border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);
      background:${color};border:2px solid #fff;
      box-shadow:0 2px 6px rgba(0,0,0,0.4);
    "><span style="transform:rotate(45deg);color:#fff;font-weight:700;font-size:12px;">${letter}</span></div>`,
    iconSize: [28, 28],
    iconAnchor: [4, 28],  // 锚点在底部尖端
  })
  const marker = L.marker(coords, { icon }).addTo(mapInstance).bindPopup(label)
  return marker
}

function renderRoute() {
  if (!mapInstance) return false
  // 确保地图容器尺寸正确（容器从隐藏切换到可见时 Leaflet 需要重新计算）
  mapInstance.invalidateSize()
  const geometry = props.nav.geometry?.filter(
    (point): point is [number, number] =>
      Array.isArray(point) &&
      point.length === 2 &&
      Number.isFinite(point[0]) &&
      Number.isFinite(point[1]),
  ) || []
  const origin = props.nav.originCoords
  const destination = props.nav.destinationCoords

  if (geometry.length < 2 && !destination) return false

  clearRoute()
  if (currentMarker) {
    currentMarker.remove()
    currentMarker = null
  }

  if (geometry.length >= 2) {
    routeLayer = L.polyline(geometry, {
      color: '#0ea5e9',
      weight: 7,
      opacity: 0.9,
      lineCap: 'round',
      lineJoin: 'round',
    }).addTo(mapInstance)
  }

  if (origin) originMarker = setRouteMarker(origin, '起点', 'origin')
  if (destination) destinationMarker = setRouteMarker(destination, props.nav.destination || '目的地', 'destination')

  const boundsPoints = [
    ...(routeLayer ? routeLayer.getLatLngs() as L.LatLng[] : []),
    ...(origin ? [L.latLng(origin[0], origin[1])] : []),
    ...(destination ? [L.latLng(destination[0], destination[1])] : []),
  ]
  if (boundsPoints.length > 0) {
    mapInstance.fitBounds(L.latLngBounds(boundsPoints), { padding: [56, 56], maxZoom: 15 })
  }
  destinationMarker?.openPopup()
  return true
}

function locateMe() {
  if (!mapInstance) return
  if (!('geolocation' in navigator)) {
    flyTo(31.2304, 121.4737, 14)  // 无 GPS → 上海默认
    return
  }
  // 两级降级：高精度 8s → 低精度 15s → 上海默认
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const { latitude, longitude } = pos.coords
      reportLocation(latitude, longitude)
      flyTo(latitude, longitude)
    },
    () => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const { latitude, longitude } = pos.coords
          reportLocation(latitude, longitude)
          flyTo(latitude, longitude)
        },
        () => { flyTo(31.2304, 121.4737, 14) },
        { enableHighAccuracy: false, timeout: 15000 },
      )
    },
    { enableHighAccuracy: true, timeout: 8000 },
  )
}

function zoomIn() { mapInstance?.zoomIn() }
function zoomOut() { mapInstance?.zoomOut() }

// Watch nav destination changes to fly to location
watch(() => props.nav.destination, async (dest) => {
  if (!dest || !mapInstance) return
  // 如果已有路线数据（geometry 或坐标），直接渲染路线，不走 geocode 降级
  if (renderRoute()) return
  const seq = ++geocodeRequestSeq
  // 通过后端代理调用高德地理编码（避免暴露 API Key）
  try {
    const resp = await fetch(`/api/map/geocode?address=${encodeURIComponent(dest)}`)
    const data = await resp.json()
    if (seq !== geocodeRequestSeq) return
    // 二次检查：geocode 期间路线数据可能已到达，此时不应覆盖已渲染的路线
    if (props.nav.geometry?.length || props.nav.destinationCoords) {
      renderRoute()
      return
    }
    if (data.success && data.lat != null && data.lng != null) {
      clearRoute()
      mapInstance!.setView([data.lat, data.lng], 14)
      if (currentMarker) currentMarker.remove()
      currentMarker = L.marker([data.lat, data.lng])
        .addTo(mapInstance!)
        .bindPopup(data.formatted || dest)
        .openPopup()
    }
  } catch { /* geocode failed */ }
})

// Watch route data changes — 用 geometry.length 替代 deep watch，
// 避免 8000+ 点的 geometry 数组深度遍历导致卡顿
watch(
  () => [
    props.nav.geometry?.length || 0,
    props.nav.originCoords?.[0] || 0,
    props.nav.destinationCoords?.[0] || 0,
    props.nav.destination,
  ],
  () => {
    if (mapInstance) renderRoute()
  },
)

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
  clearRoute()
  if (mapInstance) { mapInstance.remove(); mapInstance = null }
})
</script>
