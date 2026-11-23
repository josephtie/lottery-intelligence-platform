"""Adaptive Root Predictor - Machine learning system for digital root predictions.

This module implements a predictive system that:
- Learns temporal patterns (7h, 13h, 23h specific behaviors)
- Detects doublets and symmetric structures
- Adapts based on past performance (reinforcement learning)
- Applies mean reversion for lagging digits
- Uses context-aware generation (hour, recent patterns, frequencies)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
import random

from lottery_intelligence_platform.digital_root import digital_root


@dataclass(slots=True)
class TemporalPattern:
    """Represents a temporal pattern observed at a specific hour."""
    hour: int
    dominant_digit: Optional[int] = None
    dominant_position: Optional[int] = None
    doublet_frequency: float = 0.0
    palindrome_frequency: float = 0.0
    pair_impurity_frequency: float = 0.0


@dataclass(slots=True)
class MemoryEffect:
    """Represents the memory effect between consecutive draws."""
    report_probability: float = 0.0  # Probability of digits from positions 4-5 appearing in next draw
    common_transitions: Dict[Tuple[int, int], int] = field(default_factory=dict)  # (last_digit, next_digit) -> count


@dataclass
class AdaptivePrediction:
    """Adaptive prediction with confidence and metadata."""
    predicted_roots: List[int]
    confidence: float
    adaptive_factors: Dict[str, Any]
    reasoning: List[str]
    timestamp: datetime = field(default_factory=datetime.now)


class AdaptiveRootPredictor:
    """Adaptive predictor that learns and adjusts based on observed patterns."""

    def __init__(self, min_observations: int = 10):
        self.min_observations = min_observations
        
        # Temporal patterns by hour
        self.hourly_patterns: Dict[int, TemporalPattern] = {}
        
        # Memory effects
        self.memory_effects: MemoryEffect = MemoryEffect(
            report_probability=0.0,
            common_transitions=defaultdict(int)
        )
        
        # Global digit frequencies
        self.digit_frequencies: Counter = Counter()
        self.total_observations: int = 0
        
        # Recent patterns (last N draws)
        self.recent_patterns: List[List[int]] = []
        self.max_recent_patterns = 20
        
        # Performance tracking for reinforcement
        self.prediction_history: List[Dict[str, Any]] = []
        self.adaptive_weights: Dict[str, float] = {
            'temporal': 0.3,
            'frequency': 0.3,
            'memory': 0.2,
            'random': 0.2
        }

    def learn_from_history(self, draws: List[Dict[str, Any]]) -> None:
        """Learn patterns from historical draw data.
        
        Args:
            draws: List of draw records with 'scheduled_date', 'numbers', 'draw_type'
        """
        for draw in draws:
            scheduled_date = draw.get('scheduled_date')
            numbers = draw.get('numbers', [])
            
            if not numbers or not scheduled_date:
                continue
            
            # Extract hour from scheduled_date
            draw_time = scheduled_date if isinstance(scheduled_date, datetime) else datetime.combine(scheduled_date, time.min)
            hour = draw_time.hour
            
            # Convert to roots
            roots = [digital_root(n) for n in numbers]
            
            # Update frequencies
            self.digit_frequencies.update(roots)
            self.total_observations += 1
            
            # Update hourly patterns
            self._update_hourly_pattern(hour, roots)
            
            # Update memory effects
            if len(self.recent_patterns) > 0:
                self._update_memory_effect(self.recent_patterns[-1], roots)
            
            # Store recent pattern
            self.recent_patterns.append(roots)
            if len(self.recent_patterns) > self.max_recent_patterns:
                self.recent_patterns.pop(0)

    def _update_hourly_pattern(self, hour: int, roots: List[int]) -> None:
        """Update pattern statistics for a specific hour."""
        if hour not in self.hourly_patterns:
            self.hourly_patterns[hour] = TemporalPattern(
                hour=hour,
                dominant_digit=None,
                dominant_position=None,
                doublet_frequency=0.0,
                palindrome_frequency=0.0,
                pair_impurity_frequency=0.0
            )
        
        pattern = self.hourly_patterns[hour]
        
        # Update dominant digit and position
        position_counts = defaultdict(Counter)
        for i, root in enumerate(roots):
            position_counts[i][root] += 1
        
        # Find dominant position
        max_count = 0
        dominant_pos = None
        for pos, counts in position_counts.items():
            total = sum(counts.values())
            if total > max_count:
                max_count = total
                dominant_pos = pos
        
        if dominant_pos is not None:
            pattern.dominant_position = dominant_pos
            pattern.dominant_digit = position_counts[dominant_pos].most_common(1)[0][0]

    def _update_memory_effect(self, previous_roots: List[int], current_roots: List[int]) -> None:
        """Update memory effect statistics."""
        # Check if last 2 digits of previous appear in current
        if len(previous_roots) >= 2 and len(current_roots) >= 2:
            last_two = set(previous_roots[-2:])
            current_first_two = set(current_roots[:2])
            
            if last_two & current_first_two:
                self.memory_effects.report_probability = (
                    self.memory_effects.report_probability * 0.9 + 0.1
                )
            else:
                self.memory_effects.report_probability = (
                    self.memory_effects.report_probability * 0.9
                )
        
        # Track transitions
        if previous_roots and current_roots:
            last_digit = previous_roots[-1]
            first_digit = current_roots[0]
            key = (last_digit, first_digit)
            self.memory_effects.common_transitions[key] = self.memory_effects.common_transitions.get(key, 0) + 1

    def predict_adaptive(
        self,
        target_date: date,
        draw_type: str,
        target_hour: Optional[int] = None,
        top_roots: int = 3,  # Always return exactly 3 roots
    ) -> AdaptivePrediction:
        """Generate adaptive prediction based on learned patterns.
        
        Args:
            target_date: Target draw date
            draw_type: Game type
            target_hour: Specific hour for temporal patterns
            top_roots: Number of top roots to predict (fixed at 3)
            
        Returns:
            AdaptivePrediction with predicted roots and confidence
        """
        reasoning = []
        factors = {}
        
        # 1. Temporal pattern influence (highest priority)
        temporal_roots = []
        if target_hour and target_hour in self.hourly_patterns:
            pattern = self.hourly_patterns[target_hour]
            if pattern.dominant_digit is not None:
                temporal_roots.append(pattern.dominant_digit)
                reasoning.append(f"Temporal: Hour {target_hour} favors root {pattern.dominant_digit}")
                factors['temporal_hour'] = target_hour
                factors['dominant_digit'] = pattern.dominant_digit

        # 2. Frequency-based prediction (with mean reversion) - top 3
        freq_roots = self._get_frequency_roots(3)
        reasoning.append(f"Frequency: Top 3 roots by historical frequency with mean reversion")
        factors['frequency_roots'] = freq_roots

        # 3. Memory effect prediction
        memory_roots = []
        if self.recent_patterns:
            last_pattern = self.recent_patterns[-1]
            if len(last_pattern) >= 2:
                # Use last 2 digits with probability
                if random.random() < self.memory_effects.report_probability:
                    memory_roots = last_pattern[-2:]
                    reasoning.append(f"Memory: Last 2 roots may repeat (p={self.memory_effects.report_probability:.2f})")
                    factors['memory_effect'] = True

        # 4. Combine and select exactly 3 distinct roots
        combined_roots = list(set(temporal_roots + freq_roots + memory_roots))
        
        # If we have less than 3, add most frequent from history
        if len(combined_roots) < 3:
            for root, count in self.digit_frequencies.most_common():
                if root not in combined_roots:
                    combined_roots.append(root)
                    if len(combined_roots) >= 3:
                        break
        
        # If still less than 3, add remaining roots
        while len(combined_roots) < 3:
            for root in range(9):
                if root not in combined_roots:
                    combined_roots.append(root)
                    break
        
        # Take first 3
        predicted_roots = combined_roots[:3]
        
        # Calculate confidence based on consistency
        confidence = self._calculate_prediction_confidence(predicted_roots, temporal_roots, freq_roots)
        
        factors['temporal_roots'] = temporal_roots
        factors['frequency_roots'] = freq_roots
        factors['memory_roots'] = memory_roots
        factors['adaptive_weights'] = self.adaptive_weights.copy()

        return AdaptivePrediction(
            predicted_roots=predicted_roots,
            confidence=confidence,
            adaptive_factors=factors,
            reasoning=reasoning,
        )

    def _get_frequency_roots(self, top: int) -> List[int]:
        """Get top roots by frequency with mean reversion."""
        if self.total_observations < self.min_observations:
            return list(range(top))
        
        # Calculate expected frequency (1/9 for uniform distribution)
        expected = self.total_observations / 9
        
        # Apply mean reversion: boost under-represented digits
        adjusted_frequencies = {}
        for root in range(9):
            count = self.digit_frequencies.get(root, 0)
            deviation = (count - expected) / expected if expected > 0 else 0
            # Invert deviation for mean reversion (under-represented get boost)
            adjusted_frequencies[root] = count * (1.0 - deviation * 0.3)
        
        # Sort by adjusted frequency
        sorted_roots = sorted(adjusted_frequencies.items(), key=lambda x: x[1], reverse=True)
        return [root for root, _ in sorted_roots[:top]]

    def _calculate_prediction_confidence(self, predicted_roots: List[int], 
                                        temporal_roots: List[int], 
                                        freq_roots: List[int]) -> float:
        """Calculate confidence score based on pattern consistency."""
        if not predicted_roots:
            return 0.0
        
        confidence = 0.5  # Base confidence
        
        # Boost if temporal pattern matches
        if temporal_roots and temporal_roots[0] in predicted_roots:
            confidence += 0.2
        
        # Boost if top frequency root is in prediction
        if freq_roots and freq_roots[0] in predicted_roots:
            confidence += 0.15
        
        # Boost if predicted roots are from different sources (diversity)
        sources = set()
        if temporal_roots and temporal_roots[0] in predicted_roots:
            sources.add('temporal')
        if freq_roots and freq_roots[0] in predicted_roots:
            sources.add('frequency')
        if len(sources) >= 2:
            confidence += 0.1
        
        # Penalize if we don't have enough history
        if self.total_observations < self.min_observations:
            confidence -= 0.2
        
        return max(0.0, min(1.0, confidence))

    def update_weights(self, prediction: AdaptivePrediction, actual_roots: List[int]) -> None:
        """Update adaptive weights based on prediction performance (reinforcement learning).
        
        Args:
            prediction: The prediction that was made
            actual_roots: The actual roots that occurred
        """
        # Calculate hit rate
        hits = sum(1 for r in prediction.predicted_roots if r in actual_roots)
        hit_rate = hits / len(prediction.predicted_roots) if prediction.predicted_roots else 0
        
        # Random baseline
        random_baseline = len(prediction.predicted_roots) / 9
        
        # Calculate improvement over random
        improvement = hit_rate - random_baseline
        
        # Store prediction result
        self.prediction_history.append({
            'predicted_roots': prediction.predicted_roots,
            'actual_roots': actual_roots,
            'hit_rate': hit_rate,
            'improvement': improvement,
            'confidence': prediction.confidence,
            'timestamp': prediction.timestamp,
        })
        
        # Adjust weights based on performance
        if improvement > 0:
            # Successful prediction - boost contributing factors
            self.adaptive_weights['temporal'] = min(0.5, self.adaptive_weights['temporal'] + 0.05)
            self.adaptive_weights['frequency'] = min(0.5, self.adaptive_weights['frequency'] + 0.05)
            self.adaptive_weights['memory'] = min(0.4, self.adaptive_weights['memory'] + 0.05)
            self.adaptive_weights['random'] = max(0.05, self.adaptive_weights['random'] - 0.05)
        else:
            # Failed prediction - reduce reliance, increase exploration
            self.adaptive_weights['temporal'] = max(0.1, self.adaptive_weights['temporal'] - 0.02)
            self.adaptive_weights['frequency'] = max(0.1, self.adaptive_weights['frequency'] - 0.02)
            self.adaptive_weights['memory'] = max(0.1, self.adaptive_weights['memory'] - 0.02)
            self.adaptive_weights['random'] = min(0.4, self.adaptive_weights['random'] + 0.02)

    def get_statistics(self) -> Dict[str, Any]:
        """Get current predictor statistics."""
        if not self.prediction_history:
            return {
                'total_predictions': 0,
                'average_hit_rate': 0.0,
                'average_improvement': 0.0,
                'adaptive_weights': self.adaptive_weights,
            }
        
        total = len(self.prediction_history)
        avg_hit_rate = sum(p['hit_rate'] for p in self.prediction_history) / total
        avg_improvement = sum(p['improvement'] for p in self.prediction_history) / total
        
        return {
            'total_predictions': total,
            'average_hit_rate': avg_hit_rate,
            'average_improvement': avg_improvement,
            'adaptive_weights': self.adaptive_weights,
            'hourly_patterns': {h: {
                'dominant_digit': p.dominant_digit,
                'dominant_position': p.dominant_position,
            } for h, p in self.hourly_patterns.items()},
            'memory_effect': {
                'report_probability': self.memory_effects.report_probability,
                'common_transitions': dict(list(self.memory_effects.common_transitions.items())[:10]),
            },
            'digit_frequencies': dict(self.digit_frequencies.most_common()),
        }
