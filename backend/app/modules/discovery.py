import importlib
import logging
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

from fastapi import FastAPI
from fastapi.routing import APIRouter

from app.config import MODULES_DIRECTORY, Settings, settings


logger = logging.getLogger(__name__)


def iter_module_directories(
    config: Settings = settings,
) -> Iterator[tuple[str, Path]]:
    if not MODULES_DIRECTORY.exists():
        return
    for directory in sorted(
        MODULES_DIRECTORY.iterdir(),
        key=lambda item: module_llm_name(item.name),
    ):
        if not directory.is_dir() or not (directory / "router.py").is_file():
            continue
        if directory.name.startswith("_") and not (
            directory.name == "_template" and config.should_expose_template
        ):
            continue
        yield directory.name, directory


def module_llm_name(directory_name: str) -> str:
    return directory_name.removeprefix("_")


def discover_module_names(config: Settings = settings) -> list[str]:
    discovered: list[str] = []
    for name, _ in iter_module_directories(config):
        try:
            module = _load_router(name)
            if getattr(module, "LLM_ENABLED", True):
                discovered.append(module_llm_name(name))
        except Exception as exc:
            logger.warning("Lecture de la configuration LLM du module %s impossible : %s", name, exc)
    return discovered


def _load_router(module_name: str) -> ModuleType:
    return importlib.import_module(f"app.modules.{module_name}.router")


def include_discovered_routers(app: FastAPI, config: Settings = settings) -> None:
    for module_name, _ in iter_module_directories(config):
        try:
            module = _load_router(module_name)
            router = getattr(module, "router")
            if not isinstance(router, APIRouter):
                raise TypeError("l'attribut router doit être un APIRouter")

            prefix = getattr(module, "PREFIX", f"/api/{module_name}")
            tags = getattr(module, "TAGS", [module_name])
            if not isinstance(prefix, str) or not isinstance(tags, list):
                raise TypeError("PREFIX doit être une chaîne et TAGS une liste")
            app.include_router(router, prefix=prefix, tags=tags)
        except Exception as exc:
            logger.warning("Chargement du module %s impossible : %s", module_name, exc)
