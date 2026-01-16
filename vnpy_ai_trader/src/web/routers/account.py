"""
Account API Router.
账户API路由

Endpoints for account and position management:
- Query account balance
- Query positions
- Reset paper trading account
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class ResetRequest(BaseModel):
    """Request model for resetting account."""
    initial_capital: float | None = Field(None, description="New initial capital")


@router.get("/info", response_model=dict)
async def get_account_info(request: Request) -> dict[str, Any]:
    """
    Get account information.
    获取账户信息

    Returns:
    - initial_capital: Starting capital
    - balance: Current total balance
    - frozen: Frozen funds (in pending orders)
    - available: Available funds for trading
    - total_pnl: Total profit/loss
    - total_commission: Total commission paid
    - total_trades: Number of trades executed
    - return_pct: Return percentage
    """
    engine = request.app.state.trading_engine
    account = engine.get_account()

    if not account:
        raise HTTPException(status_code=500, detail="Account not initialized")

    return {"success": True, "account": account}


@router.get("/positions", response_model=dict)
async def get_positions(request: Request) -> dict[str, Any]:
    """
    Get all positions.
    获取所有持仓

    Returns list of positions with:
    - symbol: Stock symbol
    - exchange: Exchange
    - volume: Position volume
    - frozen: Frozen volume
    - avg_price: Average cost price
    - pnl: Unrealized profit/loss
    """
    engine = request.app.state.trading_engine
    positions = engine.get_positions()

    return {"success": True, "positions": positions}


@router.get("/summary", response_model=dict)
async def get_account_summary(request: Request) -> dict[str, Any]:
    """
    Get combined account and position summary.
    获取账户和持仓汇总

    Returns both account info and positions in one call.
    """
    engine = request.app.state.trading_engine

    account = engine.get_account()
    positions = engine.get_positions()

    # Calculate total position value
    total_position_value = sum(
        pos.get("volume", 0) * pos.get("avg_price", 0)
        for pos in positions
    )

    # Calculate total unrealized P&L
    total_unrealized_pnl = sum(
        pos.get("pnl", 0) for pos in positions
    )

    return {
        "success": True,
        "account": account,
        "positions": positions,
        "summary": {
            "total_position_value": total_position_value,
            "total_unrealized_pnl": total_unrealized_pnl,
            "position_count": len(positions),
        }
    }


@router.post("/reset", response_model=dict)
async def reset_account(request: Request, body: ResetRequest = None) -> dict[str, Any]:
    """
    Reset paper trading account to initial state.
    重置模拟交易账户到初始状态

    This will:
    - Clear all positions
    - Clear all orders
    - Reset balance to initial capital
    - Reset all statistics
    """
    engine = request.app.state.trading_engine

    try:
        # Reset account
        account = engine.reset_account()

        return {
            "success": True,
            "message": "Account reset successfully",
            "account": account
        }
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics", response_model=dict)
async def get_statistics(request: Request) -> dict[str, Any]:
    """
    Get trading statistics.
    获取交易统计

    Returns detailed trading statistics including:
    - Total trades
    - Win rate (if applicable)
    - Return metrics
    - Commission costs
    """
    engine = request.app.state.trading_engine
    account = engine.get_account()
    positions = engine.get_positions()

    # Calculate additional statistics
    total_position_value = sum(
        pos.get("volume", 0) * pos.get("avg_price", 0)
        for pos in positions
    )

    total_unrealized_pnl = sum(
        pos.get("pnl", 0) for pos in positions
    )

    # Calculate net asset value
    nav = account.get("balance", 0) + total_position_value

    statistics = {
        "initial_capital": account.get("initial_capital", 0),
        "net_asset_value": nav,
        "cash_balance": account.get("balance", 0),
        "position_value": total_position_value,
        "frozen_funds": account.get("frozen", 0),
        "realized_pnl": account.get("total_pnl", 0),
        "unrealized_pnl": total_unrealized_pnl,
        "total_pnl": account.get("total_pnl", 0) + total_unrealized_pnl,
        "total_commission": account.get("total_commission", 0),
        "total_trades": account.get("total_trades", 0),
        "return_pct": (nav - account.get("initial_capital", 0)) / account.get("initial_capital", 1) * 100,
        "position_count": len(positions),
    }

    return {"success": True, "statistics": statistics}
