# VNPy AI Trader Development Plan

# VNPy AI交易系统开发计划

## Project Overview / 项目概述

An AI-enhanced A-share automated trading system built on vnpy framework, using DeepSeek LLM for natural language strategy parsing and real-time market analysis.

基于vnpy框架的AI增强型A股自动化交易系统，使用DeepSeek LLM实现自然语言策略解析和实时市场分析。

---

## Requirements / 需求

| Item | Choice |
|------|--------|
| Strategy Mode | Hybrid - Rules parsed once, fuzzy judgment via LLM in real-time |
| Trading Products | A-shares (SSE/SZSE) |
| Validation | Backtest → Paper → Live (progressive) |
| Interface | Simple Web UI (FastAPI + Frontend) |
| Cost | Free data sources and trading interfaces |

---

## Architecture / 架构设计

```
User Natural Language Strategy
         ↓
[DeepSeek One-time Parsing] → JSON Config
         ↓
┌─────────────────────────────┐
│     AIAlphaStrategy         │
│  ├─ on_bars()               │
│  │   ├─ Rule Signals        │ ← RuleEngine (JSON rules)
│  │   ├─ AI Signals          │ ← NewsAnalyzer (optional)
│  │   └─ Merged Signals      │
│  └─ execute_trading()       │
└─────────────────────────────┘
         ↓
    QMT Gateway Execution
```

---

## Development Phases / 开发阶段

### Phase 1: Foundation ✅
- [x] Project structure
- [x] Requirements.txt
- [x] Configuration files
- [x] Logging utilities

### Phase 2: AI Core ✅
- [x] DeepSeek client wrapper
- [x] Prompt manager
- [x] Strategy parser (NL → JSON)
- [x] News analyzer

### Phase 3: Strategy Engine ✅
- [x] Rule engine
- [x] Risk manager
- [x] AIAlphaStrategy class

### Phase 4: Data & Integration ✅
- [x] AData datafeed adapter
- [x] Backtest script
- [x] Data preparation script

### Phase 5: Web Interface ✅
- [x] FastAPI backend
- [x] WebSocket real-time push
- [x] Simple frontend

### Phase 6: Paper Trading ✅
- [x] QMT Gateway adapter
- [x] Paper trading account
- [x] Paper trading tests

### Phase 7: Live Preparation 🔲
- [ ] Live gateway
- [ ] Security audit
- [ ] Monitoring & alerts
- [ ] Unit tests

---

## Technology Stack / 技术栈

| Component | Technology |
|-----------|------------|
| Core Framework | vnpy 4.3.0 |
| AI/LLM | DeepSeek API |
| Data Source | AData (free) |
| Trading Gateway | QMT |
| Web Backend | FastAPI |
| Data Processing | Polars |

---

## Quick Start / 快速开始

### 1. Install Dependencies
```bash
cd vnpy_ai_trader
pip install -r requirements.txt
```

### 2. Configure API Key
```bash
export DEEPSEEK_API_KEY="your_api_key"
```

### 3. Run Backtest with Natural Language Strategy
```bash
python scripts/run_backtest.py \
    --strategy "沪深300成分股，RSI低于30时买入，盈利10%或亏损5%卖出" \
    --symbols "000001,000002,000063" \
    --start "2023-01-01" \
    --end "2024-01-01"
```

### 4. Run Backtest with JSON Config
```bash
python scripts/run_backtest.py \
    --config "path/to/strategy.json" \
    --symbols "000001,000002" \
    --start "2023-01-01" \
    --end "2024-01-01"
```

---

## Risks & Notes / 风险与注意事项

1. **API Cost**: Control DeepSeek API call frequency
2. **Data Quality**: AData free data may have delays
3. **Trading Interface**: QMT free version has limitations
4. **Risk Control**: Must pass paper trading before live
