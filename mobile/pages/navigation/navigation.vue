<template>
    <view class="nav-page">
        <!-- 地图区域 -->
        <view class="map-section">
            <map
                id="navMap"
                class="nav-map"
                :latitude="centerLat"
                :longitude="centerLon"
                :scale="mapScale"
                :markers="markers"
                :polyline="polylines"
                @markertap="onMarkerTap"
                @regionchange="onRegionChange"
                show-location
            ></map>

            <!-- GPS 控制浮层 -->
            <view class="map-overlay">
                <view class="gps-btn-group">
                    <view class="gps-btn" @click="getLocationOnce">
                        <text class="gps-icon">📍</text>
                        <text class="gps-label">{{ locating ? '定位中...' : '定位' }}</text>
                    </view>
                    <view class="gps-btn" :class="{ active: tracking }" @click="toggleTracking">
                        <text class="gps-icon">{{ tracking ? '⏸' : '🛰️' }}</text>
                        <text class="gps-label">{{ tracking ? '停止' : '追踪' }}</text>
                    </view>
                    <view class="gps-btn" @click="recenterMap">
                        <text class="gps-icon">🎯</text>
                        <text class="gps-label">居中</text>
                    </view>
                </view>
            </view>

            <!-- GPS 状态 -->
            <view class="gps-status-bar" v-if="gpsStatus">
                <text :class="['status-dot', gpsStatusType]"></text>
                <text class="status-text">{{ gpsStatus }}</text>
            </view>
        </view>

        <!-- 路线规划 -->
        <view class="route-section">
            <view class="route-input-row">
                <input
                    class="route-input"
                    v-model="destination"
                    placeholder="输入目的地（如 北京天安门）"
                    @confirm="planRoute"
                />
                <button class="route-btn" @click="planRoute" :disabled="!destination.trim() || planning">
                    {{ planning ? '...' : '导航' }}
                </button>
            </view>

            <!-- 路线信息 -->
            <view class="route-info" v-if="routeInfo">
                <view class="route-summary">
                    <view class="route-item">
                        <text class="route-label">目的地</text>
                        <text class="route-value">{{ routeInfo.destination }}</text>
                    </view>
                    <view class="route-item">
                        <text class="route-label">距离</text>
                        <text class="route-value highlight">{{ routeInfo.distance }}km</text>
                    </view>
                    <view class="route-item">
                        <text class="route-label">预计</text>
                        <text class="route-value highlight">{{ routeInfo.duration }}分钟</text>
                    </view>
                </view>

                <!-- 路线步骤 -->
                <view class="route-steps" v-if="routeInfo.steps && routeInfo.steps.length > 0">
                    <text class="steps-title">路线指引</text>
                    <scroll-view scroll-y class="steps-scroll">
                        <view v-for="(step, i) in routeInfo.steps" :key="i" class="step-item">
                            <text class="step-num">{{ i + 1 }}</text>
                            <text class="step-text">{{ step.instruction || step }}</text>
                            <text class="step-dist" v-if="step.distance">{{ step.distance }}m</text>
                        </view>
                    </scroll-view>
                </view>

                <!-- 在高德地图中打开 -->
                <view class="open-amap" @click="openInAmap">
                    <text>🧭 在高德地图中打开</text>
                </view>
            </view>
        </view>

        <!-- 天气卡片 -->
        <view class="weather-section" v-if="weatherData">
            <view class="weather-card">
                <view class="weather-main">
                    <text class="weather-emoji">{{ weatherEmoji }}</text>
                    <text class="weather-temp">{{ weatherData.temperature != null ? weatherData.temperature + '°' : '--' }}</text>
                </view>
                <view class="weather-detail">
                    <text class="weather-desc">{{ weatherData.weather || weatherData.description || '未知' }}</text>
                    <text class="weather-city">{{ weatherData.city || '当前位置' }}</text>
                </view>
            </view>

            <view class="env-grid">
                <view class="env-cell">
                    <text class="env-cell-label">💧 湿度</text>
                    <text class="env-cell-value">{{ weatherData.humidity != null ? weatherData.humidity + '%' : '--' }}</text>
                </view>
                <view class="env-cell">
                    <text class="env-cell-label">💨 风速</text>
                    <text class="env-cell-value">{{ weatherData.wind_speed != null ? weatherData.wind_speed + 'km/h' : '--' }}</text>
                </view>
                <view class="env-cell">
                    <text class="env-cell-label">👁️ 能见度</text>
                    <text class="env-cell-value">{{ weatherData.visibility != null ? weatherData.visibility + 'km' : '--' }}</text>
                </view>
                <view class="env-cell" v-if="weatherData.risk_score != null">
                    <text class="env-cell-label">⚠️ 风险</text>
                    <text class="env-cell-value" :class="riskClass">{{ riskDisplay }}</text>
                </view>
            </view>

            <!-- 驾驶建议 -->
            <view class="driving-tip" v-if="weatherData.driving_context">
                <text class="tip-icon">🚗</text>
                <text class="tip-text">{{ weatherData.driving_context }}</text>
            </view>

            <!-- 预警 -->
            <view class="alert-list" v-if="weatherData.alerts && weatherData.alerts.length > 0">
                <view v-for="(alert, i) in weatherData.alerts" :key="i" class="alert-item" :class="'alert-' + (alert.level || 'info')">
                    <text class="alert-icon">{{ alert.icon || '⚠️' }}</text>
                    <text class="alert-text">{{ alert.text }}</text>
                </view>
            </view>
        </view>

        <!-- 当前位置信息 -->
        <view class="location-section">
            <view class="loc-row">
                <text class="loc-icon">📍</text>
                <text class="loc-text">{{ currentCity || '未知位置' }}</text>
                <text class="loc-coord">{{ centerLat.toFixed(4) }}, {{ centerLon.toFixed(4) }}</text>
            </view>
        </view>
    </view>
