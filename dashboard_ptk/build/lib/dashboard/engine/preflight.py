"""Project activation preflight checks and lightweight initialization."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .content_locator import resolve_content_dir
from .env_resolver import EnvResolver
from .runtime_config import RuntimeConfig
from .tool_registry import ToolRegistry
from .types import ExecutionContext


Severity = Literal["error", "warning", "info"]


@dataclass
class PreflightFinding:
    """Single preflight check result."""

    severity: Severity
    check: str
    message: str
    fix_hint: str | None = None


@dataclass
class ProjectPreflightReport:
    """Project preflight report."""

    repo_root: Path
    created_paths: list[Path] = field(default_factory=list)
    findings: list[PreflightFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[PreflightFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[PreflightFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def infos(self) -> list[PreflightFinding]:
        return [f for f in self.findings if f.severity == "info"]

    @property
    def is_ready(self) -> bool:
        return len(self.errors) == 0

    def add(self, severity: Severity, check: str, message: str, fix_hint: str | None = None) -> None:
        self.findings.append(
            PreflightFinding(severity=severity, check=check, message=message, fix_hint=fix_hint)
        )


class ProjectPreflight:
    """Run deterministic checks whenever a project is activated."""

    def __init__(
        self,
        repo_root: Path,
        website_id: str | None = None,
        *,
        tool_registry: ToolRegistry | None = None,
        runtime_config: RuntimeConfig | None = None,
        required_clis: list[str] | tuple[str, ...] | None = None,
        check_cli: bool = True,
        check_reddit_auth: bool = False,
    ):
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.website_id = website_id
        self.tool_registry = tool_registry or ToolRegistry()
        self.runtime_config = runtime_config or RuntimeConfig()
        if required_clis is not None:
            self.required_clis = tuple(str(cli) for cli in required_clis if str(cli).strip())
        else:
            self.required_clis = tuple(self.runtime_config.required_clis)
        self.check_cli = check_cli
        self.check_reddit_auth = check_reddit_auth

    def run(self) -> ProjectPreflightReport:
        report = ProjectPreflightReport(repo_root=self.repo_root)

        if not self.repo_root.exists():
            report.add(
                "error",
                "repo_root",
                f"Project path does not exist: {self.repo_root}",
                "Update repo_root in projects config.",
            )
            return report

        automation_dir = self.repo_root / ".github" / "automation"
        self._ensure_dir(report, automation_dir, "automation_dir")
        self._ensure_dir(report, automation_dir / "artifacts", "artifacts_dir")
        self._ensure_dir(report, automation_dir / "task_results", "task_results_dir")
        self._ensure_dir(report, automation_dir / "reddit", "reddit_dir")

        self._check_required_project_files(report, automation_dir)
        self._check_content_dir(report)
        self._check_gitignore(report)

        if self.check_cli:
            self._check_required_clis(report)

        if self.check_reddit_auth:
            self._check_reddit_auth(report)

        return report

    def _ensure_dir(self, report: ProjectPreflightReport, path: Path, check: str) -> None:
        if path.exists():
            return
        path.mkdir(parents=True, exist_ok=True)
        report.created_paths.append(path)
        report.add("info", check, f"Created missing directory: {path}")

    def _check_required_project_files(self, report: ProjectPreflightReport, automation_dir: Path) -> None:
        articles_json = automation_dir / "articles.json"
        if not articles_json.exists():
            report.add(
                "error",
                "articles_json",
                f"Missing required file: {articles_json}",
                "Create/restore articles.json before running content workflows.",
            )

        # Check for project configuration files (templates created during init)
        config_files = [
            (automation_dir / "manifest.json", "manifest"),
            (automation_dir / "brandvoice.md", "brandvoice"),
            (automation_dir / "project_summary.md", "project_summary"),
            (automation_dir / "seo_content_brief.md", "seo_content_brief"),
        ]
        
        missing_config = []
        for path, name in config_files:
            if not path.exists():
                missing_config.append((name, path))
        
        if missing_config:
            for name, path in missing_config:
                report.add(
                    "warning",
                    f"config_{name}",
                    f"Missing project config file: {path.name}",
                    f"Create {path.name} or re-run project initialization to generate templates.",
                )

        if not self.website_id:
            return

        reddit_files = [
            automation_dir / "reddit_config.md",
            automation_dir / "reddit" / "_reply_guardrails.md",
        ]
        missing = [path for path in reddit_files if not path.exists()]
        if missing:
            report.add(
                "warning",
                "reddit_config",
                f"Reddit workflow config missing ({len(missing)} file(s))",
                "Add missing files under .github/automation before running reddit_opportunity_search.",
            )

    def _check_content_dir(self, report: ProjectPreflightReport) -> None:
        """Check if content directory exists with markdown files."""
        resolution = resolve_content_dir(
            repo_root=self.repo_root,
            website_id=self.website_id,
            include_empty_auto_fallback=True,
        )

        if resolution.configured_path and not resolution.configured_exists:
            report.add(
                "warning",
                "content_dir_configured",
                f"Configured content directory not found: {self._display_path(resolution.configured_path)}",
                "Update project content_dir or create the configured directory.",
            )

        if not resolution.selected:
            common_paths = "webapp/content/blog/, src/blog/posts/, src/content/, content/blog/, content/"
            report.add(
                "warning",
                "content_dir",
                "No content directory found with markdown files.",
                f"Create one of: {common_paths} and add markdown files, or set project content_dir.",
            )
            return

        selected_path = self._display_path(resolution.selected)
        if resolution.selected_source == "configured":
            if resolution.selected_has_markdown:
                report.add("info", "content_dir", f"Using configured content directory: {selected_path}")
            else:
                report.add(
                    "warning",
                    "content_dir",
                    f"Configured content directory exists but has no markdown files: {selected_path}",
                    "Add .md/.mdx files or update project content_dir.",
                )
            return

        if resolution.selected_has_markdown:
            report.add("info", "content_dir", f"Content directory found: {selected_path}")
            return

        report.add(
            "warning",
            "content_dir",
            f"Content directory exists but has no markdown files: {selected_path}",
            "Add .md/.mdx files, or configure a different project content_dir.",
        )

    def _check_required_clis(self, report: ProjectPreflightReport) -> None:
        if not self.required_clis:
            return

        for cli in self.required_clis:
            if shutil.which(cli):
                continue
            report.add(
                "error",
                "missing_cli",
                f"Required CLI not found on PATH: {cli}",
                "Run scripts/install_uv_tools.sh (or start via ./dashboard for local wrappers).",
            )

    def _check_gitignore(self, report: ProjectPreflightReport) -> None:
        """Check if automation data is excluded from git."""
        gitignore_path = self.repo_root / ".gitignore"
        
        if not gitignore_path.exists():
            # No gitignore - might not be a git repo, skip
            return
        
        try:
            content = gitignore_path.read_text()
            if ".github/automation/" not in content:
                report.add(
                    "warning",
                    "gitignore",
                    ".gitignore doesn't exclude automation data",
                    "Use dashboard 'Fix gitignore now' to add .github/automation/ exclusion.",
                )
        except IOError:
            # Can't read file, skip
            pass

    def fix_gitignore_exclusions(self) -> tuple[bool, str]:
        """Ensure `.github/automation/` is excluded in repo `.gitignore`."""
        gitignore_path = self.repo_root / ".gitignore"
        header = "# Automation data - do not commit"
        target = ".github/automation/"
        existing = ""

        try:
            if gitignore_path.exists():
                existing = gitignore_path.read_text()
                if target in existing:
                    return True, ".gitignore already excludes automation data."

            with open(gitignore_path, "a", encoding="utf-8") as handle:
                if existing and not existing.endswith("\n"):
                    handle.write("\n")
                if existing:
                    handle.write("\n")
                handle.write(f"{header}\n{target}\n")

            return True, f"Updated {gitignore_path}."
        except OSError as exc:
            return False, f"Failed to update .gitignore: {exc}"

    def _check_reddit_auth(self, report: ProjectPreflightReport) -> None:
        resolver = EnvResolver(repo_root=self.repo_root)
        token, source, saw_empty = resolver.resolve_key("REDDIT_REFRESH_TOKEN")

        if not token:
            if saw_empty:
                report.add(
                    "warning",
                    "reddit_token",
                    "REDDIT_REFRESH_TOKEN is present but empty.",
                    "Set a non-empty REDDIT_REFRESH_TOKEN value.",
                )
            else:
                report.add(
                    "warning",
                    "reddit_token",
                    "REDDIT_REFRESH_TOKEN not found (auto-post disabled).",
                    "Set token in env, ~/.config/automation/secrets.env, repo .env/.env.local, or automation/.env.",
                )
            return

        context = ExecutionContext(repo_root=self.repo_root)
        result = self.tool_registry.run_command(
            command=["automation-cli", "reddit", "auth-status"],
            context=context,
            timeout=45,
            env_overrides={"REDDIT_REFRESH_TOKEN": token},
        )
        if not result.success:
            report.add(
                "warning",
                "reddit_auth",
                "Could not validate Reddit auth status (auto-post may fail).",
                (result.stderr or result.stdout or "Check pageseeds reddit auth-status").strip(),
            )
            return

        payload = self._parse_json_payload(result.stdout)
        if payload is None:
            report.add(
                "warning",
                "reddit_auth",
                "Could not parse reddit auth-status output.",
                "Run `pageseeds reddit auth-status` manually to inspect output.",
            )
            return

        if payload.get("authenticated") is True:
            source_hint = source if source else "resolved source"
            report.add("info", "reddit_auth", f"Reddit auto-post auth ready ({source_hint}).")
            return

        error = payload.get("error") or "Unknown reddit auth error."
        report.add("warning", "reddit_auth", "Reddit auth not ready (auto-post disabled).", str(error))

    @staticmethod
    def _parse_json_payload(stdout: str) -> dict | None:
        if not stdout:
            return None
        try:
            return json.loads(stdout)
        except Exception:
            pass
        start = stdout.find("{")
        end = stdout.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(stdout[start : end + 1])
        except Exception:
            return None

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.repo_root))
        except ValueError:
            return str(path)
