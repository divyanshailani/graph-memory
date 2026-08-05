import json
import os
import re
from graph_memory.core.snapshot import generate_active_snapshot
from graph_memory.core import engine

HOME = os.path.expanduser("~")

def get_db_path():
    return engine.get_db_path()

# ---------------------------------------------------------------------------
# 1. Antigravity Hook
# ---------------------------------------------------------------------------
ANTIGRAVITY_SKILL_DIR = os.path.join(HOME, ".gemini", "config", "skills", "graph_memory")
ANTIGRAVITY_AUTO_FILE = os.path.join(ANTIGRAVITY_SKILL_DIR, "AUTO_MEMORY.md")

def install_antigravity_hook(db_path=None):
    os.makedirs(ANTIGRAVITY_SKILL_DIR, exist_ok=True)
    actual_db = db_path or get_db_path()
    snapshot = generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)
    
    content = f"""---
name: graph-memory-auto
description: Auto-injected Epistemic Graph Memory snapshot for Antigravity sessions.
---

# Auto-Injected Epistemic Memory Snapshot

{snapshot}

> [!NOTE]
> This snapshot is automatically updated by `graph-memory hook install` to provide ground-truth memory recall without manual user reminders.
"""
    with open(ANTIGRAVITY_AUTO_FILE, "w") as f:
        f.write(content)
    return True, f"Installed Antigravity auto-memory snapshot to {ANTIGRAVITY_AUTO_FILE}"

def uninstall_antigravity_hook():
    if os.path.exists(ANTIGRAVITY_AUTO_FILE):
        os.remove(ANTIGRAVITY_AUTO_FILE)
        return True, f"Removed {ANTIGRAVITY_AUTO_FILE}"
    return False, "Antigravity hook was not installed."

# ---------------------------------------------------------------------------
# 2. Claude Code CLI Hook
# ---------------------------------------------------------------------------
CLAUDE_SKILL_DIR = os.path.join(HOME, ".claude", "skills")
CLAUDE_AUTO_FILE = os.path.join(CLAUDE_SKILL_DIR, "graph-memory-auto.md")

def install_claude_code_hook(db_path=None):
    os.makedirs(CLAUDE_SKILL_DIR, exist_ok=True)
    actual_db = db_path or get_db_path()
    snapshot = generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)

    content = f"""# Epistemic Graph Memory Auto-Context

{snapshot}

> Auto-injected by `graph-memory hook install --framework claude-code`.
"""
    with open(CLAUDE_AUTO_FILE, "w") as f:
        f.write(content)
    return True, f"Installed Claude Code auto-memory snapshot to {CLAUDE_AUTO_FILE}"

def uninstall_claude_code_hook():
    if os.path.exists(CLAUDE_AUTO_FILE):
        os.remove(CLAUDE_AUTO_FILE)
        return True, f"Removed {CLAUDE_AUTO_FILE}"
    return False, "Claude Code hook was not installed."

# ---------------------------------------------------------------------------
# 3. Claude Desktop Hook
# ---------------------------------------------------------------------------
CLAUDE_DESKTOP_CONFIG = os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")

def install_claude_desktop_hook(db_path=None):
    if not os.path.exists(CLAUDE_DESKTOP_CONFIG):
        return False, "Claude Desktop configuration file not found."

    with open(CLAUDE_DESKTOP_CONFIG, "r") as f:
        config = json.load(f)

    mcp_servers = config.get("mcpServers", {})
    if "graph_memory" in mcp_servers:
        env = mcp_servers["graph_memory"].get("env", {})
        env["GRAPH_MEMORY_AUTO_SNAPSHOT"] = "1"
        mcp_servers["graph_memory"]["env"] = env
        config["mcpServers"] = mcp_servers
        with open(CLAUDE_DESKTOP_CONFIG, "w") as f:
            json.dump(config, f, indent=2)
        return True, "Updated Claude Desktop config with GRAPH_MEMORY_AUTO_SNAPSHOT=1 env flag."
    return False, "graph_memory MCP server is not present in claude_desktop_config.json."

def uninstall_claude_desktop_hook():
    if not os.path.exists(CLAUDE_DESKTOP_CONFIG):
        return False, "Claude Desktop configuration file not found."

    with open(CLAUDE_DESKTOP_CONFIG, "r") as f:
        config = json.load(f)

    mcp_servers = config.get("mcpServers", {})
    if "graph_memory" in mcp_servers and "env" in mcp_servers["graph_memory"]:
        mcp_servers["graph_memory"]["env"].pop("GRAPH_MEMORY_AUTO_SNAPSHOT", None)
        with open(CLAUDE_DESKTOP_CONFIG, "w") as f:
            json.dump(config, f, indent=2)
        return True, "Removed GRAPH_MEMORY_AUTO_SNAPSHOT env flag from Claude Desktop config."
    return False, "Claude Desktop hook was not enabled."

