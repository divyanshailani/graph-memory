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

def _merge_json_config(file_path, mutate):
    """Loads a JSON config (or starts fresh), applies `mutate(data)`, writes atomically."""
    data = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
    mutate(data)
    atomic_write_json(file_path, data)

# ---------------------------------------------------------------------------
# Framework Paths Definition
# ---------------------------------------------------------------------------
ANTIGRAVITY_SKILL_DIR = os.path.join(HOME, ".gemini", "config", "skills", "graph_memory")
ANTIGRAVITY_AUTO_FILE = os.path.join(ANTIGRAVITY_SKILL_DIR, "AUTO_MEMORY.md")

CLAUDE_SKILL_DIR = os.path.join(HOME, ".claude", "skills")
CLAUDE_AUTO_FILE = os.path.join(CLAUDE_SKILL_DIR, "graph-memory-auto.md")
CLAUDE_SETTINGS_PATH = os.path.join(HOME, ".claude", "settings.json")

CODEX_RULES_DIR = os.path.join(HOME, ".codex", "rules")
CODEX_AUTO_FILE = os.path.join(CODEX_RULES_DIR, "graph_memory_auto.md")
CODEX_CONFIG_TOML = os.path.join(HOME, ".codex", "config.toml")

HERMES_MEMORIES_DIR = os.path.join(HOME, ".hermes", "memories")
HERMES_MEMORY_FILE = os.path.join(HERMES_MEMORIES_DIR, "MEMORY.md")

ZCODE_CONFIG_PATH = os.path.join(HOME, ".zcode", "cli", "config.json")

CURSOR_MCP_PATH = os.path.join(HOME, ".cursor", "mcp.json")
CURSOR_RULE_FILE = os.path.join(HOME, ".cursor", "rules", "graph-memory-auto.mdc")

QODER_RULE_FILE = os.path.join(HOME, ".qoder", "rules", "graph-memory-auto.md")

OPENCODE_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config"))
OPENCODE_AGENTS_FILE = os.path.join(OPENCODE_CONFIG_HOME, "opencode", "AGENTS.md")
OPENCODE_SECTION_START = "<!-- graph-memory:auto:start -->"
OPENCODE_SECTION_END = "<!-- graph-memory:auto:end -->"

CODEX_MCP_MARKER = "# >>> graph-memory mcp >>>"

# Hook entrypoint: venv-proof module invocation of the lifecycle dispatcher.
HOOK_EVENT_ARGS = ["-m", "graph_memory.cli", "hook-event"]
MCP_SERVER_COMMAND = "graph-memory-mcp"

# Identification markers for our hook entries inside host configs (any of these
# substrings in a command/args marks the entry as ours for idempotent reinstall).
HOOK_MARKERS = ("graph_memory.cli hook-event", "graph-memory hook-event")

LIFECYCLE_INSTRUCTIONS = """
## Graph Memory Lifecycle Protocol

1. **Session start**: call the `get_active_snapshot` MCP tool (or read the snapshot below)
   to load active high-trust project memory before planning.
2. **After editing any file**: call `ingest_file` with the changed path so the code
   graph stays current (<5ms).
3. **Before ending / summarizing**: call `distill_session` with the session's key
   exchanges so decisions and facts persist.
4. **Search before re-deciding**: use `search_nodes` and `query_decision_history` —
   past agent rationales live in the Decision Ledger.
"""

# ---------------------------------------------------------------------------
# Snapshot renderers (shared by install and refresh so files never go stale)
# ---------------------------------------------------------------------------
def render_snapshot_section(max_tokens=600):
    return generate_active_snapshot(get_db_path(), max_tokens=max_tokens, min_trust=0.7)

def _render_antigravity(snapshot):
    return f"""---
name: graph-memory-auto
description: Auto-injected Epistemic Graph Memory snapshot for Antigravity sessions.
---

# Auto-Injected Epistemic Memory Snapshot

{snapshot}

{LIFECYCLE_INSTRUCTIONS}
> [!NOTE]
> This snapshot is automatically refreshed by `graph-memory hook install/refresh` and by
> session lifecycle hooks to provide ground-truth memory recall without manual user reminders.
"""

