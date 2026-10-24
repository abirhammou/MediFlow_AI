import httpx

from app.errors import LLMRateLimitError, LLMResponseError, LLMTimeoutError
from app.llm.providers.base import BaseProvider


class AnthropicProvider(BaseProvider):
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def complete_json(
        self,
        system: str,
        user: str,
        model: str,
        timeout: float,
    ) -> str:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": model,
                        "max_tokens": 2048,
                        "system": system,
                        "messages": [{"role": "user", "content": user}],
                    },
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError() from exc
        except httpx.RequestError as exc:
            raise LLMResponseError() from exc

        if response.status_code == 429:
            raise LLMRateLimitError()
        if response.is_error:
            raise LLMResponseError()
        try:
            content = response.json()["content"]
            return "".join(
                block["text"] for block in content if block.get("type") == "text"
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMResponseError() from exc
