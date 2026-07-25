<template>
    <view class="logs-page">
        <!-- 顶栏统计 -->
        <view class="stats-bar">
            <view class="stat-item">
                <text class="stat-num">{{ logs.length }}</text>
                <text class="stat-label">总事件</text>
            </view>
            <view class="stat-item">
                <text class="stat-num warn">{{ warningCount }}</text>
                <text class="stat-label">警告</text>
            </view>
            <view class="stat-item">
                <text class="stat-num danger">{{ dangerCount }}</text>
                <text class="stat-label">危险</text>
            </view>
            <view class="stat-item" @click="clearLogs">
                <text class="stat-num clear">🗑️</text>
                <text class="stat-label">清空</text>
            </view>
        </view>

        <!-- 筛选标签 -->
        <scroll-view scroll-x class="filter-bar">
            <view class="filter-tabs">
                <view
                    v-for="tab in filterTabs"
                    :key="tab.key"
                    class="filter-tab"
                    :class="{ active: activeFilter === tab.key }"
                    @click="activeFilter = tab.key"
                >
                    <text>{{ tab.label }}</text>
                </view>
            </view>
        </scroll-view>

        <!-- 日志列表 -->
        <scroll-view scroll-y class="log-list">
            <view v-if="filteredLogs.length === 0" class="empty">
                <text class="empty-icon">📋</text>
                <text class="empty-text">暂无日志记录</text>
                <text class="empty-hint">驾驶事件将自动记录在此</text>
            </view>

            <view
                v-for="(log, i) in filteredLogs"
                :key="i"
                class="log-card"
                :class="'log-' + log.level"
            >
                <view class="log-header">
                    <text class="log-type-tag" :class="'tag-' + log.type">{{ typeLabel(log.type) }}</text>
                    <text class="log-time">{{ formatTime(log.time) }}</text>
                </view>
                <text class="log-text">{{ log.text }}</text>
                <view class="log-meta" v-if="log.detail">
                    <text class="log-detail">{{ log.detail }}</text>
                </view>
            </view>
        </scroll-view>

        <!-- 驾驶洞察 -->
        <view class="insight-section" v-if="insight">
            <view class="insight-card">
                <text class="insight-title">AI 驾驶洞察</text>
                <text class="insight-text">{{ insight }}</text>
                <view class="insight-refresh" @click="fetchInsight">
                    <text>🔄 刷新</text>
                </view>
            </view>
        </view>
    </view>
</template>

<script>
import config from '@/utils/config.js'

export default {
    data() {
        return {
            logs: [],
            activeFilter: 'all',
            insight: '',
            filterTabs: [
                { key: 'all', label: '全部' },
                { key: 'safety', label: '安全' },
                { key: 'ac', label: '空调' },
                { key: 'music', label: '音乐' },
                { key: 'agent', label: 'Agent' },
                { key: 'nav', label: '导航' },
            ],
        }
    },

    computed: {
        filteredLogs() {
            if (this.activeFilter === 'all') return this.logs
            return this.logs.filter(l => l.type === this.activeFilter)
        },
        warningCount() {
            return this.logs.filter(l => l.level === 'warning').length
        },
        dangerCount() {
            return this.logs.filter(l => l.level === 'danger').length
        },
    },

    onLoad() {
        this.loadLogs()
        this.fetchInsight()
    },

    onShow() {
        // 每次显示时重新加载（可能有新日志）
        this.loadLogs()
    },

    methods: {
        loadLogs() {
            const stored = uni.getStorageSync('drive_logs') || []
            this.logs = stored.sort((a, b) => b.time - a.time)
        },

        clearLogs() {
            uni.showModal({
                title: '确认清空',
                content: '将删除所有日志记录，不可恢复',
                success: (res) => {
                    if (res.confirm) {
                        this.logs = []
                        uni.removeStorageSync('drive_logs')
                        uni.showToast({ title: '已清空', icon: 'success' })
                    }
                }
            })
        },

        fetchInsight() {
            uni.request({
                url: config.url(config.DRIVE_INSIGHT_API),
                timeout: 15000,
                success: (res) => {
                    if (res.data && res.data.insight) {
                        this.insight = res.data.insight
                    } else if (res.data && res.data.text) {
                        this.insight = res.data.text
                    }
                },
                fail: () => {
                    // 静默失败
                }
            })
        },

        typeLabel(type) {
            const labels = {
                safety: '安全',
                ac: '空调',
                music: '音乐',
                agent: 'Agent',
                nav: '导航',
                system: '系统',
            }
            return labels[type] || type
        },

        formatTime(timestamp) {
            if (!timestamp) return ''
            const d = new Date(timestamp)
            const pad = (n) => String(n).padStart(2, '0')
            return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
        },
    },
}
</script>

