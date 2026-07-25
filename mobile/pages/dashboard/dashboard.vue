<template>
    <view class="dashboard">
        <!-- 顶栏 -->
        <view class="top-bar">
            <text class="title">EdgeGuard v2.0</text>
            <text class="time">{{ currentTime }}</text>
            <view class="status">
                <text class="attention">注意力 {{ attentionScore }}%</text>
                <text class="dot" :class="{ offline: isOffline }"></text>
                <text class="net-status">{{ isOffline ? '离线' : '在线' }}</text>
            </view>
        </view>

        <!-- 主内容区 -->
        <scroll-view scroll-y class="main-content">
            <!-- 摄像头预览 -->
            <view class="panel camera-panel" @click="refreshCamera">
                <image v-if="cameraUrl" :src="cameraUrl" mode="aspectFill" class="camera-img" @error="onCameraError" />
                <view v-else class="camera-placeholder">
                    <text class="placeholder-text">摄像头加载中...</text>
                </view>
                <view class="camera-overlay" v-if="driverState.gaze && driverState.gaze !== 'center'">
                    <text class="gaze-warn">⚠️ 视线: {{ driverState.gaze }}</text>
                </view>
            </view>

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
                        <text class="metric-label">疲劳分数</text>
                        <text class="metric-value" :class="fatigueClass">{{ fatigueScore }}</text>
                    </view>
                    <view class="metric-row">
                        <text class="metric-label">驾驶状态</text>
                        <text class="metric-value" :class="fatigueClass">{{ driverState.state || '正常' }}</text>
                    </view>
                </view>
            </view>

            <!-- 安全告警 -->
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

            <!-- 空调控制 -->
            <view class="panel">
                <text class="panel-title">空调控制</text>
                <view class="ac-controls">
                    <view class="ac-temp-row">
                        <button class="ac-btn-sm" @click="acCommand('temp_down')">−</button>
                        <text class="ac-temp">{{ acState.temperature || 24 }}°C</text>
                        <button class="ac-btn-sm" @click="acCommand('temp_up')">+</button>
                    </view>
                    <view class="ac-modes">
                        <button class="ac-mode-btn" :class="{ active: acState.power }" @click="acCommand(acState.power ? 'TurnOffAC' : 'TurnOnAC')">
                            {{ acState.power ? '⏻ 已开' : '⏻ 开启' }}
                        </button>
                        <button class="ac-mode-btn" @click="acCommand('cool')">❄️</button>
                        <button class="ac-mode-btn" @click="acCommand('heat')">🔥</button>
                        <button class="ac-mode-btn" @click="acCommand('auto')">🔄</button>
                    </view>
                </view>
            </view>

            <!-- 音乐播放器 -->
            <view class="panel">
                <text class="panel-title">音乐播放</text>
                <view class="music-info" v-if="musicState.current_song">
                    <text class="music-name">{{ musicState.current_song.name }}</text>
                    <text class="music-artist">{{ musicState.current_song.artist }}</text>
                </view>
                <view class="music-search-row">
                    <input class="music-input" v-model="musicKeyword" placeholder="搜索歌曲/歌手..." />
                    <button class="music-search-btn" @click="searchMusic" :disabled="!musicKeyword.trim()">🔍</button>
                </view>
                <view class="music-controls">
                    <button class="music-btn" @click="musicControl('previous_track')">⏮</button>
                    <button class="music-btn play" @click="musicControl(musicState.is_playing ? 'StopMusic' : 'resume')">{{ musicState.is_playing ? '⏸' : '▶' }}</button>
                    <button class="music-btn" @click="musicControl('next_track')">⏭</button>
                </view>
            </view>

            <!-- 语音交互 -->
            <view class="panel voice-panel">
                <text class="panel-title">语音交互 (ReAct Agent)</text>
                <view class="voice-history" v-if="messages.length > 0">
                    <view v-for="(msg, i) in messages.slice(-5)" :key="i" class="voice-msg" :class="msg.role">
                        <text class="msg-role">{{ msg.role === 'user' ? '🧑' : '🤖' }}</text>
                        <text class="msg-text">{{ msg.text }}</text>
                    </view>
                </view>
                <view v-else class="placeholder">
                    <text>点击麦克风开始语音交互</text>
                </view>
                <view class="voice-input-row">
                    <input class="voice-input" v-model="inputText" placeholder="输入或语音..." @confirm="sendText" />
                    <button class="voice-btn" @click="startVoice" :disabled="listening">{{ listening ? '🎙️' : '🎤' }}</button>
                    <button class="voice-btn send" @click="sendText" :disabled="!inputText.trim()">➤</button>
                </view>
                <view class="agent-steps" v-if="agentSteps.length > 0">
                    <text class="steps-title">Agent 思维链:</text>
                    <view v-for="(step, i) in agentSteps" :key="i" class="agent-step">
                        <text class="step-text">{{ step }}</text>
                    </view>
                </view>
            </view>
        </scroll-view>

        <!-- AI 主动播报 -->
        <view v-if="insightMsg" class="insight-toast" @click="insightMsg = ''">
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
            driverState: { gaze: '--', gesture: '--', state: '正常' },
            fatigueScore: 0,
            fatigueLevel: 'normal',
            lastDecision: { action_code: 'normal' },
            insightMsg: '',
            // 摄像头
            cameraUrl: '',
            cameraTimer: null,
            // 空调
            acState: { power: false, temperature: 24 },
            // 音乐
            musicState: { current_song: null, is_playing: false },
            musicKeyword: '',
            // 语音交互
            inputText: '',
            messages: [],
            listening: false,
            agentSteps: [],
            // WebSocket
            wsTask: null,
            clockTimer: null,
            statusTimer: null,
            acTimer: null,
            musicTimer: null,
        }
    },
    computed: {
        severity() { return this.lastDecision.severity || 'mild' },
        shouldAlert() {
            return this.lastDecision.action_code !== 'normal' && this.lastDecision.recommendation_text
        },
        alertText() { return this.lastDecision.recommendation_text || '检测到分心驾驶' },
        severityIcon() {
            return { mild: '⚠️', moderate: '🟠', severe: '🔴' }[this.severity] || '⚠️'
        },
        fatigueClass() { return 'level-' + this.fatigueLevel },
    },
    onLoad() {
        this.initClock()
        this.connectWebSocket()
        this.checkStatus()
        this.refreshCamera()
        this.fetchAcState()
        this.fetchMusicState()
    },
    onUnload() {
        clearInterval(this.clockTimer)
        clearInterval(this.statusTimer)
        clearInterval(this.cameraTimer)
        clearInterval(this.acTimer)
        clearInterval(this.musicTimer)
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

        // ── 摄像头预览 ──
        refreshCamera() {
            this.cameraUrl = config.url(config.CAMERA_FRAME_API) + '?t=' + Date.now() + '&landmarks=1'
        },
        onCameraError() {
            setTimeout(() => this.refreshCamera(), 3000)
        },

        // ── WebSocket ──
        connectWebSocket() {
            const wsUrl = config.getWsBase() + '/ws/mobile'
            this.wsTask = uni.connectSocket({ url: wsUrl, complete: () => {} })
            this.wsTask.onOpen(() => { this.isOffline = false })
            this.wsTask.onMessage((res) => {
                try {
                    const msg = JSON.parse(res.data)
                    this.handleWsMessage(msg)
                } catch (e) {}
            })
            this.wsTask.onClose(() => {
                this.isOffline = true
                setTimeout(() => this.connectWebSocket(), 5000)
            })
            this.wsTask.onError(() => { this.isOffline = true })
        },
        handleWsMessage(msg) {
            if (msg.type === 'ai_decision') {
                const d = msg.data || {}
                this.driverState = {
                    gaze: d.gaze || this.driverState.gaze,
                    gesture: d.gesture || this.driverState.gesture,
                    state: d.state || this.driverState.state,
                }
                this.lastDecision = {
                    action_code: d.action_code || 'normal',
                    recommendation_text: d.recommendation_text,
                    severity: d.severity || 'mild',
                }
                if (d.metrics) {
                    this.fatigueScore = d.metrics.fatigue_score || 0
                    this.fatigueLevel = d.metrics.fatigue_level || 'normal'
                }
            } else if (msg.type === 'driver_state') {
                Object.assign(this.driverState, msg.data || {})
            } else if (msg.type === 'environment') {
                this.weather = msg.data || {}
            } else if (msg.type === 'agent_think') {
                this.agentSteps.push(msg.data?.text || '')
            } else if (msg.type === 'agent_tool_call') {
                this.agentSteps.push('🔧 调用工具: ' + (msg.data?.tool || ''))
            } else if (msg.type === 'agent_final') {
                const text = msg.data?.text || ''
                if (text) {
                    this.messages.push({ role: 'ai', text })
                }
                this.agentSteps = []
            }
        },

        // ── 状态检查 ──
        checkStatus() {
            this._doCheck()
            this.statusTimer = setInterval(() => this._doCheck(), 10000)
        },
        _doCheck() {
            uni.request({
                url: config.url(config.STATUS_API),
                success: (res) => {
                    this.isOffline = res.data.offline_mode || false
                    if (res.data.driver_state) {
                        this.driverState.state = res.data.driver_state.state || '正常'
                        this.fatigueScore = res.data.driver_state.risk_score || 0
                    }
                },
                fail: () => { this.isOffline = true }
            })
        },

        // ── 空调控制 ──
        fetchAcState() {
            uni.request({
                url: config.url(config.AC_STATE_API),
                success: (res) => { this.acState = res.data || this.acState }
            })
            this.acTimer = setInterval(() => {
                uni.request({
                    url: config.url(config.AC_STATE_API),
                    success: (res) => { this.acState = res.data || this.acState }
                })
            }, 5000)
        },
        acCommand(command) {
            uni.request({
                url: config.url(config.AC_COMMAND_API),
                method: 'POST',
                data: { command },
                success: (res) => {
                    if (res.data.status === 'ok') {
                        uni.showToast({ title: '已执行', icon: 'success', duration: 1000 })
                        this.fetchAcState()
                    }
                }
            })
        },

        // ── 音乐控制 ──
        fetchMusicState() {
            uni.request({
                url: config.url(config.MUSIC_STATE_API),
                success: (res) => { this.musicState = res.data || this.musicState }
            })
            this.musicTimer = setInterval(() => {
                uni.request({
                    url: config.url(config.MUSIC_STATE_API),
                    success: (res) => { this.musicState = res.data || this.musicState }
                })
            }, 5000)
        },
        searchMusic() {
            const kw = this.musicKeyword.trim()
            if (!kw) return
            uni.request({
                url: config.url(config.MUSIC_SEARCH_API),
                method: 'POST',
                data: { keyword: kw },
                success: (res) => {
                    const songs = res.data.songs || []
                    if (songs.length > 0) {
                        uni.request({
                            url: config.url(config.MUSIC_PLAY_API),
                            method: 'POST',
                            data: { song_id: songs[0].id },
                            success: () => {
                                uni.showToast({ title: '播放: ' + songs[0].name, icon: 'none' })
                                this.fetchMusicState()
                            }
                        })
                    } else {
                        uni.showToast({ title: '未找到歌曲', icon: 'none' })
                    }
                }
            })
        },
        musicControl(command) {
            uni.request({
                url: config.url('/api/music/control'),
                method: 'POST',
                data: { command },
                success: () => { this.fetchMusicState() }
            })
        },

        // ── 语音交互 ──
        startVoice() {
            this.listening = true
            // #ifdef APP
            plus.speech.startRecognize({
                engine: 'iFly',
                prompt: '请说话...',
            }, (result) => {
                this.listening = false
                const text = typeof result === 'string' ? result : (result.result || '')
                if (text) {
                    this.inputText = text
                    this.sendText()
                }
            }, (err) => {
                this.listening = false
                uni.showToast({ title: '语音识别失败', icon: 'none' })
            })
            // #endif
            // #ifdef H5
            // H5 环境使用浏览器 Web Speech API
            if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
                const SR = window.SpeechRecognition || window.webkitSpeechRecognition
                const rec = new SR()
                rec.lang = 'zh-CN'
                rec.continuous = false
                rec.interimResults = false
                rec.onresult = (event) => {
                    this.listening = false
                    const text = event.results[0][0].transcript || ''
                    if (text) {
                        this.inputText = text
                        this.sendText()
                    }
                }
                rec.onerror = () => {
                    this.listening = false
                    uni.showToast({ title: '语音识别失败', icon: 'none' })
                }
                rec.start()
            } else {
                this.listening = false
                uni.showToast({ title: '浏览器不支持语音识别', icon: 'none' })
            }
            // #endif
        },
        async sendText() {
            const text = this.inputText.trim()
            if (!text) return
            this.messages.push({ role: 'user', text })
            this.inputText = ''
            this.agentSteps = []

            // 快速路由：简单指令直通
            const quickResult = this.quickRoute(text)
            if (quickResult) {
                this.messages.push({ role: 'ai', text: quickResult.label })
                if (quickResult.type === 'ac') this.acCommand(quickResult.command)
                else if (quickResult.type === 'music') this.musicControl(quickResult.command)
                else if (quickResult.type === 'music_search') {
                    this.musicKeyword = quickResult.keyword
                    this.searchMusic()
                }
                return
            }

            // 复杂指令 → ReAct Agent
            uni.showLoading({ title: 'Agent 思考中...' })
            uni.request({
                url: config.url(config.AGENT_CHAT_API),
                method: 'POST',
                data: { text, driver_state: this.driverState },
                timeout: 60000,
                success: (res) => {
                    uni.hideLoading()
                    if (res.data.status === 'ok') {
                        const reply = res.data.result?.reply_text || '（未收到回复）'
                        this.messages.push({ role: 'ai', text: reply })
                    } else {
                        this.messages.push({ role: 'ai', text: '处理失败，请重试' })
                    }
                },
                fail: () => {
                    uni.hideLoading()
                    // 超时但 WebSocket 可能已有结果
                    this.messages.push({ role: 'ai', text: '正在处理中，结果请查看上方...' })
                }
            })
        },
        quickRoute(text) {
            const COMPOSITE = ['并', '同时', '还有', '然后', '顺便', '以及']
            if (COMPOSITE.some(m => text.includes(m))) return null

            const patterns = [
                { p: /打开空调|开空调/, type: 'ac', command: 'TurnOnAC', label: '已开启空调' },
                { p: /关闭空调|关掉空调/, type: 'ac', command: 'TurnOffAC', label: '已关闭空调' },
                { p: /太热/, type: 'ac', command: 'set', params: { temperature: 22 }, label: '已调低温度至22度' },
                { p: /太冷/, type: 'ac', command: 'set', params: { temperature: 26 }, label: '已调高温度至26度' },
                { p: /暂停|停止播放/, type: 'music', command: 'StopMusic', label: '已暂停播放' },
                { p: /下一首|换一首/, type: 'music', command: 'next_track', label: '切换下一首' },
                { p: /上一首/, type: 'music', command: 'previous_track', label: '切换上一首' },
            ]
            for (const item of patterns) {
                if (item.p.test(text)) return item
            }
            // 音乐搜索
            const m = text.match(/播放(.+?)的歌|来一首(.+)/)
            if (m) {
                const kw = (m[1] || m[2] || '').trim()
                if (kw) return { type: 'music_search', keyword: kw, label: `搜索: ${kw}` }
            }
            return null
        },
    },
}
</script>

