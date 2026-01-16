# AI-QTRD

## AI-Powered Quantitative Trading & Research Development
## AI驱动的量化交易与研究开发平台

<p align="center">
    <img src ="https://img.shields.io/badge/version-1.0.0--alpha-blueviolet.svg"/>
    <img src ="https://img.shields.io/badge/platform-windows|linux|macos-yellow.svg"/>
    <img src ="https://img.shields.io/badge/python-3.10|3.11|3.12|3.13-blue.svg" />
    <img src ="https://img.shields.io/github/license/UU114/AI-QTRD.svg?color=orange"/>
</p>

**AI-QTRD** is an advanced quantitative trading platform that combines **VeighNa framework** with cutting-edge **LLM technologies** (DeepSeek) to enable natural language-driven strategy development and AI-enhanced trading decisions.

**AI-QTRD** 是一个先进的量化交易平台，结合了 **VeighNa框架** 与前沿的 **大语言模型技术**（DeepSeek），实现自然语言驱动的策略开发和AI增强的交易决策。

---

## 🚀 Core Features | 核心特性

### 1. **AI-Enhanced Trading** | AI增强交易

- **Natural Language Strategy** | 自然语言策略编写
  - Describe trading strategies in plain language | 使用自然语言描述交易策略
  - DeepSeek LLM auto-converts to executable code | DeepSeek自动转换为可执行代码

- **Hybrid Decision System** | 混合决策系统
  - Rule-based signals for deterministic logic | 规则信号处理确定性逻辑
  - Real-time LLM analysis for fuzzy judgments | 实时LLM分析处理模糊判断

- **News & Sentiment Analysis** | 新闻与情绪分析
  - AI-powered market news interpretation | AI驱动的市场新闻解读
  - Real-time sentiment scoring | 实时情绪评分

### 2. **Machine Learning Alpha** | 机器学习Alpha

Built on VeighNa 4.0's **vnpy.alpha** module for professional ML-based quantitative research:

基于VeighNa 4.0的 **vnpy.alpha** 模块，提供专业的机器学习量化研究能力：

- **Factor Engineering** | 因子工程
  - Polars-based high-performance feature computation | 基于Polars的高性能特征计算
  - Alpha101, Alpha158 factor sets | Alpha101、Alpha158因子集

- **ML Models** | 机器学习模型
  - Lasso, LightGBM, MLP neural networks | Lasso、LightGBM、MLP神经网络
  - Unified API for model training and backtesting | 统一的模型训练和回测API

- **Complete Workflow** | 完整工作流
  - Data management → Feature engineering → Model training → Signal generation → Backtesting
  - 数据管理 → 特征工程 → 模型训练 → 信号生成 → 策略回测

### 3. **Event-Driven Architecture** | 事件驱动架构

- **MainEngine** orchestrates gateways, apps, and strategies | MainEngine协调网关、应用和策略
- **EventEngine** enables asynchronous component communication | EventEngine实现异步组件通信
- High-performance tick/bar data processing | 高性能tick/bar数据处理

### 4. **Multi-Market Support** | 多市场支持

#### Domestic Markets | 国内市场
- **Futures & Options** | 期货期权: CTP, Mini CTP, SOPT, UFT, Femas, Esunny
- **A-Share** | A股: XTP, TORA, OST, EMT
- **Gold TD** | 黄金TD: KSGold, SGIT

#### International Markets | 海外市场
- **Interactive Brokers**: Global stocks, futures, options | 全球股票、期货、期权
- **Overseas Futures** | 海外期货: TAP, Direct Access

### 5. **Comprehensive Trading Apps** | 完善的交易应用

- **CTA Strategy** | CTA策略: High-frequency CTA with fine-grained order control | 支持高频CTA策略
- **Portfolio Strategy** | 组合策略: Multi-asset Alpha strategies | 多资产Alpha策略
- **Spread Trading** | 价差交易: Custom spreads with algo execution | 自定义价差与算法执行
- **Option Master** | 期权大师: Pricing models, Greeks tracking | 期权定价、希腊值跟踪
- **Algo Trading** | 算法交易: TWAP, Iceberg, BestLimit algorithms | TWAP、冰山、最优限价算法
- **Risk Manager** | 风险管理: Flow control, position limits | 交易流控、持仓限制

---

## 📦 Installation | 安装

### Prerequisites | 环境要求

- **Python**: 3.10+ (3.13 recommended) | Python 3.10以上（推荐3.13）
- **OS**: Windows 11+ / Ubuntu 22.04+ / macOS | Windows 11以上 / Ubuntu 22.04以上 / macOS
- **DeepSeek API Key** (for AI features) | DeepSeek API密钥（用于AI功能）

### Quick Install | 快速安装

```bash
# Windows
install.bat

# Ubuntu / macOS
bash install.sh

# Development mode | 开发模式
pip install -e .

# With ML features | 安装ML功能依赖
pip install -e ".[alpha]"
```

---

## 🎯 Quick Start | 快速开始

### 1. AI-Enhanced Trading | AI增强交易

#### Natural Language Strategy Backtesting | 自然语言策略回测

```bash
cd vnpy_ai_trader

# Set DeepSeek API key | 配置DeepSeek密钥
export DEEPSEEK_API_KEY="your_api_key"

# Run backtest with natural language | 使用自然语言运行回测
python scripts/run_backtest.py \
    --strategy "沪深300成分股，RSI低于30时买入，盈利10%或亏损5%卖出" \
    --symbols "000001,000002,000063" \
    --start "2023-01-01" \
    --end "2024-01-01" \
    --capital 1000000
```

