"""Pure contracts for the disposable live Gemini validation harness.

This module has no network or application imports so its classification,
reporting, and review rules remain fast and deterministic under pytest.
"""

from __future__ import annotations

from collections.abc import Iterable
from statistics import median
from typing import Any


DOCS_CHECKED_ON = "2026-07-21"

_DOCUMENTED_MODELS: dict[str, dict[str, Any]] = {
    "gemini-3.1-flash-image": {
        "operations": {"generate", "edit", "safety"},
        "regions": {"global"},
        "stage": "GA",
        "source": (
            "https://docs.cloud.google.com/gemini-enterprise-agent-platform/"
            "models/gemini/3-1-flash-image"
        ),
    },
    "gemini-3.5-flash": {
        "operations": {"enhance"},
        # These are the documented Standard PayGo locations. Additional
        # locations require Provisioned Throughput and are not the app default.
        "regions": {"global", "us", "eu"},
        "stage": "GA",
        "source": (
            "https://docs.cloud.google.com/gemini-enterprise-agent-platform/"
            "models/gemini/3-5-flash"
        ),
    },
}

_QUALITY_PROFILES = {
    "enhance": {
        "criteria": (
            "intent_preservation",
            "sprite_specificity",
            "clarity_and_editability",
        ),
        "critical": {"intent_preservation"},
    },
    "generate": {
        "criteria": (
            "prompt_fidelity",
            "silhouette_readability",
            "style_adherence",
            "directional_correctness",
            "background_separation",
            "technical_cleanliness",
        ),
        "critical": {
            "prompt_fidelity",
            "silhouette_readability",
            "directional_correctness",
            "technical_cleanliness",
        },
    },
    "edit": {
        "criteria": (
            "identity_consistency",
            "motion_clarity",
            "directional_correctness",
            "style_consistency",
            "background_separation",
            "technical_cleanliness",
        ),
        "critical": {
            "identity_consistency",
            "motion_clarity",
            "directional_correctness",
            "technical_cleanliness",
        },
    },
}


def documented_models() -> dict[str, dict[str, Any]]:
    """Return a JSON-safe copy of the maintained support table."""

    return {
        model: {
            **details,
            "operations": sorted(details["operations"]),
            "regions": sorted(details["regions"]),
        }
        for model, details in _DOCUMENTED_MODELS.items()
    }


def support_expectation(model: str, region: str, operation: str) -> dict[str, str]:
    """Classify a model/region/operation against the checked documentation."""

    details = _DOCUMENTED_MODELS.get(model)
    if details is None or operation not in details["operations"]:
        return {
            "expectation": "unknown",
            "note": "not covered by the maintained documentation table",
        }
    if region in details["regions"]:
        return {
            "expectation": "supported",
            "note": f"documented {details['stage']} support",
        }
    return {
        "expectation": "unsupported",
        "note": "region is not documented for this model/operation",
    }


def classify_error(exc: Exception) -> str:
    """Reduce provider/transport errors to stable report categories."""

    code = getattr(exc, "code", None) or getattr(exc, "status_code", None) or ""
    text = f"{code} {type(exc).__name__} {exc}".lower()
    if any(marker in text for marker in ("safety", "prohibited", "blocklist")):
        return "safety_blocked"
    if isinstance(exc, TimeoutError) or any(
        marker in text for marker in ("timeout", "deadline exceeded")
    ):
        return "timeout"
    if any(marker in text for marker in ("429", "resource exhausted", "rate limit")):
        return "throttled"
    if any(marker in text for marker in ("403", "permission denied", "forbidden")):
        return "access_denied"
    if any(
        marker in text
        for marker in ("404", "not found", "unsupported location", "unsupported region")
    ):
        return "unavailable"
    return "error"


def percentile(values: Iterable[float], fraction: float) -> float | None:
    """Nearest-rank percentile for small, deliberately low-cost live samples."""

    ordered = sorted(values)
    if not ordered:
        return None
    rank = max(1, int(len(ordered) * fraction + 0.999999))
    return ordered[min(rank, len(ordered)) - 1]


def aggregate_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate repeated observations by operation/model/region."""

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for result in results:
        key = (result["operation"], result["model"], result["region"])
        groups.setdefault(key, []).append(result)

    aggregates = []
    for (operation, model, region), rows in sorted(groups.items()):
        latencies = [float(row["latency_ms"]) for row in rows]
        statuses = [row["status"] for row in rows]
        available = sum(status == "available" for status in statuses)
        aggregates.append(
            {
                "operation": operation,
                "model": model,
                "region": region,
                "expectation": rows[0]["expectation"],
                "samples": len(rows),
                "available": available,
                "statuses": sorted(set(statuses)),
                "median_ms": round(median(latencies)),
                "p95_ms": round(percentile(latencies, 0.95) or 0),
            }
        )
    return aggregates


def build_review_template(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Create the human-editable quality review file for successful artifacts."""

    cases = []
    for result in results:
        operation = result["operation"]
        profile = _QUALITY_PROFILES.get(operation)
        artifact = result.get("review_artifact")
        if result["status"] != "available" or profile is None or not artifact:
            continue
        cases.append(
            {
                "case_id": result["case_id"],
                "operation": operation,
                "artifact": artifact,
                "scores": {criterion: None for criterion in profile["criteria"]},
                "notes": "",
            }
        )
    return {
        "schema_version": 1,
        "scale": {
            "0": "unacceptable or missing",
            "1": "usable with visible correction",
            "2": "production-ready for this prototype",
        },
        "acceptance": "mean >= 1.5 and no critical criterion scored 0",
        "cases": cases,
    }


def evaluate_review(review: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a completed review without guessing unfilled human scores."""

    case_results = []
    for case in review.get("cases", []):
        operation = case.get("operation")
        profile = _QUALITY_PROFILES.get(operation)
        if profile is None:
            raise ValueError(f"unknown review operation: {operation}")
        scores = case.get("scores", {})
        expected = set(profile["criteria"])
        if set(scores) != expected:
            raise ValueError(f"review criteria do not match {operation} profile")
        values = list(scores.values())
        if any(value is None for value in values):
            case_results.append({"case_id": case["case_id"], "verdict": "pending"})
            continue
        if any(not isinstance(value, int) or value not in (0, 1, 2) for value in values):
            raise ValueError("review scores must be integers 0, 1, or 2")
        mean_score = sum(values) / len(values)
        critical_zero = any(scores[name] == 0 for name in profile["critical"])
        verdict = "pass" if mean_score >= 1.5 and not critical_zero else "fail"
        case_results.append(
            {
                "case_id": case["case_id"],
                "verdict": verdict,
                "mean_score": round(mean_score, 2),
            }
        )

    verdicts = {case["verdict"] for case in case_results}
    if not case_results or "pending" in verdicts:
        verdict = "pending"
    elif "fail" in verdicts:
        verdict = "fail"
    else:
        verdict = "pass"
    return {"verdict": verdict, "cases": case_results}
