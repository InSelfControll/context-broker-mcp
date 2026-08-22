"""Environment doctor MCP tool handlers."""

from fastmcp import Context, FastMCP

from context_broker.doctor_ttc import (
    build_report,
    install_packages,
    missing_required_packages,
    run_checks,
)
from context_broker.lifecycle import tracked_activity
from context_broker.server_ttc.tools.helpers import notify_error, progress
from context_broker.utils import log

_STATUS_ICON = {"ok": "✅", "warn": "⚠", "missing": "❌"}


def _render_report_lines(report: dict) -> list[str]:
    """Human-readable rendering of a doctor report."""
    lines = [
        "🩺 Context Broker Environment Check",
        f"🐍 Python: {report['python']}",
        f"📊 Overall: {report['status'].upper()}",
        "",
    ]
    for check in report["checks"]:
        icon = _STATUS_ICON.get(check["status"], "•")
        req = "required" if check["required"] else "optional"
        line = f"{icon} {check['name']} [{req}] — {check['detail']}"
        if check["status"] == "missing" and check["install_hint"]:
            line += f" (install: {check['install_hint']})"
        lines.append(line)
    return lines


def register_doctor_tools(mcp: FastMCP) -> None:
    """Register environment self-check tools."""

    @mcp.tool()
    async def check_environment(
        install_missing: bool = False,
        confirm: str = "",
        ctx: Context = None,
    ) -> str:
        """Check this machine for everything context-broker needs to run.

        Reports missing required/optional dependencies (Python version,
        packages, embedding model cache, external tools). Nothing is installed
        by default. To install missing required Python packages, call again
        with install_missing=True; the tool then asks for explicit
        confirmation and only proceeds when confirm="yes".
        """
        with tracked_activity():
            log("🩺 check_environment called")
            await progress(ctx, "🩺 Probing environment (Python, packages, model cache, tools)...")
            try:
                report = build_report()
                lines = _render_report_lines(report)
                lines.append("")

                packages = missing_required_packages(run_checks())
                if not packages:
                    if report["missing_required"]:
                        lines.append(
                            "❌ Required gaps need manual fixes (e.g. upgrade Python); "
                            "no auto-install available for them."
                        )
                    else:
                        lines.append("✅ All required dependencies are present.")
                    return "\n".join(lines)

                lines.append(
                    "❌ Missing required packages: " + ", ".join(packages)
                )
                if not install_missing:
                    lines.append(
                        "ℹ Re-run with install_missing=True and I will ask before installing."
                    )
                    return "\n".join(lines)

                if confirm.strip().lower() != "yes":
                    lines.append(
                        "❓ Install these now with uv/pip? "
                        "Re-run with install_missing=True, confirm='yes' to proceed."
                    )
                    return "\n".join(lines)

                await progress(ctx, f"🔧 Installing: {', '.join(packages)}")
                outcome = install_packages(packages)
                lines.append(f"🔧 Install result: {outcome['status']} — {outcome['detail']}")
                if outcome["status"] == "ok":
                    followup = build_report()
                    lines.append("")
                    lines.append(f"📊 Post-install status: {followup['status'].upper()}")
                    if followup["missing_required"]:
                        lines.append(
                            "❌ Still missing: " + ", ".join(followup["missing_required"])
                        )
                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Environment check error: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return f"Error: {str(e)}"
