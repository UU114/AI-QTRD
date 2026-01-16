"""
Prompt Template Manager.
提示词模板管理器

Loads and manages prompt templates from YAML configuration.
"""

from pathlib import Path
import yaml
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("prompt_manager")


class PromptManager:
    """
    Manages prompt templates for DeepSeek API calls.
    从YAML配置文件加载和管理提示词模板
    """

    def __init__(self, config_path: str | Path | None = None):
        """
        Initialize prompt manager.

        Args:
            config_path: Path to prompts YAML file, defaults to config/deepseek_prompts.yaml
        """
        if config_path is None:
            # Default path relative to project root
            config_path = Path(__file__).parent.parent.parent / "config" / "deepseek_prompts.yaml"

        self.config_path = Path(config_path)
        self.prompts: dict[str, Any] = {}

        self._load_prompts()

    def _load_prompts(self) -> None:
        """Load prompts from YAML configuration file."""
        if not self.config_path.exists():
            logger.warning(f"Prompts config file not found: {self.config_path}")
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.prompts = yaml.safe_load(f) or {}
            logger.info(f"Loaded {len(self.prompts)} prompt templates")
        except Exception as e:
            logger.error(f"Failed to load prompts config: {e}")
            self.prompts = {}

    def get_prompt(self, name: str, prompt_type: str = "system") -> str:
        """
        Get a prompt template by name.

        Args:
            name: Prompt template name (e.g., "strategy_parser", "news_analyzer")
            prompt_type: Type of prompt ("system", "user", "examples")

        Returns:
            Prompt template string
        """
        if name not in self.prompts:
            logger.warning(f"Prompt template not found: {name}")
            return ""

        template = self.prompts[name]

        if isinstance(template, str):
            return template

        if isinstance(template, dict):
            return template.get(prompt_type, "")

        return ""

    def get_examples(self, name: str) -> list[dict]:
        """
        Get example input/output pairs for a prompt.

        Args:
            name: Prompt template name

        Returns:
            List of example dicts with "input" and "output" keys
        """
        if name not in self.prompts:
            return []

        template = self.prompts[name]

        if isinstance(template, dict) and "examples" in template:
            return template["examples"]

        return []

    def format_prompt(self, name: str, prompt_type: str = "system", **kwargs) -> str:
        """
        Get and format a prompt template with variables.

        Args:
            name: Prompt template name
            prompt_type: Type of prompt
            **kwargs: Variables to substitute in the template

        Returns:
            Formatted prompt string
        """
        template = self.get_prompt(name, prompt_type)

        if not template:
            return ""

        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")
            return template

    def reload(self) -> None:
        """Reload prompts from configuration file."""
        self._load_prompts()
