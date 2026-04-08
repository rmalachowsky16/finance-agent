"""Singleton Anthropic client with retry logic for rate limits."""

import logging
from functools import lru_cache

import anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_claude_client() -> anthropic.Anthropic:
    """
    Return a module-level singleton Anthropic client.

    The client is constructed once and reused for the lifetime of the process.
    API key is read from settings (environment variable ANTHROPIC_API_KEY).
    """
    settings = get_settings()
    logger.info("Initialising Anthropic client")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


# ---------------------------------------------------------------------------
# Retry-decorated thin wrappers for direct use outside the summarizer
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type(anthropic.RateLimitError),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def create_message_with_retry(**kwargs) -> anthropic.types.Message:
    """
    Call ``client.messages.create`` with automatic exponential-backoff retry
    on rate-limit errors (HTTP 429).

    Pass the same kwargs you would pass to ``client.messages.create``.

    Example::

        response = create_message_with_retry(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello"}],
        )
    """
    client = get_claude_client()
    return client.messages.create(**kwargs)
