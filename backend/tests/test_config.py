import os
import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "CHANGE-ME-use-a-local-secret-of-at-least-32-characters",
        "too-short",
    ],
)
def test_production_refuses_missing_or_weak_jwt_secret(secret):
    environment = os.environ.copy()
    environment["APP_ENV"] = "production"
    environment["JWT_SECRET"] = secret

    result = subprocess.run(
        [sys.executable, "-c", "from app.config import settings"],
        cwd=BACKEND_DIRECTORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "APP_ENV=production exige un JWT_SECRET" in result.stderr


def test_development_allows_placeholder_jwt_secret():
    environment = os.environ.copy()
    environment["APP_ENV"] = "development"
    environment["JWT_SECRET"] = "CHANGE-ME"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.config import settings; assert settings.app_env == 'development'",
        ],
        cwd=BACKEND_DIRECTORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_production_accepts_a_configured_secret():
    environment = os.environ.copy()
    environment["APP_ENV"] = "production"
    environment["JWT_SECRET"] = "a-valid-local-secret-with-at-least-32-chars"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.config import settings; assert settings.app_env == 'production'",
        ],
        cwd=BACKEND_DIRECTORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
