import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]


def import_settings(env: str, secret: str, check: str = "") -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment["ENV"] = env
    environment["JWT_SECRET"] = secret
    return subprocess.run(
        [sys.executable, "-c", f"from app.core.config import settings; {check}"],
        cwd=BACKEND_DIRECTORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "secret",
    ["", "CHANGE-ME-use-a-local-secret-of-at-least-32-characters", "too-short"],
)
def test_production_refuses_missing_or_weak_jwt_secret(secret):
    result = import_settings("prod", secret)

    assert result.returncode != 0
    assert "ENV=prod exige un JWT_SECRET" in result.stderr


def test_development_allows_placeholder_jwt_secret():
    result = import_settings("dev", "CHANGE-ME", "assert settings.env == 'dev'")

    assert result.returncode == 0, result.stderr


def test_production_accepts_a_configured_secret():
    result = import_settings(
        "prod", "a-valid-local-secret-with-at-least-32-chars", "assert settings.env == 'prod'"
    )

    assert result.returncode == 0, result.stderr
