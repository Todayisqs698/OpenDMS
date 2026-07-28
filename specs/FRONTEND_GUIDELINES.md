# FRONTEND_GUIDELINES — EdgeGuard 前端设计规范

> **版本**: 1.0.0 | **最后更新**: 2026-07-26

---

## 1. 设计原则

| 原则 | 说明 |
|------|------|
| **安全优先** | 告警状态视觉层级最高，颜色对比度满足驾驶场景可读性 |
| **暗色为主** | 车载场景默认暗色主题，减少夜间眩光，支持浅色切换 |
| **一目了然** | 关键信息 200ms 内可辨识，告警 100ms 内可察觉 |
| **触控友好** | 最小触控区域 44×44px，间距足够防止误触 |
| **动画克制** | 仅告警/状态变化使用动画，避免驾驶场景注意力分散 |

---

## 2. 字体系统

### 2.1 字体族

| Token | 字体栈 | 用途 |
|-------|--------|------|
| `--font-sans` | `'Geist Sans', ui-sans-serif, system-ui, sans-serif` | 正文、UI 文本 |
| `--font-mono` | `'Geist Mono', ui-monospace, monospace` | 数据、状态码、时间戳 |

### 2.2 字号刻度 (Tailwind 默认扩展)

| 层级 | 字号 | 行高 | 用途 |
|------|------|------|------|
| `text-xs` | 0.75rem (12px) | 1rem | 标签、辅助信息 |
| `text-sm` | 0.875rem (14px) | 1.25rem | 面板正文、告警详情 |
| `text-base` | 1rem (16px) | 1.5rem | 主内容、对话文本 |
| `text-lg` | 1.125rem (18px) | 1.75rem | 面板标题 |
| `text-xl` | 1.25rem (20px) | 1.75rem | 区域标题 |
| `text-2xl` | 1.5rem (24px) | 2rem | 页面标题 |
| `text-3xl` | 1.875rem (30px) | 2.25rem | 核心数据 (速度、温度) |
| `text-4xl` | 2.25rem (36px) | 2.5rem | 大屏关键数值 |

### 2.3 字重

| Token | 值 | 用途 |
|-------|-----|------|
| `font-normal` | 400 | 正文 |
| `font-medium` | 500 | 标签、按钮文字 |
| `font-semibold` | 600 | 面板标题、导航 |
| `font-bold` | 700 | 告警文字、关键数据 |

---

## 3. 调色板

### 3.1 语义颜色 (OKLCH 色彩空间)

#### 浅色主题 (`:root`)

| Token | OKLCH 值 | HEX 近似 | 用途 |
|-------|---------|---------|------|
| `--background` | `oklch(0.98 0.01 255)` | `#F7F8FA` | 页面背景 |
| `--foreground` | `oklch(0.15 0.03 255)` | `#1A1D23` | 主文字 |
| `--card` | `oklch(1 0 0)` | `#FFFFFF` | 卡片背景 |
| `--card-foreground` | `oklch(0.15 0.03 255)` | `#1A1D23` | 卡片文字 |
| `--panel` | `oklch(0.96 0.01 255)` | `#EDEFF2` | 面板背景 |
| `--panel-foreground` | `oklch(0.15 0.03 255)` | `#1A1D23` | 面板文字 |
| `--popover` | `oklch(1 0 0)` | `#FFFFFF` | 弹出层背景 |
| `--popover-foreground` | `oklch(0.15 0.03 255)` | `#1A1D23` | 弹出层文字 |
| `--primary` | `oklch(0.5 0.15 230)` | `#2563EB` | 主色调 (蓝) |
| `--primary-foreground` | `oklch(1 0 0)` | `#FFFFFF` | 主色调上的文字 |
| `--secondary` | `oklch(0.94 0.01 255)` | `#E5E7EB` | 次要背景 |
| `--secondary-foreground` | `oklch(0.15 0.03 255)` | `#1A1D23` | 次要文字 |
| `--muted` | `oklch(0.94 0.01 255)` | `#E5E7EB` | 弱化背景 |
| `--muted-foreground` | `oklch(0.45 0.02 245)` | `#6B7280` | 弱化文字 |
| `--accent` | `oklch(0.9 0.03 200)` | `#DBEAFE` | 强调背景 |
| `--accent-foreground` | `oklch(0.15 0.03 255)` | `#1A1D23` | 强调文字 |
| **`--safe`** | `oklch(0.55 0.17 165)` | `#10B981` | 安全/正常状态 |
| **`--warn`** | `oklch(0.6 0.15 80)` | `#F59E0B` | 警告状态 |
| **`--danger`** | `oklch(0.55 0.2 25)` | `#EF4444` | 危险/严重告警 |
| `--destructive` | `oklch(0.55 0.2 25)` | `#EF4444` | 破坏性操作 (同 danger) |
| `--border` | `oklch(0 0 0 / 10%)` | `rgba(0,0,0,0.1)` | 边框 |
| `--input` | `oklch(0 0 0 / 12%)` | `rgba(0,0,0,0.12)` | 输入框边框 |
| `--ring` | `oklch(0.5 0.15 230)` | `#2563EB` | 聚焦环 |

