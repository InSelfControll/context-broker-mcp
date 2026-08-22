"""Tests for the environment doctor checks, report, and gated installs."""

from __future__ import annotations

from context_broker.doctor_ttc import (
    build_report,
    install_packages,
    missing_required_packages,
    run_checks,
    startup_warnings,
)
from context_broker.doctor_ttc.tasks import doctor_tasks
from context_broker.doctor_ttc.tools import env_checks


def test_run_checks_includes_python_and_core_packages() -> None:
    checks = run_checks()
    names = {c.name for c in checks}
    assert "python" in names
    assert "package:fastmcp" in names
    assert "package:torch" in names
    assert "binary:git" in names
    python_check = next(c for c in checks if c.name == "python")
    assert python_check.status == "ok"  # repo requires Python 3.13+


def test_build_report_shape() -> None:
    report = build_report()
    assert report["status"] in {"ok", "warn", "missing"}
    assert isinstance(report["checks"], list) and report["checks"]
    for check in report["checks"]:
        assert set(check) >= {"name", "status", "required", "detail", "install_hint"}


def test_missing_required_package_detected(monkeypatch) -> None:
    real = env_checks._module_available
    monkeypatch.setattr(
        env_checks,
        "_module_available",
        lambda module: False if module == "torch" else real(module),
    )
    report = build_report()
    assert report["status"] == "missing"
    assert "package:torch" in report["missing_required"]
    assert "torch" in missing_required_packages()
    warnings = startup_warnings()
    assert any("package:torch" in w for w in warnings)


def test_optional_missing_does_not_fail_overall(monkeypatch) -> None:
    real = env_checks._module_available
    monkeypatch.setattr(
        env_checks,
        "_module_available",
        lambda module: False if module == "jinja2" else real(module),
    )
    report = build_report()
    assert "package:jinja2" in report["missing_optional"]
    assert "package:jinja2" not in report["missing_required"]
    assert report["status"] != "missing"


def test_install_packages_empty_is_noop() -> None:
    outcome = install_packages([])
    assert outcome["status"] == "ok"
    assert outcome["installed"] == []


def test_install_packages_runs_uv_or_pip(monkeypatch) -> None:
    calls: list[list[str]] = []

    class _Proc:
        returncode = 0
        stdout = "installed"
        stderr = ""

    monkeypatch.setattr(
        doctor_tasks.subprocess,
        "run",
        lambda cmd, **kwargs: (calls.append(cmd), _Proc())[1],
    )
    outcome = install_packages(["some-package"])
    assert outcome["status"] == "ok"
    assert outcome["installed"] == ["some-package"]
    assert len(calls) == 1
    assert calls[0][:2] in (["uv", "pip"], [doctor_tasks.sys.executable, "-m"])


def test_install_packages_reports_failure(monkeypatch) -> None:
    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "boom: package not found"

    monkeypatch.setattr(doctor_tasks.subprocess, "run", lambda *a, **k: _Proc())
    outcome = install_packages(["nope-package"])
    assert outcome["status"] == "error"
    assert "boom" in outcome["detail"]
