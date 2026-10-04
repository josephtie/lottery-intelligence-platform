from __future__ import annotations

import calendar
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable
from zoneinfo import ZoneInfo

from urllib.error import URLError

from lottery_intelligence_platform.collectors.lotobonheur import (
    CollectedBatch,
    LotobonheurResultCollector,
    MONTHS_FR,
    ResultObservation,
    SourceHTTPError,
)
from lottery_intelligence_platform.draw_registry import DrawRegistry, ResultRegistration
from lottery_intelligence_platform.raw import RawObjectStore

_MONTH_NAMES = {number: name for name, number in MONTHS_FR.items()}
EARLIEST_RESULTS_DATE = date(2020, 11, 1)


def subtract_calendar_months(value: date, months: int) -> date:
    if months < 1:
        raise ValueError("months must be positive")
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True, slots=True)
class BackfillWindow:
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date")

    @classmethod
    def trailing_months(
        cls,
        months: int = 6,
        *,
        through: date | None = None,
    ) -> BackfillWindow:
        end_date = through or datetime.now(ZoneInfo("Africa/Abidjan")).date()
        return cls(subtract_calendar_months(end_date, months), end_date)

    @classmethod
    def available_history(cls, *, through: date | None = None) -> BackfillWindow:
        end_date = through or datetime.now(ZoneInfo("Africa/Abidjan")).date()
        if end_date < EARLIEST_RESULTS_DATE:
            raise ValueError("end_date predates the earliest official results month")
        return cls(EARLIEST_RESULTS_DATE, end_date)

    def contains(self, value: date) -> bool:
        return self.start_date <= value <= self.end_date

    def month_years(self) -> tuple[str, ...]:
        month_index = self.start_date.year * 12 + self.start_date.month - 1
        last_index = self.end_date.year * 12 + self.end_date.month - 1
        values = []
        while month_index <= last_index:
            year, zero_based_month = divmod(month_index, 12)
            values.append(f"{_MONTH_NAMES[zero_based_month + 1]} {year}")
            month_index += 1
        return tuple(values)


@dataclass(frozen=True, slots=True)
class BackfillMonthFailure:
    month_year: str
    error_type: str


@dataclass(frozen=True, slots=True)
class DrawTypeCoverage:
    draw_name: str
    result_group: str
    observation_count: int
    first_draw_date: date
    last_draw_date: date


@dataclass(frozen=True, slots=True)
class BackfillResult:
    window: BackfillWindow
    batches: tuple[CollectedBatch[ResultObservation], ...]
    failures: tuple[BackfillMonthFailure, ...]
    registrations: tuple[tuple[str, tuple[ResultRegistration, ...]], ...] = ()

    def _deduplicate_observations(
        self,
    ) -> tuple[tuple[ResultObservation, ...], int, tuple[tuple[date, str, str], ...]]:
        by_identity: dict[tuple[date, str, str], ResultObservation] = {}
        conflicts: set[tuple[date, str, str]] = set()
        duplicate_count = 0
        for batch in self.batches:
            for observation in batch.validation.observations:
                if not self.window.contains(observation.draw_date):
                    continue
                identity = (observation.draw_date, observation.result_group, observation.draw_name)
                previous = by_identity.get(identity)
                if previous is None:
                    by_identity[identity] = observation
                    continue
                duplicate_count += 1
                if (previous.winning_numbers, previous.machine_numbers) != (
                    observation.winning_numbers,
                    observation.machine_numbers,
                ):
                    conflicts.add(identity)
        observations = tuple(
            observation for identity, observation in by_identity.items() if identity not in conflicts
        )
        return observations, duplicate_count, tuple(sorted(conflicts))

    @property
    def observations(self) -> tuple[ResultObservation, ...]:
        return self._deduplicate_observations()[0]

    @property
    def overlapping_observation_count(self) -> int:
        return self._deduplicate_observations()[1]

    @property
    def conflicting_observations(self) -> tuple[tuple[date, str, str], ...]:
        return self._deduplicate_observations()[2]

    @property
    def coverage(self) -> tuple[DrawTypeCoverage, ...]:
        grouped: dict[tuple[str, str], list[ResultObservation]] = {}
        for observation in self.observations:
            grouped.setdefault((observation.result_group, observation.draw_name), []).append(observation)
        return tuple(
            DrawTypeCoverage(
                draw_name=name,
                result_group=group,
                observation_count=len(observations),
                first_draw_date=min(item.draw_date for item in observations),
                last_draw_date=max(item.draw_date for item in observations),
            )
            for (group, name), observations in sorted(grouped.items())
        )

    @property
    def is_complete(self) -> bool:
        return (
            not self.failures
            and not self.conflicting_observations
            and all(batch.validation.status != "FAILED" for batch in self.batches)
            and all(
                registration.status != "CONFLICT"
                for _, month_registrations in self.registrations
                for registration in month_registrations
            )
        )


def collect_result_window(
    collector: LotobonheurResultCollector,
    connection,
    raw_store: RawObjectStore,
    *,
    source_id,
    window: BackfillWindow,
    draw_registry: DrawRegistry | None = None,
    pause_seconds: float = 0.5,
    sleeper: Callable[[float], None] = time.sleep,
) -> BackfillResult:
    if pause_seconds < 0:
        raise ValueError("pause_seconds cannot be negative")

    batches = []
    failures = []
    registrations = []
    months = window.month_years()
    for index, month_year in enumerate(months):
        try:
            batch = collector.collect(
                connection,
                raw_store,
                source_id=source_id,
                month_year=month_year,
                date_from=window.start_date,
                date_to=window.end_date,
            )
            batches.append(batch)
            if batch.validation.status == "FAILED":
                failures.append(BackfillMonthFailure(month_year, "VALIDATION_FAILED"))
            elif draw_registry is not None:
                registrations.append((month_year, draw_registry.register_result_batch(batch)))
        except (SourceHTTPError, URLError, TimeoutError) as exc:
            failures.append(BackfillMonthFailure(month_year, type(exc).__name__))
        if pause_seconds and index + 1 < len(months):
            sleeper(pause_seconds)

    return BackfillResult(window, tuple(batches), tuple(failures), tuple(registrations))
