/**
 * EdgeGuard 数据类型与接口
 * -------------------------------------------------------------
 * 对接后端 REST + WebSocket 端点，同时提供 mock 数据用于离线开发。
 * 真实后端路径见 ENDPOINTS，连接后端时替换 connect* 实现即可。
 */

export const ENDPOINTS = {
  // WebSocket 实时流
  agentPanelWS: '/ws/agent_panel',
  agentResultWS: '/ws/agent_result',
  navPanelWS: '/ws/navpanel',

  // REST — AI
  agentChat: '/api/agent/chat',
  agentQuery: '/api/agent/query',
  agentThinking: '/api/agent/thinking',
  agentOrchestrate: '/api/agent/orchestrate',
  interactionQuery: '/api/interaction/query',

  // REST — 感知
  cameraFrame: '/api/camera/frame',
  analyze: '/api/analyze',
  status: '/api/status',

  // REST — 驾驶
  driveInsight: '/api/drive/insight',
  driveReport: '/api/drive/report',
  navigation: '/api/navigation/route',
  environment: '/api/environment',

  // REST — 车辆控制
  acState: '/api/ac/state',
  acCommand: '/api/ac/command',
  musicState: '/api/music/state',
  musicSearch: '/api/music/search',
  musicPlay: '/api/music/play',
  musicPause: '/api/music/pause',
  musicNext: '/api/music/next',
  musicPrev: '/api/music/prev',
  musicVolume: '/api/music/volume',

  // REST — 位置
  gpsUpdate: '/api/gps/update',
  gpsCurrent: '/api/gps/current',
  location: '/api/location',

  // REST — 其他
  tts: '/api/tts',
  gestures: '/api/gesture/available',
  voiceProcess: '/api/voice/process',
  voiceState: '/api/voice/state',
  dashboardState: '/api/dashboard/state',
} as const

/* ========================== 安全门控 ========================== */

export type SafetyLevel = 'normal' | 'attn_declining' | 'distracted' | 'dangerous'
export type ToolAvailability = 'full' | 'restricted' | 'readonly'

export interface SafetyGateState {
  riskLevel: SafetyLevel
  toolAvailability: ToolAvailability
  allowedTools: string[]
  blockedTools: string[]
  label: string
}

export const safetyGateMap: Record<SafetyLevel, SafetyGateState> = {
  normal: {
    riskLevel: 'normal', toolAvailability: 'full',
    allowedTools: ['speak', 'control_ac', 'control_music', 'search_knowledge', 'get_weather', 'alert_driver', 'ask_clarification', 'search_attractions', 'start_navigation', 'plan_trip'],
    blockedTools: [], label: '全工具',
  },
  attn_declining: {
    riskLevel: 'attn_declining', toolAvailability: 'restricted',
    allowedTools: ['speak', 'control_ac', 'get_weather', 'alert_driver', 'ask_clarification'],
    blockedTools: ['control_music', 'search_attractions', 'start_navigation', 'plan_trip'], label: '受限',
  },
  distracted: {
    riskLevel: 'distracted', toolAvailability: 'restricted',
    allowedTools: ['speak', 'control_ac', 'alert_driver'],
    blockedTools: ['control_music', 'search_knowledge', 'get_weather', 'ask_clarification', 'search_attractions', 'start_navigation', 'plan_trip'], label: '受限',
  },
  dangerous: {
    riskLevel: 'dangerous', toolAvailability: 'readonly',
    allowedTools: ['speak', 'alert_driver'],
    blockedTools: ['control_ac', 'control_music', 'search_knowledge', 'get_weather', 'ask_clarification', 'search_attractions', 'start_navigation', 'plan_trip'], label: '仅告警',
  },
}

/* ========================== 实时遥测 & 告警 ========================== */

