import os
import sys
import pytest
from graph_memory.integrations import framework_hooks

def test_framework_hook_status():
    status = framework_hooks.get_hook_status()
    assert len(status) == 5
    frameworks = [s["framework"] for s in status]
    assert "antigravity" in frameworks
    assert "claude-code" in frameworks
    assert "claude-desktop" in frameworks
    assert "codex" in frameworks
    assert "hermes" in frameworks
    for s in status:
        assert s["os_platform"] == sys.platform

def test_cross_platform_path_resolver():
    path = framework_hooks.get_claude_desktop_config_path()
    assert isinstance(path, str)
    assert len(path) > 0

def test_framework_hook_install_uninstall():
    results = framework_hooks.install_hooks(target_framework="antigravity")
    assert len(results) == 1
    assert results[0]["status"] == "installed"

    status = framework_hooks.get_hook_status()
    antigravity_status = next(s for s in status if s["framework"] == "antigravity")
    assert antigravity_status["installed"] is True

    un_res = framework_hooks.uninstall_hooks(target_framework="antigravity")
    assert len(un_res) == 1
    assert un_res[0]["status"] == "uninstalled"
