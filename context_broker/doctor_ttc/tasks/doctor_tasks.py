"""Doctor orchestration: reports, startup warnings, and gated installs."""

import shutil
import subprocess
import sys
from dataclasses import asdict
from typing import Any

from context_broker.doctor_ttc.tools.env_checks import EnvCheck, run_checks
from context_broker.utils import log

INSTALL_TIMEOUT_SECONDS = 600


def build_report() -> dict[str, Any]:
    """Run all probes and return a JSON-serializable environment report."""
    checks = run_checks()
    missing_required = [c for c in checks if c.status == "missing" and c.required]
    missing_optional = [c for c in checks if c.status == "missing" and not c.required]
    warnings = [c for c in checks if c.status == "warn"]
    return {
        "status": "missing" if missing_required else ("warn" if (missing_optional or warnings) else "ok"),
        "python": sys.version.split()[0],
        "checks": [asdict(c) for c in checks],
        "missing_required": [c.name for c in missing_required],
        "missing_optional": [c.name for c in missing_optional],
        "warnings": [c.name for c in warnings],
    }


def startup_warnings() -> list[str]:
    """Short WARN lines for server startup when required pieces are missing."""
    warnings: list[str] = []
    for check in run_checks():
        if check.status == "missing" and check.required:
            hint = f" — install with: {check.install_hint}" if check.install_hint else ""
            warnings.append(f"⚠ Missing required dependency: {check.name} ({check.detail}){hint}")
    if warnings:
        warnings.append(
            "⚠ Run the check_environment MCP tool for a full report and a guided install."
        )
    return warnings


def _install_command(packages: list[str]) -> list[str]:
    """Pick the install command: uv when available, else the current pip."""
    if shutil.which("uv"):
        return ["uv", "pip", "install", *packages]
    return [sys.executable, "-m", "pip", "install", *packages]


def install_packages(packages: list[str]) -> dict[str, Any]:
    """Install packages with uv/pip; returns a JSON-serializable outcome.

    Callers must gate this behind explicit user confirmation.
    """
    if not packages:
        return {"status": "ok", "installed": [], "detail": "Nothing to install."}
    cmd = _install_command(packages)
    log(f"🔧 Installing missing packages: {' '.join(packages)}")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "installed": [],
            "detail": f"Install timed out after {INSTALL_TIMEOUT_SECONDS}s: {' '.join(cmd)}",
        }
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        return {"status": "error", "installed": [], "detail": tail}
    return {
        "status": "ok",
        "installed": list(packages),
        "detail": f"Installed via: {' '.join(cmd)}",
    }


def missing_required_packages(checks: list[EnvCheck] | None = None) -> list[str]:
    """Install hints (pip names) for missing required Python packages."""
    checks = checks if checks is not None else run_checks()
    return [
        c.install_hint
        for c in checks
        if c.status == "missing" and c.required and c.install_hint and not c.name.startswith("python")
    ]
