# Nexus Quant - 实盘量化交易终端

Nexus Quant 是一款基于前后端分离架构构建的高性能、实时量化交易终端。它结合了 FastAPI 的异步能力与原生的前端交互，专门为 Binance (币安) 统一账户 (Portfolio Margin) 与 USDT-M 标准合约账户设计。

![Nexus Quant Dashboard](https://img.shields.io/badge/Status-Active-brightgreen)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Framework-teal)

## 核心功能 🌟

- **自动化实盘引擎**: 内置异步 `LiveEngine`，每 30 秒轮询 Binance 实时行情，计算技术指标 (如 ADX、布林带等)，自动触发买卖信号。
- **WebSocket 实时通信**: 毫秒级的行情分析与交易日志推送，让前端仪表盘的雷达面板时刻保持最新。
- **强大的订单管理系统**: 支持币安 U本位合约的市价单、限价单、一键撤销所有挂单、以及**紧急平仓** (Panic Close) 功能。
- **实时账户快照**: 动态获取并展示用户的保证金比例、总权益、可用余额与实时未实现盈亏。
- **Dry-Run 模式保护**: 默认开启模拟运行模式，即使信号触发也不会执行真实下单，全面保护您的资金安全。

## 技术栈 🛠️

*   **后端**: Python 3.14+, FastAPI, Uvicorn, Pandas, CCXT (用于回测与数据抓取), Websockets
*   **前端**: HTML5, Vanilla JavaScript, CSS3 (原生玻璃态与极光风格 UI), FontAwesome
*   **通信协议**: RESTful API + WebSocket

## 快速开始 🚀

### 1. 环境准备
确保您的计算机已安装 Python 3.9 或更高版本。

```bash
# 克隆仓库
git clone https://github.com/yourusername/quant_dashboard.git
cd quant_dashboard

# 安装依赖
pip install -r requirements.txt
```

*(如果 `requirements.txt` 不存在，请手动安装以下核心库: `fastapi`, `uvicorn`, `requests`, `pandas`, `ccxt`, `websockets`)*

### 2. 启动服务
在项目根目录运行以下命令以启动后端服务器：
```bash
python server.py
```

服务器将在 `http://127.0.0.1:8000` 启动。

### 3. 访问仪表盘
打开浏览器并访问 `http://127.0.0.1:8000`。
在左侧菜单栏中点击 **“API与账户”**，输入您的 Binance API Key 和 Secret Key，随后点击 **“刷新快照”** 即可同步您的资金与持仓数据。

## 目录结构 📂

```text
quant_dashboard/
├── server.py                 # FastAPI 后端主入口，定义了所有 API 与 WebSocket 路由
├── core/
│   ├── account_info.py       # 币安账户信息获取、持仓查询
│   ├── order_manager.py      # 订单执行模块（开多、平空、设置杠杆等）
│   ├── live_engine.py        # 核心实盘交易引擎与策略循环
│   └── backtester.py         # 历史数据获取与技术指标计算组件
├── frontend/                 # 前端静态文件目录
│   ├── index.html            # 主控面板 UI 界面
│   ├── app.js                # 前端交互逻辑与 WebSocket 客户端
│   └── index.css             # 样式表，包含了赛博朋克极光风格设计
└── .gitignore                # Git 忽略文件
```

## 安全声明 ⚠️

1.  **妥善保管 API Key**: 请不要将您的 `API_KEY` 和 `SECRET_KEY` 提交到任何公开的代码仓库中。建议将其实际保存在环境变量中。
2.  **交易风险提示**: 加密货币合约交易具有极高的风险，可能导致您的全部本金损失。本系统提供的量化策略及相关代码仅供学习与技术交流，**不构成任何投资建议**。
3.  **实盘开启方法**: 要开启真正的自动化实盘下单，请在 `core/live_engine.py` 中将 `self.dry_run = True` 修改为 `False`。在此之前，请务必经过充分的模拟测试。

## 许可证 📄
MIT License
