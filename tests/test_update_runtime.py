"""Installation ownership and service lifecycle guard the public update command."""

import subprocess
from unittest.mock import Mock

import pytest

from context_broker.integrations_ttc.tools import update_tools as updater


def test_unknown_installation_and_dirty_checkout_are_not_modified(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.shutil, "which", lambda _: "/bin/uv")
    monkeypatch.setattr(updater.sys, "prefix", str(tmp_path / "external"))
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=str(tmp_path / "tools")))
    monkeypatch.setattr(updater.subprocess, "run", run)
    metadata = Mock()
    metadata.read_text.return_value = '{}'
    monkeypatch.setattr(updater, "distribution", lambda _: metadata)
    with pytest.raises(RuntimeError, match="externally managed"):
        updater.update_runtime()
    assert run.call_count == 1
    metadata.read_text.return_value = '{"dir_info": {"editable": true}}'
    with pytest.raises(RuntimeError, match="Commit or stash"):
        updater.update_runtime()
    assert all(call.args[0][1] in {"tool", "status"} for call in run.call_args_list)


def test_check_is_read_only_and_update_restarts_only_after_success(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "update_commands", lambda: ([["uv", "tool", "upgrade", "context-broker"]], None))
    monkeypatch.setattr(updater, "runtime_directory", lambda: tmp_path)
    service = {"url": "http://127.0.0.1:1234/mcp", "token": "private"}
    monkeypatch.setattr(updater, "running_service", lambda: service)
    stop = Mock()
    monkeypatch.setattr(updater, "stop_service", stop)
    run = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(updater.subprocess, "run", run)
    updater.update_runtime(check_only=True)
    stop.assert_not_called()
    run.assert_not_called()
    updater.update_runtime()
    stop.assert_called_once_with(service)
    assert run.call_args_list[-1].args[0][-3:] == ["-m", "context_broker", "start"]
    run.reset_mock()
    run.side_effect = subprocess.CalledProcessError(1, ["uv"])
    with pytest.raises(subprocess.CalledProcessError):
        updater.update_runtime()
    assert run.call_count == 1