def _render_claude_code(snapshot):
    return f"""# Epistemic Graph Memory Auto-Context

{snapshot}

{LIFECYCLE_INSTRUCTIONS}
> Auto-injected by `graph-memory hook install --framework claude-code`. Lifecycle hooks in
> `~/.claude/settings.json` keep the graph and this file current automatically.
"""

def _render_codex(snapshot):
    return f"""# Codex Active Graph Memory Snapshot Rule

{snapshot}

{LIFECYCLE_INSTRUCTIONS}
> Auto-injected rule for Codex sessions. MCP server entry is registered in ~/.codex/config.toml.
"""

def _render_cursor(snapshot):
    return f"""---
description: Epistemic Graph Memory auto-context and lifecycle protocol
alwaysApply: true
---

# Epistemic Graph Memory Auto-Context

{snapshot}

{LIFECYCLE_INSTRUCTIONS}
> Auto-injected by `graph-memory hook install --framework cursor`. The graph-memory MCP
> server is registered in ~/.cursor/mcp.json — use its tools for search and ingestion.
"""

def _render_qoder(snapshot):
    return f"""---
kind: "project_memory"
category: "auto_context"
title: "Epistemic Graph Memory Auto-Context"
updated_at: "{engine.now_iso()}"
---

# Epistemic Graph Memory Auto-Context

{snapshot}

{LIFECYCLE_INSTRUCTIONS}
> Auto-injected by `graph-memory hook install --framework qoder`.
"""

def _render_opencode(snapshot):
    return f"""{OPENCODE_SECTION_START}
# Epistemic Graph Memory Auto-Context

{snapshot}

{LIFECYCLE_INSTRUCTIONS}
> Auto-managed by `graph-memory hook install --framework opencode`. OpenCode currently
> requires remote HTTP/SSE MCP servers, so run `graph-memory-mcp` behind an HTTP
> transport (or use the CLI: `graph-memory snapshot`, `graph-memory ingest-file`).
{OPENCODE_SECTION_END}"""

# ---------------------------------------------------------------------------
# Hook entry installers for host configs (Claude Code settings.json, ZCode config.json)
# ---------------------------------------------------------------------------
def _is_our_hook(entry):
    cmd = entry.get("command", "")
    if any(marker in cmd for marker in HOOK_MARKERS):
        return True
    args = " ".join(entry.get("args", []) or [])
    return any(marker in args for marker in HOOK_MARKERS)

def install_claude_code_event_hooks():
    """Merges graph-memory lifecycle hooks into ~/.claude/settings.json (idempotent)."""
    hook_spec = {"type": "command", "command": f'"{sys.executable}" ' + " ".join(HOOK_EVENT_ARGS)}
    events = {
        "PostToolUse": [{"matcher": "Write|Edit|MultiEdit", "hooks": [hook_spec]}],
        "Stop": [{"hooks": [dict(hook_spec)]}],
        "SessionStart": [{"hooks": [dict(hook_spec)]}],
    }

    def mutate(data):
        hooks = data.get("hooks", {})
        for event, groups in events.items():
            existing = hooks.get(event, [])
            for group in existing:
                group["hooks"] = [h for h in group.get("hooks", []) if not _is_our_hook(h)]
            matched = next((g for g in existing if g.get("matcher") == groups[0].get("matcher") or (not g.get("matcher") and not groups[0].get("matcher"))), None)
            if matched:
                matched["hooks"].append(hook_spec)
            else:
                existing.append(groups[0])
            hooks[event] = existing
        data["hooks"] = hooks

    _merge_json_config(CLAUDE_SETTINGS_PATH, mutate)
    return f"Registered PostToolUse/Stop/SessionStart hooks in {CLAUDE_SETTINGS_PATH}"