</template>

<script>
import config from '@/utils/config.js'

export default {
    data() {
        return {
            // 地图
            centerLat: 39.9042,
            centerLon: 116.4074,
            mapScale: 13,
            markers: [],
            polylines: [],

            // GPS
            locating: false,
            tracking: false,
            gpsStatus: '',
            gpsStatusType: 'ok',
            trackTimer: null,
            currentCity: '',

            // 路线
            destination: '',
            planning: false,
            routeInfo: null,
            destLat: null,
            destLon: null,

            // 天气
            weatherData: null,
            weatherTimer: null,

            // 地图上下文
            mapCtx: null,
        }
    },

    computed: {
        weatherEmoji() {
            const w = (this.weatherData?.weather || '').toLowerCase()
            if (w.includes('晴')) return '☀️'
            if (w.includes('多云')) return '⛅'
            if (w.includes('阴')) return '☁️'
            if (w.includes('雨')) return w.includes('大') || w.includes('暴') ? '⛈️' : '🌧️'
            if (w.includes('雪')) return '❄️'
            if (w.includes('雾') || w.includes('霾')) return '🌫️'
            return '🌤️'
        },
        riskClass() {
            const r = this.weatherData?.risk_score || 0
            if (r >= 70) return 'risk-high'
            if (r >= 40) return 'risk-medium'
            return 'risk-low'
        },
        riskDisplay() {
            const r = this.weatherData?.risk_score || 0
            if (r >= 70) return '高风险'
            if (r >= 40) return '中等'
            return '低风险'
        },
    },

    onLoad() {
        this.mapCtx = uni.createMapContext('navMap', this)
        this.getLocationOnce()
        this.fetchWeather()
    },

    onUnload() {
        if (this.trackTimer) clearInterval(this.trackTimer)
        if (this.weatherTimer) clearInterval(this.weatherTimer)
    },

    methods: {
        // ── GPS 定位 ──
        getLocationOnce() {
            this.locating = true
            this.gpsStatus = '正在获取位置...'
            this.gpsStatusType = 'warn'

            uni.getLocation({
                type: 'gcj02',
                altitude: false,
                success: (res) => {
                    this.locating = false
                    this.gpsStatus = `定位成功（精度${Math.round(res.accuracy || 0)}m）`
                    this.gpsStatusType = 'ok'
                    this.updateLocation(res.latitude, res.longitude)
                },
                fail: (err) => {
                    this.locating = false
                    // 尝试低精度
                    this.gpsStatus = '高精度失败，尝试低精度...'
                    uni.getLocation({
                        type: 'wgs84',
                        success: (res) => {
                            this.gpsStatus = `定位成功（低精度）`
                            this.gpsStatusType = 'ok'
                            this.updateLocation(res.latitude, res.longitude)
                        },
                        fail: () => {
                            this.gpsStatus = '定位失败，使用默认位置'
                            this.gpsStatusType = 'error'
                            this.updateLocation(this.centerLat, this.centerLon)
                        }
                    })
                }
            })
        },

        toggleTracking() {
            if (this.tracking) {
                if (this.trackTimer) {
                    clearInterval(this.trackTimer)
                    this.trackTimer = null
                }
                this.tracking = false
                this.gpsStatus = '追踪已停止'
                this.gpsStatusType = 'warn'
            } else {
                this.tracking = true
                this.gpsStatus = '实时追踪中...'
                this.gpsStatusType = 'ok'
                // uni-app 无 watchLocation API，用 setInterval 轮询 getLocation
                this.trackTimer = setInterval(() => {
                    uni.getLocation({
                        type: 'gcj02',
                        success: (res) => {
                            // 仅在移动 >50m 时更新
                            if (this.calcDistance(res.latitude, res.longitude, this.centerLat, this.centerLon) > 0.05) {
                                this.gpsStatus = `追踪中（精度${Math.round(res.accuracy || 0)}m）`
                                this.updateLocation(res.latitude, res.longitude)
                            }
                        },
                        fail: () => {
                            this.gpsStatus = '追踪定位失败'
                            this.gpsStatusType = 'warn'
                        }
                    })
                }, 5000)
            }
        },

        recenterMap() {
            if (this.mapCtx) {
                this.mapCtx.moveToLocation({
                    success: () => {},
                    fail: () => {
                        // 手动设置中心
                        this.centerLat = this.centerLat + 0.0001
                    }
                })
            }
        },

        updateLocation(lat, lon) {
            this.centerLat = lat
            this.centerLon = lon

            // 更新 marker
            this.updateMarkers()

            // 上报位置到后端
            this.reportLocation(lat, lon)

            // 拉取天气
            this.fetchWeather(lat, lon)
        },

        updateMarkers() {
            const marks = [{
                id: 0,
                latitude: this.centerLat,
                longitude: this.centerLon,
                title: '当前位置',
                iconPath: '',
                width: 30,
                height: 30,
                callout: {
                    content: '📍 我的位置',
                    color: '#4FC3F7',
                    fontSize: 12,
                    borderRadius: 8,
                    bgColor: '#1a1a2e',
                    padding: 6,
                    display: 'BYCLICK'
                }
            }]

            if (this.destLat != null && this.destLon != null) {
                marks.push({
                    id: 1,
                    latitude: this.destLat,
                    longitude: this.destLon,
                    title: this.routeInfo?.destination || '目的地',
                    iconPath: '',
                    width: 30,
                    height: 30,
                    callout: {
                        content: '🚩 ' + (this.routeInfo?.destination || '目的地'),
                        color: '#ff4d4f',
                        fontSize: 12,
                        borderRadius: 8,
                        bgColor: '#1a1a2e',
                        padding: 6,
                        display: 'BYCLICK'
                    }
                })
            }

            this.markers = marks
        },

        async reportLocation(lat, lon) {
            uni.request({
                url: config.url(config.LOCATION_API),
                method: 'POST',
                data: { lat, lon },
                success: (res) => {
                    if (res.data && res.data.city) {
                        this.currentCity = res.data.city
                    }
                }
            })
        },

        // ── 天气 ──
        fetchWeather(lat, lon) {
            const params = {}
            if (lat != null && lon != null) {
                params.lat = lat
                params.lon = lon
            }

            uni.request({
                url: config.url(config.ENVIRONMENT_API),
                method: 'POST',
                data: params,
                timeout: 20000,
                success: (res) => {
                    if (res.data && res.data.data) {
                        this.weatherData = res.data.data
                    } else if (res.data) {
                        this.weatherData = res.data
                    }
                },
                fail: () => {
                    console.log('天气获取失败')
                }
            })

            // 定时刷新天气（每5分钟）
            if (this.weatherTimer) clearInterval(this.weatherTimer)
            this.weatherTimer = setInterval(() => {
                this.fetchWeather(this.centerLat, this.centerLon)
            }, 300000)
        },

        // ── 路线规划 ──
        async planRoute() {
            const dest = this.destination.trim()
            if (!dest || this.planning) return

            this.planning = true

            uni.request({
                url: config.url(config.NAVIGATION_API),
                method: 'POST',
                data: {
                    destination: dest,
                    origin_lat: this.centerLat,
                    origin_lon: this.centerLon,
                },
                timeout: 15000,
                success: (res) => {
                    this.planning = false
                    if (res.data && res.data.success !== false) {
                        const data = res.data.data || res.data
                        this.routeInfo = {
                            destination: data.destination || dest,
                            distance: data.distance || '--',
                            duration: data.duration || '--',
                            steps: data.steps || data.paths || [],
                        }

                        // 更新目的地坐标
                        if (data.dest_lat && data.dest_lon) {
                            this.destLat = data.dest_lat
                            this.destLon = data.dest_lon
                        }

                        // 更新 markers
                        this.updateMarkers()

                        // 绘制路线
                        if (data.polyline || data.path) {
                            this.drawRoute(data.polyline || data.path)
                        }

                        // 调整地图视野
                        this.fitRoute()

                        uni.showToast({ title: '路线已规划', icon: 'success' })
                    } else {
                        uni.showToast({ title: res.data?.error || '规划失败', icon: 'none' })
                    }
                },
                fail: (err) => {
                    this.planning = false
                    uni.showToast({ title: '网络错误，请重试', icon: 'none' })
                }
            })
        },

        drawRoute(polyline) {
            // polyline 格式: [[lat, lon], [lat, lon], ...] 或 [{latitude, longitude}, ...]
            let points = []
            if (Array.isArray(polyline)) {
                if (polyline[0] && typeof polyline[0] === 'object') {
                    if (polyline[0].latitude != null) {
                        // 已是 {latitude, longitude} 格式
                        points = polyline
                    } else if (polyline[0].length === 2) {
                        // [[lat, lon], ...] 格式 → 转换
                        points = polyline.map(p => ({ latitude: p[0], longitude: p[1] }))
                    }
                }
            }

            if (points.length > 0) {
                this.polylines = [{
                    points: points,
                    color: '#4FC3F7',
                    width: 6,
                    arrowLine: true,
                }]
            }
        },

        fitRoute() {
            if (this.destLat == null) return
            // 缩放地图以包含起点和终点
            const dist = this.calcDistance(this.centerLat, this.centerLon, this.destLat, this.destLon)
            if (dist > 50) this.mapScale = 7
            else if (dist > 20) this.mapScale = 9
            else if (dist > 5) this.mapScale = 11
            else this.mapScale = 13
        },

        // ── 在高德地图中打开 ──
        openInAmap() {
            if (!this.routeInfo) return
            const dest = encodeURIComponent(this.routeInfo.destination)
            const url = `https://uri.amap.com/navigation?to=${dest}&mode=car&src=EdgeGuard&coordinate=wgs84&callnative=1`
            // #ifdef APP
            plus.runtime.openURL(url, () => {
                // 高德 App 未安装，用内置浏览器打开
                plus.runtime.openURL(url)
            })
            // #endif
            // #ifdef H5
            window.open(url, '_blank')
            // #endif
        },

        // ── 地图事件 ──
        onMarkerTap(e) {
            // marker 点击事件
        },

        onRegionChange(e) {
            // 地图视野变化
        },

        // ── 工具 ──
        calcDistance(lat1, lon1, lat2, lon2) {
            const R = 6371
            const toRad = (x) => x * Math.PI / 180
            const dLat = toRad(lat2 - lat1)
            const dLon = toRad(lon2 - lon1)
            const a = Math.sin(dLat / 2) ** 2 +
                Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
            return 2 * R * Math.asin(Math.sqrt(a))
        },
    },
}
</script>

