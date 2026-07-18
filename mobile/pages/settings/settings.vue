<template>
    <view class="settings">
        <view class="panel">
            <text class="panel-title">后端地址</text>
            <input class="url-input" v-model="apiBase" placeholder="http://192.168.1.100:8000" />
            <button class="save-btn" @click="saveApiBase">保存</button>
        </view>

        <view class="panel">
            <text class="panel-title">功能开关</text>
            <view class="toggle-row">
                <text>语音播报</text>
                <switch :checked="ttsEnabled" @change="onTtsToggle" />
            </view>
            <view class="toggle-row">
                <text>面部标记</text>
                <switch :checked="showLandmarks" @change="onLandmarkToggle" />
            </view>
        </view>

        <view class="panel">
            <text class="panel-title">关于</text>
            <text class="info">EdgeGuard v1.0</text>
            <text class="info">边缘智能驾驶安全多模态交互系统</text>
            <text class="info">第5组 | 大模型应用开发实训</text>
        </view>
    </view>
</template>

<script>
import config from '@/utils/config.js'

export default {
    data() {
        return {
            apiBase: '',
            ttsEnabled: true,
            showLandmarks: false,
        }
    },

    onLoad() {
        this.apiBase = config.getApiBase()
        this.ttsEnabled = uni.getStorageSync('tts_enabled') !== false
        this.showLandmarks = uni.getStorageSync('show_landmarks') === true
    },

    methods: {
        saveApiBase() {
            config.setApiBase(this.apiBase)
            uni.showToast({ title: '已保存', icon: 'success' })
        },

        onTtsToggle(e) {
            this.ttsEnabled = e.detail.value
            uni.setStorageSync('tts_enabled', this.ttsEnabled)
        },

        onLandmarkToggle(e) {
            this.showLandmarks = e.detail.value
            uni.setStorageSync('show_landmarks', this.showLandmarks)
        },
    },
}
</script>

<style>
.settings {
    padding: 20rpx;
    background-color: #0f0f1e;
    min-height: 100vh;
}

.panel {
    background-color: #1a1a2e;
    border-radius: 20rpx;
    padding: 30rpx;
    margin-bottom: 20rpx;
}

.panel-title {
    font-size: 28rpx;
    color: #888;
    margin-bottom: 20rpx;
    display: block;
}

.url-input {
    background-color: #2d2d4e;
    color: #e0e0e0;
    padding: 20rpx;
    border-radius: 10rpx;
    font-size: 26rpx;
    width: 100%;
    box-sizing: border-box;
}

.save-btn {
    margin-top: 20rpx;
    background-color: #4FC3F7;
    color: #fff;
    border-radius: 10rpx;
    font-size: 26rpx;
}

.toggle-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15rpx 0;
}

.info {
    display: block;
    color: #888;
    font-size: 24rpx;
    line-height: 1.8;
}
</style>