def uninstall_claude_code_event_hooks():
    if not os.path.exists(CLAUDE_SETTINGS_PATH):
        return False, "No Claude Code settings.json found."

    def mutate(data):
        hooks = data.get("hooks", {})
        for event, groups in list(hooks.items()):
            for group in groups:
                group["hooks"] = [h for h in group.get("hooks", []) if not _is_our_hook(h)]
            hooks[event] = [g for g in groups if g.get("hooks")]
            if not hooks[event]:
                del hooks[event]
        data["hooks"] = hooks

    _merge_json_config(CLAUDE_SETTINGS_PATH, mutate)
    return True, f"Removed graph-memory hooks from {CLAUDE_SETTINGS_PATH}"

def install_zcode_event_hooks():
    """Merges graph-memory lifecycle hooks into ~/.zcode/cli/config.json (idempotent).

    ZCode hook schema: hooks.events.<Event> -> [{matcher?, hooks:[{type: process, command, args, timeoutMs}]}]
    Configuration-file hooks require hooks.enabled = true.
    """
    def make_entry():
        return {
            "type": "process",
            "command": sys.executable,
            "args": list(HOOK_EVENT_ARGS),
            "timeoutMs": 30000,
        }

    events = {
        "PostToolUse": [{"matcher": "Write|Edit|ApplyPatch", "hooks": [make_entry()]}],
        "Stop": [{"hooks": [make_entry()]}],
        "SessionStart": [{"hooks": [make_entry()]}],
    }

    def mutate(data):
        hooks = data.get("hooks", {})
        hooks["enabled"] = True
        hook_events = hooks.get("events", {})
        for event, groups in events.items():
            existing = hook_events.get(event, [])
            for group in existing:
                group["hooks"] = [h for h in group.get("hooks", []) if not _is_our_hook(h)]
            want_matcher = groups[0].get("matcher")
            matched = next(
                (g for g in existing if (g.get("matcher") or None) == (want_matcher or None)),
                None,
            )
            if matched:
                matched["hooks"].append(groups[0]["hooks"][0])
            else:
                existing.append(groups[0])
            hook_events[event] = existing
        hooks["events"] = hook_events
        data["hooks"] = hooks

    _merge_json_config(ZCODE_CONFIG_PATH, mutate)
    return f"Registered PostToolUse/Stop/SessionStart hooks in {ZCODE_CONFIG_PATH} (hooks.enabled=true)"

def uninstall_zcode_event_hooks():
    if not os.path.exists(ZCODE_CONFIG_PATH):
        return False, "No ZCode config.json found."

    def mutate(data):
        hooks = data.get("hooks", {})
        hook_events = hooks.get("events", {})
        for event, groups in list(hook_events.items()):
            for group in groups:
                group["hooks"] = [h for h in group.get("hooks", []) if not _is_our_hook(h)]
            hook_events[event] = [g for g in groups if g.get("hooks")]
            if not hook_events[event]:
                del hook_events[event]
        hooks["events"] = hook_events
        data["hooks"] = hooks

    _merge_json_config(ZCODE_CONFIG_PATH, mutate)
    return True, f"Removed graph-memory hooks from {ZCODE_CONFIG_PATH}"

# ---------------------------------------------------------------------------
# MCP registration (Cursor mcp.json, Codex config.toml)
# ---------------------------------------------------------------------------
def install_cursor_mcp():
    def mutate(data):
        servers = data.get("mcpServers", {})
        servers["graph-memory"] = {"command": MCP_SERVER_COMMAND}
        data["mcpServers"] = servers

    _merge_json_config(CURSOR_MCP_PATH, mutate)
    return f"Registered graph-memory MCP server in {CURSOR_MCP_PATH}"

def uninstall_cursor_mcp():
    if not os.path.exists(CURSOR_MCP_PATH):
        return False, "No Cursor mcp.json found."

    def mutate(data):
        data.get("mcpServers", {}).pop("graph-memory", None)

    _merge_json_config(CURSOR_MCP_PATH, mutate)
    return True, f"Removed graph-memory MCP server from {CURSOR_MCP_PATH}"

