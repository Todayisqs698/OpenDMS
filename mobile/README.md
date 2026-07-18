# EdgeGuard 移动端 (uni-app)

> 兰 (yin102570) 负责的移动端迁移项目

## 快速开始

### 1. 安装 HBuilderX

下载地址: https://www.dcloud.io/hbuilderx.html

### 2. 导入项目

1. 打开 HBuilderX
2. 文件 → 导入 → 从本地目录导入
3. 选择 `mobile/` 目录

### 3. 配置后端地址

1. 打开 `pages/settings/settings.vue` 或运行后在"设置"页修改
2. 默认地址: `http://192.168.1.100:8000`
3. 改成你 PC 的实际 IP 地址

### 4. 运行

- **真机调试:** 运行 → 运行到手机或模拟器
- **编译 APK:** 发行 → 原生 App-云打包 或 本地打包

## 项目结构

```
mobile/
├── App.vue                    # 根组件
├── main.js                    # 入口
├── manifest.json              # 应用配置（权限、图标等）
├── pages.json                 # 页面路由 + tabBar
├── pages/
│   ├── dashboard/dashboard.vue  # 主页（驾驶大屏）
│   ├── settings/settings.vue    # 设置页
│   └── logs/logs.vue            # 驾驶日志
└── utils/
    └── config.js              # 后端地址配置
```

## 权限说明

| 权限 | 用途 |
|------|------|
| CAMERA | 摄像头（后端推流） |
| RECORD_AUDIO | 语音交互 |
| ACCESS_FINE_LOCATION | GPS 定位 |
| INTERNET | 网络通信 |

## 后端部署

手机需要连接后端服务。两种方案：

1. **局域网:** PC 运行 FastAPI，手机连同一 WiFi
2. **云服务器:** 部署到 Railway/Render 等免费平台

详见 `docs/迁移方案.md`