#### 暗色主题 (`.dark`)

| Token | OKLCH 值 | HEX 近似 | 用途 |
|-------|---------|---------|------|
| `--background` | `oklch(0.16 0.02 255)` | `#1A1D24` | 页面背景 |
| `--foreground` | `oklch(0.96 0.01 240)` | `#F0F1F5` | 主文字 |
| `--card` | `oklch(0.21 0.022 255)` | `#262932` | 卡片背景 |
| `--card-foreground` | `oklch(0.96 0.01 240)` | `#F0F1F5` | 卡片文字 |
| `--panel` | `oklch(0.235 0.024 255)` | `#2C303A` | 面板背景 |
| `--panel-foreground` | `oklch(0.96 0.01 240)` | `#F0F1F5` | 面板文字 |
| `--primary` | `oklch(0.82 0.13 195)` | `#60A5FA` | 主色调 (亮蓝) |
| `--primary-foreground` | `oklch(0.18 0.03 240)` | `#1E293B` | 主色调上的文字 |
| **`--safe`** | `oklch(0.78 0.17 165)` | `#34D399` | 安全/正常状态 |
| **`--warn`** | `oklch(0.82 0.15 80)` | `#FBBF24` | 警告状态 |
| **`--danger`** | `oklch(0.66 0.2 25)` | `#F87171` | 危险/严重告警 |

### 3.2 图表颜色

| Token | OKLCH (浅色) | OKLCH (暗色) | 用途 |
|-------|-------------|-------------|------|
| `--chart-1` | `oklch(0.5 0.15 230)` | `oklch(0.82 0.13 195)` | 注意力分数 |
| `--chart-2` | `oklch(0.55 0.17 165)` | `oklch(0.78 0.17 165)` | 安全指标 |
| `--chart-3` | `oklch(0.6 0.15 80)` | `oklch(0.82 0.15 80)` | 警告统计 |
| `--chart-4` | `oklch(0.55 0.2 25)` | `oklch(0.66 0.2 25)` | 危险统计 |
| `--chart-5` | `oklch(0.55 0.1 260)` | `oklch(0.7 0.1 260)` | 疲劳趋势 |

### 3.3 颜色使用规则

- **safe**: 仅用于安全状态指示器和正常数据
- **warn**: 仅用于 warning 级别告警
- **danger**: 仅用于 danger/critical 级别告警 + 告警闪烁动画
- **primary**: 交互元素 (按钮/链接/选中态)
- **muted-foreground**: 辅助信息，不可用于重要状态

---

## 4. 间距系统

基于 Tailwind 默认间距刻度 (1 unit = 0.25rem = 4px)：

| Token | 值 | 用途 |
|-------|-----|------|
| `p-1` / `gap-1` | 4px | 图标与标签间距 |
| `p-2` / `gap-2` | 8px | 组件内部间距 |
| `p-3` / `gap-3` | 12px | 面板内边距 |
| `p-4` / `gap-4` | 16px | 卡片间距、面板 padding |
| `p-6` / `gap-6` | 24px | 区块间距 |
| `p-8` | 32px | 页边距 |

---

## 5. 圆角系统

| Token | 值 | 用途 |
|-------|-----|------|
| `--radius` (基础) | `1rem` (16px) | 所有圆角基准 |
| `rounded-sm` | `calc(var(--radius) - 4px)` = 12px | 小型组件 |
| `rounded-md` | `calc(var(--radius) - 2px)` = 14px | 标准组件 |
| `rounded-lg` | `var(--radius)` = 16px | 卡片/面板 |
| `rounded-xl` | `calc(var(--radius) + 4px)` = 20px | 大型面板 |
| `rounded-2xl` | `calc(var(--radius) + 8px)` = 24px | 模态框 |

---

## 6. 阴影

使用 Tailwind 内置阴影，暗色模式下减弱阴影强度：

