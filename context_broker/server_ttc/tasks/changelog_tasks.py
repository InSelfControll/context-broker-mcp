"""Changelog management MCP tool handlers."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from context_broker.changelog_ttc.codebase.api import (
    check_changelog_status,
    ensure_changelog,
    generate_changelog_for_version,
    get_changelog_stats,
)
from context_broker.lifecycle import tracked_activity
from context_broker.project import resolve_project_root
from context_broker.server_ttc.tools.helpers import notify_error, progress
from context_broker.utils import log


def register_changelog_tools(mcp: FastMCP) -> None:
    """Register changelog management tools."""

    @mcp.tool()
    async def ensure_changelog_tool(
        project_root: str = "",
        ctx: Context = None,
    ) -> str:
        """Ensure CHANGELOG.md exists and is up to date with git history.

        Creates CHANGELOG.md if missing, or appends new commits since the last update.
        Parses conventional commits (feat:, fix:, security:, etc.) and categorizes them.

        Args:
            project_root: Project root path (auto-detected if empty)
        """
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"📝 ensure_changelog called: project_root='{root_display}'")
            await progress(ctx, f"📝 Checking CHANGELOG.md for: {root_display}")

            root = resolve_project_root(project_root)
            try:
                result = ensure_changelog(str(root))
                status = result["status"]

                if status == "no_changes":
                    await progress(ctx, "✅ CHANGELOG.md is already up to date")
                    return (
                        f"📋 CHANGELOG.md Status\n"
                        f"📁 Path: {root / 'CHANGELOG.md'}\n"
                        f"\n"
                        f"✅ Already up to date. No new commits to document."
                    )

                commit_count = result.get("commit_count", "0")
                categories = result.get("categories", "")
                await progress(ctx, f"✅ Updated CHANGELOG.md with {commit_count} commits")

                lines = [
                    f"📝 CHANGELOG.md Updated",
                    f"📁 Path: {root / 'CHANGELOG.md'}",
                    f"📊 Commits added: {commit_count}",
                ]
                if categories:
                    lines.append(f"📂 Categories: {categories}")
                lines.extend([
                    "",
                    "The following section was added:",
                    "",
                    "---",
                    result.get("content", ""),
                    "---",
                ])
                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Error updating CHANGELOG.md: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg

    @mcp.tool()
    async def validate_changelog_tool(
        project_root: str = "",
        ctx: Context = None,
    ) -> str:
        """Validate that CHANGELOG.md is up to date with git history.

        Checks for undocumented commits and reports how many are missing.

        Args:
            project_root: Project root path (auto-detected if empty)
        """
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"📋 validate_changelog called: project_root='{root_display}'")
            await progress(ctx, f"📋 Validating CHANGELOG.md for: {root_display}")

            root = resolve_project_root(project_root)
            try:
                result = check_changelog_status(str(root))
                status = result["status"]
                valid = result.get("valid", False)
                missing = result.get("missing_count", 0)

                lines = [
                    f"📋 CHANGELOG.md Validation Report",
                    f"📁 Path: {root / 'CHANGELOG.md'}",
                    f"📊 Status: {status.upper()}",
                ]

                if status == "missing":
                    lines.extend([
                        "",
                        "❌ CHANGELOG.md does not exist.",
                        "",
                        "💡 Run `ensure_changelog` to create one automatically.",
                    ])
                    await progress(ctx, "❌ CHANGELOG.md is missing")
                    return "\n".join(lines)

                if valid:
                    lines.extend([
                        "",
                        "✅ CHANGELOG.md is up to date with git history.",
                    ])
                    await progress(ctx, "✅ CHANGELOG.md validation passed")
                else:
                    lines.extend([
                        "",
                        f"⚠️ {missing} commits are not documented.",
                        "",
                        f"💡 {result.get('suggestion', 'Run ensure_changelog to update.')}",
                    ])
                    await progress(ctx, f"⚠️ {missing} commits undocumented")

                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Error validating CHANGELOG.md: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg

    @mcp.tool()
    async def generate_version_changelog(
        version: str,
        project_root: str = "",
        since: str = "",
        ctx: Context = None,
    ) -> str:
        """Generate a changelog section for a specific version release.

        Args:
            version: Version label (e.g., "0.2.0")
            project_root: Project root path (auto-detected if empty)
            since: Git ref to start from (auto-detected from CHANGELOG if empty)
        """
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"🚀 generate_version_changelog called: version='{version}', project_root='{root_display}'")
            await progress(ctx, f"🚀 Generating changelog for version {version}...")

            root = resolve_project_root(project_root)
            try:
                result = generate_changelog_for_version(str(root), version, since)
                status = result["status"]
                commit_count = result.get("commit_count", "0")

                if status == "no_changes":
                    await progress(ctx, "ℹ️ No new commits found")
                    return (
                        f"📋 Version Changelog: {version}\n"
                        f"\n"
                        f"ℹ️ No new commits found since last update."
                    )

                await progress(ctx, f"✅ Generated changelog for {version} ({commit_count} commits)")
                return (
                    f"📝 Version Changelog Generated\n"
                    f"📦 Version: {version}\n"
                    f"📁 Path: {root / 'CHANGELOG.md'}\n"
                    f"📊 Commits: {commit_count}\n"
                    f"\n"
                    f"Added section:\n"
                    f"\n"
                    f"---\n"
                    f"{result.get('content', '')}\n"
                    f"---"
                )
            except Exception as e:
                error_msg = f"❌ Error generating changelog: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg

    @mcp.tool()
    async def get_changelog_stats_tool(
        project_root: str = "",
        ctx: Context = None,
    ) -> str:
        """Get statistics about the current CHANGELOG.md.

        Args:
            project_root: Project root path (auto-detected if empty)
        """
        with tracked_activity():
            root = resolve_project_root(project_root)
            try:
                result = get_changelog_stats(str(root))
                status = result["status"]

                if status == "missing":
                    return (
                        f"📋 CHANGELOG.md Statistics\n"
                        f"📁 Path: {root / 'CHANGELOG.md'}\n"
                        f"\n"
                        f"❌ CHANGELOG.md does not exist.\n"
                        f"\n"
                        f"💡 Run `ensure_changelog` to create one."
                    )

                return (
                    f"📋 CHANGELOG.md Statistics\n"
                    f"📁 Path: {root / 'CHANGELOG.md'}\n"
                    f"📊 Versions documented: {result.get('versions', '0')}\n"
                    f"🏷️  Latest version: {result.get('latest_version', 'N/A')}\n"
                    f"📝 Total entries: {result.get('total_entries', '0')}"
                )
            except Exception as e:
                error_msg = f"❌ Error getting changelog stats: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg
