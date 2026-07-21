"""Pure behavior tests for the disposable live Gemini validation harness."""

from pathlib import Path
import sys


_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.live_model_validation import (  # noqa: E402
    aggregate_results,
    build_review_template,
    classify_error,
    evaluate_review,
    support_expectation,
)
from scripts.validate_live_models import main as validation_main  # noqa: E402


def test_documented_support_matches_configured_model_roles_and_regions():
    assert support_expectation(
        "gemini-3.1-flash-image", "global", "generate"
    )["expectation"] == "supported"
    assert support_expectation(
        "gemini-3.1-flash-image", "eu", "edit"
    )["expectation"] == "unsupported"
    assert support_expectation(
        "gemini-3.5-flash", "eu", "enhance"
    )["expectation"] == "supported"
    assert support_expectation(
        "custom-model", "global", "generate"
    )["expectation"] == "unknown"


def test_errors_are_classified_for_an_actionable_availability_matrix():
    assert classify_error(RuntimeError("404 publisher model was not found")) == "unavailable"
    assert classify_error(RuntimeError("429 resource exhausted")) == "throttled"
    assert classify_error(TimeoutError("deadline exceeded")) == "timeout"
    assert classify_error(RuntimeError("finish reason: IMAGE_SAFETY")) == "safety_blocked"
    assert classify_error(RuntimeError("403 permission denied")) == "access_denied"
    assert classify_error(RuntimeError("socket closed")) == "error"


def test_repeated_results_are_aggregated_without_claiming_false_precision():
    rows = [
        {
            "operation": "generate",
            "model": "image-model",
            "region": "global",
            "expectation": "supported",
            "status": "available",
            "latency_ms": latency,
        }
        for latency in (1_000, 2_000, 8_000)
    ]

    aggregate = aggregate_results(rows)[0]

    assert aggregate["available"] == 3
    assert aggregate["samples"] == 3
    assert aggregate["median_ms"] == 2_000
    assert aggregate["p95_ms"] == 8_000


def test_manual_review_requires_complete_scores_and_critical_quality():
    results = [
        {
            "case_id": "global-generate-1",
            "operation": "generate",
            "status": "available",
            "review_artifact": "global/generate-1-clean.png",
        }
    ]
    review = build_review_template(results)
    assert evaluate_review(review)["verdict"] == "pending"

    scores = review["cases"][0]["scores"]
    for criterion in scores:
        scores[criterion] = 2
    assert evaluate_review(review)["verdict"] == "pass"

    scores["silhouette_readability"] = 0
    assert evaluate_review(review)["verdict"] == "fail"

    scores["silhouette_readability"] = 2
    scores["directional_correctness"] = 0
    assert evaluate_review(review)["verdict"] == "fail"


def test_finalize_refreshes_report_and_returns_quality_verdict(tmp_path):
    results = [
        {
            "case_id": "global-s1-enhance",
            "operation": "enhance",
            "model": "gemini-3.5-flash",
            "region": "global",
            "sample": 1,
            "expectation": "supported",
            "status": "available",
            "latency_ms": 1000,
            "review_artifact": "global/enhance-1.txt",
        }
    ]
    payload = {
        "run_id": "test-run",
        "run_dir": str(tmp_path),
        "started_at": "2026-07-21T00:00:00+00:00",
        "docs_checked_on": "2026-07-21",
        "config": {
            "text_model": "gemini-3.5-flash",
            "generate_model": "gemini-3.1-flash-image",
            "edit_model": "gemini-3.1-flash-image",
            "regions": ["global"],
        },
        "results": results,
        "aggregates": aggregate_results(results),
        "automated": {"verdict": "pass", "failures": []},
    }
    review = build_review_template(results)
    for score in review["cases"][0]["scores"]:
        review["cases"][0]["scores"][score] = 2
    (tmp_path / "matrix.json").write_text(__import__("json").dumps(payload), encoding="utf-8")
    (tmp_path / "review.json").write_text(__import__("json").dumps(review), encoding="utf-8")

    assert validation_main(["--finalize", str(tmp_path)]) == 0
    assert "Manual quality verdict: **PASS**" in (tmp_path / "MATRIX.md").read_text(
        encoding="utf-8"
    )
