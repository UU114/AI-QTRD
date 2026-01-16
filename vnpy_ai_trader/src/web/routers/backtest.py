"""
Backtest Router.
回测路由

API endpoints for running and managing backtests.
"""

import os
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException

from vnpy.trader.constant import Interval

from ..models import (
    BacktestRequest,
    BacktestResponse,
    BacktestResult,
    BacktestListResponse,
    EquityCurveResponse,
    JobStatusResponse,
    JobStatus,
    JobType
)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(request: Request, data: BacktestRequest):
    """
    Start a backtest job.
    开始回测任务

    Runs backtest asynchronously and returns job_id for progress tracking.
    Strategy can be provided as:
    - strategy_config: JSON configuration
    - strategy_description: Natural language (parsed via DeepSeek)
    - strategy_id: ID of a saved strategy
    """
    job_manager = request.app.state.job_manager
    backtest_service = request.app.state.backtest_service
    trading_engine = request.app.state.trading_engine

    # Parse dates
    try:
        start_date = datetime.strptime(data.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(data.end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Get strategy configuration
    strategy_config = None

    if data.strategy_config:
        strategy_config = data.strategy_config

    elif data.strategy_description:
        # Parse natural language strategy
        try:
            strategy_config = await backtest_service.parse_strategy(
                data.strategy_description
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Strategy parsing failed: {e}")

    elif data.strategy_id:
        # Load saved strategy
        strategy = trading_engine.get_strategy(data.strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        strategy_config = strategy.get("config", {})

    else:
        # Use default demo strategy
        strategy_config = {
            "strategy_name": "demo_strategy",
            "entry_rules": {
                "conditions": [
                    {"indicator": "RSI", "params": {"period": 14}, "operator": "<", "value": 30}
                ],
                "ai_enhanced": False
            },
            "exit_rules": {
                "take_profit": 0.10,
                "stop_loss": 0.05,
                "holding_days": 20
            },
            "risk_control": {
                "max_positions": 10,
                "position_size": 0.1
            }
        }

    # Convert interval
    interval = Interval.DAILY if data.interval.value == "daily" else Interval.MINUTE

    # Create wrapper function that saves results
    async def backtest_with_save(progress_callback=None, **kwargs):
        result = await backtest_service.run_backtest(
            strategy_config=strategy_config,
            symbols=data.symbols,
            start_date=start_date,
            end_date=end_date,
            capital=data.capital,
            interval=interval,
            progress_callback=progress_callback
        )

        # Save result to disk
        job_id = kwargs.get("_job_id", "unknown")
        backtest_service.save_result(
            job_id=job_id,
            result=result,
            strategy_config=strategy_config,
            symbols=data.symbols
        )

        return result

    # Submit job
    job_id = await job_manager.submit_job(
        job_type=JobType.BACKTEST,
        task_func=backtest_with_save,
        _job_id=""  # Will be set properly after job creation
    )

    # Update the job with its own ID for result saving
    job = job_manager.get_job(job_id)
    if job:
        job.metadata["_job_id"] = job_id

    return BacktestResponse(
        success=True,
        job_id=job_id,
        message=f"Backtest started for {len(data.symbols)} symbols"
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_backtest_status(request: Request, job_id: str):
    """
    Get backtest job status.
    获取回测任务状态
    """
    job_manager = request.app.state.job_manager
    job_info = job_manager.get_job_info(job_id)

    if not job_info:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(success=True, job=job_info)


@router.get("/results/{job_id}")
async def get_backtest_result(request: Request, job_id: str):
    """
    Get backtest result by job ID.
    获取回测结果

    Returns full statistics and can be used after job completes.
    """
    backtest_service = request.app.state.backtest_service
    result = backtest_service.load_result(job_id)

    if not result:
        # Check if job is still running
        job_manager = request.app.state.job_manager
        job = job_manager.get_job(job_id)

        if job and job.status == JobStatus.RUNNING:
            return {
                "success": False,
                "message": "Backtest still running",
                "status": "running"
            }

        raise HTTPException(status_code=404, detail="Result not found")

    return {"success": True, "result": result}


@router.get("/list", response_model=BacktestListResponse)
async def list_backtests(request: Request, limit: int = 20):
    """
    List all backtest results.
    列出所有回测结果

    Args:
        limit: Maximum number of results to return
    """
    backtest_service = request.app.state.backtest_service
    results = backtest_service.list_results()

    # Apply limit
    results = results[:limit]

    return BacktestListResponse(
        success=True,
        results=results,
        total_count=len(results)
    )


@router.get("/{job_id}/chart", response_model=EquityCurveResponse)
async def get_equity_curve(request: Request, job_id: str):
    """
    Get equity curve data for charting.
    获取权益曲线数据

    Returns dates, balance, drawdown, and daily P&L arrays.
    """
    backtest_service = request.app.state.backtest_service
    curve_data = backtest_service.get_equity_curve(job_id)

    if not curve_data:
        raise HTTPException(status_code=404, detail="Equity curve data not found")

    return EquityCurveResponse(
        success=True,
        job_id=job_id,
        data=curve_data
    )


@router.delete("/{job_id}")
async def delete_backtest(request: Request, job_id: str):
    """
    Delete a backtest result.
    删除回测结果
    """
    backtest_service = request.app.state.backtest_service
    deleted = backtest_service.delete_result(job_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Result not found")

    return {"success": True, "message": f"Deleted backtest {job_id}"}


@router.post("/{job_id}/cancel")
async def cancel_backtest(request: Request, job_id: str):
    """
    Cancel a running backtest.
    取消正在运行的回测
    """
    job_manager = request.app.state.job_manager
    cancelled = await job_manager.cancel_job(job_id)

    if not cancelled:
        raise HTTPException(status_code=400, detail="Cannot cancel job")

    return {"success": True, "message": f"Cancelled backtest {job_id}"}
