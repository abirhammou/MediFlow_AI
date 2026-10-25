"""Checks the LLM keys: one tiny prompt to each configured model (LLM_MODEL, then the fallbacks).

Run from backend/:  .\\.venv\\Scripts\\python -m scripts.llm_smoke_test

Calls the real providers even when LLM_MOCK=true, writes nothing to MongoDB and
never prints a key. Exit code 1 if any model fails.
"""

import asyncio
import sys
import time

from app.core.config import settings
from app.llm.client import call_model, describe_error

PROMPT = [{"role": "user", "content": "Réponds uniquement par le mot : OK"}]


async def main() -> int:
    models = settings.llm_models
    if not models:
        print("Aucun modèle configuré (LLM_MODEL est vide).")
        return 1
    failures = 0
    for model in models:
        started = time.perf_counter()
        try:
            result = await call_model(model, PROMPT, max_tokens=200)
        except Exception as exc:
            failures += 1
            elapsed = round((time.perf_counter() - started) * 1000)
            print(f"ERREUR {model} ({elapsed} ms)\n       {describe_error(model, exc)[:500]}")
        else:
            print(f"OK     {model} ({result.latency_ms} ms) -> {result.text[:40]!r}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
