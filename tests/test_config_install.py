"""Installation preserves user config and refuses destructive parse failures."""
import json
from pathlib import Path
import pytest
from context_broker.integrations_ttc.tools.install_tools import install_config
from context_broker.integrations_ttc.tools.config_tools import HOSTS


@pytest.mark.parametrize('host', HOSTS)
def test_install_preserves_existing_config_and_is_idempotent(tmp_path, host):
    path = tmp_path / 'config'
    if host == 'codex':
        original = '# keep comment\nmodel = "user-model"\n[mcp_servers.other]\ncommand = "other"\n'
    elif host in {'hermes', 'relayhelm'}:
        original = '# keep comment\nmodel: user-model\nmcp_servers:\n  other:\n    command: other\n'
    else:
        original = '{ // comment\n"model": "user-model", "mcpServers": {"other": {"command":"other"}},}'
    path.write_text(original)
    result = install_config(host, str(tmp_path), config_path=str(path))
    assert result['status'] == 'updated'
    assert Path(result['backup_path']).read_text() == original
    updated = path.read_text()
    skill = Path(result['skill_path'])
    assert skill.is_file()
    assert skill.parent.name == 'context-broker'
    assert skill.stat().st_mode & 0o077 == 0
    assert 'user-model' in updated and 'other' in updated
    if host in {'codex', 'hermes', 'relayhelm'}:
        assert '# keep comment' in updated
    assert install_config(host, str(tmp_path), config_path=str(path))['status'] == 'unchanged'


def test_relayhelm_plugin_merge(tmp_path):
    from ruamel.yaml import YAML
    path = tmp_path / 'config.yaml'
    path.write_text('plugins:\n  enabled: [other]\n  disabled: [context-broker, third]\n')
    install_config('relayhelm', str(tmp_path), config_path=str(path))
    config = YAML(typ='safe').load(path)
    assert config['plugins']['enabled'] == ['other', 'context-broker']
    assert config['plugins']['disabled'] == ['third']
    plugin = config['plugins']['entries']['context-broker']
    assert plugin['requires_mcp_servers'] == ['context-broker']
    assert plugin['settings']['project_root'] == str(tmp_path)


@pytest.mark.parametrize('host', HOSTS)
def test_invalid_config_unchanged(tmp_path, host):
    path = tmp_path / 'config'
    original = '[[[broken'
    path.write_text(original)
    with pytest.raises(Exception):
        install_config(host, str(tmp_path), config_path=str(path))
    assert path.read_text() == original
    assert not Path(str(path) + '.context-broker.bak').exists()


def test_preview_does_not_write(tmp_path, monkeypatch, capsys):
    import sys
    from context_broker.__main__ import main
    path = tmp_path / 'config'
    monkeypatch.setattr(sys, 'argv', ['context-broker', 'integration-config', '--host', 'relayhelm',
                        '--project-root', str(tmp_path), '--config-path', str(path), '--print'])
    main()
    assert 'mcp_servers' in json.loads(capsys.readouterr().out)
    assert not path.exists()


def test_cli_installs_by_default(tmp_path, monkeypatch, capsys):
    import sys
    from context_broker.__main__ import main
    path = tmp_path / 'config.yaml'
    monkeypatch.setattr(sys, 'argv', ['context-broker', 'integration-config', '--host', 'relayhelm',
                        '--project-root', str(tmp_path), '--config-path', str(path)])
    main()
    assert path.exists()
    assert 'updated:' in capsys.readouterr().out


def test_active_profile_destination(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path / 'profile'))
    result = install_config('relayhelm', str(tmp_path))
    assert result['config_path'] == str(tmp_path / 'profile' / 'config.yaml')


def test_malformed_plugin_section_preserves_file(tmp_path):
    path = tmp_path / 'config.yaml'
    original = 'plugins:\n  enabled: wrong-type\n'
    path.write_text(original)
    with pytest.raises(ValueError):
        install_config('relayhelm', str(tmp_path), config_path=str(path))
    assert path.read_text() == original
