"""
Data Preparation Router.
数据准备路由

API endpoints for downloading and managing historical data.
"""

from datetime import datetime
from fastapi import APIRouter, Request, HTTPException

from vnpy.trader.constant import Interval

from ..models import (
    DownloadRequest,
    DownloadResponse,
    ContractSettingRequest,
    ContractSettingsResponse,
    LocalDataResponse,
    JobStatusResponse,
    JobType
)

router = APIRouter(prefix="/api/data", tags=["data"])


@router.post("/download", response_model=DownloadResponse)
async def start_download(request: Request, data: DownloadRequest):
    """
    Start data download task.
    开始下载数据任务

    Downloads historical data from AData and saves to AlphaLab format.
    Returns a job_id for tracking progress via WebSocket.
    """
    job_manager = request.app.state.job_manager
    data_service = request.app.state.data_service

    # Parse dates
    try:
        start_date = datetime.strptime(data.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(data.end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Convert interval
    interval = Interval.DAILY if data.interval.value == "daily" else Interval.MINUTE

    # Submit job
    job_id = await job_manager.submit_job(
        job_type=JobType.DOWNLOAD,
        task_func=data_service.download_data,
        symbols=data.symbols,
        start_date=start_date,
        end_date=end_date,
        interval=interval
    )

    return DownloadResponse(
        success=True,
        job_id=job_id,
        message=f"Download started for {len(data.symbols)} symbols",
        total_symbols=len(data.symbols)
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_download_status(request: Request, job_id: str):
    """
    Get download job status.
    获取下载任务状态
    """
    job_manager = request.app.state.job_manager
    job_info = job_manager.get_job_info(job_id)

    if not job_info:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(success=True, job=job_info)


@router.get("/symbols", response_model=LocalDataResponse)
async def get_local_symbols(request: Request, interval: str = "daily"):
    """
    Get list of symbols with local data.
    获取本地数据标的列表

    Args:
        interval: 'daily' or 'minute'
    """
    data_service = request.app.state.data_service
    symbols = data_service.get_local_symbols(interval)

    return LocalDataResponse(
        success=True,
        symbols=symbols,
        total_count=len(symbols)
    )


@router.post("/contracts", response_model=ContractSettingsResponse)
async def configure_contracts(request: Request, data: ContractSettingRequest):
    """
    Configure contract settings for symbols.
    配置合约设置

    Sets commission rates, stamp duty, etc. for A-share trading.
    """
    data_service = request.app.state.data_service

    data_service.configure_contracts(
        symbols=data.symbols,
        long_rate=data.long_rate,
        short_rate=data.short_rate,
        size=data.size,
        pricetick=data.pricetick
    )

    contracts = data_service.get_contract_settings()

    return ContractSettingsResponse(success=True, contracts=contracts)


@router.get("/contracts", response_model=ContractSettingsResponse)
async def get_contracts(request: Request):
    """
    Get all contract settings.
    获取所有合约设置
    """
    data_service = request.app.state.data_service
    contracts = data_service.get_contract_settings()

    return ContractSettingsResponse(success=True, contracts=contracts)


@router.delete("/{symbol}")
async def delete_symbol_data(request: Request, symbol: str, interval: str = "daily"):
    """
    Delete local data for a symbol.
    删除本地数据

    Args:
        symbol: Stock symbol or vt_symbol
        interval: 'daily' or 'minute'
    """
    data_service = request.app.state.data_service
    deleted = data_service.delete_symbol_data(symbol, interval)

    if not deleted:
        raise HTTPException(status_code=404, detail="Symbol data not found")

    return {"success": True, "message": f"Deleted data for {symbol}"}


@router.get("/check")
async def check_data_exists(
    request: Request,
    symbols: str,
    interval: str = "daily"
):
    """
    Check if data exists for symbols.
    检查数据是否存在

    Args:
        symbols: Comma-separated list of symbols
        interval: 'daily' or 'minute'
    """
    data_service = request.app.state.data_service
    symbol_list = [s.strip() for s in symbols.split(",")]
    result = data_service.check_data_exists(symbol_list, interval)

    return {"success": True, "data_exists": result}
