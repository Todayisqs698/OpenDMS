<template>
  <section class="panel agent-result-panel">
    <div class="panel-header">
      <h2 class="panel-title">Agent 结果展示</h2>
      <button v-if="hasResults" class="clear-btn" @click="clearAll" title="清空结果">✕</button>
    </div>

    <!-- 空状态 -->
    <div v-if="!hasResults && !loading" class="empty-state">
      <span class="empty-icon">🤖</span>
      <span class="empty-text">Agent 结果将显示在这里</span>
      <div class="empty-hints">
        <span class="empty-hint">🗺️ "推荐天津景点"</span>
        <span class="empty-hint">🌤️ "今天天气怎么样"</span>
        <span class="empty-hint">📋 "计划北京一日游"</span>
        <span class="empty-hint">🧭 "导航去故宫"</span>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading && !hasResults" class="loading-state">
      <div class="loading-spinner"></div>
      <span class="loading-text">{{ loadingTool ? `正在调用 ${loadingTool}...` : 'Agent 思考中...' }}</span>
    </div>

    <!-- 结果内容区（可滚动） -->
    <div class="result-content" v-if="hasResults || loading">
      <!-- 景点推荐卡片 -->
      <TransitionGroup name="card-list" tag="div" v-if="attractions.length">
        <div class="result-section" :key="'attractions'">
          <div class="section-header">
            <span class="section-icon">🗺️</span>
            <span class="section-title">景点推荐 · {{ attractionsCity }}</span>
          </div>
          <div class="attraction-cards">
            <div v-for="(attr, i) in attractions" :key="i" class="attraction-card" :class="{ indoor: attr.indoor }">
              <div class="attraction-rank">{{ i + 1 }}</div>
              <!-- 景点照片 -->
              <div class="attraction-photo" v-if="attr.photo_url">
                <img :src="attr.photo_url" :alt="attr.name" @error="hidePhoto(i)" />
              </div>
              <div class="attraction-info">
                <div class="attraction-header">
                  <span class="attraction-name">{{ attr.name }}</span>
                  <span v-if="attr.category" class="tag tag-category">{{ attr.category }}</span>
                </div>
                <div class="attraction-meta">
                  <span v-if="attr.rating > 0" class="meta-rating">⭐ {{ attr.rating.toFixed(1) }}</span>
                  <span v-if="attr.ticket_price > 0" class="meta-ticket">🎫 ¥{{ attr.ticket_price }}</span>
                  <span v-else class="meta-ticket free">免费</span>
                  <span v-if="attr.visit_duration" class="meta-duration">
                    ⏱️ {{ Math.floor(attr.visit_duration / 60) }}h{{ attr.visit_duration % 60 ? attr.visit_duration % 60 + 'min' : '' }}
                  </span>
                </div>
                <div class="attraction-addr">📍 {{ attr.address }}</div>
                <div class="attraction-tags">
                  <span v-if="attr.indoor" class="tag tag-indoor">室内</span>
                  <span v-else class="tag tag-outdoor">户外</span>
                  <span v-if="attr.weather_hint" class="tag tag-weather">{{ attr.weather_hint }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </TransitionGroup>

      <!-- 天气查询结果卡片 -->
      <Transition name="card-pop" v-if="weatherInfo">
        <div class="result-section" v-if="weatherInfo">
          <div class="section-header">
            <span class="section-icon">🌤️</span>
            <span class="section-title">天气查询 · {{ weatherInfo.city || '--' }}</span>
          </div>
          <div class="weather-result-card" :class="'w-' + (weatherInfo.weather_icon || 'unknown')">
            <div class="w-main">
              <span class="w-emoji">{{ weatherInfo.weather_emoji || '🌤️' }}</span>
              <span class="w-temp">{{ weatherInfo.temperature != null ? weatherInfo.temperature + '°C' : '--' }}</span>
            </div>
            <div class="w-details">
              <div class="w-desc">{{ weatherInfo.weather_desc || weatherInfo.weather || '--' }}</div>
              <div class="w-meta">
                <span v-if="weatherInfo.humidity != null">💧 {{ weatherInfo.humidity }}%</span>
                <span v-if="weatherInfo.wind_speed != null">💨 {{ weatherInfo.wind_speed }} km/h</span>
              </div>
              <div class="w-context" v-if="weatherInfo.driving_context">{{ weatherInfo.driving_context }}</div>
            </div>
          </div>
        </div>
      </Transition>

      <!-- 导航路线卡片 -->
      <Transition name="card-pop" v-if="navRoute">
        <div class="result-section" v-if="navRoute">
          <div class="section-header">
            <span class="section-icon">🧭</span>
            <span class="section-title">导航路线</span>
          </div>
          <div class="nav-result-card">
            <div class="nav-dest">
              <span class="nav-from">📍 {{ navRoute.origin || '当前位置' }}</span>
              <span class="nav-arrow">→</span>
              <span class="nav-to">🎯 {{ navRoute.destination }}</span>
            </div>
            <div class="nav-stats">
              <span class="nav-stat">📏 {{ navRoute.distance_km }} km</span>
              <span class="nav-stat">⏱️ {{ navRoute.duration_min }} 分钟</span>
            </div>
            <div class="nav-roads" v-if="navRoute.route_summary">{{ navRoute.route_summary }}</div>
            <!-- 静态地图 -->
            <div class="nav-map-container" v-if="navRoute.map_url && !navMapError">
              <img :src="navRoute.map_url" alt="路线地图" class="nav-map-img" @error="navMapError = true" />
            </div>
            <a v-if="navRoute.amap_nav_url" :href="navRoute.amap_nav_url" target="_blank" class="nav-open-amap">
              🗺️ 在高德地图中打开
            </a>
          </div>
        </div>
      </Transition>

      <!-- 行程规划时间线 -->
      <Transition name="card-pop" v-if="tripPlan">
        <div class="result-section" v-if="tripPlan">
          <div class="section-header">
            <span class="section-icon">📋</span>
            <span class="section-title">行程规划 · {{ tripPlan.city }} · {{ tripPlan.days || 1 }}日游</span>
          </div>
          <!-- 行程摘要 -->
          <div class="trip-summary" v-if="tripPlan.summary">{{ tripPlan.summary }}</div>

          <!-- 预算汇总 -->
          <div class="budget-summary" v-if="tripPlan.budget && tripPlan.budget.total != null">
            <div class="budget-total">
              <span class="budget-label">预计总费用</span>
              <span class="budget-amount">¥{{ tripPlan.budget.total }}</span>
            </div>
            <div class="budget-breakdown">
              <div class="budget-item"><span>🎫 门票</span><span>¥{{ tripPlan.budget.tickets }}</span></div>
              <div class="budget-item"><span>🍽️ 餐饮</span><span>¥{{ tripPlan.budget.meals }}</span></div>
              <div class="budget-item"><span>🚗 交通</span><span>¥{{ tripPlan.budget.transport }}</span></div>
              <div class="budget-item" v-if="tripPlan.days > 1"><span>📊 日均</span><span>¥{{ tripPlan.budget.per_day }}</span></div>
            </div>
          </div>

          <!-- 多日行程时间线 -->
          <div class="day-plan" v-for="day in (tripPlan.itinerary || [])" :key="day.day">
            <div class="day-header" v-if="tripPlan.days > 1">
              <span class="day-badge">Day {{ day.day }}</span>
              <span class="day-date">{{ day.date }}</span>
            </div>
            <div class="trip-timeline">
              <div v-for="(slot, i) in (day.slots || [])" :key="i" class="timeline-item">
                <div class="timeline-time">{{ slot.time }}</div>
                <div class="timeline-dot" :class="'dot-' + (slot.type || 'visit')"></div>
                <div class="timeline-content">
                  <div class="timeline-title">
                    {{ slot.title }}
                    <span class="slot-cost" v-if="slot.cost > 0">¥{{ slot.cost }}</span>
                  </div>
                  <div class="timeline-desc" v-if="slot.desc">{{ slot.desc }}</div>
                  <!-- 景点照片（在时间线内） -->
                  <img v-if="slot.photo_url" :src="slot.photo_url" class="slot-photo"
                       @error="$event.target.style.display='none'" />
                  <!-- 景点元数据 -->
                  <div class="slot-meta" v-if="slot.rating > 0 || slot.ticket_price != null">
                    <span v-if="slot.rating > 0" class="meta-rating">⭐ {{ slot.rating.toFixed(1) }}</span>
                    <span v-if="slot.ticket_price > 0" class="meta-ticket">🎫 ¥{{ slot.ticket_price }}</span>
                    <span v-else-if="slot.ticket_price === 0 && slot.type === 'visit'" class="meta-ticket free">免费</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const attractions = ref([])
const attractionsCity = ref('')
const weatherInfo = ref(null)
const navRoute = ref(null)
const navMapError = ref(false)
const tripPlan = ref(null)
const loading = ref(false)
const loadingTool = ref('')

const hasResults = computed(() =>
  attractions.value.length > 0 || weatherInfo.value || navRoute.value || tripPlan.value
)

function clearAll() {
  attractions.value = []
  attractionsCity.value = ''
  weatherInfo.value = null
  navRoute.value = null
  tripPlan.value = null
  loading.value = false
  loadingTool.value = ''
}

function hidePhoto(idx) {
  // 照片加载失败时清除 photo_url 触发 v-if 隐藏
  if (attractions.value[idx]) {
    attractions.value[idx].photo_url = ''
  }
}

let ws = null
let reconnectTimer = null
let loadingTimeout = null

function handleMsg(msg) {
  console.log('[AgentResultPanel] WS msg:', msg.type, msg.data ? 'has data' : 'no data')

  // 工具调用开始 → 显示加载状态
  if (msg.type === 'agent_tool_call' && msg.data) {
    loading.value = true
    loadingTool.value = msg.data.tool || ''
    if (loadingTimeout) clearTimeout(loadingTimeout)
    loadingTimeout = setTimeout(() => { loading.value = false }, 30000)
  }

  // 景点推荐
  if ((msg.type === 'agent_attractions' || msg.type === 'attractions') && msg.data) {
    attractions.value = msg.data.attractions || []
    attractionsCity.value = msg.data.city || ''
    loading.value = false
  }
  // 天气查询结果
  if ((msg.type === 'agent_weather_query' || msg.type === 'agent_weather' || msg.type === 'weather_query') && msg.data) {
    weatherInfo.value = msg.data
    loading.value = false
  }
  // 导航路线
  if ((msg.type === 'agent_navigation' || msg.type === 'navigation') && msg.data) {
    navMapError.value = false
    navRoute.value = msg.data
    loading.value = false
  }
  // 行程规划
  if ((msg.type === 'agent_trip_plan' || msg.type === 'trip_plan') && msg.data) {
    tripPlan.value = msg.data
    loading.value = false
  }
  // 最终回复 → 关闭加载
  if (msg.type === 'agent_final') {
    loading.value = false
    if (loadingTimeout) clearTimeout(loadingTimeout)
  }
}

function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = location.host || 'localhost:8000'
  try {
    ws = new WebSocket(`${protocol}//${host}/ws/agent_result`)
    ws.onopen = () => { console.log('[AgentResultPanel] WS connected') }
    ws.onmessage = (e) => {
      try { handleMsg(JSON.parse(e.data)) } catch {}
    }
    ws.onclose = () => { console.log('[AgentResultPanel] WS closed, reconnecting...'); reconnectTimer = setTimeout(connectWS, 5000) }
    ws.onerror = () => { console.error('[AgentResultPanel] WS error'); ws?.close() }
  } catch { reconnectTimer = setTimeout(connectWS, 5000) }
}

