"""
Setup validation - check everything is configured correctly
"""
import json
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@dataclass
class ValidationIssue:
    """A setup issue that needs to be fixed."""
    severity: str  # "error" or "warning"
    message: str
    fix_hint: str


@dataclass
class ValidationResult:
    """Result of setup validation."""
    issues: list[ValidationIssue] = field(default_factory=list)
    
    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]
    
    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]
    
    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


class SetupValidator:
    """Validates the user's setup before running."""
    
    REQUIRED_CLIS = ["pageseeds"]
    AGENT_CLI = "kimi"
    
    def __init__(self):
        self.user_config_dir = Path.home() / ".config/automation"
        self.projects_file = self.user_config_dir / "projects.json"
        self.secrets_file = self.user_config_dir / "secrets.env"
    
    def validate(self) -> ValidationResult:
        """Run all validations and return results."""
        result = ValidationResult()
        
        self._check_cli_tools(result)
        self._check_agent_cli(result)
        self._check_config_directory(result)
        self._check_projects_config(result)
        self._check_secrets(result)
        
        return result
    
    def _check_cli_tools(self, result: ValidationResult):
        """Check CLI tools are installed."""
        for cli in self.REQUIRED_CLIS:
            if cli == "pageseeds":
                display_name = "pageseeds (unified CLI)"
            else:
                display_name = cli
            if not shutil.which(cli):
                result.issues.append(ValidationIssue(
                    severity="error",
                    message=f"Missing CLI: {display_name}",
                    fix_hint="Install with: ./scripts/install_uv_tools.sh"
                ))
    
    def _check_agent_cli(self, result: ValidationResult):
        """Check agent CLI is available."""
        if not shutil.which(self.AGENT_CLI):
            result.issues.append(ValidationIssue(
                severity="warning",
                message=f"Agent CLI not found: {self.AGENT_CLI}",
                fix_hint="Install kimi-code CLI from: https://github.com/moonshot-ai/kimi-code"
            ))
    
    def _check_config_directory(self, result: ValidationResult):
        """Check config directory exists."""
        if not self.user_config_dir.exists():
            result.issues.append(ValidationIssue(
                severity="error",
                message=f"Config directory not found: {self.user_config_dir}",
                fix_hint=f"Create it: mkdir -p {self.user_config_dir}"
            ))
    
    def _check_projects_config(self, result: ValidationResult):
        """Check projects.json exists and is valid."""
        if not self.projects_file.exists():
            result.issues.append(ValidationIssue(
                severity="error",
                message=f"Projects config not found: {self.projects_file}",
                fix_hint="Create it with: ./scripts/setup.sh or manually"
            ))
            return
        
        try:
            data = json.loads(self.projects_file.read_text())
            projects = data.get("projects", [])
            
            if not projects:
                result.issues.append(ValidationIssue(
                    severity="warning",
                    message="No projects configured in projects.json",
                    fix_hint=f"Add projects to: {self.projects_file}"
                ))
            else:
                # Validate each project
                for i, proj in enumerate(projects):
                    if "website_id" not in proj:
                        result.issues.append(ValidationIssue(
                            severity="error",
                            message=f"Project {i+1} missing 'website_id'",
                            fix_hint="Add website_id to project config"
                        ))
                    if "repo_root" not in proj:
                        result.issues.append(ValidationIssue(
                            severity="error",
                            message=f"Project {i+1} missing 'repo_root'",
                            fix_hint="Add repo_root to project config"
                        ))
                    else:
                        repo_path = Path(proj["repo_root"]).expanduser()
                        if not repo_path.exists():
                            result.issues.append(ValidationIssue(
                                severity="warning",
                                message=f"Project '{proj.get('name', proj.get('website_id', f'#{i+1}'))}' repo not found: {repo_path}",
                                fix_hint="Check repo_root path in projects.json"
                            ))
                        
        except json.JSONDecodeError as e:
            result.issues.append(ValidationIssue(
                severity="error",
                message=f"Invalid projects.json: {e}",
                fix_hint="Fix JSON syntax or regenerate the file"
            ))
        except Exception as e:
            result.issues.append(ValidationIssue(
                severity="error",
                message=f"Error reading projects.json: {e}",
                fix_hint="Check file permissions"
            ))
    
    def _check_secrets(self, result: ValidationResult):
        """Check secrets file exists."""
        if not self.secrets_file.exists():
            result.issues.append(ValidationIssue(
                severity="warning",
                message=f"Secrets file not found: {self.secrets_file}",
                fix_hint="Create it and add your API keys"
            ))
    
    def print_report(self, result: ValidationResult):
        """Print validation report."""
        if result.is_valid and not result.warnings:
            console.print(Panel(
                "[bold green]✓ All checks passed![/bold green]\n\n"
                "Your setup is ready to use.",
                title="Setup Validation",
                border_style="green"
            ))
            return
        
        # Build report content
        sections = []
        
        if result.errors:
            error_table = Table(show_header=False, box=None)
            error_table.add_column(style="red")
            error_table.add_column()
            for issue in result.errors:
                error_table.add_row("✗", f"[bold]{issue.message}[/bold]")
                error_table.add_row("", f"[dim]Fix: {issue.fix_hint}[/dim]")
            sections.append(("[bold red]Errors (must fix)[/bold red]", error_table))
        
        if result.warnings:
            warn_table = Table(show_header=False, box=None)
            warn_table.add_column(style="yellow")
            warn_table.add_column()
            for issue in result.warnings:
                warn_table.add_row("⚠", f"[bold]{issue.message}[/bold]")
                warn_table.add_row("", f"[dim]Fix: {issue.fix_hint}[/dim]")
            sections.append(("[bold yellow]Warnings (optional)[/bold yellow]", warn_table))
        
        # Print everything in one panel
        from rich.text import Text
        content = Text()
        for i, (title, table) in enumerate(sections):
            if i > 0:
                content.append("\n\n")
            content.append(Text.from_markup(title))
            content.append("\n")
            # Add table as string
            with console.capture() as capture:
                console.print(table)
            content.append(capture.get())
        
        if not result.is_valid:
            content.append("\n")
            content.append(Text.from_markup(
                f"[bold]Run setup:[/bold] [cyan]./scripts/setup.sh[/cyan]"
            ))
        
        border_style = "yellow" if result.is_valid else "red"
        console.print(Panel(content, title="Setup Validation", border_style=border_style))


def check_setup() -> bool:
    """Quick setup check. Returns True if valid."""
    validator = SetupValidator()
    result = validator.validate()
    validator.print_report(result)
    return result.is_valid


if __name__ == "__main__":
    check_setup()
