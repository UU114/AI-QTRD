"""
Real-time News Sentiment Analyzer.
实时新闻情感分析器

Analyzes news and announcements using DeepSeek LLM for sentiment scoring.
"""

from typing import Any
from dataclasses import dataclass
from datetime import datetime

from .deepseek_client import DeepSeekClient
from .prompt_manager import PromptManager
from ..utils.logger import get_logger

logger = get_logger("news_analyzer")


@dataclass
class NewsSentiment:
    """News sentiment analysis result."""
    symbol: str
    sentiment: str          # positive / negative / neutral
    score: float            # 0.0 - 1.0 (1.0 = very positive)
    confidence: float       # 0.0 - 1.0
    key_factors: list[str]
    summary: str
    analyzed_at: datetime


class NewsAnalyzer:
    """
    Analyzes financial news and announcements for sentiment.
    Uses DeepSeek LLM for real-time analysis.
    """

    def __init__(
        self,
        deepseek_client: DeepSeekClient | None = None,
        prompt_manager: PromptManager | None = None,
        cache_ttl: int = 300  # Cache TTL in seconds
    ):
        """
        Initialize news analyzer.

        Args:
            deepseek_client: DeepSeek API client
            prompt_manager: Prompt template manager
            cache_ttl: Cache time-to-live in seconds
        """
        self.client = deepseek_client or DeepSeekClient()
        self.prompt_manager = prompt_manager or PromptManager()
        self.cache_ttl = cache_ttl

        # Simple in-memory cache
        self._cache: dict[str, tuple[NewsSentiment, datetime]] = {}

    def analyze(self, symbol: str, news_content: str) -> NewsSentiment:
        """
        Analyze a single news item for sentiment.

        Args:
            symbol: Stock symbol the news relates to
            news_content: News content to analyze

        Returns:
            NewsSentiment analysis result
        """
        if not self.client.is_available():
            logger.warning("DeepSeek not available, returning neutral sentiment")
            return self._neutral_sentiment(symbol)

        # Check cache
        cache_key = f"{symbol}:{hash(news_content)}"
        if cache_key in self._cache:
            sentiment, cached_at = self._cache[cache_key]
            if (datetime.now() - cached_at).seconds < self.cache_ttl:
                return sentiment

        # Get system prompt
        system_prompt = self.prompt_manager.get_prompt("news_analyzer", "system")
        if not system_prompt:
            system_prompt = self._get_fallback_prompt()

        try:
            user_message = f"股票代码: {symbol}\n\n新闻内容:\n{news_content}"

            result = self.client.chat_json(
                user_message=user_message,
                system_message=system_prompt
            )

            sentiment = NewsSentiment(
                symbol=symbol,
                sentiment=result.get("sentiment", "neutral"),
                score=float(result.get("score", 0.5)),
                confidence=float(result.get("confidence", 0.5)),
                key_factors=result.get("key_factors", []),
                summary=result.get("summary", ""),
                analyzed_at=datetime.now()
            )

            # Cache result
            self._cache[cache_key] = (sentiment, datetime.now())

            return sentiment

        except Exception as e:
            logger.error(f"News analysis failed: {e}")
            return self._neutral_sentiment(symbol)

    def analyze_batch(
        self,
        symbols: list[str],
        news_data: dict[str, list[str]] | None = None
    ) -> dict[str, float]:
        """
        Analyze news for multiple symbols and return sentiment scores.

        Args:
            symbols: List of stock symbols
            news_data: Dict mapping symbols to list of news items

        Returns:
            Dict mapping symbols to sentiment scores (0.0 - 1.0)
        """
        scores = {}

        for symbol in symbols:
            if news_data and symbol in news_data:
                news_list = news_data[symbol]
                if news_list:
                    # Analyze most recent news
                    sentiment = self.analyze(symbol, news_list[0])
                    scores[symbol] = sentiment.score
                else:
                    scores[symbol] = 0.5  # Neutral
            else:
                scores[symbol] = 0.5  # No news = neutral

        return scores

    def _neutral_sentiment(self, symbol: str) -> NewsSentiment:
        """Return a neutral sentiment result."""
        return NewsSentiment(
            symbol=symbol,
            sentiment="neutral",
            score=0.5,
            confidence=0.0,
            key_factors=[],
            summary="No analysis available",
            analyzed_at=datetime.now()
        )

    def _get_fallback_prompt(self) -> str:
        """Get fallback system prompt."""
        return """你是金融新闻分析师。分析新闻对股票的影响。

返回JSON格式：
{
  "sentiment": "positive/negative/neutral",
  "score": 0.0-1.0,
  "confidence": 0.0-1.0,
  "key_factors": ["因素1", "因素2"],
  "summary": "一句话总结"
}"""

    def clear_cache(self) -> None:
        """Clear the sentiment cache."""
        self._cache.clear()
        logger.info("News sentiment cache cleared")