def install_codex_mcp():
    """Appends an MCP server section to ~/.codex/config.toml (marker-guarded, idempotent)."""
    section = (
        f"\n{CODEX_MCP_MARKER}\n"
        "[mcp_servers.graph-memory]\n"
        f'command = "{MCP_SERVER_COMMAND}"\n'
    )
    if os.path.exists(CODEX_CONFIG_TOML):
        with open(CODEX_CONFIG_TOML, "r", encoding="utf-8") as f:
            content = f.read()
        if CODEX_MCP_MARKER in content or "mcp_servers.graph-memory" in content:
            return f"graph-memory MCP entry already present in {CODEX_CONFIG_TOML}"
    os.makedirs(os.path.dirname(CODEX_CONFIG_TOML), exist_ok=True)
    with open(CODEX_CONFIG_TOML, "a", encoding="utf-8") as f:
        f.write(section)
    return f"Registered graph-memory MCP server in {CODEX_CONFIG_TOML}"

def uninstall_codex_mcp():
    if not os.path.exists(CODEX_CONFIG_TOML):
        return False, "No Codex config.toml found."
    with open(CODEX_CONFIG_TOML, "r", encoding="utf-8") as f:
        lines = f.readlines()
    kept, skipping = [], False
    for line in lines:
        if line.strip() == CODEX_MCP_MARKER:
            skipping = True
            continue
        if skipping and line.strip().startswith("[") and not line.strip().startswith("[mcp_servers.graph-memory]"):
            skipping = False
        if not skipping:
            kept.append(line)
    with open(CODEX_CONFIG_TOML, "w", encoding="utf-8") as f:
        f.writelines(kept)
    return True, f"Removed graph-memory MCP section from {CODEX_CONFIG_TOML}"

# ---------------------------------------------------------------------------
# Marked-section injection (OpenCode AGENTS.md)
# ---------------------------------------------------------------------------
def _write_marked_section(file_path, section_content):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    existing = ""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            existing = f.read()
    pattern = re.compile(
        re.escape(OPENCODE_SECTION_START) + r".*?" + re.escape(OPENCODE_SECTION_END),
        re.DOTALL,
    )
    if pattern.search(existing):
        updated = pattern.sub(section_content, existing)
    else:
        updated = existing.rstrip("\n") + ("\n\n" if existing.strip() else "") + section_content + "\n"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(updated)

def _remove_marked_section(file_path):
    if not os.path.exists(file_path):
        return False, f"{file_path} does not exist."
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    pattern = re.compile(
        re.escape(OPENCODE_SECTION_START) + r".*?" + re.escape(OPENCODE_SECTION_END) + r"\n*",
        re.DOTALL,
    )
    cleaned = pattern.sub("", content).strip()
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(cleaned + ("\n" if cleaned else ""))
    return True, f"Removed graph-memory section from {file_path}"

# ---------------------------------------------------------------------------
# Framework Installers & Uninstallers
# ---------------------------------------------------------------------------
def install_antigravity_hook(db_path=None):
    try:
        os.makedirs(os.path.dirname(ANTIGRAVITY_AUTO_FILE), exist_ok=True)
        actual_db = db_path or get_db_path()
        snapshot = generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)
        with open(ANTIGRAVITY_AUTO_FILE, "w", encoding="utf-8") as f:
            f.write(_render_antigravity(snapshot))
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
        os.makedirs(os.path.dirname(CLAUDE_AUTO_FILE), exist_ok=True)
        actual_db = db_path or get_db_path()
        snapshot = generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)
        with open(CLAUDE_AUTO_FILE, "w", encoding="utf-8") as f:
            f.write(_render_claude_code(snapshot))
        hooks_msg = install_claude_code_event_hooks()
        return True, f"Installed Claude Code auto-memory to {CLAUDE_AUTO_FILE}; {hooks_msg}"
    except Exception as e:
        return False, f"Failed installing Claude Code hook: {str(e)}"

