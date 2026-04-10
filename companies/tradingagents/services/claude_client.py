"""
Anthropic Claude API wrapper for TradingAgents.
Handles retries, token tracking, and the 300-token input cap.
"""
import logging
from anthropic import Anthropic

import config

log = logging.getLogger("claude_client")

_client = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            log.warning("ANTHROPIC_API_KEY not set — Claude calls will fail")
        _client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def ask(system_prompt: str, user_message: str,
        max_input_tokens: int = None,
        max_output_tokens: int = 300) -> tuple[str, int]:
    """
    Send a message to Claude. Returns (response_text, tokens_used).
    Truncates user_message to max_input_tokens if set.
    """
    if max_input_tokens and len(user_message) > max_input_tokens * 4:
        # Rough char-to-token estimate: 4 chars per token
        user_message = user_message[:max_input_tokens * 4]
        log.debug("Truncated input to ~%d tokens", max_input_tokens)

    try:
        client = get_client()
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=max_output_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens
        log.info("Claude call: %d tokens (%d in + %d out)",
                 tokens, response.usage.input_tokens, response.usage.output_tokens)
        return text, tokens
    except Exception as e:
        log.error("Claude API error: %s", e)
        return "", 0
