"""Digital Root transformation for lottery number analysis.

Digital root (racine numérique) is the recursive sum of digits until a single digit is obtained.
Convention: digital root 9 is represented as 0.

Examples:
    74 → 7 + 4 = 11 → 1 + 1 = 2
    45 → 4 + 5 = 9 → 0
    86 → 8 + 6 = 14 → 1 + 4 = 5
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

NUMBERS_MIN = 1
NUMBERS_MAX = 90


def digital_root(number: int) -> int:
    """Calculate digital root of a number (1-90).

    Args:
        number: Number between 1 and 90

    Returns:
        Digital root (0-8, where 0 represents 9)

    Raises:
        ValueError: If number is out of valid range
    """
    if not (NUMBERS_MIN <= number <= NUMBERS_MAX):
        raise ValueError(f"Number must be between {NUMBERS_MIN} and {NUMBERS_MAX}, got {number}")

    n = number
    while n >= 10:
        n = sum(int(d) for d in str(n))

    # Convention: 9 is represented as 0
    return 0 if n == 9 else n


def digital_root_batch(numbers: Sequence[int]) -> dict[int, int]:
    """Calculate digital roots for multiple numbers.

    Args:
        numbers: Sequence of numbers between 1 and 90

    Returns:
        Dictionary mapping number → digital root
    """
    return {n: digital_root(n) for n in numbers}


def numbers_by_root(root: int) -> list[int]:
    """Get all numbers (1-90) that have a specific digital root.

    Args:
        root: Digital root (0-8)

    Returns:
        List of numbers with that digital root

    Example:
        >>> numbers_by_root(3)
        [3, 12, 21, 30, 39, 48, 57, 66, 75, 84]
    """
    if not (0 <= root <= 8):
        raise ValueError(f"Root must be between 0 and 8, got {root}")

    # Root 0 corresponds to digital root 9
    target_root = 9 if root == 0 else root

    result = []
    for n in range(NUMBERS_MIN, NUMBERS_MAX + 1):
        dr = n
        while dr >= 10:
            dr = sum(int(d) for d in str(dr))
        if dr == target_root:
            result.append(n)

    return result


@dataclass(frozen=True, slots=True)
class NumberWithRoot:
    """A number with its digital root."""
    number: int
    root: int

    @classmethod
    def from_number(cls, number: int) -> "NumberWithRoot":
        """Create from a single number."""
        return cls(number=number, root=digital_root(number))


def transform_sequence(numbers: Sequence[int]) -> list[NumberWithRoot]:
    """Transform a sequence of numbers into NumberWithRoot objects.

    Args:
        numbers: Sequence of numbers in their original order

    Returns:
        List of NumberWithRoot objects preserving order
    """
    return [NumberWithRoot.from_number(n) for n in numbers]


# Precomputed lookup tables for performance
_ROOT_TO_NUMBERS: dict[int, list[int]] = {r: numbers_by_root(r) for r in range(9)}
_NUMBER_TO_ROOT: dict[int, int] = digital_root_batch(range(NUMBERS_MIN, NUMBERS_MAX + 1))


def get_numbers_by_root_fast(root: int) -> list[int]:
    """Fast lookup using precomputed table."""
    return _ROOT_TO_NUMBERS[root].copy()


def get_root_fast(number: int) -> int:
    """Fast lookup using precomputed table."""
    return _NUMBER_TO_ROOT[number]
