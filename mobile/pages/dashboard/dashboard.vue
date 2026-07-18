<template>
    <view class="dashboard">
        <!-- 顶栏 -->
        <view class="top-bar">
            <text class="title">EdgeGuard v1.0</text>
            <text class="time">{{ currentTime }}</text>
            <view class="status">
                <text class="attention">注意力 {{ attentionScore }}%</text>
                <text class="dot" :class="{ offline: isOffline }"></text>
                <text class="net-status">{{ isOffline ? '离线' : '在线' }}</text>
            </view>
        </view>

        <!-- 主内容区 -->
        <scroll-view scroll-y class="main-content">
            <!-- AI 状态面板 -->
            <view class="panel">
                <text class="panel-title">AI 状态</text>
                <view class="ai-metrics">
                    <view class="metric-row">
                        <text class="metric-label">视线</text>
                        <text class="metric-value">{{ driverState.gaze || '--' }}</text>
                    </view>
                    <view class="metric-row">
                        <text class="metric-label">手势</text>
                        <text class="metric-value">{{ driverState.gesture || '--' }}</text>
                    </view>
                    <view class="metric-row">
                        <text class="metric-label">路由</text>
                        <text class="metric-value">{{ driverState.route || '--' }}</text>
                    </view>
                    <view class="metric-row">
                        <text class="metric-label">疲劳分数</text>
                        <text class="metric-value" :class="fatigueClass">{{ fatigueScore }}</text>
                    </view>
                </view>
            </view>

            <!-- 天气/导航面板 -->
            <view class="panel">
                <text class="panel-title">环境</text>
                <view class="weather">
                    <text class="weather-emoji">{{ weather.weather_emoji || '❓' }}</text>
                    <view class="weather-info">
                        <text class="weather-temp">{{ weather.temperature || '--' }}°C</text>
                        <text class="weather-desc">{{ weather.weather_desc || '获取中...' }}</text>
                        <text class="weather-city">{{ weather.city || '定位中...' }}</text>
                    </view>
                </view>
                <text class="driving-context">{{ weather.driving_context || '' }}</text>
            </view>

            <!-- 告警面板 -->
            <view class="panel" :class="{ alerted: shouldAlert }">
                <text class="panel-title">安全告警</text>
                <view v-if="shouldAlert" class="alert-content" :class="'sev-' + severity">
                    <text class="alert-icon">{{ severityIcon }}</text>
                    <text class="alert-text">{{ alertText }}</text>
                </view>
                <view v-else class="alert-ok">
                    <text class="ok-icon">✓</text>
                    <text>驾驶状态正常</text>
                </view>
            </view>
        </scroll-view>

        <!-- 底部操作栏 -->
        <view class="bottom-bar">
            <button class="action-btn" @click="refreshWeather">刷新天气</button>
            <button class="action-btn" @click="genReport">驾驶报告</button>
        </view>

        <!-- AI 主动播报 -->
        <view v-if="insightMsg" class="insight-toast">
            <text>AI: {{ insightMsg }}</text>
        </view>
    </view>
</template>

<script>
import config from '@/utils/config.js'

