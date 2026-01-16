"""
Strategy API Router.
策略API路由

Endpoints for strategy management:
- Parse natural language strategies
- Create, list, update, delete strategies
- Activate/deactivate strategies
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class ParseRequest(BaseModel):
    """Request model for parsing natural language strategy."""
    description: str = Field(..., description="Natural language strategy description")


class StrategyCreate(BaseModel):
    """Request model for creating a strategy."""
    strategy_id: str = Field(..., description="Unique strategy identifier")
    config: dict = Field(..., description="Strategy configuration JSON")
    description: str = Field("", description="Optional human-readable description")


class StrategyFromNL(BaseModel):
    """Request model for creating strategy from natural language."""
    strategy_id: str = Field(..., description="Unique strategy identifier")
    description: str = Field(..., description="Natural language strategy description")


@router.post("/parse", response_model=dict)
async def parse_strategy(request: Request, body: ParseRequest) -> dict[str, Any]:
    """
    Parse a natural language strategy description into JSON config.
    将自然语言策略描述解析为JSON配置

    This endpoint uses DeepSeek LLM to convert natural language
    trading strategy descriptions into structured JSON configuration.
    """
    engine = request.app.state.trading_engine

    try:
        config = await engine.parse_strategy(body.description)
        return {
            "success": True,
            "config": config,
            "description": body.description
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse error: {str(e)}")


@router.post("/create", response_model=dict)
async def create_strategy(request: Request, body: StrategyCreate) -> dict[str, Any]:
    """
    Create a new strategy with JSON configuration.
    使用JSON配置创建新策略
    """
    engine = request.app.state.trading_engine

    try:
        strategy = await engine.create_strategy(
            strategy_id=body.strategy_id,
            config=body.config,
            description=body.description
        )
        return {"success": True, "strategy": strategy}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/create-from-nl", response_model=dict)
async def create_from_natural_language(
    request: Request, body: StrategyFromNL
) -> dict[str, Any]:
    """
    Create a strategy from natural language description.
    从自然语言描述创建策略

    This combines parsing and creation in one step.
    """
    engine = request.app.state.trading_engine

    try:
        # Parse natural language to config
        config = await engine.parse_strategy(body.description)

        # Create strategy with parsed config
        strategy = await engine.create_strategy(
            strategy_id=body.strategy_id,
            config=config,
            description=body.description
        )
        return {"success": True, "strategy": strategy}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/list", response_model=dict)
async def list_strategies(request: Request) -> dict[str, Any]:
    """
    List all strategies.
    列出所有策略
    """
    engine = request.app.state.trading_engine
    strategies = await engine.list_strategies()
    return {"success": True, "strategies": strategies}


@router.get("/{strategy_id}", response_model=dict)
async def get_strategy(request: Request, strategy_id: str) -> dict[str, Any]:
    """
    Get a specific strategy by ID.
    根据ID获取特定策略
    """
    engine = request.app.state.trading_engine
    strategy = await engine.get_strategy(strategy_id)

    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

    return {"success": True, "strategy": strategy}


@router.delete("/{strategy_id}", response_model=dict)
async def delete_strategy(request: Request, strategy_id: str) -> dict[str, Any]:
    """
    Delete a strategy.
    删除策略
    """
    engine = request.app.state.trading_engine
    success = await engine.delete_strategy(strategy_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

    return {"success": True, "message": f"Strategy {strategy_id} deleted"}


@router.post("/{strategy_id}/activate", response_model=dict)
async def activate_strategy(request: Request, strategy_id: str) -> dict[str, Any]:
    """
    Activate a strategy for trading.
    激活策略进行交易
    """
    engine = request.app.state.trading_engine

    try:
        await engine.activate_strategy(strategy_id)
        return {"success": True, "message": f"Strategy {strategy_id} activated"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{strategy_id}/deactivate", response_model=dict)
async def deactivate_strategy(request: Request, strategy_id: str) -> dict[str, Any]:
    """
    Deactivate a strategy.
    停用策略
    """
    engine = request.app.state.trading_engine
    success = await engine.deactivate_strategy(strategy_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

    return {"success": True, "message": f"Strategy {strategy_id} deactivated"}
