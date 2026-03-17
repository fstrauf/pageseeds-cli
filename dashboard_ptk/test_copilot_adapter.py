#!/usr/bin/env python3
"""Quick smoke-test for CopilotAdapter — run directly without the dashboard.

Usage:
    uv run python test_copilot_adapter.py
    uv run python test_copilot_adapter.py --prompt "Say hello in one sentence"
    uv run python test_copilot_adapter.py --model claude-opus-4.6
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dashboard.engine.agent_runtime import CopilotAdapter, KimiAdapter
from dashboard.engine.types import PromptSpec


def main():
    parser = argparse.ArgumentParser(description="Test agent adapter directly")
    parser.add_argument("--prompt", default="Reply with exactly: ADAPTER_OK", help="Prompt to send")
    parser.add_argument("--model", default=None, help="Override COPILOT_MODEL")
    parser.add_argument("--provider", default="copilot", choices=["copilot", "kimi"])
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    if args.provider == "copilot":
        import os
        if args.model:
            os.environ["COPILOT_MODEL"] = args.model
        adapter = CopilotAdapter()
        print(f"Provider : copilot")
        print(f"Model    : {os.environ.get('COPILOT_MODEL', adapter._DEFAULT_MODEL)}")
    else:
        adapter = KimiAdapter()
        print(f"Provider : kimi")

    print(f"Available: {adapter.is_available()}")
    if not adapter.is_available():
        print("ERROR: adapter not available — check CLI is installed")
        sys.exit(1)

    print(f"Prompt   : {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    print("-" * 60)

    result = adapter.run(
        PromptSpec(text=args.prompt, timeout=args.timeout),
        cwd=Path.cwd(),
    )

    print(f"Success  : {result.success}")
    if result.error:
        print(f"Error    : {result.error}")
    if result.output_text:
        print(f"Output   :\n{result.output_text[:500]}")
    else:
        print("Output   : (empty)")

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
