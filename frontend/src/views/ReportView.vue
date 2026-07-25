<template>
  <div class="report-page">
    <!-- 顶部导航 -->
    <header class="top-bar">
      <span class="top-left">EdgeGuard v1.0</span>
      <span class="top-center">📊 驾驶报告</span>
      <span class="top-right">
        <router-link to="/" class="back-link">← 返回大屏</router-link>
      </span>
    </header>

    <main class="report-main">
      <!-- ===== 区域1：驾驶总结卡片 ===== -->
      <section class="section">
        <h2 class="section-title">📋 本次驾驶总结</h2>
        <div class="summary-grid">
          <div class="summary-card">
            <span class="summary-icon">⏱️</span>
            <div class="summary-body">
              <span class="summary-value">{{ summary.duration }}</span>
              <span class="summary-label">驾驶时长</span>
            </div>
          </div>
          <div class="summary-card">
            <span class="summary-icon">🛣️</span>
            <div class="summary-body">
              <span class="summary-value">{{ summary.distance }} km</span>
              <span class="summary-label">行驶里程</span>
            </div>
          </div>
          <div class="summary-card">
            <span class="summary-icon">😰</span>
            <div class="summary-body">
              <span class="summary-value" :class="fatigueClass">{{ summary.avgFatigue }}</span>
              <span class="summary-label">平均疲劳分</span>
            </div>
          </div>
          <div class="summary-card">
            <span class="summary-icon">🚨</span>
            <div class="summary-body">
              <span class="summary-value alert-count">{{ summary.alertCount }}</span>
              <span class="summary-label">告警次数</span>
            </div>
          </div>
        </div>
      </section>

      <!-- ===== 区域2：数据统计图表 ===== -->
      <section class="section">
        <h2 class="section-title">📈 数据统计</h2>
        <div class="charts-row">
          <!-- 疲劳趋势折线图 -->
          <div class="chart-box">
            <h3 class="chart-title">疲劳分数趋势</h3>
            <div ref="trendChart" class="chart-body"></div>
          </div>
          <!-- 告警等级分布饼图 -->
          <div class="chart-box">
            <h3 class="chart-title">告警等级分布</h3>
            <div ref="pieChart" class="chart-body"></div>
          </div>
        </div>
      </section>

      <!-- ===== 区域3：历史告警列表 ===== -->
      <section class="section">
        <h2 class="section-title">🚨 历史告警记录</h2>

        <!-- 筛选 -->
        <div class="filter-row">
          <button
            v-for="lvl in ['全部', 'severe', 'moderate', 'mild']"
            :key="lvl"
            :class="['filter-btn', { active: filterLevel === lvl }]"
            @click="filterLevel = lvl"
          >{{ levelLabel(lvl) }}</button>
        </div>

        <!-- 列表 -->
        <div class="alert-list" v-if="filteredAlerts.length > 0">
          <TransitionGroup name="list">
            <div
              v-for="alert in filteredAlerts"
              :key="alert.id"
              class="alert-item"
              :class="'alert-' + alert.level"
            >
              <div class="alert-left">
                <span class="alert-level-icon">{{ levelIcon(alert.level) }}</span>
                <div class="alert-info">
                  <span class="alert-msg">{{ alert.msg }}</span>
                  <span class="alert-time">{{ alert.time }}</span>
                </div>
              </div>
              <div class="alert-right">
                <span class="alert-metric">PERCLOS {{ (alert.perclos * 100).toFixed(0) }}%</span>
                <span class="alert-metric">疲劳 {{ alert.fatigueScore }}</span>
              </div>
            </div>
          </TransitionGroup>
        </div>
        <div v-else class="empty-list">暂无告警记录</div>
      </section>

      <!-- ===== 区域4：驾驶行为洞察 ===== -->
      <section class="section">
        <h2 class="section-title">💡 驾驶行为洞察</h2>
        <div class="insight-grid">
          <div class="insight-card" v-for="item in insights" :key="item.title">
            <span class="insight-icon">{{ item.icon }}</span>
            <div class="insight-body">
              <span class="insight-title">{{ item.title }}</span>
              <span class="insight-desc">{{ item.desc }}</span>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'

// ===== Mock 数据 =====

const summary = ref({
  duration: '2h 35min',
  distance: 86.4,
  avgFatigue: 32,
  alertCount: 7,
})

const fatigueClass = computed(() => {
  const s = summary.value.avgFatigue
  if (s >= 70) return 'fatigue-high'
  if (s >= 40) return 'fatigue-mid'
  return 'fatigue-low'
})

const allAlerts = ref([
  { id: 1, level: 'severe',  msg: '重度疲劳！视线偏离道路超过5秒',       time: '14:32:18', perclos: 0.42, fatigueScore: 78 },
  { id: 2, level: 'moderate', msg: '中度分心 — 频繁查看中控屏',          time: '14:18:05', perclos: 0.28, fatigueScore: 55 },
  { id: 3, level: 'mild',     msg: '注意力下降 — 眨眼频率升高',          time: '14:05:42', perclos: 0.18, fatigueScore: 38 },
  { id: 4, level: 'moderate', msg: '疲劳趋势上升 — 建议休息',            time: '13:50:21', perclos: 0.32, fatigueScore: 62 },
  { id: 5, level: 'mild',     msg: '轻微注意力分散',                     time: '13:30:10', perclos: 0.15, fatigueScore: 30 },
  { id: 6, level: 'severe',   msg: '危险！检测到闭眼超过2秒',            time: '13:12:45', perclos: 0.55, fatigueScore: 85 },
  { id: 7, level: 'mild',     msg: '驾驶姿态偏移 — 提醒坐正',            time: '12:48:33', perclos: 0.10, fatigueScore: 25 },
])

const filterLevel = ref('全部')

const filteredAlerts = computed(() => {
  if (filterLevel.value === '全部') return allAlerts.value
  return allAlerts.value.filter(a => a.level === filterLevel.value)
})

function levelLabel(lvl) {
  const map = { '全部': '全部 (7)', 'severe': '🔴 严重 (2)', 'moderate': '🟠 中度 (2)', 'mild': '🟡 轻度 (3)' }
  return map[lvl] || lvl
}
function levelIcon(lvl) {
  const map = { severe: '🔴', moderate: '🟠', mild: '🟡' }
  return map[lvl] || '⚪'
}

const insights = ref([
  { icon: '⚠️', title: '疲劳高发时段', desc: '13:00-14:30 期间疲劳告警密集，建议该时段前适当休息。' },
  { icon: '👍', title: '安全时段', desc: '12:00-12:45 零告警，注意力保持良好水平。' },
  { icon: '📉', title: '改善趋势', desc: '14:32 后疲劳分数呈下降趋势，短暂休息起到了作用。' },
  { icon: '💡', title: '建议', desc: '连续驾驶超过2小时后疲劳风险显著升高，建议每1.5小时休息10分钟。' },
])

// ===== ECharts =====

const trendChart = ref(null)
const pieChart = ref(null)

onMounted(async () => {
  await nextTick()
  initTrendChart()
  initPieChart()
})

function initTrendChart() {
  if (!trendChart.value) return
  const chart = echarts.init(trendChart.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 16, bottom: 28 },
    xAxis: {
      type: 'category',
      data: ['12:00','12:20','12:40','13:00','13:20','13:40','14:00','14:20','14:40'],
      axisLabel: { color: '#94a3b8', fontSize: 10 },
      axisLine: { lineStyle: { color: '#334155' } },
    },
    yAxis: {
      type: 'value', min: 0, max: 100,
      axisLabel: { color: '#94a3b8', fontSize: 10 },
      splitLine: { lineStyle: { color: '#1e293b' } },
    },
    series: [{
      data: [15, 18, 20, 30, 55, 62, 78, 85, 42],
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { color: '#4FC3F7', width: 2 },
      itemStyle: { color: '#4FC3F7' },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(79,195,247,0.3)' },
        { offset: 1, color: 'rgba(79,195,247,0.02)' },
      ])},
      markLine: {
        silent: true,
        symbol: 'none',
        lineStyle: { color: '#ef4444', type: 'dashed', width: 1 },
        data: [{ yAxis: 70, label: { formatter: '⚠ 危险线', color: '#fca5a5', fontSize: 10 } }],
      },
    }],
  })
}

function initPieChart() {
  if (!pieChart.value) return
  const chart = echarts.init(pieChart.value)
  chart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['45%', '75%'],
      center: ['50%', '50%'],
      itemStyle: { borderRadius: 4, borderColor: '#0f172a', borderWidth: 3 },
      label: { color: '#94a3b8', fontSize: 11 },
      data: [
        { value: 2, name: '严重', itemStyle: { color: '#ef4444' } },
        { value: 2, name: '中度', itemStyle: { color: '#f59e0b' } },
        { value: 3, name: '轻度', itemStyle: { color: '#fbbf24' } },
      ],
    }],
  })
}
</script>

<style scoped>
.report-page {
  min-height: 100vh;
  background: #0f172a;
  color: #e2e8f0;
  font-family: 'Segoe UI', system-ui, sans-serif;
}

/* ── 顶部导航 ── */
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background: #1e293b;
  border-bottom: 1px solid #334155;
  position: sticky;
  top: 0;
  z-index: 100;
}
.top-left { color: #4FC3F7; font-weight: bold; font-size: 14px; }
.top-center { font-size: 16px; font-weight: 600; }
.top-right { font-size: 13px; }
.back-link {
  color: #4FC3F7;
  text-decoration: none;
  padding: 6px 14px;
  border: 1px solid #334155;
  border-radius: 6px;
  transition: all 0.2s;
}
.back-link:hover { background: #1e3a5f; border-color: #4FC3F7; }

/* ── 主体 ── */
.report-main {
  max-width: 1000px;
  margin: 0 auto;
  padding: 24px 20px 40px;
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.section-title {
  font-size: 16px;
  color: #94a3b8;
  margin: 0 0 14px 0;
  text-transform: uppercase;
  letter-spacing: 1px;
}

/* ── 驾驶总结卡片 ── */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.summary-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 18px 16px;
  display: flex;
  align-items: center;
  gap: 14px;
}
.summary-icon { font-size: 28px; flex-shrink: 0; }
.summary-body { display: flex; flex-direction: column; gap: 4px; }
.summary-value { font-size: 22px; font-weight: bold; color: #f1f5f9; }
.summary-label { font-size: 12px; color: #64748b; }
.fatigue-low { color: #4ade80; }
.fatigue-mid { color: #fbbf24; }
.fatigue-high { color: #f87171; }
.alert-count { color: #f87171; }

/* ── 图表区域 ── */
.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.chart-box {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 16px;
}
.chart-title {
  font-size: 13px;
  color: #94a3b8;
  margin: 0 0 8px 0;
}
.chart-body { width: 100%; height: 260px; }

/* ── 筛选按钮 ── */
.filter-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.filter-btn {
  background: #1e293b;
  color: #94a3b8;
  border: 1px solid #334155;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.filter-btn:hover { border-color: #4FC3F7; color: #e2e8f0; }
.filter-btn.active {
  background: #1e3a5f;
  border-color: #4FC3F7;
  color: #4FC3F7;
  font-weight: 600;
}

/* ── 告警列表 ── */
.alert-list { display: flex; flex-direction: column; gap: 8px; }
.alert-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-radius: 8px;
  border-left: 4px solid;
}
.alert-mild     { background: rgba(251, 191, 36, 0.08);  border-color: #fbbf24; }
.alert-moderate { background: rgba(245, 158, 11, 0.1);   border-color: #f59e0b; }
.alert-severe   { background: rgba(239, 68, 68, 0.12);   border-color: #ef4444; }

.alert-left { display: flex; align-items: center; gap: 12px; }
.alert-level-icon { font-size: 18px; flex-shrink: 0; }
.alert-info { display: flex; flex-direction: column; gap: 4px; }
.alert-msg { font-size: 14px; color: #e2e8f0; font-weight: 500; }
.alert-time { font-size: 11px; color: #64748b; font-family: monospace; }
.alert-right { display: flex; gap: 16px; }
.alert-metric { font-size: 12px; color: #94a3b8; font-family: monospace; }

.empty-list {
  text-align: center;
  color: #475569;
  padding: 32px 0;
  font-size: 14px;
}

/* ── 列表动画 ── */
.list-enter-active { transition: all 0.3s ease-out; }
.list-leave-active { transition: all 0.2s ease-in; }
.list-enter-from { opacity: 0; transform: translateY(-8px); }
.list-leave-to { opacity: 0; transform: translateY(8px); }

/* ── 驾驶洞察 ── */
.insight-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.insight-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.insight-icon { font-size: 22px; flex-shrink: 0; margin-top: 2px; }
.insight-body { display: flex; flex-direction: column; gap: 4px; }
.insight-title { font-size: 14px; font-weight: 600; color: #e2e8f0; }
.insight-desc { font-size: 12px; color: #94a3b8; line-height: 1.6; }

/* ── 响应式：小屏时卡片/图表堆叠 ── */
@media (max-width: 768px) {
  .summary-grid { grid-template-columns: 1fr 1fr; }
  .charts-row { grid-template-columns: 1fr; }
  .insight-grid { grid-template-columns: 1fr; }
}
</style>
