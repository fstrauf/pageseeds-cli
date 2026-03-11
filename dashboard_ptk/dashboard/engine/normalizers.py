"""Deterministic normalizers for agent raw output."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .types import AgentRawResult, NormalizedResult, NormalizationError


class NormalizerRegistry:
    """Registry of deterministic output normalizers."""

    def __init__(self):
        self._normalizers = {
            "passthrough_markdown": self._passthrough_markdown,
            "keyword_research": self._normalize_keyword_research,
            "investigation": self._normalize_investigation,
            "specification": self._normalize_specification,
            "reddit_opportunities": self._normalize_reddit_opportunities,
        }

    def normalize(
        self,
        normalizer_id: str,
        raw: AgentRawResult,
        context: dict[str, Any],
    ) -> NormalizedResult:
        """Normalize raw output and persist structured artifact."""
        normalizer = self._normalizers.get(normalizer_id)
        if not normalizer:
            return NormalizedResult(success=False, error=f"Unknown normalizer: {normalizer_id}")

        try:
            payload = normalizer(raw, context)
        except NormalizationError as exc:
            return NormalizedResult(success=False, error=str(exc))
        except Exception as exc:  # pragma: no cover - defensive path
            return NormalizedResult(success=False, error=f"Normalization failed: {exc}")

        output_path = self._write_normalized_payload(payload, context)
        return NormalizedResult(success=True, payload=payload, output_path=output_path)

    def _write_normalized_payload(self, payload: dict[str, Any], context: dict[str, Any]) -> str | None:
        task_results_dir = context.get("task_results_dir")
        task_id = context.get("task_id")
        artifact_name = context.get("artifact_name", "normalized")

        if not task_results_dir or not task_id:
            return None

        normalized_dir = Path(task_results_dir) / task_id / "normalized"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        output_path = normalized_dir / f"{artifact_name}.json"
        output_path.write_text(json.dumps(payload, indent=2))
        return str(output_path)

    def _extract_json_object(self, text: str) -> dict[str, Any] | None:
        patterns = [
            r"```json\s*(\{[\s\S]*?\})\s*```",
            r"(\{[\s\S]*\})",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, text):
                try:
                    data = json.loads(match)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    continue
        return None

    def _passthrough_markdown(self, raw: AgentRawResult, context: dict[str, Any]) -> dict[str, Any]:
        if not raw.output_text.strip():
            raise NormalizationError("Agent produced empty output")
        return {
            "content": raw.output_text,
            "provider": raw.provider,
            "source": raw.output_path,
        }

    def _normalize_keyword_research(self, raw: AgentRawResult, context: dict[str, Any]) -> dict[str, Any]:
        data = self._extract_json_object(raw.output_text)
        if not data:
            raise NormalizationError("Unable to parse keyword research JSON from agent output")

        candidates = data.get("keyword_candidates", [])
        if not isinstance(candidates, list) or not candidates:
            raise NormalizationError("keyword_candidates is missing or empty")

        normalized_candidates = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            keyword = str(item.get("keyword", "")).strip()
            if not keyword:
                continue
            normalized_candidates.append(
                {
                    "keyword": keyword,
                    "estimated_volume": item.get("estimated_volume", "unknown"),
                    "estimated_kd": item.get("estimated_kd", "unknown"),
                    "intent": item.get("intent", "unknown"),
                    "opportunity_score": item.get("opportunity_score", "unknown"),
                    "proposed_title": item.get("proposed_title", f"Write article: {keyword}"),
                }
            )

        if not normalized_candidates:
            raise NormalizationError("No valid keyword candidates in output")

        return {
            "summary": data.get("summary", ""),
            "keyword_candidates": normalized_candidates,
            "optimize_candidates": data.get("optimize_candidates", []),
            "source": raw.output_path,
        }

    def _normalize_investigation(self, raw: AgentRawResult, context: dict[str, Any]) -> dict[str, Any]:
        data = self._extract_json_object(raw.output_text)
        if not data:
            raise NormalizationError("Unable to parse investigation JSON from agent output")

        findings = data.get("findings") or data.get("issues")
        if findings is None:
            raise NormalizationError("Investigation output must include findings or issues")

        return {
            "summary": data.get("summary", ""),
            "findings": findings,
            "recommended_tasks": data.get("recommended_tasks", []),
            "source": raw.output_path,
        }

    def _normalize_specification(self, raw: AgentRawResult, context: dict[str, Any]) -> dict[str, Any]:
        text = raw.output_text.strip()
        if not text:
            raise NormalizationError("Specification output is empty")

        required_headers = ["## Problem", "## Solution", "## Implementation Steps"]
        missing_headers = [header for header in required_headers if header not in text]
        if missing_headers:
            raise NormalizationError(f"Specification missing sections: {', '.join(missing_headers)}")

        return {
            "markdown": text,
            "headers_present": ["## Problem", "## Root Cause", "## Solution", "## Implementation Steps", "## Files to Modify", "## Acceptance Criteria"],
            "source": raw.output_path,
        }

    def _normalize_reddit_opportunities(self, raw: AgentRawResult, context: dict[str, Any]) -> dict[str, Any]:
        text = raw.output_text
        opportunities = []
        for block in re.split(r"\n---+\n", text):
            title_match = re.search(r"\*\*Post:\*\*\s*(.+)", block)
            score_match = re.search(r"\*\*Score:\*\*\s*([0-9.]+)/10", block)
            url_match = re.search(r"\*\*URL:\*\*\s*(.+)", block)
            if title_match and score_match:
                opportunities.append(
                    {
                        "post": title_match.group(1).strip(),
                        "score": score_match.group(1).strip(),
                        "url": url_match.group(1).strip() if url_match else "",
                    }
                )

        if not opportunities:
            raise NormalizationError("No Reddit opportunities parsed from output")

        return {
            "opportunities": opportunities,
            "source": raw.output_path,
        }
