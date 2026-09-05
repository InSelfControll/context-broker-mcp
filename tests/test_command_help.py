"""CLI discovery must never start a server or fetch project memory."""
import sys
from unittest.mock import Mock

import pytest

from context_broker import __main__ as cli


@pytest.mark.parametrize('args,code', [(['--help'], 0), (['serve', '--help'], 0),
    (['dashboard', '--typo'], 2), (['typo'], 2), (['serve', '--port', '-1'], 2)])
def test_help_and_errors_do_not_start_services(monkeypatch, args, code):
    server = Mock(side_effect=AssertionError('server started'))
    monkeypatch.setattr(cli, '_run_mcp_server', server)
    monkeypatch.setattr(cli, '_run_dashboard', server)
    monkeypatch.setattr(sys, 'argv', ['context-broker', *args])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == code
    server.assert_not_called()


def test_default_stdio_preserved(monkeypatch):
    server = Mock()
    monkeypatch.setattr(cli, '_run_mcp_server', server)
    monkeypatch.setattr(sys, 'argv', ['context-broker'])
    cli.main()
    server.assert_called_once_with()


def test_mcp_exposes_command_prompt_and_resource():
    import asyncio
    asyncio.run(_check_mcp_help())


async def _check_mcp_help():
    from context_broker.server_ttc.codebase.assembly import create_mcp_server
    from fastmcp import Client

    async with Client(create_mcp_server()) as client:
        assert 'context-broker' in [p.name for p in await client.list_prompts()]
        content = await client.read_resource('context-broker://commands')
        assert 'context-broker --help' in content[0].text
        prompt = await client.get_prompt('context-broker')
        assert 'No index' in prompt.messages[0].content.text
