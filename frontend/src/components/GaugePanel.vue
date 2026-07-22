<template>
  <section class="panel gauge-panel">
    <h2>仪表盘</h2>

    <!-- ECharts 仪表盘区域 -->
    <div ref="gaugeChart" class="gauge-chart"></div>

    <!-- 疲劳分数进度条 -->
    <div class="fatigue-bar" v-if="fatigueScore !== null">
      <div class="fatigue-label">
        <span>疲劳分数</span>
        <span class="fatigue-value" :class="fatigueClass">{{ fatigueScore }}</span>
      </div>
      <div class="fatigue-track">
        <div class="fatigue-fill" :class="fatigueClass"
             :style="{ width: fatigueScore + '%' }"></div>
      </div>
      <div class="fatigue-level" :class="fatigueClass">{{ fatigueLevelText }}</div>
    </div>

    <!-- 基础指标 -->
    <div class="metrics" v-if="data">
      <div class="metric">
        <span class="metric-label">视线</span>
        <span class="metric-value">{{ gazeLabel }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">手势</span>
        <span class="metric-value">{{ data.gesture || '--' }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">语音</span>
        <span class="metric-value">{{ data.speech || '--' }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">路由</span>
        <span class="metric-value">{{ data.route || '--' }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">置信度</span>
        <span class="metric-value">{{ data.confidence || 0 }}%</span>
      </div>
    </div>

    <!-- 趋势指示 -->
    <div class="trend-indicator" v-if="trend">
      <span class="trend-label">趋势</span>
      <span class="trend-value" :class="trendClass">{{ trendIcon }} {{ trendText }}</span>
    </div>

    <p v-if="!data && fatigueScore === null" class="placeholder">等待数据...</p>
  </section>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({ data: Object })

const gazeLabelMap = {
  center: '前方', left: '左', right: '右', up: '上', down: '下',
  up_left: '左上', up_right: '右上', down_left: '左下', down_right: '右下', lost: '丢失'
}
const gazeLabel = computed(() => {
  const g = props.data?.gaze
  return g ? (gazeLabelMap[g] || g) : '--'
})

const gaugeChart = ref(null)
let chartInstance = null

// 从 props.data 或 props.data.metrics 提取疲劳相关数据
const fatigueScore = ref(null)
const fatigueLevel = ref('')
const perclos = ref(0)
const blinkRate = ref(0)
const trend = ref('')

const fatigueClass = ref('')
const fatigueLevelText = ref('')
const trendClass = ref('')
const trendIcon = ref('')
const trendText = ref('')

function updateDerived() {
  const d = props.data || {}

  // 兼容两种数据结构：
  // 1. 后端直接传 metrics: {fatigue_score, fatigue_level, perclos, blink_rate}
  // 2. 只有顶层字段（旧格式）
  const m = d.metrics || {}
  fatigueScore.value = m.fatigue_score ?? d.fatigue_score ?? null
  fatigueLevel.value = m.fatigue_level ?? d.fatigue_level ?? ''
  perclos.value = m.perclos ?? d.perclos ?? 0
  blinkRate.value = m.blink_rate ?? d.blink_rate ?? 0
  trend.value = m.trend ?? d.trend ?? ''

  // 疲劳等级样式
  const levelMap = {
    normal:   { cls: 'level-normal',   text: '正常' },
    warning:  { cls: 'level-warning',  text: '注意力下降' },
    danger:   { cls: 'level-danger',   text: '重度疲劳' },
  }
  const lv = levelMap[fatigueLevel.value] || { cls: '', text: fatigueLevel.value }
  fatigueClass.value = lv.cls
  fatigueLevelText.value = lv.text

  // 趋势样式
  const trendMap = {
    rising:   { cls: 'trend-up',    icon: '↑', text: '上升' },
    declining:{ cls: 'trend-down',  icon: '↓', text: '下降' },
    stable:  { cls: 'trend-stable', icon: '→', text: '稳定' },
  }
  const tr = trendMap[trend.value] || {}
  trendClass.value = tr.cls || ''
  trendIcon.value = tr.icon || ''
  trendText.value = tr.text || trend.value
}

function renderGauge() {
  if (!gaugeChart.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(gaugeChart.value)
  }

  const score = fatigueScore.value ?? 0

  // 根据分数选择颜色
  let color = '#52c41a'  // 绿
  if (score >= 70) color = '#ff4d4f'     // 红
  else if (score >= 40) color = '#faad14' // 橙

  chartInstance.setOption({
    series: [{
      type: 'gauge',
      min: 0,
      max: 100,
      progress: { show: true, width: 12 },
      axisLine: {
        lineStyle: { width: 12, color: [
          [0.4, '#52c41a'],
          [0.7, '#faad14'],
          [1, '#ff4d4f'],
        ] }
      },
      pointer: { width: 5, length: '60%' },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      detail: {
        formatter: '{value}',
        fontSize: 28,
        offsetCenter: [0, '70%'],
        color: color,
      },
      title: {
        offsetCenter: [0, '100%'],
        fontSize: 12,
        color: '#999',
      },
      data: [{ value: score, name: '疲劳分数' }],
    }]
  })
}

function handleResize() {
  chartInstance && chartInstance.resize()
}

watch(() => props.data, () => {
  updateDerived()
  nextTick(() => renderGauge())
}, { deep: true })

onMounted(() => {
  updateDerived()
  nextTick(() => renderGauge())
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})
</script>

<style scoped>
.gauge-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.gauge-chart {
  width: 100%;
  height: 160px;
}

.fatigue-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.fatigue-label {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

.fatigue-value {
  font-weight: bold;
  font-size: 15px;
}

.fatigue-track {
  height: 8px;
  background: #e8e8e8;
  border-radius: 4px;
  overflow: hidden;
}

.fatigue-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s ease, background 0.3s ease;
}

.level-normal   .fatigue-fill,
.level-normal   .fatigue-value { color: #52c41a; }
.level-normal   .fatigue-fill { background: #52c41a; }

.level-warning  .fatigue-fill,
.level-warning  .fatigue-value { color: #faad14; }
.level-warning  .fatigue-fill { background: #faad14; }

.level-danger   .fatigue-fill,
.level-danger   .fatigue-value { color: #ff4d4f; }
.level-danger   .fatigue-fill { background: #ff4d4f; }

.fatigue-level {
  font-size: 12px;
  text-align: right;
}

.metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.metric {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  padding: 2px 6px;
  background: #f5f5f5;
  border-radius: 4px;
}

.metric-label { color: #888; }
.metric-value { font-weight: 500; }

.trend-indicator {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  padding: 4px 6px;
}

.trend-label { color: #888; }

.trend-up    { color: #ff4d4f; }
.trend-down  { color: #52c41a; }
.trend-stable { color: #999; }

.placeholder {
  color: #999;
  text-align: center;
  padding: 20px;
}
</style>