onMounted(() => { connectWS() })
onUnmounted(() => {
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (loadingTimeout) clearTimeout(loadingTimeout)
  if (ws) ws.close()
})
</script>

<style scoped>
.agent-result-panel {
  display: flex; flex-direction: column; gap: 8px;
  overflow: hidden;
}
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0;
}
.panel-title {
  margin: 0; font-size: 14px; color: #64748b;
  text-transform: uppercase; letter-spacing: 1px;
}
.clear-btn {
  background: none; border: 1px solid #334155; border-radius: 4px;
  color: #64748b; cursor: pointer; font-size: 12px; padding: 2px 8px;
  transition: all 0.2s;
}
.clear-btn:hover { color: #ef4444; border-color: #ef4444; }

/* 空状态 */
.empty-state {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  color: #4b5563; margin-top: 20px;
}
.empty-icon { font-size: 36px; }
.empty-text { font-size: 13px; }
.empty-hints {
  display: flex; flex-direction: column; gap: 4px; margin-top: 6px;
}
.empty-hint { font-size: 11px; color: #374151; }

/* 加载状态 */
.loading-state {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  margin-top: 30px;
}
.loading-spinner {
  width: 28px; height: 28px; border-radius: 50%;
  border: 3px solid #1e293b; border-top-color: #3b82f6;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-text { font-size: 12px; color: #64748b; }

/* 结果内容区（可滚动） */
.result-content {
  flex: 1; overflow-y: auto; padding-right: 4px;
}
.result-content::-webkit-scrollbar { width: 4px; }
.result-content::-webkit-scrollbar-thumb { background: #334155; border-radius: 2px; }

/* 结果区块 */
.result-section { margin-bottom: 10px; }
.section-header {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 6px; padding-bottom: 4px;
  border-bottom: 1px solid #1e293b;
}
.section-icon { font-size: 16px; }
.section-title { font-size: 13px; font-weight: 600; color: #93c5fd; }

/* 景点卡片 */
.attraction-cards { display: flex; flex-direction: column; gap: 6px; }
.attraction-card {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 8px 10px; border-radius: 8px;
  background: #1a2332; border: 1px solid #1e293b;
  transition: all 0.3s;
}
.attraction-card:hover { border-color: #2563eb; background: #1e293b; }
.attraction-card.indoor { border-left: 3px solid #22c55e; }
.attraction-card:not(.indoor) { border-left: 3px solid #f59e0b; }
.attraction-rank {
  flex-shrink: 0; width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  background: #2563eb; color: #fff; border-radius: 50%;
  font-size: 12px; font-weight: bold;
}
.attraction-info { flex: 1; min-width: 0; }
.attraction-header { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.attraction-name { font-size: 13px; font-weight: 600; color: #e2e8f0; }
.attraction-meta { display: flex; gap: 8px; margin-top: 3px; flex-wrap: wrap; }
.meta-rating { font-size: 11px; color: #fde68a; }
.meta-ticket { font-size: 11px; color: #93c5fd; }
.meta-ticket.free { color: #86efac; }
.meta-duration { font-size: 11px; color: #94a3b8; }
.attraction-photo { width: 100%; height: 80px; border-radius: 6px; overflow: hidden; margin-bottom: 4px; flex-shrink: 0; }
.attraction-photo img { width: 100%; height: 100%; object-fit: cover; }
.attraction-addr { font-size: 11px; color: #64748b; margin-top: 2px; }
.attraction-tags { display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap; }
.tag {
  font-size: 10px; padding: 1px 6px; border-radius: 4px; font-weight: 500;
}
.tag-indoor { background: rgba(34,197,94,0.15); color: #86efac; }
.tag-outdoor { background: rgba(245,158,11,0.15); color: #fde68a; }
.tag-weather { background: rgba(96,165,250,0.15); color: #93c5fd; }
.tag-category { background: rgba(168,85,247,0.15); color: #c4b5fd; }

/* 天气结果卡片 */
.weather-result-card {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-radius: 10px;
}
.w-sun { background: linear-gradient(135deg, #1a3a2a, #0f2b1a); border: 1px solid #166534; }
.w-cloud { background: linear-gradient(135deg, #1e293b, #1a2332); border: 1px solid #334155; }
.w-rain { background: linear-gradient(135deg, #1a2744, #162033); border: 1px solid #1e3a5f; }
.w-snow { background: linear-gradient(135deg, #1e2a3a, #162233); border: 1px solid #2a3a4f; }
.w-fog { background: linear-gradient(135deg, #2a2a2a, #1e1e1e); border: 1px solid #444; }
.w-unknown { background: #1e1e2d; border: 1px solid #333; }
.w-main { display: flex; align-items: center; gap: 8px; }
.w-emoji { font-size: 32px; }
.w-temp { font-size: 24px; font-weight: bold; color: #f1f5f9; }
.w-details { text-align: right; }
.w-desc { font-size: 13px; color: #e2e8f0; }
.w-meta { display: flex; gap: 10px; justify-content: flex-end; font-size: 11px; color: #94a3b8; margin-top: 2px; }
.w-context { font-size: 11px; color: #64748b; margin-top: 4px; max-width: 180px; }

/* 导航结果卡片 */
.nav-result-card {
  padding: 10px 12px; border-radius: 10px;
  background: linear-gradient(135deg, #1e3a5f, #162233);
  border: 1px solid #2563eb;
}
.nav-dest {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #e2e8f0; margin-bottom: 8px; flex-wrap: wrap;
}
.nav-from { color: #94a3b8; }
.nav-arrow { color: #2563eb; }
.nav-to { color: #f1f5f9; font-weight: 600; }
.nav-stats { display: flex; gap: 12px; }
.nav-stat {
  font-size: 14px; font-weight: 600; color: #93c5fd;
  background: rgba(37,99,235,0.15); padding: 4px 10px; border-radius: 6px;
}
.nav-roads {
  font-size: 11px; color: #64748b; line-height: 1.5;
  padding: 6px 8px; background: rgba(0,0,0,0.2); border-radius: 6px; margin-top: 6px;
}

/* 静态地图（AgentResultPanel 内） */
.nav-map-container {
  margin-top: 8px; border-radius: 8px; overflow: hidden;
  border: 1px solid #1e3a5f;
}
.nav-map-img { width: 100%; display: block; border-radius: 8px; }
.nav-open-amap {
  display: block; text-align: center; margin-top: 8px;
  padding: 6px 12px; border-radius: 6px;
  background: rgba(37,99,235,0.2); border: 1px solid rgba(37,99,235,0.4);
  color: #93c5fd; font-size: 12px; text-decoration: none;
  transition: all 0.2s;
}
.nav-open-amap:hover { background: rgba(37,99,235,0.35); color: #bfdbfe; }

/* 行程摘要 */
.trip-summary {
  font-size: 12px; color: #94a3b8; line-height: 1.6;
  padding: 8px 10px; border-radius: 8px;
  background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.2);
  margin-bottom: 8px;
}

/* 行程时间线 */
.trip-summary {
  font-size: 12px; color: #94a3b8; margin-bottom: 8px; line-height: 1.5;
  padding: 6px 10px; background: rgba(37,99,235,0.08); border-radius: 6px;
}

/* 预算汇总 */
.budget-summary {
  display: flex; gap: 12px; margin-bottom: 10px;
  padding: 8px 12px; background: #1a2332; border-radius: 8px;
  border: 1px solid #1e293b;
}
.budget-total { display: flex; flex-direction: column; justify-content: center; }
.budget-label { font-size: 10px; color: #64748b; }
.budget-amount { font-size: 18px; font-weight: bold; color: #fbbf24; }
.budget-breakdown { display: flex; flex-wrap: wrap; gap: 8px; flex: 1; }
.budget-item { display: flex; flex-direction: column; font-size: 11px; color: #94a3b8; }
.budget-item span:last-child { color: #e2e8f0; font-weight: 500; }

/* 多日行程 */
.day-plan { margin-bottom: 10px; }
.day-header {
  display: flex; align-items: center; gap: 8px; margin: 8px 0 4px;
}
.day-badge {
  font-size: 11px; font-weight: bold; color: #fff;
  background: #2563eb; padding: 2px 8px; border-radius: 4px;
}
.day-date { font-size: 11px; color: #64748b; }

.trip-timeline { position: relative; padding-left: 8px; }
.timeline-item {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 6px 0; position: relative;
}
.timeline-item::before {
  content: ''; position: absolute; left: 18px; top: 20px; bottom: -6px;
  width: 2px; background: #1e293b;
}
.timeline-item:last-child::before { display: none; }
.timeline-time {
  flex-shrink: 0; width: 50px; font-size: 11px; color: #64748b;
  text-align: right; padding-top: 2px;
}
.timeline-dot {
  flex-shrink: 0; width: 10px; height: 10px; border-radius: 50%;
  margin-top: 4px; z-index: 1;
}
.dot-visit { background: #22c55e; }
.dot-meal { background: #f59e0b; }
.dot-transport { background: #3b82f6; }
.dot-rest { background: #8b5cf6; }
.timeline-content { flex: 1; }
.timeline-title { font-size: 13px; color: #e2e8f0; font-weight: 500; display: flex; align-items: center; gap: 6px; }
.slot-cost { font-size: 11px; color: #fbbf24; }
.timeline-desc { font-size: 11px; color: #64748b; margin-top: 2px; }
.slot-photo { width: 100%; max-height: 60px; object-fit: cover; border-radius: 4px; margin-top: 4px; }
.slot-meta { display: flex; gap: 8px; margin-top: 2px; }

/* 动画 */
.card-list-enter-active { transition: all 0.4s ease-out; }
.card-list-leave-active { transition: all 0.3s ease-in; }
.card-list-enter-from { opacity: 0; transform: translateY(15px); }
.card-list-leave-to { opacity: 0; transform: translateX(20px); }

.card-pop-enter-active { transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); }
.card-pop-leave-active { transition: all 0.3s ease-in; }
.card-pop-enter-from { opacity: 0; transform: scale(0.9); }
.card-pop-leave-to { opacity: 0; transform: scale(0.95); }
</style>
