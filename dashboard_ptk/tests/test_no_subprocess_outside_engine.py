"""Static guard: subprocess.run calls are only allowed in dashboard/engine."""
from __future__ import annotations

from pathlib import Path


def test_no_subprocess_run_outside_engine() -> None:
    root = Path(__file__).resolve().parents[1] / "dashboard"
    violations: list[Path] = []

    for file_path in root.rglob("*.py"):
        content = file_path.read_text()
        if "subprocess.run(" in content:
            normalized = str(file_path).replace("\\", "/")
            if "/dashboard/engine/" not in normalized:
                violations.append(file_path)

    assert not violations, f"Found subprocess.run outside engine: {[str(v) for v in violations]}"


if __name__ == "__main__":
    test_no_subprocess_run_outside_engine()
    print("ok")
