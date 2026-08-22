"""Agents MD management MCP tool handlers."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from context_broker.agents_ttc.codebase.api import (
    ensure_agents_md,
    generate_agents_md,
    scan_for_missing_agents_md,
    validate_agents_md,
)
from context_broker.lifecycle import tracked_activity
from context_broker.project import resolve_project_root
from context_broker.server_ttc.tools.helpers import notify_error, progress
from context_broker.utils import log


def register_agents_tools(mcp: FastMCP) -> None:
    """Register AGENTS.md management tools."""

    @mcp.tool()
    async def ensure_agents_md_tool(
        project_root: str = "",
        ctx: Context = None,
    ) -> str:
        """Ensure AGENTS.md exists for a project. Creates it if missing.

        Args:
            project_root: Project root path (auto-detected if empty)
        """
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"📝 ensure_agents_md called: project_root='{root_display}'")
            await progress(ctx, f"🔍 Checking AGENTS.md for project: {root_display}")

            root = resolve_project_root(project_root)
            try:
                result = ensure_agents_md(root)
                status = result["status"]
                path = result["path"]

                if status == "exists":
                    await progress(ctx, "✅ AGENTS.md already exists")
                    return f"📄 AGENTS.md already exists at: {path}\n\nNo changes were made."

                await progress(ctx, "✅ Created AGENTS.md")
                return (
                    f"📝 Created AGENTS.md\n"
                    f"📁 Path: {path}\n"
                    f"\n"
                    f"The file was generated from project metadata.\n"
                    f"Review and customize it to add project-specific goals and conventions."
                )
            except Exception as e:
                error_msg = f"❌ Error ensuring AGENTS.md: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg

    @mcp.tool()
    async def validate_agents_md_tool(
        project_root: str = "",
        ctx: Context = None,
    ) -> str:
        """Validate AGENTS.md for a project and report missing information.

        Args:
            project_root: Project root path (auto-detected if empty)
        """
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"📋 validate_agents_md called: project_root='{root_display}'")
            await progress(ctx, f"📋 Validating AGENTS.md for: {root_display}")

            root = resolve_project_root(project_root)
            try:
                result = validate_agents_md(root)
                status = result["status"]
                path = result["path"]
                score = result.get("score", 0)

                lines = [
                    "📋 AGENTS.md Validation Report",
                    f"📁 Path: {path}",
                    f"📊 Status: {status.upper()}",
                    f"⭐ Score: {score}/100",
                    "",
                ]

                if status == "missing":
                    lines.extend([
                        "⚠  AGENTS.md is missing!",
                        "",
                        "💡 Run `ensure_agents_md` to create one automatically.",
                    ])
                    await progress(ctx, "⚠ AGENTS.md is missing")
                    return "\n".join(lines)

                missing_required = result.get("missing_required", [])
                missing_optional = result.get("missing_optional", [])
                suggestions = result.get("suggestions", [])

                if missing_required:
                    lines.extend([
                        "❌ Missing Required Sections:",
                    ])
                    for item in missing_required:
                        lines.append(f"   • {item}")
                    lines.append("")

                if missing_optional:
                    lines.extend([
                        f"⚠  Missing Optional Sections ({len(missing_optional)}):",
                    ])
                    for item in missing_optional[:10]:
                        lines.append(f"   • {item}")
                    if len(missing_optional) > 10:
                        lines.append(f"   ... and {len(missing_optional) - 10} more")
                    lines.append("")

                if suggestions:
                    lines.extend([
                        "💡 Suggestions:",
                    ])
                    for item in suggestions:
                        lines.append(f"   • {item}")
                    lines.append("")

                if result.get("valid"):
                    lines.extend([
                        "✅ AGENTS.md looks good!",
                        "",
                    ])
                    await progress(ctx, "✅ AGENTS.md validation passed")
                else:
                    lines.extend([
                        "⚠  AGENTS.md needs improvement.",
                        "",
                    ])
                    await progress(ctx, "⚠ AGENTS.md needs improvement")

                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Error validating AGENTS.md: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg

    @mcp.tool()
    async def generate_agents_md_tool(
        project_root: str = "",
        force: bool = False,
        ctx: Context = None,
    ) -> str:
        """Generate AGENTS.md for a project. Overwrites existing if force=True.

        Args:
            project_root: Project root path (auto-detected if empty)
            force: Overwrite existing AGENTS.md
        """
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"🚀 generate_agents_md called: project_root='{root_display}', force={force}")
            await progress(ctx, f"🚀 Generating AGENTS.md for: {root_display}")

            root = resolve_project_root(project_root)
            try:
                result = generate_agents_md(root, force=force)
                status = result["status"]
                path = result["path"]

                if status == "exists":
                    await progress(ctx, "⚠ AGENTS.md already exists")
                    return (
                        f"📄 AGENTS.md already exists at: {path}\n"
                        f"\n"
                        f"Use force=True to overwrite."
                    )

                action = "Overwritten" if status == "overwritten" else "Created"
                await progress(ctx, f"✅ {action} AGENTS.md")
                return (
                    f"📝 {action} AGENTS.md\n"
                    f"📁 Path: {path}\n"
                    f"\n"
                    f"Review and customize the generated file."
                )
            except Exception as e:
                error_msg = f"❌ Error generating AGENTS.md: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg

    @mcp.tool()
    async def scan_projects_for_agents_md(
        project_root: str = "",
        max_depth: int = 3,
        ctx: Context = None,
    ) -> str:
        """Scan for projects missing AGENTS.md.

        Args:
            project_root: Root directory to scan (auto-detected if empty)
            max_depth: Maximum depth to search (default: 3)
        """
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"🔍 scan_projects_for_agents_md called: project_root='{root_display}', max_depth={max_depth}")
            await progress(ctx, "🔍 Scanning for projects missing AGENTS.md...")

            root = resolve_project_root(project_root)
            try:
                results = scan_for_missing_agents_md(root, max_depth=max_depth)
                missing = [r for r in results if not r["has_agents_md"]]
                ok_count = len(results) - len(missing)

                await progress(ctx, f"📊 Found {len(results)} projects, {len(missing)} missing AGENTS.md")

                lines = [
                    "🔍 AGENTS.md Scan Results",
                    f"📁 Scanned from: {root}",
                    f"📊 Projects found: {len(results)}",
                    f"✅ With AGENTS.md: {ok_count}",
                    f"❌ Missing AGENTS.md: {len(missing)}",
                    "",
                ]

                if missing:
                    lines.extend([
                        "Projects missing AGENTS.md:",
                        "",
                    ])
                    for r in missing:
                        lines.append(f"   ❌ {r['name']}  ({r['path']})")
                    lines.extend([
                        "",
                        "💡 Run `ensure_agents_md` for each project to create them.",
                    ])
                else:
                    lines.append("🎉 All projects have AGENTS.md!")

                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Error scanning projects: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg
