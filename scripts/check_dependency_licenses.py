"""Audit installed Python and locked npm runtime dependency licenses.

The checker is intentionally offline. Python dependencies come from installed
distribution metadata; npm dependencies come from the committed lockfile.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
import importlib.metadata
import json
from pathlib import Path
import re
from typing import Any

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement


PROJECT_DISTRIBUTION = "sprite-game-asset-tool"
PACKAGE_LOCK = Path(__file__).resolve().parents[1] / "frontend" / "package-lock.json"

# Exceptions are exact so a package version or declared-license change requires
# another review. Keep this table small and give every entry a concrete reason.
REVIEWED_EXCEPTIONS: dict[tuple[str, str, str, str], str] = {
    (
        "python",
        "certifi",
        "2026.4.22",
        "MPL-2.0",
    ): "Required TLS trust-data dependency; approved for this exact reviewed release.",
}

_ALLOWED_LICENSE_IDS = {
    "0BSD",
    "APACHE-2.0",
    "BSD-2-CLAUSE",
    "BSD-3-CLAUSE",
    "BSL-1.0",
    "CC0-1.0",
    "HPND",
    "ISC",
    "MIT",
    "MIT-0",
    "MIT-CMU",
    "PSF-2.0",
    "PYTHON-2.0",
    "UNLICENSE",
    "ZLIB",
}
_ALLOWED_EXCEPTION_IDS = {"LLVM-EXCEPTION"}
_LICENSE_ALIASES = {
    "APACHE 2.0": "Apache-2.0",
    "APACHE LICENSE 2.0": "Apache-2.0",
    "APACHE LICENSE, VERSION 2.0": "Apache-2.0",
    "APACHE SOFTWARE LICENSE": "Apache-2.0",
    "BSD": "BSD-3-Clause",
    "3-CLAUSE BSD LICENSE": "BSD-3-Clause",
    "BSD LICENSE": "BSD-3-Clause",
    "ISC LICENSE": "ISC",
    "MIT LICENSE": "MIT",
    "PYTHON SOFTWARE FOUNDATION LICENSE": "PSF-2.0",
    "THE UNLICENSE": "Unlicense",
}
_CLASSIFIER_LICENSES = {
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "Historical Permission Notice and Disclaimer (HPND)": "HPND",
    "ISC License (ISCL)": "ISC",
    "MIT License": "MIT",
    "Python Software Foundation License": "PSF-2.0",
}
_COPYLEFT_PATTERN = re.compile(
    r"(?:AGPL|CDDL|CPAL|EPL|EUPL|GPL|LGPL|MPL|OSL|RPL)-?", re.IGNORECASE
)
_EXPRESSION_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*")
_EXPRESSION_OPERATORS = {"AND", "OR", "WITH"}


@dataclass(frozen=True)
class PythonDistribution:
    """The installed metadata needed by the pure Python audit."""

    name: str
    version: str = ""
    license_expression: str = ""
    license_text: str = ""
    classifiers: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()


@dataclass(frozen=True)
class LicenseResult:
    ecosystem: str
    name: str
    version: str
    declared_license: str
    category: str
    allowed: bool
    exception_reason: str = ""


class DependencyMetadataError(ValueError):
    """Raised when dependency metadata cannot be audited safely."""


def _canonical_python_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _canonical_package_name(ecosystem: str, name: str) -> str:
    if ecosystem == "python":
        return _canonical_python_name(name)
    return name.lower()


def classify_license(declared_license: str) -> str:
    """Classify a declared license using a conservative offline allowlist."""

    value = declared_license.strip()
    if not value or value.upper() in {"UNKNOWN", "NONE", "N/A"}:
        return "unknown"

    value = _LICENSE_ALIASES.get(value.upper(), value)
    if "SSPL" in value.upper() or "SERVER SIDE PUBLIC LICENSE" in value.upper():
        return "sspl"
    if _COPYLEFT_PATTERN.search(value):
        return "copyleft"

    tokens = [token.upper() for token in _EXPRESSION_TOKEN.findall(value)]
    identifiers = [token for token in tokens if token not in _EXPRESSION_OPERATORS]
    if identifiers and all(
        token in _ALLOWED_LICENSE_IDS or token in _ALLOWED_EXCEPTION_IDS
        for token in identifiers
    ):
        return "permissive"
    return "unknown"


def _declared_python_license(distribution: PythonDistribution) -> str:
    expression = distribution.license_expression.strip()
    if expression:
        return expression

    license_text = distribution.license_text.strip()
    if license_text and classify_license(license_text) != "unknown":
        return license_text

    prefix = "License :: OSI Approved :: "
    for classifier in sorted(distribution.classifiers):
        if classifier.startswith(prefix):
            classifier_name = classifier[len(prefix) :]
            mapped = _CLASSIFIER_LICENSES.get(classifier_name)
            if mapped:
                return mapped
    return license_text


def installed_python_distributions() -> list[PythonDistribution]:
    """Read installed distributions without accessing package source paths."""

    records = []
    for distribution in importlib.metadata.distributions():
        metadata = distribution.metadata
        name = metadata.get("Name", "").strip()
        if not name:
            continue
        records.append(
            PythonDistribution(
                name=name,
                version=metadata.get("Version", "").strip(),
                license_expression=metadata.get("License-Expression", "").strip(),
                license_text=metadata.get("License", "").strip(),
                classifiers=tuple(metadata.get_all("Classifier") or ()),
                requirements=tuple(distribution.requires or ()),
            )
        )
    return records


def _requirement_applies(
    requirement: Requirement,
    active_extra: str,
    marker_environment: Mapping[str, str],
) -> bool:
    if requirement.marker is None:
        return True
    environment = dict(marker_environment)
    environment["extra"] = active_extra
    return requirement.marker.evaluate(environment)


def audit_python_distributions(
    distributions: Iterable[PythonDistribution],
    *,
    root_name: str = PROJECT_DISTRIBUTION,
    marker_environment: Mapping[str, str] | None = None,
) -> list[LicenseResult]:
    """Audit the installed runtime closure rooted at the project distribution."""

    by_name = {
        _canonical_python_name(distribution.name): distribution
        for distribution in distributions
    }
    canonical_root = _canonical_python_name(root_name)
    if canonical_root not in by_name:
        raise DependencyMetadataError("project distribution metadata is not installed")

    environment = dict(
        default_environment() if marker_environment is None else marker_environment
    )
    queue: deque[tuple[str, str]] = deque([(canonical_root, "")])
    visited_contexts: set[tuple[str, str]] = set()
    dependency_names: set[str] = set()

    while queue:
        package_name, active_extra = queue.popleft()
        context = (package_name, active_extra)
        if context in visited_contexts:
            continue
        visited_contexts.add(context)

        distribution = by_name.get(package_name)
        if distribution is None:
            dependency_names.add(package_name)
            continue

        if package_name != canonical_root:
            dependency_names.add(package_name)

        for requirement_text in distribution.requirements:
            try:
                requirement = Requirement(requirement_text)
            except InvalidRequirement as exc:
                raise DependencyMetadataError(
                    f"invalid requirement metadata for {distribution.name}"
                ) from exc
            if not _requirement_applies(requirement, active_extra, environment):
                continue
            required_name = _canonical_python_name(requirement.name)
            queue.append((required_name, ""))
            for extra in sorted(requirement.extras):
                queue.append((required_name, extra))

    results = []
    for package_name in sorted(dependency_names):
        distribution = by_name.get(package_name)
        if distribution is None:
            declared_license = ""
            version = ""
            display_name = package_name
        else:
            declared_license = _declared_python_license(distribution)
            version = distribution.version
            display_name = distribution.name
        category = classify_license(declared_license)
        results.append(
            LicenseResult(
                ecosystem="python",
                name=display_name,
                version=version,
                declared_license=declared_license,
                category=category,
                allowed=category == "permissive",
            )
        )
    return sorted(results, key=_result_sort_key)


def _npm_name_from_lock_path(lock_path: str) -> str:
    return lock_path.rsplit("node_modules/", 1)[-1]


def audit_npm_lock(lock_data: Mapping[str, Any]) -> list[LicenseResult]:
    """Audit non-dev package entries from an npm lockfile v3 document."""

    if lock_data.get("lockfileVersion") != 3:
        raise DependencyMetadataError("npm lockfileVersion must be 3")
    packages = lock_data.get("packages")
    if not isinstance(packages, Mapping):
        raise DependencyMetadataError("npm lockfile packages metadata is missing")

    results = []
    for lock_path, package_data in packages.items():
        if not lock_path or "node_modules/" not in lock_path:
            continue
        if not isinstance(package_data, Mapping) or any(
            package_data.get(marker) is True for marker in ("dev", "devOptional")
        ):
            continue
        name = _npm_name_from_lock_path(str(lock_path))
        version = package_data.get("version", "")
        declared_license = package_data.get("license", "")
        if not isinstance(version, str):
            version = ""
        if not isinstance(declared_license, str):
            declared_license = ""
        category = classify_license(declared_license)
        results.append(
            LicenseResult(
                ecosystem="npm",
                name=name,
                version=version,
                declared_license=declared_license,
                category=category,
                allowed=category == "permissive",
            )
        )
    return sorted(results, key=_result_sort_key)


def apply_reviewed_exceptions(
    results: Iterable[LicenseResult],
    exceptions: Mapping[tuple[str, str, str, str], str] = REVIEWED_EXCEPTIONS,
) -> list[LicenseResult]:
    """Apply only exact, reasoned exceptions to otherwise blocked results."""

    reviewed = []
    for result in results:
        key = (
            result.ecosystem,
            _canonical_package_name(result.ecosystem, result.name),
            result.version,
            result.declared_license,
        )
        reason = exceptions.get(key, "").strip()
        if not result.allowed and reason:
            result = replace(result, allowed=True, exception_reason=reason)
        reviewed.append(result)
    return sorted(reviewed, key=_result_sort_key)


def _result_sort_key(result: LicenseResult) -> tuple[str, str, str]:
    return (
        result.ecosystem,
        _canonical_package_name(result.ecosystem, result.name),
        result.version,
    )


def format_report(results: Iterable[LicenseResult]) -> str:
    """Render a stable report containing package identifiers and categories only."""

    ordered = sorted(results, key=_result_sort_key)
    lines = []
    for result in ordered:
        status = "EXCEPTION" if result.exception_reason else (
            "PASS" if result.allowed else "FAIL"
        )
        lines.append(f"{status} {result.ecosystem} {result.name}: {result.category}")

    blocked = sum(not result.allowed for result in ordered)
    verdict = "PASS" if blocked == 0 else "FAIL"
    lines.append(f"Dependency license check: {verdict} ({blocked} blocked)")
    return "\n".join(lines)


def _metadata_failure(ecosystem: str, name: str) -> LicenseResult:
    return LicenseResult(
        ecosystem=ecosystem,
        name=name,
        version="",
        declared_license="",
        category="unknown",
        allowed=False,
    )


def main() -> int:
    results: list[LicenseResult] = []
    try:
        results.extend(audit_python_distributions(installed_python_distributions()))
    except DependencyMetadataError:
        results.append(_metadata_failure("python", PROJECT_DISTRIBUTION))

    try:
        with PACKAGE_LOCK.open(encoding="utf-8") as lock_file:
            lock_data = json.load(lock_file)
        results.extend(audit_npm_lock(lock_data))
    except (DependencyMetadataError, OSError, json.JSONDecodeError):
        results.append(_metadata_failure("npm", "package-lock"))

    reviewed = apply_reviewed_exceptions(results)
    print(format_report(reviewed))
    return 1 if any(not result.allowed for result in reviewed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
