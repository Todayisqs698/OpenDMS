import { ref, onMounted, onUnmounted, readonly } from 'vue'
import type { AgentStep, AgentResult, NavInfo, WSMessage } from '@/lib/edgeguard'

/**
 * Agent WebSocket 实时数据流。
 *
 * 连接到 /ws/agent_panel 接收后端广播的结构化消息：
 *   - agent_step       → Agent 思维链步骤
 *   - agent_final      → 最终回复文本
 *   - agent_navigation → 导航结构结果
 *   - agent_weather_query → 天气查询结果
 *   - agent_trip_plan  → 行程规划结果
 *   - agent_error      → 错误信息
 *   - navigation       → 导航规划结果
 *   - ai_decision      → AI 分析决策
 *   - driver_state     → 驾驶员状态
 *
 * 用法：
 *   const { steps, results, finalReply, navInfo, tripPlan, connected } = useAgentWS()
 */
export function useAgentWS() {
  const connected = ref(false)
  const steps = ref<AgentStep[]>([])
  const results = ref<AgentResult[]>([])
  const finalReply = ref('')
  const navInfo = ref<Partial<NavInfo>>({})
  const tripPlan = ref<any>(null)
  const error = ref('')

  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined
  let shouldReconnect = true

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws/agent_panel`

    try {
      ws = new WebSocket(url)
    } catch {
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      connected.value = true
      error.value = ''
    }

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data)
        handleMessage(msg)
      } catch {
        // 非 JSON 消息忽略
      }
    }

    ws.onclose = () => {
      connected.value = false
      scheduleReconnect()
    }

    ws.onerror = () => {
      ws?.close()
    }
  }

  function handleMessage(msg: WSMessage) {
    const { type, data } = msg

    switch (type) {
      // ── Agent 思维链步骤 ──
      case 'agent_step': {
        const step: AgentStep = {
          id: (data.id as string) || `s${Date.now()}`,
          label: (data.label as string) || (data.step as string) || '',
          status: (data.status as AgentStep['status']) || 'running',
        }
        // 更新已有步骤或追加
        const idx = steps.value.findIndex(s => s.id === step.id)
        if (idx >= 0) {
          steps.value = [...steps.value.slice(0, idx), step, ...steps.value.slice(idx + 1)]
        } else {
          steps.value = [...steps.value, step]
        }
        break
      }

      // ── Agent 最终回复 ──
      case 'agent_final': {
        finalReply.value = (data.text as string) || ''
        break
      }

      // ── 导航结果 ──
      case 'agent_navigation':
      case 'navigation': {
        const dist = (data.distance_km as number) ?? (data.distanceKm as number) ?? 0
        const dur = (data.duration_min as number) ?? (data.durationMin as number) ?? 0
        navInfo.value = {
          destination: (data.destination as string) || '',
          distanceKm: dist,
          etaMin: dur,
          nextTurn: (data.route_summary as string) || (data.routeSummary as string) || '',
          originCoords: (data.origin_coords as [number, number] | null) || null,
          destinationCoords: (data.destination_coords as [number, number] | null) || null,
          geometry: (data.geometry as [number, number][]) || [],
          steps: (data.steps as string[]) || [],
          routeSource: (data.source as string) || '',
          coordinateSystem: (data.coordinate_system as string) || '',
        }
        // 也作为 Agent 结果卡展示
        results.value = [
          ...results.value,
          {
            id: `nav-${Date.now()}`,
            type: 'route',
            title: (data.destination as string) || '导航目的地',
            subtitle: `${dist} km · ${dur} 分钟`,
            meta: (data.route_summary as string) || '',
          },
        ]
        break
      }

      // ── 天气结果 ──
      case 'agent_weather_query': {
        const city = (data.city as string) || ''
        const desc = (data.weather_desc as string) || (data.desc as string) || ''
        const temp = data.temperature as number | null
        const ctx = (data.driving_context as string) || ''
        results.value = [
          ...results.value,
          {
            id: `weather-${Date.now()}`,
            type: 'weather',
            title: `${city}天气` || '当前天气',
            subtitle: temp != null ? `${desc} ${temp}°C` : desc,
            meta: ctx || '天气信息',
          },
        ]
        break
      }

      // ── 行程规划结果 ──
      case 'agent_trip_plan': {
        tripPlan.value = data
        break
      }

      // ── 错误 ──
      case 'agent_error': {
        error.value = (data.message as string) || 'Agent 执行出错'
        break
      }

      // ── 忽略其他消息类型 ──
      default:
        break
    }
  }

  function scheduleReconnect() {
    if (!shouldReconnect) return
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(() => {
      if (shouldReconnect) connect()
    }, 3000)
  }

  function disconnect() {
    shouldReconnect = false
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (ws) {
      ws.onclose = null // 防止触发重连
      ws.close()
      ws = null
    }
    connected.value = false
  }

  function clear() {
    steps.value = []
    results.value = []
    finalReply.value = ''
    error.value = ''
  }

  onMounted(() => {
    shouldReconnect = true
    connect()
  })

  onUnmounted(() => {
    disconnect()
  })

  return {
    connected: readonly(connected),
    steps: readonly(steps),
    results: readonly(results),
    finalReply: readonly(finalReply),
    navInfo: readonly(navInfo),
    tripPlan: readonly(tripPlan),
    error: readonly(error),
    clear,
    disconnect,
  }
}
