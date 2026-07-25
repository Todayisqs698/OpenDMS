<template>
  <div class="flex h-full flex-col gap-4 overflow-y-auto p-4">
    <h2 class="text-sm font-semibold text-muted-foreground">设置</h2>

    <div class="flex flex-col gap-2">
      <div class="flex items-center justify-between rounded-xl bg-card p-4">
        <div>
          <div class="text-sm font-medium">面部标记</div>
          <div class="text-[11px] text-muted-foreground">摄像头画面显示面部关键点</div>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" :checked="landmarksOn" @change="$emit('toggleLandmarks')">
          <span class="toggle-slider"></span>
        </label>
      </div>

      <div class="flex items-center justify-between rounded-xl bg-card p-4">
        <div>
          <div class="text-sm font-medium">浅色模式</div>
          <div class="text-[11px] text-muted-foreground">切换浅色/深色主题</div>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" :checked="lightMode" @change="$emit('toggleTheme')">
          <span class="toggle-slider"></span>
        </label>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  landmarksOn: boolean
  lightMode: boolean
}>()

defineEmits<{
  toggleLandmarks: []
  toggleTheme: []
}>()
</script>

<style scoped>
.toggle-switch { position: relative; display: inline-block; width: 36px; height: 20px; }
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.toggle-slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background: #334155; border-radius: 20px; transition: .2s; }
.toggle-slider::before { content: ''; position: absolute; height: 14px; width: 14px; left: 3px; bottom: 3px; background: #94a3b8; border-radius: 50%; transition: .2s; }
input:checked + .toggle-slider { background: #22c55e; }
input:checked + .toggle-slider::before { transform: translateX(16px); background: #fff; }
</style>
