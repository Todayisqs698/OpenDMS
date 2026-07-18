<template>
    <view class="logs">
        <view class="log-item" v-for="(log, i) in logs" :key="i">
            <text class="log-time">{{ log.time }}</text>
            <text class="log-type" :class="log.type">{{ log.type }}</text>
            <text class="log-text">{{ log.text }}</text>
        </view>
        <view v-if="logs.length === 0" class="empty">
            <text>暂无日志</text>
        </view>
    </view>
</template>

<script>
export default {
    data() {
        return { logs: [] }
    },
    onLoad() {
        // 从本地存储加载历史日志
        const stored = uni.getStorageSync('drive_logs') || []
        this.logs = stored
    },
}
</script>

<style>
.logs { padding: 20rpx; background: #0f0f1e; min-height: 100vh; }
.log-item { display: flex; gap: 20rpx; padding: 15rpx; background: #1a1a2e; border-radius: 10rpx; margin-bottom: 10rpx; }
.log-time { color: #666; font-size: 24rpx; flex-shrink: 0; }
.log-type { font-size: 24rpx; padding: 2rpx 10rpx; border-radius: 6rpx; }
.log-type.warning { color: #faad14; background: rgba(250,173,20,0.1); }
.log-type.danger { color: #ff4d4f; background: rgba(255,77,79,0.1); }
.log-type.info { color: #4FC3F7; background: rgba(79,195,247,0.1); }
.log-text { color: #aaa; font-size: 24rpx; flex: 1; }
.empty { text-align: center; color: #666; padding: 100rpx; }
</style>