<style>
.logs-page {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background-color: #0f0f1e;
}

/* 统计栏 */
.stats-bar {
    display: flex;
    justify-content: space-around;
    padding: 20rpx;
    background-color: #1a1a2e;
}
.stat-item {
    display: flex;
    flex-direction: column;
    align-items: center;
}
.stat-num {
    font-size: 36rpx;
    font-weight: bold;
    color: #4FC3F7;
}
.stat-num.warn { color: #faad14; }
.stat-num.danger { color: #ff4d4f; }
.stat-num.clear { font-size: 32rpx; }
.stat-label {
    font-size: 22rpx;
    color: #666;
    margin-top: 4rpx;
}

/* 筛选 */
.filter-bar {
    background-color: #1a1a2e;
    border-bottom: 1rpx solid #2d2d4e;
    white-space: nowrap;
}
.filter-tabs {
    display: flex;
    padding: 0 10rpx;
}
.filter-tab {
    padding: 15rpx 25rpx;
    flex-shrink: 0;
}
.filter-tab text {
    font-size: 26rpx;
    color: #888;
}
.filter-tab.active text {
    color: #4FC3F7;
    font-weight: bold;
}
.filter-tab.active {
    border-bottom: 4rpx solid #4FC3F7;
}

/* 日志列表 */
.log-list {
    flex: 1;
    padding: 15rpx;
}

/* 空状态 */
.empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 120rpx 0;
}
.empty-icon {
    font-size: 80rpx;
    margin-bottom: 20rpx;
}
.empty-text {
    font-size: 28rpx;
    color: #666;
}
.empty-hint {
    font-size: 22rpx;
    color: #444;
    margin-top: 10rpx;
}

/* 日志卡片 */
.log-card {
    background-color: #1a1a2e;
    border-radius: 12rpx;
    padding: 20rpx;
    margin-bottom: 12rpx;
    border-left: 6rpx solid #4FC3F7;
}
.log-card.log-warning {
    border-left-color: #faad14;
}
.log-card.log-danger {
    border-left-color: #ff4d4f;
}
.log-card.log-info {
    border-left-color: #4FC3F7;
}
.log-card.log-success {
    border-left-color: #52c41a;
}

.log-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10rpx;
}
.log-type-tag {
    font-size: 20rpx;
    padding: 4rpx 12rpx;
    border-radius: 6rpx;
    background-color: rgba(79, 195, 247, 0.15);
    color: #4FC3F7;
}
.tag-safety { background-color: rgba(255, 77, 79, 0.15); color: #ff4d4f; }
.tag-ac { background-color: rgba(79, 195, 247, 0.15); color: #4FC3F7; }
.tag-music { background-color: rgba(82, 196, 26, 0.15); color: #52c41a; }
.tag-agent { background-color: rgba(168, 85, 247, 0.15); color: #a855f7; }
.tag-nav { background-color: rgba(250, 173, 20, 0.15); color: #faad14; }
.tag-system { background-color: rgba(102, 102, 102, 0.15); color: #999; }

.log-time {
    font-size: 22rpx;
    color: #666;
}
.log-text {
    font-size: 26rpx;
    color: #e0e0e0;
    line-height: 1.5;
}
.log-meta {
    margin-top: 8rpx;
}
.log-detail {
    font-size: 22rpx;
    color: #888;
}

/* 洞察 */
.insight-section {
    padding: 15rpx;
}
.insight-card {
    background-color: rgba(79, 195, 247, 0.1);
    border: 1rpx solid rgba(79, 195, 247, 0.3);
    border-radius: 12rpx;
    padding: 20rpx;
}
.insight-title {
    font-size: 24rpx;
    color: #4FC3F7;
    font-weight: bold;
    display: block;
    margin-bottom: 10rpx;
}
.insight-text {
    font-size: 24rpx;
    color: #ccc;
    line-height: 1.5;
}
.insight-refresh {
    margin-top: 10rpx;
    text-align: right;
}
.insight-refresh text {
    font-size: 22rpx;
    color: #4FC3F7;
}
</style>
