"""Version checking utilities for seo-cli.

Fetches remote pyproject.toml from GitHub and compares versions.
Supports both public repos (raw content) and private repos (GitHub API with token).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError


# GitHub repository configuration
GITHUB_OWNER = "fstrauf"
GITHUB_REPO = "pageseeds-cli"
DEFAULT_BRANCH = "main"


@dataclass
class VersionInfo:
    """Version information for a package."""
    name: str
    local_version: str
    remote_version: str | None
    is_outdated: bool
    error: str | None = None


def _has_github_token() -> bool:
    """Check if GitHub token is available."""
    return bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))


def _fetch_with_auth(url: str, timeout: int = 10) -> bytes | None:
    """Fetch URL with optional GitHub token authentication."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github.v3+json"
    
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as response:
            return response.read()
    except URLError:
        return None
    except Exception:
        return None


def _fetch_remote_pyproject(package_path: str, branch: str = DEFAULT_BRANCH) -> dict | None:
    """Fetch and parse pyproject.toml from GitHub."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    
    if token:
        from urllib.parse import quote
        path = quote(f"packages/{package_path}/pyproject.toml")
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}?ref={branch}"
        
        try:
            content = _fetch_with_auth(url, timeout=10)
            if content is None:
                return None
            
            import json
            data = json.loads(content.decode("utf-8"))
            import base64
            file_content = base64.b64decode(data["content"]).decode("utf-8")
            return tomllib.loads(file_content)
        except Exception:
            return None
    else:
        url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{branch}/packages/{package_path}/pyproject.toml"
        
        try:
            with urlopen(url, timeout=5) as response:
                content = response.read().decode("utf-8")
                return tomllib.loads(content)
        except URLError:
            return None
        except Exception:
            return None


def _find_repo_root() -> Path | None:
    """Find the repository root by looking for .github directory."""
    here = Path(__file__).resolve().parent
    repo_root = here
    
    while repo_root.parent != repo_root:
        if (repo_root / ".github").exists() and (repo_root / "packages").exists():
            return repo_root
        repo_root = repo_root.parent
    
    return None


def _read_local_pyproject(package_path: str) -> dict | None:
    """Read local pyproject.toml for a package."""
    repo_root = _find_repo_root()
    
    if repo_root:
        pyproject_path = repo_root / "packages" / package_path / "pyproject.toml"
        
        try:
            if pyproject_path.exists():
                content = pyproject_path.read_text(encoding="utf-8")
                return tomllib.loads(content)
        except Exception:
            pass
    
    # Fallback for installed packages
    try:
        if package_path == "seo-cli":
            from . import __file__ as module_file
            here = Path(module_file).resolve().parent
            pyproject_path = here.parent.parent / "pyproject.toml"
            if pyproject_path.exists():
                content = pyproject_path.read_text(encoding="utf-8")
                return tomllib.loads(content)
    except Exception:
        pass
    
    return None


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse version string to comparable tuple."""
    import re
    parts = re.split(r'[.-]', version_str)
    numeric_parts = []
    for part in parts:
        try:
            numeric_parts.append(int(part))
        except ValueError:
            numeric_parts.append(-1)
    return tuple(numeric_parts)


def _is_outdated(local: str, remote: str) -> bool:
    """Check if local version is outdated compared to remote."""
    local_tuple = _parse_version(local)
    remote_tuple = _parse_version(remote)
    return remote_tuple > local_tuple


def check_version(package_path: str, package_name: str) -> VersionInfo:
    """Check if a package is outdated."""
    local_pyproject = _read_local_pyproject(package_path)
    if local_pyproject is None:
        return VersionInfo(
            name=package_name,
            local_version="unknown",
            remote_version=None,
            is_outdated=False,
            error="Could not read local pyproject.toml"
        )
    
    try:
        local_version = local_pyproject["project"]["version"]
    except KeyError:
        return VersionInfo(
            name=package_name,
            local_version="unknown",
            remote_version=None,
            is_outdated=False,
            error="Local pyproject.toml missing version"
        )
    
    remote_pyproject = _fetch_remote_pyproject(package_path)
    if remote_pyproject is None:
        return VersionInfo(
            name=package_name,
            local_version=local_version,
            remote_version=None,
            is_outdated=False,
            error="Could not fetch remote version from GitHub"
        )
    
    try:
        remote_version = remote_pyproject["project"]["version"]
    except KeyError:
        return VersionInfo(
            name=package_name,
            local_version=local_version,
            remote_version=None,
            is_outdated=False,
            error="Remote pyproject.toml missing version"
        )
    
    is_outdated = _is_outdated(local_version, remote_version)
    
    return VersionInfo(
        name=package_name,
        local_version=local_version,
        remote_version=remote_version,
        is_outdated=is_outdated
    )


def format_version_output(info: VersionInfo) -> str:
    """Format version info for display."""
    lines = []
    
    if info.error:
        lines.append(f"{info.name}: {info.local_version}")
        if "Could not fetch remote" in (info.error or "") and not _has_github_token():
            lines.append(f"  ⚠️  {info.error}")
            lines.append(f"     (For private repos, set GITHUB_TOKEN or GH_TOKEN environment variable)")
        else:
            lines.append(f"  ⚠️  {info.error}")
        return "\n".join(lines)
    
    if info.is_outdated:
        lines.append(f"{info.name}: {info.local_version} → {info.remote_version}")
        lines.append(f"  ⚠️  Update available! Run: cd ~/automation && git pull")
    else:
        lines.append(f"{info.name}: {info.local_version} (up to date)")
    
    return "\n".join(lines)


def print_version_check(package_path: str, package_name: str) -> None:
    """Check and print version info for a single package."""
    info = check_version(package_path, package_name)
    print(format_version_output(info))
