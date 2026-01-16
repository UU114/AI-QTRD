"""
DeepSeek API Client Wrapper.
DeepSeek API客户端封装

Provides a unified interface for interacting with DeepSeek LLM API.
"""

import os
import json
from typing import Any
from openai import OpenAI

from ..utils.logger import get_logger

logger = get_logger("deepseek_client")


class DeepSeekClient:
    """
    DeepSeek API client wrapper.
    Handles API calls, retries, and response parsing.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        timeout: int = 30,
        retry_count: int = 3
    ):
        """
        Initialize DeepSeek client.

        Args:
            api_key: DeepSeek API key, defaults to DEEPSEEK_API_KEY env var
            base_url: API base URL
            model: Model name to use
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (lower = more deterministic)
            timeout: Request timeout in seconds
            retry_count: Number of retries on failure
        """
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        if not self.api_key:
            logger.warning("DeepSeek API key not set. Set DEEPSEEK_API_KEY environment variable.")

        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.retry_count = retry_count

        # Initialize OpenAI-compatible client
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout
        )

        logger.info(f"DeepSeek client initialized with model: {self.model}")

    def chat(
        self,
        user_message: str,
        system_message: str | None = None,
        json_mode: bool = False,
        **kwargs
    ) -> str:
        """
        Send a chat message and get response.

        Args:
            user_message: User's input message
            system_message: Optional system prompt
            json_mode: If True, request JSON output format
            **kwargs: Additional parameters for the API call

        Returns:
            Response content as string
        """
        messages = []

        if system_message:
            messages.append({"role": "system", "content": system_message})

        messages.append({"role": "user", "content": user_message})

        # Prepare request parameters
        request_params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
        }

        if json_mode:
            request_params["response_format"] = {"type": "json_object"}

        # Execute with retry logic
        last_error = None
        for attempt in range(self.retry_count):
            try:
                response = self.client.chat.completions.create(**request_params)
                content = response.choices[0].message.content
                logger.debug(f"DeepSeek response received, length: {len(content)}")
                return content

            except Exception as e:
                last_error = e
                logger.warning(f"DeepSeek API call failed (attempt {attempt + 1}/{self.retry_count}): {e}")

        logger.error(f"DeepSeek API call failed after {self.retry_count} attempts")
        raise last_error

    def chat_json(
        self,
        user_message: str,
        system_message: str | None = None,
        **kwargs
    ) -> dict[str, Any]:
        """
        Send a chat message and get JSON response.

        Args:
            user_message: User's input message
            system_message: Optional system prompt
            **kwargs: Additional parameters

        Returns:
            Parsed JSON response as dict
        """
        response = self.chat(
            user_message=user_message,
            system_message=system_message,
            json_mode=True,
            **kwargs
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response}")
            raise ValueError(f"Invalid JSON response from DeepSeek: {e}")

    def is_available(self) -> bool:
        """
        Check if the DeepSeek API is available and configured.

        Returns:
            True if API key is set and client is ready
        """
        return bool(self.api_key)
