"""
OS-level scheduling for mechanical memory verification (v3.9.0).

Trust decays on a half-life whether or not anything verifies, so a repo with no
agent activity quietly drops its own knowledge below the retrieval floor. The
hash-stable pass needs no agent — it only needs to run. This module installs an
OS-native job (launchd LaunchAgent, systemd user unit, or Task Scheduler task)
that executes `graph-memory verify --tests` on an interval.

No daemon, no third-party dependency: install/uninstall/status are thin
wrappers over `launchctl`, `systemctl --user`, and `schtasks`, keyed by a hash
of the db path so multiple project stores can schedule independently.
"""

import hashlib
import os
import subprocess
import sys

from graph_memory.core import engine

LABEL_PREFIX = "com.graphmemory.verify"


def _home():
    """Indirection for tests: HOME resolution."""
    return os.path.expanduser("~")


def _job_key(db_path: str) -> str:
    return hashlib.sha1(os.path.abspath(db_path).encode("utf-8")).hexdigest()[:8]


def verify_argv(db_path: str, tests: bool = True) -> list:
    argv = [sys.executable, "-m", "graph_memory.cli", "--db", db_path, "verify"]
    if tests:
        argv.append("--tests")
    return argv


def _run(argv: list) -> tuple:
    """Runs a scheduler command; returns (returncode, combined output)."""
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


# ---------------------------------------------------------------------------
# macOS — launchd LaunchAgent
# ---------------------------------------------------------------------------

def _macos_plist_path(key: str) -> str:
    return os.path.join(_home(), "Library", "LaunchAgents", f"{LABEL_PREFIX}-{key}.plist")


def build_macos_plist(argv: list, interval: int, log_path: str, label: str) -> str:
    """Renders the LaunchAgent plist. Pure function: no HOME or filesystem reads."""
    args_xml = "\n".join(f"        <string>{a}</string>" for a in argv)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>StartInterval</key>
    <integer>{interval}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""


def _install_macos(argv: list, interval: int, key: str) -> dict:
    agents_dir = os.path.join(_home(), "Library", "LaunchAgents")
    os.makedirs(agents_dir, exist_ok=True)
    log_dir = os.path.join(_home(), "Library", "Logs", "GraphMemory")
    os.makedirs(log_dir, exist_ok=True)
    plist_path = os.path.join(agents_dir, f"{LABEL_PREFIX}-{key}.plist")
    with open(plist_path, "w", encoding="utf-8") as fh:
        fh.write(build_macos_plist(argv, interval, os.path.join(log_dir, "verify.log"),
                                   f"{LABEL_PREFIX}-{key}"))
    uid = os.getuid()
    # Modern bootdomain syntax first; fall back to the legacy load for older macOS.
    rc, out = _run(["launchctl", "bootstrap", f"gui/{uid}", plist_path])
    if rc != 0:
        rc, out = _run(["launchctl", "load", plist_path])
    return {"installed": rc == 0, "backend": "launchd", "target": plist_path, "output": out}


def _uninstall_macos(key: str) -> dict:
    plist_path = _macos_plist_path(key)
    if not os.path.exists(plist_path):
        return {"uninstalled": False, "backend": "launchd", "reason": f"No job file at {plist_path}"}
    uid = os.getuid()
    _run(["launchctl", "bootout", f"gui/{uid}/{LABEL_PREFIX}-{key}"])
    _run(["launchctl", "unload", plist_path])
    os.remove(plist_path)
    return {"uninstalled": True, "backend": "launchd", "target": plist_path}


def _status_macos(key: str) -> dict:
    plist_path = _macos_plist_path(key)
    if not os.path.exists(plist_path):
        return {"scheduled": False, "backend": "launchd", "reason": f"No job file at {plist_path}"}
    rc, _ = _run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL_PREFIX}-{key}"])
    return {"scheduled": True, "backend": "launchd", "loaded": rc == 0, "target": plist_path}


# ---------------------------------------------------------------------------
# Linux — systemd user units
# ---------------------------------------------------------------------------

def _units_dir() -> str:
    return os.path.join(_home(), ".config", "systemd", "user")


def _unit_names(key: str) -> tuple:
    base = f"graphmemory-verify-{key}"
    return f"{base}.service", f"{base}.timer"