| Token | 浅色 | 暗色 | 用途 |
|-------|------|------|------|
| `shadow-sm` | 轻微投影 | 无投影 | 卡片默认 |
| `shadow` | 标准投影 | 极弱投影 | 悬浮面板 |
| `shadow-lg` | 深投影 | 弱投影 | 模态框 |

---

## 7. 响应式断点

| 断点 | 最小宽度 | 目标设备 |
|------|---------|---------|
| `sm` | 640px | 手机横屏 |
| `md` | 768px | 平板竖屏 |
| `lg` | 1024px | 平板横屏 / 小型中控屏 |
| `xl` | 1280px | 标准中控屏 (目标) |
| `2xl` | 1536px | 大型中控屏 |

### 7.1 中控大屏布局 (≥1280px)

```
┌──────────┬──────────────────────────────────────┬──────────┐
│ AppSide  │                                      │ AiPanel  │
│ bar      │          MapArea (中央地图)           │ (AI对话) │
│ (导航)   │                                      │          │
│ 64px     │                                      │ 360px    │
├──────────┤                                      │          │
│ Safety   │                                      │          │
│ Panel    │                                      │          │
│ (告警)   │                                      │          │
├──────────┤                                      │          │
│ Stats    │                                      │          │
│ Panel    │                                      │          │
│ (统计)   │                                      │          │
└──────────┴──────────────────────────────────────┴──────────┘
│                      BottomBar (快捷操作)                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. 核心组件样式规范

### 8.1 安全告警面板 (SafetyPanel)

```
┌─────────────────────────────────┐
│ 🔴 安全告警                      │  ← text-sm font-semibold text-danger
│ ┌─────────────────────────────┐ │
│ │ ⚠️ 严重分心                   │ │  ← 告警卡片: bg-card rounded-lg
│ │ 检测到视线偏离路面 4.2s       │ │     border-l-4 border-danger
│ │ 2 分钟前                      │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ ✅ 状态良好                   │ │  ← border-l-4 border-safe
│ │ 驾驶员注意力保持稳定          │ │
│ │ 5 分钟前                      │ │
│ └─────────────────────────────┘ │
└─────────────────────────────────┘
```

规则:
- 告警级别 → 左边框颜色: `danger`→`border-danger`, `warning`→`border-warn`, `normal`→`border-safe`
- 告警卡片间距: `gap-2`
- 告警图标: Lucide `AlertTriangle` (danger), `AlertCircle` (warning), `CheckCircle` (safe)
- 红色闪烁动画: `animate-hmi-pulse` (仅 danger)

### 8.2 AI 对话面板 (AiPanel)

```
┌─────────────────────────────────┐
│ 💬 AI 助手                       │  ← text-sm font-semibold
│ ─────────────────────────────── │
│                                 │
│ ┌─────────────────────────────┐ │
│ │ 用户: 打开空调并播放轻音乐    │ │  ← text-right bg-accent rounded-lg
│ └─────────────────────────────┘ │
│                                 │
│ ┌─────────────────────────────┐ │
│ │ AI: 已为主驾开启空调至        │ │  ← bg-secondary rounded-lg
│ │ 22.5°C，开始播放轻音乐       │ │
│ └─────────────────────────────┘ │
│                                 │
│ ┌─────────────────────────────┐ │
│ │ 🔧 调用 control_ac           │ │  ← Agent 追踪链: bg-muted
│ │ ✓ 空调已开启 (280ms)          │ │     text-muted-foreground text-xs
│ └─────────────────────────────┘ │
│                                 │
│ ─────────────────────────────── │
│ [打开空调] [播放音乐] [导航回家] │  ← 快捷回复: text-xs rounded-full
│ ─────────────────────────────── │
│ [________________🎤________]    │  ← 输入框 + 语音按钮
└─────────────────────────────────┘
```

规则:
- 用户消息: 右对齐, `bg-accent`, `rounded-lg`, `ml-8`
- AI 消息: 左对齐, `bg-secondary`, `rounded-lg`, `mr-8`
- Agent 追踪链: 可折叠, `bg-muted`, monospace 字体, 显示耗时
- 快捷回复: `rounded-full`, `border`, `text-xs`, `px-3 py-1.5`
- 输入框: Element Plus `el-input` + 语音按钮 (Lucide `Mic`)

### 8.3 摄像头画面 + 注意力环 (AttentionRing)

```
┌──────────────────────────────┐
│ ┌──────────────────────────┐ │
│ │                          │ │
│ │      [摄像头实时画面]      │ │  ← 外层: rounded-xl overflow-hidden
│ │                          │ │
│ │   ◎ 注意力 88%           │ │  ← 叠加: AttentionRing 组件
│ │                          │ │     stroke 颜色 = safe(绿) / warn(黄) / danger(红)
│ └──────────────────────────┘ │
│ Gaze: center · Gesture: --   │  ← 底部 HUD 信息条
│ Fatigue: normal · FPS: 22    │
└──────────────────────────────┘
```

规则:
- 摄像头画面: `aspect-video`, `rounded-xl`, `bg-black`
- 注意力环: SVG 圆环, 颜色根据注意力分数渐变
  - ≥ 80: `--safe`
  - 50-79: `--warn`
  - < 50: `--danger`
- HUD 信息: `bg-black/60`, `text-white`, `text-xs`

### 8.4 空调控制 (ClimateControl)

```
┌─────────────────────────────────────┐
│ 🌡️ 空调控制                    ✕    │  ← 标题栏
│ ─────────────────────────────────── │
│                                     │
│         ┌───┐                       │
│         │ ↑ │ 温度                   │
│    ┌────┤24°├────┐                  │  ← 大号温度显示: text-3xl font-bold
│    │    │ C │    │                  │
│    │    └───┘    │                  │
│    │   ┌─────┐   │                  │
│    │ ← │ OFF │ → │ 风速              │  ← Element Plus el-slider
│    │   └─────┘   │                  │
│    └────────────┘                   │
│                                     │
│  [制冷] [制热] [自动] [送风]         │  ← 模式切换: el-button-group
│                                     │
│  风速: [1] [2] [3] [4] [5]          │  ← 风速选择
└─────────────────────────────────────┘
```

规则:
- 开关按钮: 拟物化大圆形按钮, `w-16 h-16 rounded-full`
- 开启态: `bg-primary text-primary-foreground`
- 关闭态: `bg-muted text-muted-foreground`
- 温度调节: ± 按钮 + 数字显示
- 模式按钮: Element Plus `el-radio-button`

### 8.5 地图区域 (MapArea)

```
┌──────────────────────────────────────┐
│ 🌤️ 多云 22°C  北京                   │  ← 天气叠加条
│ ──────────────────────────────────── │
│                                      │
│          [Leaflet 地图]               │  ← 全宽地图
│     📍 当前位置                       │     z-index 分层:
│     ─── 规划路线                      │       1. 地图瓦片
│     📍 目的地                         │       2. 路线折线
│                                      │       3. 标记点
│                                      │       4. 天气叠加
│                                      │
│ ──────────────────────────────────── │
│ 🚗 距离: 12.3km · ⏱️ 预计: 25min    │  ← 导航信息条
└──────────────────────────────────────┘
```

规则:
- 地图容器: `h-full w-full`, `z-0`
- 路线: Leaflet polyline, `color: var(--primary)`, `weight: 5`
- 标记: Leaflet L.divIcon 自定义 HTML 标记
- 天气条: 半透明背景 `bg-card/80 backdrop-blur-sm`
- Leaflet 修复: `.leaflet-tile { max-width: none !important; }` (防止 Tailwind preflight 冲突)

---

## 9. 动画规范

### 9.1 动画定义

```css
/* 呼吸动画 — 安全状态指示器 */
@keyframes hmi-breathe {
  0%, 100% { opacity: 0.55; transform: scale(1); }
  50%      { opacity: 1;    transform: scale(1.06); }
}
.animate-hmi-breathe { animation: hmi-breathe 2.4s ease-in-out infinite; }

