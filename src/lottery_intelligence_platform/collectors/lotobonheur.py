from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Any, Generic, TypeVar
from urllib.parse import urlencode, urljoin
from uuid import UUID

from lottery_intelligence_platform.collectors.http import HttpClient, HttpResponse, UrllibHttpClient
from lottery_intelligence_platform.ingestion import (
    CollectionReceipt,
    ingest_payload,
    record_collection_failure,
)
from lottery_intelligence_platform.raw import RawObjectStore
from lottery_intelligence_platform.validation import (
    ValidationReport,
    persist_validation_report,
    validation_status,
)

BASE_URL = "https://lotobonheur.ci"
SCHEDULE_PAGE_PATH = "/"
RESULTS_API_PATH = "/api/results"
DRAW_TYPE_FILTER = "Tous les tirages"
COLLECTOR_VERSION = "0.1.0"
MONTHS_FR = {
    "janvier": 1,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
}
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ScheduleObservation:
    external_draw_id: str
    external_event_id: str
    draw_name: str
    group_date: date
    source_datetime: str
    scheduled_at: datetime
    source_timezone: str
    end_time: str
    is_single_set: bool
    preview: str
    source_data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ResultObservation:
    draw_date: date
    draw_name: str
    result_group: str
    winning_numbers: tuple[int, ...]
    machine_numbers: tuple[int, ...] | None
    source_date: str
    source_data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ResultValidationRules:
    minimum_number: int
    maximum_number: int
    numbers_per_draw: int
    duplicates_allowed: bool = False

    def __post_init__(self) -> None:
        values = (self.minimum_number, self.maximum_number, self.numbers_per_draw)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise TypeError("number validation rules must be integers")
        if self.minimum_number < 1 or self.maximum_number < self.minimum_number:
            raise ValueError("number range is invalid")
        if self.numbers_per_draw < 1 or self.numbers_per_draw > self.maximum_number - self.minimum_number + 1:
            raise ValueError("numbers_per_draw is invalid for the configured range")
        if not isinstance(self.duplicates_allowed, bool):
            raise ValueError("duplicates_allowed must be boolean")

    @classmethod
    def from_game_version(cls, connection: Any, game_version_id: UUID) -> ResultValidationRules:
        row = connection.execute(
            "SELECT rules FROM catalog.game_versions WHERE game_version_id = %s",
            (game_version_id,),
        ).fetchone()
        if row is None or not isinstance(row[0], dict):
            raise ValueError("game version is missing or has invalid rules")
        rules = row[0]
        try:
            return cls(
                minimum_number=rules["number_min"],
                maximum_number=rules["number_max"],
                numbers_per_draw=rules["numbers_per_draw"],
                duplicates_allowed=rules["duplicates_allowed"],
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("game version rules lack result validation parameters") from exc


@dataclass(frozen=True, slots=True)
class CollectedBatch(Generic[T]):
    receipts: tuple[CollectionReceipt, ...]
    validation: ValidationReport[T]


class SourceHTTPError(RuntimeError):
    def __init__(self, status_code: int, url: str) -> None:
        super().__init__(f"source returned HTTP {status_code}: {url}")
        self.status_code = status_code
        self.url = url


class _NextDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capturing = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._capturing = tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._capturing = False

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self.parts.append(data)


def extract_next_build_id(html_payload: bytes) -> str:
    parser = _NextDataParser()
    parser.feed(html_payload.decode("utf-8"))
    if not parser.parts:
        raise ValueError("Next.js bootstrap data was not found")
    try:
        data = json.loads("".join(parser.parts))
    except json.JSONDecodeError as exc:
        raise ValueError("Next.js bootstrap data is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Next.js bootstrap data must be an object")
    build_id = data.get("buildId")
    if not isinstance(build_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", build_id):
        raise ValueError("Next.js build identifier is missing or invalid")
    return build_id


def _request_metadata(response: HttpResponse, **extra: Any) -> dict[str, Any]:
    return {
        "requested_url": response.requested_url,
        "response_url": response.response_url,
        "http_status": response.status_code,
        "content_type": response.content_type,
        **extra,
    }


def _fetch_or_record_failure(
    http_client: HttpClient,
    connection: Any,
    source_id: UUID,
    collector_name: str,
    url: str,
    *,
    accept: str,
    request_metadata: dict[str, Any] | None = None,
) -> HttpResponse:
    metadata = {"requested_url": url, **(request_metadata or {})}
    try:
        response = http_client.get(url, accept=accept)
    except Exception as exc:
        record_collection_failure(
            connection,
            source_id=source_id,
            collector_name=collector_name,
            collector_version=COLLECTOR_VERSION,
            error_type=type(exc).__name__,
            request_metadata=metadata,
        )
        raise
    if not 200 <= response.status_code < 300:
        metadata.update(_request_metadata(response))
        record_collection_failure(
            connection,
            source_id=source_id,
            collector_name=collector_name,
            collector_version=COLLECTOR_VERSION,
            error_type=f"HTTP_{response.status_code}",
            request_metadata=metadata,
            response_status=response.status_code,
        )
        raise SourceHTTPError(response.status_code, response.response_url)
    return response


def _parse_schedule_datetime(raw: Any) -> tuple[datetime, str]:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("endDateTime is required")
    value = raw.strip()
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("endDateTime must contain a timezone")
    source_timezone = "UTC" if parsed.utcoffset().total_seconds() == 0 else parsed.strftime("%z")
    return parsed.astimezone(timezone.utc), source_timezone


def validate_schedule_payload(payload: bytes) -> ValidationReport[ScheduleObservation]:
    issues: list[dict[str, Any]] = []
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ValidationReport("FAILED", (), ({"severity": "ERROR", "issue_code": "INVALID_JSON"},))

    page_props = document.get("pageProps") if isinstance(document, dict) else None
    schedule = page_props.get("activeDrawsData") if isinstance(page_props, dict) else None
    if not isinstance(schedule, dict):
        issue = {"severity": "ERROR", "issue_code": "MISSING_ACTIVE_DRAWS_DATA"}
        return ValidationReport("FAILED", (), (issue,))
    if str(schedule.get("status")) != "0" or schedule.get("success") is not True:
        issue = {"severity": "ERROR", "issue_code": "SCHEDULE_SOURCE_UNSUCCESSFUL"}
        return ValidationReport("FAILED", (), (issue,))

    groups = schedule.get("drawGroups")
    if not isinstance(groups, list):
        issue = {"severity": "ERROR", "issue_code": "INVALID_DRAW_GROUPS"}
        return ValidationReport("FAILED", (), (issue,))

    observations: list[ScheduleObservation] = []
    external_ids: set[str] = set()
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            issues.append({"severity": "ERROR", "issue_code": "INVALID_DRAW_GROUP", "group_index": group_index})
            continue
        try:
            group_date = date.fromisoformat(group.get("groupDate", ""))
        except (TypeError, ValueError):
            issues.append({"severity": "ERROR", "issue_code": "INVALID_GROUP_DATE", "group_index": group_index})
            continue
        draws = group.get("draws")
        if not isinstance(draws, list):
            issues.append({"severity": "ERROR", "issue_code": "INVALID_SCHEDULE_DRAWS", "group_index": group_index})
            continue
        for draw_index, draw in enumerate(draws):
            if not isinstance(draw, dict):
                issues.append({"severity": "ERROR", "issue_code": "INVALID_SCHEDULE_DRAW", "group_index": group_index, "draw_index": draw_index})
                continue
            external_draw_id = str(draw.get("id", "")).strip()
            external_event_id = str(draw.get("eventId", "")).strip()
            draw_name = draw.get("name")
            try:
                scheduled_at, source_timezone = _parse_schedule_datetime(draw.get("endDateTime"))
                if scheduled_at.date() != group_date:
                    raise ValueError("scheduled date does not match groupDate")
                if not external_draw_id or not external_event_id:
                    raise ValueError("external id and eventId are required")
                if not isinstance(draw_name, str) or not draw_name.strip() or draw_name == "-":
                    raise ValueError("draw name is missing")
                end_time = draw.get("endTime")
                if not isinstance(end_time, str) or not end_time.strip():
                    raise ValueError("endTime is missing")
                is_single_set = draw.get("isSingleSet")
                if not isinstance(is_single_set, bool):
                    raise ValueError("isSingleSet must be boolean")
                if external_draw_id in external_ids:
                    raise ValueError("duplicate external draw id in one schedule response")
            except (TypeError, ValueError) as exc:
                issues.append({
                    "severity": "ERROR",
                    "issue_code": "INVALID_SCHEDULE_DRAW",
                    "group_index": group_index,
                    "draw_index": draw_index,
                    "reason": str(exc),
                })
                continue
            external_ids.add(external_draw_id)
            observations.append(ScheduleObservation(
                external_draw_id=external_draw_id,
                external_event_id=external_event_id,
                draw_name=draw_name.strip(),
                group_date=group_date,
                source_datetime=draw["endDateTime"],
                scheduled_at=scheduled_at,
                source_timezone=source_timezone,
                end_time=end_time,
                is_single_set=is_single_set,
                preview=str(draw.get("preview", "")),
                source_data=draw,
            ))

    expected_count = schedule.get("drawsNumber")
    if isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 0:
        issues.append({"severity": "ERROR", "issue_code": "INVALID_SCHEDULE_COUNT"})
    elif expected_count != len(observations):
        issues.append({
            "severity": "ERROR",
            "issue_code": "SCHEDULE_COUNT_MISMATCH",
            "expected": expected_count,
            "observed": len(observations),
        })
    return ValidationReport(validation_status(issues), tuple(observations), tuple(issues))


def _parse_numbers(raw: Any, rules: ResultValidationRules) -> tuple[int, ...]:
    if not isinstance(raw, str):
        raise ValueError("number list must be text")
    pieces = [piece.strip() for piece in raw.split("-")]
    if len(pieces) != rules.numbers_per_draw or any(not re.fullmatch(r"\d{1,2}", piece) for piece in pieces):
        raise ValueError(f"exactly {rules.numbers_per_draw} numeric values are required")
    values = tuple(int(piece) for piece in pieces)
    if any(number < rules.minimum_number or number > rules.maximum_number for number in values):
        raise ValueError("number is outside the configured range")
    if not rules.duplicates_allowed and len(set(values)) != len(values):
        raise ValueError("duplicate numbers are not allowed")
    return values


def _month_year(value: str) -> tuple[int, int]:
    parts = " ".join(value.strip().lower().split()).split(" ")
    if len(parts) != 2 or parts[0] not in MONTHS_FR or not parts[1].isdigit():
        raise ValueError("month must be a French month name followed by a year")
    year = int(parts[1])
    if not 1 <= year <= 9999:
        raise ValueError("year is invalid")
    return MONTHS_FR[parts[0]], year


def _result_date(raw: Any, requested_month: int, requested_year: int) -> date:
    if not isinstance(raw, str):
        raise ValueError("draw date must be text")
    match = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?$", raw.strip())
    if not match:
        raise ValueError("draw date must end in DD/MM or DD/MM/YYYY")
    day, month = int(match.group(1)), int(match.group(2))
    year = int(match.group(3)) if match.group(3) else requested_year
    if not match.group(3) and month - requested_month > 6:
        year -= 1
    elif not match.group(3) and requested_month - month > 6:
        year += 1
    return date(year, month, day)


def validate_results_payload(
    payload: bytes,
    month_year: str,
    rules: ResultValidationRules,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ValidationReport[ResultObservation]:
    issues: list[dict[str, Any]] = []
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValueError("date_from cannot be after date_to")
    try:
        requested_month, requested_year = _month_year(month_year)
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return ValidationReport("FAILED", (), ({"severity": "ERROR", "issue_code": "INVALID_JSON_OR_MONTH"},))
    if not isinstance(document, dict) or document.get("success") is not True or str(document.get("status")) != "0":
        issue = {"severity": "ERROR", "issue_code": "RESULT_SOURCE_UNSUCCESSFUL"}
        return ValidationReport("FAILED", (), (issue,))

    weeks = document.get("drawsResultsWeekly")
    if not isinstance(weeks, list):
        issue = {"severity": "ERROR", "issue_code": "INVALID_WEEKLY_RESULTS"}
        return ValidationReport("FAILED", (), (issue,))

    observations: list[ResultObservation] = []
    seen: set[tuple[date, str, str]] = set()
    for week_index, week in enumerate(weeks):
        daily_results = week.get("drawResultsDaily") if isinstance(week, dict) else None
        if not isinstance(daily_results, list):
            issues.append({"severity": "ERROR", "issue_code": "INVALID_DAILY_RESULTS", "week_index": week_index})
            continue
        for day_index, day in enumerate(daily_results):
            try:
                raw_date = day.get("date")
                draw_date = _result_date(raw_date, requested_month, requested_year)
                if (date_from is not None and draw_date < date_from) or (date_to is not None and draw_date > date_to):
                    issues.append({
                        "severity": "INFO",
                        "issue_code": "OUTSIDE_REQUESTED_WINDOW",
                        "draw_date": draw_date.isoformat(),
                    })
                    continue
                result_groups = day.get("drawResults")
                if not isinstance(result_groups, dict):
                    raise ValueError("drawResults is missing")
            except (AttributeError, TypeError, ValueError) as exc:
                issues.append({"severity": "ERROR", "issue_code": "INVALID_RESULT_DATE_OR_GROUP", "week_index": week_index, "day_index": day_index, "reason": str(exc)})
                continue
            for group_name in ("nightDraws", "standardDraws"):
                draws = result_groups.get(group_name, [])
                if not isinstance(draws, list):
                    issues.append({"severity": "ERROR", "issue_code": "INVALID_RESULT_LIST", "result_group": group_name, "draw_date": draw_date.isoformat()})
                    continue
                for draw_index, draw in enumerate(draws):
                    if not isinstance(draw, dict):
                        issues.append({"severity": "ERROR", "issue_code": "INVALID_RESULT_DRAW", "result_group": group_name, "draw_date": draw_date.isoformat(), "draw_index": draw_index})
                        continue
                    draw_name = draw.get("drawName")
                    if not isinstance(draw_name, str) or not draw_name.strip() or draw_name.strip() == "-":
                        issues.append({"severity": "WARNING", "issue_code": "UNAVAILABLE_DRAW", "result_group": group_name, "draw_date": draw_date.isoformat(), "draw_index": draw_index})
                        continue
                    try:
                        winning_numbers = _parse_numbers(draw.get("winningNumbers"), rules)
                    except ValueError as exc:
                        issues.append({"severity": "ERROR", "issue_code": "INVALID_WINNING_NUMBERS", "result_group": group_name, "draw_date": draw_date.isoformat(), "draw_name": draw_name, "reason": str(exc)})
                        continue
                    machine_numbers = None
                    try:
                        machine_numbers = _parse_numbers(draw.get("machineNumbers"), rules)
                    except ValueError as exc:
                        issues.append({"severity": "WARNING", "issue_code": "INVALID_MACHINE_NUMBERS", "result_group": group_name, "draw_date": draw_date.isoformat(), "draw_name": draw_name, "reason": str(exc)})
                    key = (draw_date, group_name, draw_name.strip())
                    if key in seen:
                        issues.append({"severity": "ERROR", "issue_code": "DUPLICATE_DRAW", "result_group": group_name, "draw_date": draw_date.isoformat(), "draw_name": draw_name})
                        continue
                    seen.add(key)
                    observations.append(ResultObservation(
                        draw_date=draw_date,
                        draw_name=draw_name.strip(),
                        result_group=group_name,
                        winning_numbers=winning_numbers,
                        machine_numbers=machine_numbers,
                        source_date=raw_date,
                        source_data=draw,
                    ))
    return ValidationReport(validation_status(issues), tuple(observations), tuple(issues))


class LotobonheurScheduleCollector:
    name = "lotobonheur_schedule_collector"

    def __init__(self, http_client: HttpClient | None = None, *, base_url: str = BASE_URL) -> None:
        self._http = http_client or UrllibHttpClient()
        self._base_url = base_url.rstrip("/")

    def collect(self, connection: Any, raw_store: RawObjectStore, *, source_id: UUID) -> CollectedBatch[ScheduleObservation]:
        page_url = urljoin(self._base_url + "/", SCHEDULE_PAGE_PATH.lstrip("/"))
        page_response = _fetch_or_record_failure(
            self._http, connection, source_id, self.name, page_url, accept="text/html"
        )
        page_receipt = ingest_payload(
            connection,
            raw_store,
            source_id=source_id,
            collector_name=self.name,
            collector_version=COLLECTOR_VERSION,
            payload=page_response.body,
            content_type=page_response.content_type,
            response_status=page_response.status_code,
            request_metadata={**_request_metadata(page_response), "purpose": "resolve_next_build_id"},
        )
        try:
            build_id = extract_next_build_id(page_response.body)
            bootstrap_report = ValidationReport("PASSED", (), ())
        except (UnicodeDecodeError, ValueError) as exc:
            bootstrap_report = ValidationReport("FAILED", (), ({"severity": "ERROR", "issue_code": "INVALID_NEXT_BOOTSTRAP", "reason": str(exc)},))
            persist_validation_report(
                connection, page_receipt, bootstrap_report,
                validator_name="lotobonheur_next_bootstrap", validator_version=COLLECTOR_VERSION,
            )
            raise
        persist_validation_report(
            connection, page_receipt, bootstrap_report,
            validator_name="lotobonheur_next_bootstrap", validator_version=COLLECTOR_VERSION,
        )

        data_url = urljoin(self._base_url + "/", f"_next/data/{build_id}/index.json")
        data_response = _fetch_or_record_failure(
            self._http, connection, source_id, self.name, data_url, accept="application/json",
            request_metadata={"next_build_id": build_id},
        )
        receipt = ingest_payload(
            connection,
            raw_store,
            source_id=source_id,
            collector_name=self.name,
            collector_version=COLLECTOR_VERSION,
            payload=data_response.body,
            content_type=data_response.content_type,
            response_status=data_response.status_code,
            request_metadata={**_request_metadata(data_response), "next_build_id": build_id, "representation": "schedule_json"},
        )
        report = validate_schedule_payload(data_response.body)
        persist_validation_report(
            connection, receipt, report,
            validator_name=self.name, validator_version=COLLECTOR_VERSION,
        )
        return CollectedBatch((page_receipt, receipt), report)


class LotobonheurResultCollector:
    name = "lotobonheur_result_collector"

    def __init__(
        self,
        *,
        rules: ResultValidationRules,
        http_client: HttpClient | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        self._rules = rules
        self._http = http_client or UrllibHttpClient()
        self._base_url = base_url.rstrip("/")

    def collect(
        self,
        connection: Any,
        raw_store: RawObjectStore,
        *,
        source_id: UUID,
        month_year: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> CollectedBatch[ResultObservation]:
        _month_year(month_year)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from cannot be after date_to")
        query = urlencode({"monthYear": month_year, "drawType": DRAW_TYPE_FILTER})
        url = f"{self._base_url}{RESULTS_API_PATH}?{query}"
        response = _fetch_or_record_failure(
            self._http, connection, source_id, self.name, url, accept="application/json"
        )
        receipt = ingest_payload(
            connection,
            raw_store,
            source_id=source_id,
            collector_name=self.name,
            collector_version=COLLECTOR_VERSION,
            payload=response.body,
            content_type=response.content_type,
            response_status=response.status_code,
            request_metadata={
                **_request_metadata(response),
                "month_year": month_year,
                "date_from": date_from.isoformat() if date_from is not None else None,
                "date_to": date_to.isoformat() if date_to is not None else None,
            },
        )
        report = validate_results_payload(
            response.body,
            month_year,
            self._rules,
            date_from=date_from,
            date_to=date_to,
        )
        persist_validation_report(
            connection, receipt, report,
            validator_name=self.name, validator_version=COLLECTOR_VERSION,
        )
        return CollectedBatch((receipt,), report)


def _fetch_or_record_failure(
    http_client: HttpClient,
    connection: Any,
    source_id: UUID,
    collector_name: str,
    url: str,
    *,
    accept: str,
    request_metadata: dict[str, Any] | None = None,
) -> HttpResponse:
    metadata = {"requested_url": url, **(request_metadata or {})}
    try:
        response = http_client.get(url, accept=accept)
    except Exception as exc:
        record_collection_failure(
            connection,
            source_id=source_id,
            collector_name=collector_name,
            collector_version=COLLECTOR_VERSION,
            error_type=type(exc).__name__,
            request_metadata=metadata,
        )
        raise
    if not 200 <= response.status_code < 300:
        metadata.update(_request_metadata(response))
        record_collection_failure(
            connection,
            source_id=source_id,
            collector_name=collector_name,
            collector_version=COLLECTOR_VERSION,
            error_type=f"HTTP_{response.status_code}",
            request_metadata=metadata,
            response_status=response.status_code,
        )
        raise SourceHTTPError(response.status_code, response.response_url)
    return response