#### Web-Based Trading Interface | Web交易界面

```bash
cd vnpy_ai_trader

# Start web server | 启动Web服务器
python scripts/run_web_server.py

# Access UI | 访问界面
# http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### 2. ML Alpha Research | ML Alpha研究

```python
from vnpy.alpha.lab import AlphaLab
from vnpy.alpha.dataset.datasets.alpha_158 import Alpha158Dataset
from vnpy.alpha.model.models.lgb_model import LGBModel

# Initialize research lab | 初始化研究环境
lab = AlphaLab("my_alpha_project")

# Load Alpha158 features | 加载Alpha158因子
dataset = Alpha158Dataset()
lab.load_dataset(dataset)

# Train LightGBM model | 训练LightGBM模型
model = LGBModel()
lab.train_model(model)

# Generate signals and backtest | 生成信号并回测
lab.generate_signals()
lab.run_backtest()
```

### 3. Traditional VeighNa Trading | 传统VeighNa交易

```python
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp

from vnpy_ctp import CtpGateway
from vnpy_ctastrategy import CtaStrategyApp

def main():
    qapp = create_qapp()

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)

    # Add gateways and apps | 添加网关和应用
    main_engine.add_gateway(CtpGateway)
    main_engine.add_app(CtaStrategyApp)

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()

if __name__ == "__main__":
    main()
```

---

## 📁 Project Structure | 项目结构

```
AI-QTRD/
├── vnpy/                      # VeighNa core framework | 核心框架
│   ├── trader/                # Trading engine | 交易引擎
│   ├── alpha/                 # ML Alpha module | ML Alpha模块
│   ├── event/                 # Event engine | 事件引擎
│   ├── chart/                 # Chart visualization | 图表可视化
│   └── rpc/                   # RPC communication | RPC通信
│
├── vnpy_ai_trader/            # AI-enhanced subsystem | AI增强子系统
│   ├── src/
│   │   ├── ai_core/           # DeepSeek integration | DeepSeek集成
│   │   ├── strategy/          # AI strategies | AI策略
│   │   ├── datafeed/          # Free data sources | 免费数据源
│   │   ├── gateway/           # Trading gateways | 交易网关
│   │   └── web/               # Web interface | Web界面
│   ├── scripts/               # Execution scripts | 执行脚本
│   └── config/                # Configuration files | 配置文件
│
└── examples/
    └── alpha_research/        # ML research notebooks | ML研究示例
```

---

## 🔧 Code Quality | 代码质量

```bash
# Lint with ruff | 使用ruff检查代码
ruff check .

# Type check with mypy | 使用mypy类型检查
mypy vnpy

# Run tests | 运行测试
pytest tests/
```

---

## 📚 Documentation | 文档

- **VeighNa Documentation** | VeighNa官方文档: [www.vnpy.com/docs](https://www.vnpy.com/docs/cn/index.html)
- **AI Trader Guide** | AI交易指南: See `vnpy_ai_trader/doc/` | 见 `vnpy_ai_trader/doc/`
- **API Reference** | API参考: Auto-generated at `/docs` endpoint | Web服务的 `/docs` 端点自动生成

---

## 🎓 Key Dependencies | 核心依赖

- **PySide6**: GUI framework | GUI框架
- **Polars**: High-performance DataFrames | 高性能数据框架
- **NumPy / Pandas**: Data processing | 数据处理
- **TA-Lib**: Technical indicators | 技术指标
- **LightGBM / scikit-learn**: ML models | 机器学习模型
- **FastAPI**: Web API framework | Web API框架
- **OpenAI SDK**: DeepSeek client | DeepSeek客户端

---

## 🤝 Contributing | 贡献

We welcome contributions! Please follow the standard GitHub workflow:

欢迎贡献代码！请遵循标准的GitHub工作流程：

1. Fork the repository | Fork本仓库
2. Create a feature branch | 创建功能分支
3. Commit changes with clear messages | 提交明确的更改说明
4. Ensure code passes `ruff check .` and `mypy vnpy` | 确保代码通过代码检查
5. Submit a Pull Request | 提交Pull Request

---

## 📖 Credits | 致谢

**AI-QTRD** is built upon the excellent work of:

**AI-QTRD** 基于以下优秀项目构建：

- **[VeighNa](https://github.com/vnpy/vnpy)**: Core quantitative trading framework | 核心量化交易框架
- **[Qlib](https://github.com/microsoft/qlib)**: Inspiration for vnpy.alpha design | vnpy.alpha设计灵感来源
- **[DeepSeek](https://www.deepseek.com/)**: LLM inference engine | 大语言模型推理引擎
- **[AData](https://github.com/nrliangxy/adata)**: Free A-share data source | 免费A股数据源

---

## 📄 License | 许可证

MIT License

---

## 🔗 Links | 链接

- **GitHub**: [https://github.com/UU114/AI-QTRD](https://github.com/UU114/AI-QTRD)
- **VeighNa Official** | VeighNa官方: [www.vnpy.com](https://www.vnpy.com/)
- **Issues & Support** | 问题与支持: [GitHub Issues](https://github.com/UU114/AI-QTRD/issues)

---

<p align="center">
  <strong>AI-QTRD: Where Traditional Quantitative Trading Meets Modern AI</strong><br>
  <strong>AI-QTRD: 传统量化交易与现代AI的完美结合</strong>
</p>