/* 告警脉冲 — danger 级别 */
@keyframes hmi-pulse-ring {
  0%   { box-shadow: 0 0 0 0 color-mix(in oklch, var(--danger) 55%, transparent); }
  70%  { box-shadow: 0 0 0 12px color-mix(in oklch, var(--danger) 0%, transparent); }
  100% { box-shadow: 0 0 0 0 color-mix(in oklch, var(--danger) 0%, transparent); }
}
.animate-hmi-pulse { animation: hmi-pulse-ring 1.8s ease-out infinite; }
```

### 9.2 动画使用规则

| 动画 | 触发条件 | 持续时间 | 循环 |
|------|---------|---------|------|
| `hmi-breathe` | 系统正常运行 | 2.4s | 无限 (状态指示器) |
| `hmi-pulse` | danger 级别告警 | 1.8s | 无限 (直到告警解除) |
| 边框闪烁 | 红色边框 (告警条) | 250ms (4Hz) | 无限 (直到告警解除) |
| 过渡 | 颜色/背景切换 | 150-200ms | 一次性 |
| 淡入 | 面板/卡片出现 | 200ms | 一次性 |

### 9.3 禁止的动画

- ❌ 弹跳/弹跳文本 (分散驾驶注意力)
- ❌ 持续旋转/加载动画 (仅在初始加载时使用)
- ❌ 视差滚动
- ❌ 超过 500ms 的过渡动画

---

## 10. 组件模式

### 10.1 Vue 单文件组件结构

```vue
<script setup lang="ts">
// 1. 导入
// 2. Props / Emits 定义
// 3. Composables
// 4. 响应式状态
// 5. 计算属性
// 6. 方法
// 7. 生命周期钩子
</script>

