"""Verify actual executable arguments and each host's config format and units."""

import json
import os
import sys
import tomllib

import pytest

from context_broker.integrations_ttc.tools.config_tools import client_config


@pytest.mark.parametrize("host", ["codex", "hermes", "cursor", "claude-code"])
def test_host_configuration_preserves_project_and_safe_consent(tmp_path, host):
    project = tmp_path / "project with spaces"
    project.mkdir()
    output = client_config(host, str(project), runtime_dir=str(tmp_path / "runtime"))
    config = tomllib.loads(output) if host == "codex" else json.loads(output)
    key = "mcp_servers" if host in {"codex", "hermes"} else "mcpServers"
    entry = config[key]["context-broker"]
    assert entry["command"] == os.path.abspath(sys.executable)
    assert entry["args"] == ["-m", "context_broker", "connect", "--project-root", str(project)]
    assert entry["env"]["CONTEXT_BROKER_AUTO_LOAD_ENV"] == "0"
    assert "LLM_API_KEY" not in output
    if host == "codex":
        assert entry["tool_timeout_sec"] == 600
    elif host == "hermes":
        assert entry["timeout"] == 600 and entry["elicitation"]["enabled"]
    elif host == "claude-code":
        assert entry["timeout"] == 600000


def test_config_rejects_unknown_host_and_missing_root(tmp_path):
    with pytest.raises(ValueError):
        client_config("unknown", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        client_config("codex", str(tmp_path / "missing"))
