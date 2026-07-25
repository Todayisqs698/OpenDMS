<template>
    <view class="settings-page">
        <scroll-view scroll-y class="settings-scroll">
            <!-- 后端连接 -->
            <view class="panel">
                <text class="panel-title">后端连接</text>
                <view class="conn-status">
                    <view class="conn-dot" :class="connStatus"></view>
                    <text class="conn-text">{{ connText }}</text>
                    <text class="conn-latency" v-if="latency > 0">{{ latency }}ms</text>
                </view>
                <view class="input-row">
                    <input class="url-input" v-model="apiBase" placeholder="http://192.168.1.100:8000" />
                    <button class="test-btn" @click="testConnection" :disabled="testing">
                        {{ testing ? '...' : '测试' }}
                    </button>
                </view>
                <button class="save-btn" @click="saveApiBase">保存地址</button>

                <!-- 快速连接历史 -->
                <view class="history-list" v-if="urlHistory.length > 0">
                    <text class="history-title">最近使用</text>
                    <view v-for="(url, i) in urlHistory" :key="i" class="history-item" @click="apiBase = url">
                        <text class="history-url">{{ url }}</text>
                        <text class="history-arrow">→</text>
                    </view>
                </view>
            </view>

            <!-- 系统状态 -->
            <view class="panel" v-if="systemStatus">
                <text class="panel-title">系统状态</text>
                <view class="status-grid">
                    <view class="status-cell">
                        <text class="status-label">离线模式</text>
                        <text class="status-value" :class="systemStatus.offline_mode ? 'danger' : 'success'">
                            {{ systemStatus.offline_mode ? '是' : '否' }}
                        </text>
                    </view>
                    <view class="status-cell">
                        <text class="status-label">云延迟</text>
                        <text class="status-value">{{ systemStatus.cloud_latency || '--' }}ms</text>
                    </view>
                </view>

                <text class="sub-title">AI 模块</text>
                <view class="agent-list">
                    <view class="agent-row" v-for="(loaded, name) in (systemStatus.agents || {})" :key="name">
                        <text class="agent-name">{{ agentLabel(name) }}</text>
                        <view class="agent-dot" :class="loaded ? 'on' : 'off'"></view>
                        <text class="agent-state">{{ loaded ? '已加载' : '未加载' }}</text>
                    </view>
                </view>

                <view class="status-grid" v-if="systemStatus.driver_state">
                    <text class="sub-title">驾驶员状态</text>
                    <view class="status-cell">
                        <text class="status-label">状态</text>
                        <text class="status-value">{{ systemStatus.driver_state.state || '--' }}</text>
                    </view>
                    <view class="status-cell">
                        <text class="status-label">风险分</text>
                        <text class="status-value">{{ systemStatus.driver_state.risk_score || 0 }}</text>
                    </view>
                </view>
            </view>

            <!-- 功能开关 -->
            <view class="panel">
                <text class="panel-title">功能开关</text>
                <view class="toggle-row">
                    <view class="toggle-info">
                        <text class="toggle-label">语音播报</text>
                        <text class="toggle-desc">Agent 回复自动 TTS</text>
                    </view>
                    <switch :checked="ttsEnabled" @change="onTtsToggle" color="#4FC3F7" />
                </view>
                <view class="toggle-row">
                    <view class="toggle-info">
                        <text class="toggle-label">面部标记</text>
                        <text class="toggle-desc">摄像头叠加面部关键点</text>
                    </view>
                    <switch :checked="showLandmarks" @change="onLandmarkToggle" color="#4FC3F7" />
                </view>
                <view class="toggle-row">
                    <view class="toggle-info">
                        <text class="toggle-label">自动刷新</text>
                        <text class="toggle-desc">定时拉取状态/空调/音乐</text>
                    </view>
                    <switch :checked="autoRefresh" @change="onRefreshToggle" color="#4FC3F7" />
                </view>
                <view class="toggle-row">
                    <view class="toggle-info">
                        <text class="toggle-label">震动反馈</text>
                        <text class="toggle-desc">安全告警时震动提醒</text>
                    </view>
                    <switch :checked="vibrationEnabled" @change="onVibrationToggle" color="#4FC3F7" />
                </view>
            </view>

            <!-- 刷新间隔 -->
            <view class="panel">
                <text class="panel-title">刷新间隔</text>
                <view class="interval-list">
                    <view
                        v-for="opt in intervalOptions"
                        :key="opt.value"
                        class="interval-item"
                        :class="{ active: refreshInterval === opt.value }"
                        @click="setInterval(opt.value)"
                    >
                        <text>{{ opt.label }}</text>
                    </view>
                </view>
            </view>

            <!-- 关于 -->
            <view class="panel">
                <text class="panel-title">关于</text>
                <view class="about-row">
                    <text class="about-label">版本</text>
                    <text class="about-value">v2.0.0</text>
                </view>
                <view class="about-row">
                    <text class="about-label">名称</text>
                    <text class="about-value">EdgeGuard</text>
                </view>
                <view class="about-row">
                    <text class="about-label">描述</text>
                    <text class="about-value">边缘智能驾驶安全多模态交互系统</text>
                </view>
                <view class="about-row">
                    <text class="about-label">团队</text>
                    <text class="about-value">第5组 | 大模型应用开发实训</text>
                </view>
                <view class="about-row">
                    <text class="about-label">技术栈</text>
                    <text class="about-value">uni-app + FastAPI + LangGraph + DeepSeek</text>
                </view>
            </view>
        </scroll-view>
    </view>
