"""
v3.9.0 regression tests: receiver-aware cross-file CALLS resolution.

The v3.7.0 resolver rewired stubs by unique name alone, which produced false
edges: np.dot() linked to any in-project `dot`, and `from json import loads;
loads()` linked to a project function named `loads`. v3.9.0 resolves through
the caller file's import bindings stored on File nodes:

1. External receiver (`np.dot`, `la.solve` via `import numpy.linalg as la`)
   rewires to synthetic Dependency member nodes, never to in-project defs.
2. Relative receiver (`from . import mod_a; mod_a.helper()`) resolves to the
   def inside the bound file (`method="receiver"`), including the
   import_prefix grammar nesting for the dot count.
3. Bare call with a relative binding (`from .helpers import fmt; fmt()`)
   resolves to the bound file's def (`method="relative_binding"`).
4. Bare call bound to an external module (`from json import loads; loads()`)
   wins over the unique-name rule (`method="external_binding"`).
5. Unbound receivers keep the legacy unique-name fallback.
6. Re-ingestion is idempotent (batch path now pre-sweeps CALLS edges).
"""
import json
import sqlite3
from pathlib import Path

import pytest

from graph_memory.core.ingest import ingest_codebase, project_namespace

TREE = {
    "pkg/__init__.py": "",
    "pkg/mod_a.py": "def helper(x):\n    return x\n",
    "pkg/helpers.py": "def fmt(v):\n    return str(v)\n",
    "pkg/dot.py": "def dot(a, b):\n    return a\n\n\ndef loads(s):\n    return s\n",
    "pkg/caller.py": (
        "import numpy as np\n"
        "import numpy.linalg as la\n"
        "from . import mod_a\n"
        "from .helpers import fmt\n"
        "from json import loads\n"
        "\n\n"
        "def use_everything(a, b):\n"
        "    np.dot(a, b)\n"
        "    la.solve(a, b)\n"
        "    mod_a.helper(a)\n"
        "    fmt(b)\n"
        "    loads(b)\n"
        "\n\n"
        "def unique_call():\n"
        "    helper_only_once()\n"
        "\n\n"
        "def helper_only_once():\n"
        "    return 1\n"
    ),
}


@pytest.fixture
def graph(tmp_path):
    root = tmp_path / "fixture"
    for rel, src in TREE.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src)
    db = str(tmp_path / "g.sqlite")
    ingest_codebase(db, str(root))
    return db, project_namespace(root)


def _calls(conn, ns, caller):
    rows = conn.execute(
        "SELECT target_id, properties FROM Edges WHERE relation_type='CALLS' AND source_id = ?",
        (f"Func_{caller}_{ns}/pkg/caller.py",),
    ).fetchall()
    return {t: json.loads(p or "{}").get("resolved_by") for t, p in rows}


def test_external_receiver_never_links_in_project(graph):
    db, ns = graph
    conn = sqlite3.connect(db)
    got = _calls(conn, ns, "use_everything")
    assert got.get(f"Dependency_{ns}/numpy.dot") == "receiver_external"
    assert got.get(f"Dependency_{ns}/numpy.linalg.solve") == "receiver_external"
    # The false-positive guard: nothing from use_everything may touch dot.py.
    assert not any("/pkg/dot.py" in t for t in got)


def test_relative_receiver_resolves_into_bound_file(graph):
    db, ns = graph
    conn = sqlite3.connect(db)
    got = _calls(conn, ns, "use_everything")
    assert got.get(f"Func_helper_{ns}/pkg/mod_a.py") == "receiver"


def test_bare_relative_binding_resolves(graph):
    db, ns = graph
    conn = sqlite3.connect(db)
    got = _calls(conn, ns, "use_everything")
    assert got.get(f"Func_fmt_{ns}/pkg/helpers.py") == "relative_binding"


def test_external_binding_beats_unique_name(graph):
    db, ns = graph
    conn = sqlite3.connect(db)
    got = _calls(conn, ns, "use_everything")
    assert got.get(f"Dependency_{ns}/json.loads") == "external_binding"
    assert f"Func_loads_{ns}/pkg/dot.py" not in got


def test_unbound_receiver_keeps_unique_name_fallback(graph):
    db, ns = graph
    conn = sqlite3.connect(db)
    got = _calls(conn, ns, "unique_call")
    assert got.get(f"Func_helper_only_once_{ns}/pkg/caller.py") in (None, "unique_name")


def test_reingest_is_idempotent(graph, tmp_path):
    db, ns = graph
    conn = sqlite3.connect(db)
    before = conn.execute("SELECT COUNT(*) FROM Edges WHERE relation_type='CALLS'").fetchone()[0]
    ingest_codebase(db, str(tmp_path / "fixture"))  # hash-skip path
    after = conn.execute("SELECT COUNT(*) FROM Edges WHERE relation_type='CALLS'").fetchone()[0]
    assert after == before


# --- v3.9.0 stable project identity -------------------------------------------

def test_namespace_survives_relocation(tmp_path):
    """With a committed .agents/project_id, moving/renaming the checkout keeps
    the namespace; without it, the path-hash fallback is unchanged."""
    from graph_memory.core.ingest import project_namespace

    src = tmp_path / "old-name"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "a.py").write_text("def f():\n    pass\n")
    ns1 = project_namespace(src)
    assert (src / ".agents" / "project_id").read_text().strip() == ns1

    dst = tmp_path / "new-name"
    src.rename(dst)
    assert project_namespace(dst) == ns1  # identity file carried the token over

    # Fresh repo without the file: legacy path-hash namespace, and the file is minted.
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    ns2 = project_namespace(fresh)
    assert ns2.startswith("fresh_")
    assert (fresh / ".agents" / "project_id").read_text().strip() == ns2
