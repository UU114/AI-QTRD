# VNPy AI Trader Architecture Document

# VNPy AI交易系统架构文档

## Directory Structure / 目录结构

```
vnpy_ai_trader/
├── config/                         # Configuration files
│   ├── settings.yaml               # Global settings
│   ├── strategy_schema.json        # Strategy JSON Schema
│   └── deepseek_prompts.yaml       # LLM prompt templates
│
├── src/                            # Source code
│   ├── __init__.py
│   │
│   ├── ai_core/                    # AI Core Module
│   │   ├── __init__.py
│   │   ├── deepseek_client.py      # DeepSeek API client
│   │   ├── prompt_manager.py       # Prompt template management
│   │   ├── strategy_parser.py      # NL to JSON parser
│   │   └── news_analyzer.py        # Real-time news analyzer
│   │
│   ├── strategy/                   # Strategy Module
│   │   ├── __init__.py
│   │   ├── ai_alpha_strategy.py    # Main AI strategy class
│   │   ├── rule_engine.py          # JSON rule executor
│   │   └── risk_manager.py         # Risk management
│   │
│   ├── datafeed/                   # Data Source Module
│   │   ├── __init__.py
│   │   └── adata_datafeed.py       # AData adapter
│   │
│   ├── gateway/                    # Trading Gateway Module
│   │   ├── __init__.py
│   │   ├── qmt_gateway.py          # QMT gateway (TODO)
│   │   └── paper_account.py        # Paper trading (TODO)
│   │
│   ├── web/                        # Web Interface Module
│   │   ├── __init__.py
│   │   ├── app.py                  # FastAPI app (TODO)
│   │   └── routers/                # API routes (TODO)
│   │
│   └── utils/                      # Utilities
│       ├── __init__.py
│       └── logger.py               # Logging utilities
│
├── scripts/                        # Runner scripts
│   ├── run_backtest.py             # Backtesting script
│   ├── run_paper_trading.py        # Paper trading (TODO)
│   └── run_web_server.py           # Web server (TODO)
│
├── tests/                          # Test suite
│
├── doc/                            # Documentation
│   ├── plan.md                     # Development plan
│   ├── structure.md                # This file
│   └── process.md                  # Development progress
│
└── requirements.txt                # Python dependencies
```

---

## Core Components / 核心组件

### 1. AI Core Module (`src/ai_core/`)

#### DeepSeekClient
- Wraps OpenAI-compatible API for DeepSeek
- Handles retries and error handling
- Supports JSON mode for structured output

#### StrategyParser
- Converts natural language to JSON configuration
- Validates against strategy_schema.json
- Uses configurable prompt templates

#### NewsAnalyzer
- Real-time news sentiment analysis
- Caches results to reduce API calls
- Returns structured sentiment scores

### 2. Strategy Module (`src/strategy/`)

#### AIAlphaStrategy
- Extends vnpy AlphaStrategy base class
- Combines rule-based and AI signals
- Implements on_bars() trading logic

#### RuleEngine
- Parses and evaluates JSON rule conditions
- Supports technical indicators (RSI, MA, etc.)
- Handles entry and exit conditions

#### RiskManager
- Position sizing calculations
- Drawdown and daily loss limits
- Order validation

### 3. Datafeed Module (`src/datafeed/`)

#### AdataDatafeed
- Implements vnpy BaseDatafeed interface
- Uses AData library for free A-share data
- Includes local data caching

### 4. Gateway Module (`src/gateway/`) [TODO]

#### QmtGateway
- Will implement vnpy BaseGateway interface
- Support for QMT/xtquant SDK
- Both simulation and live modes

---

## Data Flow / 数据流

```
┌─────────────────────────────────────────────────────────────┐
│                    Strategy Configuration                    │
│  User Input: "RSI低于30时买入，盈利10%卖出"                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    StrategyParser                            │
│  DeepSeek API → JSON Config                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    AIAlphaStrategy                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ RuleEngine   │  │ NewsAnalyzer │  │ RiskManager  │       │
│  │ (条件评估)   │  │ (情感分析)   │  │ (风险控制)   │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│            │               │               │                 │
│            └───────────────┴───────────────┘                │
│                         │                                    │
│                    Trading Signals                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Gateway (QMT/Paper)                       │
│  Order Execution → Exchange                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Strategy Configuration Schema / 策略配置Schema

```json
{
  "strategy_name": "string",
  "description": "string",
  "universe": {
    "type": "index_component | custom_list | filter_based",
    "index": "000300.SSE",
    "symbols": ["000001.SZSE", "..."]
  },
  "entry_rules": {
    "conditions": [
      {
        "indicator": "RSI",
        "params": {"period": 14},
        "operator": "<",
        "value": 30
      }
    ],
    "ai_enhanced": true,
    "ai_factors": ["news_sentiment"]
  },
  "exit_rules": {
    "take_profit": 0.10,
    "stop_loss": 0.05,
    "holding_days": 20
  },
  "risk_control": {
    "max_positions": 30,
    "position_size": 0.03,
    "max_drawdown": 0.15
  }
}
```

---

## Key vnpy Integration Points / vnpy集成点

| vnpy Class | Our Implementation |
|------------|-------------------|
| `AlphaStrategy` | `AIAlphaStrategy` extends it |
| `BaseDatafeed` | `AdataDatafeed` implements it |
| `BaseGateway` | `QmtGateway` will implement it |
| `BacktestingEngine` | Used in `run_backtest.py` |
| `AlphaLab` | Used for data management |

---

## Dependencies / 依赖关系

```
vnpy (4.3.0)
├── Polars (data processing)
├── PySide6 (GUI, optional)
└── Other core dependencies

vnpy_ai_trader
├── openai (DeepSeek API)
├── adata (free A-share data)
├── fastapi (web backend)
├── loguru (logging)
├── jsonschema (validation)
└── pyyaml (configuration)
```
