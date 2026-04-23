"""Documentation management MCP tool handlers."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from context_broker.docs_ttc.codebase.api import docs_stats, ensure_docs, scan_docs
from context_broker.lifecycle import tracked_activity
from context_broker.project import resolve_project_root
from context_broker.server_ttc.tools.helpers import notify_error, progress
from context_broker.utils import log


def register_docs_tools(mcp: FastMCP) -> None:
    """Register documentation management tools."""

    @mcp.tool()
    async def ensure_feature_docs_tool(
        project_root: str = "",
        since: str = "",
        ctx: Context = None,
    ) -> str:
        """Ensure documentation exists for all recent feature changes.

        Creates docs/{feature}/{feature}-{fix-type}.md for each detected feature change,
        or docs/{feature}/{fix-type}.md if no related docs exist yet.

        Args:
            project_root: Project root path (auto-detected if empty)
            since: Git ref to start from (default: recent commits)
        """
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"📝 ensure_feature_docs called: project_root='{root_display}'")
            await progress(ctx, f"📝 Generating feature docs for: {root_display}")

            root = resolve_project_root(project_root)
            try:
                result = ensure_docs(str(root), since=since)
                status = result["status"]
                created = result.get("created_count", 0)
                existing = result.get("existing_count", 0)

                if status == "no_changes":
                    await progress(ctx, "ℹ️ No commits found to document")
                    return "📄 No commits found to document.\n\nMake some commits first."

                lines = [
                    f"📝 Feature Documentation Report",
                    f"📁 Project: {root.name}",
                    f"📊 Created: {created} docs",
                    f"📊 Already exist: {existing} docs",
                    "",
                ]

                docs = result.get("docs", [])
                created_docs = [d for d in docs if d["status"] == "created"]
                if created_docs:
                    lines.append("New documentation created:")
                    lines.append("")
                    for doc in created_docs:
                        lines.append(f"  ✅ {doc['feature']} — {doc['fix_type']}")
                        lines.append(f"     📄 {doc['path']}")
                        lines.append(f"     📝 {doc['commit_count']} commits documented")
                        lines.append("")

                existing_docs = [d for d in docs if d["status"] == "exists"]
                if existing_docs:
                    lines.append("Already documented (skipped):")
                    lines.append("")
                    for doc in existing_docs:
                        lines.append(f"  ⏭️  {doc['feature']} — {doc['fix_type']} ({doc['path']})")
                    lines.append("")

                await progress(ctx, f"✅ Created {created} feature docs")
                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Error generating feature docs: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg

    @mcp.tool()
    async def scan_missing_docs_tool(
        project_root: str = "",
        since: str = "",
        ctx: Context = None,
    ) -> str:
        """Scan for feature changes that are missing documentation.

        Args:
            project_root: Project root path (auto-detected if empty)
            since: Git ref to start from
        """
        with tracked_activity():
            root_display = project_root if project_root else "[auto-detected]"
            log(f"🔍 scan_missing_docs called: project_root='{root_display}'")
            await progress(ctx, f"🔍 Scanning for missing docs: {root_display}")

            root = resolve_project_root(project_root)
            try:
                result = scan_docs(str(root), since=since)
                status = result["status"]
                missing_count = result.get("missing_count", 0)

                lines = [
                    f"🔍 Missing Documentation Report",
                    f"📁 Project: {root.name}",
                ]

                if status == "no_commits":
                    lines.extend(["", "ℹ️ No commits found to analyze."])
                    await progress(ctx, "ℹ️ No commits found")
                    return "\n".join(lines)

                if status == "complete":
                    lines.extend(["", "✅ All feature changes are documented!"])
                    await progress(ctx, "✅ All docs complete")
                    return "\n".join(lines)

                lines.extend([
                    "",
                    f"⚠️  {missing_count} feature doc(s) missing:",
                    "",
                ])

                for item in result.get("missing", []):
                    lines.append(f"  📂 Feature: {item['feature']}")
                    lines.append(f"  🏷️  Type: {item['fix_type']}")
                    lines.append(f"  📝 Commits: {item['commits']}")
                    lines.append(f"  💡 Suggested: {item['suggested_path']}")
                    lines.append("")

                lines.append("💡 Run `ensure_feature_docs` to create them automatically.")
                await progress(ctx, f"⚠️ {missing_count} docs missing")
                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Error scanning docs: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg

    @mcp.tool()
    async def get_docs_stats_tool(
        project_root: str = "",
        ctx: Context = None,
    ) -> str:
        """Get statistics about feature documentation.

        Args:
            project_root: Project root path (auto-detected if empty)
        """
        with tracked_activity():
            root = resolve_project_root(project_root)
            try:
                result = docs_stats(str(root))
                status = result["status"]

                if status == "missing":
                    return (
                        f"📚 Documentation Statistics\n"
                        f"📁 Project: {root.name}\n"
                        f"\n"
                        f"❌ No docs/ directory found.\n"
                        f"\n"
                        f"💡 Run `ensure_feature_docs` to create documentation."
                    )

                features = result.get("features_list", [])
                lines = [
                    f"📚 Documentation Statistics",
                    f"📁 Project: {root.name}",
                    f"📊 Features documented: {result.get('features', 0)}",
                    f"📄 Total docs: {result.get('total_docs', 0)}",
                    "",
                ]

                if features:
                    lines.append("Features with documentation:")
                    lines.append("")
                    for feature in features:
                        lines.append(f"  📂 {feature}")

                return "\n".join(lines)
            except Exception as e:
                error_msg = f"❌ Error getting docs stats: {e}"
                log(error_msg, "ERROR")
                await notify_error(ctx, error_msg)
                return error_msg