# ---------------------------------------------------------------------------
# 4. Codex Hook
# ---------------------------------------------------------------------------
CODEX_RULES_DIR = os.path.join(HOME, ".codex", "rules")
CODEX_AUTO_FILE = os.path.join(CODEX_RULES_DIR, "graph_memory_auto.md")

def install_codex_hook(db_path=None):
    os.makedirs(CODEX_RULES_DIR, exist_ok=True)
    actual_db = db_path or get_db_path()
    snapshot = generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)

    content = f"""# Codex Active Graph Memory Snapshot Rule

{snapshot}

> Auto-injected rule for Codex sessions.
"""
    with open(CODEX_AUTO_FILE, "w") as f:
        f.write(content)
    return True, f"Installed Codex auto-memory rule to {CODEX_AUTO_FILE}"

def uninstall_codex_hook():
    if os.path.exists(CODEX_AUTO_FILE):
        os.remove(CODEX_AUTO_FILE)
        return True, f"Removed {CODEX_AUTO_FILE}"
    return False, "Codex hook was not installed."

# ---------------------------------------------------------------------------
# 5. Hermes Hook
# ---------------------------------------------------------------------------
HERMES_MEMORIES_DIR = os.path.join(HOME, ".hermes", "memories")
HERMES_MEMORY_FILE = os.path.join(HERMES_MEMORIES_DIR, "MEMORY.md")

def install_hermes_hook(db_path=None):
    os.makedirs(HERMES_MEMORIES_DIR, exist_ok=True)
    actual_db = db_path or get_db_path()
    snapshot = generate_active_snapshot(actual_db, max_tokens=400, min_trust=0.7)

    existing_content = ""
    if os.path.exists(HERMES_MEMORY_FILE):
        with open(HERMES_MEMORY_FILE, "r") as f:
            existing_content = f.read()

    # Strip old § Epistemic Graph Memory section if present
    clean_existing = re.sub(r'§\s*# Epistemic Graph Memory.*?(?=(§|$))', '', existing_content, flags=re.DOTALL).strip()
    
    new_section = f"\n§\n# Epistemic Graph Memory Auto-Sync\n{snapshot}\n"
    final_content = (clean_existing + new_section).strip()

    with open(HERMES_MEMORY_FILE, "w") as f:
        f.write(final_content)
    return True, f"Synced Graph Memory active snapshot into Hermes {HERMES_MEMORY_FILE}"

def uninstall_hermes_hook():
    if os.path.exists(HERMES_MEMORY_FILE):
        with open(HERMES_MEMORY_FILE, "r") as f:
            content = f.read()
        clean = re.sub(r'§\s*# Epistemic Graph Memory.*?(?=(§|$))', '', content, flags=re.DOTALL).strip()
        with open(HERMES_MEMORY_FILE, "w") as f:
            f.write(clean)
        return True, f"Cleaned Graph Memory section from Hermes {HERMES_MEMORY_FILE}"
    return False, "Hermes MEMORY.md does not exist."

# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
FRAMEWORKS = {
    "antigravity": (install_antigravity_hook, uninstall_antigravity_hook, ANTIGRAVITY_AUTO_FILE),
    "claude-code": (install_claude_code_hook, uninstall_claude_code_hook, CLAUDE_AUTO_FILE),
    "claude-desktop": (install_claude_desktop_hook, uninstall_claude_desktop_hook, CLAUDE_DESKTOP_CONFIG),
    "codex": (install_codex_hook, uninstall_codex_hook, CODEX_AUTO_FILE),
    "hermes": (install_hermes_hook, uninstall_hermes_hook, HERMES_MEMORY_FILE),
}

def install_hooks(target_framework="all", db_path=None):
    results = []
    targets = FRAMEWORKS.keys() if target_framework == "all" else [target_framework]
    for fw in targets:
        if fw in FRAMEWORKS:
            installer = FRAMEWORKS[fw][0]
            ok, msg = installer(db_path)
            results.append({"framework": fw, "status": "installed" if ok else "failed", "message": msg})
    return results

def uninstall_hooks(target_framework="all"):
    results = []
    targets = FRAMEWORKS.keys() if target_framework == "all" else [target_framework]
    for fw in targets:
        if fw in FRAMEWORKS:
            uninstaller = FRAMEWORKS[fw][1]
            ok, msg = uninstaller()
            results.append({"framework": fw, "status": "uninstalled" if ok else "skipped", "message": msg})
    return results

def get_hook_status():
    status = []
    for fw, (_, _, path) in FRAMEWORKS.items():
        installed = os.path.exists(path)
        status.append({"framework": fw, "installed": installed, "path": path})
    return status
