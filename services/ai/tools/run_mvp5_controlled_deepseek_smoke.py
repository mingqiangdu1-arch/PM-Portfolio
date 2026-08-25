"""Run one explicitly authorized, redacted DeepSeek Requirement clarification smoke.

The credential is accepted through stdin or ``DEEPSEEK_API_KEY`` and is never
printed. The command performs exactly one provider request and never retries.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
import sys

from app.providers.base import ProviderError
from app.providers.openai_compatible import OpenAICompatibleAdapter
from app.providers.profiles.deepseek import deepseek_profile
from app.requirement_clarification.models import ClarificationSource, RequirementClarifyTask
from app.requirement_clarification.real_provider import RealRequirementClarifier


def _authorized() -> bool:
    return os.getenv("AI_LIVE_PROVIDER_AUTHORIZED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _credential() -> str:
    value = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if value:
        return value
    if not sys.stdin.isatty():
        return sys.stdin.readline().strip()
    return ""


def _task() -> RequirementClarifyTask:
    return RequirementClarifyTask.model_validate(
        {
            "schema_version": "0.2.0",
            "task_public_id": "mvp5-controlled-smoke",
            "user_id": "1",
            "project_id": "1",
            "project_version_id": "1",
            "module": "product_design",
            "task_type": "requirement.clarify",
            "target": {
                "object_type": "requirement",
                "object_id": "1",
                "object_version_id": "1",
            },
            "target_snapshot_hash": hashlib.sha256(
                b"mvp5-controlled-deepseek-smoke"
            ).hexdigest(),
            "source_ref_ids": ["1"],
            "capability_selection": None,
            "risk_acceptances": [],
            "command_id": "mvp5-controlled-smoke-command",
            "trace_id": "mvp5-controlled-smoke-trace",
            "requested_at": datetime.now(UTC).isoformat(),
            "input": {
                "mode": "auto",
                "round_no": 0,
                "continue_deep_confirmed": False,
            },
            "status": "queued",
        }
    )


def _source() -> ClarificationSource:
    content_hash = hashlib.sha256(
        "我需要一个可由团队审阅和确认的任务审批流程。".encode("utf-8")
    ).hexdigest()
    return ClarificationSource(
        source_type="requirement_version",
        source_id="1",
        source_version_id="1",
        content_fingerprint=content_hash,
        label="Controlled smoke Requirement Version",
        token_count=32,
    )


def main() -> int:
    if not _authorized():
        print(json.dumps({"gate": "BLOCKED", "reason": "LIVE_PROVIDER_NOT_AUTHORIZED"}))
        return 2
    api_key = _credential()
    if not api_key:
        print(json.dumps({"gate": "BLOCKED", "reason": "PROVIDER_KEY_NOT_PRESENT"}))
        return 2

    try:
        adapter = OpenAICompatibleAdapter(
            deepseek_profile(),
            api_key=api_key,
            network_authorized=True,
        )
        execution = RealRequirementClarifier(
            adapter,
            model="deepseek-v4-flash",
        ).run(
            _task(),
            (_source(),),
            requirement_content={
                "raw_input": "我需要一个可由团队审阅和确认的任务审批流程。"
            },
        )
        provider = execution.provider_response or {}
        usage = provider.get("usage") or {}
        source_refs = execution.result["assessment"]["source_refs"]
        evidence = {
            "gate": "PASS",
            "truth_label": execution.truth_label,
            "formalization_allowed": execution.formalization_allowed,
            "provider": provider.get("provider"),
            "model": provider.get("model"),
            "finish_reason": provider.get("finish_reason"),
            "result_kind": execution.result.get("result_kind"),
            "result_status": execution.result.get("status"),
            "source_binding_valid": bool(source_refs)
            and source_refs[0].get("content_hash") == _source().content_fingerprint,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "billed_tokens": usage.get("billed_tokens"),
            "estimated_cost": usage.get("estimated_cost"),
            "currency_code": usage.get("currency_code"),
            "cost_source": usage.get("cost_source"),
            "pricing_version": usage.get("pricing_version"),
        }
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        return 0 if evidence["source_binding_valid"] else 3
    except ProviderError as exc:
        print(
            json.dumps(
                {
                    "gate": "FAIL",
                    "reason": f"PROVIDER_{exc.error_class.upper()}",
                    "failure_detail": str(exc),
                    "retryable": exc.retryable,
                },
                sort_keys=True,
            )
        )
        return 3
    except Exception as exc:  # Failure evidence intentionally excludes exception text.
        print(
            json.dumps(
                {
                    "gate": "FAIL",
                    "reason": "CONTROLLED_SMOKE_FAILED",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
