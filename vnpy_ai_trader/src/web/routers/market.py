"""
Market Data API Router.
行情数据API路由

Endpoints for market data queries:
- Historical bar data
- Symbol search
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Query

router = APIRouter()


@router.get("/history", response_model=dict)
async def get_history(
    request: Request,
    symbol: str = Query(..., description="Stock symbol (e.g., 000001)"),
    exchange: str = Query("SZSE", description="Exchange (SSE or SZSE)"),
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
    interval: str = Query("1d", description="Data interval (1m, 5m, 15m, 30m, 1h, 1d)"),
) -> dict[str, Any]:
    """
    Get historical bar data.
    获取历史K线数据

    Returns OHLCV data for the specified symbol and time range.
    返回指定标的和时间范围的OHLCV数据。
    """
    engine = request.app.state.trading_engine

    # Validate interval
    valid_intervals = ["1m", "5m", "15m", "30m", "1h", "1d"]
    if interval not in valid_intervals:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval. Must be one of: {valid_intervals}"
        )

    # Validate exchange
    if exchange.upper() not in ["SSE", "SZSE"]:
        raise HTTPException(
            status_code=400,
            detail="Exchange must be SSE or SZSE"
        )

    try:
        bars = await engine.get_history(
            symbol=symbol,
            exchange=exchange,
            start=start,
            end=end,
            interval=interval
        )

        return {
            "success": True,
            "symbol": symbol,
            "exchange": exchange,
            "interval": interval,
            "count": len(bars),
            "data": bars
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch data: {str(e)}")


@router.get("/quote", response_model=dict)
async def get_quote(
    request: Request,
    symbol: str = Query(..., description="Stock symbol"),
    exchange: str = Query("SZSE", description="Exchange (SSE or SZSE)"),
) -> dict[str, Any]:
    """
    Get latest quote for a symbol.
    获取标的最新报价

    Note: In paper trading mode, returns the last known price
    from the paper account's tick data.
    """
    engine = request.app.state.trading_engine

    vt_symbol = f"{symbol}.{exchange.upper()}"

    # Check if we have tick data
    if engine.paper_account and vt_symbol in engine.paper_account.ticks:
        tick = engine.paper_account.ticks[vt_symbol]
        return {
            "success": True,
            "symbol": symbol,
            "exchange": exchange,
            "quote": {
                "last_price": tick.last_price,
                "bid_price_1": tick.bid_price_1,
                "ask_price_1": tick.ask_price_1,
                "volume": tick.volume,
                "datetime": tick.datetime.isoformat() if tick.datetime else None,
            }
        }

    # No tick data available, try to get from historical
    try:
        from datetime import datetime, timedelta

        end = datetime.now()
        start = end - timedelta(days=5)

        bars = await engine.get_history(
            symbol=symbol,
            exchange=exchange,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1d"
        )

        if bars:
            last_bar = bars[-1]
            return {
                "success": True,
                "symbol": symbol,
                "exchange": exchange,
                "quote": {
                    "last_price": last_bar["close"],
                    "open": last_bar["open"],
                    "high": last_bar["high"],
                    "low": last_bar["low"],
                    "volume": last_bar["volume"],
                    "datetime": last_bar["datetime"],
                },
                "source": "historical"
            }
    except Exception:
        pass

    raise HTTPException(status_code=404, detail=f"No quote available for {vt_symbol}")


@router.get("/symbols", response_model=dict)
async def search_symbols(
    request: Request,
    query: str = Query("", description="Search query"),
    exchange: str = Query("", description="Filter by exchange"),
) -> dict[str, Any]:
    """
    Search for stock symbols.
    搜索股票代码

    Note: This is a basic implementation. In production,
    you would query a comprehensive symbol database.
    """
    # Common A-share symbols for demo
    demo_symbols = [
        {"symbol": "000001", "exchange": "SZSE", "name": "平安银行"},
        {"symbol": "000002", "exchange": "SZSE", "name": "万科A"},
        {"symbol": "000063", "exchange": "SZSE", "name": "中兴通讯"},
        {"symbol": "000333", "exchange": "SZSE", "name": "美的集团"},
        {"symbol": "000651", "exchange": "SZSE", "name": "格力电器"},
        {"symbol": "000858", "exchange": "SZSE", "name": "五粮液"},
        {"symbol": "002415", "exchange": "SZSE", "name": "海康威视"},
        {"symbol": "002594", "exchange": "SZSE", "name": "比亚迪"},
        {"symbol": "300750", "exchange": "SZSE", "name": "宁德时代"},
        {"symbol": "600000", "exchange": "SSE", "name": "浦发银行"},
        {"symbol": "600036", "exchange": "SSE", "name": "招商银行"},
        {"symbol": "600519", "exchange": "SSE", "name": "贵州茅台"},
        {"symbol": "600900", "exchange": "SSE", "name": "长江电力"},
        {"symbol": "601318", "exchange": "SSE", "name": "中国平安"},
        {"symbol": "601398", "exchange": "SSE", "name": "工商银行"},
    ]

    results = demo_symbols

    # Filter by query
    if query:
        query = query.lower()
        results = [
            s for s in results
            if query in s["symbol"].lower() or query in s["name"].lower()
        ]

    # Filter by exchange
    if exchange:
        results = [s for s in results if s["exchange"].upper() == exchange.upper()]

    return {
        "success": True,
        "count": len(results),
        "symbols": results
    }
