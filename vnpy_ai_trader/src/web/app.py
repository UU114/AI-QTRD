"""
FastAPI Web Application.
FastAPI Web应用

Main entry point for the web interface providing:
- REST API for strategy management
- Trading operations
- Real-time WebSocket updates
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .routers import strategy, trading, account, market, data, backtest
from .websocket_manager import WebSocketManager
from .trading_engine import TradingEngine
from .services import JobManager, DataService, BacktestService
from ..utils.logger import get_logger

logger = get_logger("web_app")

# Global instances
ws_manager = WebSocketManager()
trading_engine: TradingEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global trading_engine

    logger.info("Starting VNPy AI Trader Web Server...")

    # Initialize trading engine
    trading_engine = TradingEngine(ws_manager)
    await trading_engine.initialize()

    # Initialize job manager with WebSocket for progress updates
    job_manager = JobManager(ws_manager)

    # Initialize data and backtest services
    data_service = DataService(data_dir="./data/lab")
    backtest_service = BacktestService(
        data_dir="./data/lab",
        results_dir="./data/backtest_results"
    )

    # Store in app state
    app.state.trading_engine = trading_engine
    app.state.ws_manager = ws_manager
    app.state.job_manager = job_manager
    app.state.data_service = data_service
    app.state.backtest_service = backtest_service

    logger.info("All services initialized successfully")

    yield

    # Cleanup
    logger.info("Shutting down...")
    await job_manager.shutdown()
    if trading_engine:
        await trading_engine.shutdown()


# Create FastAPI application
app = FastAPI(
    title="VNPy AI Trader",
    description="AI-enhanced A-share automated trading system / AI增强型A股自动化交易系统",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(strategy.router, prefix="/api/strategy", tags=["Strategy"])
app.include_router(trading.router, prefix="/api/trading", tags=["Trading"])
app.include_router(account.router, prefix="/api/account", tags=["Account"])
app.include_router(market.router, prefix="/api/market", tags=["Market"])
app.include_router(data.router, tags=["Data"])
app.include_router(backtest.router, tags=["Backtest"])

# Mount static files for frontend
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=FileResponse)
async def root():
    """Serve the main frontend page."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "VNPy AI Trader API", "docs": "/docs"}


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "trading_engine": trading_engine is not None,
        "websocket_connections": ws_manager.active_connections_count,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.

    Message types:
    - tick: Real-time market data
    - order: Order status updates
    - trade: Trade execution notifications
    - position: Position changes
    - account: Account balance updates
    - signal: Strategy signal notifications
    - log: System log messages
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_json()
            await handle_ws_message(websocket, data)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


async def handle_ws_message(websocket: WebSocket, data: dict) -> None:
    """Handle incoming WebSocket messages."""
    msg_type = data.get("type", "")

    if msg_type == "subscribe":
        # Subscribe to specific symbols
        symbols = data.get("symbols", [])
        for symbol in symbols:
            ws_manager.subscribe(websocket, symbol)
        await websocket.send_json({
            "type": "subscribed",
            "symbols": symbols
        })

    elif msg_type == "unsubscribe":
        # Unsubscribe from symbols
        symbols = data.get("symbols", [])
        for symbol in symbols:
            ws_manager.unsubscribe(websocket, symbol)
        await websocket.send_json({
            "type": "unsubscribed",
            "symbols": symbols
        })

    elif msg_type == "ping":
        # Heartbeat
        await websocket.send_json({"type": "pong"})

    else:
        await websocket.send_json({
            "type": "error",
            "message": f"Unknown message type: {msg_type}"
        })


def create_app() -> FastAPI:
    """Factory function to create the app."""
    return app