<style>
.nav-page {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    background-color: #0f0f1e;
}

/* 地图 */
.map-section {
    position: relative;
    width: 100%;
    height: 500rpx;
}
.nav-map {
    width: 100%;
    height: 100%;
}
.map-overlay {
    position: absolute;
    right: 20rpx;
    bottom: 20rpx;
    z-index: 100;
}
.gps-btn-group {
    display: flex;
    flex-direction: column;
    gap: 15rpx;
}
.gps-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 90rpx;
    height: 90rpx;
    border-radius: 50%;
    background-color: rgba(26, 26, 46, 0.9);
    border: 2rpx solid #4FC3F7;
}
.gps-btn.active {
    background-color: #4FC3F7;
}
.gps-icon {
    font-size: 32rpx;
}
.gps-label {
    font-size: 18rpx;
    color: #e0e0e0;
    margin-top: 2rpx;
}
.gps-btn.active .gps-label {
    color: #fff;
}
.gps-status-bar {
    position: absolute;
    left: 20rpx;
    top: 20rpx;
    display: flex;
    align-items: center;
    gap: 10rpx;
    background-color: rgba(26, 26, 46, 0.85);
    padding: 8rpx 20rpx;
    border-radius: 20rpx;
    z-index: 100;
}
.status-dot {
    width: 14rpx;
    height: 14rpx;
    border-radius: 50%;
    background-color: #52c41a;
}
.status-dot.warn { background-color: #faad14; }
.status-dot.error { background-color: #ff4d4f; }
.status-text {
    font-size: 22rpx;
    color: #e0e0e0;
}

/* 路线规划 */
.route-section {
    padding: 20rpx;
}
.route-input-row {
    display: flex;
    gap: 15rpx;
    margin-bottom: 20rpx;
}
.route-input {
    flex: 1;
    background-color: #1a1a2e;
    color: #e0e0e0;
    padding: 20rpx;
    border-radius: 12rpx;
    font-size: 26rpx;
}
.route-btn {
    width: 140rpx;
    background-color: #4FC3F7;
    color: #fff;
    border-radius: 12rpx;
    font-size: 26rpx;
    display: flex;
    align-items: center;
    justify-content: center;
}
.route-btn[disabled] {
    opacity: 0.5;
}

/* 路线信息 */
.route-info {
    background-color: #1a1a2e;
    border-radius: 16rpx;
    padding: 25rpx;
}
.route-summary {
    display: flex;
    justify-content: space-around;
    margin-bottom: 20rpx;
}
.route-item {
    display: flex;
    flex-direction: column;
    align-items: center;
}
.route-label {
    font-size: 22rpx;
    color: #666;
    margin-bottom: 6rpx;
}
.route-value {
    font-size: 28rpx;
    color: #e0e0e0;
    font-weight: bold;
}
.route-value.highlight {
    color: #4FC3F7;
    font-size: 32rpx;
}

/* 路线步骤 */
.route-steps {
    border-top: 1rpx solid #2d2d4e;
    padding-top: 20rpx;
}
.steps-title {
    font-size: 24rpx;
    color: #888;
    margin-bottom: 15rpx;
    display: block;
}
.steps-scroll {
    max-height: 300rpx;
}
.step-item {
    display: flex;
    align-items: center;
    gap: 15rpx;
    padding: 12rpx 0;
    border-bottom: 1rpx solid rgba(45, 45, 78, 0.5);
}
.step-num {
    width: 36rpx;
    height: 36rpx;
    border-radius: 50%;
    background-color: #4FC3F7;
    color: #fff;
    font-size: 20rpx;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.step-text {
    flex: 1;
    font-size: 24rpx;
    color: #ccc;
}
.step-dist {
    font-size: 22rpx;
    color: #666;
    flex-shrink: 0;
}

/* 打开高德 */
.open-amap {
    margin-top: 20rpx;
    text-align: center;
    padding: 15rpx;
    background-color: rgba(79, 195, 247, 0.15);
    border-radius: 10rpx;
}
.open-amap text {
    font-size: 24rpx;
    color: #4FC3F7;
}

/* 天气 */
.weather-section {
    padding: 0 20rpx 20rpx;
}
.weather-card {
    display: flex;
    align-items: center;
    gap: 20rpx;
    background-color: #1a1a2e;
    border-radius: 16rpx;
    padding: 25rpx;
    margin-bottom: 15rpx;
}
.weather-main {
    display: flex;
    align-items: center;
    gap: 10rpx;
}
.weather-emoji {
    font-size: 56rpx;
}
.weather-temp {
    font-size: 48rpx;
    font-weight: bold;
    color: #e0e0e0;
}
.weather-detail {
    display: flex;
    flex-direction: column;
}
.weather-desc {
    font-size: 28rpx;
    color: #e0e0e0;
}
.weather-city {
    font-size: 22rpx;
    color: #666;
}

/* 环境网格 */
.env-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 15rpx;
    margin-bottom: 15rpx;
}
.env-cell {
    flex: 1;
    min-width: 160rpx;
    background-color: #1a1a2e;
    border-radius: 12rpx;
    padding: 20rpx;
    display: flex;
    flex-direction: column;
    align-items: center;
}
.env-cell-label {
    font-size: 22rpx;
    color: #666;
    margin-bottom: 6rpx;
}
.env-cell-value {
    font-size: 28rpx;
    color: #e0e0e0;
    font-weight: bold;
}
.risk-low { color: #52c41a; }
.risk-medium { color: #faad14; }
.risk-high { color: #ff4d4f; }

/* 驾驶建议 */
.driving-tip {
    display: flex;
    align-items: center;
    gap: 15rpx;
    background-color: rgba(79, 195, 247, 0.1);
    border-left: 6rpx solid #4FC3F7;
    border-radius: 10rpx;
    padding: 15rpx 20rpx;
    margin-bottom: 15rpx;
}
.tip-icon {
    font-size: 32rpx;
}
.tip-text {
    font-size: 24rpx;
    color: #ccc;
    flex: 1;
}

/* 预警 */
.alert-list {
    display: flex;
    flex-direction: column;
    gap: 10rpx;
}
.alert-item {
    display: flex;
    align-items: center;
    gap: 15rpx;
    padding: 15rpx 20rpx;
    border-radius: 10rpx;
}
.alert-info {
    background-color: rgba(79, 195, 247, 0.1);
    border-left: 6rpx solid #4FC3F7;
}
.alert-warning {
    background-color: rgba(250, 173, 20, 0.15);
    border-left: 6rpx solid #faad14;
}
.alert-danger {
    background-color: rgba(255, 77, 79, 0.15);
    border-left: 6rpx solid #ff4d4f;
}
.alert-icon {
    font-size: 28rpx;
}
.alert-text {
    font-size: 24rpx;
    color: #ccc;
    flex: 1;
}

/* 位置信息 */
.location-section {
    padding: 0 20rpx 30rpx;
}
.loc-row {
    display: flex;
    align-items: center;
    gap: 15rpx;
    background-color: #1a1a2e;
    border-radius: 12rpx;
    padding: 20rpx;
}
.loc-icon {
    font-size: 28rpx;
}
.loc-text {
    font-size: 26rpx;
    color: #e0e0e0;
    flex: 1;
}
.loc-coord {
    font-size: 22rpx;
    color: #666;
}
</style>
