"""Reduced Field Generator - Mathematical analysis for lottery predictions.

This module implements a reduced field strategy based on:
- Digital root analysis (0-8)
- Position-based patterns (1st, 2nd, 3rd positions)
- Historical frequency analysis
- Zone dominance and mirror patterns
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter, defaultdict

from lottery_intelligence_platform.digital_root import digital_root


@dataclass
class ReducedFieldTicket:
    """A reduced field ticket with base and associated numbers."""
    base: int  # Fixed base number (1st position)
    base_root: int  # Digital root of base
    base_family: List[int]  # Family numbers (same root)
    associated: List[int]  # Associated numbers (2nd position)
    associated_roots: List[int]  # Roots of associated numbers
    associated_families: List[List[int]]  # Families of associated numbers
    third_position: Optional[List[int]] = None  # Third position coverage (Turbo)
    third_roots: Optional[List[int]] = None  # Roots of third position
    strategy: str = ""  # Strategy name
    confidence: float = 0.0  # Confidence score


class ReducedFieldGenerator:
    """Generate reduced field tickets based on mathematical analysis."""
    
    # Root to family mapping (0-8 roots to their families)
    ROOT_FAMILIES = {
        0: [9, 18, 27, 36, 45, 54, 63, 72, 81, 90],
        1: [1, 10, 19, 28, 37, 46, 55, 64, 73, 82],
        2: [2, 11, 20, 29, 38, 47, 56, 65, 74, 83],
        3: [3, 12, 21, 30, 39, 48, 57, 66, 75, 84],
        4: [4, 13, 22, 31, 40, 49, 58, 67, 76, 85],
        5: [5, 14, 23, 32, 41, 50, 59, 68, 77, 86],
        6: [6, 15, 24, 33, 42, 51, 60, 69, 78, 87],
        7: [7, 16, 25, 34, 43, 52, 61, 70, 79, 88],
        8: [8, 17, 26, 35, 44, 53, 62, 71, 80, 89],
    }
    
    def __init__(self, min_observations: int = 5):
        self.min_observations = min_observations
        self.draw_history: List[List[int]] = []
        self.root_history: List[List[int]] = []
        self.position_analysis: Dict[int, Counter] = defaultdict(Counter)
        self.number_frequency: Counter = Counter()
        self.root_frequency: Counter = Counter()
        
    def add_draw(self, numbers: List[int]) -> None:
        """Add a draw to the history."""
        self.draw_history.append(numbers)
        roots = [digital_root(n) for n in numbers]
        self.root_history.append(roots)
        
        # Update position analysis
        for pos, (num, root) in enumerate(zip(numbers, roots)):
            self.position_analysis[pos][num] += 1
            self.number_frequency[num] += 1
            self.root_frequency[root] += 1
    
    def analyze_position_patterns(self) -> Dict[str, Any]:
        """Analyze patterns by position."""
        if not self.draw_history:
            return {}
        
        analysis = {
            "total_draws": len(self.draw_history),
            "position_1_frequency": dict(self.position_analysis[0].most_common(10)),
            "position_2_frequency": dict(self.position_analysis[1].most_common(10)),
            "position_3_frequency": dict(self.position_analysis[2].most_common(10)),
            "root_frequency": dict(self.root_frequency.most_common()),
            "most_frequent_numbers": dict(self.number_frequency.most_common(10)),
        }
        
        # Analyze position 2 parity
        pos2_roots = [draw[1] for draw in self.root_history if len(draw) > 1]
        pos2_parity = {"even": 0, "odd": 0}
        for root in pos2_roots:
            if root % 2 == 0:
                pos2_parity["even"] += 1
            else:
                pos2_parity["odd"] += 1
        analysis["position_2_parity"] = pos2_parity
        
        return analysis
    
    def _get_base_candidates(self) -> List[Tuple[int, str, float]]:
        """Get candidates for base position (1st position)."""
        if not self.position_analysis[0]:
            return []
        
        candidates = []
        for num, count in self.position_analysis[0].most_common(5):
            frequency = count / len(self.draw_history)
            candidates.append((num, f"Leader in position 1 ({frequency:.1%})", frequency))
        
        # Add missing numbers for catch-up
        if len(self.draw_history) >= 5:
            all_numbers = set(range(1, 91))
            recent_numbers = set(num for draw in self.draw_history[-5:] for num in draw)
            missing = all_numbers - recent_numbers
            for num in list(missing)[:3]:
                candidates.append((num, "Catch-up candidate", 0.1))
        
        return candidates
    
    def _get_associated_candidates(self, base_num: int, count: int = 4) -> List[int]:
        """Get associated numbers for 2nd position."""
        base_root = digital_root(base_num)
        
        # Prioritize:
        # 1. Numbers from same zone (high/low)
        # 2. Hot numbers (frequent)
        # 3. Mirrors and neighbors
        # 4. Missing roots
        
        # Determine zone dominance
        high_numbers = sum(1 for draw in self.draw_history for num in draw if num >= 49)
        total_numbers = sum(len(draw) for draw in self.draw_history)
        high_dominance = high_numbers / total_numbers if total_numbers > 0 else 0.5
        
        zone_target = "high" if high_dominance > 0.5 else "low"
        
        candidates = []
        
        # Get position 2 frequency
        pos2_freq = self.position_analysis[1]
        
        # 1. Hot numbers in position 2 from target zone
        for num, freq in pos2_freq.most_common():
            num_root = digital_root(num)
            if (zone_target == "high" and num >= 49) or (zone_target == "low" and num < 49):
                if num not in candidates:
                    candidates.append(num)
                    if len(candidates) >= count:
                        break
        
        # 2. If not enough, add other hot numbers
        if len(candidates) < count:
            for num, freq in pos2_freq.most_common():
                if num not in candidates:
                    candidates.append(num)
                    if len(candidates) >= count:
                        break
        
        # 3. If still not enough, add mirrors and neighbors
        if len(candidates) < count:
            # Mirror: 18 <-> 81, 58 <-> 85, etc.
            for num in self.number_frequency.most_common(20):
                mirror = self._get_mirror(num)
                if mirror and mirror not in candidates:
                    candidates.append(mirror)
                    if len(candidates) >= count:
                        break
        
        # 4. If still not enough, add missing roots
        if len(candidates) < count:
            missing_roots = [r for r in range(9) if r not in self.root_frequency]
            for root in missing_roots:
                for num in self.ROOT_FAMILIES[root]:
                    if num not in candidates:
                        candidates.append(num)
                        if len(candidates) >= count:
                            break
        
        return candidates[:count]
    
    def _get_mirror(self, num: int) -> Optional[int]:
        """Get mirror number (digit reversal logic)."""
        if num < 10:
            return None
        tens = num // 10
        units = num % 10
        mirror = units * 10 + tens
        if 1 <= mirror <= 90:
            return mirror
        return None
    
    def _get_third_position_candidates(self, count: int = 3) -> List[int]:
        """Get candidates for 3rd position (Turbo coverage)."""
        if not self.position_analysis[2]:
            return []
        
        candidates = []
        
        # 1. Missing roots (critical unblock)
        missing_roots = [r for r in range(9) if r not in self.root_frequency]
        for root in missing_roots:
            for num in self.ROOT_FAMILIES[root]:
                if num not in candidates:
                    candidates.append(num)
                    if len(candidates) >= count:
                        break
        
        # 2. Hot numbers from position 3
        if len(candidates) < count:
            for num, freq in self.position_analysis[2].most_common():
                if num not in candidates:
                    candidates.append(num)
                    if len(candidates) >= count:
                        break
        
        return candidates[:count]
    
    def generate_reduced_field_tickets(self, with_turbo: bool = False) -> List[ReducedFieldTicket]:
        """Generate reduced field tickets.
        
        Args:
            with_turbo: If True, include 3rd position coverage (Turbo)
            
        Returns:
            List of ReducedFieldTicket objects
        """
        if len(self.draw_history) < self.min_observations:
            return []
        
        tickets = []
        base_candidates = self._get_base_candidates()
        
        strategies = [
            ("Leader Historique", "Leader in position 1"),
            ("Session Engine", "Most frequent overall"),
            ("Critical Catch-up", "Catch-up candidate"),
            ("Arithmetic Pattern", "Pattern-based selection"),
        ]
        
        for i, (base_num, reason, confidence) in enumerate(base_candidates[:4]):
            base_root = digital_root(base_num)
            base_family = self.ROOT_FAMILIES[base_root]
            
            # Get associated numbers for 2nd position
            associated = self._get_associated_candidates(base_num, count=4)
            associated_roots = [digital_root(n) for n in associated]
            associated_families = [self.ROOT_FAMILIES[digital_root(n)] for n in associated]
            
            # Get third position candidates if turbo mode
            third_position = None
            third_roots = None
            if with_turbo:
                third_position = self._get_third_position_candidates(count=3)
                third_roots = [digital_root(n) for n in third_position]
            
            ticket = ReducedFieldTicket(
                base=base_num,
                base_root=base_root,
                base_family=base_family,
                associated=associated,
                associated_roots=associated_roots,
                associated_families=associated_families,
                third_position=third_position,
                third_roots=third_roots,
                strategy=strategies[i][0],
                confidence=confidence,
            )
            tickets.append(ticket)
        
        return tickets
    
    def get_analysis_report(self) -> Dict[str, Any]:
        """Get comprehensive analysis report."""
        patterns = self.analyze_position_patterns()
        tickets = self.generate_reduced_field_tickets(with_turbo=False)
        turbo_tickets = self.generate_reduced_field_tickets(with_turbo=True)
        
        return {
            "patterns": patterns,
            "reduced_field_tickets": [
                {
                    "strategy": t.strategy,
                    "base": t.base,
                    "base_root": t.base_root,
                    "base_family": t.base_family,
                    "associated": t.associated,
                    "associated_roots": t.associated_roots,
                    "confidence": t.confidence,
                }
                for t in tickets
            ],
            "turbo_tickets": [
                {
                    "strategy": t.strategy,
                    "base": t.base,
                    "associated": t.associated,
                    "third_position": t.third_position,
                    "combinations": f"{len(t.associated)}x{len(t.third_position)} = {len(t.associated) * len(t.third_position)}",
                }
                for t in turbo_tickets
            ],
        }