</template>

<script>
import config from '@/utils/config.js'

export default {
    data() {
        return {
            apiBase: '',
            testing: false,
            connStatus: 'unknown',
            latency: 0,
            systemStatus: null,
            urlHistory: [],
            // 开关
            ttsEnabled: true,
            showLandmarks: false,
            autoRefresh: true,
            vibrationEnabled: true,
            // 刷新间隔
            refreshInterval: 5000,
            intervalOptions: [
                { label: '3秒', value: 3000 },
                { label: '5秒', value: 5000 },
                { label: '10秒', value: 10000 },
                { label: '关闭', value: 0 },
            ],
        }
    },

    computed: {
        connText() {
            return {
                online: '已连接',
                offline: '连接失败',
                testing: '测试中...',
                unknown: '未测试',
            }[this.connStatus] || '未测试'
        },
    },

    onLoad() {
        this.apiBase = config.getApiBase()
        this.ttsEnabled = uni.getStorageSync('tts_enabled') !== false
        this.showLandmarks = uni.getStorageSync('show_landmarks') === true
        this.autoRefresh = uni.getStorageSync('auto_refresh') !== false
        this.vibrationEnabled = uni.getStorageSync('vibration_enabled') !== false
        this.refreshInterval = uni.getStorageSync('refresh_interval') || 5000
        this.urlHistory = uni.getStorageSync('url_history') || []

        // 自动测试一次连接
        this.testConnection()
    },

    methods: {
        testConnection() {
            this.testing = true
            this.connStatus = 'testing'
            const startTime = Date.now()

            uni.request({
                url: config.url('/api/health'),
                timeout: 5000,
                success: (res) => {
                    this.latency = Date.now() - startTime
                    if (res.statusCode === 200 && res.data.status === 'ok') {
                        this.connStatus = 'online'
                        this.fetchSystemStatus()
                    } else {
                        this.connStatus = 'offline'
                    }
                },
                fail: () => {
                    this.latency = 0
                    this.connStatus = 'offline'
                },
                complete: () => {
                    this.testing = false
                }
            })
        },

        fetchSystemStatus() {
            uni.request({
                url: config.url(config.STATUS_API),
                timeout: 8000,
                success: (res) => {
                    if (res.data) {
                        this.systemStatus = res.data
                    }
                },
                fail: () => {}
            })
        },

        saveApiBase() {
            const url = this.apiBase.trim()
            if (!url) {
                uni.showToast({ title: '请输入地址', icon: 'none' })
                return
            }

            // 简单校验
            if (!url.startsWith('http://') && !url.startsWith('https://')) {
                uni.showToast({ title: '地址需以 http:// 开头', icon: 'none' })
                return
            }

            config.setApiBase(url)

            // 保存到历史
            let history = uni.getStorageSync('url_history') || []
            history = history.filter(u => u !== url)
            history.unshift(url)
            if (history.length > 5) history = history.slice(0, 5)
            uni.setStorageSync('url_history', history)
            this.urlHistory = history

            uni.showToast({ title: '已保存，测试连接中...', icon: 'success' })
            setTimeout(() => this.testConnection(), 500)
        },

        onTtsToggle(e) {
            this.ttsEnabled = e.detail.value
            uni.setStorageSync('tts_enabled', this.ttsEnabled)
        },

        onLandmarkToggle(e) {
            this.showLandmarks = e.detail.value
            uni.setStorageSync('show_landmarks', this.showLandmarks)
        },

        onRefreshToggle(e) {
            this.autoRefresh = e.detail.value
            uni.setStorageSync('auto_refresh', this.autoRefresh)
        },

        onVibrationToggle(e) {
            this.vibrationEnabled = e.detail.value
            uni.setStorageSync('vibration_enabled', this.vibrationEnabled)
        },

        setInterval(value) {
            this.refreshInterval = value
            uni.setStorageSync('refresh_interval', value)
        },

        agentLabel(name) {
            const labels = {
                safety: '安全检测',
                interaction: '交互Agent',
                environment: '环境Agent',
                react: 'ReAct Agent',
                orchestrator: '编排器',
            }
            return labels[name] || name
        },
    },
}
</script>

<style>
.settings-page {
    height: 100vh;
    background-color: #0f0f1e;
}
.settings-scroll {
    height: 100%;
    padding: 20rpx;
}

