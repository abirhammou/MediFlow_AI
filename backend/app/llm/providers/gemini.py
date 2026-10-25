"""
Provider Google Gemini — utilise l'API REST native de Gemini
(generateContent) avec instruction JSON forcée dans le prompt.
Compatible avec gemini-2.0-flash, gemini-1.5-flash, gemini-1.5-pro.
"""
from __future__ import annotations

import json
import re

import httpx

from app.errors import LLMRateLimitError, LLMResponseError, LLMTimeoutError
from app.llm.providers.base import BaseProvider


def _extract_json(text: str) -> str:
    """Extrait le premier objet JSON valide d'une réponse texte."""
    # Cas 1 : la réponse est déjà du JSON pur
    stripped = text.strip()
    if stripped.startswith("{"):
        return stripped

    # Cas 2 : JSON dans un bloc ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if match:
        return match.group(1)

    # Cas 3 : JSON quelque part dans le texte
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        return match.group(0)

    raise LLMResponseError()


class GeminiProvider(BaseProvider):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def complete_json(
        self,
        system: str,
        user: str,
        model: str,
        timeout: float,
    ) -> str:
        # L'API Gemini attend le nom sans préfixe "models/"
        model_name = model.removeprefix("models/")
        url = f"{self.BASE_URL}/{model_name}:generateContent?key={self.api_key}"

        # Gemini n'a pas de "system role" séparé — on l'injecte dans le user prompt
        full_prompt = f"{system}\n\n{user}"

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": full_prompt}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.3,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError() from exc
        except httpx.RequestError as exc:
            raise LLMResponseError() from exc

        if response.status_code == 429:
            raise LLMRateLimitError()
        if response.is_error:
            raise LLMResponseError()

        try:
            content = response.json()
            text = content["candidates"][0]["content"]["parts"][0]["text"]
            return _extract_json(text)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError() from exc
