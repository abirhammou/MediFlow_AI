import argparse
import re
import shutil
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME_PATTERN = re.compile(r"^[a-z]+(?:_[a-z]+)*$")
ENV_SUFFIXES = ("PROVIDER", "BASE_URL", "MODEL", "API_KEY")
TEMPLATE_CLASS_NAMES = (
    "NoteSummaryRequest",
    "NoteRepository",
    "NoteService",
    "NoteSummary",
    "NoteCreate",
    "NoteUpdate",
    "NoteOut",
)


def _replace_template_names(source: str, module_name: str) -> str:
    class_name = "".join(part.capitalize() for part in module_name.split("_"))
    for template_name in TEMPLATE_CLASS_NAMES:
        source = source.replace(template_name, template_name.replace("Note", class_name, 1))
    source = re.sub(r"(?<![A-Za-z])notes?(?![A-Za-z])", module_name, source)
    source = re.sub(r"(?<![A-Za-z])Notes?(?![A-Za-z])", class_name, source)
    source = source.replace("app.modules._template", f"app.modules.{module_name}")
    source = source.replace('module="template"', f'module="{module_name}"')
    return source


def _ensure_env_variables(path: Path, module_name: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    existing_names = {
        match.group(1)
        for line in existing.splitlines()
        if (match := re.match(r"^\s*([A-Z][A-Z0-9_]*)\s*=", line))
    }
    prefix = module_name.upper()
    missing = [
        suffix
        for suffix in ENV_SUFFIXES
        if f"{prefix}_LLM_{suffix}" not in existing_names
    ]
    if not missing:
        return

    addition = ["", "# Responsable : à compléter"]
    for suffix in missing:
        value = "mock" if suffix == "PROVIDER" else ""
        addition.append(f"{prefix}_LLM_{suffix}={value}")
    updated = existing.rstrip() + "\n" + "\n".join(addition) + "\n"
    path.write_text(updated, encoding="utf-8")


def create_module(module_name: str, backend_root: Path = BACKEND_ROOT) -> Path:
    if not MODULE_NAME_PATTERN.fullmatch(module_name):
        raise ValueError("Le nom doit être en minuscules, avec des lettres et underscores.")

    module_directory = backend_root / "app" / "modules" / module_name
    test_file = backend_root / "tests" / f"test_{module_name}.py"
    if module_directory.exists():
        raise FileExistsError(f"Le module existe déjà : {module_directory}")
    if test_file.exists():
        raise FileExistsError(f"Le fichier de test existe déjà : {test_file}")

    template_directory = backend_root / "app" / "modules" / "_template"
    if not template_directory.is_dir():
        raise FileNotFoundError(f"Le modèle de module est introuvable : {template_directory}")

    module_directory.parent.mkdir(parents=True, exist_ok=True)
    test_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        template_directory,
        module_directory,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for source_path in module_directory.rglob("*.py"):
        content = source_path.read_text(encoding="utf-8")
        source_path.write_text(_replace_template_names(content, module_name), encoding="utf-8")

    template_test = backend_root / "tests" / "test_template.py"
    test_content = _replace_template_names(
        template_test.read_text(encoding="utf-8"),
        module_name,
    )
    test_file.write_text(test_content, encoding="utf-8")
    _ensure_env_variables(backend_root / ".env.example", module_name)
    _ensure_env_variables(backend_root / ".env", module_name)
    return module_directory


def main() -> None:
    parser = argparse.ArgumentParser(description="Créer un module API depuis _template.")
    parser.add_argument("nom", help="Nom du module en minuscules")
    args = parser.parse_args()
    try:
        module_directory = create_module(args.nom)
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Module créé : {module_directory}")


if __name__ == "__main__":
    main()
