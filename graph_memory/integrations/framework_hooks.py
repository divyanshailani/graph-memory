import json
import os
import re
import sys
import shutil
import tempfile
from graph_memory.core.snapshot import generate_active_snapshot
from graph_memory.core import engine

HOME = os.path.expanduser("~")

def get_db_path():
    return engine.get_db_path()

# ---------------------------------------------------------------------------
# Cross-Platform Path Resolution (macOS, Windows, Linux)
# ---------------------------------------------------------------------------
def get_claude_desktop_config_path():
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", os.path.join(HOME, "AppData", "Roaming"))
        return os.path.join(appdata, "Claude", "claude_desktop_config.json")
    elif sys.platform == "darwin":
        return os.path.join(HOME, "Library", "Application Support", "Claude", "claude_desktop_config.json")
    else:  # linux and others
        config_home = os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config"))
        return os.path.join(config_home, "Claude", "claude_desktop_config.json")

def atomic_write_json(file_path, data):
    """Safely updates a JSON file with backup and atomic replace."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    if os.path.exists(file_path):
        backup_path = file_path + ".graphmemory.bak"
        shutil.copy2(file_path, backup_path)
    
    dir_name = os.path.dirname(file_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="gm_cfg_", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, file_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise e

# ---------------------------------------------------------------------------
# Framework Paths Definition
# ---------------------------------------------------------------------------
ANTIGRAVITY_SKILL_DIR = os.path.join(HOME, ".gemini", "config", "skills", "graph_memory")
ANTIGRAVITY_AUTO_FILE = os.path.join(ANTIGRAVITY_SKILL_DIR, "AUTO_MEMORY.md")

CLAUDE_SKILL_DIR = os.path.join(HOME, ".claude", "skills")
CLAUDE_AUTO_FILE = os.path.join(CLAUDE_SKILL_DIR, "graph-memory-auto.md")

CODEX_RULES_DIR = os.path.join(HOME, ".codex", "rules")
CODEX_AUTO_FILE = os.path.join(CODEX_RULES_DIR, "graph_memory_auto.md")

HERMES_MEMORIES_DIR = os.path.join(HOME, ".hermes", "memories")
HERMES_MEMORY_FILE = os.path.join(HERMES_MEMORIES_DIR, "MEMORY.md")

# ---------------------------------------------------------------------------
# Framework Installers & Uninstallers
# ---------------------------------------------------------------------------

def install_antigravity_hook(db_path=None):
    try:
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
        with open(ANTIGRAVITY_AUTO_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        return True, f"Installed Antigravity auto-memory snapshot to {ANTIGRAVITY_AUTO_FILE}"
    except Exception as e:
        return False, f"Failed installing Antigravity hook: {str(e)}"

def uninstall_antigravity_hook():
    if os.path.exists(ANTIGRAVITY_AUTO_FILE):
        try:
            os.remove(ANTIGRAVITY_AUTO_FILE)
            return True, f"Removed {ANTIGRAVITY_AUTO_FILE}"
        except Exception as e:
            return False, f"Failed removing Antigravity hook: {str(e)}"
    return False, "Antigravity hook was not installed."

def install_claude_code_hook(db_path=None):
    try:
        os.makedirs(CLAUDE_SKILL_DIR, exist_ok=True)
        actual_db = db_path or get_db_path()
        snapshot = generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)

        content = f"""# Epistemic Graph Memory Auto-Context

{snapshot}