<template>
  <!-- 模板 -->
</template>

<style scoped>
/* 仅组件特有样式，全局样式放 globals.css */
</style>
```

### 10.2 命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| Vue 组件 | PascalCase | `SafetyPanel.vue`, `AiPanel.vue` |
| Composable | `use` + camelCase | `useTelemetry.ts`, `useAgentWS.ts` |
| 类型/接口 | PascalCase | `Telemetry`, `AgentTraceStep` |
| 常量 | UPPER_SNAKE_CASE | `ENDPOINTS`, `gestureCommands` |
| CSS 类 | Tailwind 原子类 或 kebab-case | `animate-hmi-breathe` |
| Props | camelCase | `safetyLevel`, `isActive` |
| Events | kebab-case | `@update:model-value` |

### 10.3 状态管理

不使用 Vuex/Pinia。状态通过 composables 管理：
- `useTelemetry.ts`: 摄像头轮询 + 实时驾驶状态 (ref)
- `useAgentWS.ts`: WebSocket 连接 + Agent 消息流 (ref)
- 组件间通信: props down, events up + WebSocket 广播

### 10.4 API 调用模式

```typescript
// lib/edgeguard.ts — 所有端点常量和类型定义集中管理
import { ENDPOINTS } from '@/lib/edgeguard'

// composable 中调用
const res = await fetch(ENDPOINTS.cameraFrame)
// WebSocket
const ws = new WebSocket(`ws://${host}${ENDPOINTS.agentPanelWS}`)
```

---

## 11. 图标

使用 **Lucide Vue** (`@lucide/vue`)，统一图标库：

| 图标 | 用途 |
|------|------|
| `AlertTriangle` | danger 级告警 |
| `AlertCircle` | warning 级告警 |
| `CheckCircle` | 正常状态 |
| `Camera` | 摄像头 |
| `Mic` / `MicOff` | 语音输入 |
| `Thermometer` | 温度/空调 |
| `Music` | 音乐 |
| `MapPin` | 位置/导航 |
| `MessageSquare` | AI 对话 |
| `BarChart3` | 统计 |
| `Settings` | 设置 |
| `ChevronLeft` / `ChevronRight` | 导航箭头 |

---

## 12. 主题切换

```css
/* 默认暗色主题 (车载场景) */
:root { color-scheme: dark; }

/* 浅色主题切换 — 在 <html> 上切换 .dark 类 */
.dark { color-scheme: dark; }
/* 移除 .dark 类即为浅色模式 */

/* 系统主题跟随 */
@media (prefers-color-scheme: light) {
  :root:not(.dark) { /* 浅色变量 */ }
}
```

前端通过 Tailwind `dark:` 变体实现主题切换：
```html
<div class="bg-background text-foreground dark:bg-background dark:text-foreground">
```

---

## 13. 性能约束

| 约束 | 值 | 说明 |
|------|-----|------|
| 摄像头轮询间隔 | 200ms (5 FPS) | `useTelemetry` 中的 setInterval |
| 帧推送间隔 | 每 6 帧 (~200ms) | app.py → POST /api/analyze |
| WebSocket 心跳 | 30s | WSManager heartbeat |
| 环境广播间隔 | 30s | lifespan 周期性任务 |
| 首屏 JS Bundle | < 500 KB (gzip) | Vite code splitting |
| 图片格式 | JPEG (quality 70) | 摄像头帧压缩 |
| ECharts 实例 | ≤ 3 个 | Dashboard 面板限制 |

---

## 14. 浏览器兼容性

| 浏览器 | 最低版本 | 备注 |
|--------|---------|------|
| Chrome | 90+ | 主要开发目标 |
| Edge | 90+ | Chromium 内核，完全兼容 |
| Safari | 15+ | WebRTC/getUserMedia 需 HTTPS |
| Firefox | 90+ | 部分 CSS OKLCH 可能回退 |