def uninstall_claude_code_hook():
    removed = []
    if os.path.exists(CLAUDE_AUTO_FILE):
        try:
            os.remove(CLAUDE_AUTO_FILE)
            removed.append(f"Removed {CLAUDE_AUTO_FILE}")
        except Exception as e:
            return False, f"Failed removing Claude Code hook: {str(e)}"
    try:
        ok, msg = uninstall_claude_code_event_hooks()
        removed.append(msg)
    except Exception as e:
        return False, f"Failed removing Claude Code event hooks: {str(e)}"
    return (True if removed else False), "; ".join(removed) or "Claude Code hook was not installed."

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
        os.makedirs(os.path.dirname(CODEX_AUTO_FILE), exist_ok=True)
        actual_db = db_path or get_db_path()
        snapshot = generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)
        with open(CODEX_AUTO_FILE, "w", encoding="utf-8") as f:
            f.write(_render_codex(snapshot))
        mcp_msg = install_codex_mcp()
        return True, f"Installed Codex auto-memory rule to {CODEX_AUTO_FILE}; {mcp_msg}"
    except Exception as e:
        return False, f"Failed installing Codex hook: {str(e)}"

def uninstall_codex_hook():
    removed = []
    if os.path.exists(CODEX_AUTO_FILE):
        try:
            os.remove(CODEX_AUTO_FILE)
            removed.append(f"Removed {CODEX_AUTO_FILE}")
        except Exception as e:
            return False, f"Failed removing Codex hook: {str(e)}"
    try:
        ok, msg = uninstall_codex_mcp()
        removed.append(msg)
    except Exception as e:
        return False, f"Failed removing Codex MCP entry: {str(e)}"
    return (True if removed else False), "; ".join(removed) or "Codex hook was not installed."

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
        new_section = f"\n§\n# Epistemic Graph Memory Auto-Sync\n{snapshot}\n\n{LIFECYCLE_INSTRUCTIONS}\n"
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

def install_zcode_hook(db_path=None):
    try:
        actual_db = db_path or get_db_path()
        generate_active_snapshot(actual_db, max_tokens=50, min_trust=0.7)  # warm the DB / validate
        msg = install_zcode_event_hooks()
        return True, msg
    except Exception as e:
        return False, f"Failed installing ZCode hooks: {str(e)}"

def uninstall_zcode_hook():
    try:
        return uninstall_zcode_event_hooks()
    except Exception as e:
        return False, f"Failed removing ZCode hooks: {str(e)}"

def install_cursor_hook(db_path=None):
    try:
        actual_db = db_path or get_db_path()
        snapshot = generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)
        os.makedirs(os.path.dirname(CURSOR_RULE_FILE), exist_ok=True)
        with open(CURSOR_RULE_FILE, "w", encoding="utf-8") as f:
            f.write(_render_cursor(snapshot))
        mcp_msg = install_cursor_mcp()
        return True, f"Installed Cursor rule to {CURSOR_RULE_FILE}; {mcp_msg}"
    except Exception as e:
        return False, f"Failed installing Cursor hook: {str(e)}"

def uninstall_cursor_hook():
    removed = []
    if os.path.exists(CURSOR_RULE_FILE):
        try:
            os.remove(CURSOR_RULE_FILE)
            removed.append(f"Removed {CURSOR_RULE_FILE}")
        except Exception as e:
            return False, f"Failed removing Cursor rule: {str(e)}"
    try:
        ok, msg = uninstall_cursor_mcp()
        removed.append(msg)
    except Exception as e:
        return False, f"Failed removing Cursor MCP entry: {str(e)}"
    return (True if removed else False), "; ".join(removed) or "Cursor hook was not installed."

def install_qoder_hook(db_path=None):
    try:
        actual_db = db_path or get_db_path()
        snapshot = generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)
        os.makedirs(os.path.dirname(QODER_RULE_FILE), exist_ok=True)
        with open(QODER_RULE_FILE, "w", encoding="utf-8") as f:
            f.write(_render_qoder(snapshot))
        return True, f"Installed Qoder rule to {QODER_RULE_FILE}"
    except Exception as e:
        return False, f"Failed installing Qoder hook: {str(e)}"

