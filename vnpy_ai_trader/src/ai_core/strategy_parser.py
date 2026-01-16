"""
Natural Language Strategy Parser.
自然语言策略解析器

Converts user's natural language strategy description into structured JSON configuration.
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import validate, ValidationError

from .deepseek_client import DeepSeekClient
from .prompt_manager import PromptManager
from ..utils.logger import get_logger

logger = get_logger("strategy_parser")


class StrategyParser:
    """
    Parses natural language trading strategy descriptions into JSON configurations.
    Uses DeepSeek LLM for understanding and conversion.
    """

    def __init__(
        self,
        deepseek_client: DeepSeekClient | None = None,
        prompt_manager: PromptManager | None = None,
        schema_path: str | Path | None = None
    ):
        """
        Initialize strategy parser.

        Args:
            deepseek_client: DeepSeek API client instance
            prompt_manager: Prompt template manager
            schema_path: Path to strategy JSON schema file
        """
        self.client = deepseek_client or DeepSeekClient()
        self.prompt_manager = prompt_manager or PromptManager()

        # Load JSON schema for validation
        if schema_path is None:
            schema_path = Path(__file__).parent.parent.parent / "config" / "strategy_schema.json"

        self.schema_path = Path(schema_path)
        self.schema = self._load_schema()

    def _load_schema(self) -> dict | None:
        """Load JSON schema for strategy validation."""
        if not self.schema_path.exists():
            logger.warning(f"Strategy schema not found: {self.schema_path}")
            return None

        try:
            with open(self.schema_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load schema: {e}")
            return None

    def parse(self, user_input: str) -> dict[str, Any]:
        """
        Parse natural language strategy description into JSON configuration.

        Args:
            user_input: User's natural language strategy description

        Returns:
            Structured strategy configuration dict

        Raises:
            ValueError: If parsing or validation fails
        """
        if not self.client.is_available():
            raise ValueError("DeepSeek API is not configured. Please set DEEPSEEK_API_KEY.")

        # Get system prompt from template
        system_prompt = self.prompt_manager.get_prompt("strategy_parser", "system")

        if not system_prompt:
            # Fallback to basic prompt
            system_prompt = self._get_fallback_prompt()

        logger.info(f"Parsing strategy: {user_input[:100]}...")

        try:
            # Call DeepSeek API with JSON mode
            config = self.client.chat_json(
                user_message=user_input,
                system_message=system_prompt
            )

            logger.info(f"Parsed strategy: {config.get('strategy_name', 'unnamed')}")

            return config

        except Exception as e:
            logger.error(f"Strategy parsing failed: {e}")
            raise ValueError(f"Failed to parse strategy: {e}")

    def validate(self, config: dict) -> tuple[bool, list[str]]:
        """
        Validate strategy configuration against JSON schema.

        Args:
            config: Strategy configuration dict to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        if self.schema is None:
            logger.warning("Schema not loaded, skipping validation")
            return True, []

        errors = []

        try:
            validate(instance=config, schema=self.schema)
            return True, []

        except ValidationError as e:
            error_path = " -> ".join(str(p) for p in e.absolute_path)
            error_msg = f"{error_path}: {e.message}" if error_path else e.message
            errors.append(error_msg)
            logger.warning(f"Validation error: {error_msg}")
            return False, errors

    def parse_and_validate(self, user_input: str) -> tuple[dict | None, list[str]]:
        """
        Parse and validate strategy in one step.

        Args:
            user_input: Natural language strategy description

        Returns:
            Tuple of (config or None, error_messages)
        """
        try:
            config = self.parse(user_input)
            is_valid, errors = self.validate(config)

            if is_valid:
                return config, []
            else:
                return None, errors

        except ValueError as e:
            return None, [str(e)]

    def _get_fallback_prompt(self) -> str:
        """Get fallback system prompt if template is not available."""
        return """你是一个专业的量化策略解析器。将用户的自然语言策略描述转换为JSON配置。

输出JSON格式：
{
  "strategy_name": "策略名称",
  "universe": {"type": "index_component", "index": "000300.SSE"},
  "entry_rules": {"conditions": [{"indicator": "RSI", "params": {"period": 14}, "operator": "<", "value": 30}]},
  "exit_rules": {"take_profit": 0.1, "stop_loss": 0.05},
  "risk_control": {"max_positions": 30, "position_size": 0.03}
}

注意：
1. 百分比转为小数（5% = 0.05）
2. 使用合理的默认值填充未指定的参数
3. strategy_name使用小写字母和下划线"""
