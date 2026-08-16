"""
v3.4.0 regression tests: project-scoped node identity.

Guards against two collision classes caused by the legacy basename-only ID
scheme (File_{name}, Func_{name}_{filename}, MOC_{dirname}):
1. Identical basenames in different directories of one repo (two utils.py).
2. Identical relative paths in different projects sharing one database.
Also guards against junk External_Dependency nodes from relative imports
(`from . import x`, `from ...pkg import y`, JS `./module`).
"""
import json
from pathlib import Path
from graph_memory.core import engine, ingest

UTILS_CODE = '''import os

def load():
    """Loads things."""
    return os.path.getcwd()
'''


def _make_project(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    for sub in ("a", "b"):
        (root / sub).mkdir(exist_ok=True)
        (root / sub / "utils.py").write_text(UTILS_CODE, encoding="utf-8")


def _node_exists(db_path: str, node_id: str) -> bool:
    with engine.get_connection(db_path) as conn:
        return conn.execute(
            "SELECT 1 FROM Nodes WHERE id = ? AND is_deleted = 0", (node_id,)
        ).fetchone() is not None


def test_same_filename_different_dirs_no_collision(tmp_path):
    project = tmp_path / "repoA"
    _make_project(project)
    db_path = str(tmp_path / "test.sqlite")

    ingest.ingest_codebase(db_path, str(project))

    ns = ingest.project_namespace(project)
    assert _node_exists(db_path, f"File_{ns}/a/utils.py")
    assert _node_exists(db_path, f"File_{ns}/b/utils.py")
    # Both load() functions must exist as distinct nodes instead of silently merging.
    assert _node_exists(db_path, f"Func_load_{ns}/a/utils.py")
    assert _node_exists(db_path, f"Func_load_{ns}/b/utils.py")
    assert f"Func_load_{ns}/a/utils.py" != f"Func_load_{ns}/b/utils.py"


def test_cross_project_same_relpath_no_collision(tmp_path):
    project_a = tmp_path / "repoA"
    project_b = tmp_path / "repoB"
    _make_project(project_a)
    _make_project(project_b)
    db_path = str(tmp_path / "test.sqlite")

    ingest.ingest_codebase(db_path, str(project_a))
    ingest.ingest_codebase(db_path, str(project_b))

    ns_a = ingest.project_namespace(project_a)
    ns_b = ingest.project_namespace(project_b)
    assert ns_a != ns_b
    assert _node_exists(db_path, f"File_{ns_a}/a/utils.py")
    assert _node_exists(db_path, f"File_{ns_b}/a/utils.py")


def test_ingest_file_matches_codebase_identity(tmp_path):
    project = tmp_path / "repoA"
    _make_project(project)
    db_path = str(tmp_path / "test.sqlite")

    ingest.ingest_codebase(db_path, str(project))
    (project / "a" / "utils.py").write_text(
        UTILS_CODE + "\n\ndef extra():\n    pass\n", encoding="utf-8"
    )
    ingest.ingest_file(db_path, str(project / "a" / "utils.py"), agent_name="Hermes")

    ns = ingest.project_namespace(project)
    with engine.get_connection(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM Nodes WHERE id = ?",
            (f"File_{ns}/a/utils.py",),
        ).fetchone()[0]
    assert count == 1  # incremental ingest reuses the codebase node, no duplicate


def test_relative_imports_sanitized(tmp_path):
    project = tmp_path / "repoC"
    project.mkdir(parents=True, exist_ok=True)
    (project / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (project / "main.py").write_text(
        "from . import sibling\n"
        "from ...helpers import tool\n"
        "from .local import thing\n"
        "import os\n",
        encoding="utf-8",
    )
    db_path = str(tmp_path / "test.sqlite")

    ingest.ingest_codebase(db_path, str(project))

    ns = ingest.project_namespace(project)
    with engine.get_connection(db_path) as conn:
        deps = conn.execute(
            "SELECT id, properties FROM Nodes WHERE id LIKE 'Dependency_%' AND is_deleted = 0"
        ).fetchall()

    ids = [r[0] for r in deps]
    modules = [json.loads(r[1]).get("module", "") for r in deps]
    assert f"Dependency_{ns}/os" in ids
    assert f"Dependency_{ns}/helpers" in ids  # leading dots stripped, not junk
    assert f"Dependency_{ns}/local" in ids
    assert not any(m.startswith(".") for m in modules), modules
    assert not any(m in (".", "..", "") for m in modules), modules
    assert not any("sibling" in i for i in ids), ids  # `from . import x` yields no dependency node
