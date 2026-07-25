import { ref, onMounted, onUnmounted, readonly } from 'vue'
import { initialTelemetry, type SafetyAlert, type SafetyLevel, type Telemetry } from '@/lib/edgeguard'

export interface CameraHeaders {
  gaze: string
  gesture: string
  action: string
  perclos: number
  blinkRate: number
  fatigueScore: number
  fatigueLevel: string
  severity: string
  alertFlag: boolean
  alertCategory: string
  alertLabel: string
  gestureHint: string
  gestureAction: string
  confidence: number
  speech: string
  durCrowd: number
  durAbsence: number
  durFatigue: number
  durHead: number
  durGaze: number
}

function emptyHeaders(): CameraHeaders {
  return {
    gaze: '', gesture: '', action: '', perclos: 0, blinkRate: 0,
    fatigueScore: 0, fatigueLevel: 'normal', severity: 'normal',
    alertFlag: false, alertCategory: '', alertLabel: '',
    gestureHint: '', gestureAction: '', confidence: 0, speech: '',
    durCrowd: 0, durAbsence: 0, durFatigue: 0, durHead: 0, durGaze: 0,
  }
}

/**
 * 实时遥测 — 从 /api/camera/frame 响应头提取驾驶员状态。
 *
 * 每 200ms 拉取一次摄像头帧，解析响应头中的各种感知数据，
 * 转换为 Telemetry + CameraHeaders 供 SafetyPanel / AttentionRing 等组件消费。
 * 同时暴露 onAlert 回调，DashboardView 可注册以收集告警历史。
 */
export function useTelemetry() {
  const telemetry = ref<Telemetry>({ ...initialTelemetry })
  const cameraReady = ref(false)
  const headers = ref<CameraHeaders>(emptyHeaders())
  const showLandmarks = ref(true)

  let timer: ReturnType<typeof setInterval> | undefined
  const POLL_MS = 200
  const alertCallbacks: Array<(h: CameraHeaders) => void> = []

  /** 注册告警回调（DashboardView 用于收集 alertHistory） */
  function onAlert(fn: (h: CameraHeaders) => void) {
    alertCallbacks.push(fn)
  }

  function computeAttention(gaze: string, perclos: number, fatigueScore: number): number {
    let score = 100
    if (gaze !== 'center' && gaze !== '') score -= 25
    if (perclos > 0.3) score -= 30
    else if (perclos > 0.15) score -= 15
    if (fatigueScore > 60) score -= 20
    else if (fatigueScore > 30) score -= 10
    return Math.max(0, Math.min(100, Math.round(score)))
  }

  function computeGazeOnRoad(gaze: string): number {
    switch (gaze) {
      case 'center': return 94
      case 'left': case 'right': return 60
      case 'up': return 40
      case 'down': return 30
      default: return 90
    }
  }

  function computeLevel(fatigueLevel: string, severity: string, alertFlag: boolean): SafetyLevel {
    if (fatigueLevel === 'severe' || severity === 'severe') return 'dangerous'
    if (fatigueLevel === 'danger') return 'dangerous'
    if (alertFlag && (fatigueLevel === 'moderate' || severity === 'warn')) return 'distracted'
    if (fatigueLevel === 'moderate' || fatigueLevel === 'warning') return 'attn_declining'
    return 'normal'
  }

  async function poll() {
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 2000)
      const resp = await fetch(`/api/camera/frame?t=${Date.now()}&landmarks=${showLandmarks.value ? '1' : '0'}`, { signal: controller.signal })
      clearTimeout(timeout)

      if (!resp.ok) { cameraReady.value = false; return }
      cameraReady.value = true

      const h: CameraHeaders = {
        gaze: resp.headers.get('X-Gaze') || '',
        gesture: resp.headers.get('X-Gesture') || '',
        action: resp.headers.get('X-Action') || '',
        perclos: parseFloat(resp.headers.get('X-Perclos') || '0'),
        blinkRate: parseFloat(resp.headers.get('X-BlinkRate') || '0'),
        fatigueScore: parseFloat(resp.headers.get('X-FatigueScore') || '0'),
        fatigueLevel: resp.headers.get('X-FatigueLevel') || 'normal',
        severity: resp.headers.get('X-Severity') || 'normal',
        alertFlag: resp.headers.get('X-Alert') === '1',
        alertCategory: resp.headers.get('X-AlertCategory') || '',
        alertLabel: resp.headers.get('X-AlertLabel') || '',
        gestureHint: resp.headers.get('X-GestureHint') || '',
        gestureAction: resp.headers.get('X-GestureAction') || '',
        confidence: parseFloat(resp.headers.get('X-Confidence') || '0'),
        speech: resp.headers.get('X-Speech') || '',
        durCrowd: parseFloat(resp.headers.get('X-DurCrowd') || '0'),
        durAbsence: parseFloat(resp.headers.get('X-DurAbsence') || '0'),
        durFatigue: parseFloat(resp.headers.get('X-DurFatigue') || '0'),
        durHead: parseFloat(resp.headers.get('X-DurHead') || '0'),
        durGaze: parseFloat(resp.headers.get('X-DurGaze') || '0'),
      }
      headers.value = h

      telemetry.value = {
        attention: computeAttention(h.gaze, h.perclos, h.fatigueScore),
        fatigue: Math.round(h.fatigueScore),
        gazeOnRoad: computeGazeOnRoad(h.gaze),
        blinkRate: Math.round(h.blinkRate),
        level: computeLevel(h.fatigueLevel, h.severity, h.alertFlag),
      }

      // 触发告警回调
      if (h.alertFlag) {
        for (const cb of alertCallbacks) cb(h)
      }
    } catch {
      cameraReady.value = false
    }
  }

  onMounted(() => {
    poll()
    timer = setInterval(poll, POLL_MS)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
  })

  return {
    telemetry: readonly(telemetry),
    cameraReady: readonly(cameraReady),
    headers: readonly(headers),
    showLandmarks,
    onAlert,
  }
}
