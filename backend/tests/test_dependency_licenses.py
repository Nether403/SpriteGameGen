"""Deterministic dependency-license policy tests."""

from pathlib import Path
import sys


_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.check_dependency_licenses import (  # noqa: E402
    PythonDistribution,
    apply_reviewed_exceptions,
    audit_npm_lock,
    audit_python_distributions,
    classify_license,
    format_report,
)


def _distribution(
    name: str,
    license_value: str,
    *,
    requires: tuple[str, ...] = (),
    version: str = "1.0",
) -> PythonDistribution:
    return PythonDistribution(
        name=name,
        version=version,
        license_expression=license_value,
        requirements=requires,
    )


def test_python_audit_follows_only_the_installed_runtime_dependency_closure():
    distributions = [
        _distribution(
            "sprite-game-asset-tool",
            "",
            requires=(
                "runtime-lib>=1",
                "feature-lib[fast]>=2",
                "dev-lib>=1; extra == 'dev'",
            ),
        ),
        _distribution("runtime-lib", "MIT", requires=("transitive-lib>=1",)),
        _distribution(
            "feature-lib",
            "Apache-2.0",
            requires=("fast-helper>=1; extra == 'fast'",),
        ),
        _distribution("transitive-lib", "BSD-3-Clause"),
        _distribution("fast-helper", "ISC"),
        _distribution("dev-lib", "GPL-3.0-only"),
        _distribution("unrelated-installed-tool", "AGPL-3.0-only"),
    ]

    results = audit_python_distributions(distributions)

    assert [result.name for result in results] == [
        "fast-helper",
        "feature-lib",
        "runtime-lib",
        "transitive-lib",
    ]
    assert all(result.allowed for result in results)


def test_npm_audit_uses_lockfile_runtime_markers_and_skips_dev_dependencies():
    lock_data = {
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "app"},
            "node_modules/runtime": {"version": "1.0.0", "license": "MIT"},
            "node_modules/runtime/node_modules/helper": {
                "version": "2.0.0",
                "license": "Apache-2.0",
            },
            "node_modules/dev-only": {
                "version": "3.0.0",
                "license": "GPL-3.0-only",
                "dev": True,
            },
            "node_modules/dev-optional": {
                "version": "4.0.0",
                "license": "AGPL-3.0-only",
                "devOptional": True,
            },
        },
    }

    results = audit_npm_lock(lock_data)

    assert [(result.name, result.category) for result in results] == [
        ("helper", "permissive"),
        ("runtime", "permissive"),
    ]


def test_policy_rejects_copyleft_sspl_and_unknown_licenses():
    assert classify_license("MIT") == "permissive"
    assert classify_license("MIT-CMU") == "permissive"
    assert classify_license("3-Clause BSD License") == "permissive"
    assert classify_license("Apache-2.0 OR BSD-3-Clause") == "permissive"
    assert classify_license("GPL-3.0-only") == "copyleft"
    assert classify_license("SSPL-1.0") == "sspl"
    assert classify_license("") == "unknown"
    assert classify_license("Custom-Proprietary-License") == "unknown"


def test_missing_required_python_metadata_is_an_unknown_failure():
    results = audit_python_distributions(
        [_distribution("sprite-game-asset-tool", "", requires=("missing-lib>=1",))]
    )

    assert [(result.name, result.category, result.allowed) for result in results] == [
        ("missing-lib", "unknown", False)
    ]


def test_reviewed_exception_must_match_exact_metadata_and_have_a_reason():
    result = audit_npm_lock(
        {
            "lockfileVersion": 3,
            "packages": {
                "": {},
                "node_modules/legacy-runtime": {
                    "version": "1.2.3",
                    "license": "Custom-License",
                },
            },
        }
    )[0]
    exception_key = ("npm", "legacy-runtime", "1.2.3", "Custom-License")

    assert apply_reviewed_exceptions([result], {})[0].allowed is False
    assert apply_reviewed_exceptions([result], {exception_key: "Reviewed terms."})[
        0
    ].exception_reason == "Reviewed terms."
    assert apply_reviewed_exceptions([result], {exception_key: "  "})[0].allowed is False


def test_report_is_sorted_and_does_not_disclose_local_context():
    python_results = audit_python_distributions(
        [
            _distribution(
                "sprite-game-asset-tool", "", requires=("zebra>=1", "alpha>=1")
            ),
            _distribution("zebra", "MIT"),
            _distribution("alpha", "GPL-3.0-only"),
        ]
    )
    npm_results = audit_npm_lock(
        {
            "lockfileVersion": 3,
            "packages": {
                "": {},
                "node_modules/middle": {"version": "2.0.0", "license": "ISC"},
            },
        }
    )

    report = format_report([*python_results, *npm_results])

    assert report.splitlines() == [
        "PASS npm middle: permissive",
        "FAIL python alpha: copyleft",
        "PASS python zebra: permissive",
        "Dependency license check: FAIL (1 blocked)",
    ]
    assert str(_ROOT) not in report
    assert "PATH=" not in report
