/**
 * EdgeGuard 移动端 — 全局配置
 * 后端 API 地址（需根据实际部署修改）
 */
const CONFIG = {
    // 局域网部署：改成 PC 的 IP 地址
    // 云部署：改成公网地址
    API_BASE: 'http://192.168.1.100:8000',
    // API 端点
    STATUS_API: '/api/status',
    ANALYZE_API: '/api/analyze',
    AGENT_CHAT_API: '/api/agent/chat',
    AC_COMMAND_API: '/api/ac/command',
    AC_STATE_API: '/api/ac/state',
    MUSIC_SEARCH_API: '/api/music/search',
    MUSIC_PLAY_API: '/api/music/play',
    MUSIC_STATE_API: '/api/music/state',
    ENVIRONMENT_API: '/api/environment',
    NAVIGATION_API: '/api/navigation/route',
    LOCATION_API: '/api/location',
    TTS_API: '/api/tts',
    REPORT_API: '/api/drive/report',
    CAMERA_FRAME_API: '/api/camera/frame',
    DRIVE_INSIGHT_API: '/api/drive/insight',
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
        return base.replace('http', 'ws')
    },
    /**
     * 构建完整 API URL
     */
    url(path) {
        return this.getApiBase() + path
    },
}
