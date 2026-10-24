import httpx

from app.errors import LLMRateLimitError, LLMResponseError, LLMTimeoutError
from app.llm.providers.base import BaseProvider


class OpenAICompatibleProvider(BaseProvider):
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
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "response_format": {"type": "json_object"},
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
            return response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError() from exc
