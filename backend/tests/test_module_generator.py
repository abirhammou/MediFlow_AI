import shutil

import pytest

from scripts.new_module import create_module


def make_backend_copy(tmp_path):
    backend = tmp_path / "backend"
    shutil.copytree(
        "app/modules/_template",
        backend / "app" / "modules" / "_template",
    )
    (backend / "tests").mkdir(parents=True)
    shutil.copy("tests/test_template.py", backend / "tests" / "test_template.py")
    (backend / ".env.example").write_text("LLM_MOCK=true\n", encoding="utf-8")
    (backend / ".env").write_text("LLM_MOCK=true\n", encoding="utf-8")
    return backend


def test_generator_copies_and_renames_module(tmp_path):
    backend = make_backend_copy(tmp_path)

    module_path = create_module("clinical_notes", backend)
    service = (module_path / "service.py").read_text(encoding="utf-8")
    repository = (module_path / "repository.py").read_text(encoding="utf-8")
    router = (module_path / "router.py").read_text(encoding="utf-8")
    generated_test = (backend / "tests" / "test_clinical_notes.py").read_text(
        encoding="utf-8"
    )

    assert "ClinicalNotesService" in service
    assert 'module="clinical_notes"' in service
    assert 'database["clinical_notes"]' in repository
    assert 'PREFIX = "/api/clinical_notes"' in router
    assert "/api/clinical_notes/" in generated_test
    for suffix in ("PROVIDER=mock", "BASE_URL=", "MODEL=", "API_KEY="):
        assert f"CLINICAL_NOTES_LLM_{suffix}" in (
            backend / ".env.example"
        ).read_text(encoding="utf-8")
        assert f"CLINICAL_NOTES_LLM_{suffix}" in (
            backend / ".env"
        ).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["Clinical", "name-1", "_private", "two__words", ""])
def test_generator_rejects_invalid_names(tmp_path, name):
    backend = make_backend_copy(tmp_path)

    with pytest.raises(ValueError):
        create_module(name, backend)


def test_generator_refuses_existing_module(tmp_path):
    backend = make_backend_copy(tmp_path)
    (backend / "app" / "modules" / "existing").mkdir()

    with pytest.raises(FileExistsError):
        create_module("existing", backend)
