"""Atomic, locked installation into native coding-agent configuration files."""

from collections.abc import MutableMapping
from io import StringIO
import json
import os
from pathlib import Path
import tempfile

from filelock import FileLock

from context_broker.integrations_ttc.tools.config_tools import DESTINATIONS, client_config


def _mapping(parent: MutableMapping, key: str) -> MutableMapping:
    """Get a configuration table without replacing malformed existing values."""
    if key not in parent:
        parent[key] = {}
    value = parent[key]
    if not isinstance(value, MutableMapping):
        raise ValueError(f"Configuration section {key} must be a mapping")
    return value


def _include(parent: MutableMapping, key: str, value: str) -> None:
    """Add one entry while preserving all other configured entries."""
    if key not in parent:
        parent[key] = []
    if not isinstance(parent[key], list):
        raise ValueError(f"Configuration section {key} must be a list")
    if value not in parent[key]:
        parent[key].append(value)


def _write_atomic(path: Path, content: str, mode: int) -> None:
    """Replace a file only after its complete contents are flushed to disk."""
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def install_config(host: str, project_root: str, *, runtime_dir: str = "",
                   config_path: str = "") -> dict[str, str]:
    """Merge broker settings, preserving unrelated values and backing up existing files."""
    fragment = client_config(host, project_root, runtime_dir=runtime_dir)
    root = Path(project_root).resolve(strict=True)
    destination = Path(config_path).expanduser() if config_path else Path(DESTINATIONS[host]).expanduser()
    if not destination.is_absolute():
        destination = root / destination
    # Respect explicitly selected Hermes/Relayhelm profiles.
    if not config_path and host in {"hermes", "relayhelm"} and os.environ.get("HERMES_HOME"):
        destination = Path(os.environ["HERMES_HOME"]).expanduser() / "config.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(destination) + ".context-broker.lock", timeout=10):
        if destination.is_symlink():
            raise ValueError("Config is a symlink; pass its real target with --config-path")
        exists = destination.exists()
        original = destination.read_text(encoding="utf-8") if exists else ""
        if host == "codex":
            import tomlkit
            document = tomlkit.parse(original)
            patch = tomlkit.parse(fragment)
            serialize = tomlkit.dumps
        elif host in {"hermes", "relayhelm"}:
            from ruamel.yaml import YAML
            yaml = YAML(typ="rt")
            yaml.preserve_quotes = True
            document = yaml.load(original) if original.strip() else {}
            patch = json.loads(fragment)

            def serialize(value: MutableMapping) -> str:
                stream = StringIO()
                yaml.dump(value, stream)
                return stream.getvalue()
        else:
            import json5
            document = json5.loads(original, allow_duplicate_keys=False) if original.strip() else {}
            patch = json.loads(fragment)

            def serialize(value: MutableMapping) -> str:
                return json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        if not isinstance(document, MutableMapping):
            raise ValueError("Existing configuration must be a mapping")
        key = next(iter(patch))
        entry = _mapping(_mapping(document, key), "context-broker")
        # Remove mutually exclusive remote transport settings when selecting stdio.
        for obsolete in ("url", "headers", "http_headers", "bearer_token_env_var", "type"):
            if obsolete not in patch[key]["context-broker"]:
                entry.pop(obsolete, None)
        for name, value in patch[key]["context-broker"].items():
            if isinstance(value, MutableMapping):
                _mapping(entry, name).update(value)
            else:
                entry[name] = value
        if host in {"codex", "hermes", "relayhelm"}:
            entry["enabled"] = True
        if host == "relayhelm":
            plugins = _mapping(document, "plugins")
            _include(plugins, "enabled", "context-broker")
            if "disabled" in plugins:
                if not isinstance(plugins["disabled"], list):
                    raise ValueError("plugins.disabled must be a list")
                plugins["disabled"] = [x for x in plugins["disabled"] if x != "context-broker"]
            plugin = _mapping(_mapping(plugins, "entries"), "context-broker")
            for name in ("mcp_allowlist", "requires_mcp_servers"):
                _include(plugin, name, "context-broker")
            _mapping(plugin, "settings").update(server="context-broker", project_root=str(root))
        rendered = serialize(document)
        if rendered == original:
            return {"status": "unchanged", "config_path": str(destination),
                    "skill_path": str(_install_skill(host, root, destination))}
        if destination.is_symlink() or destination.exists() != exists:
            raise RuntimeError("Config changed during installation; retry")
        if exists and destination.read_text(encoding="utf-8") != original:
            raise RuntimeError("Config changed during installation; retry")
        backup = str(destination) + ".context-broker.bak"
        if exists:
            _write_atomic(Path(backup), original, 0o600)
        _write_atomic(destination, rendered, 0o600)
        return {"status": "updated", "config_path": str(destination),
                "backup_path": backup if exists else "",
                "skill_path": str(_install_skill(host, root, destination))}


def _install_skill(host: str, root: Path, config_path: Path) -> Path:
    """Install the packaged skill into the host's discovery path, preserving prior text."""
    from importlib.resources import files

    directories = {
        "codex": root / ".agents", "cursor": root / ".cursor",
        "claude-code": root / ".claude", "hermes": config_path.parent,
        "relayhelm": config_path.parent,
    }
    path = directories[host] / "skills" / "context-broker" / "SKILL.md"
    if path.resolve() != path.absolute():
        raise ValueError("Skill destination must not contain symlinks")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = files("context_broker").joinpath(
        "integrations_ttc/assets/context-broker/SKILL.md"
    ).read_text(encoding="utf-8")
    with FileLock(str(path) + ".lock", timeout=10):
        original = path.read_text(encoding="utf-8") if path.exists() else None
        if original != content:
            if original is not None:
                _write_atomic(path.with_suffix(".md.bak"), original, 0o600)
            _write_atomic(path, content, 0o600)
    return path
