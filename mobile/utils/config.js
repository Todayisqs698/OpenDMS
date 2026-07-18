/**
 * EdgeGuard 移动端 — 全局配置
 * 后端 API 地址（兰需根据实际部署修改）
 */
const CONFIG = {
    // 局域网部署：改成 PC 的 IP 地址
    // 云部署：改成公网地址
    API_BASE: 'http://192.168.1.100:8000',
    WS_BASE: 'ws://192.168.1.100:8000/ws/mobile',

    // 天气 API（复用后端）
    WEATHER_API: '/api/weather',

    // AI 分析
    ANALYZE_API: '/api/analyze',

    // 驾驶报告
    REPORT_API: '/api/drive/report',

    // 状态
    STATUS_API: '/api/status',
}

export default {
    ...CONFIG,

    /**
     * 获取后端地址（动态配置，存 localStorage）
     */
    getApiBase() {
        const saved = uni.getStorageSync('api_base')
        return saved || CONFIG.API_BASE
    },

    setApiBase(url) {
        uni.setStorageSync('api_base', url)
    },

    getWsBase() {
        const base = this.getApiBase()
        return base.replace('http', 'ws') + '/ws/mobile'
    },
}
