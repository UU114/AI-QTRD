# VNPy AI Trader

基于VNPy框架的AI增强型A股自动化交易系统

An AI-enhanced A-share automated trading system built on VNPy framework

## Features / 功能特点

- **自然语言策略** - 使用自然语言描述交易策略，DeepSeek自动解析为可执行配置
- **混合交易模式** - 规则策略一次性解析，模糊判断（新闻解读等）实时调用LLM
- **免费数据源** - 使用AData开源库获取免费A股历史数据
- **风险管理** - 内置持仓限制、止盈止损、回撤控制
- **渐进式验证** - 支持回测→模拟→实盘的渐进式策略验证

## Quick Start / 快速开始

### 1. Install Dependencies / 安装依赖

```bash
cd vnpy_ai_trader
pip install -r requirements.txt
pip install adata  # Free A-share data library
```

### 2. Configure API Key / 配置API密钥

```bash
# Windows
set DEEPSEEK_API_KEY=your_api_key

# Linux/Mac
export DEEPSEEK_API_KEY=your_api_key
```

### 3. Run Backtest / 运行回测

使用自然语言策略：
```bash
python scripts/run_backtest.py \
    --strategy "沪深300成分股，RSI低于30时买入，盈利10%或亏损5%卖出" \
    --symbols "000001,000002,000063,000333,000651" \
    --start "2023-01-01" \
    --end "2024-01-01" \
    --capital 1000000
```

使用JSON配置文件：
```bash
python scripts/run_backtest.py \
    --config "path/to/strategy.json" \
    --symbols "000001,000002" \
    --start "2023-01-01" \
    --end "2024-01-01"
```

### 4. Run Paper Trading / 运行模拟交易

使用历史数据回放模式：
```bash
python scripts/run_paper_trading.py \
    --strategy "RSI低于30买入，盈利10%或亏损5%卖出" \
    --symbols "000001,000002" \
    --replay \
    --start "2024-01-01" \
    --end "2024-03-01" \
    --speed 10
```

使用实时模拟模式（演示用）：
```bash
python scripts/run_paper_trading.py \
    --strategy "均线突破策略" \
    --symbols "000001" \
    --live \
    --duration 1
```

### 5. Run Web Interface / 运行Web界面

启动Web服务器：
```bash
python scripts/run_web_server.py
```

自定义主机和端口：
```bash
python scripts/run_web_server.py --host 0.0.0.0 --port 8080
```

开发模式（自动重载）：
```bash
python scripts/run_web_server.py --reload
```

访问Web界面：http://localhost:8000
API文档：http://localhost:8000/docs

## Project Structure / 项目结构

```
vnpy_ai_trader/
├── config/                 # 配置文件
│   ├── settings.yaml       # 全局配置
│   ├── strategy_schema.json # 策略JSON Schema
│   └── deepseek_prompts.yaml # LLM提示词模板
├── src/
│   ├── ai_core/            # AI核心模块
│   │   ├── deepseek_client.py
│   │   ├── strategy_parser.py
│   │   └── news_analyzer.py
│   ├── strategy/           # 策略模块
│   │   ├── ai_alpha_strategy.py
│   │   ├── rule_engine.py
│   │   └── risk_manager.py
│   ├── datafeed/           # 数据源模块
│   │   └── adata_datafeed.py
│   ├── gateway/            # 交易网关模块
│   │   ├── qmt_gateway.py      # QMT交易网关
│   │   └── paper_account.py    # 模拟交易账户
│   └── web/                # Web界面模块
│       ├── app.py              # FastAPI应用
│       ├── websocket_manager.py # WebSocket管理
│       ├── trading_engine.py   # 交易引擎
│       ├── routers/            # API路由
│       └── static/             # 前端静态文件
├── scripts/                # 运行脚本
│   ├── run_backtest.py         # 回测脚本
│   ├── run_paper_trading.py    # 模拟交易脚本
│   └── run_web_server.py       # Web服务器脚本
└── doc/                    # 文档
    ├── plan.md
    ├── structure.md
    └── process.md
```

## Strategy Configuration / 策略配置

自然语言策略会被解析为以下JSON格式：

```json
{
  "strategy_name": "rsi_oversold_strategy",
  "entry_rules": {
    "conditions": [
      {"indicator": "RSI", "params": {"period": 14}, "operator": "<", "value": 30}
    ],
    "ai_enhanced": false
  },
  "exit_rules": {
    "take_profit": 0.10,
    "stop_loss": 0.05,
    "holding_days": 20
  },
  "risk_control": {
    "max_positions": 30,
    "position_size": 0.03
  }
}
```

## Requirements / 依赖要求

- Python 3.10+
- vnpy 4.0+
- DeepSeek API Key

## Development Status / 开发状态

- [x] AI Core (DeepSeek integration)
- [x] Strategy Parser (NL to JSON)
- [x] Rule Engine
- [x] Risk Manager
- [x] AData Datafeed
- [x] Backtesting Script
- [x] QMT Gateway
- [x] Paper Trading Account
- [x] Paper Trading Runner
- [x] Web Interface (FastAPI + WebSocket)
- [x] Frontend UI
- [ ] Live Trading

## License / 许可证

MIT License