def _install_linux(argv: list, interval: int, key: str) -> dict:
    service, timer = _unit_names(key)
    os.makedirs(_units_dir(), exist_ok=True)
    exec_str = " ".join(f'"{a}"' for a in argv)
    service_path = os.path.join(_units_dir(), service)
    timer_path = os.path.join(_units_dir(), timer)
    with open(service_path, "w", encoding="utf-8") as fh:
        fh.write(
            "[Unit]\nDescription=Graph-Memory mechanical verification pass\n\n"
            "[Service]\nType=oneshot\n"
            f"ExecStart={exec_str}\n"
        )
    hours = max(1, round(interval / 3600))
    with open(timer_path, "w", encoding="utf-8") as fh:
        fh.write(
            "[Unit]\nDescription=Run Graph-Memory verification periodically\n\n"
            "[Timer]\nOnBootSec=5min\n"
            f"OnUnitActiveSec={hours}h\n\n"
            "[Install]\nWantedBy=timers.target\n"
        )
    rc, out = _run(["systemctl", "--user", "daemon-reload"])
    if rc == 0:
        rc, out = _run(["systemctl", "--user", "enable", "--now", timer])
    if rc != 0:
        out += "\nHint: user timers need lingering outside a login session: loginctl enable-linger $USER"
    return {"installed": rc == 0, "backend": "systemd-user", "target": timer_path, "output": out}


def _uninstall_linux(key: str) -> dict:
    service, timer = _unit_names(key)
    unit_dir = _units_dir()
    if not any(os.path.exists(os.path.join(unit_dir, u)) for u in (service, timer)):
        return {"uninstalled": False, "backend": "systemd-user", "reason": f"No units in {unit_dir}"}
    _run(["systemctl", "--user", "disable", "--now", timer])
    for unit in (service, timer):
        path = os.path.join(unit_dir, unit)
        if os.path.exists(path):
            os.remove(path)
    _run(["systemctl", "--user", "daemon-reload"])
    return {"uninstalled": True, "backend": "systemd-user", "target": unit_dir}


def _status_linux(key: str) -> dict:
    _, timer = _unit_names(key)
    timer_path = os.path.join(_units_dir(), timer)
    if not os.path.exists(timer_path):
        return {"scheduled": False, "backend": "systemd-user", "reason": f"No unit at {timer_path}"}
    rc, _ = _run(["systemctl", "--user", "is-active", "--quiet", timer])
    return {"scheduled": True, "backend": "systemd-user", "loaded": rc == 0, "target": timer_path}


# ---------------------------------------------------------------------------
# Windows — Task Scheduler
# ---------------------------------------------------------------------------

def _win_task_name(key: str) -> str:
    return f"GraphMemoryVerify-{key}"


def _install_windows(argv: list, interval: int, key: str) -> dict:
    task = _win_task_name(key)
    tr = " ".join(f'"{a}"' for a in argv)
    every_days = max(1, round(interval / 86400))
    rc, out = _run([
        "schtasks", "/Create", "/F", "/TN", task, "/TR", tr,
        "/SC", "DAILY", "/MO", str(every_days),
    ])
    return {"installed": rc == 0, "backend": "schtasks", "target": task, "output": out}


def _uninstall_windows(key: str) -> dict:
    task = _win_task_name(key)
    rc, out = _run(["schtasks", "/Delete", "/F", "/TN", task])
    return {"uninstalled": rc == 0, "backend": "schtasks", "target": task, "output": out}


def _status_windows(key: str) -> dict:
    rc, out = _run(["schtasks", "/Query", "/TN", _win_task_name(key)])
    return {"scheduled": rc == 0, "backend": "schtasks", "loaded": rc == 0, "target": _win_task_name(key)}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def install(db_path: str, interval: int = 86400, tests: bool = True) -> dict:
    key = _job_key(db_path)
    argv = verify_argv(db_path, tests=tests)
    if sys.platform == "darwin":
        return _install_macos(argv, interval, key)
    if sys.platform == "win32":
        return _install_windows(argv, interval, key)
    return _install_linux(argv, interval, key)


def uninstall(db_path: str) -> dict:
    key = _job_key(db_path)
    if sys.platform == "darwin":
        return _uninstall_macos(key)
    if sys.platform == "win32":
        return _uninstall_windows(key)
    return _uninstall_linux(key)


def status(db_path: str) -> dict:
    key = _job_key(db_path)
    if sys.platform == "darwin":
        return _status_macos(key)
    if sys.platform == "win32":
        return _status_windows(key)
    return _status_linux(key)
