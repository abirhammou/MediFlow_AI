import httpx

from app.errors import LLMRateLimitError, LLMResponseError, LLMTimeoutError
from app.llm.providers.base import BaseProvider


def _error_detail(response: httpx.Response, api_key: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    message = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
        elif isinstance(error, str):
            message = error

    if not isinstance(message, str) or not message.strip():
        return f"Groq a répondu avec le code HTTP {response.status_code}."

    safe_message = message.replace(api_key, "[clé masquée]").strip()
    if len(safe_message) > 500:
        safe_message = f"{safe_message[:497]}..."
    return f"Groq a répondu avec le code HTTP {response.status_code} : {safe_message}"


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
            raise LLMResponseError(
                f"Connexion au fournisseur LLM impossible ({type(exc).__name__})."
            ) from exc

        if response.status_code == 429:
            raise LLMRateLimitError(_error_detail(response, self.api_key))
        if response.is_error:
            raise LLMResponseError(_error_detail(response, self.api_key))
        try:
            return response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError() from exc