export interface Telemetry { attention: number; fatigue: number; gazeOnRoad: number; blinkRate: number; level: SafetyLevel }
export interface SafetyAlert { id: string; level: SafetyLevel; title: string; detail: string; time: string }
export interface DrivingStats { durationMin: number; distractionCount: number; perclosAvg: number; fatigueTrend: number[]; score: number }
export type LatLngTuple = [number, number]
export interface NavInfo {
  destination: string
  etaMin: number
  distanceKm: number
  nextTurn: string
  nextTurnMeters: number
  speed: number
  speedLimit: number
  originCoords?: LatLngTuple | null
  destinationCoords?: LatLngTuple | null
  geometry?: LatLngTuple[]
  steps?: string[]
  routeSource?: string
  coordinateSystem?: string
}

/* ========================== 对话 & Agent ========================== */

export type ChatRole = 'user' | 'assistant'
export interface ChatMessage { id: string; role: ChatRole; text: string }

export type AgentRoute = 'auto' | 'quick' | 'react' | 'multi' | 'readonly'
export interface AgentRouteOption { id: AgentRoute; label: string; description: string }

export interface AgentTraceStep {
  id: string
  phase: 'perceive' | 'safety_gate' | 'agent' | 'tool' | 'result'
  detail: string
  status: 'done' | 'running' | 'pending' | 'failed' | 'cancelled' | 'degraded'
  durationMs?: number
  toolName?: string
  toolArgs?: Record<string, unknown>
  toolResult?: string
}

export interface AgentResult { id: string; type: 'poi' | 'weather' | 'route'; title: string; subtitle: string; meta: string }

export const agentRoutes: AgentRouteOption[] = [
  { id: 'auto', label: '自动路由', description: '系统选择最优 Agent' },
  { id: 'quick', label: '快速指令', description: '直接调用车控工具' },
  { id: 'react', label: 'ReAct 推理', description: '感知、推理后执行' },
  { id: 'multi', label: '多 Agent 编排', description: '并行协调多个能力' },
  { id: 'readonly', label: '安全模式', description: '只读分析，不执行工具' },
]

/* ========================== 空调 ========================== */

export type HvacMode = 'face' | 'feet' | 'face-feet' | 'front-defrost' | 'rear-defrost'
export interface HvacState {
  power: boolean
  driverTemp: number
  passengerTemp: number
  sync: boolean
  ac: boolean
  auto: boolean
  fanSpeed: 1 | 2 | 3 | 4 | 5
  circulation: 'inside' | 'outside'
  mode: HvacMode
  rearDefrost: boolean
}

// 旧版 AC 类型（兼容后端 ACState 接口）
export interface ACState { power: boolean; temperature: number; mode: string; fanSpeed: number }

/* ========================== 手势 ========================== */

export type GestureCategory = '空调' | '确认' | '模式' | '导航' | '媒体' | '通信' | '安全'
export interface GestureCommand { gesture: string; actionCode: string; meaning: string; category: GestureCategory }
export interface GestureDetection { gesture: string; confidence: number; status: '识别中' | '已执行' | '待确认' | '已取消' | '失败'; timestamp: string }

export const gestureCommands: GestureCommand[] = [
  { gesture: 'Open', actionCode: 'TurnOnAC', meaning: '开空调', category: '空调' },
  { gesture: 'Close', actionCode: 'TurnOffAC', meaning: '关空调', category: '空调' },
  { gesture: 'Thumbs Up', actionCode: 'confirm', meaning: '确认', category: '确认' },
  { gesture: 'Thumbs Down', actionCode: 'cancel', meaning: '取消', category: '确认' },
  { gesture: 'OK', actionCode: 'confirm', meaning: '确认', category: '确认' },
  { gesture: 'Peace', actionCode: 'cancel', meaning: '取消', category: '确认' },
  { gesture: 'Pointer', actionCode: 'attention', meaning: '注意力', category: '导航' },
  { gesture: 'Quiet Coyote', actionCode: 'mute', meaning: '静音', category: '媒体' },
]

/* ========================== Music ========================== */

export interface SongInfo { id: number; name: string; artist: string; album: string; url: string; cover: string; duration: number }
export interface MusicState { playing: boolean; current_song: SongInfo; playlist: SongInfo[]; playlist_index: number; volume: number; message?: string }

/* ========================== Agent API 类型 ========================== */

