"""
Trading API Router.
交易API路由

Endpoints for order management:
- Send orders
- Cancel orders
- Query orders
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class OrderRequest(BaseModel):
    """Request model for sending an order."""
    symbol: str = Field(..., description="Stock symbol (e.g., 000001)")
    exchange: str = Field(..., description="Exchange (SSE or SZSE)")
    direction: str = Field(..., description="Direction (LONG or SHORT)")
    order_type: str = Field("LIMIT", description="Order type (LIMIT or MARKET)")
    volume: float = Field(..., description="Order volume (must be multiple of 100)")
    price: float = Field(..., description="Order price")


class CancelRequest(BaseModel):
    """Request model for canceling an order."""
    orderid: str = Field(..., description="Order ID to cancel")


class TickUpdate(BaseModel):
    """Request model for updating tick data (simulation)."""
    symbol: str = Field(..., description="Stock symbol")
    exchange: str = Field("SZSE", description="Exchange")
    last_price: float = Field(..., description="Last traded price")
    bid_price_1: float | None = Field(None, description="Best bid price")
    ask_price_1: float | None = Field(None, description="Best ask price")


@router.post("/order", response_model=dict)
async def send_order(request: Request, body: OrderRequest) -> dict[str, Any]:
    """
    Send a trading order.
    发送交易订单

    For A-shares:
    - Volume must be at least 100 shares
    - Volume must be a multiple of 100
    - Direction: LONG for buy, SHORT for sell
    """
    engine = request.app.state.trading_engine

    # Validate volume
    if body.volume < 100:
        raise HTTPException(status_code=400, detail="Volume must be at least 100 shares")

    if body.volume % 100 != 0:
        raise HTTPException(status_code=400, detail="Volume must be a multiple of 100")

    try:
        vt_orderid = engine.send_order(
            symbol=body.symbol,
            exchange=body.exchange,
            direction=body.direction,
            order_type=body.order_type,
            volume=body.volume,
            price=body.price,
        )

        if not vt_orderid:
            raise HTTPException(status_code=400, detail="Order rejected")

        return {
            "success": True,
            "orderid": vt_orderid,
            "message": "Order submitted successfully"
        }
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cancel", response_model=dict)
async def cancel_order(request: Request, body: CancelRequest) -> dict[str, Any]:
    """
    Cancel an active order.
    撤销活动订单
    """
    engine = request.app.state.trading_engine

    try:
        engine.cancel_order(body.orderid)
        return {
            "success": True,
            "orderid": body.orderid,
            "message": "Cancel request submitted"
        }
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orders", response_model=dict)
async def get_orders(request: Request) -> dict[str, Any]:
    """
    Get all orders.
    获取所有订单
    """
    engine = request.app.state.trading_engine
    orders = engine.get_orders()
    return {"success": True, "orders": orders}


@router.get("/orders/active", response_model=dict)
async def get_active_orders(request: Request) -> dict[str, Any]:
    """
    Get active (unfilled) orders only.
    仅获取活动订单
    """
    engine = request.app.state.trading_engine
    orders = engine.get_active_orders()
    return {"success": True, "orders": orders}


@router.post("/tick", response_model=dict)
async def update_tick(request: Request, body: TickUpdate) -> dict[str, Any]:
    """
    Update market tick data (for simulation).
    更新行情数据（用于模拟）

    This endpoint is used to feed market data into the paper trading
    account for order matching simulation.
    """
    engine = request.app.state.trading_engine

    tick_data = {
        "symbol": body.symbol,
        "exchange": body.exchange,
        "last_price": body.last_price,
        "bid_price_1": body.bid_price_1,
        "ask_price_1": body.ask_price_1,
    }

    engine.update_tick(tick_data)

    return {
        "success": True,
        "message": f"Tick updated for {body.symbol}"
    }
