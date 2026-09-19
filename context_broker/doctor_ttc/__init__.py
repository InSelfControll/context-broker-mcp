"""
Doctor TTC package: host environment checks and guided installs.
"""

from context_broker.doctor_ttc.codebase.api import (
    EnvCheck,
    build_report,
    install_packages,
    missing_required_packages,
    run_checks,
    startup_warnings,
)

__all__ = [
    "EnvCheck",
    "run_checks",
    "build_report",
    "install_packages",
    "missing_required_packages",
    "startup_warnings",
]
