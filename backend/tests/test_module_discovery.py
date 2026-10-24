import logging
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI

from app.config import Settings
from app.llm.registry import status
from app.modules import discovery


def test_discovery_skips_internal_modules_unless_enabled(tmp_path, monkeypatch):
    modules_path = tmp_path / "modules"
    (modules_path / "documents").mkdir(parents=True)
    (modules_path / "documents" / "router.py").touch()
    (modules_path / "_template").mkdir()
    (modules_path / "_template" / "router.py").touch()
    monkeypatch.setattr(discovery, "MODULES_DIRECTORY", modules_path)

    assert discovery.discover_module_names(Settings(expose_template=False)) == ["documents"]
    assert discovery.discover_module_names(Settings(expose_template=True)) == [
        "documents",
        "template",
    ]


def test_broken_router_does_not_block_other_modules(monkeypatch, caplog):
    router = APIRouter()

    @router.get("/")
    async def healthy_route():
        return {"status": "ok"}

    modules = [
        ("broken", None),
        ("healthy", None),
    ]

    def load_router(name):
        if name == "broken":
            raise ImportError("import échoué")
        return SimpleNamespace(router=router)

    monkeypatch.setattr(discovery, "iter_module_directories", lambda config: iter(modules))
    monkeypatch.setattr(discovery, "_load_router", load_router)
    app = FastAPI()

    with caplog.at_level(logging.WARNING):
        discovery.include_discovered_routers(app)

    assert "/api/healthy/" in set(app.openapi()["paths"].keys())
    assert "module broken" in caplog.text
    assert "import échoué" in caplog.text


def test_registry_uses_mock_for_unconfigured_module():
    assert status(["custom_module"]) == {
        "custom_module": {"provider": "mock", "key_configured": False}
    }


def test_registry_reads_arbitrary_module_environment(monkeypatch):
    monkeypatch.setenv("NEW_TEAM_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("NEW_TEAM_LLM_BASE_URL", "https://llm.example.test")
    monkeypatch.setenv("NEW_TEAM_LLM_MODEL", "configured-model")
    monkeypatch.setenv("NEW_TEAM_LLM_API_KEY", "test-key")

    configured = status(
        ["new_team"],
        Settings(llm_mock=False, environment="production"),
    )["new_team"]
    assert configured == {"provider": "openai_compatible", "key_configured": True}
