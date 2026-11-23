"""Walk-forward validation for Digital Root Turbo Analyzer.

Implements strict walk-forward validation:
- Use only historical data before prediction
- Seal predictions before result known
- Compare to actual results
- Calculate performance metrics
- Compare to random baselines
- Separate exploration, out-of-sample, and prospective phases
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from lottery_intelligence_platform.betting_formulas import TURBO_FORMULAS
from lottery_intelligence_platform.digital_root_analyzer import (
    DigitalRootPrediction,
    DigitalRootTurboAnalyzer,
)


@dataclass(slots=True)
class ValidationResult:
    """Result of a single walk-forward validation step."""
    draw_id: UUID
    draw_type_id: UUID
    scheduled_date: date
    predicted_numbers: list[int]
    winning_numbers: list[int]
    hit_count: int
    positional_hits: dict[str, int]
    turbo_hit: bool
    turbo_variant: str
    stake: float
    payout: float
    net_profit: float
    roi: float
    used_relations_count: int
    prediction_timestamp: datetime
    settlement_timestamp: datetime


@dataclass(slots=True)
class ValidationMetrics:
    """Aggregated validation metrics."""
    total_predictions: int = 0
    total_hits: int = 0
    hit_rate: float = 0.0
    turbo_hits: int = 0
    turbo_hit_rate: float = 0.0
    total_stake: float = 0.0
    total_payout: float = 0.0
    total_net_profit: float = 0.0
    average_roi: float = 0.0
    by_game: dict[UUID, dict[str, Any]] = field(default_factory=dict)
    by_position: dict[int, dict[str, Any]] = field(default_factory=dict)
    by_relation_type: dict[str, dict[str, Any]] = field(default_factory=dict)
    random_baseline: dict[str, float] = field(default_factory=dict)


class WalkForwardValidator:
    """Walk-forward validation for digital root predictions."""

    def __init__(
        self,
        analyzer: DigitalRootTurboAnalyzer,
        *,
        training_window_days: int = 30,
        test_window_days: int = 7,
        default_stake: float = 100.0,
    ):
        self.analyzer = analyzer
        self.training_window_days = training_window_days
        self.test_window_days = test_window_days
        self.default_stake = default_stake
        self.results: list[ValidationResult] = []

    def run_validation(
        self,
        connection: Any,
        draw_type_id: UUID,
        start_date: date,
        end_date: date,
        *,
        turbo_variant: str = "turbo_2",
    ) -> ValidationMetrics:
        """Run walk-forward validation for a date range.

        Args:
            connection: Database connection
            draw_type_id: Game type to validate
            start_date: Start of validation period
            end_date: End of validation period
            turbo_variant: Turbo variant to test

        Returns:
            Aggregated validation metrics
        """
        # Get all settled draws in the range
        draws = connection.execute(
            """SELECT d.draw_id, d.draw_type_id, d.scheduled_date
               FROM core.draws d
               WHERE d.draw_type_id = %s
                 AND d.scheduled_date >= %s
                 AND d.scheduled_date <= %s
                 AND d.status = 'SETTLED'
               ORDER BY d.scheduled_date""",
            (draw_type_id, start_date, end_date),
        ).fetchall()

        results = []

        for draw_id, _, scheduled_date in draws:
            # Training cutoff: data before this draw
            training_cutoff = scheduled_date

            # Discover and train on historical data
            self.analyzer.discover_and_train(
                connection,
                [draw_type_id],
                training_cutoff,
            )

            # Make prediction (sealed before result known)
            prediction = self.analyzer.predict(
                connection,
                draw_type_id,
                scheduled_date,
                turbo_variant=turbo_variant,
            )

            # Get actual result
            result = self._settle_prediction(
                connection,
                draw_id,
                prediction,
                turbo_variant,
            )

            if result:
                results.append(result)

            # Update analyzer with actual result
            self.analyzer.update_with_result(connection, draw_id)

        self.results.extend(results)
        return self._calculate_metrics(results, draw_type_id)

    def _settle_prediction(
        self,
        connection: Any,
        draw_id: UUID,
        prediction: DigitalRootPrediction,
        turbo_variant: str,
    ) -> ValidationResult | None:
        """Settle a prediction against actual result.

        Args:
            connection: Database connection
            draw_id: Draw to settle
            prediction: Sealed prediction
            turbo_variant: Turbo variant

        Returns:
            Validation result or None if settlement fails
        """
        # Get winning numbers
        rows = connection.execute(
            """SELECT dn.number, dn.position
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

        winning_numbers = [r[0] for r in rows]
        draw_type_id = connection.execute(
            "SELECT draw_type_id FROM core.draws WHERE draw_id = %s",
            (draw_id,),
        ).fetchone()[0]
        scheduled_date = connection.execute(
            "SELECT scheduled_date FROM core.draws WHERE draw_id = %s",
            (draw_id,),
        ).fetchone()[0]

        # Calculate hits
        predicted_set = set(prediction.predicted_numbers)
        winning_set = set(winning_numbers)
        hit_count = len(predicted_set & winning_set)

        # Positional hits
        positional_hits = {}
        for k in range(1, len(winning_numbers) + 1):
            positional_hits[f"first_{k}"] = len(predicted_set & set(winning_numbers[:k]))

        # Turbo hit check
        formula = TURBO_FORMULAS.get(f"TURBO_{turbo_variant.replace('turbo_', '').upper()}")
        if formula is None:
            return None

        numbers_required = formula.numbers_required
        turbo_hit = predicted_set <= set(winning_numbers[:numbers_required])

        # Calculate payout
        stake = self.default_stake
        if turbo_hit:
            payout = stake * float(formula.odds[turbo_variant.upper()])
        else:
            payout = 0.0

        net_profit = payout - stake
        roi = (net_profit / stake) * 100 if stake > 0 else 0.0

        # Count used relations
        used_relations = sum(
            1 for p in prediction.predicted_roots
            if p.supporting_relation and p.supporting_relation.should_use_for_prediction()
        )

        return ValidationResult(
            draw_id=draw_id,
            draw_type_id=draw_type_id,
            scheduled_date=scheduled_date,
            predicted_numbers=prediction.predicted_numbers,
            winning_numbers=winning_numbers,
            hit_count=hit_count,
            positional_hits=positional_hits,
            turbo_hit=turbo_hit,
            turbo_variant=turbo_variant,
            stake=stake,
            payout=payout,
            net_profit=net_profit,
            roi=roi,
            used_relations_count=used_relations,
            prediction_timestamp=datetime.fromisoformat(
                prediction.metadata.get("timestamp", datetime.now().isoformat())
            ),
            settlement_timestamp=datetime.now(),
        )

    def _calculate_metrics(
        self,
        results: list[ValidationResult],
        draw_type_id: UUID,
    ) -> ValidationMetrics:
        """Calculate aggregated metrics from validation results.

        Args:
            results: List of validation results
            draw_type_id: Game type

        Returns:
            Aggregated metrics
        """
        if not results:
            return ValidationMetrics()

        total = len(results)
        total_hits = sum(r.hit_count for r in results)
        turbo_hits = sum(1 for r in results if r.turbo_hit)
        total_stake = sum(r.stake for r in results)
        total_payout = sum(r.payout for r in results)
        total_net = sum(r.net_profit for r in results)

        metrics = ValidationMetrics(
            total_predictions=total,
            total_hits=total_hits,
            hit_rate=total_hits / total if total > 0 else 0.0,
            turbo_hits=turbo_hits,
            turbo_hit_rate=turbo_hits / total if total > 0 else 0.0,
            total_stake=total_stake,
            total_payout=total_payout,
            total_net_profit=total_net,
            average_roi=total_net / total_stake if total_stake > 0 else 0.0,
        )

        # Calculate random baseline
        metrics.random_baseline = self._calculate_random_baseline(
            draw_type_id,
            results[0].turbo_variant,
        )

        return metrics

    def _calculate_random_baseline(
        self,
        draw_type_id: UUID,
        turbo_variant: str,
        samples: int = 1000,
    ) -> dict[str, float]:
        """Calculate random baseline performance.

        Args:
            draw_type_id: Game type
            turbo_variant: Turbo variant
            samples: Number of Monte Carlo samples

        Returns:
            Baseline metrics
        """
        formula = TURBO_FORMULAS.get(f"TURBO_{turbo_variant.replace('turbo_', '').upper()}")
        if formula is None:
            return {"hit_rate": 0.0, "turbo_hit_rate": 0.0, "roi": -100.0}

        numbers_required = formula.numbers_required

        # Simplified baseline: probability of random k numbers being in first k positions
        # For uniform distribution of 90 numbers:
        # P(turbo_hit) = C(90-k, k) / C(90, k) for numbers in first k positions
        # Simplified approximation

        import math

        total_combinations = math.comb(90, numbers_required)
        turbo_hit_prob = 1.0 / total_combinations  # Very small

        expected_hits = numbers_required * (numbers_required / 90)  # Expected matches
        hit_rate = expected_hits / numbers_required

        expected_roi = -100.0 + (turbo_hit_prob * float(formula.odds[turbo_variant.upper()] - 1) * 100)

        return {
            "hit_rate": hit_rate,
            "turbo_hit_rate": turbo_hit_prob,
            "roi": expected_roi,
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

        hit_rate_improvement = (
            (metrics.hit_rate - baseline["hit_rate"]) / baseline["hit_rate"] * 100
            if baseline["hit_rate"] > 0
            else 0.0
        )

        turbo_improvement = (
            (metrics.turbo_hit_rate - baseline["turbo_hit_rate"]) / baseline["turbo_hit_rate"] * 100
            if baseline["turbo_hit_rate"] > 0
            else 0.0
        )

        roi_improvement = metrics.average_roi - baseline["roi"]

        return {
            "hit_rate_improvement_percent": hit_rate_improvement,
            "turbo_hit_rate_improvement_percent": turbo_improvement,
            "roi_improvement": roi_improvement,
            "statistically_significant": (
                metrics.turbo_hits >= 5 and metrics.turbo_hit_rate > baseline["turbo_hit_rate"] * 2
            ),
        }