/* 面板 */
.panel {
    background-color: #1a1a2e;
    border-radius: 16rpx;
    padding: 30rpx;
    margin-bottom: 20rpx;
}
.panel-title {
    font-size: 28rpx;
    color: #888;
    margin-bottom: 20rpx;
    display: block;
    font-weight: bold;
}
.sub-title {
    font-size: 24rpx;
    color: #666;
    margin: 20rpx 0 10rpx;
    display: block;
}

/* 连接状态 */
.conn-status {
    display: flex;
    align-items: center;
    gap: 12rpx;
    margin-bottom: 20rpx;
}
.conn-dot {
    width: 20rpx;
    height: 20rpx;
    border-radius: 50%;
    background-color: #666;
}
.conn-dot.online { background-color: #52c41a; box-shadow: 0 0 8rpx #52c41a; }
.conn-dot.offline { background-color: #ff4d4f; }
.conn-dot.testing { background-color: #faad14; }
.conn-text {
    font-size: 28rpx;
    color: #e0e0e0;
    flex: 1;
}
.conn-latency {
    font-size: 24rpx;
    color: #52c41a;
    font-weight: bold;
}

/* 输入 */
.input-row {
    display: flex;
    gap: 15rpx;
    margin-bottom: 15rpx;
}
.url-input {
    flex: 1;
    background-color: #2d2d4e;
    color: #e0e0e0;
    padding: 20rpx;
    border-radius: 10rpx;
    font-size: 26rpx;
}
.test-btn {
    width: 120rpx;
    background-color: #2d2d4e;
    color: #4FC3F7;
    border: 1rpx solid #4FC3F7;
    border-radius: 10rpx;
    font-size: 26rpx;
    display: flex;
    align-items: center;
    justify-content: center;
}
.test-btn[disabled] {
    opacity: 0.5;
}
.save-btn {
    background-color: #4FC3F7;
    color: #fff;
    border-radius: 10rpx;
    font-size: 26rpx;
    width: 100%;
}

/* 历史 */
.history-list {
    margin-top: 20rpx;
    border-top: 1rpx solid #2d2d4e;
    padding-top: 15rpx;
}
.history-title {
    font-size: 22rpx;
    color: #666;
    margin-bottom: 10rpx;
    display: block;
}
.history-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12rpx 0;
    border-bottom: 1rpx solid rgba(45, 45, 78, 0.5);
}
.history-url {
    font-size: 24rpx;
    color: #4FC3F7;
    flex: 1;
}
.history-arrow {
    font-size: 24rpx;
    color: #666;
}

/* 状态网格 */
.status-grid {
    display: flex;
    gap: 15rpx;
    flex-wrap: wrap;
}
.status-cell {
    flex: 1;
    min-width: 200rpx;
    background-color: #2d2d4e;
    border-radius: 10rpx;
    padding: 15rpx 20rpx;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.status-label {
    font-size: 24rpx;
    color: #888;
}
.status-value {
    font-size: 26rpx;
    color: #e0e0e0;
    font-weight: bold;
}
.status-value.success { color: #52c41a; }
.status-value.danger { color: #ff4d4f; }

/* Agent 列表 */
.agent-list {
    display: flex;
    flex-direction: column;
}
.agent-row {
    display: flex;
    align-items: center;
    gap: 15rpx;
    padding: 12rpx 0;
    border-bottom: 1rpx solid rgba(45, 45, 78, 0.3);
}
.agent-name {
    font-size: 26rpx;
    color: #ccc;
    flex: 1;
}
.agent-dot {
    width: 14rpx;
    height: 14rpx;
    border-radius: 50%;
}
.agent-dot.on { background-color: #52c41a; }
.agent-dot.off { background-color: #ff4d4f; }
.agent-state {
    font-size: 22rpx;
    color: #666;
}

/* 开关 */
.toggle-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15rpx 0;
    border-bottom: 1rpx solid rgba(45, 45, 78, 0.3);
}
.toggle-info {
    flex: 1;
}
.toggle-label {
    font-size: 28rpx;
    color: #e0e0e0;
    display: block;
}
.toggle-desc {
    font-size: 22rpx;
    color: #666;
    margin-top: 4rpx;
}

/* 间隔 */
.interval-list {
    display: flex;
    gap: 15rpx;
    flex-wrap: wrap;
}
.interval-item {
    flex: 1;
    min-width: 120rpx;
    background-color: #2d2d4e;
    border-radius: 10rpx;
    padding: 15rpx;
    text-align: center;
}
.interval-item.active {
    background-color: #4FC3F7;
}
.interval-item text {
    font-size: 24rpx;
    color: #888;
}
.interval-item.active text {
    color: #fff;
    font-weight: bold;
}

/* 关于 */
.about-row {
    display: flex;
    justify-content: space-between;
    padding: 10rpx 0;
    border-bottom: 1rpx solid rgba(45, 45, 78, 0.3);
}
.about-label {
    font-size: 26rpx;
    color: #888;
    flex-shrink: 0;
}
.about-value {
    font-size: 26rpx;
    color: #e0e0e0;
    text-align: right;
    flex: 1;
    margin-left: 20rpx;
}
</style>
