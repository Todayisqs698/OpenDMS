<template>
  <section class="panel ai-panel">
    <h2>AI 决策链路</h2>
    <p v-if="!decision" class="placeholder">等待安全决策数据...</p>
    <div v-else class="decision-content">
      <div class="risk-block">
        <span class="label">综合风险等级：</span>
        <span
          class="risk-tag"
          :class="{
            'risk-danger': decision.severity === 'severe',
            'risk-warn': decision.severity === 'moderate' || decision.severity === 'mild',
            'risk-safe': decision.severity === 'normal'
          }"
        >
          {{ riskTextMap[decision.severity] || decision.severity || '正常' }}
        </span>
      </div>
      <div v-if="decision.recommendation_text" class="alert-block">
        <span class="label">安全告警提示：</span>
        <p class="alert-text">{{ decision.recommendation_text }}</p>
      </div>
      <div v-if="decision.source" class="source-block">
        <span class="label">决策来源：</span>
        <span class="source-tag">{{ decision.source }}</span>
      </div>
      <!-- 疲劳指标 -->
      <div v-if="driverState" class="metrics-block">
        <h4>实时疲劳分析指标</h4>
        <p>PERCLOS 闭眼占比：{{ driverState.perclos != null ? (driverState.perclos * 100).toFixed(1) + '%' : '--' }}</p>
        <p>平均眨眼频率：{{ driverState.blink_rate != null ? driverState.blink_rate + '/min' : '--' }}</p>
        <p>疲劳综合分数：{{ driverState.fatigue_score != null ? driverState.fatigue_score : '--' }}</p>
        <p>疲劳等级：{{ fatigueTextMap[driverState.fatigue_level] || driverState.fatigue_level || '--' }}</p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
defineProps({
  decision: { type: Object, default: null },
  driverState: { type: Object, default: null }
})

const riskTextMap = {
  normal: '正常',
  mild: '轻度分心',
  moderate: '中度分心',
  severe: '严重分心',
  distracted: '中度分心',
  dangerous: '重度危险',
  attn_declining: '注意力下降',
}

const fatigueTextMap = {
  normal: '正常',
  warning: '轻度疲劳',
  danger: '重度疲劳',
}
</script>

<style scoped>
.ai-panel {
  margin-top: 24px;
  padding: 20px;
  border: 1px solid #1e293b;
  border-radius: 10px;
  background: #111827;
  color: #e0e6ed;
}
.placeholder {
  color: #94a3b8;
  font-size: 15px;
}
.decision-content {
  margin-top: 12px;
}
.label {
  font-weight: bold;
  font-size: 16px;
  color: #cbd5e1;
}
.risk-tag {
  padding: 4px 10px;
  border-radius: 6px;
  color: #fff;
  margin-left: 8px;
}
.risk-danger {
  background-color: #ef4444;
}
.risk-warn {
  background-color: #f59e0b;
}
.risk-safe {
  background-color: #10b981;
}
.alert-block {
  margin: 12px 0;
  padding: 10px;
  background-color: #422006;
  border-radius: 6px;
}
.alert-text {
  color: #fdba74;
  margin: 4px 0 0;
}
.metrics-block {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #334155;
}
.metrics-block h4 {
  margin: 0 0 8px;
  font-size: 16px;
  color: #94a3b8;
}
.metrics-block p {
  margin: 6px 0;
  font-size: 15px;
  color: #cbd5e1;
}
</style>