export default {
    data() {
        return {
            currentTime: '',
            isOffline: false,
            attentionScore: 100,
            driverState: { gaze: '--', gesture: '--', route: '--' },
            weather: {},
            fatigueScore: 0,
            fatigueLevel: 'normal',
            lastDecision: { action_code: 'normal' },
            insightMsg: '',
            wsTask: null,
            clockTimer: null,
            statusTimer: null,
        }
    },

    computed: {
        severity() {
            return this.lastDecision.severity || 'mild'
        },
        shouldAlert() {
            return this.lastDecision.action_code !== 'normal' &&
                   this.lastDecision.recommendation_text
        },
        alertText() {
            return this.lastDecision.recommendation_text || '检测到分心驾驶'
        },
        severityIcon() {
            return { mild: '⚠️', moderate: '🟠', severe: '🔴' }[this.severity] || '⚠️'
        },
        fatigueClass() {
            return 'level-' + this.fatigueLevel
        },
    },

    onLoad() {
        this.initClock()
        this.connectWebSocket()
        this.checkStatus()
        this.fetchWeather()
    },

    onUnload() {
        clearInterval(this.clockTimer)
        clearInterval(this.statusTimer)
        if (this.wsTask) this.wsTask.close()
    },

    methods: {
        initClock() {
            this.updateClock()
            this.clockTimer = setInterval(() => this.updateClock(), 1000)
        },

        updateClock() {
            const now = new Date()
            this.currentTime = now.toLocaleTimeString('zh-CN')
        },

        connectWebSocket() {
            const wsUrl = config.getWsBase()
            this.wsTask = uni.connectSocket({
                url: wsUrl,
                complete: () => {}
            })

            this.wsTask.onOpen(() => {
                console.log('WebSocket 已连接')
                this.isOffline = false
            })

            this.wsTask.onMessage((res) => {
                try {
                    const msg = JSON.parse(res.data)
                    this.handleWsMessage(msg)
                } catch (e) {
                    console.error('WS 解析失败:', e)
                }
            })

            this.wsTask.onClose(() => {
                console.log('WebSocket 断开，5秒后重连')
                this.isOffline = true
                setTimeout(() => this.connectWebSocket(), 5000)
            })

            this.wsTask.onError(() => {
                this.isOffline = true
            })
        },

        handleWsMessage(msg) {
            if (msg.type === 'ai_decision') {
                const data = msg.data || {}
                this.driverState = {
                    gaze: data.gaze || '--',
                    gesture: data.gesture || '--',
                    route: data.route || '--',
                }
                this.lastDecision = {
                    action_code: data.action_code || 'normal',
                    recommendation_text: data.recommendation_text,
                    severity: data.severity || 'mild',
                }
                if (data.metrics) {
                    this.fatigueScore = data.metrics.fatigue_score || 0
                    this.fatigueLevel = data.metrics.fatigue_level || 'normal'
                }
            } else if (msg.type === 'driver_state') {
                const d = msg.data || {}
                this.driverState = { ...this.driverState, ...d }
                if (d.confidence !== undefined) {
                    this.attentionScore = d.confidence
                }
            } else if (msg.type === 'environment') {
                this.weather = msg.data || {}
            }
        },

        checkStatus() {
            uni.request({
                url: config.getApiBase() + config.STATUS_API,
                success: (res) => {
                    this.isOffline = res.data.offline_mode || false
                },
                fail: () => { this.isOffline = true }
            })
            this.statusTimer = setInterval(() => {
                uni.request({
                    url: config.getApiBase() + config.STATUS_API,
                    success: (res) => {
                        this.isOffline = res.data.offline_mode || false
                    },
                    fail: () => { this.isOffline = true }
                })
            }, 10000)
        },

        fetchWeather() {
            // 获取 GPS 定位
            uni.getLocation({
                type: 'gcj02',
                success: (loc) => {
                    console.log('GPS 定位成功:', loc.latitude, loc.longitude)
                    this.weather.city = '定位成功，获取天气中...'
                    uni.request({
                        url: config.getApiBase() + '/api/environment',
                        method: 'POST',
                        data: { lat: loc.latitude, lon: loc.longitude },
                        success: (res) => {
                            this.weather = res.data
                        },
                        fail: (e) => {
                            console.error('天气获取失败:', e)
                            this.weather.weather_desc = '天气获取失败'
                        }
                    })
                },
                fail: (e) => {
                    console.error('GPS 定位失败:', e)
                    this.weather.city = '定位失败'
                    // 降级用默认城市
                    uni.request({
                        url: config.getApiBase() + '/api/environment',
                        method: 'POST',
                        data: {},
                        success: (res) => { this.weather = res.data },
                        fail: () => { this.weather.weather_desc = '天气获取失败' }
                    })
                }
            })
        },

        refreshWeather() {
            uni.showLoading({ title: '刷新中...' })
            this.fetchWeather()
            setTimeout(() => uni.hideLoading(), 1500)
        },

        genReport() {
            uni.showLoading({ title: '生成报告中...' })
            uni.request({
                url: config.getApiBase() + config.REPORT_API,
                method: 'POST',
                success: (res) => {
                    uni.hideLoading()
                    if (res.data.report) {
                        uni.showModal({
                            title: '驾驶报告',
                            content: res.data.report,
                            showCancel: false,
                        })
                    }
                },
                fail: () => {
                    uni.hideLoading()
                    uni.showToast({ title: '报告生成失败', icon: 'none' })
                }
            })
        },
    },
}
</script>

