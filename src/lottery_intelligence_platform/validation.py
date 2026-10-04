from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from lottery_intelligence_platform.ingestion import CollectionReceipt, record_validation_event

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ValidationReport(Generic[T]):
    status: str
    observations: tuple[T, ...]
    issues: tuple[dict[str, Any], ...]


def validation_status(issues: list[dict[str, Any]]) -> str:
    if any(issue.get("severity") == "ERROR" for issue in issues):
        return "FAILED"
    if any(issue.get("severity") == "WARNING" for issue in issues):
        return "WARNING"
    return "PASSED"


def persist_validation_report(
    connection: Any,
    receipt: CollectionReceipt,
    report: ValidationReport[Any],
    *,
    validator_name: str,
    validator_version: str,
) -> None:
    record_validation_event(
        connection,
        receipt,
        validator_name=validator_name,
        validator_version=validator_version,
        status=report.status,
        issues=list(report.issues),
    )