export interface AgentChatResponse { status: string; result: { reply_text: string; steps: number; safety_level: string; status: string } }
export interface AgentOrchestrateResult { intent_id: string; intent_category: string; agent: string; success: boolean; reply: string; actions: string[]; error: string | null; duration_ms: number }
export interface AgentOrchestrateResponse { status: string; result: { reply_text: string; intent_plan: string; results: AgentOrchestrateResult[]; actions: string[]; needs_clarification: boolean; clarification_question: string; total_duration_ms: number; route: string } }
export interface WSMessage { type: string; data: Record<string, unknown> }
export interface NavRouteResponse { status: string; destination: string; distance_km: number; duration_min: number; route_summary: string; origin: string; map_url: string; waypoints: Array<{ lat: number; lon: number; name: string }> }
export interface EnvironmentData { city: string; temperature: number | null; weather_desc: string; humidity: number | null; wind_speed: number | null; driving_risk: string; driving_tip: string; time_context: string }

/* ========================== Mock 数据 ========================== */

export const initialTelemetry: Telemetry = { attention: 88, fatigue: 22, gazeOnRoad: 94, blinkRate: 14, level: 'normal' }
export const initialAlerts: SafetyAlert[] = [
  { id: 'a1', level: 'attn_declining', title: '轻微分心', detail: '检测到视线偏离路面 1.2s', time: '刚刚' },
  { id: 'a2', level: 'normal', title: '状态良好', detail: '驾驶员注意力保持稳定', time: '2 分钟前' },
]
export const initialStats: DrivingStats = { durationMin: 0, distractionCount: 0, perclosAvg: 0, fatigueTrend: new Array(12).fill(0), score: 100 }
export const initialChat: ChatMessage[] = [
  { id: 'm1', role: 'assistant', text: '你好，我是 EdgeGuard。安全门控正常，已开放低风险车控能力。' },
  { id: 'm2', role: 'user', text: '打开空调并播放轻音乐' },
  { id: 'm3', role: 'assistant', text: '已为主驾开启空调至 22.5°C，并开始播放夜间驾驶电台。' },
]
export const initialHvac: HvacState = { power: true, driverTemp: 22.5, passengerTemp: 23, sync: false, ac: true, auto: true, fanSpeed: 2, circulation: 'inside', mode: 'face-feet', rearDefrost: false }
export const mockNav: NavInfo = { destination: '', etaMin: 0, distanceKm: 0, nextTurn: '', nextTurnMeters: 0, speed: 0, speedLimit: 0 }
export const quickReplies = ['打开空调', '播放音乐', '导航回家', '检查驾驶状态']
export const mockAgentResults: AgentResult[] = [
  { id: 'r1', type: 'poi', title: '特来电快充站', subtitle: '1.4 km · 6 个空闲', meta: '¥1.2/度' },
  { id: 'r2', type: 'weather', title: '驾驶环境', subtitle: '多云 22°C', meta: '能见度良好' },
]
export const mockAgentTrace: AgentTraceStep[] = [
  { id: 't1', phase: 'perceive', detail: '视线 center · 疲劳 normal · PERCLOS 0.03', status: 'done', durationMs: 120 },
  { id: 't2', phase: 'safety_gate', detail: 'normal → 开放全部 10 个工具', status: 'done', durationMs: 42 },
  { id: 't3', phase: 'agent', detail: 'LLM 分析意图 → 空调开启 + 音乐搜索', status: 'done', durationMs: 310 },
  { id: 't4', phase: 'tool', detail: '调用 control_ac', status: 'done', durationMs: 280, toolName: 'control_ac', toolArgs: { command: 'TurnOnAC' }, toolResult: '✓ 空调已开启' },
  { id: 't5', phase: 'tool', detail: '调用 control_music(search)', status: 'done', durationMs: 420, toolName: 'control_music', toolArgs: { command: 'search', keyword: '轻音乐' }, toolResult: '✓ 找到 3 首' },
  { id: 't6', phase: 'result', detail: '全部完成，TTS 播报中', status: 'pending' },
]