<style>
.dashboard {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background-color: #0f0f1e;
    color: #e0e0e0;
}

.top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15rpx 30rpx;
    background-color: #1a1a2e;
    height: 88rpx;
}

.title {
    font-size: 28rpx;
    font-weight: bold;
    color: #4FC3F7;
}

.time {
    font-size: 32rpx;
    color: #e0e0e0;
}

.status {
    display: flex;
    align-items: center;
    gap: 10rpx;
}

.attention {
    font-size: 24rpx;
    color: #52c41a;
}

.dot {
    width: 16rpx;
    height: 16rpx;
    border-radius: 50%;
    background-color: #52c41a;
}

.dot.offline {
    background-color: #ff4d4f;
}

.main-content {
    flex: 1;
    padding: 20rpx;
}

.panel {
    background-color: #1a1a2e;
    border-radius: 20rpx;
    padding: 30rpx;
    margin-bottom: 20rpx;
}

.panel.alerted {
    border: 2rpx solid #faad14;
}

.panel-title {
    font-size: 28rpx;
    color: #888;
    margin-bottom: 20rpx;
}

.metric-row {
    display: flex;
    justify-content: space-between;
    padding: 10rpx 0;
}

.metric-label {
    color: #888;
    font-size: 26rpx;
}

.metric-value {
    color: #e0e0e0;
    font-size: 26rpx;
    font-weight: bold;
}

.level-normal { color: #52c41a; }
.level-warning { color: #faad14; }
.level-danger { color: #ff4d4f; }

.weather {
    display: flex;
    align-items: center;
    gap: 20rpx;
    margin-bottom: 15rpx;
}

.weather-emoji {
    font-size: 60rpx;
}

.weather-temp {
    font-size: 40rpx;
    font-weight: bold;
    color: #e0e0e0;
}

.weather-desc {
    font-size: 26rpx;
    color: #aaa;
}

.weather-city {
    font-size: 24rpx;
    color: #666;
}

.driving-context {
    font-size: 24rpx;
    color: #4FC3F7;
    margin-top: 10rpx;
}

.alert-content {
    display: flex;
    align-items: center;
    gap: 15rpx;
    padding: 20rpx;
    border-radius: 10rpx;
}

.sev-mild {
    background-color: rgba(250, 173, 20, 0.15);
    border-left: 6rpx solid #faad14;
}

.sev-moderate {
    background-color: rgba(250, 140, 20, 0.2);
    border-left: 6rpx solid #fa8c16;
}

.sev-severe {
    background-color: rgba(255, 77, 79, 0.2);
    border-left: 6rpx solid #ff4d4f;
}

.alert-icon {
    font-size: 40rpx;
}

.alert-text {
    font-size: 26rpx;
    color: #e0e0e0;
}

.alert-ok {
    display: flex;
    align-items: center;
    gap: 15rpx;
    color: #52c41a;
}

.ok-icon {
    font-size: 32rpx;
    font-weight: bold;
}

.bottom-bar {
    display: flex;
    gap: 20rpx;
    padding: 20rpx;
    background-color: #1a1a2e;
}

.action-btn {
    flex: 1;
    background-color: #2d2d4e;
    color: #4FC3F7;
    border-radius: 10rpx;
    font-size: 26rpx;
}

.insight-toast {
    position: fixed;
    bottom: 120rpx;
    left: 30rpx;
    right: 30rpx;
    background-color: rgba(79, 195, 247, 0.9);
    color: #fff;
    padding: 20rpx;
    border-radius: 10rpx;
    text-align: center;
    font-size: 26rpx;
}
</style>