> Auto-injected by `graph-memory hook install --framework claude-code`.
"""
        with open(CLAUDE_AUTO_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        return True, f"Installed Claude Code auto-memory snapshot to {CLAUDE_AUTO_FILE}"
    except Exception as e:
        return False, f"Failed installing Claude Code hook: {str(e)}"

def uninstall_claude_code_hook():
    if os.path.exists(CLAUDE_AUTO_FILE):
        try:
            os.remove(CLAUDE_AUTO_FILE)
            return True, f"Removed {CLAUDE_AUTO_FILE}"
        except Exception as e:
            return False, f"Failed removing Claude Code hook: {str(e)}"
    return False, "Claude Code hook was not installed."

def install_claude_desktop_hook(db_path=None):
    config_path = get_claude_desktop_config_path()
    if not os.path.exists(config_path):
        return False, f"Claude Desktop configuration file not found at {config_path} on platform {sys.platform}."

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        mcp_servers = config.get("mcpServers", {})
        if "graph_memory" in mcp_servers:
            env = mcp_servers["graph_memory"].get("env", {})
            env["GRAPH_MEMORY_AUTO_SNAPSHOT"] = "1"
            mcp_servers["graph_memory"]["env"] = env
            config["mcpServers"] = mcp_servers
            atomic_write_json(config_path, config)
            return True, f"Updated Claude Desktop config at {config_path} with GRAPH_MEMORY_AUTO_SNAPSHOT=1 env flag."
        return False, f"graph_memory MCP server entry is not present in {config_path}."
    except Exception as e:
        return False, f"Failed updating Claude Desktop hook: {str(e)}"

def uninstall_claude_desktop_hook():
    config_path = get_claude_desktop_config_path()
    if not os.path.exists(config_path):
        return False, f"Claude Desktop configuration file not found at {config_path}."

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        mcp_servers = config.get("mcpServers", {})
        if "graph_memory" in mcp_servers and "env" in mcp_servers["graph_memory"]:
            mcp_servers["graph_memory"]["env"].pop("GRAPH_MEMORY_AUTO_SNAPSHOT", None)
            config["mcpServers"] = mcp_servers
            atomic_write_json(config_path, config)
            return True, f"Removed GRAPH_MEMORY_AUTO_SNAPSHOT env flag from Claude Desktop config at {config_path}."
        return False, "Claude Desktop hook was not enabled."
    except Exception as e:
        return False, f"Failed removing Claude Desktop hook: {str(e)}"

def install_codex_hook(db_path=None):
    try:
        os.makedirs(CODEX_RULES_DIR, exist_ok=True)
        actual_db = db_path or get_db_path()
        snapshot = generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)

        content = f"""# Codex Active Graph Memory Snapshot Rule

{snapshot}

> Auto-injected rule for Codex sessions.
"""
        with open(CODEX_AUTO_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        return True, f"Installed Codex auto-memory rule to {CODEX_AUTO_FILE}"
    except Exception as e:
        return False, f"Failed installing Codex hook: {str(e)}"

def uninstall_codex_hook():
    if os.path.exists(CODEX_AUTO_FILE):
        try:
            os.remove(CODEX_AUTO_FILE)
            return True, f"Removed {CODEX_AUTO_FILE}"
        except Exception as e:
            return False, f"Failed removing Codex hook: {str(e)}"
    return False, "Codex hook was not installed."

def install_hermes_hook(db_path=None):
    try:
        os.makedirs(HERMES_MEMORIES_DIR, exist_ok=True)
        actual_db = db_path or get_db_path()
        snapshot = generate_active_snapshot(actual_db, max_tokens=400, min_trust=0.7)

        existing_content = ""
        if os.path.exists(HERMES_MEMORY_FILE):
            with open(HERMES_MEMORY_FILE, "r", encoding="utf-8") as f:
                existing_content = f.read()

        clean_existing = re.sub(r'§\s*# Epistemic Graph Memory.*?(?=(§|$))', '', existing_content, flags=re.DOTALL).strip()
        new_section = f"\n§\n# Epistemic Graph Memory Auto-Sync\n{snapshot}\n"
        final_content = (clean_existing + new_section).strip()

        with open(HERMES_MEMORY_FILE, "w", encoding="utf-8") as f:
            f.write(final_content)
        return True, f"Synced Graph Memory active snapshot into Hermes {HERMES_MEMORY_FILE}"
    except Exception as e:
        return False, f"Failed installing Hermes hook: {str(e)}"

def uninstall_hermes_hook():
    if os.path.exists(HERMES_MEMORY_FILE):
        try:
            with open(HERMES_MEMORY_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            clean = re.sub(r'§\s*# Epistemic Graph Memory.*?(?=(§|$))', '', content, flags=re.DOTALL).strip()
            with open(HERMES_MEMORY_FILE, "w", encoding="utf-8") as f:
                f.write(clean)
            return True, f"Cleaned Graph Memory section from Hermes {HERMES_MEMORY_FILE}"
        except Exception as e:
            return False, f"Failed removing Hermes hook: {str(e)}"
    return False, "Hermes MEMORY.md does not exist."

# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
FRAMEWORKS = {
    "antigravity": (install_antigravity_hook, uninstall_antigravity_hook, ANTIGRAVITY_AUTO_FILE),
    "claude-code": (install_claude_code_hook, uninstall_claude_code_hook, CLAUDE_AUTO_FILE),
    "claude-desktop": (install_claude_desktop_hook, uninstall_claude_desktop_hook, get_claude_desktop_config_path),
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
            results.append({"framework": fw, "status": "installed" if ok else "skipped", "message": msg})
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
    for fw, (_, _, path_entry) in FRAMEWORKS.items():
        path = path_entry() if callable(path_entry) else path_entry
        installed = os.path.exists(path)
        status.append({"framework": fw, "installed": installed, "path": path, "os_platform": sys.platform})
    return status
