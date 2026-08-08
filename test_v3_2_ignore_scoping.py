from pathlib import Path
from graph_memory.core.ingest import should_ignore_path, ingest_file

def test_should_ignore_path_dependency_dirs():
    assert should_ignore_path(Path("venv/lib/python3.10/site-packages/torch/cuda.py")) is True
    assert should_ignore_path(Path(".venv/lib/site-packages/pytorch_internal.py")) is True
    assert should_ignore_path(Path("my_project/node_modules/express/index.js")) is True
    assert should_ignore_path(Path("my_project/dist/main.js")) is True
    assert should_ignore_path(Path("my_project/build/app.exe")) is True
    assert should_ignore_path(Path("my_project/__pycache__/utils.cpython-310.pyc")) is True
    assert should_ignore_path(Path("my_project/.git/config")) is True
    assert should_ignore_path(Path("my_project/env/lib/python3.14/site-packages/package.py")) is True

def test_should_ignore_path_project_files():
    assert should_ignore_path(Path("graph_memory/core/engine.py")) is False
    assert should_ignore_path(Path("src/utils/graph_helpers.ts")) is False
    assert should_ignore_path(Path("main.go")) is False
    assert should_ignore_path(Path("src/lib.rs")) is False

def test_ingest_file_ignores_third_party(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    venv_file = tmp_path / "venv" / "lib" / "python3.14" / "site-packages" / "third_party.py"
    venv_file.parent.mkdir(parents=True, exist_ok=True)
    venv_file.write_text("def third_party_func(): pass")

    res = ingest_file(db_path, str(venv_file))
    assert res["status"] == "ignored"
    assert "ignored directory" in res["message"]
