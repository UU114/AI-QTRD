"""
Pydantic Models for Web API.
Web API Pydantic模型

Request and response models for data preparation and backtesting endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ========== Enumerations ==========

class DataInterval(str, Enum):
    """Data interval enumeration / 数据周期枚举"""
    DAILY = "daily"
    MINUTE = "minute"


class JobStatus(str, Enum):
    """Job status enumeration / 任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Job type enumeration / 任务类型枚举"""
    DOWNLOAD = "download"
    BACKTEST = "backtest"


# ========== Data Preparation Models ==========

class DownloadRequest(BaseModel):
    """Request to download historical data / 下载历史数据请求"""
    symbols: list[str] = Field(..., description="List of stock symbols")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    interval: DataInterval = Field(default=DataInterval.DAILY)


class DownloadResponse(BaseModel):
    """Response for download task / 下载任务响应"""
    success: bool
    job_id: str
    message: str
    total_symbols: int


class DownloadProgress(BaseModel):
    """Download progress update / 下载进度更新"""
    job_id: str
    status: JobStatus
    current_symbol: Optional[str] = None
    current_index: int = 0
    total_symbols: int = 0
    completed_symbols: list[str] = Field(default_factory=list)
    failed_symbols: list[str] = Field(default_factory=list)
    progress_percent: float = 0.0
    error: Optional[str] = None


class ContractSettingRequest(BaseModel):
    """Request to configure contract settings / 合约设置请求"""
    symbols: list[str]
    long_rate: float = Field(default=0.0003, description="Long commission rate")
    short_rate: float = Field(default=0.0013, description="Short rate with stamp duty")
    size: float = Field(default=1.0, description="Contract size")
    pricetick: float = Field(default=0.01, description="Price tick")


class LocalSymbolInfo(BaseModel):
    """Local symbol data info / 本地标的数据信息"""
    symbol: str
    exchange: str
    vt_symbol: str
    interval: str
    bar_count: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    file_size_kb: float = 0.0


class LocalDataResponse(BaseModel):
    """Response with local data info / 本地数据响应"""
    success: bool
    symbols: list[LocalSymbolInfo] = Field(default_factory=list)
    total_count: int = 0


class ContractSettingsResponse(BaseModel):
    """Response with contract settings / 合约设置响应"""
    success: bool
    contracts: dict[str, dict] = Field(default_factory=dict)


# ========== Backtest Models ==========

class BacktestRequest(BaseModel):
    """Request to run backtest / 运行回测请求"""
    # Strategy configuration (one of these required)
    strategy_config: Optional[dict] = Field(None, description="Strategy JSON config")
    strategy_description: Optional[str] = Field(None, description="Natural language strategy")
    strategy_id: Optional[str] = Field(None, description="ID of saved strategy")

    # Backtest parameters
    symbols: list[str] = Field(..., description="Symbols to trade")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    capital: int = Field(default=1_000_000, description="Initial capital")
    interval: DataInterval = Field(default=DataInterval.DAILY)


class BacktestResponse(BaseModel):
    """Response for backtest task / 回测任务响应"""
    success: bool
    job_id: str
    message: str


class BacktestProgress(BaseModel):
    """Backtest progress update / 回测进度更新"""
    job_id: str
    status: JobStatus
    phase: str = ""  # 'parsing', 'loading_data', 'running', 'calculating'
    progress_percent: float = 0.0
    current_date: Optional[str] = None
    start_date: str = ""
    end_date: str = ""
    elapsed_seconds: float = 0.0
    error: Optional[str] = None


class BacktestStatistics(BaseModel):
    """Backtest result statistics / 回测结果统计"""
    start_date: str
    end_date: str
    total_days: int
    profit_days: int
    loss_days: int
    capital: float
    end_balance: float
    total_return: float
    annual_return: float
    max_drawdown: float
    max_ddpercent: float
    max_drawdown_duration: int
    sharpe_ratio: float
    total_trade_count: int
    total_commission: float
    total_turnover: float
    return_drawdown_ratio: float


class BacktestResult(BaseModel):
    """Complete backtest result / 完整回测结果"""
    job_id: str
    status: JobStatus
    strategy_name: str = ""
    strategy_config: Optional[dict] = None
    symbols: list[str] = Field(default_factory=list)
    statistics: Optional[BacktestStatistics] = None
    created_at: str = ""
    completed_at: Optional[str] = None
    error: Optional[str] = None


class BacktestListResponse(BaseModel):
    """Response with backtest list / 回测列表响应"""
    success: bool
    results: list[BacktestResult] = Field(default_factory=list)
    total_count: int = 0


class EquityCurveData(BaseModel):
    """Equity curve data for charting / 权益曲线图表数据"""
    dates: list[str] = Field(default_factory=list)
    balance: list[float] = Field(default_factory=list)
    drawdown: list[float] = Field(default_factory=list)
    daily_pnl: list[float] = Field(default_factory=list)
    daily_return: list[float] = Field(default_factory=list)


class EquityCurveResponse(BaseModel):
    """Response with equity curve data / 权益曲线响应"""
    success: bool
    job_id: str
    data: Optional[EquityCurveData] = None
    error: Optional[str] = None


# ========== Job Models ==========

class JobInfo(BaseModel):
    """Job information / 任务信息"""
    job_id: str
    job_type: JobType
    status: JobStatus
    progress: float = 0.0
    created_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    """Response with job status / 任务状态响应"""
    success: bool
    job: Optional[JobInfo] = None
    error: Optional[str] = None
