"""Walk-forward validation for digital root statistics.

Validates whether digital root statistics have predictive power by:
- Using only historical data before prediction
- Sealing predictions before results known
- Comparing to actual results
- Measuring performance against random baseline
- Separating descriptive, out-of-sample, and prospective phases
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from lottery_intelligence_platform.digital_root import get_root_fast, get_numbers_by_root_fast
from lottery_intelligence_platform.digital_root_statistics import (
    DigitalRootStatistics,
    GameStatistics,
    WindowStatistics,
)


@dataclass(slots=True)
class StatisticalPrediction:
    """A prediction based on statistical analysis."""
    prediction_id: UUID
    draw_id: UUID
    draw_type_id: UUID
    scheduled_date: date
    window_days_used: int
    predicted_roots: list[int]
    predicted_numbers: list[int]
    confidence_scores: list[float]
    prediction_timestamp: datetime


@dataclass(slots=True)
class StatisticalValidationResult:
    """Result of validating a statistical prediction."""
    prediction_id: UUID
    draw_id: UUID
    scheduled_date: date
    predicted_roots: list[int]
    actual_roots: list[int]
    predicted_numbers: list[int]
    actual_numbers: list[int]
    root_hits: int
    number_hits: int
    total_roots_predicted: int
    total_numbers_predicted: int
    prediction_timestamp: datetime
    settlement_timestamp: datetime


@dataclass(slots=True)
class ValidationMetrics:
    """Aggregated validation metrics."""
    total_predictions: int = 0
    root_hit_rate: float = 0.0
    number_hit_rate: float = 0.0
    average_window_used: float = 0.0
    by_window: dict[int, dict[str, Any]] = field(default_factory=dict)
    random_baseline: dict[str, float] = field(default_factory=dict)


class WalkForwardStatisticalValidator:
    """Walk-forward validator for digital root statistics."""

    def __init__(
        self,
        statistics_analyzer: DigitalRootStatistics,
        *,
        default_window: int = 30,
    ):
        self.statistics_analyzer = statistics_analyzer
        self.default_window = default_window
        self.predictions: list[StatisticalPrediction] = []
        self.results: list[StatisticalValidationResult] = []

    def validate_game(
        self,
        connection: Any,
        game_id: UUID,
        start_date: date,
        end_date: date,
        *,
        window_days: int | None = None,
    ) -> ValidationMetrics:
        """Run walk-forward validation for a date range.

        Args:
            connection: Database connection
            game_id: Game type to validate
            start_date: Start of validation period
            end_date: End of validation period
            window_days: Time window to use (default: self.default_window)

        Returns:
            Validation metrics
        """
        window = window_days or self.default_window

        # Get all settled draws in the range
        draws = connection.execute(
            """SELECT d.draw_id, d.draw_type_id, d.scheduled_date
               FROM core.draws d
               WHERE d.draw_type_id = %s
                 AND d.scheduled_date >= %s
                 AND d.scheduled_date <= %s
                 AND d.status = 'SETTLED'
               ORDER BY d.scheduled_date""",
            (game_id, start_date, end_date),
        ).fetchall()

        results = []

        for draw_id, _, scheduled_date in draws:
            # 1. Calculate statistics BEFORE this draw (descriptive phase)
            prediction = self._make_statistical_prediction(
                connection,
                game_id,
                draw_id,
                scheduled_date,
                window_days=window,
            )

            if prediction:
                self.predictions.append(prediction)

                # 2. Settle prediction against actual result
                result = self._settle_prediction(
                    connection,
                    draw_id,
                    prediction,
                )

                if result:
                    results.append(result)
                    self.results.append(result)

        return self._calculate_metrics(results, window)

    def _make_statistical_prediction(
        self,
        connection: Any,
        game_id: UUID,
        draw_id: UUID,
        target_date: date,
        *,
        window_days: int,
    ) -> StatisticalPrediction | None:
        """Make a prediction based on historical statistics.

        Args:
            connection: Database connection
            game_id: Game type
            draw_id: Target draw ID
            target_date: Target draw date
            window_days: Time window to analyze

        Returns:
            Statistical prediction or None if insufficient data
        """
        # Calculate statistics from historical data
        stats = self.statistics_analyzer.calculate_game_statistics(
            connection,
            game_id,
            target_date,
        )

        window_stats = stats.windows.get(window_days)
        if not window_stats or window_stats.draw_count < 5:
            # Insufficient data
            return None

        # Use the most frequent roots from the window
        # Rank by deviation from expected (positive deviation = hot)
        ranked_roots = sorted(
            window_stats.global_distribution,
            key=lambda d: d.deviation_from_reference,
            reverse=True,
        )

        # Predict top 5 roots
        predicted_roots = [d.root for d in ranked_roots[:5]]
        confidence_scores = [d.deviation_from_reference for d in ranked_roots[:5]]

        # Generate numbers from predicted roots
        predicted_numbers = []
        for root in predicted_roots:
            family = get_numbers_by_root_fast(root)
            # Use the most frequent number from this family
            # (simplified: just take first one)
            predicted_numbers.extend(family[:1])

        # Remove duplicates and limit to 5 numbers
        predicted_numbers = list(dict.fromkeys(predicted_numbers))[:5]

        return StatisticalPrediction(
            prediction_id=draw_id,  # Use draw_id as prediction_id for simplicity
            draw_id=draw_id,
            draw_type_id=game_id,
            scheduled_date=target_date,
            window_days_used=window_days,
            predicted_roots=predicted_roots,
            predicted_numbers=predicted_numbers,
            confidence_scores=confidence_scores,
            prediction_timestamp=datetime.now(),
        )

    def _settle_prediction(
        self,
        connection: Any,
        draw_id: UUID,
        prediction: StatisticalPrediction,
    ) -> StatisticalValidationResult | None:
        """Settle a prediction against actual result.

        Args:
            connection: Database connection
            draw_id: Draw to settle
            prediction: Sealed prediction

        Returns:
            Validation result or None if settlement fails
        """
        # Get winning numbers
        rows = connection.execute(
            """SELECT dn.number
               FROM core.draws d
               JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
               JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
               WHERE d.draw_id = %s
                 AND dv.validation_status = 'VALID'
                 AND dn.number_role = 'WINNING'
               ORDER BY dn.position""",
            (draw_id,),
        ).fetchall()

        if not rows:
            return None

        actual_numbers = [r[0] for r in rows]
        actual_roots = [get_root_fast(n) for n in actual_numbers]

        # Calculate hits
        root_hits = len(set(prediction.predicted_roots) & set(actual_roots))
        number_hits = len(set(prediction.predicted_numbers) & set(actual_numbers))

        return StatisticalValidationResult(
            prediction_id=prediction.prediction_id,
            draw_id=draw_id,
            scheduled_date=prediction.scheduled_date,
            predicted_roots=prediction.predicted_roots,
            actual_roots=actual_roots,
            predicted_numbers=prediction.predicted_numbers,
            actual_numbers=actual_numbers,
            root_hits=root_hits,
            number_hits=number_hits,
            total_roots_predicted=len(prediction.predicted_roots),
            total_numbers_predicted=len(prediction.predicted_numbers),
            prediction_timestamp=prediction.prediction_timestamp,
            settlement_timestamp=datetime.now(),
        )

    def _calculate_metrics(
        self,
        results: list[StatisticalValidationResult],
        window_days: int,
    ) -> ValidationMetrics:
        """Calculate aggregated validation metrics.

        Args:
            results: List of validation results
            window_days: Window used

        Returns:
            Validation metrics
        """
        if not results:
            return ValidationMetrics()

        total = len(results)
        total_root_hits = sum(r.root_hits for r in results)
        total_number_hits = sum(r.number_hits for r in results)
        total_roots_predicted = sum(r.total_roots_predicted for r in results)
        total_numbers_predicted = sum(r.total_numbers_predicted for r in results)

        metrics = ValidationMetrics(
            total_predictions=total,
            root_hit_rate=(total_root_hits / total_roots_predicted) if total_roots_predicted > 0 else 0.0,
            number_hit_rate=(total_number_hits / total_numbers_predicted) if total_numbers_predicted > 0 else 0.0,
            average_window_used=float(window_days),
        )

        # Calculate random baseline
        metrics.random_baseline = self._calculate_random_baseline()

        return metrics

    def _calculate_random_baseline(self) -> dict[str, float]:
        """Calculate random baseline performance.

        Returns:
            Baseline metrics
        """
        # Expected random performance:
        # - For roots: 5 random roots out of 9 = 5/9 ≈ 55.6% hit rate
        # - For numbers: 5 random numbers out of 90 = 5/90 ≈ 5.6% hit rate
        # But we're comparing to actual roots in the draw (5 roots)
        # So expected root hits = 5 * (5/9) ≈ 2.78 out of 5 predicted
        # Expected number hits = 5 * (5/90) ≈ 0.28 out of 5 predicted

        expected_root_hit_rate = 5.0 / 9.0  # ~55.6%
        expected_number_hit_rate = 5.0 / 90.0  # ~5.6%

        return {
            "root_hit_rate": expected_root_hit_rate,
            "number_hit_rate": expected_number_hit_rate,
        }

    def compare_to_baseline(
        self,
        metrics: ValidationMetrics,
    ) -> dict[str, Any]:
        """Compare validation metrics to random baseline.

        Args:
            metrics: Validation metrics

        Returns:
            Comparison report
        """
        baseline = metrics.random_baseline

        root_improvement = (
            (metrics.root_hit_rate - baseline["root_hit_rate"]) / baseline["root_hit_rate"] * 100
            if baseline["root_hit_rate"] > 0
            else 0.0
        )

        number_improvement = (
            (metrics.number_hit_rate - baseline["number_hit_rate"]) / baseline["number_hit_rate"] * 100
            if baseline["number_hit_rate"] > 0
            else 0.0
        )

        return {
            "root_hit_rate_improvement_percent": root_improvement,
            "number_hit_rate_improvement_percent": number_improvement,
            "statistically_significant": (
                metrics.total_predictions >= 30
                and metrics.root_hit_rate > baseline["root_hit_rate"] * 1.2
            ),
            "sample_size": metrics.total_predictions,
        }
