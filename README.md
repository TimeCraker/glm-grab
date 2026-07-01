<div align="center">

<img src="https://raw.githubusercontent.com/TimeCraker/glm-grab/main/.github/banner.svg" alt="GLM Grab Banner" width="100%"/>

# ⚡ GLM Coding 抢购脚本

**智谱 GLM Coding 套餐（Lite / Pro / Max）补货时自动抢 — 设好时间就睡**

[![CI](https://github.com/TimeCraker/glm-grab/actions/workflows/ci.yml/badge.svg)](https://github.com/TimeCraker/glm-grab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-≥3.12-3776ab?logo=python&logoColor=white)](https://www.python.org)
[![Playwright](https://img.shields.io/badge/Playwright-async-2e8555?logo=playwright&logoColor=white)](https://playwright.dev)

> **v2 优化（2026-06-18 实战后）**：4 tab 并发 · 09:58 自动进入高频模式 · 400ms 刷新 · 命中即停

</div>

---

## 📑 目录

- [⚡ 核心特性](#-核心特性)
- [🕐 抢购时序图](#-抢购时序图)
- [🚀 快速开始](#-快速开始)
- [⚙️ 配置项](#-配置项)
- [🧠 v2 优化点](#-v2-优化点)
- [⚠️ 风险与免责](#-风险与免责)
- [📜 License](#-license)

---

## ⚡ 核心特性

| 特性 | 说明 | 价值 |
|------|------|------|
| 🕐 **定时自动启动** | 提前 2 分钟开 tab，无需守在电脑前 | 设好就睡 |
| 🔥 **多 tab 并发** | 默认 4 个 tab 同时抢，命中率 4× | 提高成功概率 |
| ⚡ **高频扫描** | 400ms 刷新 + 100ms 按钮扫描 | 抢在 0.5 秒内 |
| 🎯 **智能识别** | 16 种按钮文字（"立即开通"/"抢购"/"补货"…） | 抗 UI 改版 |
| 🛑 **命中即停** | 一个 tab 抢到 → 其他 tab 立即停 | 避免重复下单 |
| 🪟 **Windows 友好** | emoji / 特殊字符不乱码（stdout 重配 utf-8） | 双击 .bat 就能跑 |

---

## 🕐 抢购时序图

<div align="center">

<img src="https://raw.githubusercontent.com/TimeCraker/glm-grab/main/.github/architecture.svg" alt="GLM Grab Timeline" width="100%"/>

</div>

**5 个阶段**：

| 阶段 | 时间 | 行为 |
|------|------|------|
| 💤 IDLE | `< 09:56` | 监听 GO.txt 触发信号 |
| ⏰ WARM-UP | `09:56 ~ 09:58` | 打开 4 个 tab · 加载页面 |
| 🔥 HIGH-FREQ | `09:58 ~ 10:00` | 400ms 循环 · 扫描按钮 |
| ⚡ FIRE | `10:00:00` | 命中 → 4 tab 并发点击 |
| ✅ DONE | `10:00:00.x` | 订单确认页 + 提醒 |

---

## 🚀 快速开始

### 1. 安装 Playwright

```bash
pip install playwright
playwright install chromium
```

### 2. 编辑 `grab.py` 顶部的配置

```python
PLAN = "Pro"                    # 套餐: "Lite" / "Pro" / "Max"
RESTOCK_TIME = "10:00:00"       # 补货时间（24h 制）
AUTO_START_MIN_BEFORE = 2       # 提前几分钟开始刷（推荐 1-3）
TAB_COUNT = 4                   # 并发 tab 数（推荐 3-5）
```

### 3. 登录 + 启动

```bash
# 第一步：先打开浏览器手动登录一次（保存 cookie）
# 第二步：开始抢购
python grab.py
```

启动后脚本会：
- 现在时间 → 等待到 `RESTOCK_TIME - AUTO_START_MIN_BEFORE`
- 自动开 4 个 tab · 进入高频模式
- 命中按钮 → 立即点击 → 通知你

### 4. 远程触发（可选）

在你的 `grab.py` 所在目录新建空文件 `GO.txt` → 脚本立即进入高频模式（不等定时）。

适合：**先在手机/另一台机器 touch 文件，立刻开始抢**。

---

## ⚙️ 配置项

| 变量 | 默认 | 范围 | 作用 |
|------|------|------|------|
| `PLAN` | `"Pro"` | `Lite`/`Pro`/`Max` | 套餐等级（仅用于日志标识） |
| `RESTOCK_TIME` | `"10:00:00"` | `HH:MM:SS` | 补货时间（24h） |
| `AUTO_START_MIN_BEFORE` | `2` | `1-3` | 提前几分钟开 tab |
| `TAB_COUNT` | `4` | `1-5` | 并发 tab 数（>5 易风控） |
| `REFRESH_INTERVAL` | `0.4` | `0.2-1.0` | 页面刷新间隔（秒） |
| `SCAN_INTERVAL` | `0.1` | `0.05-0.3` | 按钮扫描间隔（秒） |
| `TRIGGER_FILE` | `"GO.txt"` | path | 远程触发文件名 |

**调优建议**：

- 网络差 → `TAB_COUNT = 3` · `REFRESH_INTERVAL = 0.6`
- 风控严 → `TAB_COUNT = 2` · 错峰 0.5-1.5s 随机
- 抢救市（如首发） → `TAB_COUNT = 5` · `REFRESH_INTERVAL = 0.3`

---

## 🧠 v2 优化点

| 优化 | v1 | v2 | 收益 |
|------|-----|-----|------|
| 并发 tab | 1 | 4 | 命中率 ×4 |
| 刷新间隔 | 800ms | 400ms | 提早 400ms 命中 |
| 自动启动 | 手动 | 提前 2 分钟定时 | 解放双手 |
| 按钮识别 | 2 种文字 | 16 种文字 | 抗 UI 改版 |
| 命中策略 | 4 tab 都点 | 命中即停 | 避免重复订单 |
| 智能判断 | 无 | "今日已抢 vs 等下次补货" | 减少无效刷新 |

---

## ⚠️ 风险与免责

- **本脚本仅供学习研究使用**，请遵守 [智谱 GLM Coding 用户协议](https://www.zhipuai.cn/)
- 高频请求可能触发智谱风控（IP / 账号限流），后果自负
- 商品售罄/库存变动/页面改版等情况脚本**无法保证 100% 成功**
- 商业使用请购买官方 API（[智谱开放平台](https://open.bigmodel.cn/)）

---

## 📜 License

MIT License — 详见 [LICENSE](LICENSE)。

<div align="center">

**⚡ 设好时间就睡，剩下交给脚本 ⚡**

</div>
