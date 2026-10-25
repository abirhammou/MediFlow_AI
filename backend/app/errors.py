from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class APIError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(detail)


class LLMConfigurationError(APIError):
    def __init__(self, detail: str = "La clé LLM n'est pas configurée.") -> None:
        super().__init__(503, "llm_key_missing", detail)


class LLMTimeoutError(APIError):
    def __init__(self) -> None:
        super().__init__(504, "llm_timeout", "Le fournisseur LLM n'a pas répondu à temps.")


class LLMRateLimitError(APIError):
    def __init__(self) -> None:
        super().__init__(429, "llm_rate_limited", "Le quota du fournisseur LLM est dépassé.")


class LLMResponseError(APIError):
    def __init__(self) -> None:
        super().__init__(
            502, "llm_invalid_response", "Le fournisseur LLM a renvoyé une réponse invalide."
        )


class LlmUnavailableError(APIError):
    """Every configured model failed (timeout, quota, provider error, missing key)."""

    def __init__(self) -> None:
        super().__init__(
            503,
            "llm_unavailable",
            "Le service IA est momentanément indisponible, réessayez plus tard",
        )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def handle_api_error(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "code": "validation_error"},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": "http_error"},
            headers=exc.headers,
        )
