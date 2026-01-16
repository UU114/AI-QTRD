"""
WebSocket Connection Manager.
WebSocket连接管理器

Manages WebSocket connections for real-time updates to clients.
"""

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from ..utils.logger import get_logger

logger = get_logger("websocket")


class WebSocketManager:
    """
    WebSocket Connection Manager.
    WebSocket连接管理器

    Features:
    - Multiple client connections
    - Symbol-based subscriptions
    - Broadcast and targeted messaging
    """

    def __init__(self):
        """Initialize WebSocket manager."""
        # All active connections
        self.active_connections: list[WebSocket] = []

        # Symbol subscriptions: {symbol: [websocket1, websocket2, ...]}
        self.subscriptions: dict[str, list[WebSocket]] = defaultdict(list)

        # Reverse mapping: {websocket: [symbol1, symbol2, ...]}
        self.client_subscriptions: dict[WebSocket, list[str]] = defaultdict(list)

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    @property
    def active_connections_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept a new WebSocket connection.

        Args:
            websocket: WebSocket connection to add
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection.

        Args:
            websocket: WebSocket connection to remove
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        # Remove from all subscriptions
        if websocket in self.client_subscriptions:
            for symbol in self.client_subscriptions[websocket]:
                if websocket in self.subscriptions[symbol]:
                    self.subscriptions[symbol].remove(websocket)
            del self.client_subscriptions[websocket]

        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    def subscribe(self, websocket: WebSocket, symbol: str) -> None:
        """
        Subscribe a client to symbol updates.

        Args:
            websocket: WebSocket connection
            symbol: Symbol to subscribe to (e.g., "000001.SZSE")
        """
        if websocket not in self.subscriptions[symbol]:
            self.subscriptions[symbol].append(websocket)
            self.client_subscriptions[websocket].append(symbol)
            logger.debug(f"Client subscribed to {symbol}")

    def unsubscribe(self, websocket: WebSocket, symbol: str) -> None:
        """
        Unsubscribe a client from symbol updates.

        Args:
            websocket: WebSocket connection
            symbol: Symbol to unsubscribe from
        """
        if websocket in self.subscriptions[symbol]:
            self.subscriptions[symbol].remove(websocket)
        if symbol in self.client_subscriptions[websocket]:
            self.client_subscriptions[websocket].remove(symbol)
            logger.debug(f"Client unsubscribed from {symbol}")

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        """
        Send a message to a specific client.

        Args:
            websocket: Target WebSocket connection
            message: Message to send
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: dict) -> None:
        """
        Broadcast a message to all connected clients.

        Args:
            message: Message to broadcast
        """
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to broadcast: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_to_symbol(self, symbol: str, message: dict) -> None:
        """
        Send a message to all clients subscribed to a symbol.

        Args:
            symbol: Target symbol
            message: Message to send
        """
        subscribers = self.subscriptions.get(symbol, [])
        disconnected = []

        for connection in subscribers:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to subscriber: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def send_tick(self, symbol: str, tick_data: dict) -> None:
        """
        Send tick data update.

        Args:
            symbol: Stock symbol
            tick_data: Tick data dictionary
        """
        message = {
            "type": "tick",
            "symbol": symbol,
            "data": tick_data
        }
        await self.broadcast_to_symbol(symbol, message)

    async def send_order_update(self, order_data: dict) -> None:
        """
        Broadcast order status update.

        Args:
            order_data: Order data dictionary
        """
        message = {
            "type": "order",
            "data": order_data
        }
        await self.broadcast(message)

    async def send_trade_update(self, trade_data: dict) -> None:
        """
        Broadcast trade execution update.

        Args:
            trade_data: Trade data dictionary
        """
        message = {
            "type": "trade",
            "data": trade_data
        }
        await self.broadcast(message)

    async def send_position_update(self, position_data: dict) -> None:
        """
        Broadcast position update.

        Args:
            position_data: Position data dictionary
        """
        message = {
            "type": "position",
            "data": position_data
        }
        await self.broadcast(message)

    async def send_account_update(self, account_data: dict) -> None:
        """
        Broadcast account update.

        Args:
            account_data: Account data dictionary
        """
        message = {
            "type": "account",
            "data": account_data
        }
        await self.broadcast(message)

    async def send_signal(self, signal_data: dict) -> None:
        """
        Broadcast trading signal.

        Args:
            signal_data: Signal data dictionary
        """
        message = {
            "type": "signal",
            "data": signal_data
        }
        await self.broadcast(message)

    async def send_log(self, level: str, msg: str) -> None:
        """
        Broadcast log message.

        Args:
            level: Log level (info, warning, error)
            msg: Log message
        """
        message = {
            "type": "log",
            "level": level,
            "message": msg
        }
        await self.broadcast(message)

    async def send_job_progress(self, job_id: str, job_type: str, progress: dict) -> None:
        """
        Broadcast job progress update.

        Args:
            job_id: Unique job identifier
            job_type: Type of job (download, backtest)
            progress: Progress data dictionary
        """
        message = {
            "type": f"{job_type}_progress",
            "job_id": job_id,
            **progress
        }
        await self.broadcast(message)

    async def send_job_completed(self, job_id: str, job_type: str, result: dict | None = None) -> None:
        """
        Broadcast job completion notification.

        Args:
            job_id: Unique job identifier
            job_type: Type of job (download, backtest)
            result: Optional result summary
        """
        message = {
            "type": "job_completed",
            "job_id": job_id,
            "job_type": job_type,
            "result": result
        }
        await self.broadcast(message)

    async def send_job_failed(self, job_id: str, job_type: str, error: str) -> None:
        """
        Broadcast job failure notification.

        Args:
            job_id: Unique job identifier
            job_type: Type of job (download, backtest)
            error: Error message
        """
        message = {
            "type": "job_failed",
            "job_id": job_id,
            "job_type": job_type,
            "error": error
        }
        await self.broadcast(message)