def uninstall_qoder_hook():
    if os.path.exists(QODER_RULE_FILE):
        try:
            os.remove(QODER_RULE_FILE)
            return True, f"Removed {QODER_RULE_FILE}"
        except Exception as e:
            return False, f"Failed removing Qoder rule: {str(e)}"
    return False, "Qoder rule was not installed."

def install_opencode_hook(db_path=None):
    try:
        actual_db = db_path or get_db_path()
        snapshot = generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)
        _write_marked_section(OPENCODE_AGENTS_FILE, _render_opencode(snapshot))
        return True, f"Installed graph-memory auto section into {OPENCODE_AGENTS_FILE}"
    except Exception as e:
        return False, f"Failed installing OpenCode hook: {str(e)}"

def uninstall_opencode_hook():
    try:
        return _remove_marked_section(OPENCODE_AGENTS_FILE)
    except Exception as e:
        return False, f"Failed removing OpenCode section: {str(e)}"

# ---------------------------------------------------------------------------
# Dispatcher & Snapshot Refresh
# ---------------------------------------------------------------------------
FRAMEWORKS = {
    "antigravity": (install_antigravity_hook, uninstall_antigravity_hook, ANTIGRAVITY_AUTO_FILE),
    "claude-code": (install_claude_code_hook, uninstall_claude_code_hook, CLAUDE_AUTO_FILE),
    "claude-desktop": (install_claude_desktop_hook, uninstall_claude_desktop_hook, get_claude_desktop_config_path),
    "codex": (install_codex_hook, uninstall_codex_hook, CODEX_AUTO_FILE),
    "hermes": (install_hermes_hook, uninstall_hermes_hook, HERMES_MEMORY_FILE),
    "zcode": (install_zcode_hook, uninstall_zcode_hook, ZCODE_CONFIG_PATH),
    "cursor": (install_cursor_hook, uninstall_cursor_hook, CURSOR_RULE_FILE),
    "qoder": (install_qoder_hook, uninstall_qoder_hook, QODER_RULE_FILE),
    "opencode": (install_opencode_hook, uninstall_opencode_hook, OPENCODE_AGENTS_FILE),
}

# Frameworks whose installed files embed a snapshot that must be re-rendered on refresh.
_REFRESHABLE = {
    "antigravity": (ANTIGRAVITY_AUTO_FILE, lambda snap: (_render_antigravity(snap))),
    "claude-code": (CLAUDE_AUTO_FILE, lambda snap: (_render_claude_code(snap))),
    "codex": (CODEX_AUTO_FILE, lambda snap: (_render_codex(snap))),
    "cursor": (CURSOR_RULE_FILE, lambda snap: (_render_cursor(snap))),
    "qoder": (QODER_RULE_FILE, lambda snap: (_render_qoder(snap))),
    "opencode": (OPENCODE_AGENTS_FILE, lambda snap: (_render_opencode(snap))),
}

def refresh_installed_snapshots(db_path=None) -> list:
    """Re-renders the auto-memory snapshot inside every installed framework file.

    Called by the SessionStart/Stop lifecycle hooks so injected memory never goes stale.
    """
    actual_db = db_path or get_db_path()
    refreshed = []

    def _read_path(entry):
        return entry() if callable(entry) else entry

    for fw, (path_entry, renderer) in _REFRESHABLE.items():
        path = _read_path(path_entry)
        if not os.path.exists(path):
            continue
        try:
            if fw == "opencode":
                _write_marked_section(path, _render_opencode(generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)))
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(renderer(generate_active_snapshot(actual_db, max_tokens=600, min_trust=0.7)))
            refreshed.append(fw)
        except Exception as e:
            print(f"[graph-memory] refresh failed for {fw}: {e}", file=sys.stderr)

    if os.path.exists(HERMES_MEMORY_FILE):
        try:
            install_hermes_hook(actual_db)
            refreshed.append("hermes")
        except Exception as e:
            print(f"[graph-memory] refresh failed for hermes: {e}", file=sys.stderr)

    return refreshed

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