<style>
.dashboard { display: flex; flex-direction: column; height: 100vh; background-color: #0f0f1e; color: #e0e0e0; }
.top-bar { display: flex; justify-content: space-between; align-items: center; padding: 15rpx 30rpx; background-color: #1a1a2e; height: 88rpx; }
.title { font-size: 28rpx; font-weight: bold; color: #4FC3F7; }
.time { font-size: 32rpx; color: #e0e0e0; }
.status { display: flex; align-items: center; gap: 10rpx; }
.attention { font-size: 24rpx; color: #52c41a; }
.dot { width: 16rpx; height: 16rpx; border-radius: 50%; background-color: #52c41a; }
.dot.offline { background-color: #ff4d4f; }
.main-content { flex: 1; padding: 20rpx; }

/* 摄像头 */
.camera-panel { padding: 0; overflow: hidden; position: relative; }
.camera-img { width: 100%; height: 300rpx; }
.camera-placeholder { height: 300rpx; display: flex; align-items: center; justify-content: center; }
.placeholder-text { color: #666; font-size: 24rpx; }
.camera-overlay { position: absolute; top: 10rpx; right: 10rpx; background: rgba(0,0,0,0.7); padding: 6rpx 16rpx; border-radius: 8rpx; }
.gaze-warn { color: #faad14; font-size: 22rpx; }

/* 面板 */
.panel { background-color: #1a1a2e; border-radius: 20rpx; padding: 30rpx; margin-bottom: 20rpx; }
.panel.alerted { border: 2rpx solid #faad14; }
.panel-title { font-size: 28rpx; color: #888; margin-bottom: 20rpx; display: block; }

/* AI 指标 */
.metric-row { display: flex; justify-content: space-between; padding: 10rpx 0; }
.metric-label { color: #888; font-size: 26rpx; }
.metric-value { color: #e0e0e0; font-size: 26rpx; font-weight: bold; }
.level-normal { color: #52c41a; }
.level-warning { color: #faad14; }
.level-danger { color: #ff4d4f; }

/* 告警 */
.alert-content { display: flex; align-items: center; gap: 15rpx; padding: 20rpx; border-radius: 10rpx; }
.sev-mild { background-color: rgba(250,173,20,0.15); border-left: 6rpx solid #faad14; }
.sev-moderate { background-color: rgba(250,140,20,0.2); border-left: 6rpx solid #fa8c16; }
.sev-severe { background-color: rgba(255,77,79,0.2); border-left: 6rpx solid #ff4d4f; }
.alert-icon { font-size: 40rpx; }
.alert-text { font-size: 26rpx; color: #e0e0e0; flex: 1; }
.alert-ok { display: flex; align-items: center; gap: 15rpx; color: #52c41a; }
.ok-icon { font-size: 32rpx; font-weight: bold; }

/* 空调 */
.ac-controls { display: flex; flex-direction: column; gap: 20rpx; }
.ac-temp-row { display: flex; align-items: center; justify-content: center; gap: 30rpx; }
.ac-temp { font-size: 48rpx; font-weight: bold; color: #4FC3F7; }
.ac-btn-sm { width: 60rpx; height: 60rpx; border-radius: 50%; background-color: #2d2d4e; color: #4FC3F7; font-size: 36rpx; display: flex; align-items: center; justify-content: center; }
.ac-modes { display: flex; gap: 15rpx; }
.ac-mode-btn { flex: 1; background-color: #2d2d4e; color: #888; border-radius: 10rpx; font-size: 28rpx; padding: 15rpx 0; }
.ac-mode-btn.active { background-color: #4FC3F7; color: #fff; }

/* 音乐 */
.music-info { margin-bottom: 15rpx; }
.music-name { font-size: 28rpx; color: #e0e0e0; display: block; }
.music-artist { font-size: 24rpx; color: #888; }
.music-search-row { display: flex; gap: 15rpx; margin-bottom: 15rpx; }
.music-input { flex: 1; background-color: #2d2d4e; color: #e0e0e0; padding: 15rpx 20rpx; border-radius: 10rpx; font-size: 26rpx; }
.music-search-btn { width: 80rpx; background-color: #4FC3F7; color: #fff; border-radius: 10rpx; }
.music-controls { display: flex; gap: 20rpx; justify-content: center; }
.music-btn { width: 80rpx; height: 80rpx; border-radius: 50%; background-color: #2d2d4e; color: #4FC3F7; font-size: 32rpx; display: flex; align-items: center; justify-content: center; }
.music-btn.play { width: 100rpx; height: 100rpx; background-color: #4FC3F7; color: #fff; font-size: 40rpx; }

/* 语音交互 */
.voice-panel { padding-bottom: 30rpx; }
.voice-history { max-height: 400rpx; margin-bottom: 20rpx; }
.voice-msg { display: flex; gap: 15rpx; padding: 10rpx 0; }
.voice-msg.user { justify-content: flex-end; }
.msg-role { font-size: 32rpx; }
.msg-text { font-size: 26rpx; color: #e0e0e0; max-width: 500rpx; }
.voice-msg.user .msg-text { color: #4FC3F7; }
.placeholder { text-align: center; color: #666; font-size: 24rpx; padding: 30rpx 0; }
.voice-input-row { display: flex; gap: 15rpx; margin-bottom: 15rpx; }
.voice-input { flex: 1; background-color: #2d2d4e; color: #e0e0e0; padding: 15rpx 20rpx; border-radius: 10rpx; font-size: 26rpx; }
.voice-btn { width: 80rpx; height: 80rpx; border-radius: 50%; background-color: #2d2d4e; font-size: 32rpx; display: flex; align-items: center; justify-content: center; }
.voice-btn.send { background-color: #4FC3F7; color: #fff; }
.agent-steps { background-color: #0f0f1e; border-radius: 10rpx; padding: 15rpx; }
.steps-title { font-size: 22rpx; color: #666; display: block; margin-bottom: 10rpx; }
.agent-step { padding: 5rpx 0; }
.step-text { font-size: 22rpx; color: #4FC3F7; }

/* AI 播报 */
.insight-toast { position: fixed; bottom: 120rpx; left: 30rpx; right: 30rpx; background-color: rgba(79,195,247,0.9); color: #fff; padding: 20rpx; border-radius: 10rpx; text-align: center; font-size: 26rpx; }
</style>
