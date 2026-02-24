"""テスト用LLM API呼び出し。"""

from typing import Any

import anthropic

from mcp_gauge.exceptions import LLMAPIError


class LLMClient:
    """Anthropic APIを使用したLLMクライアント。"""

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> anthropic.types.Message:
        """LLMにメッセージを送信する。"""
        try:
            return self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                tools=tools,  # type: ignore[arg-type]
            )
        except anthropic.APIError as e:
            raise LLMAPIError(str(e), cause=e) from e

    def chat_with_history(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> anthropic.types.Message:
        """会話履歴付きでLLMにメッセージを送信する。"""
        try:
            return self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,  # type: ignore[arg-type]
                tools=tools,  # type: ignore[arg-type]
            )
        except anthropic.APIError as e:
            raise LLMAPIError(str(e), cause=e) from e
